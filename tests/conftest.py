"""Shared test helpers for the public edition."""
from datetime import date, timedelta

from gexlab.engine.calendar import TradingCalendar

import pytest
import gex_acquisition_pause as acquisition_pause


@pytest.fixture(autouse=True)
def simulated_vendor_unit_tests(monkeypatch, request):
    """Legacy formula/vendor tests run with controlled fake inputs, not production HTTP.

    Only the dedicated suspension suite tests the production pause. This
    fixture exists solely inside tests; no runtime secrets or UI override.
    """
    if request.node.path.name != "test_gex_acquisition_pause.py":
        monkeypatch.setattr(acquisition_pause, "GEX_ACQUISITIONS_PAUSED", False)



def exchange_cal(start=date(2026, 9, 1), end=date(2026, 11, 30), closes=None):
    """An exchange calendar shaped like Alpaca's /v2/calendar (weekdays, optional early closes)."""
    rows, d = [], start
    while d <= end:
        if d.weekday() < 5:
            rows.append({"date": d.isoformat(), "open": "09:30", "close": (closes or {}).get(d, "16:00")})
        d += timedelta(days=1)
    cal = TradingCalendar.from_alpaca(rows)
    cal.covered = (start, end)
    return cal
