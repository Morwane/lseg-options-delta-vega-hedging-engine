"""Load historical LSEG option bid/ask data for the confirmed SPY option RIC universe.

Strike decoding:
    RIC format: SPYA1527{5-digit-cents}.U
    Example: SPYA152705000.U  → int('05000') / 100 = $50.00 strike
             SPYA152762500.U  → int('62500') / 100 = $625.00 strike

Data coverage (from audit 2026-04-29):
    - 120 SPY call RICs confirmed, Jan 2027 expiry
    - 30 rows of BID/ASK history per RIC (2026-03-18 to 2026-04-29)
    - Historical Greeks: only 1 row each — Greeks are recomputed daily via BS IV bisection
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


# ---------------------------------------------------------------------------
# RIC decoding
# ---------------------------------------------------------------------------

def decode_strike_from_ric(ric: str) -> float | None:
    """Decode strike price from a LSEG SPY option RIC.

    Matches the 5-digit numeric suffix immediately before '.U'.
    Returns strike in USD (e.g. '05000' → 50.00, '62500' → 625.00).
    Returns None if the pattern is not found.
    """
    m = re.search(r"(\d{5})\.U$", ric)
    if m is None:
        return None
    return int(m.group(1)) / 100.0


# ---------------------------------------------------------------------------
# Universe loading
# ---------------------------------------------------------------------------

def load_ric_universe(config_path: Path) -> list[str]:
    """Load confirmed RIC list from a YAML file with a 'rics' key."""
    raw = yaml.safe_load(config_path.read_text())
    return [str(r) for r in raw.get("rics", [])]


# ---------------------------------------------------------------------------
# LSEG DataFrame helpers
# ---------------------------------------------------------------------------

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse MultiIndex columns to flat strings (LSEG sometimes returns these)."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [
            " | ".join(str(v) for v in c if str(v) not in {"", "None"})
            for c in df.columns
        ]
    return df


def _extract_numeric_series(df: pd.DataFrame, field: str) -> pd.Series:
    """Find the column whose name contains *field* (case-insensitive) and coerce to float."""
    df = _flatten_columns(df)
    for col in df.columns:
        if field.upper() in col.upper():
            return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# Live LSEG loading
# ---------------------------------------------------------------------------

def load_option_history_lseg(
    rics: list[str],
    count: int = 35,
) -> pd.DataFrame:
    """Fetch bid/ask daily history for *rics* from LSEG.

    Calls get_history per RIC with fields=["BID", "ASK"].
    Silently skips RICs that return no usable data.

    Returns:
        DataFrame with columns: date (datetime.date), ric, bid, ask
    Raises:
        ImportError   — lseg.data not installed
        RuntimeError  — LSEG returned no data for any RIC
    """
    import lseg.data as ld  # type: ignore[import]

    rows: list[dict[str, Any]] = []

    for ric in rics:
        try:
            df = ld.get_history(
                universe=[ric],
                fields=["BID", "ASK"],
                interval="daily",
                count=count,
            )
            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                continue

            bid_s = _extract_numeric_series(df, "BID")
            ask_s = _extract_numeric_series(df, "ASK")

            all_dates = bid_s.index.union(ask_s.index)
            bid_s = bid_s.reindex(all_dates)
            ask_s = ask_s.reindex(all_dates)

            for dt in all_dates:
                rows.append(
                    {
                        "date": pd.to_datetime(dt).date(),
                        "ric": ric,
                        "bid": bid_s.get(dt),
                        "ask": ask_s.get(dt),
                    }
                )
        except Exception:
            continue

    if not rows:
        raise RuntimeError(
            "LSEG returned no option history for any RIC. "
            "Check that LSEG Workspace is open and the session is active."
        )

    df_out = pd.DataFrame(rows)
    df_out["bid"] = pd.to_numeric(df_out["bid"], errors="coerce")
    df_out["ask"] = pd.to_numeric(df_out["ask"], errors="coerce")
    return df_out


def load_spy_history_lseg(count: int = 35) -> pd.DataFrame:
    """Fetch SPY daily close prices from LSEG.

    Returns:
        DataFrame with columns: date (datetime.date), spot
    Raises:
        ImportError   — lseg.data not installed
        RuntimeError  — LSEG returned no usable SPY data
    """
    import lseg.data as ld  # type: ignore[import]

    df = ld.get_history(
        universe=["SPY"],
        fields=["TRDPRC_1", "TR.PriceClose"],
        interval="daily",
        count=count,
    )
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        raise RuntimeError("LSEG returned no SPY history.")

    # Try TRDPRC_1 first; fall back to TR.PriceClose
    spot_s = _extract_numeric_series(df, "TRDPRC_1")
    if spot_s.dropna().empty:
        spot_s = _extract_numeric_series(df, "TR.PriceClose")
    if spot_s.dropna().empty:
        raise RuntimeError("LSEG returned no usable SPY close prices.")

    result = pd.DataFrame(
        {
            "date": [pd.to_datetime(d).date() for d in spot_s.index],
            "spot": spot_s.values,
        }
    ).dropna()
    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Mock data for offline testing / CI
# ---------------------------------------------------------------------------

_MOCK_EXPIRY = date(2027, 1, 15)
_MOCK_RFR = 0.05
_MOCK_DVY = 0.013
_MOCK_IV_BASE = 0.20
_MOCK_SPY_SPOT_0 = 700.0
_MOCK_TRADING_DAYS = 30
_MOCK_START = date(2026, 3, 18)


def _mock_trading_dates() -> list[date]:
    dates: list[date] = []
    d = _MOCK_START
    while len(dates) < _MOCK_TRADING_DAYS:
        if d.weekday() < 5:
            dates.append(d)
        d += timedelta(days=1)
    return dates


def load_spy_history_mock() -> pd.DataFrame:
    """Synthetic SPY daily prices seeded for reproducibility."""
    dates = _mock_trading_dates()
    rng = np.random.default_rng(42)
    daily_rets = rng.normal(0.0, 0.01, size=len(dates))
    spots = _MOCK_SPY_SPOT_0 * np.cumprod(1.0 + daily_rets)
    return pd.DataFrame({"date": dates, "spot": np.round(spots, 2)})


def load_option_history_mock(rics: list[str]) -> pd.DataFrame:
    """Synthetic bid/ask history derived from Black-Scholes for offline testing.

    Uses IV=0.20 for all strikes. Adds small random noise and a 0.3% bid/ask spread.
    Deep-ITM calls near $50 strike correctly produce mids near intrinsic value.
    """
    from src.pricing.black_scholes import BlackScholesInputs, black_scholes_price

    spy_df = load_spy_history_mock()
    spot_by_date: dict[date, float] = dict(zip(spy_df["date"], spy_df["spot"]))
    dates = sorted(spot_by_date.keys())

    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(99)

    for ric in rics:
        strike = decode_strike_from_ric(ric)
        if strike is None:
            continue

        for d in dates:
            spot = spot_by_date[d]
            tte = (_MOCK_EXPIRY - d).days / 365.0
            if tte <= 0:
                continue

            try:
                bs_mid = black_scholes_price(
                    BlackScholesInputs(
                        spot=spot,
                        strike=strike,
                        time_to_expiry=tte,
                        risk_free_rate=_MOCK_RFR,
                        volatility=_MOCK_IV_BASE,
                        option_type="call",
                        dividend_yield=_MOCK_DVY,
                    )
                )
            except Exception:
                continue

            if not math.isfinite(bs_mid) or bs_mid <= 0:
                continue

            spread = max(0.50, bs_mid * 0.003)
            noise = rng.normal(0.0, bs_mid * 0.001)
            mid = max(0.01, bs_mid + noise)
            bid = round(max(0.01, mid - spread / 2.0), 2)
            ask = round(mid + spread / 2.0, 2)

            rows.append({"date": d, "ric": ric, "bid": bid, "ask": ask})

    if not rows:
        raise RuntimeError("Mock data generation produced no rows — check RIC list.")

    return pd.DataFrame(rows)
