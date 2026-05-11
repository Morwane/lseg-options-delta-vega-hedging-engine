"""Regenerate all data and charts for the README.

Usage
-----
python scripts/build_readme_outputs.py

Steps
-----
1. Regenerate backtest CSVs via run_real_lseg_historical_hedge_backtest.py --mock.
2. Regenerate demo portfolio CSVs via run_demo.py.
3. Build all charts from outputs/reports/ into docs/images/.
4. Print a summary of created files.

Requires no live IBKR or LSEG connection — uses synthetic mock data.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_REPORTS = ROOT / "outputs" / "reports"
_IMAGES  = ROOT / "docs" / "images"
_PYTHON  = sys.executable


def _run(cmd: list[str]) -> int:
    print(f"\n[RUN] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"  [WARN] exited with code {result.returncode}")
    return result.returncode


def main() -> int:
    print("=" * 64)
    print("build_readme_outputs — regenerating data and charts")
    print("=" * 64)

    # Step 1: backtest CSVs (mock)
    _run([
        _PYTHON,
        str(ROOT / "scripts" / "run_real_lseg_historical_hedge_backtest.py"),
        "--mock",
        "--output-dir", str(_REPORTS),
    ])

    # Step 2: demo portfolio CSVs
    _run([_PYTHON, str(ROOT / "scripts" / "run_demo.py")])

    # Step 3: charts
    print("\n[CHARTS] Building charts …")
    from src.reporting.charts import build_all_charts
    created = build_all_charts(_REPORTS, _IMAGES)

    # Summary
    print(f"\n{'=' * 64}")
    print("DONE")
    print(f"{'=' * 64}")
    print(f"  Reports dir : {_REPORTS}")
    print(f"  Images dir  : {_IMAGES}")
    print(f"  Charts built: {len(created)}")
    for p in created:
        print(f"    {Path(p).name}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
