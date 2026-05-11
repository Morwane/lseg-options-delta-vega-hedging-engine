"""Portfolio-level Greeks aggregation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.pricing.black_scholes import BlackScholesInputs, black_scholes_all
from src.portfolio.positions import PortfolioBook


@dataclass
class PositionGreeks:
    id: str
    underlying: str
    option_type: str
    strike: float
    expiry: str
    quantity: int
    multiplier: int
    spot: float
    implied_vol: float
    time_to_expiry: float
    # per-contract option Greeks
    option_price: float
    option_delta: float
    option_gamma: float
    option_vega: float
    option_theta: float
    # position-level: quantity × multiplier × greek
    position_delta: float
    position_gamma: float
    position_vega: float
    position_theta: float


@dataclass
class UnderlyingExposure:
    underlying: str
    spot: float
    net_delta: float
    net_gamma: float
    net_vega: float
    net_theta: float
    num_positions: int


def _years_to_expiry(expiry_str: str, as_of: date) -> float:
    return (date.fromisoformat(expiry_str) - as_of).days / 365.0


def compute_position_greeks(
    book: PortfolioBook,
    as_of: date | None = None,
) -> list[PositionGreeks]:
    """Compute Black-Scholes Greeks for every non-expired option in the book."""
    valuation_date = as_of or date.today()
    results: list[PositionGreeks] = []

    for pos in book.option_positions:
        spot = book.spot_prices.get(pos.underlying)
        if spot is None:
            raise ValueError(f"No spot price for underlying '{pos.underlying}'")

        T = _years_to_expiry(pos.expiry, valuation_date)
        if T <= 0:
            continue  # expired — skip silently

        inputs = BlackScholesInputs(
            spot=spot,
            strike=pos.strike,
            time_to_expiry=T,
            risk_free_rate=book.risk_free_rate,
            volatility=pos.implied_vol,
            option_type=pos.option_type,
        )
        g = black_scholes_all(inputs)
        scale = pos.quantity * pos.multiplier

        results.append(
            PositionGreeks(
                id=pos.id,
                underlying=pos.underlying,
                option_type=pos.option_type,
                strike=pos.strike,
                expiry=pos.expiry,
                quantity=pos.quantity,
                multiplier=pos.multiplier,
                spot=spot,
                implied_vol=pos.implied_vol,
                time_to_expiry=T,
                option_price=g.price,
                option_delta=g.delta,
                option_gamma=g.gamma,
                option_vega=g.vega,
                option_theta=g.theta,
                position_delta=scale * g.delta,
                position_gamma=scale * g.gamma,
                position_vega=scale * g.vega,
                position_theta=scale * g.theta,
            )
        )

    return results


def aggregate_by_underlying(
    position_greeks: list[PositionGreeks],
    spot_prices: dict[str, float],
) -> dict[str, UnderlyingExposure]:
    """Sum position-level Greeks by underlying symbol."""
    buckets: dict[str, dict] = {}

    for pg in position_greeks:
        if pg.underlying not in buckets:
            buckets[pg.underlying] = {
                "net_delta": 0.0,
                "net_gamma": 0.0,
                "net_vega": 0.0,
                "net_theta": 0.0,
                "num_positions": 0,
            }
        b = buckets[pg.underlying]
        b["net_delta"] += pg.position_delta
        b["net_gamma"] += pg.position_gamma
        b["net_vega"] += pg.position_vega
        b["net_theta"] += pg.position_theta
        b["num_positions"] += 1

    return {
        sym: UnderlyingExposure(
            underlying=sym,
            spot=spot_prices.get(sym, float("nan")),
            **vals,
        )
        for sym, vals in buckets.items()
    }
