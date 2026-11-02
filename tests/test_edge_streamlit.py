"""Edge app smoke tests for the current single-password security boundary."""
import hashlib
from pathlib import Path

from streamlit.testing.v1 import AppTest
import edge_archive as A

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "edge_streamlit.py")


def authorized_test_app(monkeypatch):
    """Only a mocked private server session unlocks tests; no live Supabase."""
    user_id = "11111111-2222-4333-8444-555555555555"
    monkeypatch.setattr(
        A, "login_reader",
        lambda *args, **kwargs: A.ReaderSession("FAKE_TOKEN", "FAKE_REFRESH", 10**11, user_id)
    )
    monkeypatch.setattr(
        A, "renew_reader",
        lambda *args, **kwargs: args[2]
    )
    app = AppTest.from_file(APP)
    app.secrets["EDGE_APP_PASSWORD"] = "STRONG_TEST_PASSWORD"
    app.secrets["SUPABASE_URL"] = "https://exampleproject.supabase.co"
    app.secrets["SUPABASE_ANON_KEY"] = "sb_publishable_test"
    app.secrets["EDGE_READER_USER_ID"] = user_id
    app.secrets["EDGE_ARCHIVE_ENABLED"] = True
    app.secrets["EDGE_READER_EMAIL"] = "reader@example.test"
    app.secrets["EDGE_READER_PASSWORD"] = "FAKE_TEST_ONLY"
    app.session_state["edge_app_authorized"] = True
    app.session_state["edge_app_password_version"] = hashlib.sha256(
        b"STRONG_TEST_PASSWORD"
    ).hexdigest()
    return app


def test_startup_without_secrets_fails_closed_not_crash():
    app = AppTest.from_file(APP).run(timeout=20)
    assert not app.exception
    assert app.title[0].value == "SPX · Edge GEX Lab"
    assert any("EDGE_APP_PASSWORD" in message.value for message in app.error)
    assert not app.radio and not app.selectbox and not app.metric


def test_synthetic_snapshot_runs_full_app_and_all_expiry_modes(monkeypatch):
    app = authorized_test_app(monkeypatch)
    # No live storage call is required when entering the synthetic test mode.
    app.session_state["edge_advanced_source"] = "Esempio sintetico (test)"
    app.run(timeout=20)
    assert not app.exception and not app.error
    assert len(app.metric) == 5
    assert app.metric[0].value == "6,000.00"
    assert app.metric[1].value == "6,000.00"
    assert any("SINTETICO" in message.value for message in app.warning)
    app.selectbox[0].set_value("Prossime 4 scadenze").run(timeout=20)
    assert not app.exception and not app.error and len(app.metric) == 5
    app.selectbox[0].set_value("Tutte (finestra Edge)").run(timeout=20)
    assert not app.exception and not app.error
    app.radio(key="edge_advanced_source").set_value("Carica fotografia CBOE").run(timeout=20)
    assert not app.exception and len(app.metric) == 0


def test_unconfigured_automatic_archive_never_exposes_data():
    app = AppTest.from_file(APP)
    app.secrets["EDGE_APP_PASSWORD"] = "STRONG_TEST_PASSWORD"
    app.session_state["edge_app_authorized"] = True
    app.session_state["edge_app_password_version"] = hashlib.sha256(
        b"STRONG_TEST_PASSWORD"
    ).hexdigest()
    app.run(timeout=20)
    assert not app.exception and len(app.metric) == 0
    assert any("Archivio Edge non configurato" in message.value for message in app.error)
    assert not app.radio and not app.selectbox
