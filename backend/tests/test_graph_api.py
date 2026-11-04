import asyncio
from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from app.api.auth import get_current_user_id
from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app
from app.models.contracts import TripRequest
from app.services.graph_workflow import GraphRun, LangGraphOrchestrator
from app.services.mock_workflow import fixture, mock_components
from app.services.persistence import WorkflowPersistence
from app.services.workflow_factory import get_graph_orchestrator


def graph():
    return LangGraphOrchestrator(mock_components(), defaults=fixture("planner_defaults"))


def test_json_recovery_preserves_typed_outputs_and_counters():
    request = TripRequest.model_validate(fixture("trip_request"))
    request.destination.city = None
    run = asyncio.run(graph().run(request, current_date=date(2026, 11, 4)))
    assert run.state.status == "clarifying"
    restored = GraphRun.model_validate_json(run.model_dump_json())
    assert isinstance(restored.outputs["request_parser"], TripRequest)
    resumed = asyncio.run(graph().run(TripRequest.model_validate(fixture("trip_request")),
        current_date=date(2026, 11, 4), previous=restored, answer_raw="Da Lat"))
    assert resumed.state.status == "completed"
    assert resumed.transitions > restored.transitions
    assert resumed.visits["request_parser"] == 2
    assert set(restored.artifacts) <= set(resumed.artifacts)
    assert resumed.limits == restored.limits


def test_api_graph_dependency_and_persisted_result(monkeypatch):
    application = create_app(Settings(_env_file=None))
    session, row = MagicMock(), MagicMock()
    row.status, row.trip_id = "parsing", uuid4()
    identifier = uuid4()
    stored = {}
    monkeypatch.setattr(WorkflowPersistence, "request", lambda *a, **kw: row)
    monkeypatch.setattr(WorkflowPersistence, "save", lambda *a: None)
    monkeypatch.setattr(WorkflowPersistence, "sync", lambda self, run: setattr(row, "status", run.state.status))
    monkeypatch.setattr(WorkflowPersistence, "save_graph", lambda self, run: stored.update(snapshot=run.model_dump_json()))
    monkeypatch.setattr(WorkflowPersistence, "load_graph", lambda *a: GraphRun.model_validate_json(stored["snapshot"]))
    application.dependency_overrides[get_current_user_id] = uuid4
    application.dependency_overrides[get_session] = lambda: session
    application.dependency_overrides[get_graph_orchestrator] = graph
    with TestClient(application) as client:
        body = fixture("trip_request")
        body["destination"]["city"] = None
        url = f"/api/v1/requests/{identifier}"
        waiting = client.post(url + "/mock-run", json={"trip_request": body})
        assert waiting.status_code == 200, waiting.text
        assert waiting.json()["state"]["status"] == "clarifying"
        assert client.get(url + "/result").status_code == 409
        assert client.post(url + "/mock-run", json={"trip_request": fixture("trip_request")}).status_code == 422
        assert client.post(url + "/mock-run", json={"trip_request": fixture("trip_request"),
            "answer_raw": "Da Lat", "expected_transitions": 0}).status_code == 409
        complete = client.post(url + "/mock-run", json={"trip_request": fixture("trip_request"),
            "answer_raw": "Da Lat", "expected_transitions": waiting.json()["transitions"]})
        assert complete.status_code == 200, complete.text
        assert complete.json()["state"]["request_id"] == str(identifier)
        assert complete.json()["state"]["status"] == "completed"
        assert client.get(url + "/run").json()["history"] == complete.json()["history"]
        assert client.get(url + "/result").json() == complete.json()["final_result"]
        assert client.post(url + "/mock-run", json={"trip_request": fixture("trip_request")}).status_code == 409


def test_snapshot_repository_validates_identity():
    from app.core.errors import ApplicationError
    import pytest
    run = asyncio.run(graph().run(TripRequest.model_validate(fixture("trip_request")), current_date=date(2026, 11, 4)))
    session = MagicMock()
    session.scalar.return_value = type("Row", (), dict(graph_snapshot=run.model_dump(mode="json"),
        trip_id=uuid4(), status=run.state.status))()
    with pytest.raises(ApplicationError, match="snapshot and request differ"):
        WorkflowPersistence(session, uuid4()).load_graph(run.state.request_id)
