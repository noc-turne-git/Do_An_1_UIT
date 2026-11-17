-- Replace retired destination-selection encodings in persisted canonical state.
-- This is intentionally forward-only: existing histories remain readable, but
-- every resumption uses the five-intent/three-authority contract.
BEGIN;

CREATE OR REPLACE FUNCTION public.normalize_destination_policy_v2(value jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE result jsonb := coalesce(value, '{}'::jsonb); intent text;
BEGIN
  intent := CASE result->>'selection_intent'
    WHEN 'ANY' THEN 'ANY_DESTINATION'
    WHEN 'UNKNOWN' THEN 'USER_UNKNOWN'
    WHEN 'EXPLICIT' THEN 'EXPLICIT'
    WHEN 'USER_UNKNOWN' THEN 'USER_UNKNOWN'
    WHEN 'ANY_DESTINATION' THEN 'ANY_DESTINATION'
    WHEN 'DELEGATE_SELECTION' THEN 'DELEGATE_SELECTION'
    ELSE 'UNSPECIFIED'
  END;
  result := jsonb_set(result, '{selection_intent}', to_jsonb(intent), true);
  result := jsonb_set(result, '{selection_authority}', CASE intent
    WHEN 'EXPLICIT' THEN '"USER"'::jsonb
    WHEN 'USER_UNKNOWN' THEN '"USER"'::jsonb
    WHEN 'ANY_DESTINATION' THEN '"USER"'::jsonb
    WHEN 'DELEGATE_SELECTION' THEN '"AGENT"'::jsonb
    ELSE 'null'::jsonb END, true);
  result := jsonb_set(result, '{destination_source}', CASE intent
    WHEN 'EXPLICIT' THEN '"user"'::jsonb
    ELSE 'null'::jsonb END, true);
  IF result->'selection_provenance'->>'source' IS DISTINCT FROM 'user' THEN
    result := result - 'selection_provenance';
  END IF;
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION public.normalize_destination_result_v2(value jsonb)
RETURNS jsonb LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE result jsonb := coalesce(value, '{}'::jsonb); method text;
BEGIN
  method := CASE result->>'selection_method'
    WHEN 'DELEGATED' THEN 'AGENT_DELEGATED'
    WHEN 'ANY_DEFAULT' THEN 'SYSTEM_DEFAULT'
    WHEN 'USER_EXPLICIT' THEN 'USER_EXPLICIT'
    WHEN 'USER_CHOICE' THEN 'USER_CHOICE'
    WHEN 'AGENT_DELEGATED' THEN 'AGENT_DELEGATED'
    WHEN 'SYSTEM_DEFAULT' THEN 'SYSTEM_DEFAULT'
    ELSE NULL END;
  result := jsonb_set(result, '{selection_method}',
    CASE WHEN method IS NULL THEN 'null'::jsonb ELSE to_jsonb(method) END, true);
  result := jsonb_set(result, '{destination_source}', CASE method
    WHEN 'USER_EXPLICIT' THEN '"user"'::jsonb
    WHEN 'USER_CHOICE' THEN '"user"'::jsonb
    WHEN 'AGENT_DELEGATED' THEN '"AGENT_DELEGATED"'::jsonb
    WHEN 'SYSTEM_DEFAULT' THEN '"SYSTEM_DEFAULT"'::jsonb
    ELSE 'null'::jsonb END, true);
  RETURN result - 'selection_provenance';
END $$;

-- Historical canonical snapshots are immutable at runtime.  This one-time
-- compatibility migration updates their encoding before current contracts read
-- them, then immediately restores all normal guards.
ALTER TABLE public.workflow_requests DISABLE TRIGGER guard_failed_workflow;
ALTER TABLE public.destination_episodes DISABLE TRIGGER guard_canonical_episode;
ALTER TABLE public.clarification_questions DISABLE TRIGGER guard_canonical_question;
ALTER TABLE public.clarification_answers DISABLE TRIGGER guard_canonical_answer;

UPDATE public.destination_episodes
SET selection_policy = public.normalize_destination_policy_v2(selection_policy);

UPDATE public.clarification_questions
SET payload = jsonb_set(payload, '{intent_snapshot}', to_jsonb(CASE payload->>'intent_snapshot'
  WHEN 'ANY' THEN 'ANY_DESTINATION'
  WHEN 'UNKNOWN' THEN 'USER_UNKNOWN'
  ELSE coalesce(payload->>'intent_snapshot', 'UNSPECIFIED') END), true)
WHERE payload ? 'intent_snapshot';

UPDATE public.clarification_answers
SET payload = jsonb_set(payload, '{destination_update}',
  public.normalize_destination_policy_v2(payload->'destination_update'), true)
WHERE jsonb_typeof(payload->'destination_update') = 'object';

UPDATE public.workflow_artifacts
SET payload = jsonb_set(payload, '{destination}',
  public.normalize_destination_policy_v2(payload->'destination'), true)
WHERE artifact_type = 'trip_request' AND payload ? 'destination';

UPDATE public.workflow_artifacts
SET payload = public.normalize_destination_result_v2(payload)
WHERE artifact_type = 'destination_result';

UPDATE public.workflow_requests
SET graph_snapshot = jsonb_set(
  jsonb_set(
    jsonb_set(graph_snapshot, '{outputs,request_parser,destination}',
      CASE WHEN jsonb_typeof(graph_snapshot #> '{outputs,request_parser,destination}') = 'object'
        THEN public.normalize_destination_policy_v2(graph_snapshot #> '{outputs,request_parser,destination}')
        ELSE graph_snapshot #> '{outputs,request_parser,destination}' END, false),
    '{outputs,destination_agent}',
      CASE WHEN jsonb_typeof(graph_snapshot #> '{outputs,destination_agent}') = 'object'
        THEN public.normalize_destination_result_v2(graph_snapshot #> '{outputs,destination_agent}')
        ELSE graph_snapshot #> '{outputs,destination_agent}' END, false),
  '{state,destination_episode}',
      CASE WHEN jsonb_typeof(graph_snapshot #> '{state,destination_episode}') = 'object'
        THEN public.normalize_destination_policy_v2(graph_snapshot #> '{state,destination_episode}')
        ELSE graph_snapshot #> '{state,destination_episode}' END, false)
WHERE graph_snapshot IS NOT NULL;

UPDATE public.workflow_requests
SET graph_snapshot = jsonb_set(graph_snapshot, '{pending_questions}', coalesce((
  SELECT jsonb_agg(jsonb_set(question, '{intent_snapshot}', to_jsonb(CASE question->>'intent_snapshot'
    WHEN 'ANY' THEN 'ANY_DESTINATION' WHEN 'UNKNOWN' THEN 'USER_UNKNOWN'
    ELSE coalesce(question->>'intent_snapshot', 'UNSPECIFIED') END), true))
  FROM jsonb_array_elements(graph_snapshot->'pending_questions') AS question), '[]'::jsonb), true)
WHERE graph_snapshot IS NOT NULL AND jsonb_typeof(graph_snapshot->'pending_questions') = 'array';

UPDATE public.workflow_requests
SET graph_snapshot = jsonb_set(graph_snapshot, '{answers_history}', coalesce((
  SELECT jsonb_agg(CASE WHEN answer ? 'destination_update' AND answer->'destination_update' <> 'null'::jsonb
    THEN jsonb_set(answer, '{destination_update}', public.normalize_destination_policy_v2(answer->'destination_update'), true)
    ELSE answer END)
  FROM jsonb_array_elements(graph_snapshot->'answers_history') AS answer), '[]'::jsonb), true)
WHERE graph_snapshot IS NOT NULL AND jsonb_typeof(graph_snapshot->'answers_history') = 'array';

ALTER TABLE public.clarification_answers ENABLE TRIGGER guard_canonical_answer;
ALTER TABLE public.clarification_questions ENABLE TRIGGER guard_canonical_question;
ALTER TABLE public.destination_episodes ENABLE TRIGGER guard_canonical_episode;
ALTER TABLE public.workflow_requests ENABLE TRIGGER guard_failed_workflow;

DROP FUNCTION public.normalize_destination_result_v2(jsonb);
DROP FUNCTION public.normalize_destination_policy_v2(jsonb);
COMMIT;
