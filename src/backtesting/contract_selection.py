"""No-look-ahead contract selection for the historical backtest.

Selection rules applied for date t:
    1. Only use rows with date == t (no future data).
    2. Require valid bid > 0 and ask > 0.
    3. Require ask > bid (no crossed markets).
    4. Require mid > 0.
    5. Require decodable strike from RIC.
    6. Sort remaining candidates by abs(strike - spot) ascending.
    7. Return top_n; log all exclusions with their reason.

Moneyness classification:
    ATM band: |strike - spot| / spot ≤ 2% (configurable).
    For calls: ITM when strike < spot (outside ATM band).
               OTM when strike > spot (outside ATM band).
    Near-ATM warning: if no selected contract is within 3% of spot,
    the selection is labelled "nearest available liquid call selection"
    rather than "ATM selection".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from src.backtesting.option_history_loader import decode_strike_from_ric


@dataclass(frozen=True)
class ContractBar:
    ric: str
    strike: float
    date: date
    bid: float
    ask: float
    mid: float
    spread: float
    moneyness_abs: float    # abs(strike - spot)
    moneyness_pct: float    # (spot - strike) / spot  (positive = ITM call)
    moneyness_class: str    # "ATM", "ITM", or "OTM"


@dataclass(frozen=True)
class ExcludedContract:
    ric: str
    strike: float | None
    date: date
    reason: str


@dataclass
class ContractSelectionResult:
    date: date
    spot: float
    selected: list[ContractBar]
    excluded: list[ExcludedContract]

    @property
    def selected_rics(self) -> list[str]:
        return [c.ric for c in self.selected]


# ---------------------------------------------------------------------------
# Moneyness helpers
# ---------------------------------------------------------------------------

def classify_moneyness(
    strike: float,
    spot: float,
    option_type: str = "call",
    atm_band_pct: float = 0.02,
) -> Literal["ATM", "ITM", "OTM"]:
    """Classify an option as ATM, ITM, or OTM.

    ATM band: |strike - spot| / spot ≤ atm_band_pct (default 2%).
    Outside the ATM band:
        call: ITM when strike < spot, OTM when strike > spot.
        put:  ITM when strike > spot, OTM when strike < spot.

    Args:
        strike:       Option strike price.
        spot:         Underlying spot price.
        option_type:  "call" or "put".
        atm_band_pct: Fraction of spot defining the ATM band (default 0.02 = 2%).

    Returns:
        One of "ATM", "ITM", "OTM".
    """
    if spot <= 0:
        return "OTM"
    if abs(strike - spot) / spot <= atm_band_pct:
        return "ATM"
    if option_type == "call":
        return "ITM" if strike < spot else "OTM"
    # put
    return "ITM" if strike > spot else "OTM"


def is_near_atm(strike: float, spot: float, threshold_pct: float = 0.03) -> bool:
    """Return True if |strike - spot| / spot ≤ threshold_pct.

    Default threshold is 3% — used for the moneyness warning.
    """
    if spot <= 0:
        return False
    return abs(strike - spot) / spot <= threshold_pct


def check_atm_warning(
    selected: list[ContractBar],
    spot: float,
    threshold_pct: float = 0.03,
) -> tuple[bool, str]:
    """Check whether all selected contracts are beyond threshold_pct from ATM.

    Returns:
        (warning_triggered, warning_message)
        warning_triggered is True when NO selected contract is within threshold_pct.
    """
    if not selected:
        return False, ""
    if any(is_near_atm(c.strike, spot, threshold_pct) for c in selected):
        return False, ""
    closest = min(selected, key=lambda c: c.moneyness_abs)
    direction = "ITM" if closest.moneyness_pct > 0 else "OTM"
    pct_away = abs(closest.moneyness_pct) * 100
    return True, (
        f"No selected contract is within {threshold_pct * 100:.0f}% of spot "
        f"(${spot:.2f}). "
        f"Nearest: {closest.ric}, strike ${closest.strike:.0f} "
        f"({pct_away:.1f}% {direction}). "
        f"Reporting as 'nearest available liquid calls'."
    )


def get_selection_label(
    selected: list[ContractBar],
    spot: float,
    near_atm_threshold_pct: float = 0.03,
) -> str:
    """Return a user-facing label describing the selection type.

    Returns "ATM selection" when at least one contract is within
    near_atm_threshold_pct of spot; otherwise returns
    "nearest available liquid call selection".
    """
    if any(is_near_atm(c.strike, spot, near_atm_threshold_pct) for c in selected):
        return "ATM selection"
    return "nearest available liquid call selection"


# ---------------------------------------------------------------------------
# Contract selection
# ---------------------------------------------------------------------------

def select_atm_contracts(
    selection_date: date,
    option_history: pd.DataFrame,
    spot: float,
    top_n: int = 5,
) -> ContractSelectionResult:
    """Return the *top_n* contracts closest to ATM on *selection_date*.

    Uses only rows matching selection_date — strictly no look-ahead.
    Every excluded contract is logged with a reason string.

    Args:
        selection_date: Date for which to run selection.
        option_history:  DataFrame with columns (date, ric, bid, ask).
                         The 'date' column must already be typed as datetime.date.
        spot:            SPY spot price on selection_date.
        top_n:           Maximum number of contracts to select.

    Returns:
        ContractSelectionResult containing selected and excluded lists.
    """
    day_data = option_history[option_history["date"] == selection_date]

    excluded: list[ExcludedContract] = []
    candidates: list[ContractBar] = []

    for _, row in day_data.iterrows():
        ric = str(row["ric"])
        strike = decode_strike_from_ric(ric)

        if strike is None:
            excluded.append(
                ExcludedContract(
                    ric=ric, strike=None, date=selection_date,
                    reason="cannot_decode_strike",
                )
            )
            continue

        # Parse bid / ask safely
        try:
            bid = float(row["bid"])
        except (TypeError, ValueError):
            bid = float("nan")
        try:
            ask = float(row["ask"])
        except (TypeError, ValueError):
            ask = float("nan")

        if math.isnan(bid) or bid <= 0:
            excluded.append(
                ExcludedContract(ric=ric, strike=strike, date=selection_date, reason="invalid_bid")
            )
            continue
        if math.isnan(ask) or ask <= 0:
            excluded.append(
                ExcludedContract(ric=ric, strike=strike, date=selection_date, reason="invalid_ask")
            )
            continue
        if ask <= bid:
            excluded.append(
                ExcludedContract(ric=ric, strike=strike, date=selection_date, reason="crossed_market")
            )
            continue

        mid = (bid + ask) / 2.0
        if mid <= 0:
            excluded.append(
                ExcludedContract(ric=ric, strike=strike, date=selection_date, reason="non_positive_mid")
            )
            continue

        spread = ask - bid
        moneyness_abs = abs(strike - spot)
        moneyness_pct = (spot - strike) / spot if spot > 0 else 0.0
        moneyness_class = classify_moneyness(strike, spot, option_type="call")

        candidates.append(
            ContractBar(
                ric=ric,
                strike=strike,
                date=selection_date,
                bid=bid,
                ask=ask,
                mid=mid,
                spread=spread,
                moneyness_abs=moneyness_abs,
                moneyness_pct=moneyness_pct,
                moneyness_class=moneyness_class,
            )
        )

    # Sort by distance to ATM; take top_n
    candidates.sort(key=lambda c: c.moneyness_abs)
    selected = candidates[:top_n]

    # Candidates beyond top_n are excluded by the ATM filter
    for c in candidates[top_n:]:
        excluded.append(
            ExcludedContract(
                ric=c.ric,
                strike=c.strike,
                date=selection_date,
                reason="not_in_top_n_atm",
            )
        )

    return ContractSelectionResult(
        date=selection_date,
        spot=spot,
        selected=selected,
        excluded=excluded,
    )
