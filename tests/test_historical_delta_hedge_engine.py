"""Mocked tests for src/backtesting/historical_delta_hedge_engine.py."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from src.backtesting.historical_delta_hedge_engine import (
    HistoricalBacktestConfig,
    IVResult,
    _compute_iv_and_greeks,
    _rolling_realized_vol,
    load_backtest_config,
    run_backtest,
    to_daily_hedge_df,
    to_data_quality_df,
    to_greeks_df,
)
from src.backtesting.option_history_loader import (
    load_option_history_mock,
    load_ric_universe,
    load_spy_history_mock,
)


# ---------------------------------------------------------------------------
# Fixture: small config
# ---------------------------------------------------------------------------

SAMPLE_RICS = [
    "SPYA152762500.U",  # $625
    "SPYA152763000.U",  # $630
    "SPYA152763500.U",  # $635
    "SPYA152764000.U",  # $640
    "SPYA152764500.U",  # $645
]

SAMPLE_CONFIG = HistoricalBacktestConfig(
    underlying="SPY",
    option_type="call",
    expiry_date=date(2027, 1, 15),
    atm_contract_count=3,
    risk_free_rate=0.05,
    spy_dividend_yield=0.013,
    iv_bisection_sigma_low=0.001,
    iv_bisection_sigma_high=5.0,
    iv_bisection_tolerance=1e-6,
    iv_fallback_allowed=True,
    iv_fallback_vol_window_days=10,
    iv_fallback_max_rate_warning=0.30,
    delta_threshold_shares=1.0,
    max_order_notional_usd=5_000_000,
    hedge_cost_bps=2.0,
    contracts_per_position=1,
    contract_multiplier=100,
    output_dir=Path("outputs/reports"),
)


# ---------------------------------------------------------------------------
# load_backtest_config
# ---------------------------------------------------------------------------

class TestLoadBacktestConfig:
    def test_loads_from_yaml(self, tmp_path):
        yaml_text = """\
underlying: SPY
option_type: call
expiry_date: "2027-01-15"
atm_contract_count: 5
risk_free_rate: 0.05
spy_dividend_yield: 0.013
iv_bisection_sigma_low: 0.001
iv_bisection_sigma_high: 5.0
iv_bisection_tolerance: 0.000001
iv_fallback_allowed: true
iv_fallback_vol_window_days: 20
iv_fallback_max_rate_warning: 0.30
delta_threshold_shares: 5.0
max_order_notional_usd: 2000000
hedge_cost_bps: 2.0
contracts_per_position: 1
contract_multiplier: 100
output_dir: outputs/reports
"""
        p = tmp_path / "historical_backtest.yaml"
        p.write_text(yaml_text)
        cfg = load_backtest_config(p)
        assert cfg.underlying == "SPY"
        assert cfg.expiry_date == date(2027, 1, 15)
        assert cfg.atm_contract_count == 5
        assert cfg.risk_free_rate == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# _compute_iv_and_greeks
# ---------------------------------------------------------------------------

class TestComputeIVAndGreeks:
    def test_bs_bisection_succeeds_for_near_atm(self):
        # SPY spot=700, strike=640, TTE ~9 months: BS price should be solvable
        result = _compute_iv_and_greeks(
            market_mid=80.0,
            spot=700.0,
            strike=640.0,
            tte_years=0.75,
            config=SAMPLE_CONFIG,
            realized_vol=0.20,
        )
        assert result.iv_source == "bs_bisection"
        assert result.iv is not None
        assert 0.001 < result.iv < 5.0
        assert result.bs_result is not None
        assert 0 < result.bs_result.delta <= 1.0

    def test_fallback_used_when_market_price_outside_no_arbitrage_range(self):
        # Market price below intrinsic → IV solve will fail; fallback should kick in
        result = _compute_iv_and_greeks(
            market_mid=0.001,   # impossibly low for a deep ITM call
            spot=700.0,
            strike=50.0,
            tte_years=0.75,
            config=SAMPLE_CONFIG,
            realized_vol=0.20,
        )
        assert result.iv_source in ("realized_vol_fallback", "failed")

    def test_no_fallback_when_disabled(self):
        import dataclasses
        cfg_no_fallback = dataclasses.replace(SAMPLE_CONFIG, iv_fallback_allowed=False)
        result = _compute_iv_and_greeks(
            market_mid=0.001,
            spot=700.0,
            strike=50.0,
            tte_years=0.75,
            config=cfg_no_fallback,
            realized_vol=0.20,
        )
        assert result.iv_source == "failed"
        assert result.bs_result is None

    def test_fallback_with_no_realized_vol_returns_failed(self):
        result = _compute_iv_and_greeks(
            market_mid=0.001,
            spot=700.0,
            strike=50.0,
            tte_years=0.75,
            config=SAMPLE_CONFIG,
            realized_vol=None,
        )
        assert result.iv_source == "failed"


# ---------------------------------------------------------------------------
# _rolling_realized_vol
# ---------------------------------------------------------------------------

class TestRollingRealizedVol:
    def test_returns_series_of_same_length(self):
        import pandas as pd
        import numpy as np
        spots = pd.Series([100.0 * (1 + r) for r in [0.01, -0.005, 0.008, 0.012, -0.003]])
        rv = _rolling_realized_vol(spots, window=3)
        assert len(rv) == len(spots)

    def test_annualised_positive(self):
        import pandas as pd
        import numpy as np
        rng = np.random.default_rng(7)
        rets = rng.normal(0, 0.01, 50)
        spots = pd.Series(100.0 * np.cumprod(1 + rets))
        rv = _rolling_realized_vol(spots, window=10)
        rv_clean = rv.dropna()
        assert (rv_clean > 0).all()
        assert (rv_clean < 10.0).all()   # sanity upper bound


# ---------------------------------------------------------------------------
# Full backtest integration (mock data)
# ---------------------------------------------------------------------------

class TestRunBacktest:
    def test_runs_without_error(self):
        spy_df = load_spy_history_mock()
        opt_df = load_option_history_mock(SAMPLE_RICS)
        result = run_backtest(SAMPLE_CONFIG, opt_df, spy_df)
        assert result is not None

    def test_daily_rows_count_matches_spy_dates(self):
        spy_df = load_spy_history_mock()
        opt_df = load_option_history_mock(SAMPLE_RICS)
        result = run_backtest(SAMPLE_CONFIG, opt_df, spy_df)
        assert len(result.daily_hedge_rows) == len(spy_df)

    def test_initial_selection_within_top_n(self):
        spy_df = load_spy_history_mock()
        opt_df = load_option_history_mock(SAMPLE_RICS)
        result = run_backtest(SAMPLE_CONFIG, opt_df, spy_df)
        assert len(result.initial_selection) <= SAMPLE_CONFIG.atm_contract_count

    def test_cumulative_pnl_is_float(self):
        spy_df = load_spy_history_mock()
        opt_df = load_option_history_mock(SAMPLE_RICS)
        result = run_backtest(SAMPLE_CONFIG, opt_df, spy_df)
        final = result.daily_hedge_rows[-1]
        assert isinstance(final.cumulative_net_pnl, float)

    def test_hedge_pnl_timing_uses_previous_shares(self):
        # On day 1: hedge_pnl = hedge_shares[0] × (spot[1] - spot[0])
        spy_df = load_spy_history_mock()
        opt_df = load_option_history_mock(SAMPLE_RICS)
        result = run_backtest(SAMPLE_CONFIG, opt_df, spy_df)
        rows = result.daily_hedge_rows
        if len(rows) >= 2:
            day1 = rows[1]
            day0 = rows[0]
            expected_hedge_pnl = day0.hedge_shares_after * (day1.spot - day0.spot)
            assert day1.hedge_pnl == pytest.approx(expected_hedge_pnl, rel=1e-4)

    def test_limitations_list_not_empty(self):
        spy_df = load_spy_history_mock()
        opt_df = load_option_history_mock(SAMPLE_RICS)
        result = run_backtest(SAMPLE_CONFIG, opt_df, spy_df)
        assert len(result.limitations) >= 5
        assert any("calls only" in lim.lower() for lim in result.limitations)

    def test_raises_on_too_few_dates(self):
        import pandas as pd
        spy_one = load_spy_history_mock().head(1)
        opt_df = load_option_history_mock(SAMPLE_RICS)
        with pytest.raises(ValueError, match="at least 2"):
            run_backtest(SAMPLE_CONFIG, opt_df, spy_one)

    def test_fallback_rate_in_range(self):
        spy_df = load_spy_history_mock()
        opt_df = load_option_history_mock(SAMPLE_RICS)
        result = run_backtest(SAMPLE_CONFIG, opt_df, spy_df)
        assert 0.0 <= result.fallback_rate_overall <= 1.0


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

class TestOutputHelpers:
    def _get_result(self):
        spy_df = load_spy_history_mock()
        opt_df = load_option_history_mock(SAMPLE_RICS)
        return run_backtest(SAMPLE_CONFIG, opt_df, spy_df)

    def test_to_daily_hedge_df_has_expected_columns(self):
        result = self._get_result()
        df = to_daily_hedge_df(result.daily_hedge_rows)
        for col in ("date", "spot", "portfolio_delta", "cumulative_net_pnl", "hedge_order_side"):
            assert col in df.columns

    def test_to_greeks_df_has_expected_columns(self):
        result = self._get_result()
        df = to_greeks_df(result.daily_greeks)
        for col in ("date", "ric", "strike", "delta", "iv", "iv_source", "market_vs_bs_gap_bps"):
            assert col in df.columns

    def test_to_data_quality_df_has_fallback_rate(self):
        result = self._get_result()
        df = to_data_quality_df(
            result.daily_greeks,
            result.exclusion_log,
            result.fallback_rate_overall,
            result.is_low_confidence,
        )
        assert "fallback_rate" in df.columns
        assert all(0.0 <= r <= 1.0 for r in df["fallback_rate"])
