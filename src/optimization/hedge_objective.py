"""Objective function for the delta-vega hedge optimizer.

Minimises:
    J = lambda_delta    × residual_delta²
      + lambda_vega     × residual_vega²
      + lambda_cost     × transaction_cost
      + lambda_turnover × turnover

Definitions:
    residual_delta = book_delta + h_underlying + Σ(w_i × delta_i × multiplier)
    residual_vega  = book_vega  + Σ(w_i × vega_i  × multiplier)
    transaction_cost = |h_underlying| × spot × bps/10000
                     + Σ |w_i| × mid_i × multiplier × bps/10000
    turnover = |h_underlying − prev_h| + Σ |w_i − prev_w_i|
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class HedgeObjectiveParams:
    lambda_delta: float = 1.0
    lambda_vega: float = 0.5
    lambda_cost: float = 0.05
    lambda_turnover: float = 0.02
    cost_bps: float = 2.0
    multiplier: int = 100


def compute_objective(
    h_underlying: float,
    option_weights: np.ndarray,
    candidate_deltas: np.ndarray,
    candidate_vegas: np.ndarray,
    candidate_mids: np.ndarray,
    spot: float,
    book_delta: float,
    book_vega: float,
    prev_h: float,
    prev_weights: np.ndarray,
    params: HedgeObjectiveParams,
) -> float:
    """Scalar hedge objective J (minimise this)."""
    mult = params.multiplier
    cost_rate = params.cost_bps / 10_000.0

    residual_delta = (
        book_delta
        + h_underlying
        + float(np.dot(option_weights, candidate_deltas)) * mult
    )
    residual_vega = book_vega + float(np.dot(option_weights, candidate_vegas)) * mult

    cost_h = abs(h_underlying) * spot * cost_rate
    cost_opts = float(np.sum(np.abs(option_weights) * candidate_mids)) * mult * cost_rate
    total_cost = cost_h + cost_opts

    turnover_h = abs(h_underlying - prev_h)
    turnover_opts = float(np.sum(np.abs(option_weights - prev_weights)))
    total_turnover = turnover_h + turnover_opts

    return (
        params.lambda_delta * residual_delta**2
        + params.lambda_vega * residual_vega**2
        + params.lambda_cost * total_cost
        + params.lambda_turnover * total_turnover
    )


def compute_residuals(
    h_underlying: float,
    option_weights: np.ndarray,
    candidate_deltas: np.ndarray,
    candidate_vegas: np.ndarray,
    book_delta: float,
    book_vega: float,
    multiplier: int = 100,
) -> tuple[float, float]:
    """Return (residual_delta, residual_vega) for a hedge allocation."""
    rd = book_delta + h_underlying + float(np.dot(option_weights, candidate_deltas)) * multiplier
    rv = book_vega + float(np.dot(option_weights, candidate_vegas)) * multiplier
    return rd, rv


def estimate_hedge_cost(
    h_underlying: float,
    option_weights: np.ndarray,
    candidate_mids: np.ndarray,
    spot: float,
    multiplier: int = 100,
    cost_bps: float = 2.0,
) -> float:
    """Estimate one-way transaction cost for a hedge allocation."""
    cost_rate = cost_bps / 10_000.0
    cost_h = abs(h_underlying) * spot * cost_rate
    cost_opts = float(np.sum(np.abs(option_weights) * candidate_mids)) * multiplier * cost_rate
    return cost_h + cost_opts
