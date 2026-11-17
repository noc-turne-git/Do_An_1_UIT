-- Canonical choices can also receive a parser-confirmed new destination/intent
-- or an explicit unresolved response. An option still must match its snapshot.
BEGIN;
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
          (d->>'selection_intent' = 'UNSPECIFIED' AND d->>'selection_authority' IS NULL
            AND d->>'destination_source' IS NULL) OR
          (d->>'selection_intent' = 'EXPLICIT' AND d->>'selection_authority' = 'USER'
            AND d->>'destination_source' = 'user' AND length(trim(d->>'city')) > 0) OR
          (d->>'selection_intent' = 'USER_UNKNOWN' AND d->>'selection_authority' = 'USER'
            AND coalesce(d->>'destination_source', 'user') = 'user') OR
          (d->>'selection_intent' = 'ANY_DESTINATION' AND
            ((d->>'selection_authority' = 'USER' AND d->>'destination_source' IS NULL) OR
             (d->>'selection_authority' = 'USER' AND d->>'destination_source' = 'user') OR
             (d->>'selection_authority' = 'SYSTEM' AND d->>'destination_source' = 'SYSTEM_DEFAULT'))) OR
          (d->>'selection_intent' = 'DELEGATE_SELECTION' AND d->>'selection_authority' = 'AGENT'
            AND (d->>'destination_source' IS NULL OR d->>'destination_source' = 'AGENT_DELEGATED')), false) THEN
        RAISE EXCEPTION 'Destination update requires a canonical parser-confirmed intent';
      END IF;
    ELSIF NOT COALESCE(NEW.payload->'declared_unknown_fields' ? 'destination.city', false) THEN
      RAISE EXCEPTION 'Answer requires an option or parser-confirmed destination response';
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
COMMIT;
