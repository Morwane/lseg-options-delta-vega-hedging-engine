"""LSEG option data loader — structured facade for the data pipeline.

Wraps the lower-level loaders in src/backtesting/option_history_loader.py
and adds explicit mode control, structured results, and graceful fallback.

Modes:
    'auto'   — try LSEG first; fall back to synthetic mock if unavailable
    'lseg'   — require LSEG; raise RuntimeError if unavailable
    'mock'   — always use synthetic offline data (CI / offline use)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd


@dataclass(frozen=True)
class LsegLoaderConfig:
    ric_config_path: Path
    history_count: int = 35
    mode: Literal["lseg", "mock", "auto"] = "auto"


@dataclass
class LsegLoadResult:
    option_history: pd.DataFrame
    spy_history: pd.DataFrame
    source: Literal["lseg", "mock"]
    rics_requested: int
    rics_with_data: int
    trading_days: int
    warnings: list[str]


def load_lseg_option_data(config: LsegLoaderConfig) -> LsegLoadResult:
    """Load LSEG option history and SPY underlying history.

    Falls back to synthetic mock data with a warning when LSEG is unavailable
    and mode='auto' (the default).
    """
    from src.backtesting.option_history_loader import (
        load_option_history_lseg,
        load_option_history_mock,
        load_ric_universe,
        load_spy_history_lseg,
        load_spy_history_mock,
    )

    rics = load_ric_universe(config.ric_config_path)
    warnings: list[str] = []

    if config.mode == "mock":
        option_df = load_option_history_mock(rics)
        spy_df = load_spy_history_mock()
        return LsegLoadResult(
            option_history=option_df,
            spy_history=spy_df,
            source="mock",
            rics_requested=len(rics),
            rics_with_data=int(option_df["ric"].nunique()) if not option_df.empty else 0,
            trading_days=int(option_df["date"].nunique()) if not option_df.empty else 0,
            warnings=["Using synthetic mock data (mode='mock')."],
        )

    # Attempt to open LSEG session
    try:
        import lseg.data as ld  # type: ignore[import]
        ld.open_session()
    except ImportError:
        msg = "lseg.data not installed — using synthetic mock data."
        if config.mode == "lseg":
            raise RuntimeError(msg + " Install with: pip install lseg-data") from None
        warnings.append(msg)
        option_df = load_option_history_mock(rics)
        spy_df = load_spy_history_mock()
        return LsegLoadResult(
            option_history=option_df,
            spy_history=spy_df,
            source="mock",
            rics_requested=len(rics),
            rics_with_data=int(option_df["ric"].nunique()) if not option_df.empty else 0,
            trading_days=int(option_df["date"].nunique()) if not option_df.empty else 0,
            warnings=warnings,
        )
    except Exception as exc:
        msg = f"LSEG session failed ({exc}) — using synthetic mock data."
        if config.mode == "lseg":
            raise RuntimeError(msg) from exc
        warnings.append(msg)
        option_df = load_option_history_mock(rics)
        spy_df = load_spy_history_mock()
        return LsegLoadResult(
            option_history=option_df,
            spy_history=spy_df,
            source="mock",
            rics_requested=len(rics),
            rics_with_data=int(option_df["ric"].nunique()) if not option_df.empty else 0,
            trading_days=int(option_df["date"].nunique()) if not option_df.empty else 0,
            warnings=warnings,
        )

    # LSEG session is open — fetch data
    source: Literal["lseg", "mock"] = "lseg"
    try:
        spy_df = load_spy_history_lseg(count=config.history_count)
        option_df = load_option_history_lseg(rics=rics, count=config.history_count)
    except Exception as exc:
        msg = f"LSEG data load failed ({exc}) — using synthetic mock data."
        if config.mode == "lseg":
            try:
                import lseg.data as ld  # noqa: F811
                ld.close_session()
            except Exception:
                pass
            raise RuntimeError(msg) from exc
        warnings.append(msg)
        option_df = load_option_history_mock(rics)
        spy_df = load_spy_history_mock()
        source = "mock"
    finally:
        try:
            import lseg.data as ld  # noqa: F811
            ld.close_session()
        except Exception:
            pass

    return LsegLoadResult(
        option_history=option_df,
        spy_history=spy_df,
        source=source,
        rics_requested=len(rics),
        rics_with_data=int(option_df["ric"].nunique()) if not option_df.empty else 0,
        trading_days=int(option_df["date"].nunique()) if not option_df.empty else 0,
        warnings=warnings,
    )
