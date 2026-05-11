"""Tests for Black-Scholes pricing and Greeks."""
import math
import pytest

from src.pricing.black_scholes import (
    BlackScholesInputs,
    black_scholes_all,
    black_scholes_delta,
    black_scholes_gamma,
    black_scholes_price,
    black_scholes_theta,
    black_scholes_vega,
)

# Standard reference inputs: ATM, 1-year, 20% vol, 5% rate
ATM_CALL = BlackScholesInputs(
    spot=100.0, strike=100.0, time_to_expiry=1.0,
    risk_free_rate=0.05, volatility=0.20, option_type="call",
)
ATM_PUT = BlackScholesInputs(
    spot=100.0, strike=100.0, time_to_expiry=1.0,
    risk_free_rate=0.05, volatility=0.20, option_type="put",
)


# --- Price sanity ---

def test_call_price_positive() -> None:
    assert black_scholes_price(ATM_CALL) > 0

def test_put_price_positive() -> None:
    assert black_scholes_price(ATM_PUT) > 0

def test_call_price_known_value() -> None:
    # Textbook result: ~10.45 for ATM, T=1, r=5%, σ=20%
    price = black_scholes_price(ATM_CALL)
    assert abs(price - 10.45) < 0.05

def test_put_price_known_value() -> None:
    # Textbook result: ~5.57 for ATM, T=1, r=5%, σ=20%
    price = black_scholes_price(ATM_PUT)
    assert abs(price - 5.57) < 0.05

def test_put_call_parity() -> None:
    # C - P = S*exp(-qT) - K*exp(-rT)
    C = black_scholes_price(ATM_CALL)
    P = black_scholes_price(ATM_PUT)
    S, K, r, T = 100.0, 100.0, 0.05, 1.0
    expected = S - K * math.exp(-r * T)
    assert abs((C - P) - expected) < 1e-8

def test_deep_itm_call_price_near_intrinsic() -> None:
    inputs = BlackScholesInputs(
        spot=150.0, strike=100.0, time_to_expiry=0.01,
        risk_free_rate=0.05, volatility=0.20, option_type="call",
    )
    price = black_scholes_price(inputs)
    intrinsic = max(0.0, 150.0 - 100.0 * math.exp(-0.05 * 0.01))
    assert price >= intrinsic * 0.99

def test_deep_otm_call_price_near_zero() -> None:
    inputs = BlackScholesInputs(
        spot=50.0, strike=200.0, time_to_expiry=0.1,
        risk_free_rate=0.05, volatility=0.20, option_type="call",
    )
    assert black_scholes_price(inputs) < 1e-3


# --- Delta bounds ---

def test_call_delta_between_zero_and_one() -> None:
    delta = black_scholes_delta(ATM_CALL)
    assert 0.0 < delta < 1.0

def test_put_delta_between_minus_one_and_zero() -> None:
    delta = black_scholes_delta(ATM_PUT)
    assert -1.0 < delta < 0.0

def test_atm_call_delta_near_half() -> None:
    delta = black_scholes_delta(ATM_CALL)
    assert abs(delta - 0.5) < 0.15  # ATM call delta > 0.5 due to drift

def test_deep_itm_call_delta_near_one() -> None:
    inputs = BlackScholesInputs(
        spot=200.0, strike=100.0, time_to_expiry=1.0,
        risk_free_rate=0.05, volatility=0.20, option_type="call",
    )
    assert black_scholes_delta(inputs) > 0.95

def test_deep_otm_put_delta_near_zero() -> None:
    inputs = BlackScholesInputs(
        spot=200.0, strike=100.0, time_to_expiry=1.0,
        risk_free_rate=0.05, volatility=0.20, option_type="put",
    )
    assert abs(black_scholes_delta(inputs)) < 0.05

def test_call_put_delta_sum() -> None:
    # call_delta - put_delta = exp(-q*T), with q=0 => 1.0
    call_d = black_scholes_delta(ATM_CALL)
    put_d = black_scholes_delta(ATM_PUT)
    assert abs((call_d - put_d) - 1.0) < 1e-8


# --- Gamma ---

def test_gamma_positive_call() -> None:
    assert black_scholes_gamma(ATM_CALL) > 0

def test_gamma_positive_put() -> None:
    assert black_scholes_gamma(ATM_PUT) > 0

def test_call_put_gamma_equal() -> None:
    # Gamma is identical for call and put with same inputs
    g_call = black_scholes_gamma(ATM_CALL)
    g_put = black_scholes_gamma(ATM_PUT)
    assert abs(g_call - g_put) < 1e-10


# --- Vega ---

def test_vega_positive_call() -> None:
    assert black_scholes_vega(ATM_CALL) > 0

def test_vega_positive_put() -> None:
    assert black_scholes_vega(ATM_PUT) > 0

def test_call_put_vega_equal() -> None:
    v_call = black_scholes_vega(ATM_CALL)
    v_put = black_scholes_vega(ATM_PUT)
    assert abs(v_call - v_put) < 1e-10

def test_vega_known_value() -> None:
    # ATM T=1 σ=20%: Vega ≈ 37.52
    vega = black_scholes_vega(ATM_CALL)
    assert abs(vega - 37.52) < 0.5


# --- Theta ---

def test_theta_negative_call() -> None:
    # Long option loses time value
    assert black_scholes_theta(ATM_CALL) < 0

def test_theta_negative_put() -> None:
    assert black_scholes_theta(ATM_PUT) < 0


# --- black_scholes_all consistency ---

def test_all_matches_individual_functions_call() -> None:
    result = black_scholes_all(ATM_CALL)
    assert abs(result.price - black_scholes_price(ATM_CALL)) < 1e-10
    assert abs(result.delta - black_scholes_delta(ATM_CALL)) < 1e-10
    assert abs(result.gamma - black_scholes_gamma(ATM_CALL)) < 1e-10
    assert abs(result.vega - black_scholes_vega(ATM_CALL)) < 1e-10
    assert abs(result.theta - black_scholes_theta(ATM_CALL)) < 1e-10

def test_all_matches_individual_functions_put() -> None:
    result = black_scholes_all(ATM_PUT)
    assert abs(result.price - black_scholes_price(ATM_PUT)) < 1e-10
    assert abs(result.delta - black_scholes_delta(ATM_PUT)) < 1e-10


# --- Input validation ---

def test_raises_on_zero_expiry() -> None:
    inputs = BlackScholesInputs(
        spot=100.0, strike=100.0, time_to_expiry=0.0,
        risk_free_rate=0.05, volatility=0.20, option_type="call",
    )
    with pytest.raises(ValueError):
        black_scholes_price(inputs)

def test_raises_on_zero_vol() -> None:
    inputs = BlackScholesInputs(
        spot=100.0, strike=100.0, time_to_expiry=1.0,
        risk_free_rate=0.05, volatility=0.0, option_type="call",
    )
    with pytest.raises(ValueError):
        black_scholes_price(inputs)
