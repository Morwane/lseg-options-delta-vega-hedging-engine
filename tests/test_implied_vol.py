"""Tests for the implied volatility bisection solver."""
import pytest

from src.pricing.black_scholes import BlackScholesInputs, black_scholes_price
from src.pricing.implied_vol import implied_vol_bisection

# Common params shared across tests
_BASE = dict(
    spot=100.0, strike=100.0, time_to_expiry=1.0,
    risk_free_rate=0.05, dividend_yield=0.0,
)


def _price(option_type: str, sigma: float) -> float:
    return black_scholes_price(
        BlackScholesInputs(
            spot=_BASE["spot"], strike=_BASE["strike"],
            time_to_expiry=_BASE["time_to_expiry"],
            risk_free_rate=_BASE["risk_free_rate"],
            volatility=sigma, option_type=option_type,  # type: ignore[arg-type]
            dividend_yield=_BASE["dividend_yield"],
        )
    )


# --- Round-trip tests ---

def test_round_trip_atm_call() -> None:
    true_sigma = 0.20
    market_price = _price("call", true_sigma)
    recovered = implied_vol_bisection(market_price, option_type="call", **_BASE)
    assert recovered is not None
    assert abs(recovered - true_sigma) < 1e-4

def test_round_trip_atm_put() -> None:
    true_sigma = 0.20
    market_price = _price("put", true_sigma)
    recovered = implied_vol_bisection(market_price, option_type="put", **_BASE)
    assert recovered is not None
    assert abs(recovered - true_sigma) < 1e-4

def test_round_trip_high_vol_call() -> None:
    true_sigma = 0.50
    market_price = _price("call", true_sigma)
    recovered = implied_vol_bisection(market_price, option_type="call", **_BASE)
    assert recovered is not None
    assert abs(recovered - true_sigma) < 1e-4

def test_round_trip_low_vol_call() -> None:
    true_sigma = 0.05
    market_price = _price("call", true_sigma)
    recovered = implied_vol_bisection(market_price, option_type="call", **_BASE)
    assert recovered is not None
    assert abs(recovered - true_sigma) < 1e-4

def test_round_trip_otm_call() -> None:
    params = dict(
        spot=100.0, strike=110.0, time_to_expiry=0.5,
        risk_free_rate=0.05, dividend_yield=0.0,
    )
    true_sigma = 0.25
    market_price = black_scholes_price(
        BlackScholesInputs(
            spot=params["spot"], strike=params["strike"],
            time_to_expiry=params["time_to_expiry"],
            risk_free_rate=params["risk_free_rate"],
            volatility=true_sigma, option_type="call",
            dividend_yield=params["dividend_yield"],
        )
    )
    recovered = implied_vol_bisection(market_price, option_type="call", **params)
    assert recovered is not None
    assert abs(recovered - true_sigma) < 1e-4

def test_round_trip_itm_put() -> None:
    params = dict(
        spot=100.0, strike=115.0, time_to_expiry=0.25,
        risk_free_rate=0.05, dividend_yield=0.0,
    )
    true_sigma = 0.30
    market_price = black_scholes_price(
        BlackScholesInputs(
            spot=params["spot"], strike=params["strike"],
            time_to_expiry=params["time_to_expiry"],
            risk_free_rate=params["risk_free_rate"],
            volatility=true_sigma, option_type="put",
            dividend_yield=params["dividend_yield"],
        )
    )
    recovered = implied_vol_bisection(market_price, option_type="put", **params)
    assert recovered is not None
    assert abs(recovered - true_sigma) < 1e-4


# --- Edge / failure cases ---

def test_raises_for_zero_price() -> None:
    with pytest.raises(ValueError, match="market_price"):
        implied_vol_bisection(market_price=0.0, option_type="call", **_BASE)

def test_raises_for_negative_price() -> None:
    with pytest.raises(ValueError, match="market_price"):
        implied_vol_bisection(market_price=-1.0, option_type="call", **_BASE)

def test_raises_for_price_above_spot() -> None:
    # Call price cannot exceed the spot — outside no-arbitrage range
    with pytest.raises(ValueError, match="no-arbitrage"):
        implied_vol_bisection(market_price=200.0, option_type="call", **_BASE)

def test_raises_for_zero_expiry() -> None:
    with pytest.raises(ValueError, match="time_to_expiry"):
        implied_vol_bisection(
            market_price=5.0, spot=100.0, strike=100.0,
            time_to_expiry=0.0, risk_free_rate=0.05, option_type="call",
        )

def test_recovered_vol_is_positive() -> None:
    market_price = _price("call", 0.20)
    recovered = implied_vol_bisection(market_price, option_type="call", **_BASE)
    assert recovered > 0
