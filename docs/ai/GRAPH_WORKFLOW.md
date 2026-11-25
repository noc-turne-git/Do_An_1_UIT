# LangGraph dynamic mock workflow

LangGraph is the sole workflow orchestrator. Both mock-run routes depend on
`get_graph_orchestrator`; Python callers instantiate `LangGraphOrchestrator`.
Shared `WorkflowRun`, `StateMachine`, `STEPS`, `REFS` and `OUTPUTS` live in
`app/services/workflow_state.py`. See [removal result](LANGGRAPH_REMOVAL_RESULT.md).

```python
from datetime import date
from shared.contracts import TripRequest
from ai.orchestration.graph_workflow import LangGraphOrchestrator, GraphLimits
from ai.orchestration.mock_workflow import fixture, mock_components

workflow = LangGraphOrchestrator(
    mock_components(), defaults=fixture("planner_defaults"),
    limits=GraphLimits(max_clarifications=3, max_repair_rounds=3,
                       max_retries=3, max_transitions=80),
)
result = await workflow.run(
    TripRequest.model_validate(fixture("trip_request")),
    current_date=date(2026, 11, 4),
)
# Explicit structured user edit or clarification; previous is not mutated:
result = await workflow.run(updated_request, current_date=date(2026, 11, 4),
                            previous=result, answer_raw="Updated choices")
```

## Scheduling and implemented branches

`StateGraph(GraphState)` registers nine separate component nodes plus `halt`.
Each node invokes just its component. LangGraph calls `_route` through
`add_conditional_edges` after every node and at START. There is no Python
execution loop outside the compiled graph.
`workflow.graph` also supports native LangGraph streaming; the test suite checks
that every scheduled component appears as a separate stream update.

A = Destination Agent, B = Place Agent, C = Budget Module. Parser, Constraint
Planner, Builder and Explainer also have their own nodes. Prerequisites are
rebuilt in dependency order whenever a refresh invalidates their outputs.

| Trigger | Route / outcome |
| --- | --- |
| Parser missing fields, destination unresolved, or Planner missing required fields | `clarifying`, return questions and stop; explicit structured answer resumes |
| Component raises `DataRequirement(provider, reason)` | Refresh the named upstream provider, then rebuild invalidated consumers; provider and reason recorded |
| B returns no candidates or omits a requested must-visit ID/name | B searches again with a larger candidate limit |
| C reports missing costs, UNKNOWN price, mismatched place IDs, or required-place max costs exceeding the allowed budget | B searches again with a larger candidate limit; C and Builder rerun |
| Engine returns infeasible/partial without relaxation proposals | B expands search, C and Builder rerun, then Engine retries |
| Engine returns infeasible/partial with proposals | `awaiting_relaxation`; never apply proposals automatically |
| Engine returns error | Failed, record an error attempt |
| Validator requests replan with budget, price_integrity, or must_visit violation | B → C → Builder → Engine → Validator |
| Validator requests replan with input_integrity violation | Constraint Planner → B → C → Builder → Engine → Validator |
| Validator requests replan with other findings | Engine → Validator with fresh seed, without rerunning B/C |
| Validator asks user | Await relaxation when proposals exist; otherwise clarify additional_constraints |
| Validator fails | Failed; no Explainer/final result |
| Valid acceptance and successful Explainer | Completed, expose final result |
| Explicit user update to a nonfailed run | Parser → all affected downstream nodes, conservatively rebuild everything |
| Invalid output/ID, unsupported dependency, exception, or exhausted limit | Failed with structured error; no final result |

These paths are driven by returned domain data or explicit requirements.
There is no unconditional back edge or production routing based on call counts.
Controllable doubles change domain outcomes to exercise these paths in tests.
For example, one engine double remains infeasible until an expanded search
supplies the needed candidate metadata.

Adapters may import `DataRequirement` from `ai.orchestration.graph_workflow` and
raise it when their data is insufficient. Its optional `exclude_place_ids`
accumulate in state and are passed to B. Providers must precede the requester
in the dependency order; invalid/self/forward dependencies fail explicitly.
No free-text message is interpreted as a routing instruction.

## State, invalidation and limits

> **Canonical policy:** [CLARIFICATION_POLICY.md](CLARIFICATION_POLICY.md).
> Contracts and persistence are foundation work; parser, Agent A routing, graph
> counter fixes and Chat integration remain planned.

`GraphState` contains the structured user input, date, answer, previous parsed
request and `GraphRun`. `GraphRun` extends the existing Pydantic `WorkflowRun`
with current validated outputs, per-node visit counts, node-update history,
routing provider/reason, exclusions, candidate limit, revisions, retries, total
component transitions, last seed and stop reason. Existing contract artifacts,
checkpoints, questions, answers, errors and attempts remain available.

Before any node runs, its own previous output and all downstream outputs are
removed. Their current artifact references and completed markers are cleared;
final_result and explanation are cleared. Upstream outputs survive. New
validated outputs get fresh artifact IDs; immutable old JSON artifacts and
attempt references remain in history. Components receive deep copies of inputs.
History records invalidated nodes and artifact references before/after updates.

Limits persist across explicit resumes:

- Canonical budgets classify questions by purpose: trip_request uses clarification_round
  (max 3); destination_info and destination_choice share destination_round (max 2)
  owned by a destination episode. Count only newly persisted question identities.
  Retry does not count; the second open question can still be answered. The current
  graph counter increments on Agent A execution are a known runtime gap to fix next.
- Canonical routing first accepts an answer to an open question, even at the
  budget limit. With no open question, use the applicable purpose budget for new
  issuance or final resolve/default/fail. A persisted final resolve must never be
  rerun merely because pending_fields is empty. This routing is planned.
- After TripRequest clarification exhaustion, only configured defaults apply.
  `trip.start_date`, `trip.end_date`, `travelers.adults`, and
  `destination.city` when explicit never default; unresolved ones fail. See
  the policy document for children, preferences and budget.
- A repair round starts when Validator requests another itinerary cycle. The
  third round completes through validation; another failed validation stops
  with a recovery explanation. User turns and data refreshes do not consume
  repair rounds. `max_repair_rounds` defaults to 3.
- Retry counts every Engine invocation after the first. Both `max_retries` and
  the current PlanningInput's solver retry limit apply. Seeds increase across
  both direct replans and full preparation cycles.
- `max_transitions` bounds component invocations within each graph turn.
  `halt` is a terminal bookkeeping node, not another component invocation.
  LangGraph recursion_limit is a secondary guard above this application limit.
- Search expansion is capped by `max_candidates` (default 400). Exhausting a
  catalog still ends through transition limits.

The cost routing guard considers only required-place max costs and configured
overrun allowance. It does not treat the sum of every optional candidate as a
hard budget failure: the optimizer may skip optional places. User hard
constraints are never automatically changed.

## Scope and unsupported behavior

- Mock Agents, Builder, Engine and Validator remain fixture based. Constraint
  Planner is the existing deterministic implementation. No real LLM, Places API,
  solver optimization or execution of the Validator's 14 rules is added.
- Real catalog expansion/alternate destinations require richer adapters. The
  existing Mock Engine intentionally rejects dates/places outside its fixture.
  Tests use controlled doubles to demonstrate recovery, not an actual solver.
- Cross-agent requests support upstream data refresh. Arbitrary forward
  dependencies, parallel execution and automatic dependency discovery are not
  supported by the existing component protocols.
- A user change after `completed` resumes the same request under the 9.4
  policy (**planned**): reset `retry_count` and `clarification_round`, create a
  fresh episode with destination_round=0 if destination selection restarts,
  invalidate affected downstream outputs, and
  write fresh artifact IDs while retaining immutable historical artifacts.
  Failed runs are always terminal (lifecycle B). An explicit destination after failure
  requires both a new workflow request_id and a new destination episode_id.
  A fresh episode is also required when starting another destination selection after
  completed; do not reset the budget on an existing episode.
- Python resume accepts a `GraphRun`, including a JSON-deserialized snapshot.
  `WorkflowPersistence.save_graph/load_graph` stores/restores the application snapshot
  in `workflow_requests.graph_snapshot`. The authenticated mock-run endpoint resumes
  clarifying/awaiting_relaxation requests with a structured TripRequest and answer_raw;
  expected_transitions optionally detects stale updates. Request locks serialize writers.
  Native LangGraph checkpointers and natural-language answer parsing remain unsupported
  in the current implementation; the target unified chat/graph state machine is planned.
- Technical exceptions fail immediately. There is no automatic provider retry;
  the configured workflow retry budget covers replanning Engine attempts.

## Verification

Run database-independent tests from `backend` with a writable temporary directory:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -m "not postgres" -q -rs -p no:cacheprovider --basetemp=.tmp-langgraph-tests
```

See [removal result](LANGGRAPH_REMOVAL_RESULT.md) for executed counts and database
limitations. PostgreSQL integration tests are preserved; offline checks do not
establish PostgreSQL acceptance.
