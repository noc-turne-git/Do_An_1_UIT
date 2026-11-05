"""Offline branch tests: route on domain outcomes, never scripted node names."""
import asyncio
import socket
from datetime import date
from unittest.mock import AsyncMock

import pytest

from shared.contracts import TripRequest
from ai.orchestration.graph_workflow import DataRequirement, GraphLimits, LangGraphOrchestrator
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.workflow_state import STEPS


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original(sock, address)
        raise AssertionError("External network forbidden")
    monkeypatch.setattr(socket.socket, "connect", connect)


def workflow(c=None, **kwargs):
    return LangGraphOrchestrator(c or mock_components(), defaults=fixture("planner_defaults"), **kwargs)


def execute(w, data=None, **kwargs):
    return asyncio.run(w.run(TripRequest.model_validate(data or fixture("trip_request")),
                             current_date=date(2026, 11, 4), **kwargs))


def path(r):
    return [e["step"] for e in r.history if e["event"] == "node"]


def validation(rule, action="replan"):
    data = fixture("validation_result")
    data.update(is_valid=False, suggested_action=action, violations=[
        dict(type=rule, rule=rule, severity="hard", message="Controlled domain finding")])
    return data


def reject_once(c, rule):
    original = c.validator.validate
    async def validate(itinerary, planning_input, **kwargs):
        if validate.rejection:
            validate.rejection = False
            return {**validation(rule), "trip_id": planning_input.trip_id}
        return await original(itinerary, planning_input, **kwargs)
    validate.rejection = True
    c.validator.validate = AsyncMock(side_effect=validate)


def test_happy_path_and_actual_langgraph_nodes():
    w = workflow()
    r = execute(w)
    assert r.state.status == "completed", r.errors
    assert path(r) == list(STEPS)
    assert set(STEPS) <= set(w.graph.get_graph().nodes)
    assert r.transitions == 9 and r.retries == r.revisions == 0
    assert r.outputs["constraint_planner"].model_dump(mode="json") == fixture("time_constraints")
    assert r.final_result == r.outputs["planning_engine"]
    assert len(r.artifacts) == 8
    assert r.attempts[0].result == "accepted"


def test_a_b_c_b_planning_missing_costs():
    c = mock_components()
    original = c.budget_module.estimate
    async def estimate(*args, **kwargs):
        result = await original(*args, **kwargs)
        if estimate.unresolved:
            estimate.unresolved = False
            result.missing_costs = ["p001"]
        return result
    estimate.unresolved = True
    c.budget_module.estimate = AsyncMock(side_effect=estimate)
    c.place_agent.find = AsyncMock(wraps=c.place_agent.find)
    r = execute(workflow(c))
    assert r.state.status == "completed", r.errors
    assert path(r) == [*STEPS[:5], "place_agent", *STEPS[4:]]
    assert r.visits["destination_agent"] == 1
    assert r.visits["place_agent"] == r.visits["budget_module"] == 2
    assert r.history[5]["reason"] == "missing_costs_or_required_cost_exceeds_budget"


def test_engine_b_c_engine_and_state_propagation():
    c = mock_components()
    original_engine, original_find = c.planning_engine.plan, c.place_agent.find
    async def find(*args, **kwargs):
        places = await original_find(*args, **kwargs)
        if kwargs["max_candidates"] > 100:
            places[0].suitability.score_places = 73
        return places
    async def plan(planning_input):
        if planning_input.candidate_places[0].score_places != 73:
            data = fixture("itinerary")
            data.update(trip_id=planning_input.trip_id, status="infeasible")
            data["diagnostics"].update(solver_status="infeasible", unsatisfied_constraints=["Candidate coverage"])
            return data
        return await original_engine(planning_input)
    c.place_agent.find = AsyncMock(side_effect=find)
    c.planning_engine.plan = AsyncMock(side_effect=plan)
    r = execute(workflow(c))
    assert r.state.status == "completed", r.errors
    assert path(r) == [*STEPS[:7], *STEPS[3:]]
    assert c.place_agent.find.call_args.kwargs["max_candidates"] == 200
    assert c.planning_engine.plan.call_args.args[0].candidate_places[0].score_places == 73
    second_b = [e for e in r.history if e.get("step") == "place_agent"][1]
    assert set(second_b["invalidated"]) == set(STEPS[3:7])
    assert all(second_b["refs_before"][key] is None for key in (
        "candidates_id", "costed_candidates_id", "planning_input_id", "itinerary_id", "validation_result_id"))
    b_artifacts = [v for v in r.artifacts.values() if isinstance(v, list)]
    assert [v[0]["suitability"]["score_places"] for v in b_artifacts] == [92, 73]
    assert [a.result for a in r.attempts] == ["infeasible", "accepted"]
    assert r.attempts[0].itinerary_id != r.attempts[1].itinerary_id


def test_validator_engine_validator():
    c = mock_components()
    reject_once(c, "overlap")
    r = execute(workflow(c))
    assert r.state.status == "completed", r.errors
    assert path(r) == [*STEPS[:8], *STEPS[6:]]
    assert [a.random_seed for a in r.attempts] == [42, 43]
    assert r.visits["place_agent"] == 1
    assert r.attempts[0].validation_result_id != r.attempts[1].validation_result_id


@pytest.mark.parametrize("rule,target", [("budget", "place_agent"), ("price_integrity", "place_agent"),
    ("must_visit", "place_agent"), ("input_integrity", "constraint_planner")])
def test_validator_preparation_routes(rule, target):
    c = mock_components()
    reject_once(c, rule)
    r = execute(workflow(c))
    assert r.state.status == "completed", r.errors
    assert path(r)[8] == target
    assert r.visits[target] == 2


def test_agent_requires_other_agent_and_consumer_rebuilt():
    c = mock_components()
    original = c.place_agent.find
    async def find(*args, **kwargs):
        if find.needs_region:
            find.needs_region = False
            raise DataRequirement("destination_agent", "Region metadata needs refresh")
        return await original(*args, **kwargs)
    find.needs_region = True
    c.place_agent.find = AsyncMock(side_effect=find)
    r = execute(workflow(c))
    assert r.state.status == "completed", r.errors
    assert path(r) == [*STEPS[:4], *STEPS[1:]]
    assert r.history[3]["requirement"]["provider"] == "destination_agent"


@pytest.mark.parametrize("provider", ["unknown", "validator", "place_agent"])
def test_invalid_dependency_fails(provider):
    c = mock_components()
    c.place_agent.find = AsyncMock(side_effect=DataRequirement(provider, "bad dependency"))
    r = execute(workflow(c))
    assert r.state.status == "failed"
    assert "invalid_dependency" in r.errors[-1].message


def test_explicit_exclusions_pass_to_place_agent():
    c = mock_components()
    c.budget_module.estimate = AsyncMock(side_effect=DataRequirement(
        "place_agent", "Refresh stale candidate", exclude_place_ids=["p003"]))
    c.place_agent.find = AsyncMock(wraps=c.place_agent.find)
    r = execute(workflow(c, limits=GraphLimits(max_revisions=2)))
    assert r.state.status == "failed"
    assert c.place_agent.find.call_args.kwargs["exclude_place_ids"] == ["p003"]


def test_empty_place_search_expands_then_succeeds():
    c = mock_components()
    original = c.place_agent.find
    async def find(*args, **kwargs):
        return [] if kwargs["max_candidates"] == 100 else await original(*args, **kwargs)
    c.place_agent.find = AsyncMock(side_effect=find)
    r = execute(workflow(c))
    assert r.state.status == "completed"
    assert path(r)[3:6] == ["place_agent", "place_agent", "budget_module"]


def test_missing_must_visit_expands():
    c = mock_components()
    original = c.place_agent.find
    async def find(*args, **kwargs):
        found = await original(*args, **kwargs)
        return found[1:] if kwargs["max_candidates"] == 100 else found
    c.place_agent.find = AsyncMock(side_effect=find)
    data = fixture("trip_request")
    data["destination"]["must_visit"] = ["p001"]
    r = execute(workflow(c), data)
    assert r.state.status == "completed"
    assert r.visits["place_agent"] == 2


def test_required_cost_over_budget_routes_b_without_relaxing_request():
    c = mock_components()
    original = c.budget_module.estimate
    async def estimate(*args, **kwargs):
        result = await original(*args, **kwargs)
        if estimate.expensive:
            estimate.expensive = False
            result.places[0].estimated_total_cost.max = 4000000
        return result
    estimate.expensive = True
    c.budget_module.estimate = AsyncMock(side_effect=estimate)
    data = fixture("trip_request")
    data["destination"]["must_visit"] = ["p001"]
    r = execute(workflow(c), data)
    assert r.state.status == "completed", r.errors
    assert r.visits["place_agent"] == 2
    assert r.outputs["request_parser"].budget.amount == 3000000


def test_optional_catalog_sum_is_not_budget_failure():
    data = fixture("trip_request")
    data["budget"]["amount"] = 1
    r = execute(workflow(), data)
    # Mock validator is fixture-only; this tests routing, not business feasibility.
    assert r.visits["place_agent"] == 1


@pytest.mark.parametrize("kind", ["revision", "transition", "retry", "solver_retry"])
def test_limits(kind):
    c = mock_components()
    settings = dict(max_revisions=100, max_retries=10, max_transitions=100)
    config = None
    if kind == "revision":
        settings["max_revisions"] = 2
        c.place_agent.find = AsyncMock(return_value=[])
    elif kind == "transition":
        settings["max_transitions"] = 4
        c.place_agent.find = AsyncMock(return_value=[])
    else:
        if kind == "retry":
            settings["max_retries"] = 1
        else:
            config = {"solver_config": dict(time_limit_seconds=30, random_seed=42, max_retries=1)}
        async def validate(itinerary, planning_input, **kwargs):
            return {**validation("overlap"), "trip_id": planning_input.trip_id}
        c.validator.validate = AsyncMock(side_effect=validate)
    r = execute(workflow(c, limits=GraphLimits(**settings), configuration=config))
    assert r.state.status == "failed" and r.final_result is None
    assert r.transitions <= settings["max_transitions"]
    assert r.revisions <= settings["max_revisions"]
    assert r.history[-1]["event"] == "halt"
    if kind in {"retry", "solver_retry"}:
        assert r.retries == 1
        assert [a.random_seed for a in r.attempts] == [42, 43]


def test_clarification_limit_resume_and_previous_immutable():
    w = workflow(limits=GraphLimits(max_clarifications=2, max_revisions=20))
    data = fixture("trip_request")
    data["budget"]["amount"] = None
    first = execute(w, data)
    assert first.state.status == "clarifying"
    assert execute(w, data, previous=first) == first
    second = execute(w, data, previous=first, answer_raw="unknown")
    final = execute(w, data, previous=second, answer_raw="unknown")
    assert final.state.status == "failed" and final.state.clarification_round == 2
    assert first.state.clarification_round == 1 and len(first.answers_history) == 0
    assert len(final.answers_history) == 2


def test_user_update_rebuilds_and_keeps_old_artifacts():
    w = workflow(limits=GraphLimits(max_revisions=20))
    first = execute(w)
    before = first.model_dump_json()
    data = fixture("trip_request")
    data["budget"]["amount"] = 4000000
    final = execute(w, data, previous=first, answer_raw="Change budget")
    assert final.state.status == "completed", final.errors
    assert final.outputs["planning_input_builder"].budget.amount == 4000000
    assert first.model_dump_json() == before
    assert final.state.artifacts.itinerary_id != first.state.artifacts.itinerary_id
    assert final.artifacts[first.state.artifacts.planning_input_id]["budget"]["amount"] == 3000000
    assert set(final.history[9]["invalidated"]) == set(STEPS)


@pytest.mark.parametrize("step,method", list(zip(STEPS, ["parse", "select", "build", "find", "estimate", "build", "plan", "validate", "explain"])))
def test_invalid_boundary_never_saves_output(step, method):
    c = mock_components()
    setattr(getattr(c, step), method, AsyncMock(return_value={"invalid": True}))
    r = execute(workflow(c))
    assert r.state.status == "failed" and r.state.current_step == step
    assert step not in r.outputs and step not in r.state.completed_steps
    assert "output_schema_invalid" in r.errors[-1].message


@pytest.mark.parametrize("action,expected", [("fail", "failed"), ("ask_user", "clarifying")])
def test_validator_terminal_actions(action, expected):
    c = mock_components()
    async def validate(itinerary, planning_input, **kwargs):
        return {**validation("overlap", action), "trip_id": planning_input.trip_id}
    c.validator.validate = validate
    r = execute(workflow(c))
    assert r.state.status == expected and r.final_result is None
    assert "explainer" not in path(r)


def test_infeasible_with_relaxation_waits_for_user():
    c = mock_components()
    async def plan(planning_input):
        data = fixture("itinerary")
        data.update(trip_id=planning_input.trip_id, status="infeasible", relaxation_suggestions=[
            dict(constraint_type="budget", description="User approval required", payload={"amount": 4000000})])
        data["diagnostics"]["solver_status"] = "infeasible"
        return data
    c.planning_engine.plan = plan
    r = execute(workflow(c))
    assert r.state.status == "awaiting_relaxation"
    assert r.visits["place_agent"] == 1
    assert "validator" not in path(r) and r.final_result is None


def test_langgraph_stream_exposes_each_scheduled_node():
    from ai.orchestration.graph_workflow import GraphRun
    from shared.contracts import WorkflowState
    from uuid import uuid4
    w = workflow()
    async def stream():
        initial = dict(run=GraphRun(state=WorkflowState(request_id=uuid4(), trip_id=uuid4(),
            status="parsing", current_step="request_parser", completed_steps=[], artifacts={},
            clarification_round=0, pending_fields=[], retry_count=0)),
            request=TripRequest.model_validate(fixture("trip_request")), current_date=date(2026,11,4),
            answer_raw=None, previous_request=None)
        return [next(iter(update)) async for update in w.graph.astream(initial)]
    assert asyncio.run(stream()) == list(STEPS)


def test_multiple_preparation_cycles_keep_seed_and_retry_limit():
    c = mock_components()
    async def validate(itinerary, planning_input, **kwargs):
        return {**validation("budget"), "trip_id": planning_input.trip_id}
    c.validator.validate = validate
    r = execute(workflow(c, limits=GraphLimits(max_revisions=100, max_retries=2)))
    assert r.state.status == "failed"
    assert [a.random_seed for a in r.attempts] == [42, 43, 44]
    assert r.retries == 2 and r.visits["place_agent"] >= 3


def test_resume_at_transition_limit_clears_previous_final_result():
    w = workflow(limits=GraphLimits(max_transitions=9))
    first = execute(w)
    assert first.state.status == "completed"
    final = execute(w, previous=first, answer_raw="Replan")
    assert final.state.status == "failed"
    assert final.final_result is None and final.explanation is None
    assert first.final_result is not None


def test_resume_clarification_records_resolved_field():
    w = workflow(limits=GraphLimits(max_revisions=20))
    data = fixture("trip_request")
    data["budget"]["amount"] = None
    first = execute(w, data)
    data["budget"]["amount"] = 3000000
    final = execute(w, data, previous=first, answer_raw="3 million")
    assert final.state.status == "completed"
    assert final.answers_history[-1].resolved_fields == ["budget.amount"]
    assert final.pending_questions == []


def test_defaults_only_after_clarification_exhausted():
    data = fixture("trip_request")
    data["preferences"]["pace"] = None
    data["meta"]["field_sources"].pop("preferences.pace")
    w = workflow(limits=GraphLimits(max_clarifications=1),
                 clarification_defaults={"preferences.pace": "relaxed"})
    first = execute(w, data)
    assert first.state.status == "clarifying"
    final = execute(w, data, previous=first, answer_raw="Use default")
    assert final.state.status == "completed"
    assert final.outputs["request_parser"].meta.field_sources["preferences.pace"] == "default"


def test_module_cannot_mutate_state_or_original_input():
    c = mock_components()
    original = c.budget_module.estimate
    async def estimate(request, places, **kwargs):
        output = await original(request, places, **kwargs)
        request.budget.amount = 1
        places.clear()
        return output
    c.budget_module.estimate = estimate
    data = fixture("trip_request")
    r = execute(workflow(c), data)
    assert r.state.status == "completed"
    assert r.outputs["planning_input_builder"].budget.amount == 3000000
    assert len(r.outputs["place_agent"]) == 3
    assert data == fixture("trip_request")


@pytest.mark.parametrize("step,method", [("planning_engine", "plan"), ("validator", "validate")])
def test_cross_trip_output_rejected(step, method):
    c = mock_components()
    setattr(getattr(c, step), method, AsyncMock(return_value=fixture(
        "itinerary" if step == "planning_engine" else "validation_result")))
    r = execute(workflow(c))
    assert r.state.status == "failed" and step not in r.outputs
    assert "planning_input_inconsistent" in r.errors[-1].message
