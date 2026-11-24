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
