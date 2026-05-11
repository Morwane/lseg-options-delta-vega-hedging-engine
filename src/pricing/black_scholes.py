"""Black-Scholes option pricing and Greeks."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from scipy.stats import norm

_N = norm.cdf   # cumulative standard normal
_n = norm.pdf   # standard normal PDF


@dataclass
class BlackScholesInputs:
    spot: float
    strike: float
    time_to_expiry: float       # years; must be > 0
    risk_free_rate: float
    volatility: float           # annualised; must be > 0
    option_type: Literal["call", "put"]
    dividend_yield: float = 0.0


@dataclass
class BlackScholesResult:
    price: float
    delta: float
    gamma: float
    vega: float     # ∂V/∂σ per unit of sigma (not per 1%)
    theta: float    # ∂V/∂t per calendar day
    d1: float
    d2: float


def _validate(inputs: BlackScholesInputs) -> None:
    if inputs.time_to_expiry <= 0:
        raise ValueError(f"time_to_expiry must be positive, got {inputs.time_to_expiry}")
    if inputs.volatility <= 0:
        raise ValueError(f"volatility must be positive, got {inputs.volatility}")
    if inputs.spot <= 0:
        raise ValueError(f"spot must be positive, got {inputs.spot}")
    if inputs.strike <= 0:
        raise ValueError(f"strike must be positive, got {inputs.strike}")


def _d1_d2(
    S: float, K: float, T: float, r: float, sigma: float, q: float
) -> tuple[float, float]:
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def black_scholes_price(inputs: BlackScholesInputs) -> float:
    _validate(inputs)
    S, K, T, r, sigma, q = (
        inputs.spot, inputs.strike, inputs.time_to_expiry,
        inputs.risk_free_rate, inputs.volatility, inputs.dividend_yield,
    )
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    disc = math.exp(-r * T)
    eq = math.exp(-q * T)
    if inputs.option_type == "call":
        return float(S * eq * _N(d1) - K * disc * _N(d2))
    return float(K * disc * _N(-d2) - S * eq * _N(-d1))


def black_scholes_delta(inputs: BlackScholesInputs) -> float:
    _validate(inputs)
    S, K, T, r, sigma, q = (
        inputs.spot, inputs.strike, inputs.time_to_expiry,
        inputs.risk_free_rate, inputs.volatility, inputs.dividend_yield,
    )
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    eq = math.exp(-q * T)
    if inputs.option_type == "call":
        return float(eq * _N(d1))
    return float(eq * (_N(d1) - 1.0))


def black_scholes_gamma(inputs: BlackScholesInputs) -> float:
    _validate(inputs)
    S, K, T, r, sigma, q = (
        inputs.spot, inputs.strike, inputs.time_to_expiry,
        inputs.risk_free_rate, inputs.volatility, inputs.dividend_yield,
    )
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    eq = math.exp(-q * T)
    return float(eq * _n(d1) / (S * sigma * math.sqrt(T)))


def black_scholes_vega(inputs: BlackScholesInputs) -> float:
    """Vega = ∂V/∂σ per unit of sigma (divide by 100 to get per 1% move)."""
    _validate(inputs)
    S, K, T, r, sigma, q = (
        inputs.spot, inputs.strike, inputs.time_to_expiry,
        inputs.risk_free_rate, inputs.volatility, inputs.dividend_yield,
    )
    d1, _ = _d1_d2(S, K, T, r, sigma, q)
    eq = math.exp(-q * T)
    return float(S * eq * _n(d1) * math.sqrt(T))


def black_scholes_theta(inputs: BlackScholesInputs) -> float:
    """Theta per calendar day (negative = time decay cost)."""
    _validate(inputs)
    S, K, T, r, sigma, q = (
        inputs.spot, inputs.strike, inputs.time_to_expiry,
        inputs.risk_free_rate, inputs.volatility, inputs.dividend_yield,
    )
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    eq = math.exp(-q * T)
    disc = math.exp(-r * T)
    decay = -S * eq * _n(d1) * sigma / (2.0 * math.sqrt(T))
    if inputs.option_type == "call":
        carry = -r * K * disc * _N(d2) + q * S * eq * _N(d1)
    else:
        carry = r * K * disc * _N(-d2) - q * S * eq * _N(-d1)
    return float((decay + carry) / 365.0)


def black_scholes_all(inputs: BlackScholesInputs) -> BlackScholesResult:
    """Compute price and all first-order Greeks in a single pass."""
    _validate(inputs)
    S, K, T, r, sigma, q = (
        inputs.spot, inputs.strike, inputs.time_to_expiry,
        inputs.risk_free_rate, inputs.volatility, inputs.dividend_yield,
    )
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    eq = math.exp(-q * T)
    disc = math.exp(-r * T)
    sqrt_T = math.sqrt(T)
    nd1 = float(_n(d1))

    if inputs.option_type == "call":
        price = float(S * eq * _N(d1) - K * disc * _N(d2))
        delta = float(eq * _N(d1))
        carry = -r * K * disc * _N(d2) + q * S * eq * _N(d1)
    else:
        price = float(K * disc * _N(-d2) - S * eq * _N(-d1))
        delta = float(eq * (_N(d1) - 1.0))
        carry = r * K * disc * _N(-d2) - q * S * eq * _N(-d1)

    gamma = float(eq * nd1 / (S * sigma * sqrt_T))
    vega = float(S * eq * nd1 * sqrt_T)
    theta = float((-S * eq * nd1 * sigma / (2.0 * sqrt_T) + carry) / 365.0)

    return BlackScholesResult(
        price=price, delta=delta, gamma=gamma, vega=vega, theta=theta, d1=d1, d2=d2
    )
