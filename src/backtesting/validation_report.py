"""Build the real LSEG historical hedge validation report as a Markdown string.

The report is written to outputs/reports/real_lseg_hedge_validation.md after
every run of run_real_lseg_historical_hedge_backtest.py, regardless of whether
live LSEG or synthetic mock data was used.

Contents:
    1. Header and metadata
    2. RIC universe summary
    3. Contract selection (with 3% ATM proximity warning and rename)
    4. Per-contract coverage table (dates, bid/ask/mid availability)
    5. IV bisection quality (overall + per-date table)
    6. Backtest P&L and hedge activity
    7. Limitations
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from src.backtesting.contract_selection import (
    check_atm_warning,
    get_selection_label,
)
from src.backtesting.historical_delta_hedge_engine import (
    BacktestResult,
    DailyContractGreeks,
    HistoricalBacktestConfig,
    to_daily_hedge_df,
)

_SEP = "-" * 72


def _fmt_pnl(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}${v:,.2f}"


def _pct(num: int, denom: int) -> str:
    if denom == 0:
        return "N/A"
    return f"{num / denom * 100:.1f}%"


def _coverage_row(ric: str, strike: float, greeks: list[DailyContractGreeks]) -> dict[str, Any]:
    """Aggregate coverage stats for one RIC from its greeks entries."""
    total = len(greeks)
    bid_ok = sum(1 for g in greeks if g.bid is not None and math.isfinite(g.bid))
    ask_ok = sum(1 for g in greeks if g.ask is not None and math.isfinite(g.ask))
    mid_ok = sum(
        1 for g in greeks
        if g.market_mid is not None and math.isfinite(g.market_mid)
    )
    iv_solved = sum(1 for g in greeks if g.iv_source == "bs_bisection")
    iv_fallback = sum(1 for g in greeks if g.iv_source == "realized_vol_fallback")
    iv_failed = sum(1 for g in greeks if g.iv_source == "failed")
    return dict(
        ric=ric,
        strike=strike,
        total_dates=total,
        bid_days=bid_ok,
        ask_days=ask_ok,
        mid_days=mid_ok,
        iv_solved=iv_solved,
        iv_fallback=iv_fallback,
        iv_failed=iv_failed,
    )


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown pipe table from headers and string rows."""
    col_widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
    sep = "| " + " | ".join("-" * w for w in col_widths) + " |"
    header_row = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    data_rows = [
        "| " + " | ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([header_row, sep] + data_rows)


def build_validation_report(
    result: BacktestResult,
    config: HistoricalBacktestConfig,
    total_rics_in_universe: int,
    data_source: str,
    generated_at: str | None = None,
) -> str:
    """Build and return the full validation report as a Markdown string.

    Args:
        result:                 BacktestResult from run_backtest().
        config:                 HistoricalBacktestConfig used for the run.
        total_rics_in_universe: Number of RICs in lseg_option_coverage_rics.yaml.
        data_source:            Human-readable label, e.g. "LSEG live" or
                                "Synthetic mock (offline)".
        generated_at:           ISO-8601 timestamp string; defaults to UTC now.

    Returns:
        Markdown string suitable for writing to a .md file.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    hedge_df = to_daily_hedge_df(result.daily_hedge_rows)
    initial = result.initial_selection

    # Spot on the first backtest date
    first_spot = result.daily_hedge_rows[0].spot if result.daily_hedge_rows else 0.0

    # Selection label and ATM warning
    selection_label = get_selection_label(initial, first_spot)
    atm_warned, atm_warning_msg = check_atm_warning(initial, first_spot)

    # Group greeks by RIC
    greeks_by_ric: dict[str, list[DailyContractGreeks]] = {}
    for g in result.daily_greeks:
        greeks_by_ric.setdefault(g.ric, []).append(g)

    # Total trading days
    total_days = len(result.daily_hedge_rows)
    period_start = str(hedge_df["date"].iloc[0]) if not hedge_df.empty else "N/A"
    period_end = str(hedge_df["date"].iloc[-1]) if not hedge_df.empty else "N/A"

    # Overall IV stats
    total_iv_attempts = len(result.daily_greeks)
    iv_solved_total = sum(1 for g in result.daily_greeks if g.iv_source == "bs_bisection")
    iv_fallback_total = sum(1 for g in result.daily_greeks if g.iv_source == "realized_vol_fallback")
    iv_failed_total = sum(1 for g in result.daily_greeks if g.iv_source == "failed")

    # P&L
    final_row = hedge_df.iloc[-1] if len(hedge_df) > 1 else None
    cum_hedged = float(final_row["cumulative_net_pnl"]) if final_row is not None else 0.0
    cum_unhedged = float(final_row["cumulative_unhedged_pnl"]) if final_row is not None else 0.0
    total_costs = float(hedge_df["transaction_costs"].sum()) if not hedge_df.empty else 0.0
    rebalances = int((hedge_df["hedge_order_side"] != "NONE").sum()) if not hedge_df.empty else 0

    # Strike range in universe
    min_strike = 50.0
    max_strike = min_strike + (total_rics_in_universe - 1) * 5.0

    # Build sections
    lines: list[str] = []

    # --- Header ---
    lines += [
        "# Real LSEG Historical Hedge Validation Report",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Generated | {generated_at} |",
        f"| Data source | {data_source} |",
        f"| Underlying | {config.underlying} |",
        f"| Option type | {config.option_type.capitalize()}s only |",
        f"| Expiry | {config.expiry_date} |",
        f"| Selection method | {selection_label} |",
        "",
        _SEP,
        "",
    ]

    # --- Section 1: RIC Universe ---
    lines += [
        "## 1. RIC Universe",
        "",
        f"- Total confirmed RICs: **{total_rics_in_universe}**",
        f"- Strike range: ${min_strike:.0f}–${max_strike:.0f} ($5 increments)",
        f"- Expiry: January 2027 ({config.expiry_date})",
        f"- Option type confirmed: **calls only** (no puts confirmed in LSEG audit)",
        "",
        _SEP,
        "",
    ]

    # --- Section 2: Contract Selection ---
    lines += [
        "## 2. Contract Selection",
        "",
        f"**Selection method:** {selection_label}  ",
        f"**Contracts selected:** {len(initial)} of {config.atm_contract_count} requested  ",
        f"**Selection spot:** ${first_spot:.2f}  ",
        "",
    ]

    if atm_warned:
        lines += [
            f"> ⚠️ **WARNING:** {atm_warning_msg}",
            "",
        ]

    if initial:
        headers = ["RIC", "Strike", "Moneyness%", "Class", "Mid$", "Spread$", "Moneyness$"]
        rows = [
            [
                c.ric,
                f"${c.strike:.0f}",
                f"{c.moneyness_pct * 100:+.1f}%",
                c.moneyness_class,
                f"{c.mid:.2f}",
                f"{c.spread:.2f}",
                f"${c.moneyness_abs:.1f}",
            ]
            for c in initial
        ]
        lines += [_md_table(headers, rows), ""]

    lines += [_SEP, ""]

    # --- Section 3: Per-contract Coverage ---
    lines += [
        "## 3. Contract Coverage",
        "",
        f"Total trading days in backtest: **{total_days}**",
        "",
    ]

    if greeks_by_ric:
        headers = ["RIC", "Strike", "Bid days", "Ask days", "Mid days", "IV solved", "IV fallback", "IV failed", "Coverage"]
        cov_rows = []
        for ric, g_list in sorted(greeks_by_ric.items()):
            stats = _coverage_row(ric, g_list[0].strike, g_list)
            coverage_pct = _pct(stats["mid_days"], stats["total_dates"])
            cov_rows.append([
                ric,
                f"${stats['strike']:.0f}",
                f"{stats['bid_days']}/{stats['total_dates']}",
                f"{stats['ask_days']}/{stats['total_dates']}",
                f"{stats['mid_days']}/{stats['total_dates']}",
                f"{stats['iv_solved']}/{stats['total_dates']}",
                f"{stats['iv_fallback']}/{stats['total_dates']}",
                f"{stats['iv_failed']}/{stats['total_dates']}",
                coverage_pct,
            ])
        lines += [_md_table(headers, cov_rows), ""]

    lines += [_SEP, ""]

    # --- Section 4: IV Quality ---
    lines += [
        "## 4. IV Bisection Quality",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total IV computation attempts | {total_iv_attempts} |",
        f"| BS bisection success | {iv_solved_total} / {total_iv_attempts} ({_pct(iv_solved_total, total_iv_attempts)}) |",
        f"| Realized vol fallback | {iv_fallback_total} / {total_iv_attempts} ({_pct(iv_fallback_total, total_iv_attempts)}) |",
        f"| IV failed | {iv_failed_total} / {total_iv_attempts} ({_pct(iv_failed_total, total_iv_attempts)}) |",
        f"| Overall fallback rate | {result.fallback_rate_overall:.1%} |",
        f"| Backtest confidence | {'**LOW** ⚠️' if result.is_low_confidence else '**HIGH**'} |",
        "",
    ]

    if result.is_low_confidence:
        lines += [
            "> ⚠️ **LOW CONFIDENCE:** Overall IV fallback rate exceeds 30%.",
            "> Greeks derived from realized vol rather than market-implied vol for the majority of contract-days.",
            "",
        ]

    # Per-date IV table (show all dates)
    iv_by_date: dict[str, dict[str, int]] = {}
    for g in result.daily_greeks:
        key = str(g.date)
        entry = iv_by_date.setdefault(key, {"solved": 0, "fallback": 0, "failed": 0, "total": 0})
        entry["total"] += 1
        if g.iv_source == "bs_bisection":
            entry["solved"] += 1
        elif g.iv_source == "realized_vol_fallback":
            entry["fallback"] += 1
        else:
            entry["failed"] += 1

    if iv_by_date:
        lines += ["### Per-date IV summary", ""]
        iv_headers = ["Date", "Solved", "Fallback", "Failed", "Fallback rate"]
        iv_rows = [
            [
                date_str,
                f"{v['solved']}/{v['total']}",
                f"{v['fallback']}/{v['total']}",
                f"{v['failed']}/{v['total']}",
                _pct(v["fallback"], v["total"]),
            ]
            for date_str, v in sorted(iv_by_date.items())
        ]
        lines += [_md_table(iv_headers, iv_rows), ""]

    lines += [_SEP, ""]

    # --- Section 5: Backtest P&L ---
    hedge_improvement = cum_hedged - cum_unhedged
    spot_min = float(hedge_df["spot"].min()) if not hedge_df.empty else 0.0
    spot_max = float(hedge_df["spot"].max()) if not hedge_df.empty else 0.0

    lines += [
        "## 5. Backtest Results",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Period | {period_start} → {period_end} |",
        f"| Trading days | {total_days} |",
        f"| Contracts in book | {len(initial)} |",
        f"| SPY spot range | ${spot_min:.2f} – ${spot_max:.2f} |",
        f"| Cumulative P&L (hedged) | {_fmt_pnl(cum_hedged)} |",
        f"| Cumulative P&L (unhedged) | {_fmt_pnl(cum_unhedged)} |",
        f"| Hedge improvement | {_fmt_pnl(hedge_improvement)} |",
        f"| Total transaction costs | ${total_costs:,.2f} |",
        f"| Rebalances | {rebalances} / {total_days} days ({_pct(rebalances, total_days)}) |",
        f"| IV fallback rate | {result.fallback_rate_overall:.1%} |",
        "",
        _SEP,
        "",
    ]

    # --- Section 6: Limitations ---
    lines += ["## 6. Limitations", ""]
    for lim in result.limitations:
        lines.append(f"- {lim}")
    lines += [""]

    if atm_warned:
        lines += [
            "### Additional data coverage warning",
            "",
            f"> ⚠️ The confirmed LSEG RIC universe covers only strikes "
            f"${min_strike:.0f}–${max_strike:.0f}.",
            f"> At a spot of ${first_spot:.2f}, the nearest available contract "
            f"({initial[0].ric if initial else 'N/A'}) is "
            f"{abs(initial[0].moneyness_pct) * 100:.1f}% in-the-money." if initial else ">",
            f"> True ATM delta-hedging results would differ from those shown here.",
            "",
        ]

    return "\n".join(lines)
