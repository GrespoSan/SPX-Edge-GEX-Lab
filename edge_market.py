"""Public price context and descriptive level map; never gamma inputs."""
from datetime import datetime, timezone, timedelta, time as day_time
import json
import math
import time
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

SYMBOLS = {'ES=F':'ES%3DF', '^GSPC':'%5EGSPC', '^NDX':'%5ENDX'}
HOSTS = ('query1.finance.yahoo.com', 'query2.finance.yahoo.com')


class MarketUnavailable(ValueError):
    pass


def _positive(value):
    if isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError
    return number


def parse_market(body, symbol, *, day=None, now=None):
    current = time.time() if now is None else now
    try:
        if body['chart'].get('error'):
            raise ValueError
        item = body['chart']['result'][0]
        meta = item['meta']
        if meta['symbol'] != symbol:
            raise ValueError
        candles = []
        values = (item.get('indicators', {}).get('quote') or [{}])[0]
        for index, stamp in enumerate(item.get('timestamp') or []):
            try:
                stamp = _positive(stamp)
                if stamp + 300 > current:
                    continue  # Only completed 5-minute bars, like APP SPX.
                row = {key:_positive(values[key][index]) for key in ('open','high','low','close')}
                if row['low'] > min(row['open'],row['close']) or row['high'] < max(row['open'],row['close']):
                    continue
                row['time'] = datetime.fromtimestamp(stamp+300, timezone.utc)
                if day is not None and row['time'].astimezone(ZoneInfo('Europe/Rome')).date()!=day:
                    continue
                candles.append(row)
            except (ValueError, TypeError, KeyError, IndexError, OverflowError, OSError):
                continue
        frame = pd.DataFrame(candles, columns=['time','open','high','low','close'])
        if not frame.empty:
            frame = frame.drop_duplicates('time',keep='last').sort_values('time')
            if day is None:
                frame = frame.tail(72)
            frame = frame.reset_index(drop=True)
        quote = None
        try:
            price, stamp = _positive(meta['regularMarketPrice']), _positive(meta['regularMarketTime'])
            moment = datetime.fromtimestamp(stamp,timezone.utc)
            if stamp <= current + 60 and (day is None or moment.astimezone(ZoneInfo('Europe/Rome')).date()==day):
                quote = {'price':price,'timestamp':datetime.fromtimestamp(stamp,timezone.utc).isoformat(),'kind':'quote'}
        except (ValueError, TypeError, KeyError, OverflowError, OSError):
            pass
        if not frame.empty:
            last = frame.iloc[-1]
            if quote is None or last.time.timestamp() > datetime.fromisoformat(quote['timestamp']).timestamp():
                quote = {'price':float(last.close),'timestamp':last.time.isoformat(),'kind':'closed_bar'}
        if quote is None:
            raise ValueError
        delay = meta.get('exchangeDataDelayedBy')
        if isinstance(delay,bool) or not isinstance(delay,(int,float)) or not math.isfinite(delay) or delay < 0:
            delay = None
        return {**quote,'symbol':symbol,'source':'Yahoo Finance','delay_minutes':delay,'candles':frame}
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError):
        raise MarketUnavailable('Quotazione non disponibile o non riconoscibile dalla fonte.') from None


def fetch_market(symbol, *, day=None, transport=None, now=None):
    if symbol not in SYMBOLS:
        raise MarketUnavailable('Strumento di mercato non supportato.')
    current = time.time() if now is None else now
    params = {'range':'5d','interval':'5m','includePrePost':'true'}
    if day is not None:
        today = datetime.fromtimestamp(current,ZoneInfo('Europe/Rome')).date()
        if day>today or day<today-timedelta(days=59):
            raise MarketUnavailable('Giornata fuori dallo storico intraday disponibile; nessuna candela odierna viene sostituita allo storico.')
        start = datetime.combine(day,day_time.min,ZoneInfo('Europe/Rome'))
        end = datetime.combine(day+timedelta(days=1),day_time.min,ZoneInfo('Europe/Rome'))
        params = {'period1':int(start.timestamp()),'period2':int(min(end.timestamp(),current)),
                  'interval':'5m','includePrePost':'true'}
    failures = []
    quote_only = None
    # Independent clients prevent cookies from the first endpoint being sent
    # to the second. Only the ticker and identical period are requested.
    for host in HOSTS:
        try:
            with httpx.Client(timeout=httpx.Timeout(6,connect=3),follow_redirects=False,
                              transport=transport,headers={
                                  'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                                  'Accept':'application/json'}) as client:
                with client.stream('GET','https://'+host+'/v8/finance/chart/'+SYMBOLS[symbol],
                                   params=params) as response:
                    if response.status_code != 200:
                        raise MarketUnavailable('HTTP '+str(response.status_code))
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2*1024*1024:
                            raise MarketUnavailable('Risposta quotazioni troppo grande.')
                    market = parse_market(json.loads(raw),symbol,day=day,now=current)
                    if not market['candles'].empty:
                        return market
                    quote_only = market
        except httpx.TimeoutException:
            failures.append('tempo di risposta scaduto')
        except httpx.HTTPError:
            failures.append('connessione non riuscita')
        except (ValueError,TypeError) as error:
            failures.append(str(error) if isinstance(error,MarketUnavailable) else 'risposta non valida')
    if quote_only is not None:
        return quote_only
    details = '; '.join(f'{index}: {reason}' for index,reason in enumerate(failures,1))
    raise MarketUnavailable('Lettura Yahoo non riuscita sui due endpoint ('+details+').') from None

