from ai.tests.test_agent_runtime_graph import graph

def test_runtime_graph_clarification_and_api(monkeypatch):
    # Reuse existing API assertions: auth dependency, save/load snapshots, resume,
    # conflict handling, final response and artifact save hooks.
    import test_graph_api
    monkeypatch.setattr(test_graph_api,'graph',graph)
    test_graph_api.test_api_graph_dependency_and_persisted_result(monkeypatch)
    test_graph_api.test_json_recovery_preserves_typed_outputs_and_counters()

