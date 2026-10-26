"""Price timestamps, closed bars and overlays: public source mocked, no gamma changes."""
from datetime import datetime,timezone

import httpx
import pytest

from edge_market import MarketUnavailable, fetch_market, parse_market

NOW = datetime(2026,10,23,14,tzinfo=timezone.utc).timestamp()


def body():
    return {'chart':{'error':None,'result':[{'meta':{
        'symbol':'ES=F','regularMarketPrice':7720.,'regularMarketTime':NOW-5,'exchangeDataDelayedBy':10},
        'timestamp':[NOW-600,NOW-360,NOW-100],
        'indicators':{'quote':[{'open':[7710,7715,7720],'high':[7718,7722,7725],
                              'low':[7709,7712,7719],'close':[7715,7718,7724]}]}}]}}


def test_real_quote_time_and_price_preserved_and_incomplete_bar_excluded():
    quote=parse_market(body(),'ES=F',now=NOW)
    assert quote['price']==7720 and quote['kind']=='quote' and quote['delay_minutes']==10
    assert datetime.fromisoformat(quote['timestamp']).timestamp()==NOW-5
    assert len(quote['candles'])==2
    assert quote['candles'].time.max().timestamp()==NOW-60
    assert quote['candles'].close.tolist()==[7715,7718]


def test_missing_or_older_meta_quote_falls_back_to_latest_completed_close_with_its_time():
    for changes in ({'regularMarketPrice':None},{'regularMarketTime':NOW-700}):
        payload=body();payload['chart']['result'][0]['meta'].update(changes)
        quote=parse_market(payload,'ES=F',now=NOW)
        assert quote['kind']=='closed_bar' and quote['price']==7718
        assert datetime.fromisoformat(quote['timestamp']).timestamp()==NOW-60


@pytest.mark.parametrize('price',[0,-1,float('nan'),float('inf'),True])
def test_invalid_prices_with_no_valid_bars_do_not_become_current_prices(price):
    payload=body();item=payload['chart']['result'][0]
    item['meta']['regularMarketPrice']=price;item['timestamp']=[]
    with pytest.raises(MarketUnavailable):
        parse_market(payload,'ES=F',now=NOW)


def test_no_wrong_symbol_future_quote_or_malformed_source_is_used():
    future=body();future['chart']['result'][0]['timestamp']=[]
    future['chart']['result'][0]['meta']['regularMarketTime']=NOW+120
    for payload,symbol in ((body(),'^GSPC'),(future,'ES=F'),({},'ES=F'),({'chart':None},'ES=F')):
        with pytest.raises(MarketUnavailable):
            parse_market(payload,symbol,now=NOW)


def test_unpublished_delay_remains_unknown_and_old_quotes_are_not_retimed():
    payload=body();item=payload['chart']['result'][0]
    item['meta'].pop('exchangeDataDelayedBy');item['meta']['regularMarketTime']=NOW-86400;item['timestamp']=[]
    quote=parse_market(payload,'ES=F',now=NOW)
    assert quote['delay_minutes'] is None
    assert datetime.fromisoformat(quote['timestamp']).timestamp()==NOW-86400


def test_fixed_public_get_has_no_credentials_and_requests_completed_bar_context():
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.method=='GET' and request.url.host=='query1.finance.yahoo.com'
        assert request.url.path=='/v8/finance/chart/ES=F'
        assert dict(request.url.params)=={'range':'5d','interval':'5m','includePrePost':'true'}
        assert not request.content and 'authorization' not in request.headers and 'apikey' not in request.headers
        return httpx.Response(200,json=body())
    quote=fetch_market('ES=F',now=NOW,transport=httpx.MockTransport(handler))
    assert len(requests)==1 and quote['price']==7720


@pytest.mark.parametrize('status',[302,401,429,500])
def test_provider_errors_never_use_response_body_or_old_price_as_fresh(status):
    with pytest.raises(MarketUnavailable) as error:
        fetch_market('ES=F',transport=httpx.MockTransport(lambda r:httpx.Response(status,text='PRIVATE_RESPONSE')))
    assert 'PRIVATE' not in str(error.value)


@pytest.mark.parametrize('failure',['blocked','timeout','invalid','wrong_symbol','no_candles'])
def test_secondary_endpoint_recovers_closed_candles_without_auth_or_cookie_reuse(failure):
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.method=='GET' and not request.content
        assert 'authorization' not in request.headers and 'apikey' not in request.headers
        assert 'cookie' not in request.headers
        if request.url.host=='query1.finance.yahoo.com':
            if failure=='timeout':
                raise httpx.ReadTimeout('PRIVATE_NETWORK_DETAIL',request=request)
            if failure=='invalid':
                return httpx.Response(200,text='PRIVATE_INVALID_JSON',headers={'Set-Cookie':'session=private'})
            payload=body()
            if failure=='wrong_symbol':
                payload['chart']['result'][0]['meta']['symbol']='WRONG'
            if failure=='no_candles':
                payload['chart']['result'][0]['timestamp']=[]
            return httpx.Response(429,text='PRIVATE_RESPONSE',headers={'Set-Cookie':'session=private'}) if failure=='blocked' else httpx.Response(200,json=payload)
        assert request.url.host=='query2.finance.yahoo.com'
        return httpx.Response(200,json=body())
    result=fetch_market('ES=F',now=NOW,transport=httpx.MockTransport(handler))
    assert len(requests)==2 and result['price']==7720 and len(result['candles'])==2
    assert requests[0].url.params==requests[1].url.params
    assert requests[0].url.path==requests[1].url.path


def test_failed_endpoints_report_safe_causes_without_network_or_response_secrets():
    def handler(request):
        if request.url.host=='query1.finance.yahoo.com':
            return httpx.Response(429,text='PRIVATE_RESPONSE')
        raise httpx.ConnectError('PRIVATE_NETWORK_DETAIL',request=request)
    with pytest.raises(MarketUnavailable) as error:
        fetch_market('ES=F',now=NOW,transport=httpx.MockTransport(handler))
    assert 'HTTP 429' in str(error.value) and 'connessione non riuscita' in str(error.value)
    assert 'PRIVATE' not in str(error.value)


def test_quote_without_candles_is_preserved_with_original_time_if_secondary_fails():
    payload=body();payload['chart']['result'][0]['timestamp']=[]
    result=fetch_market('ES=F',now=NOW,transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json=payload) if request.url.host=='query1.finance.yahoo.com' else httpx.Response(503)))
    assert result['candles'].empty and result['price']==7720
    assert datetime.fromisoformat(result['timestamp']).timestamp()==NOW-5


def test_historical_fallback_requests_same_day_and_never_substitutes_todays_prices():
    from datetime import date
    requests=[]
    def handler(request):
        requests.append(request)
        if request.url.host=='query1.finance.yahoo.com':
            return httpx.Response(503)
        return httpx.Response(200,json=body())
    with pytest.raises(MarketUnavailable):
        fetch_market('ES=F',day=date(2026,10,22),now=NOW,transport=httpx.MockTransport(handler))
    assert len(requests)==2 and requests[0].url.params==requests[1].url.params
    assert 'range' not in requests[1].url.params


def test_unapproved_instrument_is_rejected_before_request():
    with pytest.raises(MarketUnavailable):
        fetch_market('http://other.test',transport=httpx.MockTransport(lambda r:pytest.fail('Unexpected request')))


def test_historical_day_never_uses_todays_metadata_quote_or_other_day_candles():
    from datetime import date
    payload=body();item=payload['chart']['result'][0]
    item['timestamp']=[stamp-86400 for stamp in item['timestamp']]
    quote=parse_market(payload,'ES=F',day=date(2026,10,22),now=NOW)
    assert quote['kind']=='closed_bar' and quote['price']==7724
    assert datetime.fromisoformat(quote['timestamp']).date()==date(2026,10,22)
    assert all(stamp.tz_convert('Europe/Rome').date()==date(2026,10,22) for stamp in quote['candles'].time)
    with pytest.raises(MarketUnavailable):
        parse_market(body(),'ES=F',day=date(2026,10,22),now=NOW)


def test_historical_fetch_uses_selected_italian_day_and_handles_25_hour_clock_change():
    from datetime import date
    current=datetime(2026,10,26,14,tzinfo=timezone.utc).timestamp()
    payload=body();payload['chart']['result'][0]['timestamp']=[current-86400-d for d in (600,360,100)]
    def handler(request):
        assert 'range' not in request.url.params
        assert int(request.url.params['period2'])-int(request.url.params['period1'])==25*3600
        return httpx.Response(200,json=payload)
    quote=fetch_market('ES=F',day=date(2026,10,25),now=current,transport=httpx.MockTransport(handler))
    assert datetime.fromisoformat(quote['timestamp']).date()==date(2026,10,25)


def test_unavailable_historical_date_does_not_fall_back_to_latest_day():
    from datetime import date
    for day in (date(2026,10,24),date(2026,1,1)):
        with pytest.raises(MarketUnavailable):
            fetch_market('ES=F',day=day,now=NOW,transport=httpx.MockTransport(lambda r:pytest.fail('Unexpected current-market request')))

