"""Tests for transaction cost estimation."""
from src.hedging.transaction_costs import estimate_transaction_cost


def test_bps_fallback_basic() -> None:
    # 100 shares * $50 spot * 2 bps / 10_000 = $1.00
    cost = estimate_transaction_cost(quantity=100.0, spot=50.0, cost_bps=2.0)
    assert abs(cost - 1.00) < 1e-9

def test_bps_fallback_sign_ignored() -> None:
    # Sell order (negative qty) should give same cost as buy
    buy = estimate_transaction_cost(quantity=50.0, spot=100.0, cost_bps=2.0)
    sell = estimate_transaction_cost(quantity=-50.0, spot=100.0, cost_bps=2.0)
    assert abs(buy - sell) < 1e-9

def test_zero_quantity_returns_zero() -> None:
    cost = estimate_transaction_cost(quantity=0.0, spot=500.0, cost_bps=2.0)
    assert cost == 0.0

def test_bid_ask_half_spread_used_when_available() -> None:
    # spread = ask - bid = 0.10, half_spread = 0.05; 100 shares * 0.05 = $5.00
    cost = estimate_transaction_cost(
        quantity=100.0, spot=500.0, cost_bps=2.0, bid=499.95, ask=500.05
    )
    assert abs(cost - 5.00) < 1e-9

def test_bid_ask_takes_priority_over_bps() -> None:
    # With bid/ask, bps value is irrelevant
    cost_bps = estimate_transaction_cost(quantity=100.0, spot=500.0, cost_bps=999.0)
    cost_spread = estimate_transaction_cost(
        quantity=100.0, spot=500.0, cost_bps=999.0, bid=499.95, ask=500.05
    )
    # bps cost would be enormous; spread cost is $5.00
    assert cost_spread < cost_bps

def test_bid_only_falls_back_to_bps() -> None:
    # ask is None so bid/ask path is not taken
    cost = estimate_transaction_cost(
        quantity=100.0, spot=500.0, cost_bps=2.0, bid=499.95, ask=None
    )
    expected = 100.0 * 500.0 * 2.0 / 10_000.0
    assert abs(cost - expected) < 1e-9

def test_ask_only_falls_back_to_bps() -> None:
    cost = estimate_transaction_cost(
        quantity=100.0, spot=500.0, cost_bps=2.0, bid=None, ask=500.05
    )
    expected = 100.0 * 500.0 * 2.0 / 10_000.0
    assert abs(cost - expected) < 1e-9

def test_cost_is_non_negative() -> None:
    assert estimate_transaction_cost(quantity=-200.0, spot=300.0, cost_bps=5.0) >= 0.0
