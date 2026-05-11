"""Smoke tests for src/reporting/charts.py.

Tests verify charts run without error and produce files.
Missing-data paths (empty tmp dir) must also be handled gracefully.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.reporting.charts import (
    build_all_charts,
    chart_drawdown,
    chart_gamma_vega,
    chart_hedge_orders,
    chart_hedged_vs_unhedged_pnl,
    chart_ibkr_audit_summary,
    chart_lseg_audit_summary,
    chart_net_delta,
    chart_transaction_costs,
)

ROOT = Path(__file__).resolve().parent.parent
_REPORTS = ROOT / "outputs" / "reports"


# ---------------------------------------------------------------------------
# Graceful handling of missing data
# ---------------------------------------------------------------------------

class TestMissingDataGraceful:
    def test_all_charts_empty_dir_returns_empty_list(self, tmp_path):
        empty_reports = tmp_path / "reports"
        empty_reports.mkdir()
        images = tmp_path / "images"
        created = build_all_charts(empty_reports, images, silent=True)
        assert isinstance(created, list)
        # Static charts (ibkr, lseg) don't need CSV data — they may still be created
        # but no crash should occur
        for path in created:
            assert Path(path).exists()

    def test_pnl_chart_missing_csv_returns_none(self, tmp_path):
        result = chart_hedged_vs_unhedged_pnl(tmp_path, tmp_path)
        assert result is None

    def test_delta_chart_missing_csv_returns_none(self, tmp_path):
        result = chart_net_delta(tmp_path, tmp_path)
        assert result is None

    def test_orders_chart_missing_csv_returns_none(self, tmp_path):
        result = chart_hedge_orders(tmp_path, tmp_path)
        assert result is None

    def test_costs_chart_missing_csv_returns_none(self, tmp_path):
        result = chart_transaction_costs(tmp_path, tmp_path)
        assert result is None

    def test_drawdown_chart_missing_csv_returns_none(self, tmp_path):
        result = chart_drawdown(tmp_path, tmp_path)
        assert result is None

    def test_gamma_vega_chart_missing_csv_returns_none(self, tmp_path):
        result = chart_gamma_vega(tmp_path, tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# Static charts always succeed (no CSV needed)
# ---------------------------------------------------------------------------

class TestStaticCharts:
    def test_ibkr_audit_creates_file(self, tmp_path):
        result = chart_ibkr_audit_summary(tmp_path, tmp_path)
        assert result is not None
        assert Path(result).exists()
        assert Path(result).stat().st_size > 0

    def test_lseg_audit_creates_file(self, tmp_path):
        result = chart_lseg_audit_summary(tmp_path, tmp_path)
        assert result is not None
        assert Path(result).exists()
        assert Path(result).stat().st_size > 0

    def test_ibkr_audit_png_extension(self, tmp_path):
        result = chart_ibkr_audit_summary(tmp_path, tmp_path)
        assert result is not None
        assert result.endswith(".png")

    def test_lseg_audit_png_extension(self, tmp_path):
        result = chart_lseg_audit_summary(tmp_path, tmp_path)
        assert result is not None
        assert result.endswith(".png")


# ---------------------------------------------------------------------------
# Integration: build_all_charts against real report data
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not (_REPORTS / "real_historical_daily_hedge.csv").exists(),
    reason="Real backtest CSV not generated yet — run build_readme_outputs.py first",
)
class TestChartsWithRealData:
    def test_build_all_charts_returns_8(self, tmp_path):
        created = build_all_charts(_REPORTS, tmp_path, silent=True)
        assert len(created) == 8

    def test_all_files_exist(self, tmp_path):
        created = build_all_charts(_REPORTS, tmp_path, silent=True)
        for path in created:
            assert Path(path).exists(), f"Missing: {path}"

    def test_all_files_nonempty(self, tmp_path):
        created = build_all_charts(_REPORTS, tmp_path, silent=True)
        for path in created:
            assert Path(path).stat().st_size > 1_000, f"File too small: {path}"

    def test_expected_filenames_present(self, tmp_path):
        expected = {
            "hedged_vs_unhedged_pnl.png",
            "net_delta_before_after.png",
            "hedge_orders_by_underlying.png",
            "transaction_costs_over_time.png",
            "drawdown_hedged_vs_unhedged.png",
            "gamma_vega_monitoring.png",
            "ibkr_audit_summary.png",
            "lseg_audit_summary.png",
        }
        created = build_all_charts(_REPORTS, tmp_path, silent=True)
        names = {Path(p).name for p in created}
        assert names == expected

    def test_pnl_chart_creates_file(self, tmp_path):
        result = chart_hedged_vs_unhedged_pnl(_REPORTS, tmp_path)
        assert result is not None
        assert Path(result).exists()

    def test_net_delta_chart_creates_file(self, tmp_path):
        result = chart_net_delta(_REPORTS, tmp_path)
        assert result is not None
        assert Path(result).exists()

    def test_drawdown_chart_creates_file(self, tmp_path):
        result = chart_drawdown(_REPORTS, tmp_path)
        assert result is not None
        assert Path(result).exists()
