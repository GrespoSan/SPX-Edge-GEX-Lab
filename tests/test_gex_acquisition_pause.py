"""Production suspension: no new Edge GEX chain, HTTP or UI acquisition."""
from pathlib import Path
import pytest
from fastapi import HTTPException

import gex_acquisition_pause as pause
from gexlab import config, service
from gexlab import api
from gexlab.sources import cboe
from gexlab.sources.base import SourceError

ROOT = Path(__file__).resolve().parents[1]


def test_pause_is_fixed_and_has_no_external_runtime_override():
    assert pause.GEX_ACQUISITIONS_PAUSED is True
    assert "sospese" in pause.PAUSE_MESSAGE
    with pytest.raises(RuntimeError, match="sospese"):
        pause.require_gex_acquisition_enabled()


def test_all_cboe_http_sources_stop_before_lookup(monkeypatch):
    monkeypatch.setattr(cboe, "cboe_symbol",
                        lambda symbol: pytest.fail("Reached Cboe symbol/HTTP path"))
    for ticker in ("SPX", "NDX", "QQQ", "SPY"):
        with pytest.raises(SourceError, match="sospese") as exc:
            cboe.fetch_raw(ticker)
        assert exc.value.status == 503


def test_background_recorder_and_live_service_stop_before_calendar_or_alpaca(monkeypatch):
    monkeypatch.setattr(config, "is_demo", lambda: False)
    monkeypatch.setattr(service, "get_calendar",
                        lambda *_: pytest.fail("Reached vendor calendar"))
    for symbol in ("SPX", "NDX", "SPY", "AAPL"):
        with pytest.raises(SourceError, match="sospese") as exc:
            service.fetch_chain(symbol, priority="high")
        assert exc.value.status == 503


def test_api_blocks_map_expiries_and_search_before_vendor_calls(monkeypatch):
    monkeypatch.setattr(config, "is_demo", lambda: False)
    monkeypatch.setattr(service, "search",
                        lambda *_: pytest.fail("Reached remote search"))
    monkeypatch.setattr(service, "expirations",
                        lambda *_: pytest.fail("Reached expiry retrieval"))
    monkeypatch.setattr(service, "build_map",
                        lambda *_: pytest.fail("Reached live GEX map"))
    for call in (lambda: api.search("SPX"),
                 lambda: api.expirations("SPX"),
                 lambda: api.gex_map("SPX")):
        with pytest.raises(HTTPException, match="sospese") as err:
            call()
        assert err.value.status_code == 503


def test_paused_health_and_cached_chain_never_refresh_vendor(monkeypatch):
    monkeypatch.setattr(config, "is_demo", lambda: False)
    monkeypatch.setattr(service, "get_calendar",
                        lambda *_: pytest.fail("Health performed Alpaca calendar request"))
    monkeypatch.setattr(service, "fetch_chain",
                        lambda *_args, **_kwargs: pytest.fail("Cached chain fetched again"))
    monkeypatch.setattr(service, "last_frozen", lambda: None)
    monkeypatch.setattr(service, "latest_captures", lambda: [])
    state = service.health()
    assert state["status"] == "paused"
    assert state["feeds"]["cboe"] is False
    assert state["calendar"]["source"] == "paused"
    with pytest.raises(SourceError, match="sospese") as err:
        service.cached_chain("SPX")
    assert err.value.status == 503


def test_streamlit_manual_download_is_disabled_without_deleting_archive():
    code = (ROOT / "edge_streamlit.py").read_text(encoding="utf-8")
    assert 'if acquisition_pause.GEX_ACQUISITIONS_PAUSED:' in code
    assert 'st.button("Scarica ora · sospeso"' in code
    assert 'disabled=True' in code
    assert 'return None, False' in code
    assert 'download_snapshot' in code
    assert 'st.file_uploader(' in code
    # A historical snapshot remains readable without a new Cboe call.
    assert (ROOT / "edge_archive.py").is_file()
