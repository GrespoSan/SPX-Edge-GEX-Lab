"""Independent research-only study of theoretical GEX curve peaks.

Only uses existing Edge outputs. The market comparison is conditional on an
explicit independently verified acquisition clock, never the CBOE source timestamp.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import math
import time
import pandas as pd
import streamlit as st
from edge_market import cached_market
from edge_archive import snapshot_acquisition

ROME=ZoneInfo("Europe/Rome")

def extract_peaks(result, shift):
    curve=result.get("curve")
    if curve is None or curve.empty:
        return []
    data=curve.loc[:,["spot","net_gex"]].copy()
    data["spot"]=pd.to_numeric(data["spot"],errors="coerce")
    data["net_gex"]=pd.to_numeric(data["net_gex"],errors="coerce")
    data=data.replace([float("inf"),-float("inf")],float("nan")).dropna()
    if data.empty:
        return []
    high=data.loc[data["net_gex"].idxmax()]
    low=data.loc[data["net_gex"].idxmin()]
    return [
        {"type":"Massimo NET GEX", "level":float(high["spot"])+shift, "value":float(high["net_gex"])/1e9},
        {"type":"Minimo NET GEX", "level":float(low["spot"])+shift, "value":float(low["net_gex"])/1e9},
    ]

def forward_test(candles, acquisition, level, tolerance=5.0, bounce=10.0):
    """First post-acquisition touch, then a 30-minute directional rejection.
    A rejection is counted only if the opposing excursion reaches bounce before
    a breakout of at least bounce. An ambiguous same-bar contest is unresolved.
    """
    after=candles.loc[candles["time"]>acquisition].copy()
    if after.empty:
        return {"status":"Senza candele successive","min_distance":None}
    after=after.loc[after["time"]<=acquisition+timedelta(hours=3)]
    if after.empty:
        return {"status":"Orizzonte non coperto","min_distance":None}
    distance=(after["low"]-level).clip(lower=0)+(level-after["high"]).clip(lower=0)
    touch=distance<=tolerance
    if not touch.any():
        complete=after["time"].max()>=acquisition+timedelta(hours=3)
        return {"status":"Non raggiunto in 3 ore" if complete else "Finestra incompleta: nessun contatto finora",
                "min_distance":float(distance.min())}
    first=after.loc[touch].iloc[0]
    subsequent=after.loc[(after["time"]>=first["time"])&(after["time"]<=first["time"]+timedelta(minutes=30))]
    # No direction assumed from peak: examine both an upper and lower rejection.
    came_from_below=float(after.iloc[0]["close"])<level
    if came_from_below:
        reversal=(subsequent["low"]<=level-bounce).any()
        breakout=(subsequent["high"]>=level+bounce).any()
    else:
        reversal=(subsequent["high"]>=level+bounce).any()
        breakout=(subsequent["low"]<=level-bounce).any()
    complete_reaction=subsequent["time"].max()>=first["time"]+timedelta(minutes=30)
    if reversal and breakout:
        status="Ambiguo: entrambi i movimenti"
    elif reversal:
        status="Reazione candidata (ordine intrabar non verificato)"
    elif breakout:
        status="Attraversamento"
    else:
        status="Nessuna reazione di 10 punti confermata" if complete_reaction else "30 minuti successivi non ancora disponibili"
    return {"status":status, "min_distance":float(distance.min()),
            "first_touch":first["time"].astimezone(ROME).strftime("%H:%M")}

def render(result, offset, selected_day, archive_context=None):
    if result.get("mode")!="0DTE":
        return
    with st.expander("GEX Peak Monitor · studio sperimentale",expanded=False):
        st.caption("Massimi e minimi della curva teorica Edge: NON sono Call Wall/Put Wall e non costituiscono segnali.")
        if offset is None:
            st.warning("Differenziale ES−SPX non disponibile: studio dei prezzi ES non possibile.")
            return
        peaks=extract_peaks(result,float(offset))
        if not peaks:
            st.info("Curva teorica non disponibile.")
            return
        cols=st.columns(2)
        for c,p in zip(cols,peaks):
            c.metric(p["type"]+" · ES",f"{p['level']:,.2f}",f"{p['value']:+.2f} mld USD/1%",delta_color="off")
        st.caption("I picchi sono calcolati sulla fotografia selezionata, senza utilizzare prezzi successivi. L'ora CBOE non dimostra l'ora di effettiva disponibilità.")
        ref=st.session_state.get("edge_archive_ref") if archive_context else None
        name=ref.path.rsplit("/",1)[-1] if ref else "file caricato manualmente"
        st.markdown(f"**Fotografia analizzata:** `{name}`")
        source_stamp=datetime.fromisoformat(result["timestamp"].replace("Z","+00:00"))
        if source_stamp.tzinfo is not None:
            st.caption(f"Ora del dato CBOE (interpretata come UTC): {source_stamp.astimezone(ROME):%d/%m/%Y %H:%M:%S} Roma")
        when=None
        if archive_context and ref:
            project,key,session=archive_context
            cache_key=("peak_acquisition",ref.path,session.user_id)
            cached=st.session_state.get(cache_key)
            if cached and time.monotonic()-cached[0]<300:
                when=cached[1]
            else:
                when=snapshot_acquisition(project,key,session,ref)
                st.session_state[cache_key]=(time.monotonic(),when)
        if when is None:
            st.warning("Ora effettiva del download non verificabile nei registri Serafini: test successivo disabilitato. Il timestamp CBOE non è usato come sostituto.")
            return
        st.success(f"Acquisizione verificata dal registro Serafini: {when:%d/%m/%Y %H:%M:%S} Roma")
        st.markdown("**Verifica successiva sui prezzi ES**")
        now=datetime.now(ROME)
        if when>now:
            st.warning("Fotografia futura: nessun confronto possibile.");return
        market,error=cached_market("ES=F",selected_day)
        if market is None or market["candles"].empty:
            st.warning("Candele Yahoo 5m non disponibili: "+error);return
        prices=market["candles"]
        if prices["time"].max()<when+timedelta(minutes=35):
            st.warning("Non sono ancora disponibili 30 minuti di candele successive alla fotografia.")
        rows=[]
        for p in peaks:
            t=forward_test(prices,when,p["level"])
            rows.append({"Fotografia":result["sha256"][:12], "Data":selected_day.isoformat(),
                         "Download Roma verificato":when.isoformat(),"Picco":p["type"],
                         "Livello ES":round(p["level"],2),"GEX mld":round(p["value"],2),
                         "Distanza minima (punti)":None if t["min_distance"] is None else round(t["min_distance"],2),
                         "Primo contatto":t.get("first_touch","—"),"Esito":t["status"]})
        st.dataframe(rows,use_container_width=True,hide_index=True)
        st.download_button("Esporta osservazione Peak Monitor (CSV)",
                           pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"Edge_Peak_{selected_day:%Y%m%d}_{result['sha256'][:8]}.csv",
                           mime="text/csv",key="edge_peak_export")
        st.caption("Criterio preliminare: contatto entro 5 punti nelle 3 ore successive; reazione di 10 punti entro 30 minuti. Il solo OHLC 5m non può certificare l'ordine intrabar. Da confrontare in seguito con Call Wall, Put Wall e livelli di controllo.")
