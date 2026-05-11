"""Paper order confirmation prompt and execution log record.

Extracted from the script layer so tests can import and verify behavior
without importing the full run_daily_hedge script module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PaperOrderRecord:
    """One row in the paper execution log."""
    trade_date: str
    symbol: str
    action: str
    quantity: float
    estimated_notional: float
    estimated_cost_usd: float
    proposed: bool
    executed: bool
    order_id: int | None = field(default=None)
    order_status: str = field(default="")
    reason: str = field(default="")


def prompt_confirm_paper_order(
    sym: str,
    action: str,
    qty: float,
    notional: float,
    cost: float,
    input_fn: Callable[[str], str] = input,
) -> bool:
    """Print the proposed order and prompt for y/N confirmation.

    Returns True only when the user types 'y' or 'Y'.
    Empty input or anything else defaults to No.
    """
    print(f"\n  Proposed PAPER order : {action} {qty:.0f} {sym} @ MKT")
    print(f"  Estimated notional   : ${notional:,.2f}")
    print(f"  Estimated cost       : ${cost:.2f}")
    answer = input_fn(f"  Send PAPER order for {sym}? [y/N]: ").strip()
    return answer.lower() == "y"
