-- Canonical branch only. Apply after 20261107_clarification_round_kinds.sql.
BEGIN;

CREATE TABLE public.destination_episodes (
  episode_id uuid PRIMARY KEY,
  request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','failed')),
  destination_round integer NOT NULL DEFAULT 0,
  max_destination_rounds integer NOT NULL DEFAULT 2,
  selection_policy jsonb NOT NULL,
  final_resolve_status text NOT NULL DEFAULT 'not_started',
  final_resolve_id uuid UNIQUE,
  final_resolve_result jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (request_id, episode_id),
  CHECK (destination_round >= 0 AND destination_round <= max_destination_rounds AND max_destination_rounds BETWEEN 0 AND 2),
  CHECK (final_resolve_status IN ('not_started','claimed','completed')),
  CHECK ((final_resolve_status = 'not_started') = (final_resolve_id IS NULL)),
  CHECK ((final_resolve_status = 'completed') = (final_resolve_result IS NOT NULL))
);
CREATE INDEX destination_episodes_request_idx ON public.destination_episodes(request_id);
ALTER TABLE public.workflow_requests ADD COLUMN active_episode_id uuid;
ALTER TABLE public.workflow_requests ADD CONSTRAINT workflow_active_episode_fk
  FOREIGN KEY (request_id, active_episode_id) REFERENCES public.destination_episodes(request_id, episode_id);

CREATE TABLE public.clarification_questions (
  question_id uuid PRIMARY KEY,
  request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
  episode_id uuid NOT NULL,
  counter_group text NOT NULL CHECK (counter_group IN ('trip_request','destination')),
  round integer NOT NULL CHECK (round > 0),
  kind text NOT NULL CHECK (kind IN ('trip_request','destination_info','destination_choice')),
  status text NOT NULL CHECK (status IN ('open','answered','cancelled')),
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (request_id, episode_id, question_id),
  UNIQUE (episode_id, counter_group, round),
  FOREIGN KEY (request_id, episode_id) REFERENCES public.destination_episodes(request_id, episode_id) ON DELETE CASCADE,
  CHECK ((kind = 'trip_request') = (counter_group = 'trip_request')),
  CHECK (payload ?& ARRAY['question_id','episode_id','kind','round','status','intent_snapshot','question','fields','options']),
  CHECK (jsonb_typeof(payload->'fields') = 'array' AND jsonb_typeof(payload->'options') = 'array'),
  CHECK (payload->>'question_id' = question_id::text AND payload->>'episode_id' = episode_id::text
    AND payload->>'kind' = kind AND (payload->>'round')::integer = round AND payload->>'status' = status)
);
CREATE INDEX clarification_questions_request_idx ON public.clarification_questions(request_id);
CREATE UNIQUE INDEX clarification_questions_open_idx ON public.clarification_questions(episode_id) WHERE status = 'open';
CREATE TABLE public.clarification_answers (
  answer_id uuid PRIMARY KEY,
  request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
  episode_id uuid NOT NULL,
  question_id uuid NOT NULL UNIQUE,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (request_id, episode_id, question_id)
    REFERENCES public.clarification_questions(request_id, episode_id, question_id) ON DELETE CASCADE,
  CHECK (payload ?& ARRAY['answer_id','episode_id','question_id','kind','round','asked_fields','question','answer_raw']),
  CHECK (payload->>'answer_id' = answer_id::text AND payload->>'episode_id' = episode_id::text
    AND payload->>'question_id' = question_id::text)
);
CREATE INDEX clarification_answers_request_idx ON public.clarification_answers(request_id);

-- A failed workflow is terminal even for administrative/raw SQL writers.
CREATE FUNCTION public.guard_failed_workflow() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status = 'failed' AND (
    (to_jsonb(NEW) - 'updated_at' - 'graph_snapshot') IS DISTINCT FROM
    (to_jsonb(OLD) - 'updated_at' - 'graph_snapshot') OR
    (OLD.graph_snapshot IS NOT NULL AND NEW.graph_snapshot IS DISTINCT FROM OLD.graph_snapshot) OR
    (NEW.graph_snapshot IS NOT NULL AND NEW.graph_snapshot->'state'->>'status' IS DISTINCT FROM 'failed')) THEN
    RAISE EXCEPTION 'Failed workflow is immutable; create a new workflow and episode';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER guard_failed_workflow BEFORE UPDATE ON public.workflow_requests
  FOR EACH ROW EXECUTE FUNCTION public.guard_failed_workflow();

-- Lock order is always workflow, then episode. Budget changes happen with issuance.
CREATE FUNCTION public.issue_canonical_question() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE w public.workflow_requests; e public.destination_episodes;
BEGIN
  SELECT * INTO w FROM public.workflow_requests WHERE request_id=NEW.request_id FOR UPDATE;
  SELECT * INTO e FROM public.destination_episodes WHERE episode_id=NEW.episode_id FOR UPDATE;
  IF w.status IN ('failed','completed') OR w.active_episode_id IS DISTINCT FROM NEW.episode_id OR e.status <> 'active' THEN
    RAISE EXCEPTION 'Question requires active workflow episode';
  END IF;
  IF NEW.status <> 'open' OR e.final_resolve_status <> 'not_started' THEN
    RAISE EXCEPTION 'Question issuance is closed';
  END IF;
  IF NEW.payload->>'intent_snapshot' IS DISTINCT FROM e.selection_policy->>'selection_intent' THEN
    RAISE EXCEPTION 'Question intent differs from episode';
  END IF;
  IF NEW.counter_group = 'destination' THEN
    IF NEW.round <> e.destination_round + 1 OR NEW.round > e.max_destination_rounds THEN
      RAISE EXCEPTION 'Destination budget exhausted or stale round';
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
CREATE TRIGGER issue_canonical_question BEFORE INSERT ON public.clarification_questions
  FOR EACH ROW EXECUTE FUNCTION public.issue_canonical_question();

CREATE FUNCTION public.answer_canonical_question() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE w public.workflow_requests; q public.clarification_questions;
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
  IF q.kind = 'destination_choice' AND NOT EXISTS (
    SELECT 1 FROM jsonb_array_elements(q.payload->'options') o
    WHERE o->>'option_id' = NEW.payload->>'selected_option_id') THEN
    RAISE EXCEPTION 'Answer option was not issued';
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
CREATE TRIGGER answer_canonical_question BEFORE INSERT ON public.clarification_answers
  FOR EACH ROW EXECUTE FUNCTION public.answer_canonical_question();

CREATE FUNCTION public.guard_canonical_question() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (to_jsonb(NEW) - 'status' - 'payload') IS DISTINCT FROM (to_jsonb(OLD) - 'status' - 'payload')
     OR (NEW.payload - 'status') IS DISTINCT FROM (OLD.payload - 'status')
     OR (NEW.status <> OLD.status AND (OLD.status <> 'open' OR NEW.status NOT IN ('answered','cancelled'))) THEN
    RAISE EXCEPTION 'Issued question snapshot is immutable';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER guard_canonical_question BEFORE UPDATE ON public.clarification_questions
  FOR EACH ROW EXECUTE FUNCTION public.guard_canonical_question();

CREATE FUNCTION public.guard_canonical_answer() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Canonical answer is immutable';
END $$;
CREATE TRIGGER guard_canonical_answer BEFORE UPDATE ON public.clarification_answers
  FOR EACH ROW EXECUTE FUNCTION public.guard_canonical_answer();

CREATE FUNCTION public.guard_canonical_episode() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.workflow_requests WHERE request_id=OLD.request_id AND status='failed')
     AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'Failed workflow episode cannot change';
  END IF;
  IF OLD.status <> 'active' AND NEW IS DISTINCT FROM OLD THEN
    RAISE EXCEPTION 'Terminal episode is immutable';
  END IF;
  IF NEW.request_id <> OLD.request_id OR NEW.episode_id <> OLD.episode_id
     OR NEW.destination_round < OLD.destination_round THEN
    RAISE EXCEPTION 'Episode identity and consumed budget cannot change';
  END IF;
  IF OLD.final_resolve_status <> 'not_started' AND
     (NEW.final_resolve_id IS DISTINCT FROM OLD.final_resolve_id OR NEW.final_resolve_status = 'not_started') THEN
    RAISE EXCEPTION 'Final resolve cannot restart';
  END IF;
  IF OLD.final_resolve_status = 'completed' AND
     (NEW.final_resolve_status <> 'completed' OR NEW.final_resolve_result IS DISTINCT FROM OLD.final_resolve_result) THEN
    RAISE EXCEPTION 'Final resolve result is immutable';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER guard_canonical_episode BEFORE UPDATE ON public.destination_episodes
  FOR EACH ROW EXECUTE FUNCTION public.guard_canonical_episode();

-- Legacy rows and graph snapshots deliberately receive no invented question or
-- episode identity. Their existing counters remain available for explicit adoption.
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['destination_episodes','clarification_questions','clarification_answers'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
    EXECUTE format('GRANT SELECT ON public.%I TO authenticated', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO service_role', t);
    EXECUTE format('CREATE POLICY owner_read ON public.%I FOR SELECT TO authenticated USING (public.owns_request(request_id))', t);
  END LOOP;
END $$;

COMMIT;
