"""
FULL STACK AUDIT — LSEG real option data + IBKR paper trading + delta hedge recommendation.

Purpose
-------
This script verifies, in one run:
1. LSEG session works.
2. LSEG underlying history works for SPY / QQQ / TLT / GLD.
3. LSEG real option RIC snapshot works.
4. LSEG real option bid/ask, IV and Greeks are accessible.
5. LSEG short option history works.
6. IBKR paper trading connection works.
7. IBKR stock contracts and option chains work.
8. A safe delta hedge recommendation can be produced.

Important
---------
- This script DOES NOT place orders.
- This script DOES NOT enable live trading.
- This script is an audit + recommendation layer only.
- IBKR must be open in Paper Trading on port 7497.
- LSEG Workspace must be open and logged in.

Run
---
python scripts/full_stack_lseg_ibkr_delta_hedge_audit.py

Optional
--------
python scripts/full_stack_lseg_ibkr_delta_hedge_audit.py --option-rics SPYD292650000.U SPYP292650000.U
python scripts/full_stack_lseg_ibkr_delta_hedge_audit.py --history-count 30
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# =============================================================================
# USER CONFIG — EDIT HERE IF NEEDED
# =============================================================================

DEFAULT_OPTION_RICS = [
    # Confirmed from your LSEG Workspace + Python test:
    "SPYD292650000.U",

    # Candidate put from the same visible SPY chain.
    # If it fails, the script will just mark it as limited/error.
    "SPYP292650000.U",
]

# This is the option book used for the hedge recommendation.
# Quantity = number of option contracts.
# multiplier = 100 shares per listed US equity option contract.
DEFAULT_OPTION_BOOK = [
    {
        "ric": "SPYD292650000.U",
        "underlying": "SPY",
        "quantity": 1.0,
        "multiplier": 100,
    },
    # Add more after copying exact RICs from Workspace:
    # {"ric": "SPYP292650000.U", "underlying": "SPY", "quantity": 1.0, "multiplier": 100},
]

UNDERLYINGS = {
    "SPY": {"lseg_ric": "SPY", "ibkr_symbol": "SPY", "currency": "USD"},
    "QQQ": {"lseg_ric": "QQQ.O", "ibkr_symbol": "QQQ", "currency": "USD"},
    "TLT": {"lseg_ric": "TLT.O", "ibkr_symbol": "TLT", "currency": "USD"},
    "GLD": {"lseg_ric": "GLD", "ibkr_symbol": "GLD", "currency": "USD"},
}

LSEG_UNDERLYING_FIELDS = [
    "TRDPRC_1",
    "BID",
    "ASK",
    "TR.PriceClose",
]

LSEG_OPTION_FIELDS = [
    "BID",
    "ASK",
    "TRDPRC_1",
    "CF_LAST",
    "CF_BID",
    "CF_ASK",
    "CF_CLOSE",
    "TR.PriceClose",
    "TR.BIDPRICE",
    "TR.ASKPRICE",
    "TR.ImpliedVolatility",
    "TR.Delta",
    "TR.Gamma",
    "TR.Vega",
    "TR.Theta",
    "TR.Rho",
    "TR.OPWCloseDelta",
    "TR.OPWCloseGamma",
    "TR.OPWCloseVega",
    "TR.OPWCloseTheta",
    "TR.OPWCloseRho",
    "TR.EXCHANGEPROVIDEDIMPLIEDVOLATILITY",
]

LSEG_OPTION_HISTORY_FIELDS = [
    "BID",
    "ASK",
    "TR.BIDPRICE",
    "TR.ASKPRICE",
    "TR.ImpliedVolatility",
    "TR.Delta",
    "TR.Gamma",
    "TR.Vega",
    "TR.Theta",
    "TR.Rho",
]

HEDGE_RULES = {
    "delta_threshold_shares": 1.0,
    "max_order_notional_usd": 25_000.0,
    "cost_bps": 1.0,
    "paper_trading_only": True,
    "allow_live_trading": False,
    "oversized_order_policy": "block",  # block for paper/daily safety
}

CURRENT_HEDGE_POSITIONS = {
    "SPY": 0.0,
    "QQQ": 0.0,
    "TLT": 0.0,
    "GLD": 0.0,
}


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class FieldResult:
    source: str
    instrument: str
    field: str
    status: str
    rows: int
    non_null: int
    value: Any
    first_date: str = ""
    last_date: str = ""
    error: str = ""


@dataclass
class HedgeRecommendation:
    underlying: str
    net_option_delta_shares: float
    current_hedge_shares: float
    target_hedge_shares: float
    raw_order_shares: float
    final_order_shares: float
    side: str
    spot: float | None
    raw_notional: float | None
    final_notional: float | None
    estimated_cost: float | None
    blocked: bool
    reason: str


# =============================================================================
# BASIC HELPERS
# =============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_str(x: Any, limit: int = 500) -> str:
    try:
        s = str(x)
    except Exception:
        s = repr(x)
    return s.replace("\n", " ").replace("\r", " ")[:limit]


def clean_number(x: Any) -> float | None:
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass

    if isinstance(x, str):
        x = x.strip().replace(",", "")
        if x in {"", "<NA>", "NA", "N/A", "None", "nan"}:
            return None

    try:
        out = float(x)
    except Exception:
        return None

    if not math.isfinite(out):
        return None
    return out


def normalize_iv(x: float | None) -> float | None:
    """
    Normalize LSEG IV into decimal volatility.

    Example:
    217.1047 from LSEG means 217.1047%, so store 2.171047.
    """
    if x is None:
        return None
    if x > 3.0:
        return x / 100.0
    return x


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            " | ".join(str(v) for v in col if str(v) not in {"", "None"})
            for col in out.columns
        ]
    else:
        out.columns = [str(c) for c in out.columns]
    return out


def first_non_null_value(df: pd.DataFrame) -> Any:
    if df is None or df.empty:
        return None
    flat = flatten_columns(df)

    skip_cols = {"Instrument", "Date", "DATE", "RIC"}
    for col in flat.columns:
        if str(col) in skip_cols:
            continue
        series = flat[col].dropna()
        if not series.empty:
            return series.iloc[-1]

    for col in flat.columns:
        series = flat[col].dropna()
        if not series.empty:
            return series.iloc[-1]

    return None


def date_range_from_df(df: pd.DataFrame) -> tuple[str, str]:
    if df is None or df.empty:
        return "", ""
    try:
        idx = pd.to_datetime(df.index, errors="coerce")
        idx = idx[~pd.isna(idx)]
        if len(idx) == 0:
            return "", ""
        return str(idx.min().date()), str(idx.max().date())
    except Exception:
        return "", ""


def count_non_null_values(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    flat = flatten_columns(df)
    return int(flat.notna().sum().sum())


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def save_csv(path: Path, rows: list[dict[str, Any]] | pd.DataFrame) -> None:
    df = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    df.to_csv(path, index=False)


# =============================================================================
# LSEG HELPERS
# =============================================================================

def import_lseg() -> Any:
    try:
        import lseg.data as ld
    except Exception as exc:
        raise ImportError(
            "Could not import lseg.data. Try: python -m pip install lseg-data"
        ) from exc
    return ld


def lseg_open(ld: Any) -> bool:
    try:
        ld.open_session()
        return True
    except Exception as exc:
        print(f"LSEG open_session warning/error: {safe_str(exc)}")
        return False


def lseg_close(ld: Any) -> None:
    try:
        ld.close_session()
    except Exception:
        pass


def lseg_get_data_one_field(ld: Any, ric: str, field: str) -> FieldResult:
    try:
        raw = ld.get_data(universe=[ric], fields=[field])
        if isinstance(raw, tuple):
            raw = raw[0]
        if not isinstance(raw, pd.DataFrame):
            return FieldResult("LSEG_GET_DATA", ric, field, "ERROR", 0, 0, None, error=f"Non-DataFrame: {type(raw)}")

        status = "OK" if not raw.empty else "EMPTY"
        value = first_non_null_value(raw)
        non_null = 0 if raw.empty else count_non_null_values(raw)
        return FieldResult("LSEG_GET_DATA", ric, field, status, len(raw), non_null, value)

    except Exception as exc:
        return FieldResult("LSEG_GET_DATA", ric, field, "ERROR", 0, 0, None, error=safe_str(exc))


def lseg_get_history_one_field(ld: Any, ric: str, field: str, count: int) -> FieldResult:
    try:
        raw = ld.get_history(
            universe=[ric],
            fields=[field],
            interval="daily",
            count=count,
        )
        if not isinstance(raw, pd.DataFrame):
            return FieldResult("LSEG_GET_HISTORY", ric, field, "ERROR", 0, 0, None, error=f"Non-DataFrame: {type(raw)}")

        status = "OK" if not raw.empty else "EMPTY"
        value = first_non_null_value(raw)
        first_date, last_date = date_range_from_df(raw)
        non_null = 0 if raw.empty else count_non_null_values(raw)

        return FieldResult(
            "LSEG_GET_HISTORY",
            ric,
            field,
            status,
            len(raw),
            non_null,
            value,
            first_date=first_date,
            last_date=last_date,
        )

    except Exception as exc:
        return FieldResult("LSEG_GET_HISTORY", ric, field, "ERROR", 0, 0, None, error=safe_str(exc))


def audit_lseg_underlyings(ld: Any, out_dir: Path, history_count: int) -> tuple[pd.DataFrame, dict[str, float]]:
    print("\n" + "=" * 90)
    print("LSEG UNDERLYING AUDIT")
    print("=" * 90)

    rows: list[dict[str, Any]] = []
    latest_spots: dict[str, float] = {}

    for symbol, meta in UNDERLYINGS.items():
        ric = meta["lseg_ric"]
        print(f"\n--- {symbol} / {ric} ---")

        for field in LSEG_UNDERLYING_FIELDS:
            res = lseg_get_history_one_field(ld, ric, field, history_count)
            rows.append(asdict(res))
            print(f"{ric:10s} {field:18s} -> {res.status:5s} rows={res.rows} value={res.value}")

            value = clean_number(res.value)
            if value is not None and symbol not in latest_spots:
                latest_spots[symbol] = value

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "lseg_underlying_history_audit.csv", index=False)
    return df, latest_spots


def audit_lseg_option_snapshots(ld: Any, option_rics: list[str], out_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    print("\n" + "=" * 90)
    print("LSEG REAL OPTION SNAPSHOT AUDIT")
    print("=" * 90)

    field_rows: list[dict[str, Any]] = []
    normalized_rows: list[dict[str, Any]] = []

    for ric in option_rics:
        print(f"\n--- OPTION RIC {ric} ---")
        values: dict[str, Any] = {}

        for field in LSEG_OPTION_FIELDS:
            res = lseg_get_data_one_field(ld, ric, field)
            field_rows.append(asdict(res))
            values[field] = res.value

            compact_value = safe_str(res.value, 80)
            print(f"{field:42s} -> {res.status:5s} value={compact_value}")

        bid = clean_number(values.get("BID")) or clean_number(values.get("CF_BID")) or clean_number(values.get("TR.BIDPRICE"))
        ask = clean_number(values.get("ASK")) or clean_number(values.get("CF_ASK")) or clean_number(values.get("TR.ASKPRICE"))
        last = clean_number(values.get("CF_LAST")) or clean_number(values.get("TRDPRC_1"))
        close = clean_number(values.get("CF_CLOSE")) or clean_number(values.get("TR.PriceClose"))

        iv_raw = (
            clean_number(values.get("TR.ImpliedVolatility"))
            or clean_number(values.get("TR.EXCHANGEPROVIDEDIMPLIEDVOLATILITY"))
        )
        iv = normalize_iv(iv_raw)

        delta = clean_number(values.get("TR.Delta")) or clean_number(values.get("TR.OPWCloseDelta"))
        gamma = clean_number(values.get("TR.Gamma")) or clean_number(values.get("TR.OPWCloseGamma"))
        vega = clean_number(values.get("TR.Vega")) or clean_number(values.get("TR.OPWCloseVega"))
        theta = clean_number(values.get("TR.Theta")) or clean_number(values.get("TR.OPWCloseTheta"))
        rho = clean_number(values.get("TR.Rho")) or clean_number(values.get("TR.OPWCloseRho"))

        warnings: list[str] = []
        if iv_raw is not None and iv is not None and iv_raw != iv:
            warnings.append("iv_percent_normalized")
        if bid is None:
            warnings.append("missing_bid")
        if ask is None:
            warnings.append("missing_ask")
        if delta is None:
            warnings.append("missing_delta")
        if gamma is None:
            warnings.append("missing_gamma")
        if vega is None:
            warnings.append("missing_vega")
        if theta is None:
            warnings.append("missing_theta")

        mid = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
        elif close is not None:
            mid = close
            warnings.append("mid_from_close")
        elif last is not None:
            mid = last
            warnings.append("mid_from_last")
        else:
            warnings.append("missing_price_proxy")

        normalized_rows.append(
            {
                "ric": ric,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": last,
                "close": close,
                "implied_volatility_raw": iv_raw,
                "implied_volatility_decimal": iv,
                "delta": delta,
                "gamma": gamma,
                "vega": vega,
                "theta": theta,
                "rho": rho,
                "timestamp_utc": utc_now(),
                "warnings": "|".join(warnings),
            }
        )

    field_df = pd.DataFrame(field_rows)
    normalized_df = pd.DataFrame(normalized_rows)

    field_df.to_csv(out_dir / "lseg_option_snapshot_field_audit.csv", index=False)
    normalized_df.to_csv(out_dir / "lseg_option_snapshot_normalized.csv", index=False)

    return field_df, normalized_df


def audit_lseg_option_history(ld: Any, option_rics: list[str], out_dir: Path, history_count: int) -> pd.DataFrame:
    print("\n" + "=" * 90)
    print("LSEG REAL OPTION HISTORY AUDIT")
    print("=" * 90)

    rows: list[dict[str, Any]] = []

    for ric in option_rics:
        print(f"\n--- OPTION HISTORY {ric} ---")
        for field in LSEG_OPTION_HISTORY_FIELDS:
            res = lseg_get_history_one_field(ld, ric, field, history_count)
            rows.append(asdict(res))
            print(
                f"{field:28s} -> {res.status:5s} "
                f"rows={res.rows:3d} non_null={res.non_null:3d} "
                f"date={res.first_date}->{res.last_date} value={safe_str(res.value, 80)}"
            )

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "lseg_option_history_field_audit.csv", index=False)
    return df


# =============================================================================
# IBKR HELPERS
# =============================================================================

def import_ib_insync() -> Any:
    try:
        import ib_insync
    except Exception as exc:
        raise ImportError(
            "Could not import ib_insync. Try: python -m pip install ib_insync"
        ) from exc
    return ib_insync


def audit_ibkr(out_dir: Path, client_id: int) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float], bool]:
    print("\n" + "=" * 90)
    print("IBKR PAPER TRADING AUDIT")
    print("=" * 90)

    rows: list[dict[str, Any]] = []
    chain_rows: list[dict[str, Any]] = []
    spot_rows: list[dict[str, Any]] = []
    ibkr_spots: dict[str, float] = {}
    connected = False

    try:
        ibm = import_ib_insync()
        IB = ibm.IB
        Stock = ibm.Stock

        ib = IB()
        print("Connecting to IBKR Paper Trading on 127.0.0.1:7497 ...")
        ib.connect("127.0.0.1", 7497, clientId=client_id, timeout=10)
        connected = bool(ib.isConnected())

        accounts = ib.managedAccounts()
        print("Connected:", connected)
        print("Accounts:", accounts)

        rows.append(
            {
                "component": "connection",
                "status": "OK" if connected else "ERROR",
                "accounts": "|".join(accounts),
                "error": "",
            }
        )

        # Delayed market data to avoid subscription issue.
        try:
            ib.reqMarketDataType(3)
        except Exception:
            pass

        for symbol, meta in UNDERLYINGS.items():
            contract = Stock(meta["ibkr_symbol"], "SMART", meta["currency"])
            details = ib.reqContractDetails(contract)

            rows.append(
                {
                    "component": "contract_details",
                    "symbol": symbol,
                    "status": "OK" if details else "EMPTY",
                    "count": len(details),
                    "conId": details[0].contract.conId if details else "",
                    "primaryExchange": details[0].contract.primaryExchange if details else "",
                    "error": "",
                }
            )

            print(f"{symbol}: contract details = {len(details)}")

            if not details:
                continue

            qualified = details[0].contract

            # Spot quote
            try:
                ticker = ib.reqMktData(qualified, "", False, False)
                ib.sleep(2)
                candidates = [
                    clean_number(getattr(ticker, "marketPrice", lambda: None)()),
                    clean_number(ticker.last),
                    clean_number(ticker.close),
                    clean_number(ticker.bid),
                    clean_number(ticker.ask),
                ]
                spot = next((x for x in candidates if x is not None and x > 0), None)
                ib.cancelMktData(qualified)
                if spot is not None:
                    ibkr_spots[symbol] = spot

                spot_rows.append(
                    {
                        "symbol": symbol,
                        "status": "OK" if spot is not None else "EMPTY",
                        "spot": spot,
                        "bid": clean_number(ticker.bid),
                        "ask": clean_number(ticker.ask),
                        "last": clean_number(ticker.last),
                        "close": clean_number(ticker.close),
                    }
                )
                print(f"{symbol}: delayed spot = {spot}")

            except Exception as exc:
                spot_rows.append(
                    {
                        "symbol": symbol,
                        "status": "ERROR",
                        "spot": None,
                        "error": safe_str(exc),
                    }
                )
                print(f"{symbol}: delayed spot error = {safe_str(exc)}")

            # Option chain
            try:
                chains = ib.reqSecDefOptParams(
                    qualified.symbol,
                    "",
                    qualified.secType,
                    qualified.conId,
                )
                if chains:
                    best = chains[0]
                    chain_rows.append(
                        {
                            "symbol": symbol,
                            "status": "OK",
                            "exchange": best.exchange,
                            "tradingClass": best.tradingClass,
                            "multiplier": best.multiplier,
                            "num_expirations": len(best.expirations),
                            "first_expirations": "|".join(sorted(best.expirations)[:5]),
                            "num_strikes": len(best.strikes),
                            "min_strike": min(best.strikes) if best.strikes else None,
                            "max_strike": max(best.strikes) if best.strikes else None,
                            "error": "",
                        }
                    )
                    print(
                        f"{symbol}: option chain OK "
                        f"expiries={len(best.expirations)} strikes={len(best.strikes)}"
                    )
                else:
                    chain_rows.append({"symbol": symbol, "status": "EMPTY", "error": ""})
                    print(f"{symbol}: option chain EMPTY")

            except Exception as exc:
                chain_rows.append({"symbol": symbol, "status": "ERROR", "error": safe_str(exc)})
                print(f"{symbol}: option chain error = {safe_str(exc)}")

        ib.disconnect()

    except Exception as exc:
        rows.append(
            {
                "component": "connection",
                "status": "ERROR",
                "accounts": "",
                "error": safe_str(exc, 1000),
            }
        )
        print("IBKR audit failed:", safe_str(exc, 1000))

    connection_df = pd.DataFrame(rows)
    chains_df = pd.DataFrame(chain_rows)
    spots_df = pd.DataFrame(spot_rows)

    connection_df.to_csv(out_dir / "ibkr_connection_and_contracts.csv", index=False)
    chains_df.to_csv(out_dir / "ibkr_option_chains.csv", index=False)
    spots_df.to_csv(out_dir / "ibkr_delayed_spots.csv", index=False)

    return connection_df, chains_df, ibkr_spots, connected


# =============================================================================
# HEDGE RECOMMENDATION
# =============================================================================

def build_hedge_recommendations(
    option_snapshot: pd.DataFrame,
    lseg_spots: dict[str, float],
    ibkr_spots: dict[str, float],
    out_dir: Path,
) -> pd.DataFrame:
    print("\n" + "=" * 90)
    print("SAFE DELTA HEDGE RECOMMENDATION — NO ORDERS SENT")
    print("=" * 90)

    book_df = pd.DataFrame(DEFAULT_OPTION_BOOK)
    if book_df.empty:
        raise ValueError("DEFAULT_OPTION_BOOK is empty.")

    merged = book_df.merge(option_snapshot, on="ric", how="left")
    merged["position_delta_shares"] = merged["quantity"] * merged["multiplier"] * merged["delta"]

    exposure = (
        merged.groupby("underlying", dropna=False)
        .agg(
            net_option_delta_shares=("position_delta_shares", "sum"),
            number_of_positions=("ric", "count"),
        )
        .reset_index()
    )

    exposure.to_csv(out_dir / "portfolio_delta_exposure_from_lseg_options.csv", index=False)

    recs: list[HedgeRecommendation] = []

    for _, row in exposure.iterrows():
        underlying = str(row["underlying"])
        net_delta = clean_number(row["net_option_delta_shares"]) or 0.0
        current_hedge = CURRENT_HEDGE_POSITIONS.get(underlying, 0.0)
        target_hedge = -net_delta
        raw_order = target_hedge - current_hedge

        spot = lseg_spots.get(underlying) or ibkr_spots.get(underlying)
        raw_notional = abs(raw_order * spot) if spot is not None else None

        blocked = False
        final_order = raw_order
        reason = "threshold_triggered"

        if abs(raw_order) < HEDGE_RULES["delta_threshold_shares"]:
            final_order = 0.0
            reason = "below_delta_threshold"

        if raw_notional is not None and raw_notional > HEDGE_RULES["max_order_notional_usd"]:
            if HEDGE_RULES["oversized_order_policy"] == "block":
                blocked = True
                final_order = 0.0
                reason = "blocked_max_notional_for_paper_safety"

        if final_order > 0:
            side = "BUY"
        elif final_order < 0:
            side = "SELL"
        else:
            side = "HOLD"

        final_notional = abs(final_order * spot) if spot is not None else None
        estimated_cost = (
            final_notional * HEDGE_RULES["cost_bps"] / 10000.0
            if final_notional is not None
            else None
        )

        rec = HedgeRecommendation(
            underlying=underlying,
            net_option_delta_shares=net_delta,
            current_hedge_shares=current_hedge,
            target_hedge_shares=target_hedge,
            raw_order_shares=raw_order,
            final_order_shares=final_order,
            side=side,
            spot=spot,
            raw_notional=raw_notional,
            final_notional=final_notional,
            estimated_cost=estimated_cost,
            blocked=blocked,
            reason=reason,
        )
        recs.append(rec)

        print(
            f"{underlying}: net_delta={net_delta:.4f}, "
            f"target_hedge={target_hedge:.4f}, "
            f"raw_order={raw_order:.4f}, side={side}, "
            f"blocked={blocked}, reason={reason}"
        )

    rec_df = pd.DataFrame([asdict(x) for x in recs])
    rec_df.to_csv(out_dir / "safe_delta_hedge_recommendations.csv", index=False)
    merged.to_csv(out_dir / "option_book_with_lseg_greeks.csv", index=False)

    return rec_df


# =============================================================================
# VERDICT + SUMMARY
# =============================================================================

def build_verdict(
    ibkr_connected: bool,
    ibkr_chains: pd.DataFrame,
    option_snapshot: pd.DataFrame,
    option_history: pd.DataFrame,
) -> dict[str, Any]:
    snapshot_price = bool(
        option_snapshot["bid"].notna().any()
        and option_snapshot["ask"].notna().any()
    )
    snapshot_greeks = bool(
        option_snapshot[["delta", "gamma", "vega", "theta"]].notna().any().all()
    )
    snapshot_iv = bool(option_snapshot["implied_volatility_decimal"].notna().any())

    hist_bid = option_history[
        (option_history["field"].isin(["BID", "TR.BIDPRICE"]))
        & (option_history["status"].eq("OK"))
        & (option_history["rows"] > 0)
    ]
    hist_ask = option_history[
        (option_history["field"].isin(["ASK", "TR.ASKPRICE"]))
        & (option_history["status"].eq("OK"))
        & (option_history["rows"] > 0)
    ]
    hist_greeks = option_history[
        (option_history["field"].isin(["TR.Delta", "TR.Gamma", "TR.Vega", "TR.Theta", "TR.Rho"]))
        & (option_history["status"].eq("OK"))
        & (option_history["rows"] > 0)
    ]

    history_bidask_confirmed = bool(not hist_bid.empty and not hist_ask.empty)
    history_greeks_confirmed = bool(not hist_greeks.empty)

    ibkr_chains_ok = bool(
        not ibkr_chains.empty
        and ibkr_chains["status"].eq("OK").any()
    )

    daily_ready = bool(
        ibkr_connected
        and ibkr_chains_ok
        and snapshot_price
        and snapshot_greeks
        and snapshot_iv
    )

    long_history_confirmed = bool(
        history_bidask_confirmed
        and option_history["rows"].max() >= 20
    )

    if daily_ready and long_history_confirmed:
        final = "REAL_LSEG_OPTION_DAILY_ENGINE_READY_AND_LONG_HISTORY_PARTIAL"
    elif daily_ready:
        final = "REAL_LSEG_OPTION_DAILY_HEDGE_ENGINE_READY_HISTORY_SHORT"
    elif snapshot_price and snapshot_greeks:
        final = "LSEG_OPTION_SNAPSHOT_CONFIRMED_IBKR_OR_CHAIN_LIMITED"
    else:
        final = "AUDIT_INCOMPLETE_CHECK_LSEG_OR_IBKR"

    return {
        "final_verdict": final,
        "ibkr_connected": ibkr_connected,
        "ibkr_option_chains_confirmed": ibkr_chains_ok,
        "lseg_snapshot_bidask_confirmed": snapshot_price,
        "lseg_snapshot_iv_confirmed": snapshot_iv,
        "lseg_snapshot_greeks_confirmed": snapshot_greeks,
        "lseg_history_bidask_confirmed": history_bidask_confirmed,
        "lseg_history_greeks_confirmed": history_greeks_confirmed,
        "long_history_confirmed": long_history_confirmed,
        "safe_to_place_orders": False,
        "paper_trading_only": True,
        "allow_live_trading": False,
        "interpretation": (
            "Use this project first as a real LSEG option snapshot + Greeks daily hedge engine "
            "with IBKR paper hedge recommendations. Do not claim a long historical listed-options "
            "backtest until long history across many RICs/expiries is confirmed."
        ),
    }


def write_markdown_summary(out_dir: Path, manifest: dict[str, Any]) -> None:
    text = f"""# Full Stack LSEG + IBKR Delta Hedge Audit

Generated: `{utc_now()}`

## Final verdict

**{manifest["final_verdict"]}**

## Confirmed flags

- IBKR connected: `{manifest["ibkr_connected"]}`
- IBKR option chains confirmed: `{manifest["ibkr_option_chains_confirmed"]}`
- LSEG option snapshot bid/ask confirmed: `{manifest["lseg_snapshot_bidask_confirmed"]}`
- LSEG option snapshot IV confirmed: `{manifest["lseg_snapshot_iv_confirmed"]}`
- LSEG option snapshot Greeks confirmed: `{manifest["lseg_snapshot_greeks_confirmed"]}`
- LSEG option history bid/ask confirmed: `{manifest["lseg_history_bidask_confirmed"]}`
- LSEG option history Greeks confirmed: `{manifest["lseg_history_greeks_confirmed"]}`
- Long historical option backtest confirmed: `{manifest["long_history_confirmed"]}`

## Safety

- Orders sent: `False`
- Paper trading only: `True`
- Live trading allowed: `False`

## Interpretation

{manifest["interpretation"]}

## Output files

- `lseg_underlying_history_audit.csv`
- `lseg_option_snapshot_field_audit.csv`
- `lseg_option_snapshot_normalized.csv`
- `lseg_option_history_field_audit.csv`
- `ibkr_connection_and_contracts.csv`
- `ibkr_option_chains.csv`
- `ibkr_delayed_spots.csv`
- `option_book_with_lseg_greeks.csv`
- `portfolio_delta_exposure_from_lseg_options.csv`
- `safe_delta_hedge_recommendations.csv`
- `manifest.json`

"""
    (out_dir / "readable_summary.md").write_text(text, encoding="utf-8")


# =============================================================================
# MAIN
# =============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--option-rics", nargs="+", default=DEFAULT_OPTION_RICS)
    parser.add_argument("--history-count", type=int, default=20)
    parser.add_argument("--ibkr-client-id", type=int, default=91)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path("outputs/audits") / f"full_stack_lseg_ibkr_delta_hedge_{timestamp()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 90)
    print("FULL STACK LSEG + IBKR DELTA HEDGE AUDIT")
    print("=" * 90)
    print(f"Output directory: {out_dir}")
    print(f"Option RICs: {args.option_rics}")
    print("NO ORDERS WILL BE SENT.")
    print("=" * 90)

    errors: list[dict[str, str]] = []

    # 1) LSEG
    ld = None
    lseg_opened = False
    lseg_spots: dict[str, float] = {}
    option_snapshot_norm = pd.DataFrame()
    option_history = pd.DataFrame()

    try:
        ld = import_lseg()
        lseg_opened = lseg_open(ld)

        lseg_underlying_df, lseg_spots = audit_lseg_underlyings(ld, out_dir, args.history_count)
        option_snapshot_fields, option_snapshot_norm = audit_lseg_option_snapshots(ld, args.option_rics, out_dir)
        option_history = audit_lseg_option_history(ld, args.option_rics, out_dir, args.history_count)

    except Exception as exc:
        errors.append({"component": "LSEG", "error": safe_str(exc, 2000), "traceback": traceback.format_exc()})
        print("LSEG audit failed:", safe_str(exc, 1000))

    finally:
        if ld is not None:
            lseg_close(ld)

    # 2) IBKR
    ibkr_connected = False
    ibkr_chains = pd.DataFrame()
    ibkr_spots: dict[str, float] = {}

    try:
        ibkr_conn, ibkr_chains, ibkr_spots, ibkr_connected = audit_ibkr(out_dir, args.ibkr_client_id)

    except Exception as exc:
        errors.append({"component": "IBKR", "error": safe_str(exc, 2000), "traceback": traceback.format_exc()})
        print("IBKR audit failed:", safe_str(exc, 1000))

    # 3) Hedge recommendations
    hedge_df = pd.DataFrame()

    try:
        if not option_snapshot_norm.empty:
            hedge_df = build_hedge_recommendations(option_snapshot_norm, lseg_spots, ibkr_spots, out_dir)
        else:
            print("Skipping hedge recommendation: no normalized LSEG option snapshot.")
    except Exception as exc:
        errors.append({"component": "HEDGE_RECOMMENDATION", "error": safe_str(exc, 2000), "traceback": traceback.format_exc()})
        print("Hedge recommendation failed:", safe_str(exc, 1000))

    # 4) Verdict
    try:
        manifest = build_verdict(
            ibkr_connected=ibkr_connected,
            ibkr_chains=ibkr_chains,
            option_snapshot=option_snapshot_norm,
            option_history=option_history,
        )
    except Exception as exc:
        manifest = {
            "final_verdict": "AUDIT_FAILED_DURING_VERDICT",
            "error": safe_str(exc, 2000),
            "safe_to_place_orders": False,
            "paper_trading_only": True,
            "allow_live_trading": False,
        }

    manifest["output_dir"] = str(out_dir)
    manifest["errors"] = errors

    write_json(out_dir / "manifest.json", manifest)
    write_json(out_dir / "errors.json", errors)
    write_markdown_summary(out_dir, manifest)

    print("\n" + "=" * 90)
    print("FINAL VERDICT")
    print("=" * 90)
    print(manifest["final_verdict"])
    print(manifest.get("interpretation", ""))
    print(f"\nSaved all outputs to: {out_dir}")
    print("=" * 90)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
