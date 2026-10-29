"""Independent gamma engine with read-only shared market metadata."""
from __future__ import annotations

import os
import hashlib
import json
from datetime import datetime, date
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import plotly.graph_objects as go
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from edge_clone_engine import MODES, analyze
from edge_storage import StorageReadError
from edge_archive import login_reader, renew_reader, latest_snapshot, download_snapshot, snapshots_for_day
from edge_verification import verify_snapshot
from edge_futures import BasisUnavailable, parse_basis, rounded_basis
from edge_shared_basis import read_shared_basis
from edge_market import MarketUnavailable, cached_market
from edge_charts import candles_gex_figure

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
                'edge_archive_fetched', 'edge_archive_analysis', 'edge_raw',
                'edge_archive_selection', 'edge_archive_mode',
                'edge_archive_selected_day', 'edge_archive_selected_snapshot',
                'edge_chart_zoom', 'edge_price_view'):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith(('edge_basis_', 'edge_market_')):
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
    # Everyday operation always reads the archive; manual/test modes remain
    # available only on demand, without cluttering the daily interface.
    config = archive_configuration()
    with st.expander("Strumenti avanzati · caricamento e test", expanded=False):
        alternative = st.radio(
            "Sorgente alternativa", ("Archivio automatico", UPLOAD, DEMO),
            horizontal=True, key="edge_advanced_source",
        )
        if alternative == UPLOAD:
            uploaded = st.file_uploader("Fotografia originale CBOE (.json o .json.gz)", type=("json", "gz"))
            return (uploaded.getvalue() if uploaded else None), False
        if alternative == DEMO:
            st.warning("ESEMPIO SINTETICO: dati creati per test, non una fotografia reale CBOE.")
            return (ROOT / "fixtures/synthetic_cboe_spx.json").read_bytes(), True
    if config is None:
        st.info("Archivio privato non configurato; usare gli strumenti avanzati per caricare un file.")
        return None, False
    automatic_archive(mode)
    return None, None


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
    return {'unit': 'ES_equivalent', 'offset': offset, 'target_date': day,
            'source': estimate['source'] if automatic else 'Differenziale verificato inserito dall’utente',
            'reference_date': estimate['reference_date'] if automatic else None,
            'automatic_estimate': estimate}


def chart_market(result, conversion, target, synthetic, historical):
    if synthetic:
        return None, 'Esempio sintetico: nessuna candela reale'
    symbol = 'ES=F' if conversion['unit']=='ES_equivalent' else '^GSPC' if result['symbol']=='SPX' else '^NDX'
    day = target if historical else None
    cache_key = (symbol,day.isoformat() if day is not None else 'latest')
    records = st.session_state.setdefault('edge_market_records',{})
    record = records.setdefault(cache_key,{'at':None,'market':None,'error':''})
    refresh = st.button('Rileggi candele e prezzo',key='edge_market_refresh')
    current = time.monotonic()
    ttl = 3600 if historical and target<datetime.now(ZoneInfo('Europe/Rome')).date() else 110
    if record['error']:
        ttl = 30
    if refresh or record['at'] is None or current-record['at']>=ttl:
        try:
            if refresh:
                cached_market.clear(symbol,day)
            market,error = cached_market(symbol,day)
            if market is None:
                raise MarketUnavailable(error)
            record.update(market=market,error='')
        except MarketUnavailable as error:
            record['error'] = str(error)
        record['at'] = current
    market = record['market']
    if historical:
        st.caption(f"Candele della giornata selezionata: {target:%d/%m/%Y} (Italia). La vista può includere barre successive alla fotografia; non è una simulazione limitata all’ora di acquisizione.")
    if market is None:
        st.caption('Candele/prezzo non disponibili da Yahoo. '+record['error'])
        detail = record['error'].replace(' (','<br>(').replace('; ','<br>')
        return None, 'Candele non disponibili<br>'+detail+'<br>Premi «Rileggi candele e prezzo» per riprovare'
    if record['error']:
        st.warning('Aggiornamento prezzi non riuscito. Mostro gli ultimi dati letti in questa sessione, non aggiornati. '+record['error'])
    label = 'Ultima chiusura 5m disponibile' if market['kind']=='closed_bar' else 'Ultima quotazione disponibile'
    st.caption(f"{symbol} · {label}: {market['price']:,.2f} · {italian_time(market['timestamp'])} · Yahoo Finance")
    age = max(0,int(time.time()-datetime.fromisoformat(market['timestamp']).timestamp()))
    if not historical and age>1200:
        st.warning('Quotazione datata: controlla l’orario. Lo spot della fotografia resta un riferimento storico.')
    if not historical and datetime.fromisoformat(market['timestamp']).astimezone(ZoneInfo('Europe/Rome')).date()!=target:
        st.warning('Candele e fotografia riguardano giornate diverse: i livelli restano quelli della fotografia selezionata.')
    delay = market['delay_minutes']
    st.caption(f'Ritardo dichiarato dalla fonte: {delay:g} min.' if delay is not None else 'Ritardo non dichiarato dalla fonte; dati senza garanzia di tempo reale.')
    st.caption('Lettura prezzi pubblici condivisa per 5 minuti. «Rileggi candele e prezzo» forza un nuovo tentativo.')
    return market, None


def render_result(result, synthetic=False, basis_target=None, archive_context=None, historical=False):
    if synthetic:
        st.caption("Risultati su esempio sintetico; nessuna verifica su dati reali.")

    target = basis_target or datetime.fromisoformat(result['timestamp']).date()
    conversion = price_conversion(result, synthetic, target, archive_context)
    offset = conversion['offset']
    shift = offset if offset is not None else 0
    translated = offset is not None
    suffix = ' ES' if translated else ' ' + result['symbol']
    def price(value):
        return None if value is None else value + shift
    st.markdown(f"**Timestamp del dato CBOE (interpretato come UTC): {italian_time(result['timestamp'])}**")
    if archive_context is not None:
        st.caption("L'orario di acquisizione/download è distinto dal timestamp del dato: per la fotografia delle 07:30 verificarlo nel registro di acquisizione Serafini. Non viene dedotto dal nome file.")
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
        view = st.radio(
            "Ampiezza grafico", ("Zoom operativo", "Vista completa"),
            horizontal=True, key="edge_chart_zoom",
        )
        market, unavailable = chart_market(result,conversion,target,synthetic,
                                            historical or archive_context is None)
        chart = candles_gex_figure(result,shift,market,full=view=="Vista completa",empty_message=unavailable)
        chart.update_yaxes(title="Prezzo ES" if translated else "Prezzo " + result['symbol'],row=1,col=1)
        st.caption(f"Profilo {', '.join(result['expiries'])} · {('0DTE' if len(result['expiries']) == 1 else 'scadenze multiple')} · "
                   "prezzi allineati verticalmente; Call verdi, Put rosse, NET rosa. Il prezzo delle candele non modifica i calcoli GEX.")
        st.caption('Zoom operativo: candele e livelli vicini al prezzo. Vista completa: tutti gli strike del profilo. Puoi ingrandire una zona trascinando sul grafico.')
        st.plotly_chart(chart, width="stretch",key="edge_candles_gex")
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
        # Portable Edge result for the external, read-only Serafini comparison panel.
        # No Edge calculation is rerun in the Serafini application.
        if not synthetic:
            edge_transfer = {
                "schema": "edge-gex-context-v1", "source": "Edge GEX Lab",
                "symbol": result["symbol"], "mode": result["mode"],
                "timestamp": result["timestamp"], "valuation": result["valuation"],
                "sha256": result["sha256"], "expiries": result["expiries"],
                "spot_spx": result["spot"], "es_basis": offset,
                "spot_es": price(result["spot"]) if translated else None,
                "call_wall_spx": result["call_wall"],
                "put_wall_spx": result["put_wall"], "gamma_flip_spx": result["flip"],
                "call_wall_es": price(result["call_wall"]) if translated else None,
                "put_wall_es": price(result["put_wall"]) if translated else None,
                "gamma_flip_es": price(result["flip"]) if translated else None,
                "net_gex": result["net"], "gross_gex": result["gross"],
                "regime": result["regime"], "quality_pct": result["quality_pct"],
                "rows": [
                    {"strike_spx": float(row["strike"]), "call_gex": float(row["call_gex"]),
                     "put_gex": float(row["put_gex"]), "net_gex": float(row["net_gex"])}
                    for _, row in frame.iterrows()
                ],
                "curve": [
                    {"spot_spx": float(row["spot"]), "net_gex": float(row["net_gex"])}
                    for _, row in result["curve"].iterrows()
                ],
            }
            st.download_button(
                "Scarica confronto Edge per SPX (JSON)",
                data=json.dumps(edge_transfer, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                file_name=f"EDGE_Confronto_{result['sha256'][:12]}.json",
                mime="application/json", key="edge_compare_export",
            )
    else:
        st.info("Nessuno strike nella fascia del grafico; i totali includono comunque la catena selezionata.")
    st.caption("Grafico e wall: strike entro ±10% dallo spot. Totali e curva ipotetica: contratti selezionati acquisiti entro ±20%.")
    with st.expander("Curva ipotetica e tutti i gamma flip"):
        curve = result["curve"]
        if not curve.empty:
            maximum = curve.loc[curve["net_gex"].idxmax()]
            minimum = curve.loc[curve["net_gex"].idxmin()]
            st.markdown(
                f"**Curva teorica GEX {result['mode']} — fotografia Cboe ore {italian_time(result['timestamp'])[11:16]} Roma** · "
                f"Max **{maximum['net_gex']/1e9:+.2f} mld** (ES {maximum['spot']+shift:,.2f}) · "
                f"Min **{minimum['net_gex']/1e9:+.2f} mld** (ES {minimum['spot']+shift:,.2f})"
            )
        chart = go.Figure(go.Scatter(x=curve["spot"] + shift, y=curve["net_gex"] / 1e9, mode="lines", name="NET GEX ipotetico"))
        chart.add_hline(y=0, line_dash="dash", line_color="#d9b44a", line_width=1.5)
        chart.update_yaxes(zeroline=False)
        chart.update_layout(xaxis_title="Prezzo ES equivalente" if translated else "Spot ipotetico " + result['symbol'], yaxis_title=f"GEX {result['symbol']} · miliardi USD/1%")
        st.plotly_chart(chart, width="stretch")
        st.write("Attraversamenti dello zero" + suffix + ":", [price(value) for value in result['flips']] or "Nessun attraversamento nella finestra Edge")
        st.markdown(
            """
**Come leggere la curva teorica GEX**

**A cosa serve?** Se l'SPX raggiungesse un determinato prezzo, come cambierebbe l'esposizione Gamma complessiva delle opzioni 0DTE considerate? La curva mostra il GEX ricalcolato per diversi prezzi ipotetici partendo dalla stessa fotografia Cboe, senza ipotizzare nuove operazioni o variazioni delle posizioni aperte.

**Sopra lo zero (GEX positivo):** in determinate condizioni, le coperture dei dealer possono contrastare i movimenti del prezzo, favorendo una maggiore stabilità. **Sotto lo zero (GEX negativo):** le coperture possono invece amplificare i movimenti e la volatilità.

**Il passaggio attraverso lo zero** identifica un Gamma Flip teorico. La curva non prevede la direzione del mercato e non costituisce un segnale automatico di acquisto o vendita.
            """
        )
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
    session = st.session_state.get('edge_reader_session')
    if config is None or session is None:
        st.stop()
    project, key, user_id = config
    try:
        session = renew_reader(project, key, session, user_id)
        st.session_state['edge_reader_session'] = session
    except StorageReadError:
        clear_private_session()
        st.rerun(scope="app")
    archive_mode = st.radio(
        'Fotografia da analizzare', ('Ultimo rilevamento disponibile', 'Altro rilevamento storico'),
        horizontal=True, key='edge_archive_mode',
    )
    selected_reference = None
    if archive_mode == 'Altro rilevamento storico':
        selected_day = st.date_input(
            'Data della fotografia originale', value=date.today(),
            min_value=date(2026, 10, 1), max_value=date.today(),
            key='edge_archive_selected_day',
        )
        try:
            available = snapshots_for_day(project, key, session, selected_day)
            if not available:
                st.info('Nessuna fotografia SPX originale disponibile per questa data. Scegli un altro giorno.')
                return
            names = {ref.path.rsplit('/', 1)[-1]: ref for ref in available}
            def snapshot_display(name):
                # Timestamp from the CBOE filename, interpreted as UTC like the
                # Edge source timestamp. It is NOT the archive download time.
                try:
                    source_time=datetime.strptime(name[9:24],'%Y%m%d_%H%M%S').replace(tzinfo=ZoneInfo('UTC'))
                    local=source_time.astimezone(ZoneInfo('Europe/Rome'))
                    return f"{local:%H:%M} Roma (dato CBOE, NON download) · {name}"
                except (ValueError,IndexError):
                    return f"Orario non identificato · {name}"
            chosen = st.selectbox(
                'Fotografia CBOE · orario del dato in Italia (NON del download)',
                list(names), index=len(names)-1, format_func=snapshot_display,
                key='edge_archive_selected_snapshot',
            )
            selected_reference = names[chosen]
            st.caption('Esempio: 19:30 UTC del 28/10 equivale a 20:30 Roma. L’orario reale di acquisizione va verificato nel registro Serafini; il nome file non lo certifica.')
            st.caption('La fotografia è letta dal medesimo archivio privato di Serafini; i calcoli restano esclusivamente Edge.')
        except StorageReadError as error:
            st.error(str(error))
            return
    force = False  # Aggiornamento automatico, senza pulsante manuale.
    now = time.monotonic()
    fetched = st.session_state.get('edge_archive_fetched', 0)
    try:
        if archive_mode == 'Ultimo rilevamento disponibile':
            refresh_due = force or 'edge_archive_raw' not in st.session_state or now - fetched >= 110 or st.session_state.get('edge_archive_selection') != 'latest'
            if refresh_due:
                reference = latest_snapshot(project, key, session)
                if reference != st.session_state.get('edge_archive_ref') or 'edge_archive_raw' not in st.session_state:
                    raw = download_snapshot(project, key, session, reference)
                    st.session_state['edge_archive_raw'] = raw
                    st.session_state['edge_archive_ref'] = reference
                st.session_state['edge_archive_fetched'] = now
                st.session_state['edge_archive_selection'] = 'latest'
        else:
            reference = selected_reference
            if force or reference != st.session_state.get('edge_archive_ref') or 'edge_archive_raw' not in st.session_state or st.session_state.get('edge_archive_selection') != reference.path:
                st.session_state['edge_archive_raw'] = download_snapshot(project, key, session, reference)
                st.session_state['edge_archive_ref'] = reference
                st.session_state['edge_archive_selection'] = reference.path
                st.session_state['edge_archive_fetched'] = now
        reference = st.session_state['edge_archive_ref']
        # Readable selection summary: source CBOE clock is distinct from actual download.
        file_name = reference.path.rsplit('/', 1)[-1]
        try:
            source_stamp = datetime.strptime(file_name[9:24], '%Y%m%d_%H%M%S').replace(tzinfo=ZoneInfo('UTC'))
            source_rome = source_stamp.astimezone(ZoneInfo('Europe/Rome'))
            selected_day_label = source_rome.strftime('%d/%m/%Y')
            source_time_label = source_rome.strftime('%H:%M:%S')
        except (ValueError, IndexError):
            selected_day_label = 'Non disponibile'
            source_time_label = 'Non disponibile'
        st.markdown('#### Fotografia in analisi')
        overview = st.columns([1.2, 1, 1.8])
        overview[0].metric('Data del dato CBOE', selected_day_label)
        overview[1].metric('Ora dato CBOE · Roma', source_time_label)
        overview[2].metric('Selezione', 'Ultimo rilevamento disponibile' if archive_mode == 'Ultimo rilevamento disponibile' else 'Storica selezionata')
        st.caption(
            'L’orario mostrato si riferisce al dato CBOE (interpretato come UTC), '
            'non all’effettivo download. Quest’ultimo viene verificato separatamente nei registri Serafini.'
        )
        with st.expander('Dettagli fotografia e aggiornamento', expanded=False):
            st.code(file_name, language=None)
            st.caption('Percorso archivio: ' + reference.path)
            st.caption(
                'Controllo della fotografia più recente ogni 2 minuti a pagina aperta.'
                if archive_mode == 'Ultimo rilevamento disponibile'
                else 'Fotografia storica fissata: non viene sostituita automaticamente.'
            )
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
        st.caption(f"✓ Verifica aritmetica superata · {report['contracts_cross_checked']} contratti · NET e Gross GEX riconciliati")
        target = datetime.strptime(reference.path.rsplit('/', 1)[-1][9:17], '%Y%m%d').date()
        conversion = render_result(result, basis_target=target, archive_context=(project, key, session),
                                   historical=archive_mode=='Altro rilevamento storico')
        # Download the exact, unmodified private snapshot used by this analysis.
        original_name = reference.path.rsplit('/', 1)[-1]
        st.download_button(
            "Scarica fotografia originale CBOE",
            data=raw,
            file_name=original_name,
            mime="application/gzip" if original_name.endswith(".gz") else "application/json",
            key="edge_original_snapshot_download",
            on_click="ignore",
        )
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
    # Authentication gate: no trading controls, file upload or charts before login.
    config = archive_configuration()
    if config is not None:
        session = private_session(config)
        if session is None:
            st.stop()
    st.warning("Analisi modellata per ricerca. Posizioni dealer non osservabili; fotografie e open interest possono essere ritardati.")
    mode = st.selectbox("Scadenze da analizzare", MODES, index=0)
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
