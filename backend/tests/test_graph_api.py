import asyncio
from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from app.api.auth import get_current_user_id
from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app
from shared.contracts import DestinationEpisode, TripRequest
from ai.orchestration.clarification_questions import attach_identity
from ai.orchestration.graph_workflow import GraphRun, LangGraphOrchestrator
from ai.orchestration.mock_workflow import fixture, mock_components
from app.services.persistence import WorkflowPersistence
from app.services.workflow_factory import get_graph_orchestrator
from support import confirmed_trip_request


def graph():
    return LangGraphOrchestrator(mock_components(), defaults=fixture("planner_defaults"))


def unselected_request():
    data = confirmed_trip_request()
    data['destination'].update(selection_intent='UNSPECIFIED', selection_authority=None,
        destination_source=None, selection_provenance=None, selection_mode='implicit', city=None)
    return data


def test_json_recovery_preserves_typed_outputs_and_counters():
    request = TripRequest.model_validate(unselected_request())
    run = asyncio.run(graph().run(request, current_date=date(2026, 11, 4)))
    assert run.state.status == "clarifying"
    restored = GraphRun.model_validate_json(run.model_dump_json())
    assert isinstance(restored.outputs["request_parser"], TripRequest)
    resumed = asyncio.run(graph().run(TripRequest.model_validate(confirmed_trip_request()),
        current_date=date(2026, 11, 4), previous=restored, answer_raw="Da Lat"))
    assert resumed.state.status == "completed"
    assert resumed.transitions > restored.transitions
    assert resumed.final_result is not None
    assert set(restored.artifacts) <= set(resumed.artifacts)
    assert resumed.limits == restored.limits


def test_api_graph_dependency_and_persisted_result(monkeypatch):
    application = create_app(Settings(_env_file=None))
    session, row = MagicMock(), MagicMock()
    row.status, row.trip_id = "parsing", uuid4()
    row.graph_snapshot = None
    identifier = uuid4()
    stored = {}
    monkeypatch.setattr(WorkflowPersistence, "request", lambda *a, **kw: row)
    monkeypatch.setattr(WorkflowPersistence, "save", lambda *a: None)
    episodes = {}
    def ensure_episode(self, run, policy):
        return episodes.setdefault(run.state.request_id, DestinationEpisode(
            episode_id=uuid4(), request_id=run.state.request_id, **policy.model_dump()))
    monkeypatch.setattr(WorkflowPersistence, 'ensure_episode', ensure_episode)
    def issue_question(self, run, draft, trip_request, *, question_id=None):
        episode = DestinationEpisode(episode_id=uuid4(), request_id=run.state.request_id)
        issued = attach_identity(draft, question_id=question_id or uuid4(),
            episode_id=episode.episode_id, intent_snapshot=episode.selection_intent, round=1)
        return issued, episode, 1
    monkeypatch.setattr(WorkflowPersistence, 'issue_question', issue_question)
    monkeypatch.setattr(WorkflowPersistence, 'answer_question', lambda self, run, answer: answer)
    monkeypatch.setattr(WorkflowPersistence, 'update_episode_policy', lambda self, run, policy:
        DestinationEpisode.model_validate(run.state.destination_episode.model_dump() | policy.model_dump()))
    monkeypatch.setattr(WorkflowPersistence, "sync", lambda self, run: setattr(row, "status", run.state.status))
    monkeypatch.setattr(WorkflowPersistence, "save_graph", lambda self, run: stored.update(snapshot=run.model_dump_json()))
    monkeypatch.setattr(WorkflowPersistence, "load_graph", lambda *a: GraphRun.model_validate_json(stored["snapshot"]))
    application.dependency_overrides[get_current_user_id] = uuid4
    application.dependency_overrides[get_session] = lambda: session
    application.dependency_overrides[get_graph_orchestrator] = graph
    with TestClient(application) as client:
        body = unselected_request()
        url = f"/api/v1/requests/{identifier}"
        waiting = client.post(url + "/mock-run", json={"trip_request": body})
        assert waiting.status_code == 200, waiting.text
        assert waiting.json()["state"]["status"] == "clarifying"
        assert client.get(url + "/result").status_code == 409
        assert client.post(url + "/mock-run", json={"trip_request": confirmed_trip_request()}).status_code == 422
        assert client.post(url + "/mock-run", json={"trip_request": confirmed_trip_request(),
            "answer_raw": "Da Lat", "expected_transitions": 0}).status_code == 409
        question = waiting.json()['pending_questions'][0]
        complete = client.post(url + "/mock-run", json={"trip_request": confirmed_trip_request(),
            "answer_raw": "Da Lat", "expected_transitions": waiting.json()["transitions"],
            "episode_id": question['episode_id'], "question_id": question['question_id']})
        assert complete.status_code == 200, complete.text
        assert complete.json()["state"]["request_id"] == str(identifier)
        assert complete.json()["state"]["status"] == "completed"
        assert client.get(url + "/run").json()["history"] == complete.json()["history"]
        assert client.get(url + "/result").json() == complete.json()["final_result"]
        assert client.post(url + "/mock-run", json={"trip_request": confirmed_trip_request()}).status_code == 409
