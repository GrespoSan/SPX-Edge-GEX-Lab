"""ES price-coordinate translation, independent of the SPX gamma engine.

Matches APP SPX's previous-cash-session ES minus SPX average and integer
ROUND_HALF_UP rule. No Serafini imports, database access or trading connection.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

ET = ZoneInfo('America/New_York')
SOURCE = 'Yahoo Finance ES=F / ^GSPC (chiusure a 15m)'


class BasisUnavailable(ValueError):
    """No verified ES-SPX differential is available."""


def parse_basis(value: str) -> float:
    try:
        number = Decimal(value.strip().replace(',', '.'))
        if not number.is_finite() or abs(number) > Decimal('100000'):
            raise InvalidOperation
        return float(number)
    except (InvalidOperation, ValueError):
        raise BasisUnavailable('Inserisci un differenziale ES − SPX numerico e finito.') from None


def rounded_basis(value: float) -> int:
    number = Decimal(str(value))
    if not number.is_finite():
        raise BasisUnavailable('Differenziale ES − SPX non valido.')
    return int(number.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def calculate_basis(es: pd.Series, spx: pd.Series, target: date) -> dict:
    """Synchronized raw closes, 09:30 <= bar timestamp < 16:00 New York.

    Select the latest shared session strictly before target. Match APP SPX's
    minimum 20 bars, first bar <=09:45 and last bar >=15:30. No interpolation.
    """
    prepared = []
    for name, series in (('es', es), ('spx', spx)):
        if series.empty or not isinstance(series.index, pd.DatetimeIndex) or series.index.tz is None:
            raise BasisUnavailable('Barre ES/SPX mancanti o prive di fuso orario.')
        values = pd.to_numeric(series.copy(), errors='coerce')
        values.index = values.index.tz_convert(ET)
        # A duplicated bar cannot create an ambiguous Cartesian alignment.
        values = values[~values.index.duplicated(keep='last')]
        prepared.append(values.rename(name))
    pairs = pd.concat(prepared, axis=1, join='inner').dropna().sort_index()
    pairs = pairs[((pairs.index.time >= time(9, 30)) &
                   (pairs.index.time < time(16)) & (pairs.index.date < target))]
    if pairs.empty:
        raise BasisUnavailable('Nessuna seduta precedente con barre ES/SPX allineate.')
    reference = max(pairs.index.date)
    bars = pairs[pairs.index.date == reference]
    if len(bars) < 20 or bars.index[0].time() > time(9, 45) or bars.index[-1].time() < time(15, 30):
        raise BasisUnavailable('Seduta cash precedente incompleta: servono almeno 20 barre allineate, con inizio e fine seduta coperti.')
    if not ((bars > 0) & (bars < float('inf'))).all().all():
        raise BasisUnavailable('Quotazioni ES/SPX non valide nella seduta precedente.')
    differences = bars.es - bars.spx
    return {'reference_date': reference.isoformat(), 'target_date': target.isoformat(),
            'basis': float(differences.mean()), 'bar_count': len(bars),
            'minimum': float(differences.min()), 'maximum': float(differences.max()),
            'last': float(differences.iloc[-1]), 'source': SOURCE}


def _chart_series(body: dict, symbol: str) -> pd.Series:
    try:
        chart = body['chart']
        if chart.get('error'):
            raise ValueError
        item = chart['result'][0]
        if item['meta']['symbol'] != symbol:
            raise ValueError
        stamps = item['timestamp']
        closes = item['indicators']['quote'][0]['close']
        if not stamps or len(stamps) != len(closes):
            raise ValueError
        index = pd.to_datetime(stamps, unit='s', utc=True)
        if index.hasnans:
            raise ValueError
        return pd.Series(closes, index=index, dtype=float)
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        raise BasisUnavailable('Barre Yahoo ES/SPX non disponibili o non riconoscibili.') from None


def download_basis(target: date, *, now: date | None = None, transport=None) -> dict:
    """Read the same unadjusted Yahoo 15m closes used by APP SPX/yfinance.

    Fixed public endpoints only. No credentials, redirects or storage calls.
    Yahoo availability and continuous-contract identity are not guaranteed.
    """
    today = now or datetime.now(ET).date()
    if target > today + timedelta(days=1) or target < today - timedelta(days=50):
        raise BasisUnavailable('Data fuori dallo storico intraday disponibile: inserisci un differenziale verificato per quella data.')
    start = datetime.combine(target - timedelta(days=10), time.min, ET)
    end = datetime.combine(min(target + timedelta(days=1), today + timedelta(days=1)), time.min, ET)
    params = {'period1': int(start.timestamp()), 'period2': int(end.timestamp()),
              'interval': '15m', 'includePrePost': 'false'}
    series = {}
    try:
        with httpx.Client(timeout=httpx.Timeout(8, connect=4), follow_redirects=False,
                          transport=transport, headers={'User-Agent': 'SPX-Edge-GEX-Lab/1.0'}) as client:
            for symbol, encoded in (('ES=F', 'ES%3DF'), ('^GSPC', '%5EGSPC')):
                with client.stream('GET', 'https://query1.finance.yahoo.com/v8/finance/chart/' + encoded,
                                   params=params) as response:
                    if response.status_code != 200:
                        raise BasisUnavailable('Yahoo non rende disponibili le barre ES/SPX. Puoi inserire il differenziale verificato in APP SPX.')
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 4 * 1024 * 1024:
                            raise BasisUnavailable('Risposta ES/SPX troppo grande.')
                    series[symbol] = _chart_series(json.loads(raw), symbol)
    except httpx.HTTPError:
        raise BasisUnavailable('Fonte ES/SPX temporaneamente non raggiungibile. Puoi inserire il differenziale verificato in APP SPX.') from None
    except (ValueError, TypeError) as error:
        if isinstance(error, BasisUnavailable):
            raise
        raise BasisUnavailable('Barre Yahoo ES/SPX non riconoscibili.') from None
    return calculate_basis(series['ES=F'], series['^GSPC'], target)
