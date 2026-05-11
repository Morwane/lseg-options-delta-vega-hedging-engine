"""Delta hedge recommendation engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.hedging.rebalance_rules import HedgeRules
from src.hedging.transaction_costs import estimate_transaction_cost


@dataclass(frozen=True)
class HedgeRecommendation:
    underlying: str
    portfolio_delta: float
    current_underlying_position: float
    target_underlying_position: float
    order_quantity: float           # 0.0 when side is NONE
    side: Literal["BUY", "SELL", "NONE"]
    spot: float
    estimated_notional: float
    estimated_transaction_cost: float
    reason: str
    blocked: bool                   # True when notional exceeds max — requires manual review


def recommend_delta_hedge(
    underlying: str,
    portfolio_delta: float,
    current_underlying_position: float,
    spot: float,
    rules: HedgeRules,
) -> HedgeRecommendation:
    """Compute a delta hedge recommendation for one underlying.

    Formula:
        target_underlying_position = -portfolio_delta
        order_quantity = target - current_underlying_position

    Side is NONE when |order_quantity| < delta_threshold_shares.
    Blocked is True when the notional exceeds max_order_notional_usd.
    """
    target = -portfolio_delta
    raw_order = target - current_underlying_position

    # Below threshold — no hedge needed
    if abs(raw_order) < rules.delta_threshold_shares:
        return HedgeRecommendation(
            underlying=underlying,
            portfolio_delta=portfolio_delta,
            current_underlying_position=current_underlying_position,
            target_underlying_position=target,
            order_quantity=0.0,
            side="NONE",
            spot=spot,
            estimated_notional=0.0,
            estimated_transaction_cost=0.0,
            reason=(
                f"|order| {abs(raw_order):.2f} < threshold "
                f"{rules.delta_threshold_shares} shares — no hedge"
            ),
            blocked=False,
        )

    side: Literal["BUY", "SELL"] = "BUY" if raw_order > 0 else "SELL"
    notional = abs(raw_order) * spot
    cost = estimate_transaction_cost(
        raw_order, spot, rules.fallback_transaction_cost_bps
    )

    # Exceeds max notional — flag for manual review
    if notional > rules.max_order_notional_usd:
        return HedgeRecommendation(
            underlying=underlying,
            portfolio_delta=portfolio_delta,
            current_underlying_position=current_underlying_position,
            target_underlying_position=target,
            order_quantity=raw_order,
            side=side,
            spot=spot,
            estimated_notional=notional,
            estimated_transaction_cost=cost,
            reason=(
                f"notional ${notional:,.0f} exceeds max "
                f"${rules.max_order_notional_usd:,.0f} — manual review required"
            ),
            blocked=True,
        )

    # Valid, executable recommendation
    return HedgeRecommendation(
        underlying=underlying,
        portfolio_delta=portfolio_delta,
        current_underlying_position=current_underlying_position,
        target_underlying_position=target,
        order_quantity=raw_order,
        side=side,
        spot=spot,
        estimated_notional=notional,
        estimated_transaction_cost=cost,
        reason=(
            f"portfolio delta {portfolio_delta:.2f} requires {side} "
            f"{abs(raw_order):.2f} shares of {underlying}"
        ),
        blocked=False,
    )
