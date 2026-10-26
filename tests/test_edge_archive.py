"""Automatic private reader: real HTTP shapes, mocked transport, no remote writes."""
import base64
import json
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

import edge_archive as A
import edge_verification as V
import edge_futures as F
import edge_shared_basis as S
import edge_market as M
from edge_storage import StorageReadError

URL = 'https://exampleproject.supabase.co'
KEY = 'sb_publishable_example'
UID = '11111111-2222-4333-8444-555555555555'
OTHER = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'
NOW = 1_790_000_000
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_external_quotes(monkeypatch):
    M.cached_market.clear()
    def unavailable(*args,**kwargs):
        raise M.MarketUnavailable('No live market requests in isolated tests.')
    monkeypatch.setattr(M,'fetch_market',unavailable)
    yield
    M.cached_market.clear()


def jwt(uid=UID, role='authenticated', expiry=NOW+3600):
    body = base64.urlsafe_b64encode(json.dumps({'sub': uid, 'role': role, 'exp': expiry}).encode()).decode().rstrip('=')
    return 'header.' + body + '.signature'


def auth_response(uid=UID, role='authenticated', expiry=NOW+3600):
    return {'access_token': jwt(uid, role, expiry), 'refresh_token': 'PRIVATE_REFRESH', 'user': {'id': uid}}


def session(expiry=NOW+3600):
    return A.ReaderSession(jwt(expiry=expiry), 'PRIVATE_REFRESH', expiry, UID)


def test_login_uses_auth_endpoint_and_keeps_credentials_out_of_repr():
    def handler(request):
        assert request.method == 'POST' and request.url.path == '/auth/v1/token'
        assert request.url.params['grant_type'] == 'password'
        assert json.loads(request.content) == {'email': 'edge@example.test', 'password': 'PRIVATE_PASSWORD'}
        assert request.headers['apikey'] == KEY
        return httpx.Response(200, json=auth_response())
    auth = A.login_reader(URL, KEY, 'edge@example.test', 'PRIVATE_PASSWORD', UID,
                          now=NOW, transport=httpx.MockTransport(handler))
    assert auth.user_id == UID and auth.access_token == jwt()
    assert 'PRIVATE' not in repr(auth) and jwt() not in repr(auth)


@pytest.mark.parametrize('data', [auth_response(OTHER), auth_response(role='service_role'),
                                 auth_response(expiry=NOW-1), {}, {'access_token': 'bad'}])
def test_wrong_user_privileged_expired_or_invalid_auth_response_is_rejected(data):
    with pytest.raises(StorageReadError):
        A.login_reader(URL, KEY, 'edge@example.test', 'password', UID, now=NOW,
                       transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)))


def test_refresh_is_automatic_and_rotates_tokens():
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.params['grant_type'] == 'refresh_token'
        assert json.loads(request.content) == {'refresh_token': 'PRIVATE_REFRESH'}
        data=auth_response(expiry=NOW+7200)
        data['refresh_token']='NEW_REFRESH'
        return httpx.Response(200,json=data)
    auth=A.renew_reader(URL, KEY, session(NOW+30), UID, now=NOW, transport=httpx.MockTransport(handler))
    assert len(calls)==1 and auth.refresh_token=='NEW_REFRESH'


def test_fresh_session_requires_no_auth_request_and_identity_change_is_rejected():
    auth=session()
    assert A.renew_reader(URL,KEY,auth,UID,now=NOW) is auth
    with pytest.raises(StorageReadError):
        A.renew_reader(URL,KEY,auth,OTHER,now=NOW)


@pytest.mark.parametrize('status',[302,401,403,500])
def test_auth_failures_do_not_include_response_body_or_password(status):
    with pytest.raises(StorageReadError) as error:
        A.login_reader(URL,KEY,'edge@example.test','SECRET_PASSWORD',UID,now=NOW,
                       transport=httpx.MockTransport(lambda req:httpx.Response(status,text='SECRET_RESPONSE')))
    assert 'SECRET' not in str(error.value)


def test_connection_error_and_malformed_json_are_safe():
    def handler(request):
        raise httpx.ConnectError('SECRET '+str(request.url),request=request)
    for transport in (httpx.MockTransport(handler),httpx.MockTransport(lambda r:httpx.Response(200,text='not-json'))):
        with pytest.raises(StorageReadError) as error:
            A.login_reader(URL,KEY,'edge@example.test','SECRET',UID,now=NOW,transport=transport)
        assert 'SECRET' not in str(error.value)


def test_admin_or_nonpublic_key_is_rejected_before_any_request():
    for key in ('sb_secret_key',jwt(role='service_role'),jwt()):
        with pytest.raises(StorageReadError):
            A.login_reader(URL,key,'edge@example.test','password',UID,now=NOW)


def test_latest_uses_raw_snapshots_not_newer_replay_or_logs():
    prefixes=[]
    def handler(request):
        assert request.method=='POST' and request.url.path=='/storage/v1/object/list/spx-snapshots'
        assert request.headers['authorization']=='Bearer '+jwt()
        body=json.loads(request.content);prefixes.append(body['prefix'])
        assert body['sortBy']=={'column':'name','order':'desc'}
        if not body['prefix']:
            return httpx.Response(200,json=[{'name':'replay'},{'name':'2026-W43'},{'name':'2026-W42'}])
        assert body['prefix']=='2026-W43/snapshots'
        return httpx.Response(200,json=[{'name':'SPX_CBOE_20261020_150000.json.gz','updated_at':'a'},
                                       {'name':'SPX_CBOE_20261021_160000.json.gz','updated_at':'b'},
                                       {'name':'log.json'},{'name':'SPX_CBOE_20261399_999999.json.gz'}])
    ref=A.latest_snapshot(URL,KEY,session(),now=NOW,transport=httpx.MockTransport(handler))
    assert ref.path=='2026-W43/snapshots/SPX_CBOE_20261021_160000.json.gz'
    assert ref.updated_at=='b' and prefixes==['','2026-W43/snapshots']


def test_pagination_and_fallback_to_previous_archive_week(monkeypatch):
    monkeypatch.setattr(A,'PAGE_SIZE',2)
    def handler(request):
        body=json.loads(request.content)
        prefix,offset=body['prefix'],body['offset']
        if not prefix:
            return httpx.Response(200,json=[{'name':'replay'},{'name':'2026-W43'}] if offset==0 else [{'name':'2026-W42'}])
        if prefix=='2026-W43/snapshots':return httpx.Response(200,json=[])
        return httpx.Response(200,json=[{'name':'SPX_CBOE_20261016_140000.json.gz'}])
    assert A.latest_snapshot(URL,KEY,session(),now=NOW,transport=httpx.MockTransport(handler)).path.startswith('2026-W42/')


def test_pagination_limit_fails_instead_of_silently_using_incomplete_results(monkeypatch):
    monkeypatch.setattr(A,'PAGE_SIZE',1);monkeypatch.setattr(A,'MAX_PAGES',1)
    with pytest.raises(StorageReadError,match='paginazione'):
        A.latest_snapshot(URL,KEY,session(),now=NOW,transport=httpx.MockTransport(lambda r:httpx.Response(200,json=[{'name':'2026-W43'}])))


def test_download_uses_only_get_and_rejects_replay_or_other_paths():
    ref=A.SnapshotRef('2026-W43/snapshots/SPX_CBOE_20261021_160000.json.gz','')
    def handler(request):
        assert request.method=='GET'
        assert request.url.path.endswith('/spx-snapshots/'+ref.path)
        return httpx.Response(200,content=b'PRIVATE_SNAPSHOT')
    assert A.download_snapshot(URL,KEY,session(),ref,now=NOW,transport=httpx.MockTransport(handler))==b'PRIVATE_SNAPSHOT'
    for path in ('replay/2026-W43/file.json','2026-W43/logs/a.json','../x.json'):
        with pytest.raises(StorageReadError):
            A.download_snapshot(URL,KEY,session(),A.SnapshotRef(path,''),now=NOW)


def configured_app():
    app=AppTest.from_file(str(ROOT/'edge_streamlit.py'))
    app.session_state['edge_price_view']='Indice SPX'
    app.secrets['SUPABASE_URL']=URL
    app.secrets['SUPABASE_ANON_KEY']=KEY
    app.secrets['EDGE_READER_USER_ID']=UID
    app.secrets['EDGE_ARCHIVE_ENABLED']=True
    return app


def test_public_page_cannot_read_private_archive_without_login(monkeypatch):
    monkeypatch.setattr(A,'latest_snapshot',lambda *a,**k:pytest.fail('Anonymous storage request'))
    monkeypatch.setattr(S,'read_shared_basis',lambda *a,**k:pytest.fail('Anonymous shared feed request'))
    monkeypatch.setattr(M,'fetch_market',lambda *a,**k:pytest.fail('Anonymous market request'))
    app=configured_app().run(timeout=20)
    assert not app.exception and not app.error and len(app.metric)==0
    assert [box.label for box in app.text_input]==['Email Edge','Password Edge']
    assert len(app.get('form'))==1
    assert not app.radio and not app.selectbox and not app.get('download_button')


def test_private_login_automatic_selection_cached_rerun_and_logout(monkeypatch):
    calls=[]
    checks=[]
    version=['1']
    original_verify=V.verify_snapshot
    def verify(raw,mode):
        checks.append(mode)
        return original_verify(raw,mode)
    monkeypatch.setattr(V,'verify_snapshot',verify)
    monkeypatch.setattr(A,'login_reader',lambda *a,**k:session(expiry=10**10))
    monkeypatch.setattr(A,'renew_reader',lambda *a,**k:a[2])
    def latest(*args,**kwargs):
        calls.append('list');return A.SnapshotRef('2026-W43/snapshots/SPX_CBOE_20261021_160000.json.gz',version[0])
    monkeypatch.setattr(A,'latest_snapshot',latest)
    def download(*args,**kwargs):
        calls.append('get');return (ROOT/'fixtures/synthetic_cboe_spx.json').read_bytes()+b'\n'*int(version[0])
    monkeypatch.setattr(A,'download_snapshot',download)
    app=configured_app().run(timeout=20)
    app.text_input[0].set_value('edge@example.test');app.text_input[1].set_value('PRIVATE_PASSWORD')
    app.button[0].click().run(timeout=20)
    assert not app.exception and not app.error and len(app.metric)==5
    assert calls==['list','get']
    assert checks==['0DTE']
    report=app.session_state['edge_archive_analysis'][2]
    assert report['arithmetic_check']=='passed' and report['contracts_cross_checked']==10
    assert report['independent_net_gex']==pytest.approx(report['net'])
    assert report['independent_gross_gex']==pytest.approx(report['gross'])
    assert app.success and '10 contratti' in app.success[0].value
    assert len(app.get('download_button'))==3
    assert 'PRIVATE' not in json.dumps(report)
    next(button for button in app.button if button.label=='Aggiorna ora').click().run(timeout=20)
    assert not app.exception and calls==['list','get','list']
    assert checks==['0DTE']
    app.selectbox[0].set_value('Prossime 4 scadenze').run(timeout=20)
    assert not app.exception and len(app.metric)==5 and calls==['list','get','list']
    assert checks==['0DTE','Prossime 4 scadenze']
    previous_hash=app.session_state['edge_archive_analysis'][2]['sha256']
    version[0]='2'
    next(button for button in app.button if button.label=='Aggiorna ora').click().run(timeout=20)
    assert not app.exception and not app.error
    assert calls==['list','get','list','list','get']
    assert checks==['0DTE','Prossime 4 scadenze','Prossime 4 scadenze']
    assert app.session_state['edge_archive_analysis'][2]['sha256']!=previous_hash
    next(button for button in app.button if button.label=='Esci da Edge').click().run(timeout=20)
    assert not app.exception and len(app.metric)==0
    assert 'edge_archive_raw' not in app.session_state and 'edge_reader_session' not in app.session_state
    assert 'edge_archive_analysis' not in app.session_state
    assert len(app.text_input)==2


def test_arithmetic_mismatch_does_not_publish_unverified_metrics_or_report(monkeypatch):
    monkeypatch.setattr(A,'login_reader',lambda *a,**k:session(expiry=10**10))
    monkeypatch.setattr(A,'renew_reader',lambda *a,**k:a[2])
    monkeypatch.setattr(A,'latest_snapshot',lambda *a,**k:A.SnapshotRef('2026-W43/snapshots/SPX_CBOE_20261021_160000.json.gz','1'))
    monkeypatch.setattr(A,'download_snapshot',lambda *a,**k:(ROOT/'fixtures/synthetic_cboe_spx.json').read_bytes())
    def mismatch(*args,**kwargs):
        raise ValueError('NET GEX non riconciliato.')
    monkeypatch.setattr(V,'verify_snapshot',mismatch)
    app=configured_app().run(timeout=20)
    app.text_input[0].set_value('edge@example.test');app.text_input[1].set_value('PRIVATE_PASSWORD')
    app.button[0].click().run(timeout=20)
    assert not app.exception and app.error[0].value=='NET GEX non riconciliato.'
    assert not app.success and len(app.metric)==0 and len(app.get('download_button'))==0
    assert 'edge_archive_analysis' not in app.session_state


def test_legacy_server_token_cannot_expose_private_data_to_public_page():
    app=AppTest.from_file(str(ROOT/'edge_streamlit.py'))
    app.secrets['SUPABASE_READ_TOKEN']='LEGACY_PRIVATE_TOKEN'
    app.secrets['SUPABASE_SNAPSHOT_SIGNED_URL']='PRIVATE_URL'
    app.run(timeout=20)
    assert not app.exception and len(app.metric)==0
    assert 'Oggetto Supabase privato' not in app.radio[0].options
    assert 'Fotografia con URL firmato' not in app.radio[0].options


def test_es_translation_preserves_spx_math_and_exports_and_scopes_override_to_date(monkeypatch):
    import streamlit as st
    import pandas as pd
    import io
    from edge_clone_engine import analyze
    raw=(ROOT/'fixtures/synthetic_cboe_spx.json').read_bytes()
    original=analyze(raw,'0DTE')
    current_day=['21']
    downloads={}
    original_button=st.download_button
    def capture(label,data,*args,**kwargs):
        downloads[label]=data
        return original_button(label,data,*args,**kwargs)
    monkeypatch.setattr(st,'download_button',capture)
    monkeypatch.setattr(A,'login_reader',lambda *a,**k:session(expiry=10**10))
    monkeypatch.setattr(A,'renew_reader',lambda *a,**k:a[2])
    monkeypatch.setattr(A,'latest_snapshot',lambda *a,**k:A.SnapshotRef(f'2026-W43/snapshots/SPX_CBOE_202610{current_day[0]}_160000.json.gz','1'))
    monkeypatch.setattr(A,'download_snapshot',lambda *a,**k:raw)
    calls=[]
    def shared(project,key,reader,target):
        calls.append(target)
        if target.day!=21:
            raise F.BasisUnavailable('Differenziale di un altro giorno.')
        return {'basis':40.,'reference_date':'2026-10-20','source':'Archivio APP SPX · mt4/latest.csv',
                'published_utc':'2026-10-21T16:00:00+00:00','target_date':target.isoformat(),
                'shared_object':'mt4/latest.csv','provider_source':'Yahoo Finance'}
    monkeypatch.setattr(S,'read_shared_basis',shared)
    app=configured_app()
    app.session_state['edge_price_view']='Future ES (equivalente)'
    app.query_params['es_basis_date']='2026-10-21'
    app.query_params['es_basis']='40'
    app.run(timeout=20)
    app.text_input[0].set_value('edge@example.test');app.text_input[1].set_value('PRIVATE_PASSWORD')
    app.button[0].click().run(timeout=20)
    assert not app.exception and not app.error and len(calls)==1
    assert [m.value for m in app.metric[:3]]==['6,040.00','6,040.00','6,040.00']
    assert app.metric[0].label=='Spot equivalente ES'
    report=json.loads(downloads['Scarica verifica Edge JSON'])
    assert report['net']==original['net'] and report['gross']==original['gross']
    assert report['spot']==6000 and report['display_conversion']['offset']==40
    assert report['display_conversion']['target_date']=='2026-10-21'
    csv=pd.read_csv(io.BytesIO(downloads['Scarica profilo Edge CSV']))
    assert downloads['Scarica fotografia originale CBOE']==raw
    assert (csv.strike_es==csv.strike_spx+40).all()
    assert csv.net_gex.to_list()==pytest.approx(original['rows'].net_gex.to_list())
    figures=[json.loads(element.proto.spec) for element in app.get('plotly_chart')]
    import numpy as np
    def array(value):
        return np.frombuffer(base64.b64decode(value['bdata']),dtype=value['dtype']) if isinstance(value,dict) else np.array(value)
    call=next(trace for trace in figures[0]['data'] if trace.get('name')=='Call GEX')
    assert call['orientation']=='h' and call['xaxis']=='x2'
    assert array(call['y'])==pytest.approx(original['rows'].strike.to_numpy()+40)
    assert array(call['x'])==pytest.approx(original['rows'].call_gex.to_numpy()/1e9)
    assert figures[0]['layout']['yaxis']['range']==figures[0]['layout']['yaxis2']['range']
    assert array(figures[1]['data'][0]['x'])==pytest.approx(original['curve'].spot.to_numpy()+40)
    app.radio(key='edge_price_view').set_value('Indice SPX').run(timeout=20)
    assert not app.exception and app.metric[0].value=='6,000.00'
    app.radio(key='edge_price_view').set_value('Future ES (equivalente)').run(timeout=20)
    assert not app.exception and app.metric[0].value=='6,040.00' and len(calls)==1
    current_day[0]='22'
    next(b for b in app.button if b.label=='Aggiorna ora').click().run(timeout=20)
    assert not app.exception and not app.error and len(calls)==2
    assert app.metric[0].label=='Spot SPX' and app.metric[0].value=='6,000.00'
    assert json.loads(downloads['Scarica verifica Edge JSON'])['display_conversion']['offset'] is None
    assert any('restano in SPX' in message.value for message in app.info)


def test_automatic_es_basis_rounded_once_per_date_and_manual_override_retained(monkeypatch):
    monkeypatch.setattr(A,'login_reader',lambda *a,**k:session(expiry=10**10))
    monkeypatch.setattr(A,'renew_reader',lambda *a,**k:a[2])
    monkeypatch.setattr(A,'latest_snapshot',lambda *a,**k:A.SnapshotRef('2026-W43/snapshots/SPX_CBOE_20261021_160000.json.gz','1'))
    monkeypatch.setattr(A,'download_snapshot',lambda *a,**k:(ROOT/'fixtures/synthetic_cboe_spx.json').read_bytes())
    calls=[]
    raw_basis=[39.5]
    def estimate(project,key,reader,target):
        calls.append(target)
        return {'basis':raw_basis[0],'reference_date':'2026-10-20','source':'Archivio APP SPX · mt4/latest.csv',
                'published_utc':'2026-10-21T16:00:00+00:00','target_date':target.isoformat(),
                'shared_object':'mt4/latest.csv','provider_source':'Yahoo Finance'}
    monkeypatch.setattr(S,'read_shared_basis',estimate)
    monkeypatch.setattr(F,'download_basis',lambda *a,**k:pytest.fail('Edge must not recalculate the shared basis'))
    app=configured_app();app.session_state['edge_price_view']='Future ES (equivalente)'
    app.run(timeout=20)
    app.text_input[0].set_value('edge@example.test');app.text_input[1].set_value('PRIVATE_PASSWORD')
    app.button[0].click().run(timeout=20)
    assert not app.exception and app.metric[0].value=='6,040.00' and len(calls)==1
    record=app.session_state['edge_basis_days']['2026-10-21']
    record['read_at']=-1e12
    raw_basis[0]=40.5
    app.run(timeout=20)
    assert not app.exception and app.metric[0].value=='6,041.00' and len(calls)==2
    app.text_input[0].set_value('-10,5').run(timeout=20)
    assert not app.exception and app.metric[0].value=='5,989.50' and len(calls)==2
    app.selectbox[0].set_value('0DTE').run(timeout=20)
    assert not app.exception and app.metric[0].value=='5,989.50' and len(calls)==2
    next(b for b in app.button if b.label=='Rileggi ES − SPX').click().run(timeout=20)
    assert not app.exception and app.metric[0].value=='6,041.00' and len(calls)==3
    app.session_state['edge_basis_days']['2026-10-21']={
        'value':'100','attempted':True,'estimate':{'basis':100,'source':'old Yahoo result'},'error':''}
    app.session_state['edge_basis_input_2026-10-21']='100'
    app.run(timeout=20)
    assert not app.exception and app.metric[0].value=='6,041.00' and len(calls)==4
    next(b for b in app.button if b.label=='Esci da Edge').click().run(timeout=20)
    assert not app.exception and 'edge_basis_days' not in app.session_state


def test_price_refresh_updates_only_left_panel_and_retains_0dte_and_calculation_cache(monkeypatch):
    from datetime import datetime,timedelta,timezone
    import pandas as pd
    raw=(ROOT/'fixtures/synthetic_cboe_spx.json').read_bytes()
    monkeypatch.setattr(A,'login_reader',lambda *a,**k:session(expiry=10**10))
    monkeypatch.setattr(A,'renew_reader',lambda *a,**k:a[2])
    monkeypatch.setattr(A,'latest_snapshot',lambda *a,**k:A.SnapshotRef('2026-W43/snapshots/SPX_CBOE_20261021_160000.json.gz','1'))
    monkeypatch.setattr(A,'download_snapshot',lambda *a,**k:raw)
    checks=[];requests=[];price=[6045.];original=V.verify_snapshot
    def verify(*args):
        checks.append(args[1]);return original(*args)
    monkeypatch.setattr(V,'verify_snapshot',verify)
    monkeypatch.setattr(S,'read_shared_basis',lambda *a,**k:{'basis':40.,'reference_date':'2026-10-20',
        'published_utc':'2026-10-21T16:00:00+00:00','source':'Existing archive'})
    def market(symbol,*,day=None):
        requests.append((symbol,day));now=datetime.now(timezone.utc)
        candles=pd.DataFrame([{'time':now-timedelta(minutes=10-i*5),'open':6040+i,
                               'high':6045+i,'low':6039+i,'close':6042+i} for i in range(2)])
        return {'symbol':symbol,'price':price[0],'timestamp':now.isoformat(),'kind':'quote',
                'source':'Yahoo Finance','delay_minutes':10,'candles':candles}
    monkeypatch.setattr(M,'fetch_market',market)
    app=configured_app();app.session_state['edge_price_view']='Future ES (equivalente)'
    app.run(timeout=20)
    app.text_input[0].set_value('edge@example.test');app.text_input[1].set_value('PRIVATE_PASSWORD')
    app.button[0].click().run(timeout=20)
    assert not app.exception and not app.error and checks==['0DTE'] and requests==[('ES=F',None)]
    assert app.selectbox[0].value=='0DTE' and app.metric[0].value=='6,040.00'
    net=app.session_state['edge_archive_analysis'][1]['net']
    first=json.loads(app.get('plotly_chart')[0].proto.spec)
    assert first['data'][0]['type']=='candlestick' and first['data'][0]['xaxis']=='x'
    call=next(trace for trace in first['data'] if trace.get('name')=='Call GEX')
    assert call['xaxis']=='x2' and first['layout']['yaxis2']['matches']=='y'
    price[0]=6050.
    next(button for button in app.button if button.label=='Rileggi candele e prezzo').click().run(timeout=20)
    assert not app.exception and not app.error and checks==['0DTE'] and len(requests)==2
    second=json.loads(app.get('plotly_chart')[0].proto.spec)
    marker=next(trace for trace in second['data'] if trace.get('name')=='Ultimo prezzo disponibile')
    assert marker['y']==[6050.]
    assert app.session_state['edge_archive_analysis'][1]['net']==net
    records=app.session_state['edge_market_records']
    original_stamp=records[('ES=F','latest')]['market']['timestamp']
    def unavailable(*a,**k):
        raise M.MarketUnavailable('HTTP 429')
    monkeypatch.setattr(M,'fetch_market',unavailable)
    next(button for button in app.button if button.label=='Rileggi candele e prezzo').click().run(timeout=20)
    assert not app.exception and not app.error and checks==['0DTE']
    assert any('non aggiornati' in warning.value and 'HTTP 429' in warning.value for warning in app.warning)
    failed=json.loads(app.get('plotly_chart')[0].proto.spec)
    assert any(trace['type']=='candlestick' for trace in failed['data'])
    assert app.session_state['edge_market_records'][('ES=F','latest')]['market']['timestamp']==original_stamp
    assert app.session_state['edge_archive_analysis'][1]['net']==net
    monkeypatch.setattr(M,'fetch_market',market);price[0]=6055.
    next(button for button in app.button if button.label=='Rileggi candele e prezzo').click().run(timeout=20)
    assert not app.exception and not app.error and checks==['0DTE'] and len(requests)==3
    assert not any('non aggiornati' in warning.value for warning in app.warning)
    assert app.session_state['edge_market_records'][('ES=F','latest')]['market']['price']==6055.
    next(button for button in app.button if button.label=='Esci da Edge').click().run(timeout=20)
    assert not app.exception and 'edge_market_records' not in app.session_state


def test_historical_picker_keeps_selected_photo_and_requests_its_day_candles(monkeypatch):
    from datetime import date,datetime,timezone
    import pandas as pd
    raw=(ROOT/'fixtures/synthetic_cboe_spx.json').read_bytes()
    requests=[]
    monkeypatch.setattr(A,'login_reader',lambda *a,**k:session(expiry=10**10))
    monkeypatch.setattr(A,'renew_reader',lambda *a,**k:a[2])
    monkeypatch.setattr(A,'latest_snapshot',lambda *a,**k:A.SnapshotRef('2026-W43/snapshots/SPX_CBOE_20261021_160000.json.gz','1'))
    monkeypatch.setattr(A,'download_snapshot',lambda *a,**k:raw)
    ref=A.SnapshotRef('2026-W42/snapshots/SPX_CBOE_20261014_135903.json.gz','1')
    monkeypatch.setattr(A,'snapshots_for_day',lambda p,k,s,day:[ref] if day==date(2026,10,14) else [])
    def market(symbol,*,day=None):
        requests.append((symbol,day))
        stamp=datetime(2026,10,14,14,tzinfo=timezone.utc).isoformat()
        return {'symbol':symbol,'price':6005.,'timestamp':stamp,'kind':'closed_bar',
                'source':'Yahoo Finance','delay_minutes':None,'candles':pd.DataFrame()}
    monkeypatch.setattr(M,'fetch_market',market)
    app=configured_app().run(timeout=20)
    app.text_input[0].set_value('edge@example.test');app.text_input[1].set_value('PRIVATE_PASSWORD')
    app.button[0].click().run(timeout=20)
    app.radio(key='edge_archive_mode').set_value('Seleziona fotografia storica').run(timeout=20)
    app.date_input[0].set_value(date(2026,10,14)).run(timeout=20)
    assert not app.exception and not app.error and requests[-1]==('^GSPC',date(2026,10,14))
    assert app.session_state['edge_archive_ref']==ref
    assert app.radio(key='edge_archive_mode').value=='Seleziona fotografia storica'
    assert any('non è una simulazione' in c.value for c in app.caption)
    assert any(button.label=='Scarica fotografia originale CBOE' for button in app.get('download_button'))
