-- Copy this entire file into Supabase > SQL Editor > New query, then Run.
-- One SELECT only: no data, users, roles or policies are changed.
-- It returns one cell named edge_access_report. Copy that result for review.
-- Do not enter passwords or API keys here.
SELECT jsonb_pretty(jsonb_build_object(
  'bucket', (SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM (
    SELECT id AS bucket_id, public AS bucket_is_public
    FROM storage.buckets WHERE id = 'spx-snapshots'
  ) t),
  'recent_snapshots', (SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM (
    SELECT name, created_at, updated_at FROM storage.objects
    WHERE bucket_id = 'spx-snapshots'
    ORDER BY created_at DESC, name DESC LIMIT 15
  ) t),
  'storage_rls', (SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM (
    SELECT n.nspname AS schema_name, c.relname AS table_name,
           c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'storage' AND c.relname = 'objects'
  ) t),
  'storage_policies', (SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM (
    SELECT policyname, permissive, roles, cmd, qual, with_check
    FROM pg_policies WHERE schemaname = 'storage' AND tablename = 'objects'
    ORDER BY policyname
  ) t),
  'table_grants', (SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM (
    SELECT grantee, table_schema, table_name, privilege_type
    FROM information_schema.role_table_grants
    WHERE grantee IN ('anon', 'authenticated', 'PUBLIC')
      AND table_schema NOT IN ('pg_catalog', 'information_schema', 'auth')
    ORDER BY table_schema, table_name, grantee, privilege_type
  ) t),
  'application_policies', (SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM (
    SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
    FROM pg_policies
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'auth', 'storage')
    ORDER BY schemaname, tablename, policyname
  ) t),
  'definer_functions', (SELECT coalesce(jsonb_agg(t), '[]'::jsonb) FROM (
    SELECT n.nspname AS schema_name, p.proname AS function_name,
           pg_get_function_identity_arguments(p.oid) AS arguments,
           has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_can_execute,
           has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated_can_execute
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'auth')
    ORDER BY n.nspname, p.proname
  ) t)
)) AS edge_access_report;
