"""Tests for src/broker/contract_mapper.py."""
from __future__ import annotations

import pytest

from src.broker.contract_mapper import (
    OptionContractSpec,
    StockContractSpec,
    option_contract_spec,
    underlying_contract_spec,
)
from src.portfolio.positions import OptionPosition


# ---------------------------------------------------------------------------
# StockContractSpec
# ---------------------------------------------------------------------------

class TestStockContractSpec:
    def test_defaults(self):
        spec = StockContractSpec(symbol="SPY")
        assert spec.exchange == "SMART"
        assert spec.currency == "USD"

    def test_custom_exchange(self):
        spec = StockContractSpec(symbol="SPY", exchange="ARCA")
        assert spec.exchange == "ARCA"

    def test_frozen(self):
        spec = StockContractSpec(symbol="SPY")
        with pytest.raises(Exception):
            spec.symbol = "QQQ"  # type: ignore[misc]


class TestUnderlyingContractSpec:
    def test_returns_correct_symbol(self):
        spec = underlying_contract_spec("SPY")
        assert spec.symbol == "SPY"

    def test_default_exchange(self):
        spec = underlying_contract_spec("QQQ")
        assert spec.exchange == "SMART"

    def test_default_currency(self):
        spec = underlying_contract_spec("TLT")
        assert spec.currency == "USD"

    def test_custom_exchange_and_currency(self):
        spec = underlying_contract_spec("GLD", exchange="ARCA", currency="USD")
        assert spec.exchange == "ARCA"
        assert spec.currency == "USD"

    def test_returns_stock_contract_spec(self):
        spec = underlying_contract_spec("SPY")
        assert isinstance(spec, StockContractSpec)


# ---------------------------------------------------------------------------
# OptionContractSpec
# ---------------------------------------------------------------------------

class TestOptionContractSpec:
    def test_defaults(self):
        spec = OptionContractSpec(
            symbol="SPY", expiry="20260619", strike=700.0, right="C"
        )
        assert spec.exchange == "SMART"
        assert spec.currency == "USD"
        assert spec.multiplier == 100

    def test_frozen(self):
        spec = OptionContractSpec(
            symbol="SPY", expiry="20260619", strike=700.0, right="C"
        )
        with pytest.raises(Exception):
            spec.strike = 710.0  # type: ignore[misc]


def _make_option_position(
    option_type: str = "call",
    expiry: str = "2026-06-19",
    strike: float = 700.0,
    multiplier: int = 100,
) -> OptionPosition:
    return OptionPosition(
        id="test_opt",
        underlying="SPY",
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        quantity=1,
        multiplier=multiplier,
        implied_vol=0.20,
    )


class TestOptionContractSpecFromPosition:
    def test_call_right_is_C(self):
        spec = option_contract_spec(_make_option_position(option_type="call"))
        assert spec.right == "C"

    def test_put_right_is_P(self):
        spec = option_contract_spec(_make_option_position(option_type="put"))
        assert spec.right == "P"

    def test_expiry_dashes_removed(self):
        spec = option_contract_spec(_make_option_position(expiry="2026-06-19"))
        assert spec.expiry == "20260619"
        assert "-" not in spec.expiry

    def test_expiry_2027(self):
        spec = option_contract_spec(_make_option_position(expiry="2027-01-15"))
        assert spec.expiry == "20270115"

    def test_symbol_from_underlying(self):
        spec = option_contract_spec(_make_option_position())
        assert spec.symbol == "SPY"

    def test_strike_preserved(self):
        spec = option_contract_spec(_make_option_position(strike=645.0))
        assert spec.strike == 645.0

    def test_multiplier_preserved(self):
        spec = option_contract_spec(_make_option_position(multiplier=100))
        assert spec.multiplier == 100

    def test_returns_option_contract_spec_type(self):
        spec = option_contract_spec(_make_option_position())
        assert isinstance(spec, OptionContractSpec)
