# Canonical clarification foundation — verification

Verified on 2026-11-07 with Python 3.14.7, PostgreSQL 18.4, OpenAI SDK 3.39.0
(the repository's declared SDK range). Final suite: **504 passed, 1 skipped**.
The skipped test is the opt-in live OpenAI test. Thirteen warnings are upstream
LangSmith Python deprecation warnings. No production/Supabase database was used.

## Reproduce

Use an empty, disposable PostgreSQL database on localhost whose name includes
`test`. Set `TEST_DATABASE_URL`; the fixture refuses non-local or populated
databases and does not read `DATABASE_URL`. Install the monorepo Python projects
and their test dependencies, then run from the repository root:

```powershell
$env:TEST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:55439/canonical_test_verified'
.\.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp=backend/.tmp-canonical-verified
```

Use a **new empty database name** for every run. The fixture intentionally keeps
test databases for inspection. The parity test provisions another uniquely named
local test database; the test role needs CREATE DATABASE. The completed local run
used a dedicated cluster in ignored `backend/.tmp-postgres-canonical`, port 55439.

## Evidence covered

`ai/tests/test_clarification_contracts.py` checks safe legacy defaults, explicit
authority/provenance, single-candidate confirmation, ranked default after final
resolve, episode budget/ownership, structured recovery, cross-question responses,
constraint confirmation, serialization and exported JSON Schema validation/drift.

`backend/tests/test_database.py` includes 23 PostgreSQL tests (plus a no-database
configuration test). Canonical cases cover:

- Both info → choice and choice → info, preserving fields, complete options,
  candidate identity/rank/reason, constraint proposal, intent and round snapshots.
- Fresh-session relational and graph reload with the second question open;
  answering it at destination_round=2; rejecting a third issuance.
- Same-ID retries and simultaneous retry writers consume one budget slot;
  direct SQL cannot allocate the same destination round under a different kind.
- Independent TripRequest budget, issuance rollback, answer rollback, stale,
  cross-episode, unknown-option and cross-owner rejection.
- Immutable issued question/option snapshots and answers, owner RLS and rejection
  of a modified graph snapshot.
- Persisted final-resolve claim across restart; acquired=False on retry; refusal
  of another operation ID; immutable completed result reused by both load paths.
- Failed workflow stays unchanged; a fresh workflow and episode reuse trip_id,
  seed a new validated TripRequest artifact, start counters at zero and inherit
  no old question/history/downstream references.
- Pre-migration legacy rows remain readable without fabricated canonical IDs or
  delegation. Explicit legacy adoption retains consumed budget.
- Alembic/Supabase parity for columns/defaults, constraints, indexes, triggers,
  policies and functions, using two separately provisioned local databases.

The full suite also covers existing graph/API/planning behavior. Frozen legacy
business expectations are deserialized through current contracts to add only
safe schema defaults; their business values remain frozen.

## Migration boundary

Committed migrations and baseline SQL were preserved. The historical Alembic
baseline currently expects a SHA-256/header that differs from committed
`schema.sql`. It cannot provision a fresh database directly. The test and documented
installation path provision the exact Supabase baseline in a verified empty
database, stamp that known baseline, then run the real sequential Alembic
upgrades. No hash check is bypassed and no old migration is rewritten.

The previous revision ID also exceeds Alembic's default varchar(32); Alembic env
now provisions/widens its version column to varchar(128), keeping old IDs intact.
The new migration executes the same SQL as the new Supabase migration.

## Implemented versus planned

Implemented: canonical contracts, three new relational tables, workflow episode
ownership, shared destination budget, atomic/idempotent persistence operations,
graph snapshot consistency checks, terminal failure protection, lifecycle B
factory and durable final-resolve claim/result.

Still planned: intent parsing, Agent A purpose/authority routing, fixing graph
counter increments on each Agent A run, orchestration calls to the canonical
repository, provider reconciliation for an interrupted claim, and Chat selection
integration. Canonical issuance is explicit; legacy sync never fabricates valid
canonical questions. A persisted claim prevents automatic re-execution but cannot
promise external-provider exactly-once semantics without provider cooperation.

These three commits complete the foundation, not the end-to-end clarification flow.
