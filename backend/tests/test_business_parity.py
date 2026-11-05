"""LangGraph business payload, recovery, retry and cancellation regressions."""
import asyncio
import json
from datetime import date
from pathlib import Path
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import TypeAdapter
from langgraph.errors import NodeCancelledError
import test_mock_workflow as business_helpers
import test_full_backend as backend
from shared.contracts import TripRequest, WorkflowState
from ai.orchestration.graph_workflow import LangGraphOrchestrator
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.workflow_state import OUTPUTS, REFS, STEPS, StateMachine

# Contract and boundary assertions run directly in test_mock_workflow and test_full_backend.
IDENTITY = dict(trip_id=UUID(int=101), request_id=UUID(int=102))


def execute(components, data, **kwargs):
    return asyncio.run(LangGraphOrchestrator(components, defaults=fixture('planner_defaults')).run(
        TripRequest.model_validate(data), current_date=date(2026, 11, 2), **IDENTITY, **kwargs))


def business(run):
    """Validate contract payloads; only generated artifact IDs are excluded."""
    payloads = {ref: run.artifacts[getattr(run.state.artifacts, ref)]
                for ref in REFS if ref and getattr(run.state.artifacts, ref)}
    for checkpoint in run.checkpoints:
        WorkflowState.model_validate(checkpoint.model_dump())
        assert all(value in run.artifacts for value in checkpoint.artifacts.model_dump().values() if value)
    for index, ref in enumerate(REFS):
        if ref in payloads:
            TypeAdapter(OUTPUTS[index]).validate_python(payloads[ref])
    return dict(status=run.state.status, pending=run.state.pending_fields,
                clarification_round=run.state.clarification_round,
                destination_round=run.state.destination_round, retry_count=run.state.retry_count,
                questions=[q.model_dump(mode='json') for q in run.pending_questions],
                answers=[a.model_dump(mode='json') for a in run.answers_history],
                final=run.final_result.model_dump(mode='json') if run.final_result else None,
                explanation=run.explanation, payloads=payloads,
                attempts=[(a.result, a.random_seed) for a in run.attempts])


@pytest.mark.parametrize('scenario', ['happy', 'missing', 'destination', 'resume', 'unknown', 'replan'])
def test_identical_fixtures_preserve_complete_business_payloads(scenario):
    data, components = fixture('trip_request'), mock_components()
    if scenario in {'missing', 'resume', 'unknown'}:
        data['budget']['amount'] = None
    if scenario == 'destination':
        data['destination'].update(selection_mode='ambiguous', city=None,
                                  candidate_cities=['Da Lat', 'Nha Trang'])
    if scenario == 'replan':
        original = components.validator.validate
        calls = 0
        async def validate(itinerary, planning_input, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {**business_helpers.rejected(), 'trip_id': planning_input.trip_id}
            return await original(itinerary, planning_input, **kwargs)
        components.validator.validate = validate
    result = execute(components, data)
    if scenario in {'resume', 'unknown'}:
        before = result.model_dump_json()
        if scenario == 'resume':
            data['budget']['amount'] = 3000000
        else:
            data['meta']['field_sources']['budget.amount'] = 'user'
        resumed = execute(components, data, previous=result, answer_raw='answer')
        assert result.model_dump_json() == before
        result = resumed
    payload = business(result)
    # Freeze the full contract payloads from the graph verified by the removal
    # gate, excluding generated artifact IDs only. Do not regenerate in tests.
    expected = json.loads(Path(__file__).with_name('business_payloads.json').read_text(encoding='utf-8'))
    assert json.loads(json.dumps(payload)) == expected[scenario]
    expected_status = ('clarifying' if scenario in {'missing', 'destination'} else 'completed')
    assert payload['status'] == expected_status
    if expected_status == 'completed':
        assert payload['final'] is not None and payload['explanation']
        assert payload['payloads']['itinerary_id'] == payload['final']
        assert payload['payloads']['validation_result_id']['is_valid'] is True
        assert len(payload['payloads']) == 8
        assert payload['attempts'][-1][0] == 'accepted'
    else:
        assert payload['final'] is None and payload['explanation'] is None
        assert payload['pending'] and payload['questions']
    if scenario in {'resume', 'unknown'}:
        assert len(payload['answers']) == 1
        field = 'resolved_fields' if scenario == 'resume' else 'declared_unknown_fields'
        assert payload['answers'][0][field] == ['budget.amount']
    if scenario == 'replan':
        assert payload['attempts'] == [('hard_violation', 42), ('accepted', 43)]


@pytest.mark.parametrize('status', ['partial', 'infeasible'])
@pytest.mark.parametrize('suggestions', [False, True])
def test_infeasible_business_safety_with_dynamic_recovery(status, suggestions):
    components = mock_components()
    async def plan(planning_input):
        data = fixture('itinerary')
        data.update(trip_id=planning_input.trip_id, status=status,
                    relaxation_suggestions=[dict(constraint_type='budget', description='Increase',
                        payload={'amount': 4000000})] if suggestions else [])
        data['diagnostics'].update(solver_status=status, unsatisfied_constraints=['Unavailable'])
        return data
    components.planning_engine.plan = plan
    business_helpers.attach_validation(components, business_helpers.rejected('ask_user' if suggestions else 'fail'))
    result = execute(components, fixture('trip_request'))
    assert result.state.status == ('awaiting_relaxation' if suggestions else 'failed')
    assert result.final_result is None and result.explanation is None
    assert all(a.result == 'infeasible' for a in result.attempts)
    assert 'explainer' not in result.state.completed_steps
    if not suggestions:
        assert len(result.attempts) > 1


def test_cost_id_mismatch_refreshes_without_reaching_engine():
    components = mock_components()
    original = components.budget_module.estimate
    async def estimate(*args, **kwargs):
        result = await original(*args, **kwargs)
        result.places[0].place_id = 'wrong'
        return result
    components.budget_module.estimate = estimate
    components.planning_engine.plan = AsyncMock()
    result = execute(components, fixture('trip_request'))
    assert result.state.status == 'failed' and result.final_result is None
    assert result.visits['place_agent'] > 1
    components.planning_engine.plan.assert_not_awaited()

# Block external sockets for this suite as in the existing offline backend QA.
offline = backend.offline


def test_retry_exhaustion_keeps_attempt_contracts():
    components = mock_components()
    rejected = business_helpers.rejected()
    rejected['violations'][0]['rule'] = 'overlap'
    business_helpers.attach_validation(components, rejected)
    result = execute(components, fixture('trip_request'))
    assert result.state.status == 'failed' and result.final_result is None
    assert result.state.retry_count == 3
    assert [a.random_seed for a in result.attempts] == [42, 43, 44, 45]
    assert len({a.itinerary_id for a in result.attempts}) == 4
    for attempt in result.attempts:
        assert attempt.itinerary_id in result.artifacts
        assert attempt.validation_result_id in result.artifacts
    assert all(a.result == 'hard_violation' for a in result.attempts)


@pytest.mark.parametrize('external', [False, True], ids=['component', 'external'])
@pytest.mark.parametrize('step', STEPS)
def test_cancellation_stops_workflow(external, step, monkeypatch):
    async def scenario():
        entered = asyncio.Event()
        components = mock_components()
        cancellation = asyncio.CancelledError('component cancelled')
        cleaned_up = asyncio.Event()
        async def cancel(*args, **kwargs):
            entered.set()
            try:
                if external:
                    await asyncio.Event().wait()
                raise cancellation
            finally:
                cleaned_up.set()
        methods = backend.METHODS
        target = AsyncMock(side_effect=cancel)
        setattr(getattr(components, step), methods[STEPS.index(step)], target)
        downstream = []
        for name, method in zip(STEPS[STEPS.index(step) + 1:], methods[STEPS.index(step) + 1:]):
            mock = AsyncMock()
            setattr(getattr(components, name), method, mock)
            downstream.append(mock)
        workflow = LangGraphOrchestrator(components, defaults=fixture('planner_defaults'))
        snapshots = []
        original_update = StateMachine.update
        def observe(sm, **changes):
            original_update(sm, **changes)
            snapshots.append(sm.run)
        monkeypatch.setattr(StateMachine, 'update', observe)
        persistence = MagicMock()
        workflow.persistence = persistence
        task = asyncio.create_task(workflow.run(
            TripRequest.model_validate(fixture('trip_request')), current_date=date(2026, 11, 2)))
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            if external:
                task.cancel('external cancelled')
            with pytest.raises(asyncio.CancelledError) as caught:
                await task
            if not external:
                assert caught.value is cancellation
            else:
                assert caught.value.args == ('external cancelled',)
            assert task.cancelled() and cleaned_up.is_set()
            target.assert_awaited_once()
            for mock in downstream:
                mock.assert_not_awaited()
            assert snapshots
            assert all(r.state.status != 'completed' and r.final_result is None
                       and r.explanation is None and not r.errors for r in snapshots)
            persistence.sync.assert_not_called()
            persistence.save_graph.assert_not_called()
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    asyncio.run(scenario())


@pytest.mark.parametrize('cause', [None, RuntimeError('unrelated')])
def test_node_cancellation_without_cancelled_cause_is_not_reclassified(cause):
    workflow = LangGraphOrchestrator(mock_components(), defaults=fixture('planner_defaults'))
    error = NodeCancelledError('place_agent')
    error.__cause__ = cause
    workflow.graph.ainvoke = AsyncMock(side_effect=error)
    with pytest.raises(NodeCancelledError) as caught:
        asyncio.run(workflow.run(TripRequest.model_validate(fixture('trip_request')),
                                current_date=date(2026, 11, 2)))
    assert caught.value is error
