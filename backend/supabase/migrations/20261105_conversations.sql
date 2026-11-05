-- Run once against the previous canonical schema, as the schema owner.
-- All DDL and backfill are atomic. Existing trips/messages are preserved.
BEGIN;
CREATE TABLE public.conversations (
 conversation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
 trip_id uuid UNIQUE REFERENCES public.trips(trip_id) ON DELETE SET NULL,
 request_id uuid REFERENCES public.workflow_requests(request_id) ON DELETE SET NULL,
 trip_request jsonb,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX conversations_user_idx ON public.conversations(user_id);
-- Reuse legacy trip UUIDs as conversation UUIDs so old bookmarks can be upgraded.
INSERT INTO public.conversations(conversation_id, user_id, trip_id, created_at)
 SELECT trip_id, user_id, trip_id, created_at FROM public.trips;
ALTER TABLE public.messages ADD COLUMN conversation_id uuid REFERENCES public.conversations(conversation_id) ON DELETE CASCADE;
UPDATE public.messages SET conversation_id = trip_id;
ALTER TABLE public.messages ALTER COLUMN conversation_id SET NOT NULL;
ALTER TABLE public.messages ALTER COLUMN trip_id DROP NOT NULL;
CREATE INDEX messages_conversation_idx ON public.messages(conversation_id, created_at);

CREATE FUNCTION public.owns_conversation(target uuid) RETURNS boolean LANGUAGE sql STABLE
SET search_path = '' AS $$
 SELECT EXISTS (SELECT 1 FROM public.conversations WHERE conversation_id = target AND user_id = (SELECT auth.uid()))
$$;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.conversations FROM anon, authenticated;
GRANT SELECT ON public.conversations TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.conversations TO service_role;
CREATE POLICY conversations_read ON public.conversations FOR SELECT TO authenticated
 USING (user_id = (SELECT auth.uid()));
DROP POLICY messages_owner ON public.messages;
-- Writes pass through the authenticated backend so callers cannot forge assistant replies.
REVOKE INSERT, UPDATE, DELETE ON public.messages FROM authenticated;
CREATE POLICY messages_read ON public.messages FOR SELECT TO authenticated
 USING (public.owns_conversation(conversation_id));
COMMIT;
