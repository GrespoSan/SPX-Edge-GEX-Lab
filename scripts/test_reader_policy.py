"""Exercise the Edge policy in a disposable PostgreSQL cluster, never production.

Requires local PostgreSQL binaries. Uses only a private temporary Unix socket,
synthetic rows and roles. Run: python scripts/test_reader_policy.py --pg-bin-dir DIR
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

UID='11111111-2222-4333-8444-555555555555'
OTHER='aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
RAW='2026-W43/snapshots/SPX_CBOE_20261020_140000.json.gz'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin-dir',type=Path,required=True)
    parser.add_argument('--pg-share-dir',type=Path)
    args=parser.parse_args()
    policy=(Path(__file__).resolve().parents[1]/'supabase/enable_edge_reader.sql').read_text().replace('REPLACE_WITH_EDGE_USER_UUID',UID)
    with tempfile.TemporaryDirectory(prefix='edge-policy-') as temporary:
        root=Path(temporary);data=root/'data';sock=root/'socket';sock.mkdir(mode=0o700)
        init=[str(args.pg_bin_dir/'initdb'),'-D',str(data),'-U','edge_test_admin','--auth=trust','--locale=C.UTF-8','--encoding=UTF8']
        if args.pg_share_dir:init+=['-L',str(args.pg_share_dir)]
        subprocess.run(init,check=True,stdout=subprocess.DEVNULL)
        ctl=str(args.pg_bin_dir/'pg_ctl')
        subprocess.run([ctl,'-D',str(data),'-l',str(root/'server.log'),'-o',f"-k {sock} -p 55439 -c listen_addresses=''",'-w','start'],check=True,stdout=subprocess.DEVNULL)
        try:
            base=[str(args.pg_bin_dir/'psql'),'-X','-h',str(sock),'-p','55439','-U','edge_test_admin','-d','postgres','-v','ON_ERROR_STOP=1','-qAt']
            def sql(text,expect_error=False):
                result=subprocess.run(base,input=text,text=True,capture_output=True)
                if expect_error:
                    assert result.returncode!=0,'Expected SQL rejection'
                elif result.returncode:
                    raise RuntimeError(result.stderr)
                return result.stdout.strip().splitlines()
            def as_user(statement,uid=UID,role='authenticated',expect_error=False):
                claims='{"sub":"'+uid+'","role":"'+role+'"}'
                return sql(f"BEGIN; SET LOCAL ROLE {role}; SELECT set_config('request.jwt.claims','{claims}',true); {statement}; ROLLBACK;",expect_error)
            sql(f"""
                CREATE ROLE authenticated; CREATE ROLE anon;
                CREATE SCHEMA auth; CREATE SCHEMA storage;
                CREATE TABLE auth.users(id uuid PRIMARY KEY,role text,email_confirmed_at timestamptz,is_anonymous boolean);
                INSERT INTO auth.users VALUES ('{UID}','authenticated',now(),false);
                CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
                $$ SELECT coalesce(nullif(current_setting('request.jwt.claim.sub',true),''),
                   nullif(current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid $$;
                GRANT USAGE ON SCHEMA auth,storage TO authenticated,anon;
                CREATE TABLE storage.buckets(id text PRIMARY KEY,public boolean);
                INSERT INTO storage.buckets VALUES ('spx-snapshots',false),('other',false);
                CREATE TABLE storage.objects(bucket_id text,name text);
                ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
                GRANT SELECT,INSERT,UPDATE,DELETE ON storage.objects TO authenticated,anon;
                INSERT INTO storage.objects VALUES ('spx-snapshots','{RAW}'),
                  ('spx-snapshots','2026-W43/logs/log.json'),
                  ('spx-snapshots','replay/2026-W43/replay.json'),('other','private.json');
            """)
            sql(policy)
            assert as_user('SELECT count(*) FROM storage.objects')[-1]=='1'
            assert as_user('SELECT count(*) FROM storage.objects',uid=OTHER)[-1]=='0'
            assert as_user('SELECT count(*) FROM storage.objects',role='anon')[-1]=='0'
            assert as_user("SELECT count(*) FROM storage.objects WHERE bucket_id='other' OR name LIKE 'replay/%' OR name LIKE '%/logs/%'")[-1]=='0'
            print('PASS: dedicated reader sees raw SPX only; anonymous and other users see nothing')
            as_user("INSERT INTO storage.objects VALUES ('spx-snapshots','2026-W43/snapshots/SPX_CBOE_20261021_140000.json.gz')",expect_error=True)
            assert as_user("WITH changed AS (UPDATE storage.objects SET name='tampered.json' RETURNING 1) SELECT count(*) FROM changed")[-1]=='0'
            assert as_user('WITH changed AS (DELETE FROM storage.objects RETURNING 1) SELECT count(*) FROM changed')[-1]=='0'
            as_user('TRUNCATE storage.objects',expect_error=True)
            assert sql('SELECT count(*) FROM storage.objects')[-1]=='4'
            assert sql(f"SELECT count(*) FROM storage.objects WHERE name='{RAW}'")[-1]=='1'
            print('PASS: INSERT/TRUNCATE rejected; UPDATE/DELETE alter no rows (isolated synthetic database only)')
            sql("INSERT INTO storage.objects VALUES ('spx-snapshots','writer-check'); UPDATE storage.objects SET name='writer-updated' WHERE name='writer-check'; DELETE FROM storage.objects WHERE name='writer-updated';")
            assert sql('SELECT count(*) FROM storage.objects')[-1]=='4'
            print('PASS: existing owner writer retains its access')
            sql(policy,expect_error=True)
            assert sql("SELECT count(*) FROM pg_policies WHERE policyname='edge_spx_raw_reader_v1'")[-1]=='1'
            sql('DROP POLICY edge_spx_raw_reader_v1 ON storage.objects')
            cases=[
                ("UPDATE storage.buckets SET public=true WHERE id='spx-snapshots'", "UPDATE storage.buckets SET public=false WHERE id='spx-snapshots'",'public bucket'),
                ('ALTER TABLE storage.objects DISABLE ROW LEVEL SECURITY','ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY','RLS disabled'),
                ('CREATE POLICY unrelated ON storage.objects FOR SELECT TO authenticated USING (true)','DROP POLICY unrelated ON storage.objects','pre-existing policy'),
                ('CREATE TABLE public.unprotected(x int); GRANT INSERT ON public.unprotected TO authenticated','DROP TABLE public.unprotected','other inherited writes'),
                ("CREATE FUNCTION public.unsafe() RETURNS void LANGUAGE sql SECURITY DEFINER AS 'SELECT NULL::void'",'DROP FUNCTION public.unsafe()','executable definer'),
                (f"UPDATE auth.users SET email_confirmed_at=NULL WHERE id='{UID}'",f"UPDATE auth.users SET email_confirmed_at=now() WHERE id='{UID}'",'unconfirmed identity')
            ]
            for enable,restore,label in cases:
                sql(enable);sql(policy,expect_error=True)
                assert sql("SELECT count(*) FROM pg_policies WHERE policyname='edge_spx_raw_reader_v1'")[-1]=='0'
                sql(restore)
                print('PASS: setup rejected '+label+' and created no Edge policy')
            sql(f"DELETE FROM storage.objects WHERE name='{RAW}'")
            sql(policy,expect_error=True)
            assert sql("SELECT count(*) FROM pg_policies WHERE policyname='edge_spx_raw_reader_v1'")[-1]=='0'
            sql(f"INSERT INTO storage.objects VALUES ('spx-snapshots','{RAW}')")
            print('PASS: failed post-install verification rolls back the policy creation')
            sql(policy)
            assert as_user('SELECT count(*) FROM storage.objects')[-1]=='1'
            print('PASS: clean baseline can still be installed after rejection tests')
        finally:
            subprocess.run([ctl,'-D',str(data),'-m','fast','-w','stop'],check=True,stdout=subprocess.DEVNULL)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
