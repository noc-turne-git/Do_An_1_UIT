# Mock workflow on LangGraph

LangGraph is the sole scheduler for the nine component protocols. See
[GRAPH_WORKFLOW.md](../ai/GRAPH_WORKFLOW.md) for routing, limits, invalidation and resume,
and [README.md](../../README.md) for API and database setup.

`app/services/mock_workflow.py` supplies fixture adapters. Constraint Planner uses
the deterministic implementation. Mock Engine and Validator do not optimize a
trip or execute the fourteen business validation rules. The fixture supports
Da Lat, 14–16 November 2026, p001/p002/p003 and VND; unsupported fixture inputs
return structured errors. Replace component adapters through their protocols.

The normal path is Parser → Destination → Constraint Planner → Places → Budget
→ Planning Input Builder → Engine → Validator → Explainer. Domain outcomes can
refresh upstream data and rebuild dependent outputs. Infeasible results without
relaxation proposals expand candidates; proposals require an explicit answer.
Validator findings select the appropriate replan route. Technical exceptions
fail immediately; cancellation propagates as `asyncio.CancelledError`.

All component outputs undergo Pydantic validation before they become artifacts.
Artifacts have fresh UUIDs and retain immutable historical payloads. Shared run
contracts and state transitions live in `app/services/workflow_state.py`.

`POST /api/v1/dev/workflows/mock-run` is an in-memory demo with the existing
`WorkflowRun` response and `mode="development_mock"`. HTTP 200 includes domain
failures or clarification; invalid request bodies return 422.

The authenticated `POST /api/v1/requests/{request_id}/mock-run` stores artifacts,
projections and a JSON `GraphRun` snapshot through WorkflowPersistence. Resume
requires an updated structured TripRequest and answer_raw. Python callers can
also call `LangGraphOrchestrator.run(..., previous=run, answer_raw=...)`.
Mock Parser does not interpret natural-language answers. Native LangGraph
checkpointers and automatic transient retries remain unsupported.

Run database-independent tests from `backend`:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -m "not postgres" -q -rs -p no:cacheprovider --basetemp=.tmp-langgraph-tests
```

Business regressions remain in `tests/test_mock_workflow.py`,
`tests/test_full_backend.py` and `tests/test_business_parity.py`; graph routing,
scheduler traces, API and persistence have additional dedicated suites.
See [LANGGRAPH_REMOVAL_RESULT.md](LANGGRAPH_REMOVAL_RESULT.md) for current results.
