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
from support import confirmed_trip_request


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
    return asyncio.run(w.run(TripRequest.model_validate(data or confirmed_trip_request()),
                             current_date=date(2026, 11, 4), **kwargs))


def path(r):
    return [e["step"] for e in r.history if e["event"] == "node"]


def validation(rule, action="replan"):
    data = fixture("validation_result")
    data.update(is_valid=False, suggested_action=action, violations=[
        dict(type=rule, rule=rule, severity="hard", message="Controlled domain finding")])
    return data


def reject_once(c, rule, times=1):
    original = c.validator.validate
    async def validate(itinerary, planning_input, **kwargs):
        if validate.rejections:
            validate.rejections -= 1
            return {**validation(rule), "trip_id": planning_input.trip_id}
        return await original(itinerary, planning_input, **kwargs)
    validate.rejections = times
    c.validator.validate = AsyncMock(side_effect=validate)


def test_happy_path_and_actual_langgraph_nodes():
    w = workflow()
    r = execute(w)
    assert r.state.status == "completed", r.errors
    assert path(r) == list(STEPS)
    assert set(STEPS) <= set(w.graph.get_graph().nodes)
    assert r.transitions == 9 and r.retries == r.repair_rounds == 0
    assert r.outputs["constraint_planner"].model_dump(mode="json") == fixture("time_constraints")
    assert r.final_result == r.outputs["planning_engine"]
    assert r.state.artifacts.itinerary_id in r.artifacts
    assert r.attempts[0].result == "accepted"


@pytest.mark.parametrize('repairs', [1, 3])
def test_validator_engine_validator(repairs):
    c = mock_components()
    reject_once(c, "overlap", times=repairs)
    r = execute(workflow(c))
    assert r.state.status == "completed", r.errors
    assert path(r) == [*STEPS[:8], *STEPS[6:8] * repairs, STEPS[8]]
    assert r.repair_rounds == repairs
    assert [a.random_seed for a in r.attempts] == list(range(42, 43 + repairs))
    assert r.visits["place_agent"] == 1
    assert len({a.validation_result_id for a in r.attempts}) == repairs + 1


@pytest.mark.parametrize("rule,target", [("budget", "place_agent"),
    ("input_integrity", "constraint_planner")])
def test_validator_preparation_routes(rule, target):
    c = mock_components()
    reject_once(c, rule)
    r = execute(workflow(c))
    assert r.state.status == "completed", r.errors
    assert path(r)[8] == target
    assert r.visits[target] == 2


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
    data = confirmed_trip_request()
    data["destination"]["must_visit"] = ["p001"]
    r = execute(workflow(c), data)
    assert r.state.status == "completed", r.errors
    assert r.visits["place_agent"] == 2
    assert r.outputs["request_parser"].budget.amount == 3000000


@pytest.mark.parametrize("kind", ["repair", "transition", "retry", "solver_retry"])
def test_limits(kind):
    c = mock_components()
    settings = dict(max_repair_rounds=3, max_retries=10, max_transitions=100)
    config = None
    if kind == "transition":
        settings["max_transitions"] = 4
        c.place_agent.find = AsyncMock(return_value=[])
    else:
        if kind == "retry":
            settings["max_retries"] = 1
        elif kind == "solver_retry":
            config = {"solver_config": dict(time_limit_seconds=30, random_seed=42, max_retries=1)}
        async def validate(itinerary, planning_input, **kwargs):
            return {**validation("overlap"), "trip_id": planning_input.trip_id}
        c.validator.validate = AsyncMock(side_effect=validate)
    r = execute(workflow(c, limits=GraphLimits(**settings), configuration=config))
    assert r.state.status == ("awaiting_relaxation" if kind == "repair" else "failed")
    assert r.final_result is None
    assert r.transitions <= settings["max_transitions"]
    assert r.repair_rounds <= settings["max_repair_rounds"]
    if kind == "repair":
        assert r.repair_rounds == 3 and r.visits["validator"] == 4
        assert 'điều chỉnh' in r.explanation
    else:
        assert r.history[-1]["event"] == "halt"
    if kind in {"retry", "solver_retry"}:
        assert r.retries == 1
        assert [a.random_seed for a in r.attempts] == [42, 43]


def test_user_update_rebuilds_and_keeps_old_artifacts():
    w = workflow()
    first = execute(w)
    before = first.model_dump_json()
    data = confirmed_trip_request()
    data["budget"]["amount"] = 4000000
    final = execute(w, data, previous=first, answer_raw="Change budget")
    assert final.state.status == "completed", final.errors
    assert final.repair_rounds == 0
    assert final.outputs["planning_input_builder"].budget.amount == 4000000
    assert first.model_dump_json() == before
    assert final.state.artifacts.itinerary_id != first.state.artifacts.itinerary_id
    assert final.artifacts[first.state.artifacts.planning_input_id]["budget"]["amount"] == 3000000


@pytest.mark.parametrize("step,method", [("request_parser", "parse"),
    ("planning_engine", "plan"), ("validator", "validate")])
def test_invalid_boundary_never_saves_output(step, method):
    c = mock_components()
    setattr(getattr(c, step), method, AsyncMock(return_value={"invalid": True}))
    r = execute(workflow(c))
    assert r.state.status == "failed" and r.state.current_step == step
    assert step not in r.outputs and step not in r.state.completed_steps
    assert "output_schema_invalid" in r.errors[-1].message


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


@pytest.mark.parametrize("step,method", [("planning_engine", "plan"), ("validator", "validate")])
def test_cross_trip_output_rejected(step, method):
    c = mock_components()
    setattr(getattr(c, step), method, AsyncMock(return_value=fixture(
        "itinerary" if step == "planning_engine" else "validation_result")))
    r = execute(workflow(c))
    assert r.state.status == "failed" and step not in r.outputs
    assert "planning_input_inconsistent" in r.errors[-1].message
