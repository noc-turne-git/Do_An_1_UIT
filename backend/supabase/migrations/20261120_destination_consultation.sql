-- Destination choice is conversational; information-gathering limits never
-- authorize an automatic selection. Existing final-resolve records are audit.
BEGIN;

-- Guest chat needs the same candidate/permission history, without creating
-- account-owned trips, workflow requests or artifacts.
ALTER TABLE public.conversations ADD COLUMN guest_graph_snapshot jsonb;

ALTER TABLE public.workflow_requests DROP CONSTRAINT workflow_requests_destination_round_limit_check;
ALTER TABLE public.workflow_requests ADD CONSTRAINT workflow_requests_destination_round_limit_check
  CHECK (destination_round >= 0 AND max_destination_rounds >= 0);
DO $$ DECLARE item record; BEGIN
  FOR item IN SELECT conname FROM pg_constraint
    WHERE conrelid = 'public.destination_episodes'::regclass AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%destination_round%'
  LOOP
    EXECUTE format('ALTER TABLE public.destination_episodes DROP CONSTRAINT %I', item.conname);
  END LOOP;
END $$;
ALTER TABLE public.destination_episodes ADD CONSTRAINT destination_episodes_destination_round_check
  CHECK (destination_round >= 0 AND max_destination_rounds >= 0);

CREATE OR REPLACE FUNCTION public.issue_canonical_question() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE w public.workflow_requests; e public.destination_episodes;
BEGIN
  SELECT * INTO w FROM public.workflow_requests WHERE request_id=NEW.request_id FOR UPDATE;
  SELECT * INTO e FROM public.destination_episodes WHERE episode_id=NEW.episode_id FOR UPDATE;
  IF w.status IN ('failed','completed') OR w.active_episode_id IS DISTINCT FROM NEW.episode_id
     OR e.status <> 'active' OR NEW.status <> 'open' THEN
    RAISE EXCEPTION 'Question requires active workflow episode';
  END IF;
  IF NEW.payload->>'intent_snapshot' IS DISTINCT FROM e.selection_policy->>'selection_intent' THEN
    RAISE EXCEPTION 'Question intent differs from episode';
  END IF;
  IF NEW.counter_group = 'destination' THEN
    IF NEW.round <> e.destination_round + 1
       OR (NEW.kind <> 'destination_choice' AND NEW.round > e.max_destination_rounds) THEN
      RAISE EXCEPTION 'Destination information budget exhausted or stale round';
    END IF;
    UPDATE public.destination_episodes SET destination_round=NEW.round WHERE episode_id=NEW.episode_id;
    UPDATE public.workflow_requests SET destination_round=NEW.round WHERE request_id=NEW.request_id;
  ELSE
    IF NEW.round <> w.clarification_round + 1 OR NEW.round > w.max_clarification_rounds THEN
      RAISE EXCEPTION 'Trip request budget exhausted or stale round';
    END IF;
    UPDATE public.workflow_requests SET clarification_round=NEW.round WHERE request_id=NEW.request_id;
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION public.answer_canonical_question() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE w public.workflow_requests; q public.clarification_questions; d jsonb;
BEGIN
  SELECT * INTO w FROM public.workflow_requests WHERE request_id=NEW.request_id FOR UPDATE;
  SELECT * INTO q FROM public.clarification_questions WHERE question_id=NEW.question_id FOR UPDATE;
  IF w.status IN ('failed','completed') OR w.active_episode_id IS DISTINCT FROM NEW.episode_id
     OR q.episode_id IS DISTINCT FROM NEW.episode_id OR q.request_id IS DISTINCT FROM NEW.request_id
     OR q.status IS DISTINCT FROM 'open' THEN
    RAISE EXCEPTION 'Stale or cross-episode answer';
  END IF;
  IF (NEW.payload->>'kind') IS DISTINCT FROM q.kind OR (NEW.payload->>'round')::integer IS DISTINCT FROM q.round
     OR NEW.payload->>'question' IS DISTINCT FROM q.payload->>'question'
     OR NEW.payload->'asked_fields' IS DISTINCT FROM q.payload->'fields' THEN
    RAISE EXCEPTION 'Answer snapshot does not match issued question';
  END IF;
  d := NEW.payload->'destination_update';
  IF q.kind = 'destination_choice' THEN
    IF NEW.payload->>'selected_option_id' IS NOT NULL THEN
      IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(q.payload->'options') o
          WHERE o->>'option_id' = NEW.payload->>'selected_option_id')
          OR (d IS NOT NULL AND d <> 'null'::jsonb) THEN
        RAISE EXCEPTION 'Answer option was not issued or conflicts with destination update';
      END IF;
    ELSIF d IS NOT NULL AND d <> 'null'::jsonb THEN
      IF NOT COALESCE(
          (d->>'selection_intent' = 'EXPLICIT' AND d->>'selection_authority' = 'USER'
            AND d->>'destination_source' IN ('USER','user') AND length(trim(d->>'city')) > 0) OR
          (d->>'selection_intent' IN ('USER_UNKNOWN','ANY_DESTINATION')
            AND d->>'selection_authority' = 'USER'
            AND (d->>'destination_source' IS NULL OR d->>'destination_source' IN ('USER','user'))) OR
          (d->>'selection_intent' = 'DELEGATE_SELECTION'
            AND ((d->>'selection_authority' IN ('USER','AGENT') AND d->>'destination_source' IS NULL)
              OR (d->>'selection_authority' = 'AGENT' AND d->>'destination_source' = 'AGENT_DELEGATED'))), false) THEN
        RAISE EXCEPTION 'Destination update requires a canonical user intent';
      END IF;
    ELSIF NOT COALESCE(NEW.payload->'declared_unknown_fields' ? 'destination.city', false)
          AND coalesce(NEW.payload->>'destination_action', 'none') NOT IN ('delegate','refine','suggest_again') THEN
      RAISE EXCEPTION 'Answer requires an option, a destination update, or user feedback';
    END IF;
  ELSIF d IS NOT NULL AND d <> 'null'::jsonb THEN
    RAISE EXCEPTION 'Destination update belongs to a destination choice response';
  END IF;
  IF q.payload->'constraint_proposal' <> 'null'::jsonb AND (
    NEW.payload->>'confirmed_proposal_id' IS DISTINCT FROM q.payload->'constraint_proposal'->>'proposal_id'
    OR jsonb_typeof(NEW.payload->'constraint_confirmed') IS DISTINCT FROM 'boolean') THEN
    RAISE EXCEPTION 'Constraint proposal requires explicit confirmation';
  END IF;
  UPDATE public.clarification_questions SET status='answered', payload=jsonb_set(payload,'{status}','"answered"')
    WHERE question_id=NEW.question_id;
  UPDATE public.workflow_requests SET status='planning' WHERE request_id=NEW.request_id;
  RETURN NEW;
END $$;

CREATE FUNCTION public.prevent_automatic_destination_resolution() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.final_resolve_status, NEW.final_resolve_id, NEW.final_resolve_result)
       IS DISTINCT FROM (OLD.final_resolve_status, OLD.final_resolve_id, OLD.final_resolve_result) THEN
    RAISE EXCEPTION 'Automatic destination resolution is retired';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER prevent_automatic_destination_resolution BEFORE UPDATE ON public.destination_episodes
  FOR EACH ROW EXECUTE FUNCTION public.prevent_automatic_destination_resolution();
COMMIT;
