-- Fresh Supabase database only. Not an upgrade of Alembic revision 0001.
-- Execute as database owner in Supabase SQL Editor; never with a client key.
BEGIN;
SET LOCAL search_path = public;

CREATE TYPE public.price_status AS ENUM ('ESTIMATED','UNKNOWN','VERIFIED_FREE');
CREATE TYPE public.request_type AS ENUM ('EXPLICIT','IMPLICIT','AMBIGUOUS','INSUFFICIENT');
CREATE TYPE public.workflow_status AS ENUM ('parsing','clarifying','planning','validating','awaiting_relaxation','completed','failed');
CREATE TYPE public.workflow_step AS ENUM ('request_parser','destination_agent','constraint_planner','place_agent','budget_module','planning_input_builder','planning_engine','validator','explainer');
CREATE TYPE public.artifact_type AS ENUM ('trip_request','destination_result','time_constraints','candidates','costed_candidates','planning_input','itinerary','validation_result');
CREATE TYPE public.message_role AS ENUM ('user','assistant');
CREATE TYPE public.pending_status AS ENUM ('open','resolved','unknown');
CREATE TYPE public.candidate_source AS ENUM ('user_requested','agent_suggested');
CREATE TYPE public.attempt_result AS ENUM ('accepted','hard_violation','infeasible','error');
CREATE TYPE public.workflow_error_code AS ENUM ('llm_output_invalid','external_api_error','planning_input_inconsistent','solver_error','validator_internal_error');
CREATE TYPE public.itinerary_status AS ENUM ('feasible','infeasible','partial','error');
CREATE TYPE public.validation_action AS ENUM ('accept','replan','ask_user','fail');
CREATE TYPE public.issue_kind AS ENUM ('violation','warning');
CREATE TYPE public.issue_severity AS ENUM ('hard','soft','info');

CREATE FUNCTION public.touch_updated_at() RETURNS trigger LANGUAGE plpgsql
SET search_path = '' AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END $$;

-- Shared price validation, including JSONB prices. SQL NULL means unknown.
CREATE FUNCTION public.valid_price(lo bigint, hi bigint, status public.price_status)
RETURNS boolean LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
 SELECT CASE
 WHEN status IS NULL THEN false
 WHEN status = 'UNKNOWN' THEN lo IS NULL AND hi IS NULL
 WHEN lo IS NULL OR hi IS NULL THEN false
 WHEN status = 'VERIFIED_FREE' THEN lo = 0 AND hi = 0
 ELSE lo > 0 AND hi >= lo END
$$;

-- User preferences; field provenance is recorded in trip_request payloads.
CREATE TABLE public.profiles (
 id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
 first_name text, last_name text, full_name text, avatar_url text,
 preferences jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(preferences) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER profiles_updated BEFORE UPDATE ON public.profiles
FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
CREATE FUNCTION public.handle_new_user() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = '' AS $$
BEGIN
 INSERT INTO public.profiles(id, first_name, last_name, full_name, avatar_url)
 VALUES (NEW.id, NEW.raw_user_meta_data->>'first_name', NEW.raw_user_meta_data->>'last_name',
 NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'avatar_url');
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC;
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
-- Backfill users created before this script.
INSERT INTO public.profiles(id) SELECT id FROM auth.users ON CONFLICT (id) DO NOTHING;

-- Conversation container and ownership root.
CREATE TABLE public.trips (
 trip_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
 title text, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX trips_user_idx ON public.trips(user_id);
-- Conversation messages are trip-scoped, including messages before a request exists.
CREATE TABLE public.messages (
 message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 trip_id uuid NOT NULL REFERENCES public.trips(trip_id) ON DELETE CASCADE,
 role public.message_role NOT NULL, content text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX messages_trip_idx ON public.messages(trip_id, created_at);

-- UI projection, not a LangGraph checkpoint.
CREATE TABLE public.workflow_requests (
 graph_snapshot jsonb,
 request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 trip_id uuid NOT NULL REFERENCES public.trips(trip_id) ON DELETE CASCADE,
 schema_version text NOT NULL CHECK (schema_version ~ '^[0-9]+\.[0-9]+$'),
 status public.workflow_status NOT NULL DEFAULT 'parsing',
 current_step public.workflow_step NOT NULL DEFAULT 'request_parser',
 clarification_round int NOT NULL DEFAULT 0,
 max_clarification_rounds int NOT NULL DEFAULT 3,
 destination_round int NOT NULL DEFAULT 0 CHECK (destination_round >= 0),
 retry_count int NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (clarification_round >= 0 AND max_clarification_rounds >= clarification_round),
 UNIQUE (request_id, trip_id)
);
CREATE INDEX workflow_requests_trip_idx ON public.workflow_requests(trip_id);
CREATE TRIGGER requests_updated BEFORE UPDATE ON public.workflow_requests
FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

-- Versioned payloads; only latest-marker retirement is mutable.
CREATE TABLE public.workflow_artifacts (
 artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 artifact_type public.artifact_type NOT NULL,
 parent_artifact_id uuid,
 is_latest boolean NOT NULL DEFAULT true,
 schema_version text NOT NULL CHECK (schema_version ~ '^[0-9]+\.[0-9]+$'),
 payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (request_id, artifact_type, artifact_id),
 FOREIGN KEY (request_id, artifact_type, parent_artifact_id)
 REFERENCES public.workflow_artifacts(request_id, artifact_type, artifact_id),
 CHECK (parent_artifact_id IS DISTINCT FROM artifact_id)
);
CREATE INDEX artifacts_lookup_idx ON public.workflow_artifacts(request_id, artifact_type, is_latest);
CREATE UNIQUE INDEX artifacts_latest_idx ON public.workflow_artifacts(request_id, artifact_type) WHERE is_latest;

-- Clarification history, one row per round.
CREATE TABLE public.clarification_rounds (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 round int NOT NULL CHECK (round > 0),
 asked_fields jsonb NOT NULL CHECK (jsonb_typeof(asked_fields) = 'array'),
 question text NOT NULL, answer_raw text,
 resolved_fields jsonb, declared_unknown_fields jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (request_id, round)
);
-- Outstanding questions; unknown is a deliberate user answer.
CREATE TABLE public.pending_items (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 field_path text NOT NULL, question text NOT NULL,
 status public.pending_status NOT NULL DEFAULT 'open'
);
-- Operational failures, distinct from independent validation findings.
CREATE TABLE public.workflow_errors (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 step public.workflow_step NOT NULL, code public.workflow_error_code NOT NULL,
 message text NOT NULL, retryable boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);

-- Shared place facts. Request scores, clusters and normalized prices live below.
CREATE TABLE public.places (
 place_id text PRIMARY KEY, google_place_id text UNIQUE,
 name text NOT NULL, category text, types text[], google_maps_url text,
 rating numeric(2,1) CHECK (rating BETWEEN 0 AND 5),
 user_rating_count int CHECK (user_rating_count >= 0), business_status text,
 latitude double precision CHECK (latitude BETWEEN -90 AND 90),
 longitude double precision CHECK (longitude BETWEEN -180 AND 180),
 address text, timezone text, reservation_required boolean,
 accessibility_notes jsonb, source text, opening_hours_verified boolean,
 last_verified_at timestamptz,
 opening_hours jsonb CHECK (jsonb_typeof(opening_hours) = 'object'),
 photos jsonb CHECK (jsonb_typeof(photos) = 'array'),
 visit_duration jsonb CHECK (jsonb_typeof(visit_duration) = 'object'),
 price jsonb CHECK (jsonb_typeof(price) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (price IS NULL OR (
   (price->>'min' IS NULL OR price->>'min' ~ '^[0-9]+$') AND
   (price->>'max' IS NULL OR price->>'max' ~ '^[0-9]+$') AND
   price->>'currency' IS NOT DISTINCT FROM 'VND' AND
   public.valid_price((price->>'min')::bigint, (price->>'max')::bigint,
                      (price->>'price_status')::public.price_status)))
);
CREATE TRIGGER places_updated BEFORE UPDATE ON public.places
FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
-- Shared directed travel cache; departure bucket captures time-dependent estimates.
CREATE TABLE public.travel_time_cache (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 from_place_id text NOT NULL REFERENCES public.places(place_id) ON DELETE CASCADE,
 to_place_id text NOT NULL REFERENCES public.places(place_id) ON DELETE CASCADE,
 transport_mode text NOT NULL, departure_bucket timestamptz NOT NULL,
 duration_minutes int CHECK (duration_minutes >= 0),
 distance_meters int CHECK (distance_meters >= 0), source text,
 schema_version text NOT NULL CHECK (schema_version ~ '^[0-9]+\.[0-9]+$'),
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz,
 UNIQUE (from_place_id, to_place_id, transport_mode, departure_bucket)
);
CREATE INDEX travel_cache_to_idx ON public.travel_time_cache(to_place_id);
-- Per-request selection and price snapshot.
CREATE TABLE public.request_place_candidates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 place_id text NOT NULL REFERENCES public.places(place_id),
 schema_version text NOT NULL CHECK (schema_version ~ '^[0-9]+\.[0-9]+$'),
 score_places int CHECK (score_places BETWEEN 0 AND 100),
 matched_interests jsonb CHECK (jsonb_typeof(matched_interests) = 'array'), reason text,
 cluster_id int, source_type public.candidate_source NOT NULL, original_name text,
 candidate_status text, -- Vocabulary unspecified: intentionally not an invented enum.
 price_min bigint, price_max bigint, price_status public.price_status NOT NULL DEFAULT 'UNKNOWN',
 price_confidence_score numeric(3,2) CHECK (price_confidence_score BETWEEN 0 AND 1),
 admission_price_raw text,
 UNIQUE (request_id, place_id),
 CHECK (original_name IS NULL OR source_type = 'user_requested'),
 CHECK (public.valid_price(price_min, price_max, price_status))
);
CREATE INDEX candidates_place_idx ON public.request_place_candidates(place_id);

-- Solver output snapshot; aggregate costs also carry explicit price provenance.
CREATE TABLE public.itineraries (
 itinerary_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 parent_artifact_id uuid,
 attempt_no int NOT NULL CHECK (attempt_no > 0),
 schema_version text NOT NULL CHECK (schema_version ~ '^[0-9]+\.[0-9]+$'),
 status public.itinerary_status NOT NULL, currency text NOT NULL DEFAULT 'VND' CHECK (currency = 'VND'),
 total_cost_min bigint, total_cost_max bigint,
 price_status public.price_status NOT NULL DEFAULT 'UNKNOWN',
 total_travel_minutes int CHECK (total_travel_minutes >= 0),
 total_scheduled_places int CHECK (total_scheduled_places >= 0),
 objective_value numeric, solver_status text, optimality_proven boolean,
 unsatisfied_constraints jsonb CHECK (jsonb_typeof(unsatisfied_constraints) = 'array'),
 summary_message text, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (request_id, itinerary_id), UNIQUE (request_id, attempt_no),
 CHECK (public.valid_price(total_cost_min, total_cost_max, price_status))
);
-- Daily totals with explicit request ownership.
CREATE TABLE public.itinerary_days (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 itinerary_id uuid NOT NULL, day int NOT NULL CHECK (day > 0), date date NOT NULL,
 day_cost_min bigint, day_cost_max bigint,
 price_status public.price_status NOT NULL DEFAULT 'UNKNOWN',
 UNIQUE (itinerary_id, day), UNIQUE (request_id, id),
 FOREIGN KEY (request_id, itinerary_id) REFERENCES public.itineraries(request_id, itinerary_id) ON DELETE CASCADE,
 CHECK (public.valid_price(day_cost_min, day_cost_max, price_status))
);
-- Ordered visits; same-day TIME values, overnight visits must be split.
CREATE TABLE public.itinerary_activities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 itinerary_day_id uuid NOT NULL, seq int NOT NULL CHECK (seq > 0),
 place_id text NOT NULL REFERENCES public.places(place_id),
 arrival_time time NOT NULL, start_time time NOT NULL, departure_time time NOT NULL,
 travel_minutes_from_previous int CHECK (travel_minutes_from_previous >= 0),
 cost_min bigint, cost_max bigint, price_status public.price_status NOT NULL DEFAULT 'UNKNOWN',
 UNIQUE (itinerary_day_id, seq),
 FOREIGN KEY (request_id, itinerary_day_id) REFERENCES public.itinerary_days(request_id, id) ON DELETE CASCADE,
 CHECK (arrival_time <= start_time AND start_time <= departure_time),
 CHECK (public.valid_price(cost_min, cost_max, price_status))
);
CREATE INDEX activities_place_idx ON public.itinerary_activities(place_id);
-- Explanations for excluded places.
CREATE TABLE public.itinerary_dropped_places (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 itinerary_id uuid NOT NULL, place_id text NOT NULL REFERENCES public.places(place_id), reason text NOT NULL,
 FOREIGN KEY (request_id, itinerary_id) REFERENCES public.itineraries(request_id, itinerary_id) ON DELETE CASCADE
);
CREATE INDEX dropped_place_idx ON public.itinerary_dropped_places(place_id);
-- Proposed changes; user choice is mutable workflow metadata.
CREATE TABLE public.relaxation_suggestions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 itinerary_id uuid NOT NULL, constraint_type text NOT NULL, description text NOT NULL,
 payload jsonb NOT NULL, chosen_by_user boolean,
 FOREIGN KEY (request_id, itinerary_id) REFERENCES public.itineraries(request_id, itinerary_id) ON DELETE CASCADE
);
-- Independent validator snapshot, tied to the same request and trip.
CREATE TABLE public.validation_results (
 validation_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 itinerary_id uuid NOT NULL, trip_id uuid NOT NULL,
 parent_artifact_id uuid,
 schema_version text NOT NULL CHECK (schema_version ~ '^[0-9]+\.[0-9]+$'),
 is_valid boolean NOT NULL, suggested_action public.validation_action NOT NULL,
 checked_rules jsonb NOT NULL CHECK (jsonb_typeof(checked_rules) = 'array'),
 recomputed jsonb NOT NULL CHECK (jsonb_typeof(recomputed) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (request_id, itinerary_id, validation_result_id), UNIQUE (request_id, validation_result_id),
 FOREIGN KEY (request_id, itinerary_id) REFERENCES public.itineraries(request_id, itinerary_id) ON DELETE CASCADE,
 FOREIGN KEY (request_id, trip_id) REFERENCES public.workflow_requests(request_id, trip_id) ON DELETE CASCADE,
 CHECK (suggested_action <> 'accept' OR is_valid),
 CHECK (NOT is_valid OR checked_rules @> '["input_integrity","price_integrity","travel_time","overlap","opening_hours","visit_duration","day_start_window","day_end_window","meal_window","activity_count","rest_time","must_visit","budget","summary_consistency"]'::jsonb)
);
CREATE INDEX validation_trip_idx ON public.validation_results(trip_id);
-- Individual validator findings; actual/expected use text for numeric or clock values.
CREATE TABLE public.validation_issues (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 validation_result_id uuid NOT NULL, kind public.issue_kind NOT NULL, severity public.issue_severity NOT NULL,
 rule text NOT NULL, type text NOT NULL, day int CHECK (day > 0),
 place_id text REFERENCES public.places(place_id), actual text, expected_or_limit text, message text NOT NULL,
 FOREIGN KEY (request_id, validation_result_id) REFERENCES public.validation_results(request_id, validation_result_id) ON DELETE CASCADE,
 CHECK ((kind = 'violation' AND severity = 'hard') OR (kind = 'warning' AND severity IN ('soft','info')))
);
CREATE INDEX issues_result_kind_idx ON public.validation_issues(validation_result_id, kind);
CREATE INDEX issues_place_idx ON public.validation_issues(place_id);
-- Deferred so a backend transaction can insert the result and its findings together.
CREATE FUNCTION public.check_validation_consistency() RETURNS trigger LANGUAGE plpgsql
SET search_path = '' AS $$
DECLARE target uuid;
BEGIN
 IF TG_TABLE_NAME = 'validation_results' THEN target := NEW.validation_result_id;
 ELSE target := NEW.validation_result_id; END IF;
 IF EXISTS (SELECT 1 FROM public.validation_results r
   JOIN public.validation_issues i USING (request_id, validation_result_id)
   WHERE r.validation_result_id = target AND r.is_valid AND i.kind = 'violation') THEN
   RAISE EXCEPTION 'A valid result cannot contain hard violations';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER valid_result_consistency AFTER INSERT ON public.validation_results
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_validation_consistency();
CREATE CONSTRAINT TRIGGER valid_issue_consistency AFTER INSERT ON public.validation_issues
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.check_validation_consistency();
-- Attempt ledger is created after both output tables to avoid circular dependencies.
CREATE TABLE public.solver_attempts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 request_id uuid NOT NULL REFERENCES public.workflow_requests(request_id) ON DELETE CASCADE,
 attempt_no int NOT NULL CHECK (attempt_no > 0), step public.workflow_step NOT NULL,
 random_seed int, time_limit_seconds int CHECK (time_limit_seconds > 0),
 result public.attempt_result NOT NULL,
 violations jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(violations) = 'array'),
 itinerary_id uuid, validation_result_id uuid,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (request_id, attempt_no),
 FOREIGN KEY (request_id, itinerary_id) REFERENCES public.itineraries(request_id, itinerary_id),
 FOREIGN KEY (request_id, itinerary_id, validation_result_id)
 REFERENCES public.validation_results(request_id, itinerary_id, validation_result_id),
 CHECK (validation_result_id IS NULL OR itinerary_id IS NOT NULL)
);

-- Parent links for normalized outputs must point to the matching artifact type.
ALTER TABLE public.itineraries ADD COLUMN parent_artifact_type public.artifact_type
 GENERATED ALWAYS AS ('itinerary'::public.artifact_type) STORED;
ALTER TABLE public.itineraries ADD FOREIGN KEY (request_id, parent_artifact_type, parent_artifact_id)
 REFERENCES public.workflow_artifacts(request_id, artifact_type, artifact_id);
ALTER TABLE public.validation_results ADD COLUMN parent_artifact_type public.artifact_type
 GENERATED ALWAYS AS ('validation_result'::public.artifact_type) STORED;
ALTER TABLE public.validation_results ADD FOREIGN KEY (request_id, parent_artifact_type, parent_artifact_id)
 REFERENCES public.workflow_artifacts(request_id, artifact_type, artifact_id);

-- Disallow direct result mutation, including by service_role. Cascaded owner deletion
-- is allowed only after the request has disappeared in this transaction.
CREATE FUNCTION public.guard_result_mutation() RETURNS trigger LANGUAGE plpgsql
SET search_path = '' AS $$
BEGIN
 IF TG_OP = 'DELETE' AND NOT EXISTS (
   SELECT 1 FROM public.workflow_requests WHERE request_id = OLD.request_id
 ) THEN RETURN OLD; END IF;
 IF TG_TABLE_NAME = 'workflow_artifacts' AND TG_OP = 'UPDATE' THEN
   IF OLD.is_latest AND NOT NEW.is_latest AND
      (to_jsonb(NEW) - 'is_latest') = (to_jsonb(OLD) - 'is_latest') THEN RETURN NEW; END IF;
 END IF;
 RAISE EXCEPTION 'Saved results are immutable; insert a new version with parent_artifact_id';
END $$;

-- Atomic artifact insertion: serialize writers per request before retiring latest.
CREATE FUNCTION public.prepare_artifact_insert() RETURNS trigger LANGUAGE plpgsql
SET search_path = '' AS $$
DECLARE previous_id uuid;
BEGIN
 PERFORM 1 FROM public.workflow_requests WHERE request_id = NEW.request_id FOR UPDATE;
 SELECT artifact_id INTO previous_id FROM public.workflow_artifacts
 WHERE request_id = NEW.request_id AND artifact_type = NEW.artifact_type AND is_latest;
 IF NEW.is_latest AND previous_id IS NOT NULL THEN
   IF NEW.parent_artifact_id IS DISTINCT FROM previous_id THEN
     RAISE EXCEPTION 'New latest artifact must reference the current latest parent';
   END IF;
   UPDATE public.workflow_artifacts SET is_latest = false WHERE artifact_id = previous_id;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER artifact_prepare BEFORE INSERT ON public.workflow_artifacts
FOR EACH ROW EXECUTE FUNCTION public.prepare_artifact_insert();

-- RLS helpers are security-invoker: ownership remains subject to parent-table RLS.
CREATE FUNCTION public.owns_trip(target uuid) RETURNS boolean LANGUAGE sql STABLE
SET search_path = '' AS $$
 SELECT EXISTS (SELECT 1 FROM public.trips WHERE trip_id = target AND user_id = (SELECT auth.uid()))
$$;
CREATE FUNCTION public.owns_request(target uuid) RETURNS boolean LANGUAGE sql STABLE
SET search_path = '' AS $$
 SELECT EXISTS (SELECT 1 FROM public.workflow_requests WHERE request_id = target AND public.owns_trip(trip_id))
$$;

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trips ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workflow_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.profiles, public.trips, public.messages, public.workflow_requests FROM anon, authenticated;
GRANT SELECT, UPDATE ON public.profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.trips, public.messages TO authenticated;
GRANT SELECT ON public.workflow_requests TO authenticated;
CREATE POLICY profiles_read ON public.profiles FOR SELECT TO authenticated USING (id = (SELECT auth.uid()));
CREATE POLICY profiles_update ON public.profiles FOR UPDATE TO authenticated USING (id = (SELECT auth.uid())) WITH CHECK (id = (SELECT auth.uid()));
CREATE POLICY trips_owner ON public.trips FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE POLICY messages_owner ON public.messages FOR ALL TO authenticated USING (public.owns_trip(trip_id)) WITH CHECK (public.owns_trip(trip_id));
CREATE POLICY requests_read ON public.workflow_requests FOR SELECT TO authenticated USING (public.owns_trip(trip_id));

-- Every request-scoped table gets its own request index and owner SELECT policy.
-- Only service_role writes workflow state and outputs; UI submits commands via backend.
DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['workflow_artifacts','clarification_rounds','pending_items','workflow_errors',
 'request_place_candidates','itineraries','itinerary_days','itinerary_activities',
 'itinerary_dropped_places','relaxation_suggestions','validation_results','validation_issues','solver_attempts'] LOOP
   EXECUTE format('CREATE INDEX %I ON public.%I(request_id)', t || '_request_idx', t);
   EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
   EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
   EXECUTE format('GRANT SELECT ON public.%I TO authenticated', t);
   EXECUTE format('CREATE POLICY owner_read ON public.%I FOR SELECT TO authenticated USING (public.owns_request(request_id))', t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['workflow_artifacts','itineraries','itinerary_days','itinerary_activities',
 'itinerary_dropped_places','validation_results','validation_issues'] LOOP
   EXECUTE format('CREATE TRIGGER immutable_result BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.guard_result_mutation()', t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['places','travel_time_cache'] LOOP
   EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
   EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
   EXECUTE format('GRANT SELECT ON public.%I TO anon, authenticated', t);
   EXECUTE format('CREATE POLICY shared_read ON public.%I FOR SELECT TO anon, authenticated USING (true)', t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['profiles','trips','messages','workflow_requests','workflow_artifacts',
 'clarification_rounds','pending_items','workflow_errors','places','travel_time_cache',
 'request_place_candidates','itineraries','itinerary_days','itinerary_activities',
 'itinerary_dropped_places','relaxation_suggestions','validation_results','validation_issues','solver_attempts'] LOOP
   EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO service_role', t);
 END LOOP;
END $$;

COMMIT;
