"""LSEG option data quality reporter.

Produces four audit artefacts:
    coverage_by_ric.csv    — per-RIC availability of bid, ask, mid, IV
    coverage_by_field.csv  — per-field availability across all RICs
    manifest.json          — machine-readable audit metadata
    readable_summary.md    — human-readable Markdown quality report
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class RicCoverage:
    ric: str
    strike: float | None
    total_rows: int
    bid_available: int
    ask_available: int
    mid_available: int
    iv_lseg_available: int      # always 0 — LSEG historical IV not available
    history_days: int
    date_first: date | None
    date_last: date | None
    bid_coverage_pct: float
    ask_coverage_pct: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class FieldCoverage:
    field: str
    total_rics: int
    rics_with_any_data: int
    coverage_pct: float
    notes: str


def build_coverage_by_ric(
    option_history: pd.DataFrame,
    decode_strike_fn: Any = None,
) -> list[RicCoverage]:
    """Build per-RIC coverage statistics from an option_history DataFrame.

    Expected columns: date, ric, bid, ask
    """
    if option_history.empty:
        return []

    from src.backtesting.option_history_loader import decode_strike_from_ric
    if decode_strike_fn is None:
        decode_strike_fn = decode_strike_from_ric

    records: list[RicCoverage] = []

    for ric, grp in option_history.groupby("ric"):
        grp = grp.copy()
        grp["bid_num"] = pd.to_numeric(grp.get("bid", pd.Series(dtype=float)), errors="coerce")
        grp["ask_num"] = pd.to_numeric(grp.get("ask", pd.Series(dtype=float)), errors="coerce")

        n = len(grp)
        bid_ok = int(grp["bid_num"].notna().sum())
        ask_ok = int(grp["ask_num"].notna().sum())

        valid_mask = (
            grp["bid_num"].notna()
            & grp["ask_num"].notna()
            & (grp["bid_num"] > 0)
            & (grp["ask_num"] > 0)
            & (grp["ask_num"] > grp["bid_num"])
        )
        mid_ok = int(valid_mask.sum())

        warns: list[str] = []
        if mid_ok == 0:
            warns.append("No valid bid/ask pairs — mid not computable")
        elif mid_ok < n * 0.5:
            warns.append(f"Low mid coverage: {mid_ok}/{n} rows")

        date_col = pd.to_datetime(grp["date"]).dt.date
        date_first = date_col.min() if not date_col.empty else None
        date_last = date_col.max() if not date_col.empty else None

        records.append(
            RicCoverage(
                ric=str(ric),
                strike=decode_strike_fn(str(ric)),
                total_rows=n,
                bid_available=bid_ok,
                ask_available=ask_ok,
                mid_available=mid_ok,
                iv_lseg_available=0,
                history_days=int(grp["date"].nunique()),
                date_first=date_first,
                date_last=date_last,
                bid_coverage_pct=round(bid_ok / max(1, n) * 100, 1),
                ask_coverage_pct=round(ask_ok / max(1, n) * 100, 1),
                warnings=warns,
            )
        )

    return sorted(records, key=lambda r: (r.strike or 0.0))


def build_coverage_by_field(ric_coverages: list[RicCoverage]) -> list[FieldCoverage]:
    """Summarise which fields are available across all RICs."""
    n = len(ric_coverages)
    if n == 0:
        return []

    def _pct(count: int) -> float:
        return round(count / max(1, n) * 100, 1)

    bid_n = sum(1 for r in ric_coverages if r.bid_available > 0)
    ask_n = sum(1 for r in ric_coverages if r.ask_available > 0)
    mid_n = sum(1 for r in ric_coverages if r.mid_available > 0)
    iv_lseg_n = sum(1 for r in ric_coverages if r.iv_lseg_available > 0)

    return [
        FieldCoverage("BID", n, bid_n, _pct(bid_n), "Daily close bid price from LSEG"),
        FieldCoverage("ASK", n, ask_n, _pct(ask_n), "Daily close ask price from LSEG"),
        FieldCoverage(
            "MID", n, mid_n, _pct(mid_n),
            "Derived (BID+ASK)/2 — valid when both bid and ask are positive and bid < ask",
        ),
        FieldCoverage(
            "IV (LSEG direct)", n, iv_lseg_n, _pct(iv_lseg_n),
            "TR.ImpliedVolatility — NOT available under current LSEG entitlement (EMPTY/ERROR)",
        ),
        FieldCoverage(
            "IV (BS bisection fallback)", n, mid_n, _pct(mid_n),
            "Black-Scholes IV solved from market mid — available whenever MID is available",
        ),
        FieldCoverage(
            "Greeks (LSEG direct)", n, 0, 0.0,
            "TR.Delta / TR.Gamma / TR.Vega — NOT available under current LSEG entitlement",
        ),
        FieldCoverage(
            "Greeks (BS fallback)", n, mid_n, _pct(mid_n),
            "Black-Scholes Greeks from BS-bisection IV — always used as primary engine",
        ),
    ]


def build_manifest(
    ric_coverages: list[RicCoverage],
    field_coverages: list[FieldCoverage],
    source: str,
    audit_date: date,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-serialisable audit manifest."""
    n = len(ric_coverages)
    mid_n = sum(1 for r in ric_coverages if r.mid_available > 0)
    all_days = [r.history_days for r in ric_coverages if r.history_days > 0]

    manifest: dict[str, Any] = {
        "audit_date": str(audit_date),
        "data_source": source,
        "rics_tested": n,
        "rics_with_bid": sum(1 for r in ric_coverages if r.bid_available > 0),
        "rics_with_ask": sum(1 for r in ric_coverages if r.ask_available > 0),
        "rics_with_mid": mid_n,
        "rics_with_lseg_iv": 0,
        "rics_with_bs_fallback_iv": mid_n,
        "avg_history_days": round(sum(all_days) / max(1, len(all_days)), 1),
        "min_history_days": min(all_days, default=0),
        "max_history_days": max(all_days, default=0),
        "lseg_greeks_available": False,
        "lseg_iv_available": False,
        "fallback_rule": "Black-Scholes IV bisection from market mid (bid+ask)/2",
        "fallback_applies": "Always — LSEG historical Greeks unavailable under current entitlement",
        "warnings": [
            "LSEG historical option Greeks (TR.Delta, TR.ImpliedVolatility) returned EMPTY/ERROR",
            "All Greeks computed via Black-Scholes fallback from LSEG market mid",
            "SPY calls only (Jan 2027 expiry) — no puts confirmed in current RIC audit",
            "Snapshot Greeks from LSEG audit were single-row only; not used in backtest",
        ],
    }

    if extra:
        manifest.update(extra)

    return manifest


def build_readable_summary(
    ric_coverages: list[RicCoverage],
    field_coverages: list[FieldCoverage],
    manifest: dict[str, Any],
) -> str:
    """Build a human-readable Markdown quality summary."""
    n = len(ric_coverages)
    mid_n = manifest.get("rics_with_mid", 0)
    avg_days = manifest.get("avg_history_days", 0)

    lines = [
        "# LSEG Option Universe — Data Quality Report",
        "",
        f"**Audit date:** {manifest.get('audit_date', 'N/A')}  ",
        f"**Data source:** {manifest.get('data_source', 'N/A')}  ",
        f"**RICs tested:** {n}  ",
        f"**RICs with valid mid price:** {mid_n} ({mid_n / max(1, n) * 100:.0f}%)  ",
        f"**Average history per RIC:** {avg_days:.0f} trading days  ",
        "",
        "## Field coverage",
        "",
        "| Field | RICs with data | Coverage | Notes |",
        "|---|---|---|---|",
    ]

    for fc in field_coverages:
        lines.append(
            f"| {fc.field} | {fc.rics_with_any_data} / {fc.total_rics}"
            f" | {fc.coverage_pct:.0f}% | {fc.notes} |"
        )

    lines += [
        "",
        "## Greeks and IV sourcing",
        "",
        "| Source | Available | Notes |",
        "|---|---|---|",
        "| LSEG direct IV (TR.ImpliedVolatility) | No | EMPTY/ERROR under current entitlement |",
        "| LSEG direct Greeks (TR.Delta etc.) | No | EMPTY/ERROR under current entitlement |",
        "| Black-Scholes IV bisection from mid | Yes | Primary engine — always used |",
        "| Black-Scholes Greeks from BS-IV | Yes | Derived from bisection IV |",
        "| Rolling realised-vol fallback | Yes (fallback) | Used when BS bisection fails |",
        "",
        "## Fallback rules",
        "",
        "1. **Primary:** BS bisection solves IV from LSEG market mid → compute all Greeks",
        "2. **Fallback:** If bisection fails → rolling realised vol (flagged `iv_source=realized_vol_fallback`)",
        "3. **Exclusion:** If both fail → contract excluded that day",
        "",
        "Fallback rate > 30% triggers `LOW CONFIDENCE` flag in validation report.",
        "",
        "## Warnings",
        "",
    ]

    for w in manifest.get("warnings", []):
        lines.append(f"- {w}")

    lines += [
        "",
        "## Per-RIC summary (first 20 RICs by strike)",
        "",
        "| RIC | Strike | History days | Mid pairs | Bid% | Ask% | Notes |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in ric_coverages[:20]:
        note = "; ".join(r.warnings) if r.warnings else "OK"
        lines.append(
            f"| {r.ric} | ${r.strike:.0f} | {r.history_days} | {r.mid_available}"
            f" | {r.bid_coverage_pct:.0f}% | {r.ask_coverage_pct:.0f}% | {note} |"
        )

    if len(ric_coverages) > 20:
        lines.append(f"| _(+{len(ric_coverages) - 20} more RICs)_ | | | | | | |")

    return "\n".join(lines) + "\n"


def write_audit_outputs(
    ric_coverages: list[RicCoverage],
    field_coverages: list[FieldCoverage],
    manifest: dict[str, Any],
    output_dir: Path,
) -> None:
    """Write coverage_by_ric.csv, coverage_by_field.csv, manifest.json, readable_summary.md."""
    output_dir.mkdir(parents=True, exist_ok=True)

    ric_df = pd.DataFrame(
        [
            {
                "ric": r.ric,
                "strike": r.strike,
                "total_rows": r.total_rows,
                "bid_available": r.bid_available,
                "ask_available": r.ask_available,
                "mid_available": r.mid_available,
                "iv_lseg_available": r.iv_lseg_available,
                "history_days": r.history_days,
                "date_first": str(r.date_first) if r.date_first else None,
                "date_last": str(r.date_last) if r.date_last else None,
                "bid_coverage_pct": r.bid_coverage_pct,
                "ask_coverage_pct": r.ask_coverage_pct,
                "warnings": "; ".join(r.warnings),
            }
            for r in ric_coverages
        ]
    )
    ric_df.to_csv(output_dir / "coverage_by_ric.csv", index=False)

    field_df = pd.DataFrame(
        [
            {
                "field": f.field,
                "total_rics": f.total_rics,
                "rics_with_data": f.rics_with_any_data,
                "coverage_pct": f.coverage_pct,
                "notes": f.notes,
            }
            for f in field_coverages
        ]
    )
    field_df.to_csv(output_dir / "coverage_by_field.csv", index=False)

    with open(output_dir / "manifest.json", "w", encoding="utf-8") as fp:
        json.dump(manifest, fp, indent=2, default=str)

    summary = build_readable_summary(ric_coverages, field_coverages, manifest)
    (output_dir / "readable_summary.md").write_text(summary, encoding="utf-8")
