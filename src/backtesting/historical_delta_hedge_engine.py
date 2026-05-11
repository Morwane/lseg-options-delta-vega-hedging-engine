"""Real historical listed-options delta-hedging backtest engine.

Portfolio model:
    - Contracts are selected once on the FIRST available date (no look-ahead).
    - The book is held static through the backtest; contracts that lose data on
      a given day are skipped for P&L on that day but remain in the book.
    - One contract per selected RIC, standard 100-share multiplier.

P&L timing (matches user spec):
    - hedge_shares[t-1] generate hedge_pnl on date t:
          hedge_pnl_t = hedge_shares[t-1] × (spot_t - spot_{t-1})
    - option_pnl is mark-to-market:
          option_pnl_t = Σ (mid_t - mid_{t-1}) × qty × multiplier
    - After observing date-t data, rebalance hedge → new hedge_shares[t] for t→t+1.
    - Transaction costs arise only from hedge share changes.

IV hierarchy:
    1. Black-Scholes bisection from market mid price.
    2. If (1) fails and iv_fallback_allowed=True, use rolling realized vol.
       Flagged as iv_source="realized_vol_fallback".
    3. If both fail: delta excluded from portfolio aggregate; iv_source="failed".

Data quality:
    - fallback_rate per date and overall.
    - Backtest marked low_confidence if overall fallback_rate > iv_fallback_max_rate_warning.
    - market_vs_bs_gap_bps recorded per contract per date (diagnostic only).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml

from src.backtesting.contract_selection import ContractBar, ContractSelectionResult, select_atm_contracts
from src.backtesting.option_history_loader import decode_strike_from_ric
from src.hedging.delta_hedger import recommend_delta_hedge
from src.hedging.rebalance_rules import HedgeRules
from src.hedging.transaction_costs import estimate_transaction_cost
from src.pricing.black_scholes import BlackScholesInputs, BlackScholesResult, black_scholes_all
from src.pricing.implied_vol import implied_vol_bisection


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HistoricalBacktestConfig:
    underlying: str
    option_type: str
    expiry_date: date
    atm_contract_count: int
    risk_free_rate: float
    spy_dividend_yield: float
    iv_bisection_sigma_low: float
    iv_bisection_sigma_high: float
    iv_bisection_tolerance: float
    iv_fallback_allowed: bool
    iv_fallback_vol_window_days: int
    iv_fallback_max_rate_warning: float
    delta_threshold_shares: float
    max_order_notional_usd: float
    hedge_cost_bps: float
    contracts_per_position: int
    contract_multiplier: int
    output_dir: Path


def load_backtest_config(config_path: Path) -> HistoricalBacktestConfig:
    """Parse historical_backtest.yaml into a HistoricalBacktestConfig."""
    raw = yaml.safe_load(config_path.read_text())

    expiry_raw = raw["expiry_date"]
    if isinstance(expiry_raw, str):
        expiry = date.fromisoformat(expiry_raw)
    else:
        expiry = expiry_raw  # PyYAML may parse date literals directly

    return HistoricalBacktestConfig(
        underlying=str(raw["underlying"]),
        option_type=str(raw["option_type"]),
        expiry_date=expiry,
        atm_contract_count=int(raw["atm_contract_count"]),
        risk_free_rate=float(raw["risk_free_rate"]),
        spy_dividend_yield=float(raw["spy_dividend_yield"]),
        iv_bisection_sigma_low=float(raw["iv_bisection_sigma_low"]),
        iv_bisection_sigma_high=float(raw["iv_bisection_sigma_high"]),
        iv_bisection_tolerance=float(raw["iv_bisection_tolerance"]),
        iv_fallback_allowed=bool(raw["iv_fallback_allowed"]),
        iv_fallback_vol_window_days=int(raw["iv_fallback_vol_window_days"]),
        iv_fallback_max_rate_warning=float(raw["iv_fallback_max_rate_warning"]),
        delta_threshold_shares=float(raw["delta_threshold_shares"]),
        max_order_notional_usd=float(raw["max_order_notional_usd"]),
        hedge_cost_bps=float(raw["hedge_cost_bps"]),
        contracts_per_position=int(raw["contracts_per_position"]),
        contract_multiplier=int(raw["contract_multiplier"]),
        output_dir=Path(str(raw["output_dir"])),
    )


# ---------------------------------------------------------------------------
# Per-contract IV + Greeks result
# ---------------------------------------------------------------------------

@dataclass
class IVResult:
    iv: float | None
    iv_source: Literal["bs_bisection", "realized_vol_fallback", "failed"]
    bs_result: BlackScholesResult | None
    error_msg: str = ""


@dataclass
class DailyContractGreeks:
    date: date
    ric: str
    strike: float
    spot: float
    tte_years: float
    market_mid: float
    bid: float
    ask: float
    spread: float
    iv: float | None
    iv_source: str
    delta: float | None
    gamma: float | None
    vega: float | None
    theta: float | None
    bs_price: float | None
    market_vs_bs_gap_bps: float | None    # diagnostic only, not a signal
    iv_error: str


# ---------------------------------------------------------------------------
# Daily hedge output row
# ---------------------------------------------------------------------------

@dataclass
class DailyHedgeRow:
    date: date
    spot: float
    tte_years: float
    contracts_in_book: int
    portfolio_delta: float
    hedge_shares_before: float
    target_hedge_shares: float
    hedge_order_shares: float
    hedge_order_side: str
    hedge_reason: str
    hedge_shares_after: float
    option_pnl: float
    hedge_pnl: float
    gross_pnl: float
    transaction_costs: float
    net_pnl: float
    cumulative_net_pnl: float
    unhedged_option_pnl: float
    cumulative_unhedged_pnl: float
    fallback_count: int
    fallback_rate: float
    low_confidence: bool


# ---------------------------------------------------------------------------
# Full backtest result bundle
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    daily_hedge_rows: list[DailyHedgeRow]
    daily_greeks: list[DailyContractGreeks]
    initial_selection: list[ContractBar]
    exclusion_log: list[dict[str, Any]]
    fallback_rate_overall: float
    is_low_confidence: bool
    limitations: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rolling_realized_vol(spot_series: pd.Series, window: int) -> pd.Series:
    """Annualised rolling realised volatility from log returns (√252 scaling)."""
    log_rets = np.log(spot_series / spot_series.shift(1))
    return log_rets.rolling(window=window, min_periods=max(2, window // 2)).std() * math.sqrt(252)


def _compute_iv_and_greeks(
    market_mid: float,
    spot: float,
    strike: float,
    tte_years: float,
    config: HistoricalBacktestConfig,
    realized_vol: float | None,
) -> IVResult:
    """Attempt BS IV bisection; fall back to realized vol if allowed and solve fails."""
    try:
        iv = implied_vol_bisection(
            market_price=market_mid,
            spot=spot,
            strike=strike,
            time_to_expiry=tte_years,
            risk_free_rate=config.risk_free_rate,
            option_type="call",
            dividend_yield=config.spy_dividend_yield,
            sigma_low=config.iv_bisection_sigma_low,
            sigma_high=config.iv_bisection_sigma_high,
            tolerance=config.iv_bisection_tolerance,
        )
        bs_result = black_scholes_all(
            BlackScholesInputs(
                spot=spot,
                strike=strike,
                time_to_expiry=tte_years,
                risk_free_rate=config.risk_free_rate,
                volatility=iv,
                option_type="call",
                dividend_yield=config.spy_dividend_yield,
            )
        )
        return IVResult(iv=iv, iv_source="bs_bisection", bs_result=bs_result)

    except Exception as e:
        err_msg = str(e)

    # --- Fallback: rolling realized vol ---
    if config.iv_fallback_allowed and realized_vol is not None and realized_vol > 0:
        try:
            bs_result = black_scholes_all(
                BlackScholesInputs(
                    spot=spot,
                    strike=strike,
                    time_to_expiry=tte_years,
                    risk_free_rate=config.risk_free_rate,
                    volatility=realized_vol,
                    option_type="call",
                    dividend_yield=config.spy_dividend_yield,
                )
            )
            return IVResult(
                iv=realized_vol,
                iv_source="realized_vol_fallback",
                bs_result=bs_result,
                error_msg=err_msg,
            )
        except Exception as e2:
            err_msg = f"{err_msg} | fallback_error: {e2}"

    return IVResult(iv=None, iv_source="failed", bs_result=None, error_msg=err_msg)


def _build_bar_lookup(
    option_history: pd.DataFrame,
) -> dict[tuple[date, str], tuple[float, float, float]]:
    """Pre-compute (date, ric) → (bid, ask, mid) for O(1) access in the hot loop."""
    lookup: dict[tuple[date, str], tuple[float, float, float]] = {}
    for _, row in option_history.iterrows():
        d = row["date"]
        ric = str(row["ric"])
        try:
            bid = float(row["bid"])
            ask = float(row["ask"])
        except (TypeError, ValueError):
            continue
        if math.isnan(bid) or math.isnan(ask) or bid <= 0 or ask <= 0 or ask <= bid:
            continue
        lookup[(d, ric)] = (bid, ask, (bid + ask) / 2.0)
    return lookup


def _compute_portfolio_greeks_for_date(
    d: date,
    rics: list[str],
    ric_strikes: dict[str, float | None],
    spot: float,
    config: HistoricalBacktestConfig,
    rv_by_date: dict[date, float],
    bar_lookup: dict[tuple[date, str], tuple[float, float, float]],
    qty_per_contract: int,
) -> tuple[float, list[DailyContractGreeks]]:
    """Compute BS Greeks for all held RICs on date d.

    Returns (portfolio_delta, greeks_list).
    Contracts with failed IV contribute 0 delta to the aggregate.
    """
    greeks: list[DailyContractGreeks] = []
    portfolio_delta = 0.0
    tte = max(1e-6, (config.expiry_date - d).days / 365.0)
    rv = rv_by_date.get(d)

    for ric in rics:
        strike = ric_strikes.get(ric)
        if strike is None:
            continue

        bar = bar_lookup.get((d, ric))
        if bar is None:
            greeks.append(
                DailyContractGreeks(
                    date=d, ric=ric, strike=strike, spot=spot, tte_years=tte,
                    market_mid=float("nan"), bid=float("nan"), ask=float("nan"),
                    spread=float("nan"), iv=None, iv_source="failed",
                    delta=None, gamma=None, vega=None, theta=None,
                    bs_price=None, market_vs_bs_gap_bps=None,
                    iv_error="missing_market_data",
                )
            )
            continue

        bid, ask, mid = bar
        spread = ask - bid

        iv_result = _compute_iv_and_greeks(
            market_mid=mid,
            spot=spot,
            strike=strike,
            tte_years=tte,
            config=config,
            realized_vol=rv,
        )

        bs = iv_result.bs_result
        delta = bs.delta if bs else None
        gamma = bs.gamma if bs else None
        vega = bs.vega if bs else None
        theta = bs.theta if bs else None
        bs_price = bs.price if bs else None

        gap_bps: float | None = None
        if bs_price is not None and bs_price > 0:
            gap_bps = (mid - bs_price) / bs_price * 10_000.0

        if delta is not None:
            portfolio_delta += delta * qty_per_contract

        greeks.append(
            DailyContractGreeks(
                date=d, ric=ric, strike=strike, spot=spot, tte_years=tte,
                market_mid=mid, bid=bid, ask=ask, spread=spread,
                iv=iv_result.iv, iv_source=iv_result.iv_source,
                delta=delta, gamma=gamma, vega=vega, theta=theta,
                bs_price=bs_price, market_vs_bs_gap_bps=gap_bps,
                iv_error=iv_result.error_msg,
            )
        )

    return portfolio_delta, greeks


# ---------------------------------------------------------------------------
# Main backtest entry point
# ---------------------------------------------------------------------------

def run_backtest(
    config: HistoricalBacktestConfig,
    option_history: pd.DataFrame,
    spy_history: pd.DataFrame,
) -> BacktestResult:
    """Run the real historical listed-options delta-hedging backtest.

    Args:
        config:          Loaded HistoricalBacktestConfig.
        option_history:  DataFrame with columns (date, ric, bid, ask).
                         date column must be typed as datetime.date.
        spy_history:     DataFrame with columns (date, spot).

    Returns:
        BacktestResult with all daily rows, Greeks, exclusion log, and limitations.

    Raises:
        ValueError  — fewer than 2 dates available.
        RuntimeError — no valid contracts found for initial selection.
    """
    # --- Normalise inputs ---
    option_history = option_history.copy()
    option_history["date"] = pd.to_datetime(option_history["date"]).dt.date

    spy_history = spy_history.copy()
    spy_history["date"] = pd.to_datetime(spy_history["date"]).dt.date
    spy_history = spy_history.sort_values("date").reset_index(drop=True)

    spot_by_date: dict[date, float] = dict(zip(spy_history["date"], spy_history["spot"]))

    # Rolling realised vol for IV fallback
    spot_series = spy_history.set_index("date")["spot"]
    rv_series = _rolling_realized_vol(
        pd.Series(spot_series.values, index=spot_series.index),
        window=config.iv_fallback_vol_window_days,
    )
    rv_by_date: dict[date, float] = {
        k: float(v) for k, v in rv_series.dropna().items()
    }

    dates = sorted(spot_by_date.keys())
    if len(dates) < 2:
        raise ValueError("Need at least 2 trading dates in spy_history to run backtest.")

    # --- Pre-compute bar lookup for O(1) access ---
    bar_lookup = _build_bar_lookup(option_history)

    # --- Initial contract selection (NO look-ahead: use first date only) ---
    first_date = dates[0]
    first_spot = spot_by_date[first_date]

    init_result: ContractSelectionResult = select_atm_contracts(
        selection_date=first_date,
        option_history=option_history,
        spot=first_spot,
        top_n=config.atm_contract_count,
    )

    exclusion_log: list[dict[str, Any]] = [
        {
            "date": str(e.date), "ric": e.ric, "strike": e.strike,
            "reason": e.reason, "phase": "initial_selection",
        }
        for e in init_result.excluded
    ]

    if not init_result.selected:
        raise RuntimeError(
            f"No valid contracts found for initial ATM selection on {first_date}. "
            "Ensure option_history contains data for that date."
        )

    selected_rics: list[str] = init_result.selected_rics
    ric_strikes: dict[str, float | None] = {
        ric: decode_strike_from_ric(ric) for ric in selected_rics
    }
    qty_per_contract = config.contracts_per_position * config.contract_multiplier

    # Build hedge rules (automated rebalance in backtest — no manual approval prompt)
    hedge_rules = HedgeRules(
        paper_trading_only=True,
        allow_live_trading=False,
        dry_run_default=True,
        manual_approval_required=False,
        delta_threshold_shares=config.delta_threshold_shares,
        max_order_notional_usd=config.max_order_notional_usd,
        min_rebalance_interval_minutes=0,
        fallback_transaction_cost_bps=config.hedge_cost_bps,
    )

    # --- Accumulators ---
    daily_hedge_rows: list[DailyHedgeRow] = []
    daily_greeks: list[DailyContractGreeks] = []
    total_iv_attempts = 0
    total_iv_fallbacks = 0
    hedge_shares = 0.0
    cumulative_net_pnl = 0.0
    cumulative_unhedged_pnl = 0.0

    # --- Day 0: initialise portfolio Greeks and set opening hedge ---
    d0_delta, d0_greeks = _compute_portfolio_greeks_for_date(
        d=first_date,
        rics=selected_rics,
        ric_strikes=ric_strikes,
        spot=first_spot,
        config=config,
        rv_by_date=rv_by_date,
        bar_lookup=bar_lookup,
        qty_per_contract=qty_per_contract,
    )
    daily_greeks.extend(d0_greeks)
    total_iv_attempts += len(d0_greeks)
    total_iv_fallbacks += sum(1 for g in d0_greeks if g.iv_source == "realized_vol_fallback")

    rec0 = recommend_delta_hedge(
        underlying=config.underlying,
        portfolio_delta=d0_delta,
        current_underlying_position=0.0,
        spot=first_spot,
        rules=hedge_rules,
    )
    hedge_shares = rec0.target_underlying_position if rec0.side != "NONE" else 0.0
    init_tx_cost = estimate_transaction_cost(hedge_shares, first_spot, config.hedge_cost_bps)
    cumulative_net_pnl = -init_tx_cost

    tte_0 = max(1e-6, (config.expiry_date - first_date).days / 365.0)
    fb_count_0 = sum(1 for g in d0_greeks if g.iv_source == "realized_vol_fallback")
    fb_rate_0 = fb_count_0 / max(1, len(d0_greeks))

    daily_hedge_rows.append(
        DailyHedgeRow(
            date=first_date,
            spot=first_spot,
            tte_years=tte_0,
            contracts_in_book=len(selected_rics),
            portfolio_delta=d0_delta,
            hedge_shares_before=0.0,
            target_hedge_shares=hedge_shares,
            hedge_order_shares=hedge_shares,
            hedge_order_side=rec0.side if rec0.side != "NONE" else "SELL" if hedge_shares < 0 else "BUY",
            hedge_reason="initial_hedge",
            hedge_shares_after=hedge_shares,
            option_pnl=0.0,
            hedge_pnl=0.0,
            gross_pnl=0.0,
            transaction_costs=init_tx_cost,
            net_pnl=-init_tx_cost,
            cumulative_net_pnl=cumulative_net_pnl,
            unhedged_option_pnl=0.0,
            cumulative_unhedged_pnl=0.0,
            fallback_count=fb_count_0,
            fallback_rate=fb_rate_0,
            low_confidence=fb_rate_0 > config.iv_fallback_max_rate_warning,
        )
    )

    # --- Main loop: t = 1 … T-1 ---
    prev_date = first_date

    for t in range(1, len(dates)):
        cur_date = dates[t]
        cur_spot = spot_by_date[cur_date]
        prev_spot = spot_by_date[prev_date]
        tte = max(1e-6, (config.expiry_date - cur_date).days / 365.0)

        # Option mark-to-market P&L: uses prices from prev_date and cur_date
        option_pnl = 0.0
        contracts_with_pnl: list[str] = []

        for ric in selected_rics:
            prev_bar = bar_lookup.get((prev_date, ric))
            cur_bar = bar_lookup.get((cur_date, ric))
            if prev_bar is None or cur_bar is None:
                exclusion_log.append(
                    {
                        "date": str(cur_date), "ric": ric,
                        "strike": ric_strikes.get(ric),
                        "reason": "missing_data_for_pnl",
                        "phase": "pnl_loop",
                    }
                )
                continue
            _, _, prev_mid = prev_bar
            _, _, cur_mid = cur_bar
            option_pnl += (cur_mid - prev_mid) * qty_per_contract
            contracts_with_pnl.append(ric)

        # Hedge P&L: previous day's hedge position × spot move
        hedge_pnl = hedge_shares * (cur_spot - prev_spot)

        gross_pnl = option_pnl + hedge_pnl
        unhedged_option_pnl = option_pnl

        # Recompute delta after observing today's data
        portfolio_delta, today_greeks = _compute_portfolio_greeks_for_date(
            d=cur_date,
            rics=selected_rics,
            ric_strikes=ric_strikes,
            spot=cur_spot,
            config=config,
            rv_by_date=rv_by_date,
            bar_lookup=bar_lookup,
            qty_per_contract=qty_per_contract,
        )
        daily_greeks.extend(today_greeks)
        total_iv_attempts += len(today_greeks)
        total_iv_fallbacks += sum(1 for g in today_greeks if g.iv_source == "realized_vol_fallback")

        # Rebalance hedge
        prev_hedge = hedge_shares
        rec = recommend_delta_hedge(
            underlying=config.underlying,
            portfolio_delta=portfolio_delta,
            current_underlying_position=hedge_shares,
            spot=cur_spot,
            rules=hedge_rules,
        )
        order_qty = 0.0
        if rec.side != "NONE":
            order_qty = rec.target_underlying_position - hedge_shares
            hedge_shares = rec.target_underlying_position

        tx_cost = estimate_transaction_cost(order_qty, cur_spot, config.hedge_cost_bps)
        net_pnl = gross_pnl - tx_cost
        cumulative_net_pnl += net_pnl
        cumulative_unhedged_pnl += unhedged_option_pnl

        fb_count = sum(1 for g in today_greeks if g.iv_source == "realized_vol_fallback")
        fb_rate = fb_count / max(1, len(today_greeks))

        daily_hedge_rows.append(
            DailyHedgeRow(
                date=cur_date,
                spot=cur_spot,
                tte_years=tte,
                contracts_in_book=len(contracts_with_pnl),
                portfolio_delta=portfolio_delta,
                hedge_shares_before=prev_hedge,
                target_hedge_shares=rec.target_underlying_position,
                hedge_order_shares=order_qty,
                hedge_order_side=rec.side,
                hedge_reason=rec.reason,
                hedge_shares_after=hedge_shares,
                option_pnl=option_pnl,
                hedge_pnl=hedge_pnl,
                gross_pnl=gross_pnl,
                transaction_costs=tx_cost,
                net_pnl=net_pnl,
                cumulative_net_pnl=cumulative_net_pnl,
                unhedged_option_pnl=unhedged_option_pnl,
                cumulative_unhedged_pnl=cumulative_unhedged_pnl,
                fallback_count=fb_count,
                fallback_rate=fb_rate,
                low_confidence=fb_rate > config.iv_fallback_max_rate_warning,
            )
        )

        prev_date = cur_date

    # --- Final statistics ---
    fallback_rate_overall = total_iv_fallbacks / max(1, total_iv_attempts)
    is_low_confidence = fallback_rate_overall > config.iv_fallback_max_rate_warning

    limitations = [
        "Calls only — no puts confirmed in LSEG audit",
        "SPY underlying only",
        "Jan 2027 expiry only (single expiry, no term structure)",
        "~30 trading days of data (2026-03-18 to 2026-04-29)",
        "Greeks reconstructed from market mid via Black-Scholes IV bisection",
        "Historical LSEG option Greeks not used (only 1 snapshot row per RIC in audit)",
        "Portfolio fixed at initial ATM selection — no intraday contract rotation",
        "No alpha strategy — pure delta-hedge P&L illustration",
        "No IBKR orders in this phase",
        (
            f"Confirmed RIC universe contains calls with strikes $50–$645; "
            f"nearest-ATM contracts selected at ~SPY spot"
        ),
        (
            f"Overall IV fallback rate: {fallback_rate_overall:.1%}"
            + (" [LOW CONFIDENCE — fallback rate exceeds 30%]" if is_low_confidence else "")
        ),
    ]

    return BacktestResult(
        daily_hedge_rows=daily_hedge_rows,
        daily_greeks=daily_greeks,
        initial_selection=init_result.selected,
        exclusion_log=exclusion_log,
        fallback_rate_overall=fallback_rate_overall,
        is_low_confidence=is_low_confidence,
        limitations=limitations,
    )


# ---------------------------------------------------------------------------
# Output helpers — convert results to DataFrames
# ---------------------------------------------------------------------------

def to_daily_hedge_df(rows: list[DailyHedgeRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": r.date,
                "spot": r.spot,
                "tte_years": round(r.tte_years, 4),
                "contracts_in_book": r.contracts_in_book,
                "portfolio_delta": round(r.portfolio_delta, 4),
                "hedge_shares_before": round(r.hedge_shares_before, 4),
                "target_hedge_shares": round(r.target_hedge_shares, 4),
                "hedge_order_shares": round(r.hedge_order_shares, 4),
                "hedge_order_side": r.hedge_order_side,
                "hedge_shares_after": round(r.hedge_shares_after, 4),
                "option_pnl": round(r.option_pnl, 4),
                "hedge_pnl": round(r.hedge_pnl, 4),
                "gross_pnl": round(r.gross_pnl, 4),
                "transaction_costs": round(r.transaction_costs, 4),
                "net_pnl": round(r.net_pnl, 4),
                "cumulative_net_pnl": round(r.cumulative_net_pnl, 4),
                "unhedged_option_pnl": round(r.unhedged_option_pnl, 4),
                "cumulative_unhedged_pnl": round(r.cumulative_unhedged_pnl, 4),
                "fallback_count": r.fallback_count,
                "fallback_rate": round(r.fallback_rate, 4),
                "low_confidence": r.low_confidence,
                "hedge_reason": r.hedge_reason,
            }
            for r in rows
        ]
    )


def to_greeks_df(greeks: list[DailyContractGreeks]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": g.date,
                "ric": g.ric,
                "strike": g.strike,
                "spot": g.spot,
                "tte_years": round(g.tte_years, 4),
                "market_mid": round(g.market_mid, 4) if math.isfinite(g.market_mid) else None,
                "bid": round(g.bid, 4) if math.isfinite(g.bid) else None,
                "ask": round(g.ask, 4) if math.isfinite(g.ask) else None,
                "spread": round(g.spread, 4) if math.isfinite(g.spread) else None,
                "iv": round(g.iv, 6) if g.iv is not None else None,
                "iv_source": g.iv_source,
                "delta": round(g.delta, 6) if g.delta is not None else None,
                "gamma": round(g.gamma, 8) if g.gamma is not None else None,
                "vega": round(g.vega, 6) if g.vega is not None else None,
                "theta": round(g.theta, 6) if g.theta is not None else None,
                "bs_price": round(g.bs_price, 4) if g.bs_price is not None else None,
                "market_vs_bs_gap_bps": (
                    round(g.market_vs_bs_gap_bps, 2)
                    if g.market_vs_bs_gap_bps is not None else None
                ),
                "iv_error": g.iv_error,
            }
            for g in greeks
        ]
    )


def to_data_quality_df(
    daily_greeks: list[DailyContractGreeks],
    exclusion_log: list[dict[str, Any]],
    fallback_rate_overall: float,
    is_low_confidence: bool,
) -> pd.DataFrame:
    """Aggregate per-date data quality metrics."""
    rows_by_date: dict[date, dict[str, Any]] = {}

    for g in daily_greeks:
        entry = rows_by_date.setdefault(
            g.date,
            {
                "date": g.date,
                "total_contracts": 0,
                "iv_solved": 0,
                "iv_fallback": 0,
                "iv_failed": 0,
                "missing_data": 0,
            },
        )
        entry["total_contracts"] += 1
        if g.iv_source == "bs_bisection":
            entry["iv_solved"] += 1
        elif g.iv_source == "realized_vol_fallback":
            entry["iv_fallback"] += 1
        elif g.iv_source == "failed":
            if g.iv_error == "missing_market_data":
                entry["missing_data"] += 1
            else:
                entry["iv_failed"] += 1

    for entry in rows_by_date.values():
        total = entry["total_contracts"]
        entry["fallback_rate"] = round(entry["iv_fallback"] / max(1, total), 4)
        entry["low_confidence"] = entry["fallback_rate"] > 0.30

    result = pd.DataFrame(sorted(rows_by_date.values(), key=lambda r: r["date"]))
    result.attrs["fallback_rate_overall"] = round(fallback_rate_overall, 4)
    result.attrs["is_low_confidence"] = is_low_confidence
    return result
