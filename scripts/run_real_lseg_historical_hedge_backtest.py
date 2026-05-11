"""
Real historical SPY listed-call-options delta-hedging backtest using LSEG bid/ask history.

Usage
-----
python scripts/run_real_lseg_historical_hedge_backtest.py          # live LSEG
python scripts/run_real_lseg_historical_hedge_backtest.py --mock   # offline / CI
python scripts/run_real_lseg_historical_hedge_backtest.py --mock --output-dir outputs/reports

Safety
------
- No IBKR connection in this script.
- No orders placed.
- Paper trading and dry-run flags enforced at engine level.

Limitations (printed at end)
-----------------------------
- SPY calls only (no puts confirmed in LSEG audit).
- Single Jan 2027 expiry.
- ~30 trading days of LSEG bid/ask history (2026-03-18 to 2026-04-29).
- Greeks reconstructed from market mid via Black-Scholes IV bisection.
- Historical LSEG option Greeks not used (only 1 snapshot row per RIC in audit).
- No alpha strategy — pure delta-hedge P&L illustration.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backtesting.contract_selection import check_atm_warning, get_selection_label
from src.backtesting.historical_delta_hedge_engine import (
    BacktestResult,
    load_backtest_config,
    run_backtest,
    to_daily_hedge_df,
    to_data_quality_df,
    to_greeks_df,
)
from src.backtesting.option_history_loader import (
    load_option_history_lseg,
    load_option_history_mock,
    load_ric_universe,
    load_spy_history_lseg,
    load_spy_history_mock,
)
from src.backtesting.validation_report import build_validation_report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Real historical listed-options delta-hedging backtest (SPY calls, Jan 2027)."
    )
    p.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use synthetic offline data instead of live LSEG (for CI / offline testing).",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "historical_backtest.yaml",
        help="Path to historical_backtest.yaml.",
    )
    p.add_argument(
        "--ric-config",
        type=Path,
        default=ROOT / "config" / "lseg_option_coverage_rics.yaml",
        help="Path to lseg_option_coverage_rics.yaml (confirmed RIC universe).",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output directory from config.",
    )
    p.add_argument(
        "--history-count",
        type=int,
        default=35,
        help="Number of daily bars to request from LSEG (live mode only).",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_data(
    args: argparse.Namespace,
    rics: list[str],
    count: int,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Return (option_history, spy_history, data_source_label).

    data_source_label is a human-readable string for the validation report.
    """
    if args.mock:
        print("[INFO] --mock flag set: using synthetic offline data.")
        option_df = load_option_history_mock(rics)
        spy_df = load_spy_history_mock()
        return option_df, spy_df, "Synthetic mock (offline / CI)"

    # Try live LSEG
    try:
        import lseg.data as ld  # type: ignore[import]
        print("[INFO] Opening LSEG session…")
        ld.open_session()
    except ImportError:
        print(
            "[WARN] lseg.data not installed. Falling back to synthetic mock data.\n"
            "       Install with: pip install lseg-data"
        )
        return (
            load_option_history_mock(rics),
            load_spy_history_mock(),
            "Synthetic mock (lseg.data not installed)",
        )
    except Exception as e:
        print(f"[WARN] LSEG session failed ({e}). Falling back to synthetic mock data.")
        return (
            load_option_history_mock(rics),
            load_spy_history_mock(),
            f"Synthetic mock (LSEG session failed: {e})",
        )

    data_source = "LSEG live"
    try:
        print(f"[INFO] Loading SPY spot history ({count} bars)…")
        spy_df = load_spy_history_lseg(count=count)
        print(f"[INFO] Loading option bid/ask history for {len(rics)} RICs…")
        option_df = load_option_history_lseg(rics=rics, count=count)
    except Exception as e:
        print(f"[WARN] LSEG data load failed ({e}). Falling back to synthetic mock data.")
        option_df = load_option_history_mock(rics)
        spy_df = load_spy_history_mock()
        data_source = f"Synthetic mock (LSEG data load failed: {e})"
    finally:
        try:
            ld.close_session()
        except Exception:
            pass

    return option_df, spy_df, data_source


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _save_outputs(result: BacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    hedge_df = to_daily_hedge_df(result.daily_hedge_rows)
    greeks_df = to_greeks_df(result.daily_greeks)
    quality_df = to_data_quality_df(
        result.daily_greeks,
        result.exclusion_log,
        result.fallback_rate_overall,
        result.is_low_confidence,
    )
    exclusion_df = pd.DataFrame(result.exclusion_log)

    initial_sel_df = pd.DataFrame(
        [
            {
                "ric": c.ric,
                "strike": c.strike,
                "bid": c.bid,
                "ask": c.ask,
                "mid": c.mid,
                "spread": c.spread,
                "moneyness_abs": c.moneyness_abs,
                "moneyness_pct": round(c.moneyness_pct * 100, 2),
                "moneyness_class": c.moneyness_class,
            }
            for c in result.initial_selection
        ]
    )

    hedge_df.to_csv(output_dir / "real_historical_daily_hedge.csv", index=False)
    greeks_df.to_csv(output_dir / "real_historical_greeks_by_contract.csv", index=False)
    quality_df.to_csv(output_dir / "historical_option_data_quality.csv", index=False)
    exclusion_df.to_csv(output_dir / "historical_contract_exclusions.csv", index=False)
    initial_sel_df.to_csv(output_dir / "initial_atm_selection.csv", index=False)

    print(f"\n[OUTPUT] Files saved to: {output_dir}")
    for fname in [
        "real_historical_daily_hedge.csv",
        "real_historical_greeks_by_contract.csv",
        "historical_option_data_quality.csv",
        "historical_contract_exclusions.csv",
        "initial_atm_selection.csv",
    ]:
        print(f"         {output_dir / fname}")


# ---------------------------------------------------------------------------
# Summary printing
# ---------------------------------------------------------------------------

def _print_summary(result: BacktestResult, output_dir: Path) -> None:
    hedge_df = to_daily_hedge_df(result.daily_hedge_rows)
    first_spot = result.daily_hedge_rows[0].spot if result.daily_hedge_rows else 0.0
    selection_label = get_selection_label(result.initial_selection, first_spot)
    atm_warned, atm_warning_msg = check_atm_warning(result.initial_selection, first_spot)

    print("\n" + "=" * 72)
    print("REAL HISTORICAL LISTED-OPTIONS DELTA-HEDGING BACKTEST — SUMMARY")
    print("=" * 72)

    # Initial selection (with dynamic label)
    print(f"\nInitial {selection_label} ({len(result.initial_selection)} contracts):")
    for c in result.initial_selection:
        print(
            f"  {c.ric}  strike=${c.strike:.0f}  [{c.moneyness_class}]"
            f"  mid=${c.mid:.2f}  spread=${c.spread:.2f}"
            f"  moneyness={c.moneyness_pct*100:+.1f}%"
        )

    # ATM proximity warning
    if atm_warned:
        print(f"\n  ⚠  WARNING: {atm_warning_msg}")

    # Date range
    if not hedge_df.empty:
        print(
            f"\nBacktest period: {hedge_df['date'].iloc[0]} → {hedge_df['date'].iloc[-1]}"
            f"  ({len(hedge_df)} trading days)"
        )
        print(f"SPY spot range:  ${hedge_df['spot'].min():.2f} – ${hedge_df['spot'].max():.2f}")

    # P&L summary
    if len(hedge_df) > 1:
        final = hedge_df.iloc[-1]
        print(f"\nCumulative P&L (hedged):   ${final['cumulative_net_pnl']:>10.2f}")
        print(f"Cumulative P&L (unhedged): ${final['cumulative_unhedged_pnl']:>10.2f}")
        print(f"Total transaction costs:   ${hedge_df['transaction_costs'].sum():>10.2f}")

    # Data quality
    print(f"\nOverall IV fallback rate:  {result.fallback_rate_overall:.1%}")
    if result.is_low_confidence:
        print("  *** LOW CONFIDENCE — fallback rate exceeds 30% ***")

    # Exclusions
    if result.exclusion_log:
        print(f"\nTotal exclusion events:    {len(result.exclusion_log)}")

    # Hedge activity
    if not hedge_df.empty:
        rebalanced = (hedge_df["hedge_order_side"] != "NONE").sum()
        print(f"Hedge rebalances:          {rebalanced} of {len(hedge_df)} days")

    # Limitations
    print("\n" + "-" * 72)
    print("LIMITATIONS")
    print("-" * 72)
    for lim in result.limitations:
        print(f"  • {lim}")

    print("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()

    # Load config
    if not args.config.exists():
        print(f"[ERROR] Config not found: {args.config}")
        return 1

    config = load_backtest_config(args.config)

    if args.output_dir is not None:
        from dataclasses import replace
        config = replace(config, output_dir=args.output_dir)

    output_dir = config.output_dir

    # Load RIC universe
    if not args.ric_config.exists():
        print(f"[ERROR] RIC config not found: {args.ric_config}")
        return 1

    rics = load_ric_universe(args.ric_config)
    if not rics:
        print("[ERROR] RIC universe is empty — check lseg_option_coverage_rics.yaml.")
        return 1

    print(f"[INFO] RIC universe: {len(rics)} confirmed SPY call RICs")
    print(f"[INFO] Expiry date:  {config.expiry_date}")
    print(f"[INFO] ATM count:    {config.atm_contract_count}")
    print(f"[INFO] Output dir:   {output_dir}")

    # Load data
    option_history, spy_history, data_source = _load_data(args, rics, args.history_count)
    print(
        f"[INFO] Option history: {len(option_history)} rows"
        f" across {option_history['ric'].nunique()} RICs"
    )
    print(f"[INFO] SPY history: {len(spy_history)} rows")
    print(f"[INFO] Data source:  {data_source}")

    # Run backtest
    print("\n[INFO] Running backtest…")
    try:
        result = run_backtest(config, option_history, spy_history)
    except (ValueError, RuntimeError) as e:
        print(f"[ERROR] Backtest failed: {e}")
        return 1

    # Save CSVs and print console summary
    _save_outputs(result, output_dir)
    _print_summary(result, output_dir)

    # Save markdown validation report
    output_dir.mkdir(parents=True, exist_ok=True)
    report_md = build_validation_report(
        result=result,
        config=config,
        total_rics_in_universe=len(rics),
        data_source=data_source,
    )
    report_path = output_dir / "real_lseg_hedge_validation.md"
    report_path.write_text(report_md, encoding="utf-8")
    print(f"\n[REPORT] Validation report saved to: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
