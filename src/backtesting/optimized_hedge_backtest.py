"""Four-method hedge comparison backtest.

Runs the same LSEG option book through four hedge strategies in parallel:

    1. no_hedge     — zero hedge; pure mark-to-market book P&L
    2. delta_only   — net-delta neutral via underlying shares only
    3. delta_vega   — delta + vega neutral via underlying + best single option
    4. optimized    — scipy-optimized sparse combination (underlying + ≤N options)

Uses the identical option book, spot series, and Black-Scholes Greeks as
the delta-only backtest (historical_delta_hedge_engine.py).  No IBKR
connection is used or required.

Output files:
    outputs/research/hedge_optimizer_daily_results.csv
    outputs/research/hedge_optimizer_candidate_universe.csv
    outputs/research/hedge_optimizer_selected_instruments.csv
    outputs/research/hedge_optimizer_summary.csv
    outputs/research/residual_greeks_by_method.csv
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.backtesting.contract_selection import select_atm_contracts
from src.backtesting.historical_delta_hedge_engine import (
    HistoricalBacktestConfig,
    _build_bar_lookup,
    _compute_portfolio_greeks_for_date,
    _rolling_realized_vol,
)
from src.backtesting.option_history_loader import decode_strike_from_ric
from src.optimization.delta_vega_optimizer import HedgeAllocation, OptimizerConfig, optimize_hedge
from src.optimization.hedge_universe import HedgeUniverseConfig, build_hedge_universe

METHODS = ("no_hedge", "delta_only", "delta_vega", "optimized")


@dataclass
class MethodDayResult:
    date: date
    method: str
    spot: float
    book_delta: float
    book_vega: float
    h_underlying: float
    option_weights_repr: str
    residual_delta: float
    residual_vega: float
    option_pnl: float
    hedge_pnl: float
    transaction_cost: float
    net_pnl: float
    cumulative_net_pnl: float
    selected_rics: str


@dataclass
class OptimizedBacktestResult:
    daily_results: list[MethodDayResult]
    summary_by_method: list[dict[str, Any]]
    candidate_universe_rows: list[dict[str, Any]]
    selected_instrument_rows: list[dict[str, Any]]


def run_optimized_backtest(
    config: HistoricalBacktestConfig,
    option_history: pd.DataFrame,
    spy_history: pd.DataFrame,
    optimizer_config: OptimizerConfig | None = None,
    universe_config: HedgeUniverseConfig | None = None,
) -> OptimizedBacktestResult:
    """Run the four-method hedge comparison on the LSEG option book.

    Args:
        config:           Loaded HistoricalBacktestConfig.
        option_history:   DataFrame with columns (date, ric, bid, ask).
        spy_history:      DataFrame with columns (date, spot).
        optimizer_config: Override optimizer parameters (defaults used if None).
        universe_config:  Override hedge-universe filters (defaults used if None).

    Returns:
        OptimizedBacktestResult with daily results and per-method summaries.
    """
    if optimizer_config is None:
        optimizer_config = OptimizerConfig()
    if universe_config is None:
        universe_config = HedgeUniverseConfig()

    # ── Normalise inputs ──────────────────────────────────────────────────────
    option_history = option_history.copy()
    option_history["date"] = pd.to_datetime(option_history["date"]).dt.date
    spy_history = spy_history.copy()
    spy_history["date"] = pd.to_datetime(spy_history["date"]).dt.date
    spy_history = spy_history.sort_values("date").reset_index(drop=True)

    spot_by_date: dict[date, float] = dict(zip(spy_history["date"], spy_history["spot"]))
    spot_series = spy_history.set_index("date")["spot"]
    rv_series = _rolling_realized_vol(
        pd.Series(spot_series.values, index=spot_series.index),
        window=config.iv_fallback_vol_window_days,
    )
    rv_by_date: dict[date, float] = {k: float(v) for k, v in rv_series.dropna().items()}

    dates = sorted(spot_by_date.keys())
    if len(dates) < 2:
        raise ValueError("Need at least 2 trading dates.")

    bar_lookup = _build_bar_lookup(option_history)

    # ── Initial contract selection ─────────────────────────────────────────────
    first_date = dates[0]
    first_spot = spot_by_date[first_date]
    init_result = select_atm_contracts(
        selection_date=first_date,
        option_history=option_history,
        spot=first_spot,
        top_n=config.atm_contract_count,
    )
    if not init_result.selected:
        raise RuntimeError("No valid contracts for initial ATM selection.")

    selected_rics = init_result.selected_rics
    ric_strikes = {ric: decode_strike_from_ric(ric) for ric in selected_rics}
    qty_per_contract = config.contracts_per_position * config.contract_multiplier

    # ── Per-method state ──────────────────────────────────────────────────────
    cum_pnl: dict[str, float] = {m: 0.0 for m in METHODS}
    h_prev: dict[str, float] = {m: 0.0 for m in METHODS}
    opt_w_prev: dict[str, dict[str, float]] = {m: {} for m in METHODS}

    daily_results: list[MethodDayResult] = []
    cand_rows: list[dict[str, Any]] = []
    sel_rows: list[dict[str, Any]] = []

    # ── Day 0 ─────────────────────────────────────────────────────────────────
    d0_delta, d0_greeks = _compute_portfolio_greeks_for_date(
        d=first_date, rics=selected_rics, ric_strikes=ric_strikes,
        spot=first_spot, config=config, rv_by_date=rv_by_date,
        bar_lookup=bar_lookup, qty_per_contract=qty_per_contract,
    )
    d0_vega = _sum_vega(d0_greeks, qty_per_contract)

    cands_d0 = build_hedge_universe(d0_greeks, universe_config)
    _record_candidates(cand_rows, first_date, cands_d0)

    allocs_d0 = optimize_hedge(
        book_delta=d0_delta, book_vega=d0_vega, candidates=cands_d0,
        prev_h=0.0, prev_option_weights={}, spot=first_spot, config=optimizer_config,
    )

    cost_bps = optimizer_config.objective.cost_bps
    mult = optimizer_config.objective.multiplier

    for method in METHODS:
        alloc = allocs_d0[method]
        init_cost = abs(alloc.h_underlying) * first_spot * cost_bps / 10_000.0
        cum_pnl[method] = -init_cost
        h_prev[method] = alloc.h_underlying
        opt_w_prev[method] = dict(alloc.option_weights)

        daily_results.append(
            MethodDayResult(
                date=first_date, method=method, spot=first_spot,
                book_delta=d0_delta, book_vega=d0_vega,
                h_underlying=alloc.h_underlying,
                option_weights_repr=repr(alloc.option_weights),
                residual_delta=alloc.residual_delta, residual_vega=alloc.residual_vega,
                option_pnl=0.0, hedge_pnl=0.0,
                transaction_cost=init_cost, net_pnl=-init_cost,
                cumulative_net_pnl=cum_pnl[method],
                selected_rics=",".join(alloc.selected_rics),
            )
        )
        for ric in alloc.selected_rics:
            sel_rows.append({
                "date": str(first_date), "method": method, "ric": ric,
                "weight": alloc.option_weights.get(ric, 0.0),
            })

    prev_date = first_date

    # ── Main loop ─────────────────────────────────────────────────────────────
    for t in range(1, len(dates)):
        cur_date = dates[t]
        cur_spot = spot_by_date[cur_date]
        prev_spot = spot_by_date[prev_date]

        # Book P&L (same for all methods — identical option book)
        option_pnl_today = _compute_option_pnl(selected_rics, prev_date, cur_date,
                                                bar_lookup, qty_per_contract)

        portfolio_delta, today_greeks = _compute_portfolio_greeks_for_date(
            d=cur_date, rics=selected_rics, ric_strikes=ric_strikes,
            spot=cur_spot, config=config, rv_by_date=rv_by_date,
            bar_lookup=bar_lookup, qty_per_contract=qty_per_contract,
        )
        portfolio_vega = _sum_vega(today_greeks, qty_per_contract)

        today_cands = build_hedge_universe(today_greeks, universe_config)
        _record_candidates(cand_rows, cur_date, today_cands)

        allocs = optimize_hedge(
            book_delta=portfolio_delta, book_vega=portfolio_vega,
            candidates=today_cands,
            prev_h=h_prev["optimized"],
            prev_option_weights=opt_w_prev["optimized"],
            spot=cur_spot, config=optimizer_config,
        )

        for method in METHODS:
            alloc = allocs[method]

            hedge_pnl_h = h_prev[method] * (cur_spot - prev_spot)
            hedge_pnl_opts = _compute_option_hedge_pnl(
                opt_w_prev[method], prev_date, cur_date, bar_lookup, mult
            )
            hedge_pnl = hedge_pnl_h + hedge_pnl_opts

            # Rebalancing costs
            dh = alloc.h_underlying - h_prev[method]
            cost_h = abs(dh) * cur_spot * cost_bps / 10_000.0
            cost_opts = _compute_rebal_cost(
                alloc.option_weights, opt_w_prev[method],
                cur_date, bar_lookup, mult, cost_bps,
            )
            tx_cost = cost_h + cost_opts

            net_pnl = option_pnl_today + hedge_pnl - tx_cost
            cum_pnl[method] += net_pnl

            h_prev[method] = alloc.h_underlying
            opt_w_prev[method] = dict(alloc.option_weights)

            daily_results.append(
                MethodDayResult(
                    date=cur_date, method=method, spot=cur_spot,
                    book_delta=portfolio_delta, book_vega=portfolio_vega,
                    h_underlying=alloc.h_underlying,
                    option_weights_repr=repr(alloc.option_weights),
                    residual_delta=alloc.residual_delta,
                    residual_vega=alloc.residual_vega,
                    option_pnl=option_pnl_today, hedge_pnl=hedge_pnl,
                    transaction_cost=tx_cost, net_pnl=net_pnl,
                    cumulative_net_pnl=cum_pnl[method],
                    selected_rics=",".join(alloc.selected_rics),
                )
            )
            for ric in alloc.selected_rics:
                sel_rows.append({
                    "date": str(cur_date), "method": method, "ric": ric,
                    "weight": alloc.option_weights.get(ric, 0.0),
                })

        prev_date = cur_date

    # ── Summary by method ─────────────────────────────────────────────────────
    df_all = pd.DataFrame(
        [
            {
                "method": r.method, "date": r.date, "net_pnl": r.net_pnl,
                "cumulative_net_pnl": r.cumulative_net_pnl,
                "residual_delta": r.residual_delta, "residual_vega": r.residual_vega,
                "transaction_cost": r.transaction_cost,
            }
            for r in daily_results
        ]
    )
    summaries = _build_summaries(df_all)

    return OptimizedBacktestResult(
        daily_results=daily_results,
        summary_by_method=summaries,
        candidate_universe_rows=cand_rows,
        selected_instrument_rows=sel_rows,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sum_vega(greeks_list: list, qty: int) -> float:
    return sum(
        g.vega * qty for g in greeks_list
        if g.vega is not None and math.isfinite(g.vega)
    )


def _compute_option_pnl(rics, prev_date, cur_date, bar_lookup, qty) -> float:
    pnl = 0.0
    for ric in rics:
        pb = bar_lookup.get((prev_date, ric))
        cb = bar_lookup.get((cur_date, ric))
        if pb and cb:
            pnl += (cb[2] - pb[2]) * qty
    return pnl


def _compute_option_hedge_pnl(weights, prev_date, cur_date, bar_lookup, mult) -> float:
    pnl = 0.0
    for ric, w in weights.items():
        pb = bar_lookup.get((prev_date, ric))
        cb = bar_lookup.get((cur_date, ric))
        if pb and cb:
            pnl += w * (cb[2] - pb[2]) * mult
    return pnl


def _compute_rebal_cost(new_weights, old_weights, cur_date, bar_lookup, mult, cost_bps) -> float:
    cost_rate = cost_bps / 10_000.0
    cost = 0.0
    all_rics = set(new_weights) | set(old_weights)
    for ric in all_rics:
        dw = abs(new_weights.get(ric, 0.0) - old_weights.get(ric, 0.0))
        bar = bar_lookup.get((cur_date, ric))
        if bar and dw > 0:
            cost += dw * bar[2] * mult * cost_rate
    return cost


def _record_candidates(rows, d, candidates) -> None:
    for c in candidates:
        rows.append({
            "date": str(d), "ric": c.ric, "strike": c.strike,
            "delta": round(c.delta, 6), "vega": round(c.vega, 6),
            "spread_bps": round(c.spread_bps, 1), "iv": round(c.iv, 4),
            "moneyness_pct": round(c.moneyness_pct, 2),
        })


def _build_summaries(df: pd.DataFrame) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for method in METHODS:
        mdf = df[df["method"] == method]
        if mdf.empty:
            continue
        pnl_s = mdf["net_pnl"]
        cum_s = mdf["cumulative_net_pnl"]
        summaries.append({
            "method": method,
            "total_net_pnl": round(float(cum_s.iloc[-1]), 2),
            "pnl_volatility": round(float(pnl_s.std()), 4),
            "max_drawdown": round(float((cum_s - cum_s.cummax()).min()), 2),
            "avg_abs_residual_delta": round(float(mdf["residual_delta"].abs().mean()), 4),
            "avg_abs_residual_vega": round(float(mdf["residual_vega"].abs().mean()), 4),
            "total_transaction_costs": round(float(mdf["transaction_cost"].sum()), 2),
            "trading_days": len(mdf),
        })
    return summaries


def to_daily_df(results: list[MethodDayResult]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": r.date, "method": r.method, "spot": r.spot,
                "book_delta": round(r.book_delta, 4),
                "book_vega": round(r.book_vega, 4),
                "h_underlying": round(r.h_underlying, 4),
                "option_weights": r.option_weights_repr,
                "residual_delta": round(r.residual_delta, 4),
                "residual_vega": round(r.residual_vega, 4),
                "option_pnl": round(r.option_pnl, 4),
                "hedge_pnl": round(r.hedge_pnl, 4),
                "transaction_cost": round(r.transaction_cost, 4),
                "net_pnl": round(r.net_pnl, 4),
                "cumulative_net_pnl": round(r.cumulative_net_pnl, 4),
                "selected_rics": r.selected_rics,
            }
            for r in results
        ]
    )
