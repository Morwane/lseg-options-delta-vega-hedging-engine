"""Hedge rebalancing rules loaded from config/hedge_rules.yaml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class HedgeRules:
    paper_trading_only: bool
    allow_live_trading: bool
    dry_run_default: bool
    manual_approval_required: bool
    delta_threshold_shares: float
    max_order_notional_usd: float
    min_rebalance_interval_minutes: int
    fallback_transaction_cost_bps: float

    def __post_init__(self) -> None:
        if self.allow_live_trading:
            raise ValueError(
                "allow_live_trading is True — live trading is prohibited in this prototype."
            )
        if not self.paper_trading_only:
            raise ValueError(
                "paper_trading_only is False — this prototype only supports paper trading."
            )


def load_hedge_rules(config_path: Path) -> HedgeRules:
    """Parse hedge_rules.yaml into a HedgeRules instance."""
    raw = yaml.safe_load(config_path.read_text())
    return HedgeRules(
        paper_trading_only=bool(raw["paper_trading_only"]),
        allow_live_trading=bool(raw["allow_live_trading"]),
        dry_run_default=bool(raw["dry_run_default"]),
        manual_approval_required=bool(raw["manual_approval_required"]),
        delta_threshold_shares=float(raw["delta_threshold_shares"]),
        max_order_notional_usd=float(raw["max_order_notional_usd"]),
        min_rebalance_interval_minutes=int(raw["min_rebalance_interval_minutes"]),
        fallback_transaction_cost_bps=float(raw["fallback_transaction_cost_bps"]),
    )
