"""Candidate hedge instrument selection and filtering.

Selects option instruments from the LSEG-audited RIC universe that are
suitable as hedge legs based on liquidity, IV-solve success, and moneyness.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HedgeCandidate:
    ric: str
    option_type: str        # "call" | "put"
    strike: float
    delta: float            # BS delta per share
    gamma: float
    vega: float             # BS vega per share (∂V/∂σ)
    theta: float
    bid: float
    ask: float
    mid: float
    spread_bps: float       # (ask - bid) / mid × 10 000
    iv: float
    iv_solved: bool         # True when BS bisection succeeded
    moneyness_pct: float    # (S − K) / K × 100; positive = ITM call


@dataclass(frozen=True)
class HedgeUniverseConfig:
    max_spread_bps: float = 300.0       # reject if spread > N bps
    max_moneyness_abs_pct: float = 15.0 # reject deep ITM / OTM
    require_iv_solved: bool = True       # reject if IV bisection failed
    min_vega: float = 0.005             # reject near-zero-vega contracts
    max_candidates: int = 20            # keep the N best (tightest spread)


def build_hedge_universe(
    daily_greeks: list[Any],       # list[DailyContractGreeks]
    config: HedgeUniverseConfig,
) -> list[HedgeCandidate]:
    """Filter and rank candidate hedge instruments for one trading day.

    Args:
        daily_greeks: Per-contract Greek records produced by the backtest engine.
        config:       Liquidity and quality filters.

    Returns:
        Ranked list of HedgeCandidate (tightest spread first).
    """
    candidates: list[HedgeCandidate] = []

    for g in daily_greeks:
        if g.delta is None or g.vega is None or g.gamma is None:
            continue
        if not (math.isfinite(g.delta) and math.isfinite(g.vega)):
            continue

        if not (math.isfinite(g.bid) and math.isfinite(g.ask)):
            continue
        if g.bid <= 0 or g.ask <= 0 or g.ask <= g.bid:
            continue

        if config.require_iv_solved and g.iv_source != "bs_bisection":
            continue

        mid = (g.bid + g.ask) / 2.0
        spread_bps = (g.ask - g.bid) / mid * 10_000.0
        if spread_bps > config.max_spread_bps:
            continue

        moneyness_pct = (g.spot - g.strike) / g.strike * 100.0
        if abs(moneyness_pct) > config.max_moneyness_abs_pct:
            continue

        if abs(g.vega) < config.min_vega:
            continue

        candidates.append(
            HedgeCandidate(
                ric=g.ric,
                option_type="call",
                strike=g.strike,
                delta=g.delta,
                gamma=g.gamma,
                vega=g.vega,
                theta=g.theta if g.theta is not None else 0.0,
                bid=g.bid,
                ask=g.ask,
                mid=mid,
                spread_bps=spread_bps,
                iv=g.iv if g.iv is not None else 0.0,
                iv_solved=(g.iv_source == "bs_bisection"),
                moneyness_pct=moneyness_pct,
            )
        )

    candidates.sort(key=lambda c: (c.spread_bps, -abs(c.vega)))
    return candidates[: config.max_candidates]
