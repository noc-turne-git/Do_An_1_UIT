import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from shared.errors import ApplicationError
from app.main import create_app
from shared.contracts import TripRequest, WorkflowState
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.graph_workflow import LangGraphOrchestrator
from ai.orchestration.workflow_state import STEPS


def setup():
    return mock_components(), fixture("trip_request")


def run(components, data, **kwargs):
    return asyncio.run(LangGraphOrchestrator(components, defaults=fixture("planner_defaults")).run(
        TripRequest.model_validate(data), current_date=date(2026, 11, 2), **kwargs))


def rejected(action="replan"):
    data = fixture("validation_result")
    data.update(is_valid=False, suggested_action=action,
                violations=[dict(type="budget_exceeded", rule="budget", severity="hard", message="Mock hard violation")])
    return data


def attach_validation(c, data):
    async def validate(itinerary, planning_input, **kwargs):
        return {**data, "trip_id": planning_input.trip_id}
    c.validator.validate = AsyncMock(side_effect=validate)


def test_happy_path_order_and_real_constraints():
    c, data = setup()
    result = run(c, data)
    assert result.state.status == "completed"
    assert result.state.completed_steps == list(STEPS)
    entered = []
    for checkpoint in result.checkpoints:
        WorkflowState.model_validate(checkpoint.model_dump())
        if not entered or checkpoint.current_step != entered[-1]:
            entered.append(checkpoint.current_step)
    assert entered == list(STEPS)
    assert {s.status for s in result.checkpoints} >= {"parsing", "planning", "validating", "completed"}
    times = result.artifacts[result.state.artifacts.time_constraints_id]
    assert times == fixture("time_constraints")
    planning = result.artifacts[result.state.artifacts.planning_input_id]
    assert planning["budget"] == TripRequest.model_validate(data).budget.model_dump(mode="json")
    assert planning["time_constraints"]["days"][1]["activity_window"]["end"] == {"value": "12:00", "is_hard": True}
    assert result.attempts[0].result == "accepted"
    assert result.final_result.diagnostics.optimality_proven is False
    assert result.explanation == result.final_result.summary.summary_message
    assert len(result.artifacts) == 8


def test_missing_stops_and_no_resume_without_answer():
    c, data = setup()
    data["budget"]["amount"] = None
    c.destination_agent.select = AsyncMock()
    result = run(c, data)
    assert result.state.status == "clarifying"
    assert result.state.pending_fields == ["budget.amount"]
    assert result.state.clarification_round == 1
    c.destination_agent.select.assert_not_called()
    again = run(c, data, previous=result)
    assert again == result


def test_destination_choice_stops():
    c, data = setup()
    data["destination"].update(selection_mode="ambiguous", city=None, candidate_cities=["Đà Lạt", "Nha Trang"])
    c.constraint_planner.build = AsyncMock()
    result = run(c, data)
    assert result.state.status == "clarifying"
    assert result.state.pending_fields == ["destination.city"]
    assert result.state.completed_steps == list(STEPS[:2])
    c.constraint_planner.build.assert_not_called()


@pytest.mark.parametrize("step,method", [("request_parser", "parse"), ("destination_agent", "select"),
    ("constraint_planner", "build"), ("place_agent", "find"), ("budget_module", "estimate"),
    ("planning_input_builder", "build"), ("planning_engine", "plan"), ("validator", "validate"), ("explainer", "explain")])
def test_invalid_output_at_each_boundary(step, method):
    c, data = setup()
    setattr(getattr(c, step), method, AsyncMock(return_value={"bad_field": True}))
    result = run(c, data)
    assert result.state.status == "failed"
    assert result.state.current_step == step
    assert step not in result.state.completed_steps
    assert result.errors[-1].message.startswith("[output_schema_invalid]")
    assert result.final_result is None


@pytest.mark.parametrize("exception,code", [(RuntimeError("secret"), "module_exception"),
    (ApplicationError("external_api_error", "Offline failure", retryable=True), "external_api_error")])
def test_exception_records_state(exception, code):
    c, data = setup()
    c.place_agent.find = AsyncMock(side_effect=exception)
    result = run(c, data)
    assert result.state.status == "failed"
    assert result.errors[-1].message.startswith(f"[{code}]")
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize("suggestions,expected", [([], "failed"), ([{"constraint_type": "budget", "description": "Increase budget", "payload": {"field": "budget.amount", "value": 4000000}}], "awaiting_relaxation")])
@pytest.mark.parametrize("status", ["infeasible", "partial"])
def test_infeasible_and_partial(suggestions, expected, status):
    c, data = setup()
    async def plan(planning_input):
        output = fixture("itinerary")
        output.update(trip_id=planning_input.trip_id, status=status, relaxation_suggestions=suggestions)
        output["diagnostics"].update(solver_status=status, unsatisfied_constraints=["Mock infeasible"])
        return output
    c.planning_engine.plan = AsyncMock(side_effect=plan)
    attach_validation(c, rejected("ask_user" if suggestions else "fail"))
    c.explainer.explain = AsyncMock()
    result = run(c, data)
    assert result.state.status == expected
    assert result.attempts[-1].result == "infeasible"
    assert result.state.clarification_round == 0
    assert result.final_result is None
    c.explainer.explain.assert_not_called()
    assert run(c, data, previous=result) == result


def test_replan_bound_seed_and_immutable_artifacts():
    c, data = setup()
    output = rejected()
    output["violations"][0]["rule"] = "overlap"
    attach_validation(c, output)
    result = run(c, data)
    assert result.state.status == "failed"
    assert result.errors[-1].message.startswith("[retry_or_revision_limit]")
    assert result.state.retry_count == 3
    assert [a.random_seed for a in result.attempts] == [42, 43, 44, 45]
    assert len({a.itinerary_id for a in result.attempts}) == 4
    assert all(a.result == "hard_violation" for a in result.attempts)
    assert len([p for p in result.artifacts.values() if isinstance(p, dict) and "solver_config" in p]) == 4


def test_invalid_validation_never_completes():
    c, data = setup()
    output = fixture("validation_result")
    output["checked_rules"] = []
    attach_validation(c, output)
    result = run(c, data)
    assert result.state.status == "failed"
    assert result.errors[-1].message.startswith("[output_schema_invalid]")
    assert result.attempts[-1].result == "error"


def test_resume_records_answer_and_does_not_mutate_previous():
    c, data = setup()
    data["budget"]["amount"] = None
    previous = run(c, data)
    data["budget"]["amount"] = 3000000
    result = run(c, data, previous=previous, answer_raw="3 triệu")
    assert result.state.status == "completed"
    assert previous.state.status == "clarifying"
    history = result.answers_history[-1]
    assert history.resolved_fields == ["budget.amount"]
    assert history.answer_raw == "3 triệu"
    assert not result.pending_questions


def test_three_round_limit_without_default():
    c, data = setup()
    data["budget"]["amount"] = None
    result = run(c, data)
    for _ in range(3):
        result = run(c, data, previous=result, answer_raw="still missing")
    assert result.state.status == "failed"
    assert result.state.clarification_round == 3
    assert len(result.answers_history) == 3


def test_id_mismatch_rejected():
    c, data = setup()
    c.validator.validate = AsyncMock(return_value=fixture("validation_result"))
    result = run(c, data)
    assert result.state.status == "failed"
    assert result.errors[-1].message.startswith("[planning_input_inconsistent]")


def test_demo_api_and_invalid_body():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.post("/api/v1/dev/workflows/mock-run", json=fixture("trip_request"))
        assert response.status_code == 200
        assert response.json()["mode"] == "development_mock"
        assert response.json()["state"]["status"] == "completed"
        assert client.post("/api/v1/dev/workflows/mock-run", json={}).status_code == 422
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/api/v1/dev/workflows/mock-run"]["post"]["tags"] == ["Development/Mock"]


def test_module_inputs_are_compatible_and_request_unchanged():
    c, data = setup()
    original = TripRequest.model_validate(data).model_dump(mode="json")
    methods = ["parse", "select", "build", "find", "estimate", "build", "plan", "validate", "explain"]
    for step, method in zip(STEPS, methods):
        component = getattr(c, step)
        setattr(component, method, AsyncMock(wraps=getattr(component, method)))
    result = run(c, data)
    assert result.state.status == "completed"
    assert TripRequest.model_validate(data).model_dump(mode="json") == original
    build_args = c.planning_input_builder.build.call_args.args
    _, request, destination, times, places, costs = build_args
    assert request == c.destination_agent.select.call_args.args[0]
    assert destination == c.place_agent.find.call_args.args[1]
    assert times == c.place_agent.find.call_args.args[2]
    assert places == c.budget_module.estimate.call_args.args[1]
    assert {p.place_id for p in places} == {p.place_id for p in costs.places}
    planning = c.planning_engine.plan.call_args.args[0]
    assert c.validator.validate.call_args.args[1] == planning
    itinerary = c.validator.validate.call_args.args[0]
    assert c.explainer.explain.call_args.args[0] == itinerary


def test_engine_exception_has_attempt_without_stale_ids():
    c, data = setup()
    c.planning_engine.plan = AsyncMock(side_effect=RuntimeError("engine failed"))
    result = run(c, data)
    assert result.state.current_step == "planning_engine"
    attempt = result.attempts[-1]
    assert attempt.result == "error"
    assert attempt.itinerary_id is None and attempt.validation_result_id is None


def test_preference_default_after_three_rounds():
    c, data = setup()
    data["preferences"]["pace"] = None
    data["meta"]["field_sources"].pop("preferences.pace")
    orchestrator = LangGraphOrchestrator(c, defaults=fixture("planner_defaults"),
                                clarification_defaults={"preferences.pace": "relaxed"})
    request = TripRequest.model_validate(data)
    result = asyncio.run(orchestrator.run(request, current_date=date(2026, 11, 2)))
    for _ in range(3):
        result = asyncio.run(orchestrator.run(request, current_date=date(2026, 11, 2),
                                             previous=result, answer_raw="no preference"))
    assert result.state.status == "completed"
    parsed = result.artifacts[result.state.artifacts.trip_request_id]
    assert parsed["meta"]["field_sources"]["preferences.pace"] == "default"


def test_declared_unknown_not_asked_again():
    c, data = setup()
    data["budget"]["amount"] = None
    previous = run(c, data)
    data["meta"]["field_sources"]["budget.amount"] = "user"
    result = run(c, data, previous=previous, answer_raw="chưa biết")
    assert result.state.status == "completed"
    assert result.answers_history[-1].declared_unknown_fields == ["budget.amount"]
    assert result.state.clarification_round == 1
    assert result.artifacts[result.state.artifacts.planning_input_id]["budget"]["amount"] is None


def test_replan_then_accept():
    c, data = setup()
    count = 0
    async def validate(itinerary, planning_input, **kwargs):
        nonlocal count
        count += 1
        output = rejected() if count == 1 else fixture("validation_result")
        return {**output, "trip_id": planning_input.trip_id}
    c.validator.validate = AsyncMock(side_effect=validate)
    result = run(c, data)
    assert result.state.status == "completed"
    assert [a.result for a in result.attempts] == ["hard_violation", "accepted"]
    assert result.state.retry_count == 1
