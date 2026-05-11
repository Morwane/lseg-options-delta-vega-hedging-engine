"""Mocked tests for src/backtesting/contract_selection.py."""
from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from src.backtesting.contract_selection import (
    ContractBar,
    ExcludedContract,
    select_atm_contracts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DATE = date(2026, 3, 18)
SPY_SPOT = 700.0


def _make_history(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal option_history DataFrame."""
    df = pd.DataFrame(rows)
    if "date" not in df.columns:
        df["date"] = TEST_DATE
    return df


# ---------------------------------------------------------------------------
# Basic selection
# ---------------------------------------------------------------------------

class TestSelectATMContracts:
    def test_selects_top_n_by_distance_to_atm(self):
        # Strikes 550, 600, 625, 640, 645, 700+
        rows = [
            {"ric": "SPYA152755000.U", "bid": 150.0, "ask": 151.0},  # $550 — far
            {"ric": "SPYA152760000.U", "bid": 100.0, "ask": 101.0},  # $600
            {"ric": "SPYA152762500.U", "bid": 75.0,  "ask": 76.0},   # $625 — 3rd closest
            {"ric": "SPYA152764000.U", "bid": 60.0,  "ask": 61.0},   # $640 — 2nd closest
            {"ric": "SPYA152764500.U", "bid": 55.0,  "ask": 56.0},   # $645 — closest
        ]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=3)

        assert len(result.selected) == 3
        strikes = [c.strike for c in result.selected]
        # First must be $645 (closest to SPY 700), then $640, then $625
        assert strikes == [645.0, 640.0, 625.0]

    def test_top_n_capped_at_available_count(self):
        rows = [{"ric": "SPYA152764500.U", "bid": 55.0, "ask": 56.0}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert len(result.selected) == 1

    def test_returns_correct_mid_and_spread(self):
        rows = [{"ric": "SPYA152764500.U", "bid": 55.0, "ask": 57.0}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        bar = result.selected[0]
        assert bar.mid == pytest.approx(56.0)
        assert bar.spread == pytest.approx(2.0)

    def test_moneyness_abs_computed_correctly(self):
        rows = [{"ric": "SPYA152762500.U", "bid": 75.0, "ask": 76.0}]  # strike 625
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert result.selected[0].moneyness_abs == pytest.approx(75.0)  # |700 - 625|

    def test_moneyness_pct_positive_for_itm_call(self):
        rows = [{"ric": "SPYA152762500.U", "bid": 75.0, "ask": 76.0}]  # strike 625 < spot 700
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert result.selected[0].moneyness_pct > 0  # (700-625)/700

    def test_empty_history_returns_empty_selection(self):
        hist = _make_history([])
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert result.selected == []

    def test_no_lookahead_other_dates_ignored(self):
        future_date = date(2026, 3, 25)
        rows = [
            {"ric": "SPYA152764500.U", "bid": 55.0, "ask": 56.0, "date": future_date},
        ]
        hist = pd.DataFrame(rows)
        # Query on TEST_DATE — future row must not appear
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert result.selected == []


# ---------------------------------------------------------------------------
# Exclusion reasons
# ---------------------------------------------------------------------------

class TestExclusions:
    def test_invalid_bid_excluded(self):
        rows = [{"ric": "SPYA152764500.U", "bid": None, "ask": 56.0}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT)
        assert any(e.reason == "invalid_bid" for e in result.excluded)

    def test_invalid_ask_excluded(self):
        rows = [{"ric": "SPYA152764500.U", "bid": 55.0, "ask": None}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT)
        assert any(e.reason == "invalid_ask" for e in result.excluded)

    def test_crossed_market_excluded(self):
        rows = [{"ric": "SPYA152764500.U", "bid": 57.0, "ask": 55.0}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT)
        assert any(e.reason == "crossed_market" for e in result.excluded)

    def test_zero_bid_excluded(self):
        rows = [{"ric": "SPYA152764500.U", "bid": 0.0, "ask": 56.0}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT)
        assert any(e.reason == "invalid_bid" for e in result.excluded)

    def test_undecodable_strike_excluded(self):
        rows = [{"ric": "BADRIC.X", "bid": 55.0, "ask": 56.0}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT)
        assert any(e.reason == "cannot_decode_strike" for e in result.excluded)

    def test_beyond_top_n_excluded_with_reason(self):
        rows = [
            {"ric": f"SPYA1527{50000 + i * 500:05d}.U", "bid": 50.0 + i, "ask": 51.0 + i}
            for i in range(10)
        ]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=3)
        assert len(result.selected) == 3
        not_selected = [e for e in result.excluded if e.reason == "not_in_top_n_atm"]
        assert len(not_selected) == 7

    def test_nan_bid_excluded(self):
        rows = [{"ric": "SPYA152764500.U", "bid": float("nan"), "ask": 56.0}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT)
        assert result.selected == []

    def test_all_invalid_gives_empty_selection_with_exclusion_log(self):
        rows = [
            {"ric": "SPYA152764500.U", "bid": -1.0, "ask": 56.0},
            {"ric": "SPYA152764000.U", "bid": None, "ask": 55.0},
        ]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT)
        assert result.selected == []
        assert len(result.excluded) == 2


# ---------------------------------------------------------------------------
# ContractSelectionResult helpers
# ---------------------------------------------------------------------------

class TestContractSelectionResult:
    def test_selected_rics_property(self):
        rows = [{"ric": "SPYA152764500.U", "bid": 55.0, "ask": 56.0}]
        hist = _make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert result.selected_rics == ["SPYA152764500.U"]

    def test_spot_stored_correctly(self):
        hist = _make_history([])
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert result.spot == SPY_SPOT
