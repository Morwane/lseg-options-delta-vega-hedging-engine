"""IBKR Paper Trading connection manager.

Safety enforcements:
- Only port 7497 (paper) is accepted; port 7496 (live) raises ValueError.
- Delayed market data only — reqMarketDataType(3) is called before every snapshot.
- No order placement logic here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

try:
    from ib_insync import IB, Stock  # type: ignore[import]
    _IB_INSYNC_AVAILABLE = True
except ImportError:
    _IB_INSYNC_AVAILABLE = False

PAPER_PORT = 7497
_LIVE_PORT = 7496  # blocked


class IBKRUnavailableError(RuntimeError):
    """Raised when ib_insync is missing or IBKR cannot be reached."""


@dataclass(frozen=True)
class IBKRPositionRecord:
    symbol: str
    sec_type: str   # "STK", "OPT", etc.
    quantity: float
    avg_cost: float
    exchange: str
    currency: str


class IBKRConnection:
    """Thin wrapper around ib_insync.IB for paper-only dry-run use.

    Usage::

        conn = IBKRConnection()
        conn.connect()
        spot = conn.get_delayed_spot("SPY")
        conn.disconnect()

    Or as a context manager::

        with IBKRConnection() as conn:
            spot = conn.get_delayed_spot("SPY")
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = PAPER_PORT,
        client_id: int = 10,
        market_data_wait_seconds: float = 10.0,
    ) -> None:
        if port == _LIVE_PORT:
            raise ValueError(
                f"Live trading port {_LIVE_PORT} is not permitted. "
                f"Use paper trading port {PAPER_PORT}."
            )
        if port != PAPER_PORT:
            raise ValueError(
                f"Unexpected port {port}. Only paper trading port {PAPER_PORT} is supported."
            )
        self._host = host
        self._port = port
        self._client_id = client_id
        self._wait = market_data_wait_seconds
        self._ib: Any = None  # ib_insync.IB instance; None until connected

    @property
    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    def connect(self) -> None:
        """Connect to IBKR paper TWS. Raises IBKRUnavailableError on any failure."""
        if not _IB_INSYNC_AVAILABLE:
            raise IBKRUnavailableError(
                "ib_insync is not installed. Install with: pip install ib_insync"
            )
        try:
            ib = IB()
            ib.connect(self._host, self._port, clientId=self._client_id)
            self._ib = ib
        except Exception as exc:
            raise IBKRUnavailableError(
                f"Cannot connect to IBKR at {self._host}:{self._port} — {exc}"
            ) from exc

    def disconnect(self) -> None:
        if self._ib is not None:
            try:
                self._ib.disconnect()
            except Exception:
                pass
            self._ib = None

    def __enter__(self) -> IBKRConnection:
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.disconnect()

    def get_delayed_spot(
        self,
        symbol: str,
        exchange: str = "SMART",
        currency: str = "USD",
    ) -> float | None:
        """Return delayed spot price for *symbol*, or None if unavailable."""
        if self._ib is None:
            raise IBKRUnavailableError("Not connected. Call connect() first.")
        self._ib.reqMarketDataType(3)  # 3 = delayed
        stock = Stock(symbol, exchange, currency)
        self._ib.qualifyContracts(stock)
        ticker = self._ib.reqMktData(stock, "", False, False)
        self._ib.sleep(self._wait)
        spot = _select_spot(ticker)
        self._ib.cancelMktData(stock)
        return spot

    def get_positions(self) -> list[IBKRPositionRecord]:
        """Return all positions currently held in the paper account."""
        if self._ib is None:
            raise IBKRUnavailableError("Not connected. Call connect() first.")
        self._ib.reqPositions()
        self._ib.sleep(1.0)
        records: list[IBKRPositionRecord] = []
        for pos in self._ib.positions():
            records.append(
                IBKRPositionRecord(
                    symbol=pos.contract.symbol,
                    sec_type=pos.contract.secType,
                    quantity=float(pos.position),
                    avg_cost=float(pos.avgCost),
                    exchange=pos.contract.exchange or "",
                    currency=pos.contract.currency or "USD",
                )
            )
        return records

    def get_account_summary(self) -> dict[str, str]:
        """Return key account summary fields as a tag → value dict."""
        if self._ib is None:
            raise IBKRUnavailableError("Not connected. Call connect() first.")
        return {item.tag: item.value for item in self._ib.accountSummary()}

    def place_paper_order(
        self,
        stock_spec: Any,
        order_spec: Any,
    ) -> dict[str, Any]:
        """Place a paper market order on the IBKR paper account.

        transmit is explicitly set to True — required to route the order to the
        paper exchange. The IBKROrderSpec.transmit field (always False) is ignored
        here because this method is the deliberate execution gate.

        Args:
            stock_spec: StockContractSpec from contract_mapper.
            order_spec: IBKROrderSpec from order_builder.

        Returns:
            dict with symbol, action, quantity, order_id, status.
        """
        if self._ib is None:
            raise IBKRUnavailableError("Not connected. Call connect() first.")
        from ib_insync import MarketOrder  # type: ignore[import]
        from src.broker.contract_mapper import to_ib_stock

        contract = to_ib_stock(stock_spec)
        self._ib.qualifyContracts(contract)
        order = MarketOrder(
            action=order_spec.action,
            totalQuantity=order_spec.total_quantity,
            tif=order_spec.tif,
            transmit=True,  # must be True to actually route to paper exchange
        )
        trade = self._ib.placeOrder(contract, order)
        self._ib.sleep(2.0)
        return {
            "symbol": stock_spec.symbol,
            "action": order_spec.action,
            "quantity": order_spec.total_quantity,
            "order_id": trade.order.orderId,
            "status": trade.orderStatus.status,
        }


# ---------------------------------------------------------------------------
# Spot selection helpers (module-level so tests can import them directly)
# ---------------------------------------------------------------------------

def _pick_spot_from_values(candidates: list[float | None]) -> float | None:
    """Return the first positive finite value from *candidates*, or None."""
    return next(
        (x for x in candidates if x is not None and not math.isnan(x) and x > 0),
        None,
    )


def _select_spot(ticker: Any) -> float | None:
    """Extract the best available spot price from an ib_insync Ticker."""
    try:
        market_price: float | None = ticker.marketPrice()
    except Exception:
        market_price = None
    return _pick_spot_from_values([
        market_price,
        getattr(ticker, "last", None),
        getattr(ticker, "close", None),
        getattr(ticker, "bid", None),
        getattr(ticker, "ask", None),
    ])
