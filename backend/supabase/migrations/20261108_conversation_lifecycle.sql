BEGIN;

ALTER TABLE public.clarification_questions DROP CONSTRAINT clarification_questions_status_check;
ALTER TABLE public.clarification_questions ADD CONSTRAINT clarification_questions_status_check
  CHECK (status IN ('open','answered','cancelled','superseded'));
CREATE OR REPLACE FUNCTION public.guard_canonical_question() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (to_jsonb(NEW) - 'status' - 'payload') IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'payload')
     OR (NEW.payload - 'status') IS DISTINCT FROM (OLD.payload - 'status')
     OR (NEW.status <> OLD.status AND (OLD.status <> 'open' OR NEW.status NOT IN ('answered','cancelled','superseded'))) THEN
    RAISE EXCEPTION 'Issued question snapshot is immutable';
  END IF;
  RETURN NEW;
END $$;

ALTER TABLE public.conversations ADD COLUMN active_episode_id uuid;
ALTER TABLE public.conversations ADD COLUMN revision integer NOT NULL DEFAULT 0 CHECK (revision >= 0);
ALTER TABLE public.conversations ADD CONSTRAINT conversation_active_episode_fk
  FOREIGN KEY (request_id, active_episode_id) REFERENCES public.destination_episodes(request_id, episode_id);
ALTER TABLE public.conversations ADD CONSTRAINT conversation_active_episode_requires_workflow
  CHECK (active_episode_id IS NULL OR request_id IS NOT NULL);
-- Only canonical identities are projected; legacy history stays non-actionable.
UPDATE public.conversations c SET active_episode_id=w.active_episode_id
  FROM public.workflow_requests w WHERE w.request_id=c.request_id;

CREATE TABLE public.conversation_turns (
  input_id uuid PRIMARY KEY,
  conversation_id uuid NOT NULL REFERENCES public.conversations(conversation_id) ON DELETE CASCADE,
  input_payload jsonb NOT NULL,
  response_payload jsonb,
  request_id uuid REFERENCES public.workflow_requests(request_id),
  message_id uuid REFERENCES public.messages(message_id)
);
CREATE INDEX conversation_turns_conversation_idx ON public.conversation_turns(conversation_id);
ALTER TABLE public.conversation_turns ENABLE ROW LEVEL SECURITY;
CREATE POLICY conversation_turns_owner ON public.conversation_turns FOR SELECT TO authenticated
  USING (EXISTS (SELECT 1 FROM public.conversations c WHERE c.conversation_id=conversation_turns.conversation_id AND c.user_id=auth.uid()));
GRANT SELECT ON public.conversation_turns TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.conversation_turns TO service_role;

COMMIT;
