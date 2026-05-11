#!/usr/bin/env python3
"""Offline demo: Greeks, exposures, and hedge recommendations — no LSEG or IBKR required."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

# Allow running as a script without installing the package
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.hedging.delta_hedger import HedgeRecommendation, recommend_delta_hedge
from src.hedging.rebalance_rules import load_hedge_rules
from src.portfolio.exposures import aggregate_by_underlying, compute_position_greeks
from src.portfolio.positions import load_portfolio

_CONFIG = _ROOT / "config"
_OUTPUT = _ROOT / "outputs" / "reports"


def main() -> None:
    _OUTPUT.mkdir(parents=True, exist_ok=True)

    portfolio = load_portfolio(_CONFIG / "demo_portfolio.yaml")
    rules = load_hedge_rules(_CONFIG / "hedge_rules.yaml")
    valuation_date = date.today()

    print(f"[demo] valuation date    : {valuation_date}")
    print(f"[demo] option positions  : {len(portfolio.option_positions)}")

    # Greeks per position
    position_greeks = compute_position_greeks(portfolio, as_of=valuation_date)
    print(f"[demo] live positions    : {len(position_greeks)}  (expired excluded)")

    # Aggregate by underlying
    exposures = aggregate_by_underlying(position_greeks, portfolio.spot_prices)

    # Hedge recommendations via delta_hedger module
    recommendations: list[HedgeRecommendation] = []
    for sym, exp in exposures.items():
        current_pos = portfolio.underlying_positions.get(sym)
        current_qty = current_pos.quantity if current_pos else 0.0
        rec = recommend_delta_hedge(
            underlying=sym,
            portfolio_delta=exp.net_delta,
            current_underlying_position=current_qty,
            spot=exp.spot,
            rules=rules,
        )
        recommendations.append(rec)

    # --- Write CSVs ---

    pos_rows = [
        {
            "id": pg.id,
            "underlying": pg.underlying,
            "option_type": pg.option_type,
            "strike": pg.strike,
            "expiry": pg.expiry,
            "quantity": pg.quantity,
            "multiplier": pg.multiplier,
            "spot": round(pg.spot, 4),
            "implied_vol": pg.implied_vol,
            "time_to_expiry_years": round(pg.time_to_expiry, 6),
            "option_price": round(pg.option_price, 6),
            "option_delta": round(pg.option_delta, 6),
            "option_gamma": round(pg.option_gamma, 6),
            "option_vega": round(pg.option_vega, 6),
            "option_theta": round(pg.option_theta, 6),
            "position_delta": round(pg.position_delta, 4),
            "position_gamma": round(pg.position_gamma, 6),
            "position_vega": round(pg.position_vega, 4),
            "position_theta": round(pg.position_theta, 4),
        }
        for pg in position_greeks
    ]
    df_pos = pd.DataFrame(pos_rows)
    df_pos.to_csv(_OUTPUT / "greeks_by_position.csv", index=False)
    print(f"[demo] wrote greeks_by_position.csv  ({len(df_pos)} rows)")

    exp_rows = [
        {
            "underlying": exp.underlying,
            "spot": round(exp.spot, 4),
            "net_delta": round(exp.net_delta, 4),
            "net_gamma": round(exp.net_gamma, 6),
            "net_vega": round(exp.net_vega, 4),
            "net_theta": round(exp.net_theta, 4),
            "num_positions": exp.num_positions,
        }
        for exp in exposures.values()
    ]
    df_exp = pd.DataFrame(exp_rows)
    df_exp.to_csv(_OUTPUT / "portfolio_exposures.csv", index=False)
    print(f"[demo] wrote portfolio_exposures.csv ({len(df_exp)} rows)")

    hedge_rows = [
        {
            "underlying": r.underlying,
            "spot": round(r.spot, 4),
            "portfolio_delta": round(r.portfolio_delta, 4),
            "current_position": r.current_underlying_position,
            "target_position": round(r.target_underlying_position, 4),
            "order_quantity": round(r.order_quantity, 4),
            "side": r.side,
            "estimated_notional": round(r.estimated_notional, 2),
            "estimated_cost_usd": round(r.estimated_transaction_cost, 2),
            "blocked": r.blocked,
            "dry_run": True,
            "reason": r.reason,
        }
        for r in recommendations
    ]
    df_hedge = pd.DataFrame(hedge_rows)
    df_hedge.to_csv(_OUTPUT / "hedge_orders.csv", index=False)
    print(f"[demo] wrote hedge_orders.csv        ({len(df_hedge)} rows)")

    # --- Console summary ---
    print("\n=== Portfolio exposures ===")
    print(df_exp.to_string(index=False))
    print("\n=== Hedge orders (dry_run=True) ===")
    print(
        df_hedge[
            ["underlying", "portfolio_delta", "order_quantity", "side",
             "estimated_cost_usd", "blocked", "reason"]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
