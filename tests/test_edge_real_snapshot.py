"""Explicitly skipped until an actual authorized SPX CBOE snapshot is provided."""
import os
from pathlib import Path

import pytest

from edge_verification import verify_snapshot


def test_real_spx_cboe_snapshot():
    path = os.environ.get('EDGE_REAL_SNAPSHOT_PATH')
    if not path:
        pytest.skip('Fotografia reale assente: impostare EDGE_REAL_SNAPSHOT_PATH. Le fixture sono sintetiche.')
    snapshot = Path(path)
    assert snapshot.is_file(), 'EDGE_REAL_SNAPSHOT_PATH non identifica un file leggibile'
    report = verify_snapshot(snapshot.read_bytes())
    assert report['symbol'] == 'SPX'
    assert report['contracts_cross_checked'] > 0
    assert report['arithmetic_check'] == 'passed'
    assert report['call_wall'] is not None and report['put_wall'] is not None
