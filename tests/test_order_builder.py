"""Tests for src/broker/order_builder.py."""
from __future__ import annotations

import pytest

from src.broker.order_builder import IBKROrderSpec, build_market_order
from src.hedging.delta_hedger import HedgeRecommendation


def _make_rec(
    side: str = "BUY",
    order_quantity: float = 50.0,
    blocked: bool = False,
    spot: float = 700.0,
) -> HedgeRecommendation:
    return HedgeRecommendation(
        underlying="SPY",
        portfolio_delta=50.0,
        current_underlying_position=0.0,
        target_underlying_position=-50.0,
        order_quantity=order_quantity,
        side=side,  # type: ignore[arg-type]
        spot=spot,
        estimated_notional=abs(order_quantity) * spot,
        estimated_transaction_cost=abs(order_quantity) * spot * 0.0002,
        reason="test recommendation",
        blocked=blocked,
    )


# ---------------------------------------------------------------------------
# build_market_order — None cases
# ---------------------------------------------------------------------------

class TestBuildMarketOrderNoneCases:
    def test_none_side_returns_none(self):
        rec = _make_rec(side="NONE", order_quantity=0.0)
        assert build_market_order(rec) is None

    def test_blocked_returns_none(self):
        rec = _make_rec(side="BUY", blocked=True)
        assert build_market_order(rec) is None

    def test_blocked_sell_returns_none(self):
        rec = _make_rec(side="SELL", order_quantity=-200.0, blocked=True)
        assert build_market_order(rec) is None


# ---------------------------------------------------------------------------
# build_market_order — valid cases
# ---------------------------------------------------------------------------

class TestBuildMarketOrderValid:
    def test_buy_recommendation_returns_buy_spec(self):
        spec = build_market_order(_make_rec(side="BUY", order_quantity=50.0))
        assert spec is not None
        assert spec.action == "BUY"

    def test_sell_recommendation_returns_sell_spec(self):
        spec = build_market_order(_make_rec(side="SELL", order_quantity=-30.0))
        assert spec is not None
        assert spec.action == "SELL"

    def test_quantity_is_positive_for_buy(self):
        spec = build_market_order(_make_rec(side="BUY", order_quantity=75.0))
        assert spec is not None
        assert spec.total_quantity > 0

    def test_quantity_is_positive_for_sell(self):
        spec = build_market_order(_make_rec(side="SELL", order_quantity=-75.0))
        assert spec is not None
        assert spec.total_quantity > 0

    def test_quantity_is_whole_shares(self):
        spec = build_market_order(_make_rec(side="BUY", order_quantity=50.7))
        assert spec is not None
        assert spec.total_quantity == float(round(50.7))

    def test_quantity_rounded_correctly(self):
        spec = build_market_order(_make_rec(side="BUY", order_quantity=49.4))
        assert spec is not None
        assert spec.total_quantity == 49.0


# ---------------------------------------------------------------------------
# IBKROrderSpec defaults
# ---------------------------------------------------------------------------

class TestIBKROrderSpecDefaults:
    def _buy_spec(self) -> IBKROrderSpec:
        spec = build_market_order(_make_rec(side="BUY", order_quantity=100.0))
        assert spec is not None
        return spec

    def test_order_type_is_mkt(self):
        assert self._buy_spec().order_type == "MKT"

    def test_tif_is_day(self):
        assert self._buy_spec().tif == "DAY"

    def test_transmit_is_false(self):
        assert self._buy_spec().transmit is False

    def test_spec_is_frozen(self):
        spec = self._buy_spec()
        with pytest.raises(Exception):
            spec.action = "SELL"  # type: ignore[misc]

    def test_returns_ibkr_order_spec_type(self):
        spec = self._buy_spec()
        assert isinstance(spec, IBKROrderSpec)
