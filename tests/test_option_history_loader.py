"""Mocked tests for src/backtesting/option_history_loader.py."""
from __future__ import annotations

import pytest

from src.backtesting.option_history_loader import (
    decode_strike_from_ric,
    load_option_history_mock,
    load_ric_universe,
    load_spy_history_mock,
)


# ---------------------------------------------------------------------------
# decode_strike_from_ric
# ---------------------------------------------------------------------------

class TestDecodeStrike:
    def test_first_ric_fifty_dollars(self):
        assert decode_strike_from_ric("SPYA152705000.U") == pytest.approx(50.0)

    def test_fifty_five_dollar_strike(self):
        assert decode_strike_from_ric("SPYA152705500.U") == pytest.approx(55.0)

    def test_625_strike(self):
        assert decode_strike_from_ric("SPYA152762500.U") == pytest.approx(625.0)

    def test_645_strike(self):
        assert decode_strike_from_ric("SPYA152764500.U") == pytest.approx(645.0)

    def test_five_dollar_increments(self):
        # Verify each consecutive RIC increases by $5
        for i, hundreds in enumerate(range(5000, 6500, 500)):
            ric = f"SPYA1527{hundreds:05d}.U"
            expected = hundreds / 100.0
            assert decode_strike_from_ric(ric) == pytest.approx(expected), ric

    def test_unknown_format_returns_none(self):
        assert decode_strike_from_ric("INVALID.X") is None
        assert decode_strike_from_ric("SPY.N") is None
        assert decode_strike_from_ric("") is None

    def test_missing_dot_u_returns_none(self):
        assert decode_strike_from_ric("SPYA152705000") is None


# ---------------------------------------------------------------------------
# load_ric_universe
# ---------------------------------------------------------------------------

class TestLoadRicUniverse:
    def test_loads_from_yaml(self, tmp_path):
        yaml_content = "rics:\n  - SPYA152705000.U\n  - SPYA152762500.U\n"
        p = tmp_path / "rics.yaml"
        p.write_text(yaml_content)
        result = load_ric_universe(p)
        assert result == ["SPYA152705000.U", "SPYA152762500.U"]

    def test_empty_yaml_returns_empty_list(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("rics: []\n")
        assert load_ric_universe(p) == []


# ---------------------------------------------------------------------------
# load_spy_history_mock
# ---------------------------------------------------------------------------

class TestSpyHistoryMock:
    def test_returns_30_rows(self):
        df = load_spy_history_mock()
        assert len(df) == 30

    def test_has_required_columns(self):
        df = load_spy_history_mock()
        assert "date" in df.columns
        assert "spot" in df.columns

    def test_spots_are_positive(self):
        df = load_spy_history_mock()
        assert (df["spot"] > 0).all()

    def test_dates_are_weekdays(self):
        import datetime
        df = load_spy_history_mock()
        for d in df["date"]:
            assert isinstance(d, datetime.date)
            assert d.weekday() < 5, f"{d} is a weekend"

    def test_reproducible(self):
        df1 = load_spy_history_mock()
        df2 = load_spy_history_mock()
        assert list(df1["spot"]) == list(df2["spot"])


# ---------------------------------------------------------------------------
# load_option_history_mock
# ---------------------------------------------------------------------------

SAMPLE_RICS = [
    "SPYA152762500.U",  # strike $625
    "SPYA152763000.U",  # strike $630
    "SPYA152763500.U",  # strike $635
]


class TestOptionHistoryMock:
    def test_returns_dataframe(self):
        df = load_option_history_mock(SAMPLE_RICS)
        assert not df.empty

    def test_has_required_columns(self):
        df = load_option_history_mock(SAMPLE_RICS)
        for col in ("date", "ric", "bid", "ask"):
            assert col in df.columns

    def test_bids_and_asks_positive(self):
        df = load_option_history_mock(SAMPLE_RICS)
        assert (df["bid"] > 0).all()
        assert (df["ask"] > 0).all()

    def test_ask_greater_than_bid(self):
        df = load_option_history_mock(SAMPLE_RICS)
        assert (df["ask"] > df["bid"]).all()

    def test_all_sample_rics_present(self):
        df = load_option_history_mock(SAMPLE_RICS)
        assert set(df["ric"].unique()) == set(SAMPLE_RICS)

    def test_each_ric_has_multiple_dates(self):
        df = load_option_history_mock(SAMPLE_RICS)
        for ric in SAMPLE_RICS:
            count = len(df[df["ric"] == ric])
            assert count >= 25, f"{ric} has only {count} rows"

    def test_unknown_ric_format_skipped(self):
        df = load_option_history_mock(["INVALID.X"] + SAMPLE_RICS)
        assert "INVALID.X" not in df["ric"].values

    def test_empty_ric_list_raises(self):
        with pytest.raises(RuntimeError, match="no rows"):
            load_option_history_mock([])
