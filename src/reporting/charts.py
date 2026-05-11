"""Generate summary charts for the README and reporting tearsheet.

All charts read from outputs/reports/ CSVs and write PNGs to docs/images/.
The backtest CSV is produced by:
    python scripts/run_real_lseg_historical_hedge_backtest.py --mock

Each chart function handles missing-data gracefully — it prints a warning and
returns None rather than crashing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import matplotlib
matplotlib.use("Agg")  # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np

_STYLE = {
    "hedged":   "#1f77b4",   # blue
    "unhedged": "#d62728",   # red
    "delta":    "#2ca02c",   # green
    "hedge":    "#ff7f0e",   # orange
    "buy":      "#2ca02c",
    "sell":     "#d62728",
    "gamma":    "#9467bd",
    "vega":     "#8c564b",
    "ok":       "#2ca02c",
    "na":       "#d62728",
    "cost":     "#e377c2",
    "neutral":  "#7f7f7f",
}
_FIGSIZE = (10, 5)
_DPI = 120
_NOTE = "Synthetic mock data (offline / CI)"


def _load(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        print(f"  [chart] SKIP — missing {path.name}")
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    return df


def _save(fig: plt.Figure, out: Path) -> str:
    fig.savefig(out, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    return str(out)


# ---------------------------------------------------------------------------
# 1. Hedged vs unhedged cumulative P&L
# ---------------------------------------------------------------------------

def chart_hedged_vs_unhedged_pnl(reports_dir: Path, images_dir: Path) -> str | None:
    df = _load(reports_dir / "real_historical_daily_hedge.csv")
    if df is None:
        return None

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.plot(df["date"], df["cumulative_net_pnl"], color=_STYLE["hedged"],
            linewidth=2, label="Hedged (net of costs)")
    ax.plot(df["date"], df["cumulative_unhedged_pnl"], color=_STYLE["unhedged"],
            linewidth=2, linestyle="--", label="Unhedged")
    ax.axhline(0, color=_STYLE["neutral"], linewidth=0.8, linestyle=":")
    ax.set_title("Cumulative P&L — Hedged vs Unhedged", fontsize=13)
    ax.set_ylabel("Cumulative P&L (USD)")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=0))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.legend()
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    fig.text(0.99, 0.01, _NOTE, ha="right", va="bottom",
             fontsize=7, color=_STYLE["neutral"], style="italic")
    fig.tight_layout()
    return _save(fig, images_dir / "hedged_vs_unhedged_pnl.png")


# ---------------------------------------------------------------------------
# 2. Portfolio delta before / after hedge
# ---------------------------------------------------------------------------

def chart_net_delta(reports_dir: Path, images_dir: Path) -> str | None:
    df = _load(reports_dir / "real_historical_daily_hedge.csv")
    if df is None:
        return None

    net_before = df["portfolio_delta"] + df["hedge_shares_before"]
    net_after  = df["portfolio_delta"] + df["hedge_shares_after"]

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.plot(df["date"], net_before, color=_STYLE["unhedged"],
            linewidth=2, linestyle="--", label="Net Δ before rebalance")
    ax.plot(df["date"], net_after, color=_STYLE["hedged"],
            linewidth=2, label="Net Δ after rebalance")
    ax.axhline(0, color=_STYLE["neutral"], linewidth=0.8, linestyle=":")
    ax.set_title("Net Portfolio Delta Before / After Daily Rebalance", fontsize=13)
    ax.set_ylabel("Net delta (share-equivalents)")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=0))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.legend()
    fig.text(0.99, 0.01, _NOTE, ha="right", va="bottom",
             fontsize=7, color=_STYLE["neutral"], style="italic")
    fig.tight_layout()
    return _save(fig, images_dir / "net_delta_before_after.png")


# ---------------------------------------------------------------------------
# 3. Hedge orders (daily shares bought/sold)
# ---------------------------------------------------------------------------

def chart_hedge_orders(reports_dir: Path, images_dir: Path) -> str | None:
    df = _load(reports_dir / "real_historical_daily_hedge.csv")
    if df is None:
        return None

    # Exclude the initial hedge day (side=="SELL" day 0 with no prior position)
    orders = df[df["hedge_order_side"] != "NONE"].copy()
    colors = [_STYLE["buy"] if s == "BUY" else _STYLE["sell"]
              for s in orders["hedge_order_side"]]

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.bar(orders["date"], orders["hedge_order_shares"], color=colors, width=0.7)
    ax.axhline(0, color=_STYLE["neutral"], linewidth=0.8, linestyle=":")
    ax.set_title("Daily Hedge Orders (shares)", fontsize=13)
    ax.set_ylabel("Shares (+ = BUY, − = SELL)")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=0))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")

    # Custom legend
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(color=_STYLE["buy"],  label="BUY"),
        Patch(color=_STYLE["sell"], label="SELL"),
    ])
    fig.text(0.99, 0.01, _NOTE, ha="right", va="bottom",
             fontsize=7, color=_STYLE["neutral"], style="italic")
    fig.tight_layout()
    return _save(fig, images_dir / "hedge_orders_by_underlying.png")


# ---------------------------------------------------------------------------
# 4. Transaction costs over time
# ---------------------------------------------------------------------------

def chart_transaction_costs(reports_dir: Path, images_dir: Path) -> str | None:
    df = _load(reports_dir / "real_historical_daily_hedge.csv")
    if df is None:
        return None

    df = df.copy()
    df["cumulative_costs"] = df["transaction_costs"].cumsum()

    fig, ax1 = plt.subplots(figsize=_FIGSIZE)
    ax2 = ax1.twinx()

    ax1.bar(df["date"], df["transaction_costs"], color=_STYLE["cost"],
            width=0.7, alpha=0.7, label="Daily cost")
    ax2.plot(df["date"], df["cumulative_costs"], color=_STYLE["hedged"],
             linewidth=2, label="Cumulative cost")

    ax1.set_title("Transaction Costs — Daily and Cumulative", fontsize=13)
    ax1.set_ylabel("Daily cost (USD)")
    ax2.set_ylabel("Cumulative cost (USD)")
    ax1.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    ax1.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=0))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=30, ha="right")

    lines1, labs1 = ax1.get_legend_handles_labels()
    lines2, labs2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labs1 + labs2)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.2f}"))
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.2f}"))
    fig.text(0.99, 0.01, _NOTE, ha="right", va="bottom",
             fontsize=7, color=_STYLE["neutral"], style="italic")
    fig.tight_layout()
    return _save(fig, images_dir / "transaction_costs_over_time.png")


# ---------------------------------------------------------------------------
# 5. Drawdown — hedged vs unhedged
# ---------------------------------------------------------------------------

def chart_drawdown(reports_dir: Path, images_dir: Path) -> str | None:
    df = _load(reports_dir / "real_historical_daily_hedge.csv")
    if df is None:
        return None

    def _drawdown(series: pd.Series) -> pd.Series:
        running_max = series.cummax()
        dd = series - running_max
        # Where series never exceeded 0, treat 0 as the high-water mark
        running_max2 = series.clip(lower=0).cummax()
        dd2 = series - running_max2
        return dd2

    fig, ax = plt.subplots(figsize=_FIGSIZE)
    ax.fill_between(df["date"], _drawdown(df["cumulative_net_pnl"]),
                    color=_STYLE["hedged"], alpha=0.4, label="Hedged drawdown")
    ax.fill_between(df["date"], _drawdown(df["cumulative_unhedged_pnl"]),
                    color=_STYLE["unhedged"], alpha=0.4, label="Unhedged drawdown")
    ax.set_title("Drawdown from High-Water Mark — Hedged vs Unhedged", fontsize=13)
    ax.set_ylabel("Drawdown (USD)")
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=0))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.legend()
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    fig.text(0.99, 0.01, _NOTE, ha="right", va="bottom",
             fontsize=7, color=_STYLE["neutral"], style="italic")
    fig.tight_layout()
    return _save(fig, images_dir / "drawdown_hedged_vs_unhedged.png")


# ---------------------------------------------------------------------------
# 6. Portfolio gamma and vega over time
# ---------------------------------------------------------------------------

def chart_gamma_vega(reports_dir: Path, images_dir: Path) -> str | None:
    df = _load(reports_dir / "real_historical_greeks_by_contract.csv")
    if df is None:
        return None

    MULTIPLIER = 100
    agg = (
        df.groupby("date")[["gamma", "vega"]]
        .sum()
        .reset_index()
    )
    agg["portfolio_gamma"] = agg["gamma"] * MULTIPLIER
    agg["portfolio_vega"]  = agg["vega"]  * MULTIPLIER

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)

    ax1.plot(agg["date"], agg["portfolio_gamma"], color=_STYLE["gamma"], linewidth=2)
    ax1.set_ylabel("Portfolio Gamma")
    ax1.set_title("Portfolio Gamma and Vega Monitoring (×100 multiplier)", fontsize=13)
    ax1.axhline(0, color=_STYLE["neutral"], linewidth=0.6, linestyle=":")

    ax2.plot(agg["date"], agg["portfolio_vega"], color=_STYLE["vega"], linewidth=2)
    ax2.set_ylabel("Portfolio Vega (USD / vol unit)")
    ax2.axhline(0, color=_STYLE["neutral"], linewidth=0.6, linestyle=":")
    ax2.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(byweekday=0))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right")

    fig.text(0.99, 0.01, _NOTE, ha="right", va="bottom",
             fontsize=7, color=_STYLE["neutral"], style="italic")
    fig.tight_layout()
    return _save(fig, images_dir / "gamma_vega_monitoring.png")


# ---------------------------------------------------------------------------
# 7. IBKR audit summary (static — based on validated audit results)
# ---------------------------------------------------------------------------

def chart_ibkr_audit_summary(reports_dir: Path, images_dir: Path) -> str | None:
    categories = [
        "Paper Connection",
        "Account Summary",
        "Underlying Contracts",
        "Option Chains",
        "Delayed Spot (SPY)",
        "Option Greeks",
    ]
    values  = [1, 1, 1, 1, 1, 0]
    colors  = [_STYLE["ok"] if v else _STYLE["na"] for v in values]
    labels  = ["Validated" if v else "Not available" for v in values]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.barh(categories, [1] * len(categories), color=colors, height=0.55)
    for bar, lbl in zip(bars, labels):
        ax.text(0.5, bar.get_y() + bar.get_height() / 2,
                lbl, va="center", ha="center", color="white",
                fontsize=10, fontweight="bold")
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("IBKR Paper Trading — Validated Data Access", fontsize=13)
    ax.invert_yaxis()

    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(color=_STYLE["ok"], label="Validated"),
        Patch(color=_STYLE["na"], label="Not available"),
    ], loc="lower right")
    fig.tight_layout()
    return _save(fig, images_dir / "ibkr_audit_summary.png")


# ---------------------------------------------------------------------------
# 8. LSEG audit summary (static — based on validated audit results)
# ---------------------------------------------------------------------------

def chart_lseg_audit_summary(reports_dir: Path, images_dir: Path) -> str | None:
    categories = [
        "Underlying Prices (SPY/QQQ/TLT/GLD)",
        "Option Bid / Ask History",
        "Implied Volatility (TR.IV / TR.ImpliedVolatility)",
        "Option Greeks (Delta, Gamma, Vega, Theta)",
    ]
    values = [1, 1, 0, 0]
    colors = [_STYLE["ok"] if v else _STYLE["na"] for v in values]
    labels = ["Validated" if v else "Not available" for v in values]

    fig, ax = plt.subplots(figsize=(9, 4))
    bars = ax.barh(categories, [1] * len(categories), color=colors, height=0.55)
    for bar, lbl in zip(bars, labels):
        ax.text(0.5, bar.get_y() + bar.get_height() / 2,
                lbl, va="center", ha="center", color="white",
                fontsize=10, fontweight="bold")
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("LSEG Data Library — Validated Data Access", fontsize=13)
    ax.invert_yaxis()

    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(color=_STYLE["ok"], label="Validated"),
        Patch(color=_STYLE["na"], label="Not available"),
    ], loc="lower right")
    fig.tight_layout()
    return _save(fig, images_dir / "lseg_audit_summary.png")


# ---------------------------------------------------------------------------
# Build all
# ---------------------------------------------------------------------------

_CHART_FUNCS: list[Callable[[Path, Path], str | None]] = [
    chart_hedged_vs_unhedged_pnl,
    chart_net_delta,
    chart_hedge_orders,
    chart_transaction_costs,
    chart_drawdown,
    chart_gamma_vega,
    chart_ibkr_audit_summary,
    chart_lseg_audit_summary,
]


def build_all_charts(
    reports_dir: Path,
    images_dir: Path,
    silent: bool = False,
) -> list[str]:
    """Build all README charts and return list of created file paths."""
    images_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for fn in _CHART_FUNCS:
        path = fn(reports_dir, images_dir)
        if path:
            created.append(path)
            if not silent:
                print(f"  [chart] {Path(path).name}")
    return created
