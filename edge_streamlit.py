"""Independent, archive-only Streamlit application. No Serafini integration."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from edge_clone_engine import MODES, analyze
from edge_storage import StorageReadError, read_object, read_signed_snapshot

ROOT = Path(__file__).resolve().parent
UPLOAD = "Carica fotografia CBOE"
STORAGE = "Oggetto Supabase privato"
SIGNED = "Fotografia con URL firmato"
DEMO = "Esempio sintetico (test)"


def setting(name, default=""):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except StreamlitSecretNotFoundError:
        return os.environ.get(name, default)


def confirmed(name):
    return str(setting(name, False)).lower() == "true"


def source_data():
    source = st.radio("Sorgente dati", (UPLOAD, STORAGE, SIGNED, DEMO), horizontal=True)
    # Store private data only in this session, never in a cross-user cache.
    project = setting("SUPABASE_URL")
    signed = setting("SUPABASE_SNAPSHOT_SIGNED_URL")
    api_key = setting("SUPABASE_ANON_KEY")
    token = setting("SUPABASE_READ_TOKEN")
    path = ""
    if source == STORAGE:
        st.caption("Inserisci il percorso di un oggetto già archiviato in spx-snapshots. Nessuna scrittura o modifica alle policy.")
        path = st.text_input("Percorso fotografia nel bucket", placeholder="cartella/SPX_CBOE_fotografia.json.gz")
    identity = hashlib.sha256(repr((source, path, project, signed, api_key, token,
                                   confirmed("SUPABASE_READ_ONLY_CONFIRMED"))).encode()).hexdigest()
    if st.session_state.get("edge_source_identity") != identity:
        st.session_state.pop("edge_raw", None)
        st.session_state["edge_source_identity"] = identity
    if source == UPLOAD:
        uploaded = st.file_uploader("Fotografia originale CBOE (.json o .json.gz)", type=("json", "gz"))
        return (uploaded.getvalue() if uploaded else None), False
    if source == DEMO:
        st.warning("ESEMPIO SINTETICO: dati creati per test, non una fotografia reale CBOE.")
        return (ROOT / "fixtures/synthetic_cboe_spx.json").read_bytes(), True
    if source == STORAGE:
        if not project or not api_key or not token or not confirmed("SUPABASE_READ_ONLY_CONFIRMED"):
            st.info("Accesso non configurato. Servono URL del progetto, chiave anon/publishable, identità già limitata alla lettura e conferma del proprietario nei Secrets. È disponibile il caricamento file.")
            return None, False
        ready = bool(path)
    else:
        if not signed:
            st.info("Configura nei Secrets un URL firmato già emesso per la fotografia. Non inserire chiavi amministrative.")
            return None, False
        ready = True
    if st.button("Leggi fotografia", type="primary", disabled=not ready):
        st.session_state.pop("edge_raw", None)
        try:
            if source == STORAGE:
                raw = read_object(project, path, api_key, token, read_only_confirmed=True)
            else:
                raw = read_signed_snapshot(signed, project_url=project)
            st.session_state["edge_raw"] = raw
        except StorageReadError as error:
            st.error(str(error))
        except Exception:
            st.error("Lettura non disponibile. Dettagli di connessione e credenziali omessi.")
    return st.session_state.get("edge_raw"), False


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


def main():
    st.set_page_config(page_title="SPX Edge GEX Lab", layout="wide")
    st.title("SPX · Edge GEX Lab")
    st.caption("Applicazione indipendente · fotografie CBOE in sola lettura")
    st.warning("Analisi modellata per ricerca. Posizioni dealer non osservabili; fotografie e open interest possono essere ritardati.")
    mode = st.selectbox("Scadenze da analizzare", MODES, index=1)
    raw, synthetic = source_data()
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
