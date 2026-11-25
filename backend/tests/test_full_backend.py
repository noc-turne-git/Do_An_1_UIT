"""Offline QA: contracts, component boundaries, API and storage infrastructure.

These tests do not certify the mock Engine/Validator business algorithms.
"""
import asyncio
import socket
from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

import app
from ai.agents import interfaces
from app.core.config import Settings
from shared.errors import ApplicationError
from app.db.base import Base
from app.db.models import ArtifactRecord, TripRecord, WorkflowRecord
from app.db.session import Database, postgres_url
from app.main import create_app
from app.models import (CostedPlaceCandidate, DestinationResult, Itinerary,
                        PlaceCandidate, PlanningInput, TimeConstraints, TripRequest,
                        ValidationResult, WorkflowState)
from app.repositories.artifacts import ArtifactRepository
from ai.planning.constraint_planner import DeterministicConstraintPlanner, PlannerDefaults
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.graph_workflow import LangGraphOrchestrator, GraphRun
from ai.orchestration.workflow_state import STEPS

METHODS = ("parse", "select", "build", "find", "estimate", "build", "plan", "validate", "explain")
@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Block external connections; Windows asyncio needs a loopback socketpair."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        return denied()
    def connect_ex(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect_ex(sock, address)
        return denied()
    def denied(*args, **kwargs):
        raise AssertionError("Network is forbidden in offline backend QA")
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "create_connection", denied)


def execute(components=None, data=None, **kwargs):
    return asyncio.run(LangGraphOrchestrator(components or mock_components(),
        defaults=fixture("planner_defaults")).run(
        TripRequest.model_validate(data or fixture("trip_request")),
        current_date=date(2026, 11, 2), **kwargs))


@pytest.mark.parametrize("mutation", ["duplicate", "unknown_price", "matrix_negative"])
def test_planning_input_integrity(mutation):
    data = fixture("planning_input")
    if mutation == "duplicate":
        data["candidate_places"].append(deepcopy(data["candidate_places"][0]))
    elif mutation == "unknown_price":
        data["candidate_places"][0]["price_status"] = "UNKNOWN"
    elif mutation == "matrix_mode":
        data["travel_distance_matrix"]["mode"] = "walking"
    elif mutation == "matrix_negative":
        data["travel_time_matrix"]["values"][0][1] = -1
    else:
        data["travel_time_matrix"]["locations"][1] = data["travel_time_matrix"]["locations"][0]
    with pytest.raises(ValidationError):
        PlanningInput.model_validate(data)


def test_itinerary_status_agrees_with_solver_diagnostics():
    """Open contract gap: a feasible itinerary must not claim solver infeasible."""
    data = fixture("itinerary")
    data["diagnostics"]["solver_status"] = "infeasible"
    with pytest.raises(ValidationError):
        Itinerary.model_validate(data)


@pytest.mark.parametrize("step,method,ref", [
    ("planning_input_builder", "build", "planning_input_id"),
    ("validator", "validate", "validation_result_id"),
])
def test_cross_module_trip_id_rejected_before_saving(step, method, ref):
    components = mock_components()
    original = getattr(getattr(components, step), method)
    async def changed_id(*args, **kwargs):
        output = await original(*args, **kwargs)
        return output.model_copy(update={"trip_id": __import__("uuid").uuid4()})
    setattr(getattr(components, step), method, changed_id)
    result = execute(components)
    assert result.state.status == "failed"
    assert result.state.current_step == step
    assert result.errors[-1].message.startswith("[planning_input_inconsistent]")
    assert getattr(result.state.artifacts, ref) is None
    assert step not in result.state.completed_steps


def test_cancellation_propagates():
    components = mock_components()
    components.place_agent.find = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        execute(components)


def test_workflow_artifacts_roundtrip_and_snapshot_independence():
    result = execute()
    assert GraphRun.model_validate_json(result.model_dump_json()) == result
    assert len(set(result.state.artifacts.model_dump().values())) == 8
    first = result.checkpoints[0].model_dump_json()
    itinerary = result.artifacts[result.state.artifacts.itinerary_id]
    result.final_result.summary.summary_message = "changed locally"
    assert itinerary["summary"]["summary_message"] != "changed locally"
    result.state.completed_steps.clear()
    assert result.checkpoints[0].model_dump_json() == first


@pytest.mark.parametrize("body,status", [({}, 422)])
def test_api_invalid_request_envelope(body, status):
    with TestClient(create_app(Settings(_env_file=None, database_url=None))) as client:
        response = client.post("/api/v1/dev/workflows/mock-run", json=body)
        assert response.status_code == status
        assert response.json()["error"]["code"] == "invalid_request"


def test_repository_add_and_get_without_implicit_commit():
    from uuid import uuid4
    session, user, request = MagicMock(), uuid4(), uuid4()
    session.scalar.side_effect = [WorkflowRecord(request_id=request), None]
    repository = ArtifactRepository(session, user)
    payload = TripRequest.model_validate(fixture("trip_request"))
    record = repository.add(request, "trip_request", payload)
    assert record.payload == payload.model_dump(mode="json")
    session.add.assert_called_once_with(record)
    session.flush.assert_called_once()
    session.commit.assert_not_called()
