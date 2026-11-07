-- Apply once to a canonical database provisioned from schema.sql. Do not run
-- against legacy Alembic 0001 databases.
BEGIN;

ALTER TABLE public.workflow_requests
  ADD COLUMN max_destination_rounds int NOT NULL DEFAULT 2,
  ADD CONSTRAINT workflow_requests_destination_round_limit_check
    CHECK (max_destination_rounds >= 0 AND destination_round <= max_destination_rounds);

ALTER TABLE public.clarification_rounds
  ADD COLUMN kind text NOT NULL DEFAULT 'trip_request';
ALTER TABLE public.clarification_rounds
  DROP CONSTRAINT clarification_rounds_request_id_round_key,
  ADD CONSTRAINT clarification_rounds_request_id_kind_round_key
    UNIQUE (request_id, kind, round);

COMMIT;
