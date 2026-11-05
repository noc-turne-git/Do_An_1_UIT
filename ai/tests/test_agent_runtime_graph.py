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

def graph():
    return LangGraphOrchestrator(runtime_mock_components(), defaults=fixture('planner_defaults'))

def execute(w, request=None, **kwargs):
    return asyncio.run(w.run(request or TripRequest.model_validate(fixture('trip_request')),
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
    assert [e['step'] for e in result.history] == list(STEPS)
    assert len(result.artifacts) == 8
    assert all(c.request_id == str(identifier) for c in seen) and len(seen) == 3
    assert execution_identity.get() is None
    restored = GraphRun.model_validate_json(result.model_dump_json())
    assert restored.outputs == result.outputs

@pytest.mark.parametrize('scenario',[
    'test_a_b_c_b_planning_missing_costs',
    'test_engine_b_c_engine_and_state_propagation',
    'test_validator_engine_validator',
    'test_agent_requires_other_agent_and_consumer_rebuilt',
    'test_explicit_exclusions_pass_to_place_agent',
    'test_empty_place_search_expands_then_succeeds',
    'test_missing_must_visit_expands',
    'test_required_cost_over_budget_routes_b_without_relaxing_request',
    'test_optional_catalog_sum_is_not_budget_failure',
    'test_user_update_rebuilds_and_keeps_old_artifacts',
    'test_infeasible_with_relaxation_waits_for_user',
    'test_module_cannot_mutate_state_or_original_input',
])
def test_runtime_graph_routing(monkeypatch, scenario):
    import test_graph_workflow
    monkeypatch.setattr(test_graph_workflow,'mock_components',runtime_mock_components)
    getattr(test_graph_workflow,scenario)()

@pytest.mark.parametrize('rule,target', [('budget','place_agent'),
    ('price_integrity','place_agent'), ('must_visit','place_agent'),
    ('input_integrity','constraint_planner')])
def test_runtime_validator_routes(monkeypatch, rule, target):
    import test_graph_workflow
    monkeypatch.setattr(test_graph_workflow,'mock_components',runtime_mock_components)
    test_graph_workflow.test_validator_preparation_routes(rule,target)

@pytest.mark.parametrize('kind',['revision','transition','retry','solver_retry'])
def test_runtime_graph_limits(monkeypatch, kind):
    import test_graph_workflow
    monkeypatch.setattr(test_graph_workflow,'mock_components',runtime_mock_components)
    test_graph_workflow.test_limits(kind)

def test_runtime_graph_persistence_hooks():
    persistence = MagicMock()
    w = graph()
    w.persistence = persistence
    result = execute(w)
    assert result.state.status == 'completed'
    assert persistence.save.call_count == 8
    persistence.save_graph.assert_called_once_with(result)
    assert persistence.sync.called

def test_runtime_factory_feature_flag():
    from ai.config import AISettings as Settings
    from ai.interface import build_orchestrator
    from types import SimpleNamespace
    for enabled in (False,True):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=Settings(_env_file=None,agent_runtime_enabled=enabled))))
        w = build_orchestrator(request.app.state.settings)
        assert execute(w).state.status == 'completed'
        assert hasattr(w.components.destination_agent,'harness') == enabled
