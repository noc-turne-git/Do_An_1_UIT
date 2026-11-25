-- Runtime AISettings supplies the policy for inserts and refreshes it under the
-- workflow lock on resume. Do not keep a second configuration in SQL defaults.
-- The preceding consultation migration already permits historical/choice rounds
-- above the information cap and gates new information questions in the trigger.
BEGIN;
ALTER TABLE public.workflow_requests ALTER COLUMN max_destination_rounds DROP DEFAULT;
ALTER TABLE public.destination_episodes ALTER COLUMN max_destination_rounds DROP DEFAULT;
COMMIT;
