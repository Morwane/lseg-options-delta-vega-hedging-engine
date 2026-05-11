import json
from datetime import datetime
from pathlib import Path

import lseg.data as ld

OUT = Path("outputs/audits") / f"lseg_connection_{datetime.now():%Y%m%d_%H%M%S}"
OUT.mkdir(parents=True, exist_ok=True)

manifest = {
    "timestamp": datetime.now().isoformat(),
    "status": "UNKNOWN",
    "errors": [],
}

try:
    print("Opening LSEG session...")
    ld.open_session()

    print("LSEG session opened.")

    instruments = [".SPX", "SPY", "QQQ.O", "TLT.O", "GLD"]
    fields = ["TRDPRC_1", "CLOSE"]

    results = []

    for ric in instruments:
        print(f"\nTesting {ric}...")
        for field in fields:
            try:
                df = ld.get_history(
                    universe=[ric],
                    fields=[field],
                    interval="daily",
                    count=5,
                )
                ok = df is not None and not df.empty
                print(f"  {field}: {'OK' if ok else 'EMPTY'}")
                results.append(
                    {
                        "ric": ric,
                        "field": field,
                        "status": "OK" if ok else "EMPTY",
                        "rows": 0 if df is None else len(df),
                    }
                )
                if ok:
                    break
            except Exception as e:
                print(f"  {field}: ERROR {e}")
                results.append(
                    {
                        "ric": ric,
                        "field": field,
                        "status": "ERROR",
                        "error": str(e),
                    }
                )

    manifest["status"] = "OK"
    manifest["results"] = results

except Exception as e:
    print("LSEG ERROR:", e)
    manifest["status"] = "ERROR"
    manifest["errors"].append(str(e))

finally:
    try:
        ld.close_session()
    except Exception:
        pass

    with open(OUT / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nAudit saved to: {OUT}")
