"""Portfolio domain objects and YAML config loader."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml


@dataclass
class OptionPosition:
    id: str
    underlying: str
    option_type: Literal["call", "put"]
    strike: float
    expiry: str           # ISO-8601 date string, e.g. "2026-06-19"
    quantity: int         # signed: negative = short
    multiplier: int       # shares per contract, typically 100
    implied_vol: float    # fallback IV when market IV unavailable


@dataclass
class UnderlyingPosition:
    underlying: str
    quantity: float       # signed: positive = long shares


@dataclass
class PortfolioBook:
    option_positions: list[OptionPosition]
    underlying_positions: dict[str, UnderlyingPosition]
    spot_prices: dict[str, float]
    risk_free_rate: float


def load_portfolio(config_path: Path) -> PortfolioBook:
    """Parse a demo_portfolio.yaml into a PortfolioBook."""
    raw = yaml.safe_load(config_path.read_text())

    options = [
        OptionPosition(
            id=pos["id"],
            underlying=pos["underlying"],
            option_type=pos["option_type"],
            strike=float(pos["strike"]),
            expiry=str(pos["expiry"]),
            quantity=int(pos["quantity"]),
            multiplier=int(pos["multiplier"]),
            implied_vol=float(pos["implied_vol"]),
        )
        for pos in raw.get("option_positions", [])
    ]

    underlying_positions = {
        sym: UnderlyingPosition(underlying=sym, quantity=float(data["quantity"]))
        for sym, data in raw.get("underlying_positions", {}).items()
    }

    spot_prices = {
        sym: float(price)
        for sym, price in raw.get("spot_prices", {}).items()
    }

    return PortfolioBook(
        option_positions=options,
        underlying_positions=underlying_positions,
        spot_prices=spot_prices,
        risk_free_rate=float(raw.get("risk_free_rate", 0.05)),
    )
