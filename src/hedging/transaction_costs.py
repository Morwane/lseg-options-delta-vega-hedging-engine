"""Transaction cost estimation for hedge orders."""
from __future__ import annotations


def estimate_transaction_cost(
    quantity: float,
    spot: float,
    cost_bps: float,
    bid: float | None = None,
    ask: float | None = None,
) -> float:
    """Estimate round-trip transaction cost for a hedge order.

    Uses half-spread when bid and ask are both available; falls back to a
    flat bps charge on notional otherwise.

    Args:
        quantity:  Signed order quantity (shares). Sign is ignored for cost.
        spot:      Mid-price or last price of the underlying.
        cost_bps:  Fallback cost in basis points (e.g. 2.0 = 2 bps).
        bid:       Best bid price. Used only when ask is also provided.
        ask:       Best ask price. Used only when bid is also provided.

    Returns:
        Estimated cost in USD (always non-negative).
    """
    abs_qty = abs(quantity)
    if abs_qty == 0.0:
        return 0.0

    if bid is not None and ask is not None:
        half_spread = (ask - bid) / 2.0
        return abs_qty * half_spread

    return abs_qty * spot * cost_bps / 10_000.0
