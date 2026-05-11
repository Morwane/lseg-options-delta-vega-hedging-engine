"""Build IBKR order specifications from hedge recommendations.

This module is purely data — it never submits orders. transmit is always False
so that even if an IBKROrderSpec were inadvertently passed to ib_insync's
placeOrder(), it would not be transmitted to the exchange.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.hedging.delta_hedger import HedgeRecommendation


@dataclass(frozen=True)
class IBKROrderSpec:
    """Specification for an IBKR market order.

    total_quantity is always positive; action ("BUY"/"SELL") encodes direction.
    transmit is always False — orders are never auto-submitted from dry-run mode.
    """
    action: Literal["BUY", "SELL"]
    total_quantity: float       # whole shares, always > 0
    order_type: str = field(default="MKT")
    tif: str = field(default="DAY")     # time-in-force
    transmit: bool = field(default=False)


def build_market_order(rec: HedgeRecommendation) -> IBKROrderSpec | None:
    """Build an IBKROrderSpec from a hedge recommendation.

    Returns None when:
    - rec.side is "NONE" (below threshold — no hedge needed), or
    - rec.blocked is True (notional exceeds limit — requires manual review).

    The returned spec has transmit=False and is never submitted automatically.
    """
    if rec.side == "NONE" or rec.blocked:
        return None
    return IBKROrderSpec(
        action=rec.side,  # "BUY" or "SELL"
        total_quantity=float(round(abs(rec.order_quantity))),  # whole shares
    )
