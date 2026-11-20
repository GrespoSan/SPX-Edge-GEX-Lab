"""Streamlit Edge maintenance is default-on and precedes all archive access."""
import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest

from app_maintenance import (
    DEFAULT_MAINTENANCE_MODE, MAINTENANCE_MESSAGE,
    maintenance_enabled,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "edge_streamlit.py"


def test_paused_by_default_and_fails_closed_for_missing_secrets():
    assert DEFAULT_MAINTENANCE_MODE is True
    assert maintenance_enabled({}) is True
    assert maintenance_enabled({"MAINTENANCE_MODE": "unexpected"}) is True
    assert maintenance_enabled({"MAINTENANCE_MODE": False}) is False
    assert maintenance_enabled({"MAINTENANCE_MODE": "false"}) is False


def test_app_maintenance_blocks_all_auth_and_archive_without_secrets(monkeypatch):
    import edge_archive as archive

    def never_called(*_args, **_kwargs):
        raise AssertionError("No Supabase login or Cboe archive access in maintenance")

    monkeypatch.setattr(archive, "login_reader", never_called)
    monkeypatch.setattr(archive, "latest_snapshot", never_called)
    monkeypatch.setattr(archive, "download_snapshot", never_called)
    app = AppTest.from_file(str(APP)).run(timeout=20)
    assert not app.exception
    assert app.title and app.title[0].value == "SPX · Edge GEX Lab"
    assert any("Applicazione temporaneamente sospesa" in x.value for x in app.warning)
    assert any("Nessun archivio" in x.value for x in app.info)
    assert not app.text_input and not app.selectbox and not app.metric
    assert not app.button and not app.radio


def test_explicit_secret_false_restores_original_password_gate():
    app = AppTest.from_file(str(APP))
    app.secrets["MAINTENANCE_MODE"] = False
    app.run(timeout=20)
    assert not app.exception
    assert any("EDGE_APP_PASSWORD" in x.value for x in app.error)
    assert not any("Applicazione temporaneamente sospesa" in x.value for x in app.warning)


def test_maintenance_gate_precedes_password_and_data_loading():
    source = APP.read_text(encoding="utf-8")
    ast.parse(source, filename=str(APP))
    startup = source[source.index("def main():"):]
    assert startup.index('suspend_if_enabled(st, ') < startup.index('st.title("SPX · Edge GEX Lab")')
    assert startup.index('suspend_if_enabled(st, ') < startup.index("password_gate()")
    assert startup.index('suspend_if_enabled(st, ') < startup.index("private_session(config)")
    assert "Nessun archivio" in MAINTENANCE_MESSAGE
