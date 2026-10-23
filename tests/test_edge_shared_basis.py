"""Metadata-only authenticated access to the existing feed; no publisher writes."""
import base64
from datetime import date, datetime, timezone
import json

import httpx
import pytest

from edge_archive import ReaderSession
from edge_futures import BasisUnavailable
from edge_shared_basis import parse_shared_basis, read_shared_basis

NOW = datetime(2026,10,23,12,tzinfo=timezone.utc).timestamp()
TARGET = date(2026,10,23)
META = {'schema':'serafini_mt4_v3','date_rome':'2026-10-23','slot_rome':'13:30',
        'basis_es_spx':'39.500000','basis_date':'2026-10-22','basis_source':'Yahoo Finance',
        'published_utc':'2026-10-23T11:31:10+00:00'}
HEADER = b'profile,expiry,strike_spx,price_es,net_gamma\n'


def feed(changes=None):
    meta = dict(META, **(changes or {}))
    return ''.join(f'{key},{value}\n' for key,value in meta.items()).encode()+HEADER


def session():
    claims=base64.urlsafe_b64encode(json.dumps({'role':'authenticated'}).encode()).decode().rstrip('=')
    return ReaderSession('header.'+claims+'.signature','PRIVATE_REFRESH',NOW+3600,'reader')


def test_parses_only_metadata_and_does_not_import_profile_levels():
    report=parse_shared_basis(feed()+b'0DTE,FAKE_DATE,INFINITE_STRIKE,FAKE_PRICE,SERAFINI_NET_GAMMA\n',TARGET,now=NOW)
    assert report['basis']==39.5 and report['reference_date']=='2026-10-22'
    assert report['shared_object']=='mt4/latest.csv' and report['target_date']==TARGET.isoformat()
    assert set(report)=={'basis','reference_date','shared_object','target_date','published_utc','source','provider_source'}
    assert 'GAMMA' not in json.dumps(report) and 'PRIVATE' not in json.dumps(report)


@pytest.mark.parametrize('changes', [
    {'schema':'serafini_mt4_v2'}, {'basis_es_spx':'nan'}, {'basis_es_spx':'inf'},
    {'basis_date':'2026-10-23'}, {'basis_date':'bad'},
    {'published_utc':'2026-10-23T13:00:00+00:00'},
    {'published_utc':'2026-10-23T11:00:00'},
    {'published_utc':'2026-10-22T11:00:00+00:00'},
])
def test_invalid_or_future_metadata_never_produces_an_applied_differential(changes):
    with pytest.raises(BasisUnavailable):
        parse_shared_basis(feed(changes),TARGET,now=NOW)


def test_rejects_different_target_date_duplicate_keys_missing_fields_and_truncated_header():
    with pytest.raises(BasisUnavailable,match='altro giorno'):
        parse_shared_basis(feed(),date(2026,10,22),now=NOW)
    for raw in (b'basis_es_spx,1\n'+feed(), feed().replace(b'basis_source,Yahoo Finance\n',b''),
                feed().replace(HEADER,b''), b'x'*8192+feed()):
        with pytest.raises(BasisUnavailable):
            parse_shared_basis(raw,TARGET,now=NOW)


@pytest.mark.parametrize('status',[200,206])
def test_single_get_only_fixed_file_and_only_header_range(status):
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.method=='GET'
        assert request.url.path=='/storage/v1/object/authenticated/spx-snapshots/mt4/latest.csv'
        assert request.headers['range']=='bytes=0-8191'
        assert request.headers['authorization']=='Bearer '+session().access_token
        assert not request.content
        return httpx.Response(status,content=feed()+b'PRIVATE_PROFILE_ROWS_IGNORED')
    report=read_shared_basis('https://exampleproject.supabase.co','sb_publishable_example',
                             session(),TARGET,now=NOW,transport=httpx.MockTransport(handler))
    assert len(calls)==1 and report['basis']==39.5


def test_stops_streaming_before_profile_body():
    class MetadataOnly(httpx.SyncByteStream):
        def __iter__(self):
            yield feed()
            pytest.fail('Should not read profile rows')
    report=read_shared_basis('https://exampleproject.supabase.co','sb_publishable_example',session(),
                            TARGET,now=NOW,transport=httpx.MockTransport(lambda r:httpx.Response(206,stream=MetadataOnly())))
    assert report['basis']==39.5


@pytest.mark.parametrize('status',[302,401,403,404,500])
def test_errors_do_not_expose_tokens_or_response_body(status):
    with pytest.raises(BasisUnavailable) as error:
        read_shared_basis('https://exampleproject.supabase.co','sb_publishable_example',session(),TARGET,
                          now=NOW,transport=httpx.MockTransport(lambda r:httpx.Response(status,text='PRIVATE_RESPONSE')))
    assert 'PRIVATE' not in str(error.value) and session().access_token not in str(error.value)


def test_privileged_key_or_expired_session_never_requests_the_file():
    def forbidden(request):
        pytest.fail('Unexpected request')
    expired=session();expired.expires_at=NOW
    for key,auth in [('sb_secret_admin',session()),('sb_publishable_example',expired)]:
        with pytest.raises(BasisUnavailable):
            read_shared_basis('https://exampleproject.supabase.co',key,auth,TARGET,now=NOW,
                              transport=httpx.MockTransport(forbidden))
