"""ES display basis: synchronized bars and errors, no live provider calls."""
from datetime import date

import httpx
import numpy as np
import pandas as pd
import pytest

from edge_futures import (BasisUnavailable, calculate_basis, download_basis,
                          parse_basis, rounded_basis)


def bars(day='2026-10-22', offset=40.5):
    index = pd.date_range(day + ' 09:30', periods=26, freq='15min', tz='America/New_York')
    spx = pd.Series(np.arange(26) + 7600., index=index)
    return spx + offset, spx


def test_previous_shared_cash_session_and_half_up_match_app_rule():
    es, spx = bars()
    earlier_es, earlier_spx = bars('2026-10-21', 90)
    later_es, later_spx = bars('2026-10-23', 100)
    result = calculate_basis(pd.concat([later_es, earlier_es, es]),
                             pd.concat([spx, earlier_spx, later_spx]), date(2026, 10, 23))
    assert result['reference_date'] == '2026-10-22'
    assert result['basis'] == 40.5 and result['bar_count'] == 26
    assert rounded_basis(result['basis']) == 41


def test_weekend_uses_last_available_common_session_and_ignores_extended_hours():
    es, spx = bars('2026-10-23', -40.5)
    extra = pd.DatetimeIndex(['2026-10-23 09:15', '2026-10-23 16:00'], tz=es.index.tz)
    es = pd.concat([es, pd.Series([10000., 10000.], index=extra)])
    spx = pd.concat([spx, pd.Series([7000., 7000.], index=extra)])
    result = calculate_basis(es, spx, date(2026, 10, 26))
    assert result['reference_date'] == '2026-10-23' and result['bar_count'] == 26
    assert result['basis'] == -40.5 and rounded_basis(result['basis']) == -41


def test_aligns_exact_instants_drops_missing_and_duplicate_bars_without_interpolation():
    es, spx = bars(offset=40)
    es = es.drop(es.index[[3, 4, 5]])
    spx = pd.concat([spx, spx.iloc[[-1]]]).tz_convert('UTC').sample(frac=1, random_state=1)
    result = calculate_basis(es, spx, date(2026, 10, 23))
    assert result['bar_count'] == 23 and result['basis'] == 40


@pytest.mark.parametrize('selection', [slice(0, 19), slice(2, None), slice(0, 23)])
def test_rejects_incomplete_previous_session_without_silently_using_older_day(selection):
    es, spx = bars()
    older_es, older_spx = bars('2026-10-21')
    with pytest.raises(BasisUnavailable, match='incompleta'):
        calculate_basis(pd.concat([older_es, es.iloc[selection]]),
                        pd.concat([older_spx, spx.iloc[selection]]), date(2026, 10, 23))


def test_rejects_missing_timezone_no_shared_bars_and_infinite_quotes():
    es, spx = bars()
    for left, right in ((es.tz_localize(None), spx), (es, spx.iloc[0:0]),
                        (es.shift(30, freq='D'), spx), (es * float('inf'), spx)):
        with pytest.raises(BasisUnavailable):
            calculate_basis(left, right, date(2026, 10, 23))


@pytest.mark.parametrize('value,expected', [('40',40), ('-40,5',-40.5), ('0',0), (' 0.5 ',.5)])
def test_manual_basis_keeps_user_precision(value, expected):
    assert parse_basis(value) == expected


@pytest.mark.parametrize('value', ['', 'nan', 'inf', '-Infinity', 'forty', '1e1000'])
def test_never_defaults_missing_or_nonfinite_basis_to_zero(value):
    with pytest.raises(BasisUnavailable):
        parse_basis(value)


def chart(symbol, series):
    return {'chart': {'error': None, 'result': [{'meta': {'symbol': symbol},
             'timestamp': [int(stamp.timestamp()) for stamp in series.index],
             'indicators': {'quote': [{'close': series.tolist()}]}}]}}


def test_download_reads_only_public_raw_15m_closes_and_reconciles_average():
    es, spx = bars(offset=40)
    calls = []
    def handler(request):
        calls.append(request)
        assert request.method == 'GET' and request.url.host == 'query1.finance.yahoo.com'
        assert 'authorization' not in request.headers
        assert request.url.params['interval'] == '15m'
        assert request.url.params['includePrePost'] == 'false'
        assert int(request.url.params['period1']) == int(pd.Timestamp('2026-10-13', tz='America/New_York').timestamp())
        assert int(request.url.params['period2']) == int(pd.Timestamp('2026-10-24', tz='America/New_York').timestamp())
        symbol = 'ES=F' if request.url.path.endswith('ES=F') else '^GSPC'
        return httpx.Response(200, json=chart(symbol, es if symbol == 'ES=F' else spx))
    result = download_basis(date(2026,10,23), now=date(2026,10,23), transport=httpx.MockTransport(handler))
    assert len(calls) == 2 and result['basis'] == 40 and result['reference_date'] == '2026-10-22'


@pytest.mark.parametrize('status', [302, 401, 429, 500])
def test_provider_failure_or_redirect_never_creates_a_basis_or_exposes_response(status):
    with pytest.raises(BasisUnavailable) as error:
        download_basis(date(2026,10,23), now=date(2026,10,23),
                       transport=httpx.MockTransport(lambda request: httpx.Response(status,text='PRIVATE_RESPONSE')))
    assert 'PRIVATE_RESPONSE' not in str(error.value)


@pytest.mark.parametrize('body', [{}, {'chart': {'error': 'unavailable'}},
                                 chart('WRONG_SYMBOL', bars()[0])])
def test_malformed_or_wrong_symbol_quotes_are_not_used(body):
    with pytest.raises(BasisUnavailable):
        download_basis(date(2026,10,23), now=date(2026,10,23),
                       transport=httpx.MockTransport(lambda request: httpx.Response(200,json=body)))


@pytest.mark.parametrize('target', [date(2026,1,1), date(2026,10,25)])
def test_out_of_range_dates_never_download_current_basis_for_old_snapshots(target):
    def forbidden(request):
        pytest.fail('Unexpected provider request for unavailable date')
    with pytest.raises(BasisUnavailable):
        download_basis(target, now=date(2026,10,23), transport=httpx.MockTransport(forbidden))
