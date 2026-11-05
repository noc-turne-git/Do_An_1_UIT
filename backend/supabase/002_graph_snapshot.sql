-- Apply only to an existing canonical Supabase schema in confirmed dev/test.
-- This is NOT compatible with legacy Alembic 0001.
BEGIN;
ALTER TABLE public.workflow_requests ADD COLUMN graph_snapshot jsonb;
COMMIT;
