# Chat → Conversation → TripRequest → Trip

## Lifecycle

Chat home uses `conversation_id` in the URL. A planning turn creates and associates a
Trip, WorkflowRequest and canonical destination episode in the same transaction as
its messages and turn receipt. Advice and ordinary conversation preserve the current
planning state. Reloading the URL restores the latest 100 messages and the active
workflow can be restored from its relational state plus GraphRun snapshot.

Every transport calls the same `run_turn` path. The parser only extracts and merges
fields; Graph owns routing, question issuance, answer history and workflow lifecycle.
A referenced answer is checked against workflow, episode and open question identity
before parser execution. Closed, superseded, cross-episode and terminal answers return
409 and cannot become a new explicit input. Existing conversation rows are locked to
serialize turns. The parser sees the last 12 messages, previous_request, active question
snapshot, workflow context and the current date in Asia/Ho_Chi_Minh.

## API contract

All routes require `Authorization: Bearer <Supabase access token>`. Ownership comes
from verified authentication, never from request bodies. Unknown/foreign IDs return 404.

- POST `/api/v1/chat/conversations`: no body; creates an empty conversation (201).
- POST `/api/v1/chat/messages`: `{ "input_id": "<uuid>", "content": "Đi Đà Lạt",
  "conversation_id": null, "workflow_id": null, "episode_id": null,
  "question_id": null, "expected_revision": null, "expected_transitions": null }`.
  Omitting conversation_id creates one atomically with the first message (201).
  Response: `{ message_id, conversation_id, role, content, created_at, assistant,
  parser_status, missing_fields, error_code, input_id, revision, workflow_id,
  episode_id, workflow_status, questions, clarification_round, destination_round,
  remaining_destination_rounds, selection_policy, transitions }`. The full issued
  question/options snapshot and selection authority are returned for the UI. A response
  can have `remaining_destination_rounds=0` while its second question remains open.
  `input_id` is an idempotency identity: an identical committed retry returns the stored
  response, while reuse with different content returns 409.
  Only user messages can be submitted. Text is trimmed, nonblank, max 10,000 characters.
- GET `/api/v1/chat/conversations/{id}/messages?limit=100`: latest 1–100 messages,
  returned chronologically. Replaces the former trip-based history route.
- GET `/api/v1/chat/conversations/{id}`: `{ conversation_id, trip_id, request_id,
  active_episode_id, revision, trip_request }`.
- GET `/api/v1/chat/conversations/{id}/workflows`: returns current and historical
  workflow identities, active episode identities and statuses for the conversation trip.
- POST `/api/v1/chat/conversations/{id}/prepare-trip`:
  `{ "trip_request": <complete TripRequest object> }`.
  This is a structured handoff/testing endpoint, not an LLM call. Pydantic checks
  types, dates, budget consistency and the existing TripRequest contract. The service
  independently checks required values even when missing_fields is forged or fields
  are declared user-provided. Incomplete data returns 400; malformed data returns 422.
  Success returns Conversation metadata (200), creates Trip + WorkflowRequest +
  trip_request artifact, and links them in one transaction. Identical retries reuse
  the same Trip; a different payload on a linked Conversation is rejected (400).
  Locking the Conversation serializes concurrent preparation attempts.

Required values: destination.selection_mode; city for explicit destinations;
start_date/end_date; adults/children with at least one traveler; interests, pace,
transport_modes; budget amount/scope. Empty preference lists may represent no
preference; an explicit zero budget is allowed. Other constraints use TripRequest.
Preparation saves the accepted input but does not run the mock planning workflow.
A future LLM integration can invoke the existing orchestrator using request_id,
trip_id and the stored trip_request once real planning components are ready.

## Database upgrade

For an EXISTING database on the previous schema, apply the sequential migrations through
`backend/supabase/migrations/20261108_conversation_lifecycle.sql` via Supabase SQL Editor
or psql with ON_ERROR_STOP enabled. It is transactional: failures roll back the DDL
and backfill. Do not rerun the entire schema.sql on an existing database and do not
use the obsolete Alembic migration. This migration has not been applied automatically.

The migration preserves all trips and messages, creates a Conversation per existing
Trip, and backfills messages.conversation_id. Legacy messages.trip_id remains
nullable for compatibility; all new chat writes use conversation_id. Conversation
ownership has RLS; authenticated clients can read their conversations/messages,
while writes go through the backend. service_role retains CRUD grants. No existing
message content or trip is deleted. Old Conversations already linked to legacy
Trips are kept as-is; prepare-trip rejects relinking them.

For a NEW empty database, use the updated canonical `backend/supabase/schema.sql`
(includes the same Conversation schema). Do not also run the incremental migration.

## Run and verify

Configure backend DATABASE_URL, SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and frontend
Supabase settings. Run backend on port 8000 and `npm run dev` at the root. Vite proxies
/api to backend. For separate production origins set VITE_API_BASE_URL and backend CORS.

1. Sign in and send several messages on Chats home. Observe conversation_id in URL.
2. Check conversations/messages in DB: same conversation, no new Trip.
3. Reload the URL: history must be restored; another account must receive 404.
4. Submit an incomplete TripRequest to prepare-trip: no Trip should be inserted.
5. Submit a complete, actually validated TripRequest: inspect returned trip_id and
   request_id, and the trip_request artifact. Repeating the same submission must not
   create another Trip. Test data shape is available in shared/samples/trip_request.json.

Backend tests:
`.venv/Scripts/python.exe -m pytest tests/test_chat_api.py tests/test_file_logging.py tests/test_persistence.py -q`
Frontend: `npm --prefix frontend run build`.
Real PostgreSQL integration: set TEST_DATABASE_URL to an EMPTY disposable LOCAL DB
whose name contains test, then run `pytest tests/test_database.py -q`. The existing
integration harness refuses nonempty/nonlocal databases and never falls back to .env.
Parser tests use scripted LLM outputs, not live model calls. Run all backend tests
with `backend/.venv/Scripts/python.exe -m pytest backend/tests -q` from repository root.

## Logs and limitations

Console retains HTTP request IDs/status/duration and database status logs.
Committed messages log identifiers, role and character counts, without bodies.
The trace is `ai/logs/conversations/<conversation_id>/runs/<run_id>/events.jsonl`
(configured by `AI_TRACE_ROOT`). No aggregate `execution.jsonl` is written.
A `run_id` is generated for every HTTP chat turn and every direct `run_turn`; its
`workflow_id`, `trip_id`, and HTTP `request_id` remain separate correlation fields.
The HTTP response includes `X-Trace-Run-ID`. Read every run folder beneath a
conversation to reconstruct its history. Standalone runs use the `standalone`
conversation folder.

Events include chat extraction metadata, graph start/end states, node state
transitions/outputs, routes, agent decisions, LLM request/response metadata and
output validation, persistence operations, and transaction outcomes. Raw prompts,
message bodies, free-text constraints, credentials, and contact-like values are
redacted with length/fingerprint metadata. Parser events occur before the request
transaction commits; transaction events record committed or rolled-back outcomes.
Each run keeps its complete JSONL file until `DIAGNOSTIC_RETENTION_DAYS` (default
30) expires; old run folders are pruned at startup and at most once daily while
writing. Each event is bounded to 1 MiB, and oversize events record an explicit
truncation marker. Legacy `AI_LOG_FILE`, `LOG_MAX_BYTES`, and `LOG_BACKUP_COUNT`
settings are accepted; only `AI_LOG_FILE` affects the trace directory location.
Tokens and API keys are never logged.
Streaming is not implemented. Clients must retain `input_id` across an ambiguous timeout;
the receipt prevents a duplicate committed turn, workflow or episode.

## Real parser configuration and semantics

Set backend/.env LLM_PROVIDER=openai, OPENAI_MODEL and OPENAI_API_KEY (or
LLM_MODEL/LLM_API_KEY); OPENAI_BASE_URL optionally selects a compatible provider.
Chat does not depend on AGENT_RUNTIME_ENABLED. Mock mode without scripted responses
returns a safe error reply, not a fabricated request. The lifecycle migration adds the
conversation association, revision and durable `conversation_turns` receipt table.

The LLM returns a Vietnamese summary, field changes and grouped follow-up questions.
The server merges changed fields only, validates TripRequest and filters questions
against actual missing information. At most three question groups appear per turn.
Invalid JSON, inconsistent dates and invalid schema values keep the previous draft
and produce an error reply; provider exception text is never exposed.

meta.field_decisions stores SPECIFIED, UNKNOWN, FLEXIBLE, AI_DECIDE, NO_PREFERENCE
and DEFERRED per path. UNKNOWN offers suggestions/asks permission rather than
delegating. FLEXIBLE/AI_DECIDE/NO_PREFERENCE preserve null without repeatedly asking
delegable constraints; DEFERRED stays missing but is not routinely asked again.
Adults/children counts cannot be delegated and must total at least one.

clarifying = incomplete collection; ready = collection completed, including explicit
delegation; error = this turn failed and the previous validated values survived.
ready can advance the associated workflow and may still contain delegated nulls that
the destination policy resolves. Failed workflows are terminal: a new explicit
destination creates a new workflow and episode at destination_round=0 while preserving
the failed workflow history and the approved non-destination TripRequest baseline.

Inspect logs from repository root:

```powershell
.\.venv\Scripts\python.exe -m ai.logging --conversation-id <conversation_id>
.\.venv\Scripts\python.exe -m ai.logging --run-id <run_id>
Get-Content ai/logs/conversations/<conversation_id>/runs/<run_id>/events.jsonl
```

Live smoke test: sign in, send a request, answer questions, then try uncertainty,
flexibility, AI delegation and deferral for a preference. Revise the dates. Inspect
the same conversation's trip_request, workflow/episode associations and log per turn.
Scripted tests cover parser/state contracts and errors,
not a live model's Vietnamese interpretation accuracy.
