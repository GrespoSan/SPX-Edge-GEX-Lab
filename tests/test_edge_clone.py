"""Regression tests for the independent archival adapter; all data here are synthetic."""
import gzip
import json
import math
from datetime import date
from pathlib import Path

import pytest

import edge_clone_engine as E
from edge_verification import verify_snapshot

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/synthetic_cboe_spx.json'


def snapshot(timestamp=None):
    obj = json.loads(FIXTURE.read_bytes())
    if timestamp:
        obj['timestamp'] = timestamp
    return obj


def payload(obj):
    return json.dumps(obj).encode()


@pytest.mark.parametrize('compressed', [False, True])
def test_historical_snapshot_is_independent_of_todays_date(compressed):
    raw = FIXTURE.read_bytes()
    if compressed:
        raw = gzip.compress(raw)
    report = verify_snapshot(raw)
    assert report['timestamp'] == report['valuation'] == '2026-10-14T13:59:03+00:00'
    assert report['expiries'] == ['2026-10-14', '2026-10-15', '2026-10-16', '2026-10-19']
    assert report['contracts_cross_checked'] == 40
    assert report['call_wall'] == report['put_wall'] == 6000
    assert report['net'] == pytest.approx(727812426.027492)
    assert report['arithmetic_check'] == 'passed'


def test_0dte_and_all_modes_select_different_contracts():
    raw = FIXTURE.read_bytes()
    zero = E.analyze(raw, '0DTE')
    full = E.analyze(raw, E.MODES[2])
    assert zero['expiries'] == ['2026-10-14'] and zero['total'] == 10
    assert len(full['expiries']) == 6 and full['total'] == 60
    assert E.analyze(raw, E.MODES[1])['total'] == 40


def test_time_to_expiry_uses_historical_timestamp_and_pm_settlement():
    chain, contracts, _ = E.prepare_contracts(FIXTURE.read_bytes(), '0DTE')
    seconds_to_2000_utc = 6 * 3600 + 57
    assert chain.valuation.isoformat() == '2026-10-14T13:59:03+00:00'
    assert contracts[0].T == pytest.approx(seconds_to_2000_utc / (365 * 86400))


def test_after_hours_freezes_at_the_source_days_close():
    obj = snapshot('2026-10-14 21:00:00')
    result = E.analyze(payload(obj), E.MODES[1])
    assert result['valuation'] == '2026-10-14T20:00:00+00:00'
    assert '2026-10-14' not in result['expiries']
    with pytest.raises(ValueError, match='Nessun contratto'):
        E.analyze(payload(obj), '0DTE')


def test_next_four_expiries_excludes_already_settled_am_only_date():
    obj = snapshot('2026-10-14 15:00:00')
    for option in obj['data']['options']:
        if option['option'].startswith('SPXW261014'):
            option['option'] = option['option'].replace('SPXW', 'SPX', 1)
    result = E.analyze(payload(obj), E.MODES[1])
    assert result['expiries'] == ['2026-10-15', '2026-10-16', '2026-10-19', '2026-10-20']


def test_calendar_covers_good_friday_early_close_and_dst():
    cal = E.archive_calendar(date(2026, 4, 6))
    assert not cal.is_session(date(2026, 4, 3))  # Good Friday, not a US federal holiday.
    assert cal.prev_session(date(2026, 4, 6)) == date(2026, 4, 2)
    cal = E.archive_calendar(date(2026, 11, 27))
    assert not cal.is_session(date(2026, 11, 26))
    assert cal.close_dt(date(2026, 11, 27)).isoformat() == '2026-11-27T18:00:00+00:00'
    assert cal.close_dt(date(2026, 11, 30)).hour == 21
    assert E.archive_calendar(date(2026, 10, 14)).close_dt(date(2026, 10, 14)).hour == 20


def test_empty_unknown_and_invalid_inputs_are_rejected():
    for raw in (b'', b'[]', b'{}', b'not-json', b'\x1f\x8bgarbage'):
        with pytest.raises(ValueError):
            E.analyze(raw)
    with pytest.raises(ValueError, match='Modalità'):
        E.analyze(FIXTURE.read_bytes(), 'unknown')


@pytest.mark.parametrize('spot', [0, -1, True, '6000', float('nan'), float('inf')])
def test_invalid_spot_is_rejected(spot):
    obj = snapshot()
    obj['data']['current_price'] = spot
    with pytest.raises(ValueError):
        E.analyze(payload(obj))


@pytest.mark.parametrize('oi', [-1, .5, True, '100', float('inf')])
def test_invalid_open_interest_cannot_create_negative_or_fractional_exposure(oi):
    obj = snapshot()
    obj['data']['options'][0]['open_interest'] = oi
    with pytest.raises(ValueError):
        E.analyze(payload(obj))


def test_unknown_exposure_is_not_treated_as_zero():
    obj = snapshot()
    for option in obj['data']['options']:
        if option['option'].startswith('SPXW261014'):
            option['iv'] = None
    report = E.analyze(payload(obj), E.MODES[1])
    assert report['quality_unbounded'] and report['quality_pct'] is None
    assert not report['quality_sufficient']


def test_all_missing_iv_fails_instead_of_returning_zero_gex():
    obj = snapshot()
    for option in obj['data']['options']:
        option['iv'] = None
    with pytest.raises(ValueError, match='Nessun contratto'):
        E.analyze(payload(obj))


def test_mismatched_symbol_and_duplicate_contracts_are_rejected():
    obj = snapshot()
    obj['symbol'] = 'NDX'
    with pytest.raises(ValueError, match='simbolo'):
        E.analyze(payload(obj))
    obj = snapshot()
    obj['data']['options'].append(obj['data']['options'][0])
    with pytest.raises(ValueError, match='duplicati'):
        E.analyze(payload(obj))


def test_compressed_size_limit_is_enforced(monkeypatch):
    monkeypatch.setattr(E, 'MAX_JSON_BYTES', 100)
    with pytest.raises(ValueError, match='decompressa'):
        E.analyze(gzip.compress(FIXTURE.read_bytes()))


def test_per_strike_net_reconciles_for_fixture_inside_the_display_band():
    report = E.analyze(FIXTURE.read_bytes(), E.MODES[1])
    rows = report['rows']
    assert (rows.call_gex >= 0).all() and (rows.put_gex <= 0).all()
    assert rows.net_gex.sum() == pytest.approx(report['net'])
    assert (rows.call_gex.abs() + rows.put_gex.abs()).sum() == pytest.approx(report['gross'])
