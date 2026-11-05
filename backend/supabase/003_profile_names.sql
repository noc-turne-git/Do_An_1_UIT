-- Existing databases: preserve saved names before removing identity from preferences.
BEGIN;

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS first_name text;
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS last_name text;

UPDATE public.profiles
SET first_name = COALESCE(first_name, CASE WHEN jsonb_typeof(preferences->'firstName') = 'string' THEN preferences->>'firstName' END),
    last_name = COALESCE(last_name, CASE WHEN jsonb_typeof(preferences->'lastName') = 'string' THEN preferences->>'lastName' END),
    preferences = preferences - 'firstName' - 'lastName' - 'email'
WHERE preferences ?| ARRAY['firstName', 'lastName', 'email'];

CREATE OR REPLACE FUNCTION public.handle_new_user() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
 INSERT INTO public.profiles(id, first_name, last_name, full_name, avatar_url)
 VALUES (NEW.id, NEW.raw_user_meta_data->>'first_name', NEW.raw_user_meta_data->>'last_name',
 NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'avatar_url');
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC;

NOTIFY pgrst, 'reload schema';
COMMIT;
