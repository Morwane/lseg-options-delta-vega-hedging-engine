import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import lseg.data as ld

OUT = Path("outputs/audits") / f"lseg_options_access_{datetime.now():%Y%m%d_%H%M%S}"
OUT.mkdir(parents=True, exist_ok=True)

UNDERLYINGS = {
    "SPY": ["SPY", "SPY.N", "SPY.P", "SPY.A"],
    "QQQ": ["QQQ.O", "QQQ", "QQQ.OQ"],
    "TLT": ["TLT.O", "TLT", "TLT.OQ"],
    "GLD": ["GLD", "GLD.P", "GLD.N", "GLD.A"],
}

# Fields deliberately broad: some may fail depending on entitlements.
OPTION_FIELD_CANDIDATES = [
    "TRDPRC_1",
    "CLOSE",
    "CF_CLOSE",
    "BID",
    "ASK",
    "TR.BIDPRICE",
    "TR.ASKPRICE",
    "TR.CLOSEPRICE",
    "TR.PriceClose",
    "TR.ImpliedVolatility",
    "TR.IV",
    "TR.Delta",
    "TR.Gamma",
    "TR.Vega",
    "TR.Theta",
]

def try_history(ric: str, field: str) -> dict:
    try:
        df = ld.get_history(
            universe=[ric],
            fields=[field],
            interval="daily",
            count=5,
        )
        ok = df is not None and not df.empty
        return {
            "ric": ric,
            "field": field,
            "status": "OK" if ok else "EMPTY",
            "rows": 0 if df is None else len(df),
            "columns": [] if df is None else [str(c) for c in df.columns],
            "error": "",
        }
    except Exception as e:
        return {
            "ric": ric,
            "field": field,
            "status": "ERROR",
            "rows": 0,
            "columns": [],
            "error": str(e)[:300],
        }

def main():
    print("Opening LSEG session...")
    ld.open_session()
    print("LSEG session opened.")

    rows = []

    print("\n=== UNDERLYING FIELD AUDIT ===")
    for name, candidates in UNDERLYINGS.items():
        print(f"\n--- {name} ---")
        for ric in candidates:
            result = try_history(ric, "TRDPRC_1")
            rows.append({"asset": name, "test_type": "underlying_price", **result})
            print(f"{ric} TRDPRC_1 -> {result['status']} rows={result['rows']}")
            if result["status"] == "OK":
                break

    print("\n=== OPTION FIELD NAME AUDIT ===")
    print("This does NOT discover option RICs yet.")
    print("It only checks which option-style field names are recognized by your LSEG session.")

    # Use underlying RICs as a safe field-recognition probe.
    # If fields error here, they may still work only on option RICs, but this gives a first entitlement map.
    probe_ric = "SPY"

    for field in OPTION_FIELD_CANDIDATES:
        result = try_history(probe_ric, field)
        rows.append({"asset": "SPY", "test_type": "field_probe_on_underlying", **result})
        print(f"{field} -> {result['status']} rows={result['rows']}")

    df = pd.DataFrame(rows)
    csv_path = OUT / "lseg_options_access_audit.csv"
    json_path = OUT / "manifest.json"

    df.to_csv(csv_path, index=False)

    manifest = {
        "timestamp": datetime.now().isoformat(),
        "purpose": "Audit LSEG access for underlying prices and option-style fields for Automatic Delta Hedging with IBKR API.",
        "status_counts": df["status"].value_counts().to_dict() if not df.empty else {},
        "output_csv": str(csv_path),
        "note": (
            "This audit confirms underlying access and probes option-style field names. "
            "Exact option RIC discovery may require a separate chain/discovery API or known option RICs."
        ),
    }

    with open(json_path, "w") as f:
        json.dump(manifest, f, indent=2)

    try:
        ld.close_session()
    except Exception:
        pass

    print(f"\nSaved CSV: {csv_path}")
    print(f"Saved manifest: {json_path}")
    print("\nDONE")

if __name__ == "__main__":
    main()
