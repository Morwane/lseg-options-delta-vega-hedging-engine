"""Audit the LSEG option universe for the confirmed SPY call RIC set.

Outputs (to outputs/audits/lseg_option_universe/):
    coverage_by_ric.csv     — per-RIC bid/ask/mid/IV availability
    coverage_by_field.csv   — per-field coverage across all RICs
    manifest.json           — machine-readable audit metadata
    readable_summary.md     — human-readable Markdown quality report

Usage
-----
# Offline / CI (synthetic mock data):
python scripts/audit_lseg_option_universe.py --mock

# Live LSEG:
python scripts/audit_lseg_option_universe.py

# Custom output directory:
python scripts/audit_lseg_option_universe.py --mock --output-dir outputs/audits/my_run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.lseg_option_loader import LsegLoaderConfig, load_lseg_option_data
from src.data.lseg_quality_report import (
    build_coverage_by_field,
    build_coverage_by_ric,
    build_manifest,
    write_audit_outputs,
)


DEFAULT_OUTPUT = ROOT / "outputs" / "audits" / "lseg_option_universe"
DEFAULT_RIC_CONFIG = ROOT / "config" / "lseg_option_coverage_rics.yaml"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Audit LSEG option universe: bid/ask/mid/IV coverage for all confirmed RICs."
    )
    p.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Use synthetic offline data (no LSEG connection required).",
    )
    p.add_argument(
        "--ric-config",
        type=Path,
        default=DEFAULT_RIC_CONFIG,
        help="Path to lseg_option_coverage_rics.yaml.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output directory (default: {DEFAULT_OUTPUT}).",
    )
    p.add_argument(
        "--history-count",
        type=int,
        default=35,
        help="Number of daily bars to fetch from LSEG (live mode only).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.ric_config.exists():
        print(f"[ERROR] RIC config not found: {args.ric_config}")
        return 1

    mode = "mock" if args.mock else "auto"
    print(f"[INFO] Mode: {mode}")
    print(f"[INFO] RIC config: {args.ric_config}")
    print(f"[INFO] Output dir: {args.output_dir}")

    # ── Load data ──────────────────────────────────────────────────────────────
    loader_config = LsegLoaderConfig(
        ric_config_path=args.ric_config,
        history_count=args.history_count,
        mode=mode,
    )

    print(f"\n[INFO] Loading option history...")
    load_result = load_lseg_option_data(loader_config)

    for w in load_result.warnings:
        print(f"[WARN] {w}")

    print(
        f"[INFO] Loaded {load_result.rics_with_data} RICs with data"
        f" ({load_result.rics_requested} requested)"
        f", {load_result.trading_days} trading days"
        f", source={load_result.source}"
    )

    if load_result.option_history.empty:
        print("[ERROR] No option history loaded — cannot build audit.")
        return 1

    # ── Build coverage statistics ──────────────────────────────────────────────
    print("\n[INFO] Computing coverage statistics...")
    ric_coverages = build_coverage_by_ric(load_result.option_history)
    field_coverages = build_coverage_by_field(ric_coverages)

    today = date.today()
    manifest = build_manifest(
        ric_coverages=ric_coverages,
        field_coverages=field_coverages,
        source=f"LSEG ({load_result.source})",
        audit_date=today,
        extra={
            "rics_requested": load_result.rics_requested,
            "spy_trading_days": load_result.trading_days,
            "history_count_requested": args.history_count,
            "mock_mode": args.mock,
        },
    )

    # ── Write outputs ──────────────────────────────────────────────────────────
    print(f"\n[INFO] Writing audit outputs to: {args.output_dir}")
    write_audit_outputs(ric_coverages, field_coverages, manifest, args.output_dir)

    # ── Console summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("LSEG OPTION UNIVERSE AUDIT — SUMMARY")
    print("=" * 64)
    print(f"RICs tested:              {manifest['rics_tested']}")
    print(f"RICs with bid data:       {manifest['rics_with_bid']}")
    print(f"RICs with ask data:       {manifest['rics_with_ask']}")
    print(f"RICs with valid mid:      {manifest['rics_with_mid']}")
    print(f"RICs with LSEG IV:        {manifest['rics_with_lseg_iv']}  (not available)")
    print(f"RICs with BS-fallback IV: {manifest['rics_with_bs_fallback_iv']}")
    print(f"Avg history days:         {manifest['avg_history_days']:.0f}")
    print(f"LSEG Greeks available:    {manifest['lseg_greeks_available']}")
    print(f"BS fallback rule:         {manifest['fallback_rule']}")

    print("\nField coverage:")
    for fc in field_coverages:
        print(f"  {fc.field:<35} {fc.coverage_pct:.0f}%  ({fc.rics_with_any_data}/{fc.total_rics} RICs)")

    if manifest.get("warnings"):
        print("\nWarnings:")
        for w in manifest["warnings"]:
            print(f"  - {w}")

    print("\nFiles written:")
    for fname in ["coverage_by_ric.csv", "coverage_by_field.csv", "manifest.json", "readable_summary.md"]:
        path = args.output_dir / fname
        print(f"  {path}")

    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
