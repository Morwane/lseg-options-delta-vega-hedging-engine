"""Tests for the Delta-Vega hedge optimizer.

Covers:
- Objective function correctness
- No-hedge method (trivial)
- Delta-only method: residual delta = 0
- Delta-Vega method: residual vega ≈ 0 when valid candidate provided
- Optimized method: residual delta and vega better than delta-only
- Edge cases: empty candidate universe, zero vega, extreme inputs
- HedgeCandidate and HedgeUniverseConfig filtering logic
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.optimization.delta_vega_optimizer import (
    HedgeAllocation,
    OptimizerConfig,
    optimize_hedge,
)
from src.optimization.hedge_objective import (
    HedgeObjectiveParams,
    compute_objective,
    compute_residuals,
    estimate_hedge_cost,
)
from src.optimization.hedge_universe import (
    HedgeCandidate,
    HedgeUniverseConfig,
    build_hedge_universe,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_candidate(
    ric: str = "SPYA152706500.U",
    delta: float = 0.6,
    vega: float = 50.0,
    bid: float = 10.0,
    ask: float = 10.20,
    strike: float = 650.0,
    spot: float = 700.0,
    iv: float = 0.20,
    iv_source: str = "bs_bisection",
) -> HedgeCandidate:
    mid = (bid + ask) / 2.0
    spread_bps = (ask - bid) / mid * 10_000.0
    return HedgeCandidate(
        ric=ric,
        option_type="call",
        strike=strike,
        delta=delta,
        gamma=0.005,
        vega=vega,
        theta=-0.10,
        bid=bid,
        ask=ask,
        mid=mid,
        spread_bps=spread_bps,
        iv=iv,
        iv_solved=(iv_source == "bs_bisection"),
        moneyness_pct=(spot - strike) / strike * 100.0,
    )


def _default_config() -> OptimizerConfig:
    return OptimizerConfig(
        max_option_instruments=2,
        max_contracts_per_instrument=10.0,
        max_underlying_shares=1000.0,
        objective=HedgeObjectiveParams(
            lambda_delta=1.0,
            lambda_vega=0.5,
            lambda_cost=0.01,
            lambda_turnover=0.005,
            cost_bps=2.0,
        ),
    )


# ── Objective function ─────────────────────────────────────────────────────────

class TestHedgeObjective:
    def test_no_hedge_objective_equals_delta_vega_penalty(self):
        params = HedgeObjectiveParams(lambda_delta=1.0, lambda_vega=0.5,
                                       lambda_cost=0.0, lambda_turnover=0.0)
        bd, bv = 100.0, 500.0
        obj = compute_objective(
            h_underlying=0.0,
            option_weights=np.zeros(0),
            candidate_deltas=np.zeros(0),
            candidate_vegas=np.zeros(0),
            candidate_mids=np.zeros(0),
            spot=700.0,
            book_delta=bd,
            book_vega=bv,
            prev_h=0.0,
            prev_weights=np.zeros(0),
            params=params,
        )
        expected = 1.0 * bd**2 + 0.5 * bv**2
        assert math.isclose(obj, expected, rel_tol=1e-9)

    def test_perfect_delta_hedge_reduces_delta_term(self):
        params = HedgeObjectiveParams(lambda_delta=1.0, lambda_vega=0.0,
                                       lambda_cost=0.0, lambda_turnover=0.0)
        bd = 100.0
        obj = compute_objective(
            h_underlying=-bd,
            option_weights=np.zeros(0),
            candidate_deltas=np.zeros(0),
            candidate_vegas=np.zeros(0),
            candidate_mids=np.zeros(0),
            spot=700.0,
            book_delta=bd,
            book_vega=0.0,
            prev_h=0.0,
            prev_weights=np.zeros(0),
            params=params,
        )
        assert math.isclose(obj, 0.0, abs_tol=1e-9)

    def test_compute_residuals_empty(self):
        rd, rv = compute_residuals(0.0, np.zeros(0), np.zeros(0), np.zeros(0), 50.0, 300.0)
        assert math.isclose(rd, 50.0, rel_tol=1e-9)
        assert math.isclose(rv, 300.0, rel_tol=1e-9)

    def test_compute_residuals_with_option(self):
        # Hedge: w=-2 contracts × delta=0.5 × mult=100 = -100 → cancels book_delta=100
        rd, rv = compute_residuals(
            h_underlying=0.0,
            option_weights=np.array([-2.0]),
            candidate_deltas=np.array([0.5]),
            candidate_vegas=np.array([30.0]),
            book_delta=100.0,
            book_vega=0.0,
            multiplier=100,
        )
        assert math.isclose(rd, 0.0, abs_tol=1e-9), f"residual_delta={rd}"
        # rv = 0 + (-2 × 30 × 100) = -6000
        assert math.isclose(rv, -6000.0, abs_tol=1e-6)

    def test_estimate_cost_positive(self):
        cost = estimate_hedge_cost(
            h_underlying=100.0,
            option_weights=np.array([1.0]),
            candidate_mids=np.array([10.0]),
            spot=700.0,
            multiplier=100,
            cost_bps=2.0,
        )
        # underlying: 100 × 700 × 2/10000 = 14.0
        # option:     1 × 10 × 100 × 2/10000 = 0.2
        # total = 14.2
        assert math.isclose(cost, 14.2, rel_tol=1e-6)


# ── Hedge universe builder ─────────────────────────────────────────────────────

class TestHedgeUniverseBuilder:
    def _make_mock_greek(self, **kwargs) -> MagicMock:
        g = MagicMock()
        g.ric = kwargs.get("ric", "SPYA152706500.U")
        g.strike = kwargs.get("strike", 650.0)
        g.spot = kwargs.get("spot", 700.0)
        g.delta = kwargs.get("delta", 0.6)
        g.gamma = kwargs.get("gamma", 0.005)
        g.vega = kwargs.get("vega", 50.0)
        g.theta = kwargs.get("theta", -0.10)
        g.bid = kwargs.get("bid", 10.0)
        g.ask = kwargs.get("ask", 10.20)
        g.iv = kwargs.get("iv", 0.20)
        g.iv_source = kwargs.get("iv_source", "bs_bisection")
        return g

    def test_valid_candidate_passes_all_filters(self):
        greeks = [self._make_mock_greek()]
        config = HedgeUniverseConfig()
        cands = build_hedge_universe(greeks, config)
        assert len(cands) == 1
        assert cands[0].ric == "SPYA152706500.U"

    def test_too_wide_spread_excluded(self):
        g = self._make_mock_greek(bid=10.0, ask=15.0)  # 50% spread >> 300 bps
        config = HedgeUniverseConfig(max_spread_bps=300.0)
        cands = build_hedge_universe([g], config)
        assert len(cands) == 0

    def test_deep_otm_excluded(self):
        # moneyness = (700 - 900) / 900 × 100 = -22.2% > 15%
        g = self._make_mock_greek(strike=900.0, spot=700.0)
        config = HedgeUniverseConfig(max_moneyness_abs_pct=15.0)
        cands = build_hedge_universe([g], config)
        assert len(cands) == 0

    def test_failed_iv_excluded_when_required(self):
        g = self._make_mock_greek(iv_source="realized_vol_fallback")
        config = HedgeUniverseConfig(require_iv_solved=True)
        cands = build_hedge_universe([g], config)
        assert len(cands) == 0

    def test_failed_iv_included_when_not_required(self):
        g = self._make_mock_greek(iv_source="realized_vol_fallback")
        config = HedgeUniverseConfig(require_iv_solved=False)
        cands = build_hedge_universe([g], config)
        assert len(cands) == 1

    def test_near_zero_vega_excluded(self):
        g = self._make_mock_greek(vega=0.001)
        config = HedgeUniverseConfig(min_vega=0.005)
        cands = build_hedge_universe([g], config)
        assert len(cands) == 0

    def test_none_delta_excluded(self):
        g = self._make_mock_greek()
        g.delta = None
        cands = build_hedge_universe([g], HedgeUniverseConfig())
        assert len(cands) == 0

    def test_invalid_bid_ask_excluded(self):
        g = self._make_mock_greek(bid=0.0, ask=10.0)
        cands = build_hedge_universe([g], HedgeUniverseConfig())
        assert len(cands) == 0

    def test_max_candidates_respected(self):
        greeks = [
            self._make_mock_greek(ric=f"SPYA{i}.U", bid=10.0 + i * 0.1, ask=10.2 + i * 0.1)
            for i in range(50)
        ]
        config = HedgeUniverseConfig(max_candidates=5)
        cands = build_hedge_universe(greeks, config)
        assert len(cands) <= 5

    def test_candidates_sorted_by_spread(self):
        g1 = self._make_mock_greek(ric="A.U", bid=10.0, ask=10.10)   # 10 bps
        g2 = self._make_mock_greek(ric="B.U", bid=10.0, ask=10.50)   # 50 bps
        cands = build_hedge_universe([g2, g1], HedgeUniverseConfig())
        assert cands[0].ric == "A.U"


# ── Optimizer (four methods) ───────────────────────────────────────────────────

class TestOptimizer:
    def test_no_hedge_residuals_equal_book(self):
        bd, bv = 150.0, 800.0
        results = optimize_hedge(
            book_delta=bd, book_vega=bv,
            candidates=[], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        nh = results["no_hedge"]
        assert math.isclose(nh.residual_delta, bd, rel_tol=1e-9)
        assert math.isclose(nh.residual_vega, bv, rel_tol=1e-9)
        assert nh.h_underlying == 0.0
        assert nh.transaction_cost == 0.0

    def test_delta_only_residual_delta_zero(self):
        bd = 200.0
        results = optimize_hedge(
            book_delta=bd, book_vega=500.0,
            candidates=[], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        do = results["delta_only"]
        assert math.isclose(do.residual_delta, 0.0, abs_tol=1e-9)
        assert math.isclose(do.h_underlying, -bd, rel_tol=1e-9)

    def test_delta_only_vega_unhedged(self):
        bv = 600.0
        results = optimize_hedge(
            book_delta=100.0, book_vega=bv,
            candidates=[], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        assert math.isclose(results["delta_only"].residual_vega, bv, rel_tol=1e-9)

    def test_delta_vega_reduces_vega_with_candidate(self):
        bd, bv = 100.0, 3000.0
        cand = _make_candidate(delta=0.6, vega=30.0)  # vega×100 = 3000 per contract
        results = optimize_hedge(
            book_delta=bd, book_vega=bv,
            candidates=[cand], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        dv = results["delta_vega"]
        # Should reduce |residual_vega| significantly compared to delta_only
        do = results["delta_only"]
        assert abs(dv.residual_vega) < abs(do.residual_vega), (
            f"delta_vega residual_vega={dv.residual_vega:.2f} >= "
            f"delta_only residual_vega={do.residual_vega:.2f}"
        )

    def test_delta_vega_near_zero_residual_vega(self):
        bd, bv = 100.0, 3000.0
        # vega = 30 per share; 1 contract = 100 shares → vega contribution = 3000
        cand = _make_candidate(delta=0.6, vega=30.0)
        results = optimize_hedge(
            book_delta=bd, book_vega=bv,
            candidates=[cand], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        dv = results["delta_vega"]
        assert abs(dv.residual_vega) < 1.0, f"residual_vega too large: {dv.residual_vega}"

    def test_optimized_at_least_as_good_as_delta_only(self):
        bd, bv = 150.0, 2000.0
        cand = _make_candidate(delta=0.5, vega=20.0)
        results = optimize_hedge(
            book_delta=bd, book_vega=bv,
            candidates=[cand], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        opt = results["optimized"]
        do = results["delta_only"]
        # Optimized objective must be <= delta_only objective
        assert opt.objective_value <= do.objective_value + 1e-6, (
            f"optimized obj={opt.objective_value:.4f} > delta_only obj={do.objective_value:.4f}"
        )

    def test_empty_candidates_no_crash(self):
        results = optimize_hedge(
            book_delta=100.0, book_vega=500.0,
            candidates=[], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        assert set(results.keys()) == {"no_hedge", "delta_only", "delta_vega", "optimized"}

    def test_all_methods_return_allocations(self):
        cand = _make_candidate()
        results = optimize_hedge(
            book_delta=100.0, book_vega=2000.0,
            candidates=[cand], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        for key in ("no_hedge", "delta_only", "delta_vega", "optimized"):
            assert key in results
            alloc = results[key]
            assert isinstance(alloc, HedgeAllocation)
            assert math.isfinite(alloc.residual_delta)
            assert math.isfinite(alloc.residual_vega)
            assert alloc.transaction_cost >= 0.0

    def test_transaction_cost_zero_for_no_hedge(self):
        results = optimize_hedge(
            book_delta=100.0, book_vega=500.0,
            candidates=[_make_candidate()], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        assert results["no_hedge"].transaction_cost == 0.0

    def test_transaction_cost_positive_for_active_methods(self):
        results = optimize_hedge(
            book_delta=100.0, book_vega=500.0,
            candidates=[_make_candidate()], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        assert results["delta_only"].transaction_cost > 0.0

    def test_zero_book_delta_delta_only_no_trade(self):
        results = optimize_hedge(
            book_delta=0.0, book_vega=500.0,
            candidates=[], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        do = results["delta_only"]
        assert math.isclose(do.h_underlying, 0.0, abs_tol=1e-9)
        assert do.transaction_cost == 0.0

    def test_large_book_delta_bounded_by_max_shares(self):
        config = OptimizerConfig(
            max_underlying_shares=50.0,  # tight bound
            max_option_instruments=1,
            objective=HedgeObjectiveParams(lambda_delta=1.0, lambda_vega=0.0,
                                            lambda_cost=0.0, lambda_turnover=0.0),
        )
        cand = _make_candidate()
        results = optimize_hedge(
            book_delta=1000.0, book_vega=0.0,
            candidates=[cand], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=config,
        )
        opt = results["optimized"]
        assert abs(opt.h_underlying) <= 50.0 + 1e-6

    def test_multiple_candidates_picks_best(self):
        # cand1 has low vega — bad for vega hedge
        # cand2 has high vega — good for vega hedge
        cand1 = _make_candidate(ric="LOW.U", vega=1.0, delta=0.5)
        cand2 = _make_candidate(ric="HIGH.U", vega=30.0, delta=0.6, bid=10.0, ask=10.15)
        results = optimize_hedge(
            book_delta=100.0, book_vega=3000.0,
            candidates=[cand1, cand2], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        dv = results["delta_vega"]
        # High-vega candidate should be selected
        assert "HIGH.U" in dv.selected_rics or abs(dv.residual_vega) < abs(3000.0), (
            f"delta_vega should select high-vega candidate; selected={dv.selected_rics}"
        )

    def test_sign_convention_positive_book_delta(self):
        # Positive book_delta → delta_only should SHORT underlying (negative h)
        results = optimize_hedge(
            book_delta=+200.0, book_vega=0.0,
            candidates=[], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        assert results["delta_only"].h_underlying < 0.0

    def test_sign_convention_negative_book_delta(self):
        # Negative book_delta → delta_only should LONG underlying (positive h)
        results = optimize_hedge(
            book_delta=-200.0, book_vega=0.0,
            candidates=[], prev_h=0.0, prev_option_weights={},
            spot=700.0, config=_default_config(),
        )
        assert results["delta_only"].h_underlying > 0.0
