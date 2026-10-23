"""Independent gamma engine with read-only shared market metadata."""
from __future__ import annotations

import os
import hashlib
import json
from datetime import datetime
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from edge_clone_engine import MODES, analyze
from edge_storage import StorageReadError
from edge_archive import login_reader, renew_reader, latest_snapshot, download_snapshot
from edge_verification import verify_snapshot
from edge_futures import BasisUnavailable, parse_basis, rounded_basis
from edge_shared_basis import read_shared_basis

ROOT = Path(__file__).resolve().parent
UPLOAD = "Carica fotografia CBOE"
DEMO = "Esempio sintetico (test)"
AUTO = "Archivio SPX automatico"


def italian_time(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Timestamp privo di fuso orario.')
    return stamp.astimezone(ZoneInfo('Europe/Rome')).strftime('%d/%m/%Y %H:%M:%S %Z')


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
                'edge_archive_fetched', 'edge_archive_analysis', 'edge_raw'):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith('edge_basis_'):
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


def price_conversion(result, synthetic, target, archive_context=None):
    """Translate price coordinates only; never feed ES back into the gamma engine."""
    if result['symbol'] != 'SPX':
        return {'unit': result['symbol'], 'offset': None}
    view = st.radio('Livelli visualizzati', ('Future ES (equivalente)', 'Indice SPX'),
                    index=1 if synthetic else 0, horizontal=True, key='edge_price_view')
    if view == 'Indice SPX':
        return {'unit': 'SPX', 'offset': None}
    day = target.isoformat()
    days = st.session_state.setdefault('edge_basis_days', {})
    record = days.setdefault(('synthetic:' if synthetic else '') + day,
                             {'value': '', 'estimate': None, 'error': '', 'read_at': None, 'manual': False})
    migrated = 'read_at' not in record
    if migrated:
        # Discard an estimate retained by the previous Yahoo-based release.
        record.update(value='', estimate=None, error='', read_at=None, manual=False)
    # A verified differential may be supplied in a link, scoped to ONE date.
    if archive_context is None and not synthetic and record['read_at'] is None and not record['value']:
        if st.query_params.get('es_basis_date') == day:
            proposed = st.query_params.get('es_basis', '')
            try:
                parse_basis(proposed)
                record['value'] = proposed
                record['manual'] = True
            except BasisUnavailable:
                pass
    widget_key = 'edge_basis_input_' + ('synthetic_' if synthetic else '') + day
    if migrated:
        st.session_state.pop(widget_key, None)
    if widget_key in st.session_state and st.session_state[widget_key] != record['value']:
        record['value'] = st.session_state[widget_key]
        record['manual'] = bool(record['value'].strip())
    left, right = st.columns([2, 1])
    refresh = right.button('Rileggi ES − SPX', key='edge_basis_refresh_' + day,
                           disabled=synthetic or archive_context is None)
    current = time.monotonic()
    if (archive_context is not None and not synthetic and
            (refresh or record['read_at'] is None or current - record['read_at'] >= 110)):
        try:
            with st.spinner('Lettura differenziale già pubblicato da APP SPX...'):
                estimate = read_shared_basis(*archive_context, target)
            record.update(estimate=estimate, error='')
            if refresh:
                record['manual'] = False
        except BasisUnavailable as error:
            record.update(estimate=None, error=str(error))
        record['read_at'] = current
    if not record['manual']:
        estimate = record['estimate']
        record['value'] = str(rounded_basis(estimate['basis'])) if estimate is not None else ''
        st.session_state[widget_key] = record['value']
    if widget_key not in st.session_state:
        st.session_state[widget_key] = record['value']
    record['value'] = left.text_input('Differenziale ES − SPX (punti)', key=widget_key,
                                      placeholder='Vuoto: livelli SPX',
                                      help='Letto dai metadati già pubblicati da APP SPX, arrotondato al punto intero. Eventuale correzione manuale valida solo per questa data.')
    estimate = record['estimate']
    if estimate is not None:
        st.caption(f"Differenziale pubblicato {estimate['basis']:.6f} → {rounded_basis(estimate['basis']):+d} punti · seduta {estimate['reference_date']} · pubblicazione (Italia): {italian_time(estimate['published_utc'])}. {estimate['source']}.")
    if record['error']:
        st.caption(record['error'])
    if archive_context is None and not synthetic:
        st.caption('La lettura automatica del differenziale privato richiede accesso ad Archivio SPX automatico.')
    try:
        offset = parse_basis(record['value'])
        if result['spot'] + offset <= 0:
            raise BasisUnavailable('Il differenziale produrrebbe un prezzo ES non valido.')
    except BasisUnavailable as error:
        if record['value'].strip():
            st.warning(str(error))
        st.info('Conversione ES non disponibile: i valori seguenti restano in SPX. Serve un differenziale condiviso valido per questa data.')
        return {'unit': 'SPX', 'offset': None, 'target_date': day}
    automatic = not record['manual'] and estimate is not None
    st.caption(f"Livelli ES equivalenti = SPX {offset:+g} punti · data {day} · spot SPX originale {result['spot']:,.2f}. Il valore equivalente non è una quotazione ES in tempo reale.")
    st.caption('Il differenziale è riferito al future continuo ES=F; può differire dal contratto specifico del tuo grafico. GEX e regime restano quelli delle opzioni SPX.')
    return {'unit': 'ES_equivalent', 'offset': offset, 'target_date': day,
            'source': estimate['source'] if automatic else 'Differenziale verificato inserito dall’utente',
            'reference_date': estimate['reference_date'] if automatic else None,
            'automatic_estimate': estimate}


def render_result(result, synthetic=False, basis_target=None, archive_context=None):
    if synthetic:
        st.caption("Risultati su esempio sintetico; nessuna verifica su dati reali.")
    st.caption(f"{result['symbol']} | Valutazione Edge (Italia): {italian_time(result['valuation'])}")
    target = basis_target or datetime.fromisoformat(result['timestamp']).date()
    conversion = price_conversion(result, synthetic, target, archive_context)
    offset = conversion['offset']
    shift = offset if offset is not None else 0
    translated = offset is not None
    suffix = ' ES' if translated else ' ' + result['symbol']
    def price(value):
        return None if value is None else value + shift
    st.markdown(f"**Fotografia CBOE · ora italiana: {italian_time(result['timestamp'])}**")
    columns = st.columns(5)
    for column, label, value in zip(columns,
            ("Spot equivalente ES" if translated else 'Spot' + suffix,
             'Call Wall' + suffix, 'Put Wall' + suffix, 'Gamma Flip' + suffix, 'Regime ' + result['symbol']),
            (price(result["spot"]), price(result["call_wall"]), price(result["put_wall"]), price(result["flip"]), result["regime"])):
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
        chart.add_bar(x=frame["strike"] + shift, y=frame["call_gex"] / 1e9, name="Call GEX")
        chart.add_bar(x=frame["strike"] + shift, y=frame["put_gex"] / 1e9, name="Put GEX")
        chart.add_scatter(x=frame["strike"] + shift, y=frame["net_gex"] / 1e9, name="NET GEX", mode="lines")
        spot_display = price(result["spot"])
        chart.add_vline(x=spot_display, line_dash="dot", line_color="#b5c6de")
        # Display annotations above the bars, staggered to avoid text collisions.
        markers = [
            ("Put Wall", price(result["put_wall"]), "#26b6a6"),
            ("Gamma Flip", price(result["flip"]), "#e7ae4e"),
            ("Call Wall", price(result["call_wall"]), "#e27c82"),
        ]
        for idx, (label, value, color) in enumerate(markers):
            if value is not None:
                chart.add_vline(x=value, line_color=color, line_width=1.5, line_dash="dash")
                chart.add_annotation(
                    x=value, y=1.13 + idx * 0.085, xref="x", yref="paper",
                    text=f"{label}: {value:,.2f}", showarrow=False,
                    font=dict(color=color, size=12), bgcolor="rgba(15,22,33,0.95)",
                    bordercolor=color, borderwidth=1, borderpad=4,
                )
        chart.add_annotation(
            x=spot_display, y=1.02, xref="x", yref="paper",
            text=f"Spot: {spot_display:,.2f}", showarrow=False,
            font=dict(color="#b5c6de", size=11), bgcolor="rgba(15,22,33,0.9)",
        )
        chart.update_layout(
            xaxis_title="Strike ES equivalente" if translated else "Strike " + result['symbol'],
            yaxis_title=f"GEX {result['symbol']} · miliardi USD per movimento dell'1%",
            barmode="relative", margin=dict(t=135), height=540,
            legend=dict(orientation="h", y=1.01, x=1, xanchor="right"),
        )
        center = spot_display
        important = [value for _, value, _ in markers if value is not None]
        range_limit = max(200.0, max((abs(v-center)+25 for v in important), default=0))
        view = st.radio(
            "Ampiezza grafico", ("Zoom operativo", "Vista completa"),
            horizontal=True, key="edge_chart_zoom",
        )
        if view == "Zoom operativo":
            chart.update_xaxes(range=[center-range_limit, center+range_limit])
        st.caption(f"Profilo {', '.join(result['expiries'])} · {('0DTE' if len(result['expiries']) == 1 else 'scadenze multiple')} · "
                   "barre Call/Put e NET per strike; non sono segnali di acquisto/vendita.")
        st.plotly_chart(chart, width="stretch")
        exported = frame.copy()
        if translated:
            exported = exported.rename(columns={'strike': 'strike_spx'})
            exported.insert(1, 'strike_es', frame['strike'] + shift)
            exported['basis_es_spx'] = offset
            exported['basis_target_date'] = conversion['target_date']
            exported['basis_reference_date'] = conversion['reference_date']
            exported['basis_source'] = conversion['source']
        st.download_button("Scarica profilo Edge CSV", exported.to_csv(index=False).encode(),
                           file_name=f"EDGE_{'ES_equivalente_' if translated else ''}{result['symbol']}_{'SYNTHETIC_' if synthetic else ''}{result['sha256'][:12]}.csv",
                           mime="text/csv")
    else:
        st.info("Nessuno strike nella fascia del grafico; i totali includono comunque la catena selezionata.")
    st.caption("Grafico e wall: strike entro ±10% dallo spot. Totali e curva ipotetica: contratti selezionati acquisiti entro ±20%.")
    with st.expander("Curva ipotetica e tutti i gamma flip"):
        curve = result["curve"]
        chart = go.Figure(go.Scatter(x=curve["spot"] + shift, y=curve["net_gex"] / 1e9, mode="lines", name="NET GEX ipotetico"))
        chart.add_hline(y=0, line_dash="dot")
        chart.update_layout(xaxis_title="Prezzo ES equivalente" if translated else "Spot ipotetico " + result['symbol'], yaxis_title=f"GEX {result['symbol']} · miliardi USD/1%")
        st.plotly_chart(chart, width="stretch")
        st.write("Attraversamenti dello zero" + suffix + ":", [price(value) for value in result['flips']] or "Nessun attraversamento nella finestra Edge")
    with st.expander("Metodo Edge e provenienza"):
        st.write("Gamma Black–Scholes con r = q = 0; GEX = segno × gamma × OI × 100 × spot² × 0,01. Call positive e put negative sono assunzioni sulle posizioni, non dati osservati dei dealer.")
        st.write("Tempo residuo dal timestamp storico o dall'ultima chiusura secondo il motore Edge; mai dalla data odierna. Radice SPX/NDX: AM 09:30 New York; SPXW/NDXP: PM alla chiusura di sessione.")
        st.write("Calendario locale XNYS: proxy delle sessioni USA con festività e chiusure anticipate; non è un calendario ufficiale dei regolamenti CBOE.")
        st.write("Data OI inferita dalla sessione precedente, non pubblicata da CBOE:", result["oi_date"])
        st.code("SHA-256 file: " + result["sha256"] + "\nModello Edge: " + result["model_version"])
        st.caption("Motori Edge e Serafini separati. Nessuna scrittura Supabase, nessun invio MT4 e nessuna acquisizione CBOE live avviata dall'app.")
    return conversion


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
        raw = st.session_state['edge_archive_raw']
        analysis_key = (hashlib.sha256(raw).hexdigest(), mode)
        cached = st.session_state.get('edge_archive_analysis')
        if cached is None or cached[0] != analysis_key:
            st.session_state.pop('edge_archive_analysis', None)
            result = analyze(raw, mode)
            if result['symbol'] != 'SPX':
                raise ValueError('Il file selezionato non contiene una catena SPX.')
            report = verify_snapshot(raw, mode)
            cached = (analysis_key, result, report)
            st.session_state['edge_archive_analysis'] = cached
        _, result, report = cached
        st.success(f"Verifica aritmetica superata: {report['contracts_cross_checked']} contratti, NET e Gross GEX riconciliati.")
        target = datetime.strptime(reference.path.rsplit('/', 1)[-1][9:17], '%Y%m%d').date()
        conversion = render_result(result, basis_target=target, archive_context=(project, key, session))
        exported_report = {**report, 'display_conversion': conversion}
        st.download_button('Scarica verifica Edge JSON', json.dumps(exported_report, indent=2, allow_nan=False),
                           file_name=f"EDGE_verifica_{result['sha256'][:12]}.json",
                           mime='application/json', on_click='ignore')
        st.caption('Confronto con formula scalare separata; selezione dei contratti e tempi residui sono condivisi. Non certifica origine dei dati o posizioni dealer.')
    except StorageReadError as error:
        st.session_state.pop('edge_archive_raw', None)
        st.session_state.pop('edge_archive_ref', None)
        st.session_state.pop('edge_archive_analysis', None)
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
