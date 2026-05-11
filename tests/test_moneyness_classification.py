"""Tests for moneyness classification helpers in src/backtesting/contract_selection.py."""
from __future__ import annotations

from datetime import date

import pytest

from src.backtesting.contract_selection import (
    ContractBar,
    check_atm_warning,
    classify_moneyness,
    get_selection_label,
    is_near_atm,
    select_atm_contracts,
)

import pandas as pd


SPY_SPOT = 700.0
TEST_DATE = date(2026, 3, 18)


# ---------------------------------------------------------------------------
# classify_moneyness
# ---------------------------------------------------------------------------

class TestClassifyMoneyness:
    # --- ATM band (default 2%) ---
    def test_exactly_atm_returns_atm(self):
        assert classify_moneyness(700.0, 700.0) == "ATM"

    def test_within_2pct_returns_atm(self):
        # 700 * 0.02 = 14 → strikes 686–714 are ATM
        assert classify_moneyness(690.0, 700.0) == "ATM"
        assert classify_moneyness(710.0, 700.0) == "ATM"

    def test_exactly_at_2pct_boundary_returns_atm(self):
        # |700 - 686| / 700 = 2.0% → ATM (≤ threshold)
        assert classify_moneyness(686.0, 700.0) == "ATM"

    def test_just_beyond_2pct_itm_call(self):
        # |700 - 685| / 700 = 2.14% → ITM for call (strike < spot)
        assert classify_moneyness(685.0, 700.0, option_type="call") == "ITM"

    def test_just_beyond_2pct_otm_call(self):
        # |715 - 700| / 700 = 2.14% → OTM for call (strike > spot)
        assert classify_moneyness(715.0, 700.0, option_type="call") == "OTM"

    # --- Deep ITM / OTM ---
    def test_deep_itm_call(self):
        assert classify_moneyness(50.0, 700.0, option_type="call") == "ITM"

    def test_deep_otm_call(self):
        assert classify_moneyness(1000.0, 700.0, option_type="call") == "OTM"

    def test_itm_put(self):
        # Put is ITM when strike > spot
        assert classify_moneyness(750.0, 700.0, option_type="put") == "ITM"

    def test_otm_put(self):
        # Put is OTM when strike < spot
        assert classify_moneyness(650.0, 700.0, option_type="put") == "OTM"

    def test_atm_put_same_as_call(self):
        # ATM band is symmetric — same result for put and call
        assert classify_moneyness(700.0, 700.0, option_type="put") == "ATM"

    # --- Custom ATM band ---
    def test_custom_atm_band_5pct(self):
        # 5% of 700 = 35 → strike 665 is ATM with 5% band
        assert classify_moneyness(665.0, 700.0, atm_band_pct=0.05) == "ATM"

    def test_custom_atm_band_0pct_only_exact_is_atm(self):
        assert classify_moneyness(700.0, 700.0, atm_band_pct=0.0) == "ATM"
        assert classify_moneyness(699.0, 700.0, atm_band_pct=0.0) == "ITM"

    # --- Confirmed RIC universe: all should be ITM calls ---
    def test_ric_universe_strikes_are_itm_calls(self):
        for strike in range(50, 650, 5):
            assert classify_moneyness(float(strike), SPY_SPOT, option_type="call") in ("ATM", "ITM")

    def test_degenerate_zero_spot_returns_otm(self):
        assert classify_moneyness(100.0, 0.0) == "OTM"

    def test_returns_literal_string_values(self):
        assert classify_moneyness(700.0, 700.0) in ("ATM", "ITM", "OTM")
        assert classify_moneyness(645.0, 700.0) in ("ATM", "ITM", "OTM")


# ---------------------------------------------------------------------------
# is_near_atm
# ---------------------------------------------------------------------------

class TestIsNearATM:
    def test_exactly_spot_is_near_atm(self):
        assert is_near_atm(700.0, 700.0) is True

    def test_within_3pct_is_near_atm(self):
        # 700 * 0.03 = 21 → strike 679 is within 3%
        assert is_near_atm(679.0, 700.0) is True
        assert is_near_atm(721.0, 700.0) is True

    def test_exactly_3pct_boundary_is_near_atm(self):
        # |700 - 679| / 700 ≈ 3.0% → True (≤)
        boundary = 700.0 * (1 - 0.03)  # = 679.0
        assert is_near_atm(boundary, 700.0) is True

    def test_beyond_3pct_is_not_near_atm(self):
        assert is_near_atm(645.0, 700.0) is False   # 7.9% away
        assert is_near_atm(50.0, 700.0) is False     # very deep ITM

    def test_custom_threshold(self):
        assert is_near_atm(685.0, 700.0, threshold_pct=0.10) is True
        assert is_near_atm(600.0, 700.0, threshold_pct=0.10) is False

    def test_zero_spot_returns_false(self):
        assert is_near_atm(100.0, 0.0) is False

    # Confirmed RIC universe: no strike in $50–$645 is within 3% of $700
    def test_confirmed_ric_strikes_not_near_atm(self):
        for strike in range(50, 650, 5):
            assert is_near_atm(float(strike), SPY_SPOT) is False


# ---------------------------------------------------------------------------
# check_atm_warning
# ---------------------------------------------------------------------------

def _make_bar(strike: float, spot: float) -> ContractBar:
    """Build a minimal ContractBar for testing check_atm_warning."""
    from src.backtesting.contract_selection import classify_moneyness
    mid = max(0.01, spot - strike)
    return ContractBar(
        ric=f"SPYA1527{int(strike * 100):05d}.U",
        strike=strike,
        date=TEST_DATE,
        bid=mid - 0.25,
        ask=mid + 0.25,
        mid=mid,
        spread=0.50,
        moneyness_abs=abs(strike - spot),
        moneyness_pct=(spot - strike) / spot,
        moneyness_class=classify_moneyness(strike, spot),
    )


class TestCheckATMWarning:
    def test_no_warning_when_contract_within_3pct(self):
        bar = _make_bar(690.0, 700.0)   # 1.4% ITM — within 3%
        triggered, msg = check_atm_warning([bar], 700.0)
        assert triggered is False
        assert msg == ""

    def test_warning_when_all_beyond_3pct(self):
        bars = [_make_bar(645.0, 700.0), _make_bar(640.0, 700.0)]
        triggered, msg = check_atm_warning(bars, 700.0)
        assert triggered is True
        assert "3%" in msg
        assert "700" in msg

    def test_warning_message_names_nearest_contract(self):
        bars = [_make_bar(645.0, 700.0), _make_bar(625.0, 700.0)]
        triggered, msg = check_atm_warning(bars, 700.0)
        assert triggered is True
        # Nearest is $645 (8.1% away vs $625 at 11% away)
        assert "645" in msg

    def test_no_warning_for_empty_selection(self):
        triggered, msg = check_atm_warning([], 700.0)
        assert triggered is False
        assert msg == ""

    def test_custom_threshold_1pct_triggers_on_2pct_contract(self):
        bar = _make_bar(686.0, 700.0)   # 2.0% ITM
        triggered, _ = check_atm_warning([bar], 700.0, threshold_pct=0.01)
        assert triggered is True

    def test_custom_threshold_10pct_no_warning_for_itm(self):
        bar = _make_bar(645.0, 700.0)   # 7.9% ITM
        triggered, _ = check_atm_warning([bar], 700.0, threshold_pct=0.10)
        assert triggered is False

    def test_warning_message_mentions_itm_or_otm(self):
        bars = [_make_bar(645.0, 700.0)]
        _, msg = check_atm_warning(bars, 700.0)
        assert "ITM" in msg or "OTM" in msg

    def test_confirmed_ric_universe_always_triggers_warning(self):
        # All confirmed strikes ($50–$645) are >3% ITM at spot $700
        bars = [_make_bar(float(s), SPY_SPOT) for s in range(625, 650, 5)]
        triggered, _ = check_atm_warning(bars, SPY_SPOT)
        assert triggered is True


# ---------------------------------------------------------------------------
# get_selection_label
# ---------------------------------------------------------------------------

class TestGetSelectionLabel:
    def test_returns_atm_when_contract_within_3pct(self):
        bar = _make_bar(690.0, 700.0)
        label = get_selection_label([bar], 700.0)
        assert label == "ATM selection"

    def test_returns_nearest_liquid_when_all_beyond_3pct(self):
        bars = [_make_bar(645.0, 700.0), _make_bar(640.0, 700.0)]
        label = get_selection_label(bars, 700.0)
        assert label == "nearest available liquid call selection"

    def test_empty_selection_returns_nearest_liquid(self):
        label = get_selection_label([], 700.0)
        assert label == "nearest available liquid call selection"

    def test_confirmed_ric_universe_returns_nearest_liquid(self):
        bars = [_make_bar(float(s), SPY_SPOT) for s in range(625, 650, 5)]
        label = get_selection_label(bars, SPY_SPOT)
        assert label == "nearest available liquid call selection"

    def test_mixed_selection_one_near_atm_returns_atm(self):
        # One contract at $695 (0.7% ITM), one at $645 (7.9% ITM)
        bars = [_make_bar(695.0, 700.0), _make_bar(645.0, 700.0)]
        label = get_selection_label(bars, 700.0)
        assert label == "ATM selection"

    def test_custom_threshold(self):
        bar = _make_bar(645.0, 700.0)   # 7.9% ITM
        # With 10% threshold, 7.9% is considered "near ATM"
        label = get_selection_label([bar], 700.0, near_atm_threshold_pct=0.10)
        assert label == "ATM selection"


# ---------------------------------------------------------------------------
# Integration: moneyness_class field set correctly by select_atm_contracts
# ---------------------------------------------------------------------------

class TestMoneynessClassInSelection:
    def _make_history(self, rows: list[dict]) -> pd.DataFrame:
        import pandas as pd
        df = pd.DataFrame(rows)
        if "date" not in df.columns:
            df["date"] = TEST_DATE
        return df

    def test_itm_call_classified_correctly(self):
        rows = [{"ric": "SPYA152764500.U", "bid": 55.0, "ask": 56.0}]  # strike $645 < spot $700
        hist = self._make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert len(result.selected) == 1
        assert result.selected[0].moneyness_class == "ITM"

    def test_atm_call_classified_correctly(self):
        rows = [{"ric": "SPYA152769500.U", "bid": 5.0, "ask": 6.0}]   # strike $695 → 0.7% ITM
        hist = self._make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert result.selected[0].moneyness_class == "ATM"

    def test_otm_call_classified_correctly(self):
        # Strike $730 is 4.3% OTM — clearly outside the 2% ATM band
        rows = [{"ric": "SPYA152773000.U", "bid": 2.0, "ask": 3.0}]
        hist = self._make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=5)
        assert result.selected[0].moneyness_class == "OTM"

    def test_all_confirmed_ric_strikes_itm_at_700(self):
        rows = [
            {"ric": f"SPYA1527{int(s * 100):05d}.U", "bid": max(0.1, 700 - s - 0.25), "ask": max(0.6, 700 - s + 0.25)}
            for s in range(625, 650, 5)
        ]
        hist = self._make_history(rows)
        result = select_atm_contracts(TEST_DATE, hist, SPY_SPOT, top_n=10)
        for bar in result.selected:
            assert bar.moneyness_class == "ITM", f"{bar.ric} at strike {bar.strike}"
