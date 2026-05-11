"""Implied volatility solver via bisection."""
from __future__ import annotations

from typing import Literal

from src.pricing.black_scholes import BlackScholesInputs, black_scholes_price


def implied_vol_bisection(
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    option_type: Literal["call", "put"],
    dividend_yield: float = 0.0,
    sigma_low: float = 1e-4,
    sigma_high: float = 5.0,
    tolerance: float = 1e-6,
    max_iterations: int = 300,
) -> float:
    """Return implied vol that reproduces market_price.

    Uses bisection on the Black-Scholes price function.
    Raises ValueError for invalid inputs or when market_price is outside the
    no-arbitrage range achievable within [sigma_low, sigma_high].
    """
    if time_to_expiry <= 0:
        raise ValueError(f"time_to_expiry must be positive, got {time_to_expiry}")
    if spot <= 0:
        raise ValueError(f"spot must be positive, got {spot}")
    if strike <= 0:
        raise ValueError(f"strike must be positive, got {strike}")
    if market_price <= 0:
        raise ValueError(f"market_price must be positive, got {market_price}")

    def bs_price(sigma: float) -> float:
        return black_scholes_price(
            BlackScholesInputs(
                spot=spot,
                strike=strike,
                time_to_expiry=time_to_expiry,
                risk_free_rate=risk_free_rate,
                volatility=sigma,
                option_type=option_type,
                dividend_yield=dividend_yield,
            )
        )

    price_low = bs_price(sigma_low)
    price_high = bs_price(sigma_high)

    # market_price must be bracketed by [price_low, price_high]
    if market_price < price_low or market_price > price_high:
        raise ValueError(
            f"market_price {market_price:.6f} is outside the no-arbitrage range "
            f"[{price_low:.6f}, {price_high:.6f}] for sigma in "
            f"[{sigma_low}, {sigma_high}]"
        )

    for _ in range(max_iterations):
        sigma_mid = 0.5 * (sigma_low + sigma_high)
        price_mid = bs_price(sigma_mid)
        diff = price_mid - market_price

        if abs(diff) < tolerance:
            return sigma_mid

        if diff < 0:
            sigma_low = sigma_mid
        else:
            sigma_high = sigma_mid

        if (sigma_high - sigma_low) < tolerance:
            return 0.5 * (sigma_low + sigma_high)

    # Exhausted iterations — return best mid-point estimate
    return 0.5 * (sigma_low + sigma_high)
