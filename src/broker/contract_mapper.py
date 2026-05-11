"""Map internal portfolio domain objects to IBKR contract specifications.

Pure-data layer: StockContractSpec and OptionContractSpec are plain dataclasses.
The to_ib_*() helpers import ib_insync at call time so the module is importable
even when ib_insync is not installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.portfolio.positions import OptionPosition


@dataclass(frozen=True)
class StockContractSpec:
    """Specification for an IBKR stock/ETF contract."""
    symbol: str
    exchange: str = "SMART"
    currency: str = "USD"


@dataclass(frozen=True)
class OptionContractSpec:
    """Specification for an IBKR listed equity option contract."""
    symbol: str
    expiry: str     # YYYYMMDD (no dashes)
    strike: float
    right: str      # "C" for call, "P" for put
    exchange: str = "SMART"
    currency: str = "USD"
    multiplier: int = 100


def underlying_contract_spec(
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
) -> StockContractSpec:
    """Return the IBKR contract spec for an underlying stock/ETF."""
    return StockContractSpec(symbol=symbol, exchange=exchange, currency=currency)


def option_contract_spec(pos: OptionPosition) -> OptionContractSpec:
    """Return the IBKR contract spec for an option position.

    Expiry is converted from ISO-8601 ("2026-06-19") to YYYYMMDD ("20260619").
    """
    expiry_nodash = pos.expiry.replace("-", "")
    right = "C" if pos.option_type == "call" else "P"
    return OptionContractSpec(
        symbol=pos.underlying,
        expiry=expiry_nodash,
        strike=pos.strike,
        right=right,
        multiplier=pos.multiplier,
    )


def to_ib_stock(spec: StockContractSpec) -> Any:
    """Construct an ib_insync Stock contract from a StockContractSpec.

    Requires ib_insync to be installed.
    """
    from ib_insync import Stock  # type: ignore[import]
    return Stock(spec.symbol, spec.exchange, spec.currency)


def to_ib_option(spec: OptionContractSpec) -> Any:
    """Construct an ib_insync Option contract from an OptionContractSpec.

    Requires ib_insync to be installed.
    """
    from ib_insync import Option  # type: ignore[import]
    return Option(
        spec.symbol,
        spec.expiry,
        spec.strike,
        spec.right,
        spec.exchange,
    )
