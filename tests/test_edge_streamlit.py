from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_startup_without_secrets_does_not_crash():
    app = AppTest.from_file(str(ROOT / 'edge_streamlit.py')).run(timeout=20)
    assert not app.exception
    assert app.title[0].value == 'SPX · Edge GEX Lab'
    assert not app.error
    assert len(app.metric) == 0


def test_synthetic_snapshot_runs_full_app_and_all_expiry_modes():
    app = AppTest.from_file(str(ROOT / 'edge_streamlit.py')).run(timeout=20)
    app.radio[0].set_value('Esempio sintetico (test)').run(timeout=20)
    assert not app.exception and not app.error
    assert len(app.metric) == 5
    assert app.metric[0].value == '6,000.00'
    assert app.metric[1].value == '6,000.00'
    assert any('SINTETICO' in warning.value for warning in app.warning)
    app.selectbox[0].set_value('0DTE').run(timeout=20)
    assert not app.exception and not app.error and len(app.metric) == 5
    app.selectbox[0].set_value('Tutte (finestra Edge)').run(timeout=20)
    assert not app.exception and not app.error
    app.radio[0].set_value('Carica fotografia CBOE').run(timeout=20)
    assert not app.exception and len(app.metric) == 0


def test_unconfigured_storage_and_signed_url_are_optional_not_startup_failures():
    app = AppTest.from_file(str(ROOT / 'edge_streamlit.py')).run(timeout=20)
    for source in ('Oggetto Supabase privato', 'Fotografia con URL firmato'):
        app.radio[0].set_value(source).run(timeout=20)
        assert not app.exception and not app.error and len(app.metric) == 0
