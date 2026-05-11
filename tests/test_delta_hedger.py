"""Tests for the delta hedge recommendation engine."""
import pytest

from src.hedging.delta_hedger import recommend_delta_hedge
from src.hedging.rebalance_rules import HedgeRules

# Standard rules used across most tests
_RULES = HedgeRules(
    paper_trading_only=True,
    allow_live_trading=False,
    dry_run_default=True,
    manual_approval_required=True,
    delta_threshold_shares=100.0,
    max_order_notional_usd=25_000.0,
    min_rebalance_interval_minutes=30,
    fallback_transaction_cost_bps=2.0,
)
_SPOT = 500.0


# --- HedgeRules validation ---

def test_hedge_rules_rejects_allow_live_trading() -> None:
    with pytest.raises(ValueError, match="allow_live_trading"):
        HedgeRules(
            paper_trading_only=True,
            allow_live_trading=True,    # forbidden
            dry_run_default=True,
            manual_approval_required=True,
            delta_threshold_shares=100.0,
            max_order_notional_usd=25_000.0,
            min_rebalance_interval_minutes=30,
            fallback_transaction_cost_bps=2.0,
        )

def test_hedge_rules_rejects_paper_trading_false() -> None:
    with pytest.raises(ValueError, match="paper_trading_only"):
        HedgeRules(
            paper_trading_only=False,   # forbidden
            allow_live_trading=False,
            dry_run_default=True,
            manual_approval_required=True,
            delta_threshold_shares=100.0,
            max_order_notional_usd=25_000.0,
            min_rebalance_interval_minutes=30,
            fallback_transaction_cost_bps=2.0,
        )


# --- Below threshold: NONE ---

def test_below_threshold_returns_none_side() -> None:
    rec = recommend_delta_hedge("SPY", portfolio_delta=50.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.side == "NONE"

def test_below_threshold_order_quantity_is_zero() -> None:
    rec = recommend_delta_hedge("SPY", portfolio_delta=50.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.order_quantity == 0.0

def test_below_threshold_not_blocked() -> None:
    rec = recommend_delta_hedge("SPY", portfolio_delta=50.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.blocked is False

def test_below_threshold_zero_cost() -> None:
    rec = recommend_delta_hedge("SPY", portfolio_delta=50.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.estimated_transaction_cost == 0.0

def test_exactly_at_threshold_triggers_hedge() -> None:
    # |raw_order| == threshold → fires the hedge (condition is strict <, so == triggers)
    rec = recommend_delta_hedge("SPY", portfolio_delta=-100.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.side == "BUY"


# --- Direction (sign conventions) ---

def test_positive_portfolio_delta_gives_sell() -> None:
    # portfolio is long delta → hedge by selling underlying
    rec = recommend_delta_hedge("SPY", portfolio_delta=200.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.side == "SELL"
    assert rec.order_quantity < 0.0

def test_negative_portfolio_delta_gives_buy() -> None:
    # portfolio is short delta → hedge by buying underlying
    rec = recommend_delta_hedge("SPY", portfolio_delta=-200.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.side == "BUY"
    assert rec.order_quantity > 0.0


# --- Target and order quantity formula ---

def test_target_is_negative_portfolio_delta() -> None:
    delta = 300.0
    rec = recommend_delta_hedge("SPY", portfolio_delta=delta, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert abs(rec.target_underlying_position - (-delta)) < 1e-9

def test_order_quantity_is_target_minus_current() -> None:
    delta = -300.0
    current = 50.0
    rec = recommend_delta_hedge("SPY", portfolio_delta=delta, current_underlying_position=current,
                                spot=_SPOT, rules=_RULES)
    expected_order = (-delta) - current   # 300 - 50 = 250
    assert abs(rec.order_quantity - expected_order) < 1e-9

def test_current_position_offsets_order() -> None:
    # portfolio_delta=-200 → target=+200; if already holding 200 → order=0 (below threshold)
    rec = recommend_delta_hedge("SPY", portfolio_delta=-200.0, current_underlying_position=200.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.side == "NONE"


# --- Notional cap (blocked) ---

def test_large_order_is_blocked() -> None:
    # 300 shares * $500 = $150,000 > $25,000 max notional
    rec = recommend_delta_hedge("SPY", portfolio_delta=300.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.blocked is True

def test_blocked_side_is_still_set() -> None:
    rec = recommend_delta_hedge("SPY", portfolio_delta=300.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.side == "SELL"

def test_small_order_within_notional_not_blocked() -> None:
    # 200 shares * $10 spot = $2,000 < $25,000 max notional → not blocked
    rec = recommend_delta_hedge("SPY", portfolio_delta=-200.0, current_underlying_position=0.0,
                                spot=10.0, rules=_RULES)
    assert rec.blocked is False

def test_blocked_order_quantity_is_raw_not_capped() -> None:
    # When blocked, the full raw order qty is preserved (not capped)
    rec = recommend_delta_hedge("SPY", portfolio_delta=300.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    expected_raw = -300.0  # target=-300, current=0
    assert abs(rec.order_quantity - expected_raw) < 1e-9


# --- Fields populated correctly ---

def test_underlying_field_is_passed_through() -> None:
    rec = recommend_delta_hedge("QQQ", portfolio_delta=-200.0, current_underlying_position=0.0,
                                spot=400.0, rules=_RULES)
    assert rec.underlying == "QQQ"

def test_spot_field_is_passed_through() -> None:
    rec = recommend_delta_hedge("SPY", portfolio_delta=-200.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    assert rec.spot == _SPOT

def test_reason_is_non_empty_string() -> None:
    for delta in [50.0, -200.0, 300.0]:
        rec = recommend_delta_hedge("SPY", portfolio_delta=delta,
                                    current_underlying_position=0.0,
                                    spot=_SPOT, rules=_RULES)
        assert isinstance(rec.reason, str) and len(rec.reason) > 0

def test_estimated_notional_matches_order_times_spot() -> None:
    rec = recommend_delta_hedge("SPY", portfolio_delta=-200.0, current_underlying_position=0.0,
                                spot=_SPOT, rules=_RULES)
    expected_notional = abs(rec.order_quantity) * _SPOT
    assert abs(rec.estimated_notional - expected_notional) < 1e-6
