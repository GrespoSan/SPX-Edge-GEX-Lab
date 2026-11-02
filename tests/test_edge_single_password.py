"""Regression tests: the Edge UI asks for only one password and fails closed."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

import edge_archive as A
from edge_storage import StorageReadError

ROOT = Path(__file__).resolve().parents[1]
URL = "https://exampleproject.supabase.co"
KEY = "sb_publishable_example"
UID = "11111111-2222-4333-8444-555555555555"


def app_with_password():
    app = AppTest.from_file(str(ROOT / "edge_streamlit.py"))
    app.secrets["EDGE_APP_PASSWORD"] = "STRONG_TEST_APP_PASSWORD"
    return app


def test_no_password_secret_denies_all_app_modes():
    app = AppTest.from_file(str(ROOT / "edge_streamlit.py")).run(timeout=20)
    assert not app.exception
    assert any("EDGE_APP_PASSWORD" in item.value for item in app.error)
    assert not app.radio and not app.selectbox and not app.metric


def test_single_input_rejects_wrong_password_before_any_backend_access(monkeypatch):
    monkeypatch.setattr(A, "login_reader", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("Supabase login must not be called before password gate")
    ))
    app = app_with_password().run(timeout=20)
    assert not app.exception
    assert [item.label for item in app.text_input] == ["Password"]
    assert not app.selectbox and not app.metric
    app.text_input[0].set_value("WRONG_TEST_PASSWORD")
    next(button for button in app.button if button.label == "Accedi a Edge").click().run(timeout=20)
    assert not app.exception
    assert any("Password non corretta" in item.value for item in app.error)
    assert not app.selectbox and not app.metric


def test_correct_app_password_unlocks_without_email_input():
    app = app_with_password().run(timeout=20)
    app.text_input[0].set_value("STRONG_TEST_APP_PASSWORD")
    next(button for button in app.button if button.label == "Accedi a Edge").click().run(timeout=20)
    assert not app.exception
    assert not app.text_input
    # No implicit public mode: a missing technical Supabase configuration blocks.
    assert any("Archivio Edge non configurato" in item.value for item in app.error)
    assert not app.selectbox and not app.metric


def test_server_side_supabase_credentials_and_logout(monkeypatch):
    called = []
    def fake_login(url, key, email, password, uid):
        called.append((email, password, uid))
        return A.ReaderSession("SESSION", "REFRESH", 10**11, uid)
    monkeypatch.setattr(A, "login_reader", fake_login)
    def no_snapshot(*args, **kwargs):
        raise StorageReadError("Archivio test non disponibile")
    monkeypatch.setattr(A, "latest_snapshot", no_snapshot)

    app = app_with_password()
    app.secrets["SUPABASE_URL"] = URL
    app.secrets["SUPABASE_ANON_KEY"] = KEY
    app.secrets["EDGE_READER_USER_ID"] = UID
    app.secrets["EDGE_ARCHIVE_ENABLED"] = True
    app.secrets["EDGE_READER_EMAIL"] = "reader@example.test"
    app.secrets["EDGE_READER_PASSWORD"] = "SUPABASE_SERVER_ONLY_TEST_PASSWORD"
    app.run(timeout=20)
    app.text_input[0].set_value("STRONG_TEST_APP_PASSWORD")
    next(button for button in app.button if button.label == "Accedi a Edge").click().run(timeout=20)

    assert not app.exception
    assert called == [("reader@example.test", "SUPABASE_SERVER_ONLY_TEST_PASSWORD", UID)]
    assert not app.text_input  # Supabase credentials are never requested in the page.
    next(button for button in app.button if button.label == "Esci da Edge").click().run(timeout=20)
    assert not app.exception
    assert [item.label for item in app.text_input] == ["Password"]
    assert "edge_reader_session" not in app.session_state


def test_supabase_http_402_reports_quota_not_bad_password(monkeypatch):
    monkeypatch.setattr(
        A, "login_reader",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            StorageReadError("Richiesta di lettura/accesso non riuscita (HTTP 402).")
        ),
    )
    app = app_with_password()
    app.secrets["SUPABASE_URL"] = URL
    app.secrets["SUPABASE_ANON_KEY"] = KEY
    app.secrets["EDGE_READER_USER_ID"] = UID
    app.secrets["EDGE_ARCHIVE_ENABLED"] = True
    app.secrets["EDGE_READER_EMAIL"] = "reader@example.test"
    app.secrets["EDGE_READER_PASSWORD"] = "SERVER_ONLY_TEST_PASSWORD"
    app.run(timeout=20)
    app.text_input[0].set_value("STRONG_TEST_APP_PASSWORD")
    next(button for button in app.button if button.label == "Accedi a Edge").click().run(timeout=20)
    assert not app.exception
    assert any("HTTP 402" in error.value for error in app.error)
    assert not app.selectbox and not app.metric
