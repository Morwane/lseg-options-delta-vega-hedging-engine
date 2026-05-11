"""Mocked tests for src/pricing/market_comparison.py."""
from __future__ import annotations

from datetime import date

import pytest

from src.pricing.market_comparison import MarketVsBSResult, compute_market_vs_bs

TEST_DATE = date(2026, 3, 18)
TEST_RIC = "SPYA152762500.U"


class TestComputeMarketVsBS:
    def test_zero_gap_when_prices_equal(self):
        result = compute_market_vs_bs(100.0, 100.0, TEST_RIC, TEST_DATE)
        assert result.gap_usd == pytest.approx(0.0)
        assert result.gap_bps == pytest.approx(0.0)

    def test_positive_gap_when_market_above_bs(self):
        result = compute_market_vs_bs(102.0, 100.0, TEST_RIC, TEST_DATE)
        assert result.gap_usd == pytest.approx(2.0)
        assert result.gap_bps == pytest.approx(200.0)  # 2/100 * 10000

    def test_negative_gap_when_market_below_bs(self):
        result = compute_market_vs_bs(98.0, 100.0, TEST_RIC, TEST_DATE)
        assert result.gap_usd == pytest.approx(-2.0)
        assert result.gap_bps == pytest.approx(-200.0)

    def test_gap_bps_formula_exact(self):
        market_mid = 75.0
        bs_price = 74.0
        result = compute_market_vs_bs(market_mid, bs_price, TEST_RIC, TEST_DATE)
        expected_bps = (75.0 - 74.0) / 74.0 * 10_000.0
        assert result.gap_bps == pytest.approx(expected_bps)

    def test_raises_on_zero_bs_price(self):
        with pytest.raises(ValueError, match="bs_price must be positive"):
            compute_market_vs_bs(100.0, 0.0, TEST_RIC, TEST_DATE)

    def test_raises_on_negative_bs_price(self):
        with pytest.raises(ValueError, match="bs_price must be positive"):
            compute_market_vs_bs(100.0, -5.0, TEST_RIC, TEST_DATE)

    def test_result_fields_populated(self):
        result = compute_market_vs_bs(101.0, 100.0, TEST_RIC, TEST_DATE)
        assert result.ric == TEST_RIC
        assert result.date == TEST_DATE
        assert result.market_mid == pytest.approx(101.0)
        assert result.bs_price == pytest.approx(100.0)

    def test_deep_itm_call_small_gap(self):
        # For a deep-ITM call, BS price ≈ market mid at correct IV → small gap
        result = compute_market_vs_bs(658.75, 657.0, TEST_RIC, TEST_DATE)
        assert abs(result.gap_bps) < 300  # < 30 bps gap is plausible for deep ITM

    def test_frozen_dataclass(self):
        result = compute_market_vs_bs(100.0, 99.0, TEST_RIC, TEST_DATE)
        assert isinstance(result, MarketVsBSResult)
        with pytest.raises((AttributeError, TypeError)):
            result.gap_bps = 999.0  # type: ignore[misc]
