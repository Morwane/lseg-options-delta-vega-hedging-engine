"""Delta-Vega hedge optimizer.

Compares four hedge methods for a given option book:

    1. no_hedge     — hold nothing; pure P&L exposure
    2. delta_only   — hedge underlying shares to zero net delta
    3. delta_vega   — add the best single LSEG option leg to also reduce vega
    4. optimized    — sparse scipy-optimized combination (underlying + ≤N options)

The optimizer uses scipy.optimize.minimize (SLSQP) on the objective defined in
hedge_objective.py. Sparsity for method 4 is enforced by using the top-N
candidates ranked by vega absorption ability.

No orders are placed. No live data is required. All inputs come from the
Black-Scholes Greeks computed during the LSEG historical backtest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from scipy.optimize import minimize  # type: ignore[import]

from src.optimization.hedge_objective import (
    HedgeObjectiveParams,
    compute_objective,
    compute_residuals,
    estimate_hedge_cost,
)
from src.optimization.hedge_universe import HedgeCandidate


@dataclass(frozen=True)
class OptimizerConfig:
    max_option_instruments: int = 2           # max option legs in optimized solution
    max_contracts_per_instrument: float = 5.0  # ± contract bound for each option
    max_underlying_shares: float = 500.0       # ± share bound for underlying hedge
    objective: HedgeObjectiveParams = field(default_factory=HedgeObjectiveParams)


@dataclass
class HedgeAllocation:
    method: Literal["no_hedge", "delta_only", "delta_vega", "optimized"]
    h_underlying: float                    # underlying shares (negative = short)
    option_weights: dict[str, float]       # ric → contracts
    residual_delta: float
    residual_vega: float
    transaction_cost: float
    objective_value: float
    selected_rics: list[str]


def _solve_no_hedge(book_delta: float, book_vega: float, params: HedgeObjectiveParams) -> HedgeAllocation:
    obj = params.lambda_delta * book_delta**2 + params.lambda_vega * book_vega**2
    return HedgeAllocation(
        method="no_hedge",
        h_underlying=0.0,
        option_weights={},
        residual_delta=book_delta,
        residual_vega=book_vega,
        transaction_cost=0.0,
        objective_value=obj,
        selected_rics=[],
    )


def _solve_delta_only(
    book_delta: float,
    book_vega: float,
    spot: float,
    prev_h: float,
    params: HedgeObjectiveParams,
) -> HedgeAllocation:
    h = -book_delta
    rd = 0.0
    rv = book_vega
    cost = abs(h) * spot * params.cost_bps / 10_000.0
    turnover = abs(h - prev_h)
    obj = (
        params.lambda_delta * rd**2
        + params.lambda_vega * rv**2
        + params.lambda_cost * cost
        + params.lambda_turnover * turnover
    )
    return HedgeAllocation(
        method="delta_only",
        h_underlying=h,
        option_weights={},
        residual_delta=rd,
        residual_vega=rv,
        transaction_cost=cost,
        objective_value=obj,
        selected_rics=[],
    )


def _solve_delta_vega_single(
    book_delta: float,
    book_vega: float,
    candidate: HedgeCandidate,
    spot: float,
    prev_h: float,
    prev_w: float,
    params: HedgeObjectiveParams,
) -> tuple[float, float, float]:
    """Analytic closed-form for one-option + underlying.

    Solves for vega first (w = -book_vega / (vega × mult)), then delta (h).
    Returns (h_underlying, w_contracts, objective_value).
    """
    mult = params.multiplier
    if abs(candidate.vega) < 1e-9:
        return 0.0, 0.0, float("inf")

    w = -book_vega / (candidate.vega * mult)
    w = float(np.clip(w, -params.multiplier * 5, params.multiplier * 5))
    h = -book_delta - w * candidate.delta * mult

    obj = compute_objective(
        h_underlying=h,
        option_weights=np.array([w]),
        candidate_deltas=np.array([candidate.delta]),
        candidate_vegas=np.array([candidate.vega]),
        candidate_mids=np.array([candidate.mid]),
        spot=spot,
        book_delta=book_delta,
        book_vega=book_vega,
        prev_h=prev_h,
        prev_weights=np.array([prev_w]),
        params=params,
    )
    return h, w, obj


def _solve_optimized_subset(
    book_delta: float,
    book_vega: float,
    candidates: list[HedgeCandidate],
    spot: float,
    prev_h: float,
    prev_weights: np.ndarray,
    params: HedgeObjectiveParams,
    max_shares: float,
    max_contracts: float,
) -> tuple[float, np.ndarray, float]:
    """scipy SLSQP optimization over a fixed candidate subset.

    Returns (h_underlying, option_weights_array, objective_value).
    """
    n = len(candidates)
    if n == 0:
        return 0.0, np.zeros(0), float("inf")

    deltas = np.array([c.delta for c in candidates])
    vegas = np.array([c.vega for c in candidates])
    mids = np.array([c.mid for c in candidates])

    def objective_fn(x: np.ndarray) -> float:
        return compute_objective(
            h_underlying=x[0],
            option_weights=x[1:],
            candidate_deltas=deltas,
            candidate_vegas=vegas,
            candidate_mids=mids,
            spot=spot,
            book_delta=book_delta,
            book_vega=book_vega,
            prev_h=prev_h,
            prev_weights=prev_weights,
            params=params,
        )

    # Warm-start: underlying = delta-neutral; options = 0
    x0 = np.zeros(n + 1)
    x0[0] = -book_delta

    bounds = [(-max_shares, max_shares)] + [(-max_contracts, max_contracts)] * n

    res = minimize(objective_fn, x0, method="SLSQP", bounds=bounds,
                   options={"maxiter": 300, "ftol": 1e-12})

    if not res.success and res.fun > 1e8:
        return 0.0, np.zeros(n), float("inf")

    return float(res.x[0]), res.x[1:], float(res.fun)


def optimize_hedge(
    book_delta: float,
    book_vega: float,
    candidates: list[HedgeCandidate],
    prev_h: float,
    prev_option_weights: dict[str, float],
    spot: float,
    config: OptimizerConfig,
) -> dict[str, HedgeAllocation]:
    """Run all four hedge methods and return a result for each.

    Returns:
        dict with keys 'no_hedge', 'delta_only', 'delta_vega', 'optimized'.
    """
    params = config.objective
    mult = params.multiplier
    results: dict[str, HedgeAllocation] = {}

    # ── Method 1: No hedge ─────────────────────────────────────────────────────
    results["no_hedge"] = _solve_no_hedge(book_delta, book_vega, params)

    # ── Method 2: Delta-only ───────────────────────────────────────────────────
    results["delta_only"] = _solve_delta_only(book_delta, book_vega, spot, prev_h, params)

    # ── Method 3: Delta-Vega (best single option) ──────────────────────────────
    best_dv_h = -book_delta
    best_dv_w = 0.0
    best_dv_ric: str = ""
    best_dv_obj = float("inf")

    for cand in candidates:
        prev_w_c = prev_option_weights.get(cand.ric, 0.0)
        h3, w3, obj3 = _solve_delta_vega_single(
            book_delta, book_vega, cand, spot, prev_h, prev_w_c, params
        )
        if obj3 < best_dv_obj:
            best_dv_obj, best_dv_h, best_dv_w, best_dv_ric = obj3, h3, w3, cand.ric

    if best_dv_ric:
        best_cand = next(c for c in candidates if c.ric == best_dv_ric)
        rd3, rv3 = compute_residuals(
            best_dv_h, np.array([best_dv_w]),
            np.array([best_cand.delta]), np.array([best_cand.vega]),
            book_delta, book_vega, mult,
        )
        cost3 = estimate_hedge_cost(
            best_dv_h, np.array([best_dv_w]), np.array([best_cand.mid]),
            spot, mult, params.cost_bps,
        )
        results["delta_vega"] = HedgeAllocation(
            method="delta_vega",
            h_underlying=best_dv_h,
            option_weights={best_dv_ric: best_dv_w},
            residual_delta=rd3,
            residual_vega=rv3,
            transaction_cost=cost3,
            objective_value=best_dv_obj,
            selected_rics=[best_dv_ric],
        )
    else:
        # Fall back to delta-only when no candidates pass filters
        dv_fallback = results["delta_only"]
        results["delta_vega"] = HedgeAllocation(
            method="delta_vega",
            h_underlying=dv_fallback.h_underlying,
            option_weights={},
            residual_delta=dv_fallback.residual_delta,
            residual_vega=dv_fallback.residual_vega,
            transaction_cost=dv_fallback.transaction_cost,
            objective_value=dv_fallback.objective_value,
            selected_rics=[],
        )

    # ── Method 4: Optimized sparse hedge ───────────────────────────────────────
    top_n = min(config.max_option_instruments, len(candidates))

    if top_n == 0:
        # Mirror delta_only when no candidates available
        d_only = results["delta_only"]
        results["optimized"] = HedgeAllocation(
            method="optimized",
            h_underlying=d_only.h_underlying,
            option_weights={},
            residual_delta=d_only.residual_delta,
            residual_vega=d_only.residual_vega,
            transaction_cost=d_only.transaction_cost,
            objective_value=d_only.objective_value,
            selected_rics=[],
        )
    else:
        top_cands = candidates[:top_n]
        prev_w_arr = np.array([prev_option_weights.get(c.ric, 0.0) for c in top_cands])

        h4, w4_arr, obj4 = _solve_optimized_subset(
            book_delta, book_vega, top_cands, spot, prev_h, prev_w_arr, params,
            config.max_underlying_shares, config.max_contracts_per_instrument,
        )

        deltas4 = np.array([c.delta for c in top_cands])
        vegas4 = np.array([c.vega for c in top_cands])
        mids4 = np.array([c.mid for c in top_cands])

        rd4, rv4 = compute_residuals(h4, w4_arr, deltas4, vegas4, book_delta, book_vega, mult)
        cost4 = estimate_hedge_cost(h4, w4_arr, mids4, spot, mult, params.cost_bps)

        opt_weights: dict[str, float] = {}
        selected4: list[str] = []
        for i, cand in enumerate(top_cands):
            w_i = float(w4_arr[i]) if i < len(w4_arr) else 0.0
            if abs(w_i) > 0.01:
                opt_weights[cand.ric] = round(w_i, 4)
                selected4.append(cand.ric)

        results["optimized"] = HedgeAllocation(
            method="optimized",
            h_underlying=h4,
            option_weights=opt_weights,
            residual_delta=rd4,
            residual_vega=rv4,
            transaction_cost=cost4,
            objective_value=obj4,
            selected_rics=selected4,
        )

    return results
