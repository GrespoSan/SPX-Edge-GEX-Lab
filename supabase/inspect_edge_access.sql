-- Preflight only. Run once in the existing project's Supabase SQL Editor.
-- This script changes no users, roles, policies, objects, tables or data.
-- It reads security metadata and snapshot filenames, never credential values.
-- Do not paste API keys or passwords into this script.
BEGIN TRANSACTION READ ONLY;

-- 1. Confirm the existing bucket and its privacy status.
SELECT id AS bucket_id, public AS bucket_is_public
FROM storage.buckets
WHERE id = 'spx-snapshots';

-- 2. Inspect only recent object names/metadata, not snapshot contents.
-- This establishes the actual naming/layout before choosing an automatic selector.
SELECT name, created_at, updated_at
FROM storage.objects
WHERE bucket_id = 'spx-snapshots'
ORDER BY created_at DESC, name DESC
LIMIT 15;

-- 3. Storage RLS state and all policies that a new reader might inherit.
SELECT n.nspname AS schema_name, c.relname AS table_name,
       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'storage' AND c.relname = 'objects';

SELECT policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = 'storage' AND tablename = 'objects'
ORDER BY policyname;

-- 4. Ordinary Auth users may inherit other application permissions.
-- These are grant/policy definitions only: no application table rows are read.
SELECT grantee, table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee IN ('anon', 'authenticated', 'PUBLIC')
  AND table_schema NOT IN ('pg_catalog', 'information_schema', 'auth')
ORDER BY table_schema, table_name, grantee, privilege_type;

SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies
WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'auth', 'storage')
ORDER BY schemaname, tablename, policyname;

-- 5. SECURITY DEFINER functions can bypass table RLS.
-- Inspect execute permissions, not their implementation or any credential store.
SELECT n.nspname AS schema_name, p.proname AS function_name,
       pg_get_function_identity_arguments(p.oid) AS arguments,
       has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_can_execute,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated_can_execute
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'auth')
ORDER BY n.nspname, p.proname;

ROLLBACK;
