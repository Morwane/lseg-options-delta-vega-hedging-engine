"""LSEG Historical Delta-Hedging Backtest — clean entry-point facade.

This module is the canonical entry point for the LSEG-first backtest pipeline.
It wraps historical_delta_hedge_engine.run_backtest() and writes outputs under
the standardised 'lseg_historical_*' naming convention.

Output files written to output_dir:
    lseg_historical_daily_pnl.csv       — per-day P&L, delta, hedges, costs
    lseg_historical_hedge_orders.csv    — daily hedge order details
    lseg_historical_exposures.csv       — per-contract Greeks by day
    lseg_historical_summary.csv         — single-row summary metrics
    lseg_historical_data_quality.csv    — IV source breakdown and fallback rates

Methodology:
    - Option book: top-N nearest-ATM SPY calls from the LSEG audited RIC universe
    - Greeks: Black-Scholes IV bisection from LSEG market mid (fallback: realised vol)
    - P&L: hedge_pnl[t] = hedge_shares[t-1] × (spot[t] - spot[t-1])  (no look-ahead)
    - Transaction costs: 2 bps flat on notional traded
    - IBKR is not used in this module
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.backtesting.contract_selection import check_atm_warning, get_selection_label
from src.backtesting.historical_delta_hedge_engine import (
    BacktestResult,
    HistoricalBacktestConfig,
    load_backtest_config,
    run_backtest,
    to_daily_hedge_df,
    to_data_quality_df,
    to_greeks_df,
)
from src.backtesting.option_history_loader import load_ric_universe
from src.backtesting.validation_report import build_validation_report


def run_lseg_backtest(
    config: HistoricalBacktestConfig,
    option_history: pd.DataFrame,
    spy_history: pd.DataFrame,
) -> BacktestResult:
    """Run the LSEG historical delta-hedging backtest.

    Thin wrapper around run_backtest() that preserves the full BacktestResult
    for downstream use (charts, reports, optimizer comparison).
    """
    return run_backtest(config, option_history, spy_history)


def save_lseg_backtest_outputs(
    result: BacktestResult,
    output_dir: Path,
    config: HistoricalBacktestConfig,
    total_rics_in_universe: int,
    data_source: str,
) -> dict[str, Path]:
    """Write all standardised LSEG backtest output files.

    Returns a dict mapping output_name → Path for each written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    hedge_df = to_daily_hedge_df(result.daily_hedge_rows)
    greeks_df = to_greeks_df(result.daily_greeks)
    quality_df = to_data_quality_df(
        result.daily_greeks,
        result.exclusion_log,
        result.fallback_rate_overall,
        result.is_low_confidence,
    )

    # ── lseg_historical_daily_pnl.csv ─────────────────────────────────────────
    pnl_df = hedge_df[
        [
            "date", "spot", "tte_years", "contracts_in_book",
            "portfolio_delta", "option_pnl", "hedge_pnl", "gross_pnl",
            "transaction_costs", "net_pnl", "cumulative_net_pnl",
            "unhedged_option_pnl", "cumulative_unhedged_pnl",
            "fallback_rate", "low_confidence",
        ]
    ].copy()
    pnl_path = output_dir / "lseg_historical_daily_pnl.csv"
    pnl_df.to_csv(pnl_path, index=False)

    # ── lseg_historical_hedge_orders.csv ──────────────────────────────────────
    orders_df = hedge_df[
        [
            "date", "spot", "portfolio_delta",
            "hedge_shares_before", "target_hedge_shares",
            "hedge_order_shares", "hedge_order_side",
            "hedge_shares_after", "transaction_costs", "hedge_reason",
        ]
    ].copy()
    orders_path = output_dir / "lseg_historical_hedge_orders.csv"
    orders_df.to_csv(orders_path, index=False)

    # ── lseg_historical_exposures.csv ─────────────────────────────────────────
    exp_path = output_dir / "lseg_historical_exposures.csv"
    greeks_df.to_csv(exp_path, index=False)

    # ── lseg_historical_data_quality.csv ──────────────────────────────────────
    dq_path = output_dir / "lseg_historical_data_quality.csv"
    quality_df.to_csv(dq_path, index=False)

    # ── lseg_historical_summary.csv ───────────────────────────────────────────
    summary = _build_summary_row(result, hedge_df, config, data_source)
    summary_df = pd.DataFrame([summary])
    summary_path = output_dir / "lseg_historical_summary.csv"
    summary_df.to_csv(summary_path, index=False)

    # ── Markdown validation report ────────────────────────────────────────────
    report_md = build_validation_report(
        result=result,
        config=config,
        total_rics_in_universe=total_rics_in_universe,
        data_source=data_source,
    )
    report_path = output_dir / "real_lseg_hedge_validation.md"
    report_path.write_text(report_md, encoding="utf-8")

    return {
        "daily_pnl": pnl_path,
        "hedge_orders": orders_path,
        "exposures": exp_path,
        "data_quality": dq_path,
        "summary": summary_path,
        "validation_report": report_path,
    }


def _build_summary_row(
    result: BacktestResult,
    hedge_df: pd.DataFrame,
    config: HistoricalBacktestConfig,
    data_source: str,
) -> dict:
    """Build a single-row summary dict from backtest results."""
    if hedge_df.empty:
        return {}

    final = hedge_df.iloc[-1]
    pnl_series = hedge_df["net_pnl"]
    cum_series = hedge_df["cumulative_net_pnl"]
    drawdown = float((cum_series - cum_series.cummax()).min())

    rebalances = int((hedge_df["hedge_order_side"] != "NONE").sum())
    total_days = len(hedge_df)

    return {
        "underlying": config.underlying,
        "option_type": config.option_type,
        "expiry_date": str(config.expiry_date),
        "data_source": data_source,
        "trading_days": total_days,
        "contracts_in_book": config.atm_contract_count,
        "spot_min": round(float(hedge_df["spot"].min()), 2),
        "spot_max": round(float(hedge_df["spot"].max()), 2),
        "cumulative_pnl_hedged": round(float(final["cumulative_net_pnl"]), 2),
        "cumulative_pnl_unhedged": round(float(final["cumulative_unhedged_pnl"]), 2),
        "hedge_improvement": round(
            float(final["cumulative_net_pnl"]) - float(final["cumulative_unhedged_pnl"]), 2
        ),
        "pnl_volatility_hedged": round(float(pnl_series.std()), 4),
        "max_drawdown_hedged": round(drawdown, 2),
        "total_transaction_costs": round(float(hedge_df["transaction_costs"].sum()), 2),
        "rebalances": rebalances,
        "rebalance_rate_pct": round(rebalances / max(1, total_days) * 100, 1),
        "iv_fallback_rate": round(result.fallback_rate_overall, 4),
        "iv_solve_success_rate": round(1.0 - result.fallback_rate_overall, 4),
        "is_low_confidence": result.is_low_confidence,
    }


def print_lseg_backtest_summary(result: BacktestResult, output_dir: Path) -> None:
    """Print a concise backtest summary to stdout."""
    hedge_df = to_daily_hedge_df(result.daily_hedge_rows)
    first_spot = result.daily_hedge_rows[0].spot if result.daily_hedge_rows else 0.0
    sel_label = get_selection_label(result.initial_selection, first_spot)
    atm_warned, atm_msg = check_atm_warning(result.initial_selection, first_spot)

    print("\n" + "=" * 72)
    print("LSEG HISTORICAL DELTA-HEDGING BACKTEST — SUMMARY")
    print("=" * 72)
    print(f"\nInitial {sel_label} ({len(result.initial_selection)} contracts):")
    for c in result.initial_selection:
        print(
            f"  {c.ric}  strike=${c.strike:.0f}  [{c.moneyness_class}]"
            f"  mid=${c.mid:.2f}  moneyness={c.moneyness_pct * 100:+.1f}%"
        )
    if atm_warned:
        print(f"\n  WARNING: {atm_msg}")

    if not hedge_df.empty:
        print(
            f"\nBacktest period: {hedge_df['date'].iloc[0]} → {hedge_df['date'].iloc[-1]}"
            f"  ({len(hedge_df)} trading days)"
        )
        print(f"SPY spot range:  ${hedge_df['spot'].min():.2f} – ${hedge_df['spot'].max():.2f}")
        final = hedge_df.iloc[-1]
        print(f"\nCumulative P&L (hedged):   ${final['cumulative_net_pnl']:>10.2f}")
        print(f"Cumulative P&L (unhedged): ${final['cumulative_unhedged_pnl']:>10.2f}")
        print(f"Total transaction costs:   ${hedge_df['transaction_costs'].sum():>10.2f}")
        rebalances = int((hedge_df["hedge_order_side"] != "NONE").sum())
        print(f"Hedge rebalances:          {rebalances} of {len(hedge_df)} days")

    print(f"\nIV fallback rate: {result.fallback_rate_overall:.1%}")
    if result.is_low_confidence:
        print("  *** LOW CONFIDENCE — fallback rate exceeds 30% ***")

    print(f"\nOutputs written to: {output_dir}")
    print("=" * 72)
