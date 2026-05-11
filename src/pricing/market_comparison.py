"""Market price vs Black-Scholes model price diagnostic.

gap_bps = (market_mid - bs_price) / bs_price × 10 000

This gap is a model-fit diagnostic only.
It is NOT a trading signal and MUST NOT be used for order generation.

Typical sources of the gap for deep-ITM calls:
    - Bid/ask bounce around the reported mid
    - Model parameter uncertainty (IV, dividend yield, risk-free rate)
    - Discrete vs continuous dividend treatment
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MarketVsBSResult:
    ric: str
    date: date
    market_mid: float
    bs_price: float
    gap_usd: float
    gap_bps: float    # diagnostic only — not a signal


def compute_market_vs_bs(
    market_mid: float,
    bs_price: float,
    ric: str,
    result_date: date,
) -> MarketVsBSResult:
    """Compute the diagnostic gap between market mid and Black-Scholes model price.

    Args:
        market_mid:   Observed (bid+ask)/2 from LSEG.
        bs_price:     Black-Scholes theoretical price computed from implied vol.
        ric:          Option RIC identifier.
        result_date:  Observation date.

    Returns:
        MarketVsBSResult with gap in both USD and basis points.

    Raises:
        ValueError — if bs_price <= 0 (undefined gap).
    """
    if bs_price <= 0:
        raise ValueError(
            f"bs_price must be positive to compute gap, got {bs_price:.6f} for {ric}"
        )
    gap_usd = market_mid - bs_price
    gap_bps = gap_usd / bs_price * 10_000.0
    return MarketVsBSResult(
        ric=ric,
        date=result_date,
        market_mid=market_mid,
        bs_price=bs_price,
        gap_usd=gap_usd,
        gap_bps=gap_bps,
    )
