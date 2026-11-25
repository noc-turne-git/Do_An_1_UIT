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
from support import confirmed_trip_request


def setup():
    return mock_components(), confirmed_trip_request()


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
    assert result.state.artifacts.itinerary_id in result.artifacts


def test_missing_stops_and_no_resume_without_answer():
    c, data = setup()
    data["trip"]["start_date"] = None
    result = run(c, data)
    assert result.state.status == "clarifying"
    assert result.state.pending_fields == ["trip.start_date"]
    assert result.state.clarification_round == 1
    assert 'planning_engine' not in result.visits
    again = run(c, data, previous=result)
    assert again == result


def test_destination_choice_stops():
    c, data = setup()
    from test_destination_resolution import request
    data = request('USER_UNKNOWN')
    data['destination']['candidate_cities'] = ['Da Lat', 'Nha Trang']
    c.constraint_planner.build = AsyncMock()
    result = run(c, data)
    assert result.state.status == "clarifying"
    assert result.state.pending_fields == ["destination.city"]
    assert result.state.completed_steps == list(STEPS[:2])
    c.constraint_planner.build.assert_not_called()


@pytest.mark.parametrize("step,method", [("request_parser", "parse"),
    ("planning_engine", "plan"), ("validator", "validate")])
def test_invalid_output_at_each_boundary(step, method):
    c, data = setup()
    setattr(getattr(c, step), method, AsyncMock(return_value={"bad_field": True}))
    result = run(c, data)
    assert result.state.status == "failed"
    assert result.state.current_step == step
    assert step not in result.state.completed_steps
    assert result.errors[-1].message.startswith("[output_schema_invalid]")
    assert result.final_result is None


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


def test_resume_records_answer_and_does_not_mutate_previous():
    c, data = setup()
    data["trip"]["start_date"] = None
    previous = run(c, data)
    data["trip"]["start_date"] = '2026-11-14'
    result = run(c, data, previous=previous, answer_raw="14/11/2026")
    assert result.state.status == "completed"
    assert previous.state.status == "clarifying"
    history = result.answers_history[-1]
    assert history.resolved_fields == ["trip.start_date"]
    assert history.answer_raw == "14/11/2026"
    assert not result.pending_questions


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
