"""Independent, archive-only Streamlit application. No Serafini integration."""
from __future__ import annotations

import os
from pathlib import Path
import time

import plotly.graph_objects as go
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from edge_clone_engine import MODES, analyze
from edge_storage import StorageReadError
from edge_archive import login_reader, renew_reader, latest_snapshot, download_snapshot

ROOT = Path(__file__).resolve().parent
UPLOAD = "Carica fotografia CBOE"
DEMO = "Esempio sintetico (test)"
AUTO = "Archivio SPX automatico"


def setting(name, default=""):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except StreamlitSecretNotFoundError:
        return os.environ.get(name, default)


def confirmed(name):
    return str(setting(name, False)).lower() == "true"


def archive_configuration():
    config = (setting('SUPABASE_URL'), setting('SUPABASE_ANON_KEY'), setting('EDGE_READER_USER_ID'))
    return config if confirmed('EDGE_ARCHIVE_ENABLED') and all(config) else None


def clear_private_session():
    for key in ('edge_reader_session', 'edge_archive_raw', 'edge_archive_ref',
                'edge_archive_fetched', 'edge_raw'):
        st.session_state.pop(key, None)


def private_session(config):
    if config is None:
        st.info('Archivio privato non configurato. La prima attivazione richiede l’utenza Edge dedicata e il suo permesso di sola lettura.')
        return None
    project, key, user_id = config
    session = st.session_state.get('edge_reader_session')
    if session is not None:
        try:
            session = renew_reader(project, key, session, user_id)
            st.session_state['edge_reader_session'] = session
        except StorageReadError:
            clear_private_session()
            session = None
            st.warning('Sessione terminata o accesso revocato. Accedi nuovamente a Edge.')
    if session is None:
        st.caption('Accesso alle sole fotografie private SPX. Usa l’utenza creata appositamente per Edge.')
        with st.form('edge_reader_login', clear_on_submit=True):
            email = st.text_input('Email Edge')
            password = st.text_input('Password Edge', type='password')
            submitted = st.form_submit_button('Accedi a Edge')
        if submitted:
            try:
                session = login_reader(project, key, email, password, user_id)
                clear_private_session()
                st.session_state['edge_reader_session'] = session
                st.rerun()
            except StorageReadError as error:
                st.error(str(error))
        return None
    if st.button('Esci da Edge', key='edge_reader_logout'):
        clear_private_session()
        st.rerun()
    return session


def source_data(mode):
    config = archive_configuration()
    options = (AUTO, UPLOAD, DEMO) if config else (UPLOAD, AUTO, DEMO)
    source = st.radio("Sorgente dati", options, horizontal=True)
    if source == AUTO:
        automatic_archive(mode)
        return None, None
    if source == UPLOAD:
        uploaded = st.file_uploader("Fotografia originale CBOE (.json o .json.gz)", type=("json", "gz"))
        return (uploaded.getvalue() if uploaded else None), False
    st.warning("ESEMPIO SINTETICO: dati creati per test, non una fotografia reale CBOE.")
    return (ROOT / "fixtures/synthetic_cboe_spx.json").read_bytes(), True


def render_result(result, synthetic=False):
    if synthetic:
        st.caption("Risultati su esempio sintetico; nessuna verifica su dati reali.")
    st.caption(f"{result['symbol']} | Fotografia UTC: {result['timestamp']} | Valutazione Edge: {result['valuation']}")
    columns = st.columns(5)
    for column, label, value in zip(columns,
            ("Spot", "Call Wall", "Put Wall", "Gamma Flip vicino", "Regime"),
            (result["spot"], result["call_wall"], result["put_wall"], result["flip"], result["regime"])):
        column.metric(label, f"{value:,.2f}" if isinstance(value, (int, float)) else value or "N/D")
    st.write("Scadenze effettive:", ", ".join(result["expiries"]))
    quality = "non stimabile" if result["quality_pct"] is None else f"{result['quality_pct']:.2f}%"
    st.write(f"Copertura GEX stimata: **{quality}** | Contratti validi: **{result['valid']} / {result['total']}**")
    if not result["quality_sufficient"]:
        st.warning("Copertura inferiore alla soglia Edge o non stimabile: il profilo può essere incompleto.")
    st.write(f"NET GEX: **{result['net'] / 1e9:,.4f} miliardi USD/1%** · Gross GEX: **{result['gross'] / 1e9:,.4f} miliardi USD/1%**")
    frame = result["rows"]
    if not frame.empty:
        chart = go.Figure()
        chart.add_bar(x=frame["strike"], y=frame["call_gex"] / 1e9, name="Call GEX")
        chart.add_bar(x=frame["strike"], y=frame["put_gex"] / 1e9, name="Put GEX")
        chart.add_scatter(x=frame["strike"], y=frame["net_gex"] / 1e9, name="NET GEX", mode="lines")
        chart.add_vline(x=result["spot"], line_dash="dot", annotation_text="Spot")
        chart.update_layout(xaxis_title="Strike", yaxis_title="Miliardi USD per movimento dell'1%", barmode="relative")
        st.plotly_chart(chart, width="stretch")
        st.download_button("Scarica profilo Edge CSV", frame.to_csv(index=False).encode(),
                           file_name=f"EDGE_{result['symbol']}_{'SYNTHETIC_' if synthetic else ''}{result['sha256'][:12]}.csv",
                           mime="text/csv")
    else:
        st.info("Nessuno strike nella fascia del grafico; i totali includono comunque la catena selezionata.")
    st.caption("Grafico e wall: strike entro ±10% dallo spot. Totali e curva ipotetica: contratti selezionati acquisiti entro ±20%.")
    with st.expander("Curva ipotetica e tutti i gamma flip"):
        curve = result["curve"]
        chart = go.Figure(go.Scatter(x=curve["spot"], y=curve["net_gex"] / 1e9, mode="lines", name="NET GEX ipotetico"))
        chart.add_hline(y=0, line_dash="dot")
        chart.update_layout(xaxis_title="Spot ipotetico", yaxis_title="Miliardi USD/1%")
        st.plotly_chart(chart, width="stretch")
        st.write("Attraversamenti dello zero:", result["flips"] or "Nessun attraversamento nella finestra Edge")
    with st.expander("Metodo Edge e provenienza"):
        st.write("Gamma Black–Scholes con r = q = 0; GEX = segno × gamma × OI × 100 × spot² × 0,01. Call positive e put negative sono assunzioni sulle posizioni, non dati osservati dei dealer.")
        st.write("Tempo residuo dal timestamp storico o dall'ultima chiusura secondo il motore Edge; mai dalla data odierna. Radice SPX/NDX: AM 09:30 New York; SPXW/NDXP: PM alla chiusura di sessione.")
        st.write("Calendario locale XNYS: proxy delle sessioni USA con festività e chiusure anticipate; non è un calendario ufficiale dei regolamenti CBOE.")
        st.write("Data OI inferita dalla sessione precedente, non pubblicata da CBOE:", result["oi_date"])
        st.code("SHA-256 file: " + result["sha256"] + "\nModello Edge: " + result["model_version"])
        st.caption("Nessuna scrittura Supabase, nessun invio MT4, nessuna integrazione con Serafini. Nessun processo di acquisizione live avviato dall'app.")


@st.fragment(run_every='120s')
def automatic_archive(mode):
    config = archive_configuration()
    session = private_session(config)
    if session is None:
        return
    project, key, _ = config
    force = st.button('Aggiorna ora', key='edge_archive_refresh')
    now = time.monotonic()
    fetched = st.session_state.get('edge_archive_fetched', 0)
    try:
        if force or 'edge_archive_raw' not in st.session_state or now - fetched >= 110:
            reference = latest_snapshot(project, key, session)
            if reference != st.session_state.get('edge_archive_ref') or 'edge_archive_raw' not in st.session_state:
                raw = download_snapshot(project, key, session, reference)
                st.session_state['edge_archive_raw'] = raw
                st.session_state['edge_archive_ref'] = reference
            st.session_state['edge_archive_fetched'] = now
        reference = st.session_state['edge_archive_ref']
        st.caption('Aggiornamento automatico ogni 2 minuti mentre questa pagina è aperta. Fotografia selezionata dalla settimana di archivio più recente disponibile.')
        st.caption('File archiviato: ' + reference.path)
        result = analyze(st.session_state['edge_archive_raw'], mode)
        if result['symbol'] != 'SPX':
            raise ValueError('Il file selezionato non contiene una catena SPX.')
        render_result(result)
    except StorageReadError as error:
        st.session_state.pop('edge_archive_raw', None)
        st.session_state.pop('edge_archive_ref', None)
        st.error(str(error))
    except ValueError as error:
        st.error(str(error))
    except Exception:
        st.error('Archivio non disponibile. Dettagli sensibili omessi.')


def main():
    st.set_page_config(page_title="SPX Edge GEX Lab", layout="wide")
    st.title("SPX · Edge GEX Lab")
    st.caption("Applicazione indipendente · fotografie CBOE in sola lettura")
    st.warning("Analisi modellata per ricerca. Posizioni dealer non osservabili; fotografie e open interest possono essere ritardati.")
    mode = st.selectbox("Scadenze da analizzare", MODES, index=1)
    raw, synthetic = source_data(mode)
    if synthetic is None:
        return
    if raw is None:
        st.info("Seleziona una fotografia per avviare il calcolo Edge.")
        return
    try:
        result = analyze(raw, mode)
    except ValueError as error:
        st.error(str(error))
        return
    except Exception:
        st.error("Fotografia non elaborabile. Nessun dato o dettaglio sensibile viene mostrato.")
        return
    render_result(result, synthetic)


main()
