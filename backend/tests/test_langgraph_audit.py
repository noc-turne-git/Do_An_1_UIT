"""Executable audit evidence. All scheduling is performed by compiled LangGraph."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from shared.errors import ApplicationError
from app.main import create_app
from ai.orchestration.graph_workflow import GraphRun, GraphLimits, DataRequirement
from app.services.workflow_factory import get_graph_orchestrator
from test_graph_workflow import workflow, execute, path, reject_once, offline
from ai.orchestration.mock_workflow import fixture, mock_components


EVIDENCE = {}


@pytest.fixture(scope="module", autouse=True)
def write_evidence():
    yield
    target = Path(__file__).resolve().parents[2] / "ai/logs/langgraph-audit-traces.json"
    target.write_text(json.dumps(EVIDENCE, ensure_ascii=False, indent=2), encoding="utf-8")


def observe(w):
    """Use the real graph stream in place of ainvoke; record scheduler updates."""
    scheduled = []
    async def invoke(initial, config):
        result = initial
        async for update in w.graph.astream(initial, config=config, stream_mode="updates"):
            scheduled.extend(update)
            result = {**result, **next(iter(update.values()))}
        return result
    w.graph.ainvoke = invoke
    return scheduled


def record(name, run, scheduled):
    assert [s for s in scheduled if s != "halt"] == path(run)
    EVIDENCE[name] = dict(scheduled_nodes=scheduled, run=run.model_dump(mode="json"))


def test_audit_happy():
    w = workflow()
    scheduled = observe(w)
    run = execute(w)
    assert run.state.status == "completed" and run.outputs["validator"].is_valid
    assert w.graph.checkpointer is None
    record("happy", run, scheduled)


def test_audit_destination_refresh_changes_consumer_input():
    c = mock_components()
    original_select, original_find = c.destination_agent.select, c.place_agent.find
    async def select(request):
        result = await original_select(request)
        result.selected_region.province = "refreshed" if select.refresh else "original"
        return result
    select.refresh = False
    async def find(request, destination, times, **kwargs):
        if destination.selected_region.province == "original":
            select.refresh = True
            raise DataRequirement("destination_agent", "Refresh region metadata")
        places = await original_find(request, destination, times, **kwargs)
        places[0].suitability.score_places = 73
        return places
    c.destination_agent.select = AsyncMock(side_effect=select)
    c.place_agent.find = AsyncMock(side_effect=find)
    w = workflow(c)
    scheduled = observe(w)
    run = execute(w)
    assert run.state.status == "completed"
    regions = [v["selected_region"]["province"] for v in run.artifacts.values()
               if isinstance(v, dict) and "selected_region" in v]
    assert regions == ["original", "refreshed"]
    assert [call.args[1].selected_region.province for call in c.place_agent.find.call_args_list] == regions
    assert run.outputs["planning_input_builder"].candidate_places[0].score_places == 73
    assert run.visits["destination_agent"] == run.visits["place_agent"] == 2
    # First C invocation emits a requirement, not a successful candidates output.
    record("destination_refresh", run, scheduled)


@pytest.mark.parametrize("rule", ["budget", "input_integrity", "overlap"])
def test_audit_revision_changes_payload(rule):
    c = mock_components()
    reject_once(c, rule)
    original = c.planning_engine.plan
    async def plan(data):
        result = await original(data)
        result.summary.summary_message = f"seed={data.solver_config.random_seed}"
        return result
    c.planning_engine.plan = AsyncMock(side_effect=plan)
    w = workflow(c)
    scheduled = observe(w)
    run = execute(w)
    assert run.state.status == "completed"
    assert run.visits["validator"] == run.visits["planning_engine"] == 2
    assert [a.random_seed for a in run.attempts] == [42, 43]
    itineraries = [v for v in run.artifacts.values() if isinstance(v, dict) and "diagnostics" in v]
    assert [v["summary"]["summary_message"] for v in itineraries] == ["seed=42", "seed=43"]
    assert run.attempts[0].itinerary_id != run.attempts[1].itinerary_id
    record("revision_" + rule, run, scheduled)


def test_audit_snapshot_restore_and_resume():
    w = workflow()
    scheduled = observe(w)
    data = fixture("trip_request")
    data["budget"]["amount"] = None
    waiting = execute(w, data)
    assert waiting.state.status == "clarifying"
    record("clarification_wait", waiting, scheduled.copy())
    restored = GraphRun.model_validate_json(waiting.model_dump_json())
    final = execute(w, previous=restored, answer_raw="3000000")
    assert final.state.status == "completed"
    assert final.answers_history[-1].resolved_fields == ["budget.amount"]
    assert final.outputs["planning_input_builder"].budget.amount == 3000000
    assert set(waiting.artifacts) <= set(final.artifacts)
    record("clarification_resume", final, scheduled)


@pytest.mark.parametrize("kind", ["retry", "revision", "transition", "clarification"])
def test_audit_limits(kind):
    c = mock_components()
    limits = GraphLimits(max_revisions=100)
    data = fixture("trip_request")
    if kind == "retry":
        limits.max_retries = 1
        async def validate(itinerary, planning_input, **kwargs):
            from test_graph_workflow import validation
            return {**validation("overlap"), "trip_id": planning_input.trip_id}
        c.validator.validate = validate
    elif kind == "revision":
        limits.max_revisions = 2
        c.place_agent.find = AsyncMock(return_value=[])
    elif kind == "transition":
        limits.max_transitions = 4
        c.place_agent.find = AsyncMock(return_value=[])
    else:
        limits.max_clarifications = 0
        data["budget"]["amount"] = None
    w = workflow(c, limits=limits)
    scheduled = observe(w)
    run = execute(w, data)
    assert run.state.status == "failed" and run.final_result is None
    assert run.transitions <= limits.max_transitions and run.revisions <= limits.max_revisions
    if kind == "retry":
        assert run.retries == run.state.retry_count == 1
    record("limit_" + kind, run, scheduled)


def test_audit_retryable_error_is_terminal():
    c = mock_components()
    c.planning_engine.plan = AsyncMock(side_effect=ApplicationError(
        "external_api_error", "Temporary outage", retryable=True))
    w = workflow(c)
    scheduled = observe(w)
    run = execute(w)
    assert run.state.status == "failed" and run.errors[-1].retryable
    assert run.retries == run.state.retry_count == 0
    assert c.planning_engine.plan.await_count == 1
    record("retryable_error_missing_retry", run, scheduled)


def test_audit_dev_api_real_factory(monkeypatch):
    application = create_app(Settings(_env_file=None, database_url=None))
    # Spy on actual factory class, without overriding the FastAPI dependency.
    from ai.orchestration.graph_workflow import LangGraphOrchestrator
    original = LangGraphOrchestrator.run
    captured = []
    async def spy(self, *args, **kwargs):
        scheduled = observe(self)
        run = await original(self, *args, **kwargs)
        captured.append((run, scheduled))
        return run
    monkeypatch.setattr(LangGraphOrchestrator, "run", spy)
    with TestClient(application) as client:
        for name, data in [("dev_api_happy", fixture("trip_request")),
                           ("dev_api_unsupported", fixture("trip_request"))]:
            if name.endswith("unsupported"):
                data["destination"]["city"] = "unsupported city"
            response = client.post("/api/v1/dev/workflows/mock-run", json=data)
            assert response.status_code == 200
            run, scheduled = captured[-1]
            assert response.json()["state"]["status"] == run.state.status
            assert run.state.status == ("failed" if name.endswith("unsupported") else "completed")
            record(name, run, scheduled)
        invalid = client.post("/api/v1/dev/workflows/mock-run", json={})
        assert invalid.status_code == 422
    assert get_graph_orchestrator not in application.dependency_overrides
