"""Run the Delta-Vega Hedge Optimizer comparison backtest.

Runs four hedge strategies in parallel on the LSEG SPY option book and
generates comparison outputs and charts.

Methods compared:
    1. no_hedge     — no hedge; pure option book P&L
    2. delta_only   — delta-neutral via underlying shares
    3. delta_vega   — delta + vega via underlying + best single option
    4. optimized    — sparse scipy-optimized combination

Output files (outputs/research/):
    hedge_optimizer_daily_results.csv
    hedge_optimizer_candidate_universe.csv
    hedge_optimizer_selected_instruments.csv
    hedge_optimizer_summary.csv
    residual_greeks_by_method.csv

Charts (docs/images/):
    optimized_vs_delta_hedge_pnl.png
    residual_delta_by_method.png
    residual_vega_by_method.png
    hedge_cost_vs_risk_reduction.png
    optimizer_selected_instruments.png

Usage
-----
python scripts/run_delta_vega_hedge_optimizer.py --mock
python scripts/run_delta_vega_hedge_optimizer.py          # live LSEG
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.backtesting.historical_delta_hedge_engine import load_backtest_config
from src.backtesting.optimized_hedge_backtest import (
    OptimizedBacktestResult,
    run_optimized_backtest,
    to_daily_df,
)
from src.data.lseg_option_loader import LsegLoaderConfig, load_lseg_option_data
from src.optimization.delta_vega_optimizer import OptimizerConfig
from src.optimization.hedge_objective import HedgeObjectiveParams
from src.optimization.hedge_universe import HedgeUniverseConfig

DEFAULT_CONFIG = ROOT / "config" / "historical_backtest.yaml"
DEFAULT_RIC_CONFIG = ROOT / "config" / "lseg_option_coverage_rics.yaml"
DEFAULT_OUTPUT = ROOT / "outputs" / "research"
IMAGES_DIR = ROOT / "docs" / "images"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Delta-Vega hedge optimizer: 4-method comparison backtest."
    )
    p.add_argument("--mock", action="store_true", default=False,
                   help="Use synthetic offline data.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--ric-config", type=Path, default=DEFAULT_RIC_CONFIG)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--no-charts", action="store_true", default=False,
                   help="Skip chart generation.")
    return p.parse_args()


def _save_outputs(result: OptimizedBacktestResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_df = to_daily_df(result.daily_results)
    daily_df.to_csv(output_dir / "hedge_optimizer_daily_results.csv", index=False)

    cand_df = pd.DataFrame(result.candidate_universe_rows)
    cand_df.to_csv(output_dir / "hedge_optimizer_candidate_universe.csv", index=False)

    sel_df = pd.DataFrame(result.selected_instrument_rows)
    sel_df.to_csv(output_dir / "hedge_optimizer_selected_instruments.csv", index=False)

    summary_df = pd.DataFrame(result.summary_by_method)
    summary_df.to_csv(output_dir / "hedge_optimizer_summary.csv", index=False)

    # Residual Greeks by method (pivot-friendly)
    residual_df = daily_df[["date", "method", "residual_delta", "residual_vega"]].copy()
    residual_df.to_csv(output_dir / "residual_greeks_by_method.csv", index=False)

    print(f"\n[OUTPUT] Files written to: {output_dir}")
    for fname in [
        "hedge_optimizer_daily_results.csv",
        "hedge_optimizer_candidate_universe.csv",
        "hedge_optimizer_selected_instruments.csv",
        "hedge_optimizer_summary.csv",
        "residual_greeks_by_method.csv",
    ]:
        print(f"         {output_dir / fname}")


def _build_charts(result: OptimizedBacktestResult, images_dir: Path) -> None:
    """Generate comparison charts and save to docs/images/."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[WARN] matplotlib not available — skipping charts.")
        return

    images_dir.mkdir(parents=True, exist_ok=True)

    daily_df = to_daily_df(result.daily_results)
    daily_df["date"] = pd.to_datetime(daily_df["date"])
    methods = ["no_hedge", "delta_only", "delta_vega", "optimized"]
    method_labels = {
        "no_hedge": "No Hedge",
        "delta_only": "Delta-Only",
        "delta_vega": "Delta-Vega",
        "optimized": "Optimized",
    }
    colors = {
        "no_hedge": "#d62728",
        "delta_only": "#ff7f0e",
        "delta_vega": "#2ca02c",
        "optimized": "#1f77b4",
    }

    # 1. Cumulative P&L comparison
    fig, ax = plt.subplots(figsize=(10, 5))
    for m in methods:
        mdf = daily_df[daily_df["method"] == m].sort_values("date")
        ax.plot(mdf["date"], mdf["cumulative_net_pnl"],
                label=method_labels[m], color=colors[m], linewidth=2)
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.set_title("Cumulative Net P&L by Hedge Method (LSEG SPY Calls, Mock Data)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative Net P&L ($)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(images_dir / "optimized_vs_delta_hedge_pnl.png", dpi=150)
    plt.close(fig)

    # 2. Residual delta by method
    fig, ax = plt.subplots(figsize=(10, 4))
    for m in methods:
        mdf = daily_df[daily_df["method"] == m].sort_values("date")
        ax.plot(mdf["date"], mdf["residual_delta"].abs(),
                label=method_labels[m], color=colors[m], linewidth=1.5)
    ax.set_title("Absolute Residual Delta by Hedge Method")
    ax.set_xlabel("Date")
    ax.set_ylabel("|Residual Delta| (shares equiv.)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(images_dir / "residual_delta_by_method.png", dpi=150)
    plt.close(fig)

    # 3. Residual vega by method
    fig, ax = plt.subplots(figsize=(10, 4))
    for m in methods:
        mdf = daily_df[daily_df["method"] == m].sort_values("date")
        ax.plot(mdf["date"], mdf["residual_vega"].abs(),
                label=method_labels[m], color=colors[m], linewidth=1.5)
    ax.set_title("Absolute Residual Vega by Hedge Method")
    ax.set_xlabel("Date")
    ax.set_ylabel("|Residual Vega| (vega units)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(images_dir / "residual_vega_by_method.png", dpi=150)
    plt.close(fig)

    # 4. Hedge cost vs risk reduction scatter
    summary_df = pd.DataFrame(result.summary_by_method)
    if not summary_df.empty:
        fig, ax = plt.subplots(figsize=(7, 5))
        # No-hedge is reference: risk = 1.0
        base_delta = float(summary_df[summary_df["method"] == "no_hedge"]["avg_abs_residual_delta"].iloc[0]) if len(summary_df[summary_df["method"] == "no_hedge"]) > 0 else 1.0
        for _, row in summary_df.iterrows():
            m = row["method"]
            risk_pct = float(row["avg_abs_residual_delta"]) / max(1e-9, base_delta) * 100.0
            cost = float(row["total_transaction_costs"])
            ax.scatter(cost, risk_pct, s=120, color=colors.get(m, "grey"), zorder=5)
            ax.annotate(method_labels.get(m, m), (cost, risk_pct),
                        textcoords="offset points", xytext=(6, 4), fontsize=9)
        ax.set_xlabel("Total Transaction Costs ($)")
        ax.set_ylabel("Avg |Residual Delta| as % of Unhedged")
        ax.set_title("Hedge Cost vs Delta Risk Reduction")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(images_dir / "hedge_cost_vs_risk_reduction.png", dpi=150)
        plt.close(fig)

    # 5. Optimizer selected instruments bar chart
    sel_df = pd.DataFrame(result.selected_instrument_rows)
    if not sel_df.empty:
        opt_sel = sel_df[sel_df["method"] == "optimized"]
        if not opt_sel.empty:
            ric_counts = opt_sel["ric"].value_counts().head(15)
            fig, ax = plt.subplots(figsize=(10, 4))
            ric_counts.plot(kind="bar", ax=ax, color="#1f77b4", alpha=0.8)
            ax.set_title("Top Optimizer-Selected Option Instruments (Frequency)")
            ax.set_xlabel("RIC")
            ax.set_ylabel("Days Selected")
            ax.tick_params(axis="x", rotation=45, labelsize=7)
            fig.tight_layout()
            fig.savefig(images_dir / "optimizer_selected_instruments.png", dpi=150)
            plt.close(fig)

    print(f"\n[CHARTS] Saved to: {images_dir}")
    for fname in [
        "optimized_vs_delta_hedge_pnl.png", "residual_delta_by_method.png",
        "residual_vega_by_method.png", "hedge_cost_vs_risk_reduction.png",
        "optimizer_selected_instruments.png",
    ]:
        print(f"         {images_dir / fname}")


def _print_summary(result: OptimizedBacktestResult) -> None:
    print("\n" + "=" * 72)
    print("DELTA-VEGA HEDGE OPTIMIZER — 4-METHOD COMPARISON SUMMARY")
    print("=" * 72)
    print(f"\n{'Method':<16} {'P&L':>10} {'P&L Vol':>10} {'Max DD':>10} {'|ΔRes|':>10} {'|νRes|':>10} {'Costs':>10}")
    print("-" * 72)
    for s in result.summary_by_method:
        print(
            f"{s['method']:<16} "
            f"${s['total_net_pnl']:>9.2f} "
            f"${s['pnl_volatility']:>9.4f} "
            f"${s['max_drawdown']:>9.2f} "
            f"{s['avg_abs_residual_delta']:>10.4f} "
            f"{s['avg_abs_residual_vega']:>10.4f} "
            f"${s['total_transaction_costs']:>9.2f}"
        )
    print("=" * 72)
    data_note = "Synthetic mock data" if args.mock else "Real LSEG historical data"
    print(f"\nData source: {data_note}.")


def main() -> int:
    args = _parse_args()

    if not args.config.exists():
        print(f"[ERROR] Config not found: {args.config}")
        return 1

    config = load_backtest_config(args.config)
    mode = "mock" if args.mock else "auto"

    loader = LsegLoaderConfig(
        ric_config_path=args.ric_config,
        history_count=35,
        mode=mode,
    )

    print(f"[INFO] Mode: {mode}  |  Loading data...")
    load_result = load_lseg_option_data(loader)
    for w in load_result.warnings:
        print(f"[WARN] {w}")
    print(f"[INFO] {load_result.rics_with_data} RICs, {load_result.trading_days} days")

    optimizer_config = OptimizerConfig(
        max_option_instruments=2,
        max_contracts_per_instrument=5.0,
        max_underlying_shares=500.0,
        objective=HedgeObjectiveParams(
            lambda_delta=1.0,
            lambda_vega=0.5,
            lambda_cost=0.05,
            lambda_turnover=0.02,
            cost_bps=2.0,
        ),
    )
    universe_config = HedgeUniverseConfig(
        max_spread_bps=300.0,
        max_moneyness_abs_pct=15.0,
        require_iv_solved=True,
        max_candidates=20,
    )

    print("[INFO] Running 4-method optimizer backtest...")
    try:
        result = run_optimized_backtest(
            config=config,
            option_history=load_result.option_history,
            spy_history=load_result.spy_history,
            optimizer_config=optimizer_config,
            universe_config=universe_config,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"[ERROR] Backtest failed: {exc}")
        return 1

    _save_outputs(result, args.output_dir)
    _print_summary(result)

    if not args.no_charts:
        _build_charts(result, IMAGES_DIR)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
