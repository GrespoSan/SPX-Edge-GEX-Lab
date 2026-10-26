"""Public reader parity with APP SPX; no archive or gamma values are imported."""
from datetime import date, datetime, timezone

import httpx
import pandas as pd
import pytest

import edge_market as M

NOW = datetime(2026,10,26,8,tzinfo=timezone.utc).timestamp()


@pytest.fixture(autouse=True)
def clear_public_cache():
    M.cached_market.clear()
    yield
    M.cached_market.clear()


def prices():
    return pd.DataFrame({'Open':[7660.,7665.,7670.],'High':[7668.,7672.,7675.],
                         'Low':[7659.,7663.,7668.],'Close':[7665.,7670.,7673.]},
                        index=pd.to_datetime(['2026-10-26T07:50Z','2026-10-26T07:55Z','2026-10-26T08:00Z']))


@pytest.mark.parametrize('columns',['flat','price_ticker','ticker_price'])
def test_library_reader_keeps_prices_and_closed_bar_times_for_supported_column_shapes(monkeypatch,columns):
    raw=prices()
    if columns=='price_ticker':
        raw.columns=pd.MultiIndex.from_tuples([(name,'ES=F') for name in raw])
    elif columns=='ticker_price':
        raw.columns=pd.MultiIndex.from_tuples([('ES=F',name) for name in raw])
    calls=[]
    def download(symbol,**options):
        calls.append((symbol,options));return raw
    monkeypatch.setattr(M.yf,'download',download)
    result=M.fetch_market('ES=F',now=NOW)
    assert result['reader']=='yfinance' and result['kind']=='closed_bar'
    assert result['price']==7670. and result['delay_minutes'] is None
    assert result['candles'].close.tolist()==[7665.,7670.]
    assert datetime.fromisoformat(result['timestamp']).timestamp()==NOW
    symbol,options=calls[0]
    assert symbol=='ES=F' and options=={'interval':'5m','auto_adjust':False,'progress':False,
        'prepost':True,'threads':False,'ignore_tz':False,'timeout':6,'period':'5d'}


def test_library_history_reads_same_window_as_replay_and_filters_selected_italian_day(monkeypatch):
    raw=prices();raw.index-=pd.Timedelta(days=1)
    calls=[]
    def download(symbol,**options):
        calls.append((symbol,options));return pd.concat([raw,prices()])
    monkeypatch.setattr(M.yf,'download',download)
    result=M.fetch_market('ES=F',day=date(2026,10,25),now=NOW)
    assert result['price']==7673. and len(result['candles'])==3
    assert result['candles'].time.dt.tz_convert('Europe/Rome').dt.date.unique().tolist()==[date(2026,10,25)]
    assert calls[0][1]['start']=='2026-10-24' and calls[0][1]['end']=='2026-10-27'
    assert 'period' not in calls[0][1]


@pytest.mark.parametrize('bad',['naive','nat','wrong_ticker','bad_ohlc','empty','invalid_price'])
def test_invalid_library_data_are_rejected_without_invented_timestamps(monkeypatch,bad):
    raw=prices()
    if bad=='naive':raw.index=raw.index.tz_localize(None)
    if bad=='nat':raw.index=pd.DatetimeIndex([pd.NaT]*3,tz='UTC')
    if bad=='wrong_ticker':raw.columns=pd.MultiIndex.from_tuples([(name,'OTHER') for name in raw])
    if bad=='bad_ohlc':raw=raw.drop(columns='High')
    if bad=='empty':raw=raw.iloc[:0]
    if bad=='invalid_price':raw['Close']=float('nan')
    monkeypatch.setattr(M.yf,'download',lambda *a,**k:raw)
    with pytest.raises(M.MarketUnavailable):
        M._yfinance_market('ES=F',day=None,now=NOW)


def test_library_failure_falls_back_to_http_without_echoing_external_error(monkeypatch):
    def download(*args,**options):
        raise RuntimeError('PRIVATE_EXTERNAL_ERROR')
    monkeypatch.setattr(M.yf,'download',download)
    client=M.httpx.Client
    def handler(request):
        assert request.url.host in M.HOSTS
        assert 'authorization' not in request.headers and 'apikey' not in request.headers
        return httpx.Response(429,text='PRIVATE_EXTERNAL_RESPONSE')
    monkeypatch.setattr(M.httpx,'Client',lambda **options:client(**{**options,'transport':httpx.MockTransport(handler)}))
    with pytest.raises(M.MarketUnavailable) as error:
        M.fetch_market('ES=F',now=NOW)
    assert 'HTTP 429' in str(error.value) and 'PRIVATE' not in str(error.value)


def test_public_cache_reuses_prices_across_sessions_and_isolates_ticker_and_day(monkeypatch):
    calls=[]
    def fetch(symbol,*,day=None):
        calls.append((symbol,day));return {'candles':prices(),'price':7670.,'timestamp':'2026-10-26T08:00:00+00:00'}
    monkeypatch.setattr(M,'fetch_market',fetch)
    first,error=M.cached_market('ES=F',None)
    first['candles'].iloc[0,0]=1
    second,error=M.cached_market('ES=F',None)
    assert not error and len(calls)==1 and second['candles'].iloc[0,0]==7660
    M.cached_market('^GSPC',None);M.cached_market('ES=F',date(2026,10,25))
    assert len(calls)==3
    M.cached_market.clear('ES=F',None)
    M.cached_market('ES=F',None)
    assert len(calls)==4


def test_public_cache_cools_down_failures_instead_of_repeating_rate_limited_requests(monkeypatch):
    calls=[]
    def fetch(symbol,*,day=None):
        calls.append(symbol);raise M.MarketUnavailable('HTTP 429')
    monkeypatch.setattr(M,'fetch_market',fetch)
    for _ in range(3):
        result,error=M.cached_market('ES=F',None)
        assert result is None and error=='HTTP 429'
    assert calls==['ES=F']
