-- DRAFT: one-time installation after creating a dedicated, confirmed Auth user.
-- Replace ONLY the UUID below with that user's ID. Never paste a password here.
-- Adds exactly one SELECT policy. Does not alter existing tables, rows, jobs,
-- bucket privacy, roles, or policies used by the original application.
-- Guards abort and roll back if the observed permission baseline has changed.
BEGIN;
DO $edge_setup$
DECLARE
  edge_uid uuid := 'REPLACE_WITH_EDGE_USER_UUID';
  raw_pattern constant text := '^[0-9]{4}-W[0-9]{2}/snapshots/SPX_CBOE_[0-9]{8}_[0-9]{6}\.json(\.gz)?$';
BEGIN
  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id=edge_uid AND role='authenticated'
                 AND email_confirmed_at IS NOT NULL AND NOT coalesce(is_anonymous,false)) THEN
    RAISE EXCEPTION 'Create and confirm the dedicated Edge Auth user first.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM storage.buckets WHERE id='spx-snapshots' AND NOT public) THEN
    RAISE EXCEPTION 'Expected private bucket not found. No changes applied.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                 WHERE n.nspname='storage' AND c.relname='objects' AND c.relrowsecurity) THEN
    RAISE EXCEPTION 'Storage RLS is not enabled. No changes applied.';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated' AND (rolsuper OR rolbypassrls)) THEN
    RAISE EXCEPTION 'Unexpected privileged authenticated role. No changes applied.';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='storage' AND tablename='objects') THEN
    RAISE EXCEPTION 'Storage policies already exist or installation was already applied. Review before proceeding.';
  END IF;
  -- An Auth user must not inherit unrelated write permissions through RLS policies.
  IF EXISTS (SELECT 1 FROM pg_policies
              WHERE schemaname NOT IN ('pg_catalog','information_schema','auth')
                AND cmd IN ('ALL','INSERT','UPDATE','DELETE')
                AND roles && ARRAY['public','authenticated']::name[]) THEN
    RAISE EXCEPTION 'Other potentially writable policies require review. No changes applied.';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
              WHERE c.relkind IN ('r','p')
                AND n.nspname NOT IN ('pg_catalog','information_schema','auth')
                AND (has_table_privilege('authenticated',c.oid,'TRUNCATE') OR
                     (NOT c.relrowsecurity AND has_table_privilege('authenticated',c.oid,'INSERT,UPDATE,DELETE')))) THEN
    RAISE EXCEPTION 'Other inherited write privileges require review. No changes applied.';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
              WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema','auth')
                AND has_function_privilege('authenticated',p.oid,'EXECUTE')) THEN
    RAISE EXCEPTION 'Executable SECURITY DEFINER functions require review. No changes applied.';
  END IF;
  EXECUTE format('CREATE POLICY edge_spx_raw_reader_v1 ON storage.objects FOR SELECT TO authenticated USING (bucket_id = %L AND auth.uid() = %L::uuid AND name ~ %L)',
                 'spx-snapshots', edge_uid, raw_pattern);
  PERFORM set_config('edge.reader_uid',edge_uid::text,true);
END
$edge_setup$;

-- Verify reads under the exact reader identity; no trial writes in production.
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claim.sub','',true),
       set_config('request.jwt.claims',json_build_object('sub',current_setting('edge.reader_uid'),'role','authenticated')::text,true);
DO $edge_verify$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM storage.objects WHERE bucket_id='spx-snapshots') THEN
    RAISE EXCEPTION 'Reader cannot see any SPX snapshots; rolling back.';
  END IF;
  IF EXISTS (SELECT 1 FROM storage.objects WHERE bucket_id<>'spx-snapshots'
             OR name !~ '^[0-9]{4}-W[0-9]{2}/snapshots/SPX_CBOE_[0-9]{8}_[0-9]{6}\.json(\.gz)?$') THEN
    RAISE EXCEPTION 'Reader scope too broad; rolling back.';
  END IF;
END
$edge_verify$;
-- Another ordinary Auth user must gain no access from the new policy.
SELECT set_config('request.jwt.claims',json_build_object('sub',
       CASE WHEN current_setting('edge.reader_uid')='00000000-0000-4000-8000-000000000001'
            THEN '00000000-0000-4000-8000-000000000002'
            ELSE '00000000-0000-4000-8000-000000000001' END,'role','authenticated')::text,true);
DO $edge_other$
BEGIN
  IF EXISTS (SELECT 1 FROM storage.objects) THEN
    RAISE EXCEPTION 'Unexpected access for another user; rolling back.';
  END IF;
END
$edge_other$;
RESET ROLE;
SET LOCAL ROLE anon;
SELECT set_config('request.jwt.claims','{"role":"anon"}',true);
DO $edge_anon$
BEGIN
  IF EXISTS (SELECT 1 FROM storage.objects) THEN
    RAISE EXCEPTION 'Unexpected anonymous access; rolling back.';
  END IF;
END
$edge_anon$;
RESET ROLE;
COMMIT;
SELECT policyname, roles, cmd, qual
FROM pg_policies WHERE schemaname='storage' AND tablename='objects' AND policyname='edge_spx_raw_reader_v1';
