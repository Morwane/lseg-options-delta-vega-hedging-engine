"""Daily delta-hedge dry-run and paper-execution entry point.

Usage
-----
python scripts/run_daily_hedge.py --dry-run
python scripts/run_daily_hedge.py --paper-execute

--dry-run flow
--------------
1. Load option book from config/demo_portfolio.yaml.
2. Load hedge rules from config/hedge_rules.yaml.
3. Try connecting to IBKR paper TWS on port 7497.
   - Connected: replace config spots with delayed market data; read paper positions.
   - Unavailable: fall back to config spots and config underlying positions.
4. Compute Black-Scholes Greeks for every live option in the book.
5. Aggregate portfolio delta per underlying.
6. Generate hedge recommendations — no orders placed.
7. Print summary; save CSV to outputs/reports/daily_hedge_dry_run.csv.

--paper-execute flow
--------------------
Same as --dry-run through step 6, but IBKR must be reachable (hard failure if not).
For each actionable recommendation the user is prompted:
    Send PAPER order for SPY? [y/N]:
Default is No. Only 'y' or 'Y' sends the order to the paper exchange.
Execution log saved to outputs/reports/paper_execution_log.csv.

Safety
------
- --dry-run never places orders.
- --paper-execute requires explicit 'y' at the terminal for each order.
- No live port (7496) is ever contacted.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.broker.contract_mapper import StockContractSpec, underlying_contract_spec
from src.broker.order_builder import IBKROrderSpec, build_market_order
from src.broker.paper_executor import PaperOrderRecord, prompt_confirm_paper_order
from src.data.ibkr_connection import IBKRConnection, IBKRPositionRecord, IBKRUnavailableError
from src.hedging.delta_hedger import HedgeRecommendation, recommend_delta_hedge
from src.hedging.rebalance_rules import HedgeRules, load_hedge_rules
from src.portfolio.exposures import UnderlyingExposure, aggregate_by_underlying, compute_position_greeks
from src.portfolio.positions import PortfolioBook, load_portfolio

_CONFIG = ROOT / "config"
_OUTPUT = ROOT / "outputs" / "reports"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Daily delta-hedge — dry-run and paper-execution entry point."
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Compute hedge recommendations without placing any orders.",
    )
    mode.add_argument(
        "--paper-execute",
        dest="paper_execute",
        action="store_true",
        help="Paper-execute hedge orders with per-order terminal confirmation.",
    )
    p.add_argument(
        "--portfolio-config",
        type=Path,
        default=_CONFIG / "demo_portfolio.yaml",
        help="Path to portfolio YAML.",
    )
    p.add_argument(
        "--rules-config",
        type=Path,
        default=_CONFIG / "hedge_rules.yaml",
        help="Path to hedge rules YAML.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=_OUTPUT,
        help="Directory for CSV output.",
    )
    p.add_argument(
        "--ibkr-wait",
        type=float,
        default=10.0,
        help="Seconds to wait for delayed market data from IBKR.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# IBKR data helpers
# ---------------------------------------------------------------------------

def _fetch_spots_and_positions(
    conn: IBKRConnection,
    underlyings: set[str],
) -> tuple[dict[str, float], list[IBKRPositionRecord], dict[str, str]]:
    """Fetch delayed spots, paper positions, and account summary from an open connection."""
    spot_map: dict[str, float] = {}
    for sym in sorted(underlyings):
        spot = conn.get_delayed_spot(sym)
        if spot is not None and spot > 0:
            spot_map[sym] = spot
            print(f"[IBKR] {sym} delayed spot: ${spot:.4f}")
        else:
            print(f"[IBKR] {sym}: no delayed spot received — will use config fallback.")

    positions = conn.get_positions()
    account = conn.get_account_summary()
    return spot_map, positions, account


def _try_fetch_ibkr_data(
    underlyings: set[str],
    wait_seconds: float,
) -> tuple[dict[str, float], list[IBKRPositionRecord], dict[str, str], bool]:
    """Open a transient IBKR connection, fetch data, then close.

    Returns (spot_map, positions, account, connected).
    connected=False when IBKR is unavailable — callers use config fallback.
    """
    try:
        conn = IBKRConnection(market_data_wait_seconds=wait_seconds)
        conn.connect()
        print("[IBKR] Connected to paper trading account.")
    except IBKRUnavailableError as exc:
        print(f"[WARN] IBKR unavailable: {exc}")
        return {}, [], {}, False

    try:
        spot_map, positions, account = _fetch_spots_and_positions(conn, underlyings)
    except Exception as exc:
        print(f"[WARN] IBKR data fetch failed: {exc}")
        spot_map, positions, account = {}, [], {}
    finally:
        conn.disconnect()
        print("[IBKR] Disconnected.")

    return spot_map, positions, account, True


# ---------------------------------------------------------------------------
# Shared hedge-state builder
# ---------------------------------------------------------------------------

def _build_hedge_state(
    portfolio: PortfolioBook,
    rules: HedgeRules,
    ibkr_spots: dict[str, float],
    ibkr_positions: list[IBKRPositionRecord],
    ibkr_connected: bool,
    valuation_date: date,
) -> tuple[
    dict[str, float],
    list,
    dict[str, UnderlyingExposure],
    list[HedgeRecommendation],
    dict[str, IBKROrderSpec | None],
]:
    """Return (effective_spots, position_greeks, exposures, recommendations, order_specs).

    Shared by --dry-run and --paper-execute after their data-fetch phase.
    """
    # Merge IBKR spots over config spots
    effective_spots = dict(portfolio.spot_prices)
    for sym, spot in ibkr_spots.items():
        effective_spots[sym] = spot
        old = portfolio.spot_prices.get(sym)
        if old is not None and abs(spot - old) / max(old, 1.0) > 0.01:
            print(f"[INFO] {sym} spot updated: config ${old:.2f} → IBKR ${spot:.2f}")

    effective_portfolio = PortfolioBook(
        option_positions=portfolio.option_positions,
        underlying_positions=portfolio.underlying_positions,
        spot_prices=effective_spots,
        risk_free_rate=portfolio.risk_free_rate,
    )

    position_greeks = compute_position_greeks(effective_portfolio, as_of=valuation_date)
    exposures = aggregate_by_underlying(position_greeks, effective_spots)

    # Current underlying positions: IBKR paper if connected, else config
    ibkr_stk: dict[str, float] = {
        p.symbol: p.quantity for p in ibkr_positions if p.sec_type == "STK"
    }

    def _current_qty(sym: str) -> float:
        if ibkr_connected:
            return ibkr_stk.get(sym, 0.0)
        up = portfolio.underlying_positions.get(sym)
        return up.quantity if up else 0.0

    recommendations: list[HedgeRecommendation] = [
        recommend_delta_hedge(
            underlying=sym,
            portfolio_delta=exp.net_delta,
            current_underlying_position=_current_qty(sym),
            spot=exp.spot,
            rules=rules,
        )
        for sym, exp in exposures.items()
    ]

    order_specs: dict[str, IBKROrderSpec | None] = {
        rec.underlying: build_market_order(rec) for rec in recommendations
    }

    return effective_spots, position_greeks, exposures, recommendations, order_specs


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

def _run_dry_run(args: argparse.Namespace) -> int:
    if not args.portfolio_config.exists():
        print(f"[ERROR] Portfolio config not found: {args.portfolio_config}")
        return 1
    if not args.rules_config.exists():
        print(f"[ERROR] Hedge rules config not found: {args.rules_config}")
        return 1

    portfolio = load_portfolio(args.portfolio_config)
    rules = load_hedge_rules(args.rules_config)
    valuation_date = date.today()

    print(f"[INFO] Valuation date   : {valuation_date}")
    print(f"[INFO] Option positions : {len(portfolio.option_positions)}")
    print("[INFO] Dry-run mode     : orders will NOT be placed")

    underlyings: set[str] = {pos.underlying for pos in portfolio.option_positions}
    ibkr_spots, ibkr_positions, ibkr_account, ibkr_connected = _try_fetch_ibkr_data(
        underlyings, args.ibkr_wait
    )

    if ibkr_account:
        avail = ibkr_account.get("AvailableFunds", "N/A")
        netliq = ibkr_account.get("NetLiquidation", "N/A")
        print(f"[IBKR] AvailableFunds: {avail}  NetLiquidation: {netliq}")
    if not ibkr_connected:
        print("[INFO] Using config spot prices as fallback.")

    effective_spots, position_greeks, exposures, recommendations, order_specs = (
        _build_hedge_state(
            portfolio, rules, ibkr_spots, ibkr_positions, ibkr_connected, valuation_date
        )
    )
    print(f"[INFO] Live option positions (non-expired): {len(position_greeks)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _save_dry_run_csv(
        valuation_date, recommendations, order_specs, ibkr_connected, args.output_dir
    )
    _print_dry_run_summary(recommendations, order_specs, ibkr_connected)
    return 0


def _save_dry_run_csv(
    valuation_date: date,
    recommendations: list[HedgeRecommendation],
    order_specs: dict[str, IBKROrderSpec | None],
    ibkr_connected: bool,
    output_dir: Path,
) -> None:
    spot_source = "IBKR delayed" if ibkr_connected else "config fallback"
    rows = [
        {
            "date": str(valuation_date),
            "underlying": r.underlying,
            "spot": round(r.spot, 4),
            "spot_source": spot_source,
            "portfolio_delta": round(r.portfolio_delta, 4),
            "current_position": r.current_underlying_position,
            "target_position": round(r.target_underlying_position, 4),
            "order_quantity": round(r.order_quantity, 4),
            "side": r.side,
            "estimated_notional": round(r.estimated_notional, 2),
            "estimated_cost_usd": round(r.estimated_transaction_cost, 2),
            "blocked": r.blocked,
            "dry_run": True,
            "ibkr_connected": ibkr_connected,
            "order_spec_action": order_specs[r.underlying].action if order_specs[r.underlying] else "NONE",
            "order_spec_qty": order_specs[r.underlying].total_quantity if order_specs[r.underlying] else 0,
            "reason": r.reason,
        }
        for r in recommendations
    ]
    path = output_dir / "daily_hedge_dry_run.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"\n[OUTPUT] {path}")


def _print_dry_run_summary(
    recommendations: list[HedgeRecommendation],
    order_specs: dict[str, IBKROrderSpec | None],
    ibkr_connected: bool,
) -> None:
    source = "IBKR delayed" if ibkr_connected else "config (IBKR unavailable)"
    print(f"\n{'=' * 68}")
    print("DAILY DELTA-HEDGE DRY-RUN — SUMMARY")
    print(f"{'=' * 68}")
    print(f"Spot source: {source}")
    print(
        f"\n{'Underlying':<12} {'Spot':>8} {'Net Δ':>10} {'Cur Pos':>8} "
        f"{'Target':>8} {'Order Qty':>10} {'Side':<5} {'Blocked'}"
    )
    print("-" * 68)
    for rec in recommendations:
        print(
            f"{rec.underlying:<12} {rec.spot:>8.2f} {rec.portfolio_delta:>10.2f} "
            f"{rec.current_underlying_position:>8.0f} "
            f"{rec.target_underlying_position:>8.2f} "
            f"{rec.order_quantity:>10.2f} {rec.side:<5} {str(rec.blocked)}"
        )
    print(f"\n{'Underlying':<12} {'Action':<6} {'Qty':>8}  Reason")
    print("-" * 68)
    for rec in recommendations:
        spec = order_specs[rec.underlying]
        print(
            f"{rec.underlying:<12} {spec.action if spec else 'NONE':<6} "
            f"{str(int(spec.total_quantity)) if spec else '—':>8}  {rec.reason}"
        )
    print(f"\n{'=' * 68}")
    print("DRY-RUN COMPLETE — no orders were placed.")
    print(f"{'=' * 68}\n")


# ---------------------------------------------------------------------------
# Paper execute
# ---------------------------------------------------------------------------

def _run_paper_execute(args: argparse.Namespace) -> int:
    if not args.portfolio_config.exists():
        print(f"[ERROR] Portfolio config not found: {args.portfolio_config}")
        return 1
    if not args.rules_config.exists():
        print(f"[ERROR] Hedge rules config not found: {args.rules_config}")
        return 1

    portfolio = load_portfolio(args.portfolio_config)
    rules = load_hedge_rules(args.rules_config)
    valuation_date = date.today()

    print(f"[INFO] Valuation date     : {valuation_date}")
    print(f"[INFO] Option positions   : {len(portfolio.option_positions)}")
    print("[INFO] Paper-execute mode : orders will be sent to IBKR paper exchange")
    print("[INFO]                      each order requires explicit 'y' confirmation")

    # IBKR is required for paper-execute — keep connection open for order placement
    try:
        conn = IBKRConnection(market_data_wait_seconds=args.ibkr_wait)
        conn.connect()
        print("[IBKR] Connected to paper trading account.")
    except IBKRUnavailableError as exc:
        print(f"[ERROR] IBKR unavailable: {exc}")
        print("[ERROR] --paper-execute requires an active IBKR paper TWS on port 7497.")
        return 1

    execution_log: list[PaperOrderRecord] = []

    try:
        underlyings: set[str] = {pos.underlying for pos in portfolio.option_positions}
        ibkr_spots, ibkr_positions, ibkr_account = _fetch_spots_and_positions(
            conn, underlyings
        )
        ibkr_connected = True

        if ibkr_account:
            avail = ibkr_account.get("AvailableFunds", "N/A")
            netliq = ibkr_account.get("NetLiquidation", "N/A")
            print(f"[IBKR] AvailableFunds: {avail}  NetLiquidation: {netliq}")

        effective_spots, position_greeks, exposures, recommendations, order_specs = (
            _build_hedge_state(
                portfolio, rules, ibkr_spots, ibkr_positions, ibkr_connected, valuation_date
            )
        )
        print(f"[INFO] Live option positions (non-expired): {len(position_greeks)}")

        print(f"\n{'=' * 68}")
        print("PAPER-EXECUTE ORDER REVIEW")
        print(f"{'=' * 68}")

        for rec in recommendations:
            spec = order_specs[rec.underlying]

            # Not actionable — log and skip without prompting
            if spec is None:
                reason = "blocked (notional limit)" if rec.blocked else "below delta threshold"
                print(f"\n  {rec.underlying}: no order — {reason}")
                execution_log.append(PaperOrderRecord(
                    trade_date=str(valuation_date),
                    symbol=rec.underlying,
                    action=rec.side,
                    quantity=0.0,
                    estimated_notional=rec.estimated_notional,
                    estimated_cost_usd=rec.estimated_transaction_cost,
                    proposed=False,
                    executed=False,
                    reason=reason,
                ))
                continue

            # Prompt user
            confirmed = prompt_confirm_paper_order(
                sym=rec.underlying,
                action=spec.action,
                qty=spec.total_quantity,
                notional=rec.estimated_notional,
                cost=rec.estimated_transaction_cost,
            )

            if not confirmed:
                print(f"  Skipped {rec.underlying}.")
                execution_log.append(PaperOrderRecord(
                    trade_date=str(valuation_date),
                    symbol=rec.underlying,
                    action=spec.action,
                    quantity=spec.total_quantity,
                    estimated_notional=rec.estimated_notional,
                    estimated_cost_usd=rec.estimated_transaction_cost,
                    proposed=True,
                    executed=False,
                    reason="user declined",
                ))
                continue

            # Place paper order
            try:
                stock_spec = underlying_contract_spec(rec.underlying)
                result = conn.place_paper_order(stock_spec, spec)
                print(
                    f"  [PAPER] Order sent: {result['action']} {result['quantity']:.0f} "
                    f"{result['symbol']}  orderId={result['order_id']}  "
                    f"status={result['status']}"
                )
                execution_log.append(PaperOrderRecord(
                    trade_date=str(valuation_date),
                    symbol=rec.underlying,
                    action=spec.action,
                    quantity=spec.total_quantity,
                    estimated_notional=rec.estimated_notional,
                    estimated_cost_usd=rec.estimated_transaction_cost,
                    proposed=True,
                    executed=True,
                    order_id=result["order_id"],
                    order_status=result["status"],
                ))
            except Exception as exc:
                print(f"  [ERROR] Order failed for {rec.underlying}: {exc}")
                execution_log.append(PaperOrderRecord(
                    trade_date=str(valuation_date),
                    symbol=rec.underlying,
                    action=spec.action,
                    quantity=spec.total_quantity,
                    estimated_notional=rec.estimated_notional,
                    estimated_cost_usd=rec.estimated_transaction_cost,
                    proposed=True,
                    executed=False,
                    reason=str(exc),
                ))

    finally:
        conn.disconnect()
        print("\n[IBKR] Disconnected.")

    # Save execution log
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _save_execution_log(execution_log, args.output_dir)
    _print_paper_execute_summary(execution_log)
    return 0


def _save_execution_log(
    log: list[PaperOrderRecord],
    output_dir: Path,
) -> None:
    rows = [
        {
            "date": r.trade_date,
            "symbol": r.symbol,
            "action": r.action,
            "quantity": r.quantity,
            "estimated_notional": round(r.estimated_notional, 2),
            "estimated_cost_usd": round(r.estimated_cost_usd, 2),
            "proposed": r.proposed,
            "executed": r.executed,
            "order_id": r.order_id,
            "order_status": r.order_status,
            "reason": r.reason,
        }
        for r in log
    ]
    path = output_dir / "paper_execution_log.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"[OUTPUT] {path}")


def _print_paper_execute_summary(log: list[PaperOrderRecord]) -> None:
    executed = [r for r in log if r.executed]
    declined = [r for r in log if r.proposed and not r.executed]
    skipped = [r for r in log if not r.proposed]
    print(f"\n{'=' * 68}")
    print("PAPER-EXECUTE SUMMARY")
    print(f"{'=' * 68}")
    print(f"  Orders sent    : {len(executed)}")
    print(f"  User declined  : {len(declined)}")
    print(f"  Not actionable : {len(skipped)}")
    if executed:
        print("\n  Executed orders:")
        for r in executed:
            print(f"    {r.action} {r.quantity:.0f} {r.symbol}  orderId={r.order_id}  status={r.order_status}")
    print(f"{'=' * 68}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()
    if args.paper_execute:
        return _run_paper_execute(args)
    return _run_dry_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
