-- Student identity mapping groundwork for NUST AI Assistant.
-- This migration does not create student logins or assign identities automatically.
-- A verified administrator must link an authenticated Supabase user to an existing
-- student record through a separately reviewed onboarding workflow.
CREATE TABLE IF NOT EXISTS public.student_auth_links (
    auth_user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    student_id bigint NOT NULL UNIQUE REFERENCES public.students(id) ON DELETE CASCADE,
    linked_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    linked_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.student_auth_links ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.student_auth_links FROM anon, authenticated;
GRANT ALL ON TABLE public.student_auth_links TO service_role;

COMMENT ON TABLE public.student_auth_links IS
'Server-managed mapping between a verified Supabase Auth identity and one student record. No self-service linking.';


-- Opaque server-side browser sessions. The raw session identifier is held only
-- in the HttpOnly Flask cookie; this table stores its SHA-256 digest.
CREATE TABLE IF NOT EXISTS public.student_web_sessions (
    session_key_hash text PRIMARY KEY CHECK (length(session_key_hash) = 64),
    auth_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    student_id bigint NOT NULL REFERENCES public.students(id) ON DELETE CASCADE,
    access_token text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS student_web_sessions_auth_user_id_idx
    ON public.student_web_sessions(auth_user_id);
CREATE INDEX IF NOT EXISTS student_web_sessions_expires_at_idx
    ON public.student_web_sessions(expires_at);

ALTER TABLE public.student_web_sessions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.student_web_sessions FROM anon, authenticated;
GRANT ALL ON TABLE public.student_web_sessions TO service_role;

COMMENT ON TABLE public.student_web_sessions IS
'Server-only student browser sessions. Session IDs are stored as hashes; access is mediated by the Flask server.';
