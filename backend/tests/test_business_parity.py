"""LangGraph recovery, retry and cancellation regressions."""
import asyncio
from datetime import date
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import pytest
import test_mock_workflow as business_helpers
import test_full_backend as backend
from shared.contracts import TripRequest
from ai.orchestration.graph_workflow import LangGraphOrchestrator
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.workflow_state import STEPS, StateMachine

IDENTITY = dict(trip_id=UUID(int=101), request_id=UUID(int=102))


def execute(components, data, **kwargs):
    return asyncio.run(LangGraphOrchestrator(components, defaults=fixture('planner_defaults')).run(
        TripRequest.model_validate(data), current_date=date(2026, 11, 2), **IDENTITY, **kwargs))


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


def test_repair_exhaustion_keeps_attempt_contracts():
    components = mock_components()
    rejected = business_helpers.rejected()
    rejected['violations'][0]['rule'] = 'overlap'
    business_helpers.attach_validation(components, rejected)
    result = execute(components, fixture('trip_request'))
    assert result.state.status == 'awaiting_relaxation' and result.final_result is None
    assert 'điều chỉnh' in result.explanation
    assert result.state.retry_count == 3
    assert [a.random_seed for a in result.attempts] == [42, 43, 44, 45]
    assert len({a.itinerary_id for a in result.attempts}) == 4
    for attempt in result.attempts:
        assert attempt.itinerary_id in result.artifacts
        assert attempt.validation_result_id in result.artifacts
    assert all(a.result == 'hard_violation' for a in result.attempts)


@pytest.mark.parametrize('external,step', [(False, 'request_parser'), (True, 'planning_engine')])
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
