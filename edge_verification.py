"""Independent scalar arithmetic cross-check of the upstream Edge gamma/GEX.

Reuses the adapter's contract selection and valuation, not its gamma implementation.
This checks model arithmetic, not the authenticity of the data or dealer positioning.
"""
import math

from edge_clone_engine import analyze, prepare_contracts


def verify_snapshot(raw, mode="Prossime 4 scadenze"):
    result = analyze(raw, mode)
    chain, contracts, _ = prepare_contracts(raw, mode)
    signed, gross = [], []
    for contract in contracts:
        if not contract.valid:
            continue
        scale = contract.iv * math.sqrt(contract.T)
        z = math.log(chain.spot.price / contract.strike) / scale + scale / 2
        gamma = math.exp(-z * z / 2) / (math.sqrt(2 * math.pi) * chain.spot.price * scale)
        reference = gamma * contract.oi * contract.multiplier * chain.spot.price**2 / 100
        if contract.type == "put":
            reference = -reference
        if not math.isclose(contract.gex, reference, rel_tol=1e-10, abs_tol=1e-6):
            raise ValueError("GEX di un contratto diverso dal riferimento scalare indipendente.")
        signed.append(reference)
        gross.append(abs(reference))
    net, total = math.fsum(signed), math.fsum(gross)
    if not math.isclose(result["net"], net, rel_tol=1e-10, abs_tol=1e-5):
        raise ValueError("NET GEX non riconciliato.")
    if not math.isclose(result["gross"], total, rel_tol=1e-10, abs_tol=1e-5):
        raise ValueError("Gross GEX non riconciliato.")
    keys = ("symbol", "timestamp", "valuation", "spot", "mode", "expiries", "sha256", "model_version",
            "calendar_source", "oi_date", "valid", "total", "call_wall", "put_wall", "flip",
            "flips", "net", "gross", "quality_pct")
    report = {key: result[key] for key in keys}
    report.update({"arithmetic_check": "passed", "contracts_cross_checked": len(signed),
                   "independent_net_gex": net, "independent_gross_gex": total,
                   "data_authenticity": "not established by this arithmetic check",
                   "calendar_note": "Offline XNYS session proxy, not an official CBOE settlement calendar"})
    return report
