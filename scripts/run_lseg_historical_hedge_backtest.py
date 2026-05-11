"""Run the LSEG Historical Delta-Hedging Backtest.

Loads LSEG option bid/ask history and SPY spot history, runs the delta-hedging
backtest engine, and writes standardised output files.

Output files (in --output-dir, default: outputs/reports/):
    lseg_historical_daily_pnl.csv
    lseg_historical_hedge_orders.csv
    lseg_historical_exposures.csv
    lseg_historical_summary.csv
    lseg_historical_data_quality.csv
    real_lseg_hedge_validation.md

No IBKR connection is used. All Greeks are Black-Scholes from LSEG market mid.

Usage
-----
# Offline / CI (synthetic mock data — no LSEG required):
python scripts/run_lseg_historical_hedge_backtest.py --mock

# Live LSEG:
python scripts/run_lseg_historical_hedge_backtest.py

# Custom output:
python scripts/run_lseg_historical_hedge_backtest.py --mock --output-dir /tmp/bt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backtesting.lseg_historical_hedge_backtest import (
    print_lseg_backtest_summary,
    run_lseg_backtest,
    save_lseg_backtest_outputs,
)
from src.backtesting.historical_delta_hedge_engine import load_backtest_config
from src.data.lseg_option_loader import LsegLoaderConfig, load_lseg_option_data


DEFAULT_CONFIG = ROOT / "config" / "historical_backtest.yaml"
DEFAULT_RIC_CONFIG = ROOT / "config" / "lseg_option_coverage_rics.yaml"
DEFAULT_OUTPUT = ROOT / "outputs" / "reports"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="LSEG historical delta-hedging backtest (SPY calls, Jan 2027)."
    )
    p.add_argument("--mock", action="store_true", default=False,
                   help="Use synthetic offline data (for CI / offline testing).")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--ric-config", type=Path, default=DEFAULT_RIC_CONFIG)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--history-count", type=int, default=35)
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    # ── Config ─────────────────────────────────────────────────────────────────
    if not args.config.exists():
        print(f"[ERROR] Config not found: {args.config}")
        return 1

    config = load_backtest_config(args.config)
    if args.output_dir != DEFAULT_OUTPUT:
        from dataclasses import replace
        config = replace(config, output_dir=args.output_dir)

    output_dir = args.output_dir

    # ── Load data ──────────────────────────────────────────────────────────────
    mode = "mock" if args.mock else "auto"
    loader = LsegLoaderConfig(
        ric_config_path=args.ric_config,
        history_count=args.history_count,
        mode=mode,
    )

    print(f"[INFO] Mode: {mode}")
    print(f"[INFO] Loading option and SPY history...")
    load_result = load_lseg_option_data(loader)

    for w in load_result.warnings:
        print(f"[WARN] {w}")

    print(
        f"[INFO] {load_result.rics_with_data} RICs with data"
        f", {load_result.trading_days} days, source={load_result.source}"
    )

    # ── Run backtest ───────────────────────────────────────────────────────────
    print("[INFO] Running backtest...")
    try:
        result = run_lseg_backtest(config, load_result.option_history, load_result.spy_history)
    except (ValueError, RuntimeError) as exc:
        print(f"[ERROR] Backtest failed: {exc}")
        return 1

    # ── Save outputs ───────────────────────────────────────────────────────────
    written = save_lseg_backtest_outputs(
        result=result,
        output_dir=output_dir,
        config=config,
        total_rics_in_universe=load_result.rics_requested,
        data_source=f"LSEG ({load_result.source})",
    )

    print_lseg_backtest_summary(result, output_dir)

    print("\nFiles written:")
    for name, path in written.items():
        print(f"  {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
