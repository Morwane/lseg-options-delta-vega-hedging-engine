"""Tests for portfolio exposures aggregation."""
from __future__ import annotations

from datetime import date

import pytest

from src.portfolio.exposures import (
    PositionGreeks,
    UnderlyingExposure,
    aggregate_by_underlying,
    compute_position_greeks,
)
from src.portfolio.positions import (
    OptionPosition,
    PortfolioBook,
    UnderlyingPosition,
)
from src.pricing.black_scholes import BlackScholesInputs, black_scholes_all

# Fixed valuation date so tests are deterministic
_TODAY = date(2026, 4, 29)
_EXPIRY = "2027-04-29"   # exactly 1 year from valuation date
_SPOT = 100.0
_STRIKE = 100.0
_VOL = 0.20
_RATE = 0.05


def _single_call_book(quantity: int = 1) -> PortfolioBook:
    return PortfolioBook(
        option_positions=[
            OptionPosition(
                id="test_call",
                underlying="SPY",
                option_type="call",
                strike=_STRIKE,
                expiry=_EXPIRY,
                quantity=quantity,
                multiplier=100,
                implied_vol=_VOL,
            )
        ],
        underlying_positions={"SPY": UnderlyingPosition(underlying="SPY", quantity=0.0)},
        spot_prices={"SPY": _SPOT},
        risk_free_rate=_RATE,
    )


def _expected_greeks() -> object:
    return black_scholes_all(
        BlackScholesInputs(
            spot=_SPOT, strike=_STRIKE, time_to_expiry=1.0,
            risk_free_rate=_RATE, volatility=_VOL, option_type="call",
        )
    )


# --- compute_position_greeks ---

def test_single_long_call_position_delta() -> None:
    book = _single_call_book(quantity=1)
    results = compute_position_greeks(book, as_of=_TODAY)
    assert len(results) == 1
    pg = results[0]
    expected = _expected_greeks()
    # position_delta = 1 * 100 * option_delta
    assert abs(pg.position_delta - 100.0 * expected.delta) < 1e-6

def test_single_short_call_position_delta_is_negative() -> None:
    book = _single_call_book(quantity=-10)
    results = compute_position_greeks(book, as_of=_TODAY)
    pg = results[0]
    assert pg.position_delta < 0.0

def test_position_delta_scales_with_quantity() -> None:
    book_1 = _single_call_book(quantity=1)
    book_5 = _single_call_book(quantity=5)
    pg1 = compute_position_greeks(book_1, as_of=_TODAY)[0]
    pg5 = compute_position_greeks(book_5, as_of=_TODAY)[0]
    assert abs(pg5.position_delta - 5.0 * pg1.position_delta) < 1e-8

def test_position_gamma_positive_for_long_call() -> None:
    book = _single_call_book(quantity=1)
    pg = compute_position_greeks(book, as_of=_TODAY)[0]
    assert pg.position_gamma > 0.0

def test_position_gamma_negative_for_short_call() -> None:
    book = _single_call_book(quantity=-1)
    pg = compute_position_greeks(book, as_of=_TODAY)[0]
    assert pg.position_gamma < 0.0

def test_position_vega_positive_for_long_call() -> None:
    book = _single_call_book(quantity=1)
    pg = compute_position_greeks(book, as_of=_TODAY)[0]
    assert pg.position_vega > 0.0

def test_expired_option_is_skipped() -> None:
    book = PortfolioBook(
        option_positions=[
            OptionPosition(
                id="expired",
                underlying="SPY",
                option_type="call",
                strike=100.0,
                expiry="2025-01-01",   # in the past
                quantity=1,
                multiplier=100,
                implied_vol=0.20,
            )
        ],
        underlying_positions={},
        spot_prices={"SPY": 100.0},
        risk_free_rate=0.05,
    )
    results = compute_position_greeks(book, as_of=_TODAY)
    assert results == []

def test_missing_spot_raises_value_error() -> None:
    book = PortfolioBook(
        option_positions=[
            OptionPosition(
                id="no_spot",
                underlying="XYZ",
                option_type="call",
                strike=100.0,
                expiry=_EXPIRY,
                quantity=1,
                multiplier=100,
                implied_vol=0.20,
            )
        ],
        underlying_positions={},
        spot_prices={},   # XYZ has no spot
        risk_free_rate=0.05,
    )
    with pytest.raises(ValueError, match="XYZ"):
        compute_position_greeks(book, as_of=_TODAY)

def test_put_position_delta_negative_for_long() -> None:
    book = PortfolioBook(
        option_positions=[
            OptionPosition(
                id="long_put",
                underlying="SPY",
                option_type="put",
                strike=_STRIKE,
                expiry=_EXPIRY,
                quantity=1,
                multiplier=100,
                implied_vol=_VOL,
            )
        ],
        underlying_positions={},
        spot_prices={"SPY": _SPOT},
        risk_free_rate=_RATE,
    )
    pg = compute_position_greeks(book, as_of=_TODAY)[0]
    assert pg.position_delta < 0.0

def test_option_greeks_match_black_scholes_all() -> None:
    book = _single_call_book(quantity=1)
    pg = compute_position_greeks(book, as_of=_TODAY)[0]
    expected = _expected_greeks()
    assert abs(pg.option_price - expected.price) < 1e-8
    assert abs(pg.option_delta - expected.delta) < 1e-8
    assert abs(pg.option_gamma - expected.gamma) < 1e-8
    assert abs(pg.option_vega - expected.vega) < 1e-8
    assert abs(pg.option_theta - expected.theta) < 1e-8


# --- aggregate_by_underlying ---

def test_aggregate_sums_two_positions_same_underlying() -> None:
    book = PortfolioBook(
        option_positions=[
            OptionPosition(
                id="call_1", underlying="SPY", option_type="call",
                strike=100.0, expiry=_EXPIRY, quantity=1, multiplier=100, implied_vol=0.20,
            ),
            OptionPosition(
                id="call_2", underlying="SPY", option_type="call",
                strike=100.0, expiry=_EXPIRY, quantity=2, multiplier=100, implied_vol=0.20,
            ),
        ],
        underlying_positions={},
        spot_prices={"SPY": _SPOT},
        risk_free_rate=_RATE,
    )
    pgs = compute_position_greeks(book, as_of=_TODAY)
    exposures = aggregate_by_underlying(pgs, book.spot_prices)
    assert "SPY" in exposures
    exp = exposures["SPY"]
    # net delta = (1*100 + 2*100) * option_delta = 300 * option_delta
    expected_delta = sum(pg.position_delta for pg in pgs)
    assert abs(exp.net_delta - expected_delta) < 1e-8
    assert exp.num_positions == 2

def test_aggregate_separates_different_underlyings() -> None:
    book = PortfolioBook(
        option_positions=[
            OptionPosition(
                id="spy_call", underlying="SPY", option_type="call",
                strike=100.0, expiry=_EXPIRY, quantity=1, multiplier=100, implied_vol=0.20,
            ),
            OptionPosition(
                id="qqq_call", underlying="QQQ", option_type="call",
                strike=100.0, expiry=_EXPIRY, quantity=1, multiplier=100, implied_vol=0.22,
            ),
        ],
        underlying_positions={},
        spot_prices={"SPY": _SPOT, "QQQ": 100.0},
        risk_free_rate=_RATE,
    )
    pgs = compute_position_greeks(book, as_of=_TODAY)
    exposures = aggregate_by_underlying(pgs, book.spot_prices)
    assert set(exposures.keys()) == {"SPY", "QQQ"}
    assert exposures["SPY"].num_positions == 1
    assert exposures["QQQ"].num_positions == 1

def test_aggregate_long_short_cancel() -> None:
    # Equal long and short of same call: net delta should be ~0
    book = PortfolioBook(
        option_positions=[
            OptionPosition(
                id="long", underlying="SPY", option_type="call",
                strike=100.0, expiry=_EXPIRY, quantity=1, multiplier=100, implied_vol=0.20,
            ),
            OptionPosition(
                id="short", underlying="SPY", option_type="call",
                strike=100.0, expiry=_EXPIRY, quantity=-1, multiplier=100, implied_vol=0.20,
            ),
        ],
        underlying_positions={},
        spot_prices={"SPY": _SPOT},
        risk_free_rate=_RATE,
    )
    pgs = compute_position_greeks(book, as_of=_TODAY)
    exposures = aggregate_by_underlying(pgs, book.spot_prices)
    assert abs(exposures["SPY"].net_delta) < 1e-8
    assert abs(exposures["SPY"].net_gamma) < 1e-8

def test_aggregate_spot_passed_through() -> None:
    book = _single_call_book(quantity=1)
    pgs = compute_position_greeks(book, as_of=_TODAY)
    exposures = aggregate_by_underlying(pgs, book.spot_prices)
    assert exposures["SPY"].spot == _SPOT
