"""Runtime integration regression: real LangGraph, mocked persistence only."""
import asyncio
from datetime import date
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from ai.agents.adapters.mock import runtime_mock_components
from ai.agents.runtime.context import execution_identity
from shared.contracts import TripRequest
from ai.orchestration.graph_workflow import LangGraphOrchestrator, GraphRun
from ai.orchestration.mock_workflow import fixture, mock_components
from ai.orchestration.workflow_state import STEPS
from support import confirmed_trip_request

def graph():
    return LangGraphOrchestrator(runtime_mock_components(), defaults=fixture('planner_defaults'))

def execute(w, request=None, **kwargs):
    return asyncio.run(w.run(request or TripRequest.model_validate(confirmed_trip_request()),
                             current_date=date(2026,11,4), **kwargs))

def test_runtime_graph_parity_identity_and_snapshots(monkeypatch):
    from ai.agents.runtime.harness import AgentHarness
    seen = []
    original = AgentHarness.run
    async def observe(self, definition, context, **kw):
        seen.append(context)
        return await original(self,definition,context,**kw)
    monkeypatch.setattr(AgentHarness,'run',observe)
    identifier, trip = uuid4(), uuid4()
    result = execute(graph(),request_id=identifier,trip_id=trip)
    legacy = execute(LangGraphOrchestrator(mock_components(),defaults=fixture('planner_defaults')),request_id=identifier,trip_id=trip)
    assert result.state.status == 'completed'
    assert result.outputs == legacy.outputs and result.final_result == legacy.final_result
    assert [e['step'] for e in result.history if e['event'] == 'node'] == list(STEPS)
    assert result.state.artifacts.itinerary_id in result.artifacts
    assert all(c.request_id == str(identifier) for c in seen) and len(seen) == 3
    assert execution_identity.get() is None
    restored = GraphRun.model_validate_json(result.model_dump_json())
    assert restored.outputs == result.outputs


def test_runtime_factory_feature_flag():
    from ai.config import AISettings as Settings
    from ai.interface import build_orchestrator
    from types import SimpleNamespace
    for enabled in (False,True):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=Settings(_env_file=None,agent_runtime_enabled=enabled))))
        w = build_orchestrator(request.app.state.settings)
        assert execute(w).state.status == 'completed'
        assert hasattr(w.components.destination_agent,'harness') == enabled
