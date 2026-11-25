"""Executable audit evidence. All scheduling is performed by compiled LangGraph."""
import json
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
from support import confirmed_trip_request


EVIDENCE = {}


@pytest.fixture(scope="module", autouse=True)
def write_evidence(tmp_path_factory):
    yield
    target = tmp_path_factory.mktemp('langgraph-audit') / 'traces.json'
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
    async def select(request, *, context=None):
        result = await original_select(request, context=context)
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
    data = confirmed_trip_request()
    data['destination']['province'] = None  # Resolver metadata, not a user constraint.
    run = execute(w, data)
    assert run.state.status == "completed", run.errors
    assert run.repair_rounds == 0
    regions = [v["selected_region"]["province"] for v in run.artifacts.values()
               if isinstance(v, dict) and "selected_region" in v]
    assert regions == ["original", "refreshed"]
    assert [call.args[1].selected_region.province for call in c.place_agent.find.call_args_list] == regions
    assert run.outputs["planning_input_builder"].candidate_places[0].score_places == 73
    assert run.visits["destination_agent"] == run.visits["place_agent"] == 2
    # First C invocation emits a requirement, not a successful candidates output.
    record("destination_refresh", run, scheduled)


def test_audit_snapshot_restore_and_resume():
    w = workflow()
    scheduled = observe(w)
    data = confirmed_trip_request()
    data["trip"]["start_date"] = None
    waiting = execute(w, data)
    assert waiting.state.status == "clarifying"
    record("clarification_wait", waiting, scheduled.copy())
    restored = GraphRun.model_validate_json(waiting.model_dump_json())
    final = execute(w, previous=restored, answer_raw="14/11/2026")
    assert final.state.status == "completed"
    assert final.answers_history[-1].resolved_fields == ["trip.start_date"]
    assert final.outputs["planning_input_builder"].budget.amount == 3000000
    assert set(waiting.artifacts) <= set(final.artifacts)
    record("clarification_resume", final, scheduled)
