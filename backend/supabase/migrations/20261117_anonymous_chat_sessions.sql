-- Guest chat ownership. Run as the schema owner after the conversation lifecycle migration.
BEGIN;

CREATE TABLE public.anonymous_sessions (
 anonymous_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 last_seen_at timestamptz NOT NULL DEFAULT now(),
 CHECK (expires_at > created_at)
);
CREATE INDEX anonymous_sessions_expiry_idx ON public.anonymous_sessions(expires_at);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.anonymous_sessions TO service_role;

ALTER TABLE public.conversations
 ADD COLUMN anonymous_session_id uuid REFERENCES public.anonymous_sessions(anonymous_session_id) ON DELETE CASCADE;
ALTER TABLE public.conversations ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE public.conversations ADD CONSTRAINT conversations_owner_check
 CHECK ((user_id IS NOT NULL) <> (anonymous_session_id IS NOT NULL));
CREATE INDEX conversations_anonymous_session_idx ON public.conversations(anonymous_session_id);

COMMIT;
