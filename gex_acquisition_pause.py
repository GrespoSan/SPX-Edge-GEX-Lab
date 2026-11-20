"""Temporary suspension of NEW Edge GEX Lab market-data acquisitions.

Requested 20 November 2026. Do not query Cboe or Alpaca for new GEX
chains, either from Streamlit, FastAPI, or the recorder. Existing archived
Cboe snapshots and user-supplied files remain readable for historical use.

Intentionally fixed in source code: no environment-variable or UI bypass.
"""
GEX_ACQUISITIONS_PAUSED = True
PAUSE_MESSAGE = (
    "Acquisizioni GEX sospese dal 20/11/2026: "
    "nessun nuovo download Cboe/Alpaca, manuale o automatico. "
    "Restano consultabili gli archivi e i file importati."
)


def require_gex_acquisition_enabled():
    """Fail closed before requesting or refreshing any GEX option chain."""
    if GEX_ACQUISITIONS_PAUSED:
        raise RuntimeError(PAUSE_MESSAGE)
