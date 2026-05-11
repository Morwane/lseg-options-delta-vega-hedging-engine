"""Tests for src/data/ibkr_connection.py.

All tests run without an active IBKR connection (no ib_insync calls made).
"""
from __future__ import annotations

import math
import pytest

from src.data.ibkr_connection import (
    IBKRConnection,
    IBKRPositionRecord,
    IBKRUnavailableError,
    PAPER_PORT,
    _pick_spot_from_values,
)

_LIVE_PORT = 7496


# ---------------------------------------------------------------------------
# IBKRConnection constructor guards
# ---------------------------------------------------------------------------

class TestIBKRConnectionInit:
    def test_paper_port_accepted(self):
        conn = IBKRConnection(port=PAPER_PORT)
        assert conn._port == PAPER_PORT

    def test_default_port_is_paper(self):
        conn = IBKRConnection()
        assert conn._port == PAPER_PORT

    def test_live_port_rejected(self):
        with pytest.raises(ValueError, match="7496"):
            IBKRConnection(port=_LIVE_PORT)

    def test_arbitrary_port_rejected(self):
        with pytest.raises(ValueError, match="9999"):
            IBKRConnection(port=9999)

    def test_not_connected_on_init(self):
        conn = IBKRConnection()
        assert conn.is_connected is False

    def test_ib_is_none_on_init(self):
        conn = IBKRConnection()
        assert conn._ib is None

    def test_custom_host_stored(self):
        conn = IBKRConnection(host="192.168.1.100")
        assert conn._host == "192.168.1.100"

    def test_custom_client_id_stored(self):
        conn = IBKRConnection(client_id=42)
        assert conn._client_id == 42

    def test_custom_wait_stored(self):
        conn = IBKRConnection(market_data_wait_seconds=5.0)
        assert conn._wait == 5.0


# ---------------------------------------------------------------------------
# connect() raises IBKRUnavailableError when ib_insync is missing
# ---------------------------------------------------------------------------

class TestConnectWithoutIBKR:
    def test_connect_raises_when_ib_insync_unavailable(self, monkeypatch):
        import src.data.ibkr_connection as mod
        monkeypatch.setattr(mod, "_IB_INSYNC_AVAILABLE", False)
        conn = IBKRConnection()
        with pytest.raises(IBKRUnavailableError, match="ib_insync"):
            conn.connect()

    def test_disconnect_is_noop_when_not_connected(self):
        conn = IBKRConnection()
        conn.disconnect()  # must not raise
        assert conn._ib is None


# ---------------------------------------------------------------------------
# _pick_spot_from_values
# ---------------------------------------------------------------------------

class TestPickSpotFromValues:
    def test_first_valid_returned(self):
        assert _pick_spot_from_values([100.0, 200.0, 300.0]) == 100.0

    def test_skips_none(self):
        assert _pick_spot_from_values([None, None, 150.0]) == 150.0

    def test_skips_nan(self):
        assert _pick_spot_from_values([float("nan"), 200.0]) == 200.0

    def test_skips_negative(self):
        assert _pick_spot_from_values([-1.0, 500.0]) == 500.0

    def test_skips_zero(self):
        assert _pick_spot_from_values([0.0, 600.0]) == 600.0

    def test_all_invalid_returns_none(self):
        assert _pick_spot_from_values([None, float("nan"), -5.0, 0.0]) is None

    def test_empty_list_returns_none(self):
        assert _pick_spot_from_values([]) is None

    def test_single_valid(self):
        assert _pick_spot_from_values([712.08]) == 712.08

    def test_mixed_nans_and_valid(self):
        assert _pick_spot_from_values([
            float("nan"), None, -1.0, 0.0, 712.03
        ]) == 712.03


# ---------------------------------------------------------------------------
# IBKRPositionRecord
# ---------------------------------------------------------------------------

class TestIBKRPositionRecord:
    def test_frozen(self):
        rec = IBKRPositionRecord(
            symbol="SPY", sec_type="STK", quantity=100.0,
            avg_cost=700.0, exchange="ARCA", currency="USD",
        )
        with pytest.raises(Exception):
            rec.quantity = 200.0  # type: ignore[misc]

    def test_stk_position_attributes(self):
        rec = IBKRPositionRecord(
            symbol="SPY", sec_type="STK", quantity=50.0,
            avg_cost=710.25, exchange="SMART", currency="USD",
        )
        assert rec.symbol == "SPY"
        assert rec.sec_type == "STK"
        assert rec.quantity == 50.0
        assert rec.avg_cost == 710.25

    def test_opt_position_type(self):
        rec = IBKRPositionRecord(
            symbol="SPY", sec_type="OPT", quantity=1.0,
            avg_cost=4.50, exchange="SMART", currency="USD",
        )
        assert rec.sec_type == "OPT"

    def test_empty_exchange(self):
        rec = IBKRPositionRecord(
            symbol="SPY", sec_type="STK", quantity=10.0,
            avg_cost=700.0, exchange="", currency="USD",
        )
        assert rec.exchange == ""


# ---------------------------------------------------------------------------
# IBKRUnavailableError
# ---------------------------------------------------------------------------

class TestIBKRUnavailableError:
    def test_is_runtime_error(self):
        err = IBKRUnavailableError("test")
        assert isinstance(err, RuntimeError)

    def test_message_preserved(self):
        err = IBKRUnavailableError("cannot connect")
        assert "cannot connect" in str(err)
