"""Tests for Phase 7 paper execution: prompt logic, order record, and connection gate."""
from __future__ import annotations

import pytest

from src.broker.paper_executor import PaperOrderRecord, prompt_confirm_paper_order
from src.broker.contract_mapper import StockContractSpec
from src.broker.order_builder import IBKROrderSpec
from src.data.ibkr_connection import IBKRConnection, IBKRUnavailableError


# ---------------------------------------------------------------------------
# prompt_confirm_paper_order
# ---------------------------------------------------------------------------

class TestPromptConfirmPaperOrder:
    def _call(self, answer: str) -> bool:
        return prompt_confirm_paper_order(
            sym="SPY",
            action="BUY",
            qty=50.0,
            notional=35_000.0,
            cost=7.0,
            input_fn=lambda _: answer,
        )

    def test_lowercase_y_returns_true(self):
        assert self._call("y") is True

    def test_uppercase_Y_returns_true(self):
        assert self._call("Y") is True

    def test_empty_input_returns_false(self):
        assert self._call("") is False

    def test_n_returns_false(self):
        assert self._call("n") is False

    def test_N_returns_false(self):
        assert self._call("N") is False

    def test_yes_returns_false(self):
        # Only exact 'y' accepted, not 'yes'
        assert self._call("yes") is False

    def test_whitespace_around_y_returns_true(self):
        # input_fn returns " y " — .strip() normalises it
        assert self._call(" y ") is True

    def test_whitespace_only_returns_false(self):
        assert self._call("   ") is False

    def test_arbitrary_string_returns_false(self):
        assert self._call("ok") is False

    def test_sell_side_prompt(self):
        result = prompt_confirm_paper_order(
            "SPY", "SELL", 30.0, 21_000.0, 4.2,
            input_fn=lambda _: "y",
        )
        assert result is True

    def test_decline_sell(self):
        result = prompt_confirm_paper_order(
            "QQQ", "SELL", 20.0, 8_600.0, 1.72,
            input_fn=lambda _: "",
        )
        assert result is False


# ---------------------------------------------------------------------------
# PaperOrderRecord
# ---------------------------------------------------------------------------

class TestPaperOrderRecord:
    def test_proposed_not_executed(self):
        rec = PaperOrderRecord(
            trade_date="2026-04-30",
            symbol="SPY",
            action="BUY",
            quantity=50.0,
            estimated_notional=35_000.0,
            estimated_cost_usd=7.0,
            proposed=True,
            executed=False,
            reason="user declined",
        )
        assert rec.proposed is True
        assert rec.executed is False
        assert rec.reason == "user declined"

    def test_executed_with_order_id(self):
        rec = PaperOrderRecord(
            trade_date="2026-04-30",
            symbol="SPY",
            action="BUY",
            quantity=50.0,
            estimated_notional=35_000.0,
            estimated_cost_usd=7.0,
            proposed=True,
            executed=True,
            order_id=12345,
            order_status="Submitted",
        )
        assert rec.executed is True
        assert rec.order_id == 12345
        assert rec.order_status == "Submitted"

    def test_defaults_for_optional_fields(self):
        rec = PaperOrderRecord(
            trade_date="2026-04-30",
            symbol="SPY",
            action="BUY",
            quantity=50.0,
            estimated_notional=35_000.0,
            estimated_cost_usd=7.0,
            proposed=True,
            executed=True,
        )
        assert rec.order_id is None
        assert rec.order_status == ""
        assert rec.reason == ""

    def test_not_proposed_skipped_record(self):
        rec = PaperOrderRecord(
            trade_date="2026-04-30",
            symbol="SPY",
            action="NONE",
            quantity=0.0,
            estimated_notional=0.0,
            estimated_cost_usd=0.0,
            proposed=False,
            executed=False,
            reason="below delta threshold",
        )
        assert rec.proposed is False
        assert rec.executed is False

    def test_is_mutable_dataclass(self):
        rec = PaperOrderRecord(
            trade_date="2026-04-30",
            symbol="SPY",
            action="BUY",
            quantity=50.0,
            estimated_notional=35_000.0,
            estimated_cost_usd=7.0,
            proposed=True,
            executed=False,
        )
        rec.order_id = 99
        assert rec.order_id == 99


# ---------------------------------------------------------------------------
# IBKRConnection.place_paper_order — connection guard
# ---------------------------------------------------------------------------

class TestPlacePaperOrderConnectionGuard:
    def test_raises_when_not_connected(self):
        conn = IBKRConnection()
        stock_spec = StockContractSpec(symbol="SPY")
        order_spec = IBKROrderSpec(action="BUY", total_quantity=10.0)
        with pytest.raises(IBKRUnavailableError, match="Not connected"):
            conn.place_paper_order(stock_spec, order_spec)

    def test_raises_ibkr_unavailable_error_type(self):
        conn = IBKRConnection()
        stock_spec = StockContractSpec(symbol="QQQ")
        order_spec = IBKROrderSpec(action="SELL", total_quantity=5.0)
        err = None
        try:
            conn.place_paper_order(stock_spec, order_spec)
        except IBKRUnavailableError as e:
            err = e
        assert err is not None
        assert isinstance(err, RuntimeError)


# ---------------------------------------------------------------------------
# connect() raises when ib_insync missing (paper-execute prerequisite)
# ---------------------------------------------------------------------------

class TestPaperExecutePrerequisite:
    def test_connect_fails_gracefully_without_ib_insync(self, monkeypatch):
        import src.data.ibkr_connection as mod
        monkeypatch.setattr(mod, "_IB_INSYNC_AVAILABLE", False)
        conn = IBKRConnection()
        with pytest.raises(IBKRUnavailableError, match="ib_insync"):
            conn.connect()

    def test_paper_port_enforced(self):
        with pytest.raises(ValueError, match="7496"):
            IBKRConnection(port=7496)
