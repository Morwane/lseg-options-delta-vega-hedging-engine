"""
Build LSEG option coverage audit + Claude handoff.

Goal
----
Automatically discover/test many SPY option RICs and generate:
- coverage_by_ric.csv
- coverage_by_field.csv
- normalized_snapshot.csv
- history_coverage_summary.csv
- config/lseg_option_coverage_rics.yaml
- CLAUDE_OPTION_HISTORY_HANDOFF.md

This script:
- does NOT call IBKR
- does NOT place orders
- does NOT assume long history exists
- only audits LSEG option data availability

Run:
python scripts/build_lseg_option_history_handoff.py --max-rics 120 --history-count 30

Optional:
python scripts/build_lseg_option_history_handoff.py --manual-rics SPYD292650000.U SPYP292650000.U SPYD302672000.U SPYP302672000.U
"""

from __future__ import annotations

import argparse
import json
import math
import re
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = "SPY"

CHAIN_CANDIDATES = [
    "0#SPY*.U",
    "0#SPY*.P",
    "0#SPY*.O",
    "0#SPY*.N",
    "0#SPY*.A",
]

SEED_RICS = [
    # Confirmed by your previous Python audit:
    "SPYD292650000.U",
    "SPYP292650000.U",
]

SNAPSHOT_FIELDS = [
    "BID",
    "ASK",
    "CF_LAST",
    "CF_BID",
    "CF_ASK",
    "CF_CLOSE",
    "TR.BIDPRICE",
    "TR.ASKPRICE",
    "TR.PriceClose",
    "TR.ImpliedVolatility",
    "TR.Delta",
    "TR.Gamma",
    "TR.Vega",
    "TR.Theta",
    "TR.Rho",
    "TR.OPWCloseDelta",
    "TR.OPWCloseGamma",
    "TR.OPWCloseVega",
    "TR.OPWCloseTheta",
    "TR.OPWCloseRho",
    "TR.StrikePrice",
    "TR.ExpirationDate",
    "TR.OptionType",
    "TR.InstrumentDescription",
]

HISTORY_FIELDS = [
    "BID",
    "ASK",
    "TR.BIDPRICE",
    "TR.ASKPRICE",
    "TR.ImpliedVolatility",
    "TR.Delta",
    "TR.Gamma",
    "TR.Vega",
    "TR.Theta",
    "TR.Rho",
]


@dataclass
class FieldResult:
    ric: str
    source: str
    field: str
    status: str
    rows: int
    non_null: int
    first_date: str
    last_date: str
    sample_value: str
    error: str = ""


def ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_str(x: Any, limit: int = 300) -> str:
    try:
        s = str(x)
    except Exception:
        s = repr(x)
    return s.replace("\n", " ").replace("\r", " ")[:limit]


def clean_num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except Exception:
        pass
    if isinstance(x, str):
        x = x.strip().replace(",", "")
        if x in {"", "<NA>", "NA", "N/A", "None", "nan"}:
            return None
    try:
        y = float(x)
    except Exception:
        return None
    return y if math.isfinite(y) else None


def normalize_iv(x: float | None) -> float | None:
    if x is None:
        return None
    return x / 100.0 if x > 3.0 else x


def flatten(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [" | ".join(str(v) for v in c if str(v) not in {"", "None"}) for c in out.columns]
    else:
        out.columns = [str(c) for c in out.columns]
    return out


def first_value(df: pd.DataFrame) -> Any:
    if df is None or df.empty:
        return None
    f = flatten(df)
    for col in f.columns:
        if str(col).lower() in {"instrument", "date", "ric"}:
            continue
        s = f[col].dropna()
        if len(s):
            return s.iloc[-1]
    return None


def date_range(df: pd.DataFrame) -> tuple[str, str]:
    if df is None or df.empty:
        return "", ""
    try:
        idx = pd.to_datetime(df.index, errors="coerce")
        idx = idx[~pd.isna(idx)]
        if len(idx) == 0:
            return "", ""
        return str(idx.min().date()), str(idx.max().date())
    except Exception:
        return "", ""


def non_null(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return int(flatten(df).notna().sum().sum())


def extract_ric_strings(obj: Any) -> list[str]:
    text = safe_str(obj, 200000)
    found = re.findall(r"\bSPY[A-Z0-9]{5,}\.U\b", text)
    return sorted(set(found))


def import_lseg():
    import lseg.data as ld
    return ld


def try_get_data(ld, universe: list[str] | str, fields: list[str]) -> pd.DataFrame:
    raw = ld.get_data(universe=universe if isinstance(universe, list) else [universe], fields=fields)
    if isinstance(raw, tuple):
        raw = raw[0]
    if not isinstance(raw, pd.DataFrame):
        raise ValueError(f"Non-DataFrame response: {type(raw)}")
    return raw


def try_get_history(ld, ric: str, field: str, count: int) -> pd.DataFrame:
    raw = ld.get_history(universe=[ric], fields=[field], interval="daily", count=count)
    if not isinstance(raw, pd.DataFrame):
        raise ValueError(f"Non-DataFrame response: {type(raw)}")
    return raw


def discover_rics(ld, manual_rics: list[str], max_rics: int) -> list[str]:
    candidates = set(SEED_RICS)
    candidates.update(manual_rics)

    print("\n=== DISCOVERING OPTION RICS ===")

    for chain in CHAIN_CANDIDATES:
        print(f"Testing chain candidate: {chain}")
        for fields in [["TR.RIC"], ["RIC"], ["TR.InstrumentDescription"], ["CF_NAME"]]:
            try:
                df = try_get_data(ld, chain, fields)
                found = []
                for _, row in flatten(df).iterrows():
                    found.extend(extract_ric_strings(row.to_dict()))
                for col in flatten(df).columns:
                    found.extend(extract_ric_strings(col))
                if found:
                    print(f"  Found {len(set(found))} RICs via {fields}")
                    candidates.update(found)
            except Exception as e:
                print(f"  {fields} failed: {safe_str(e, 120)}")

    cleaned = []
    for r in sorted(candidates):
        if re.match(r"^SPY[A-Z0-9]+\.U$", r):
            cleaned.append(r)

    return cleaned[:max_rics]


def audit_snapshot(ld, rics: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    field_rows: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []

    print("\n=== SNAPSHOT AUDIT ===")

    for i, ric in enumerate(rics, 1):
        print(f"[{i}/{len(rics)}] Snapshot {ric}")
        values: dict[str, Any] = {}

        for field in SNAPSHOT_FIELDS:
            try:
                df = try_get_data(ld, ric, [field])
                status = "OK" if not df.empty else "EMPTY"
                value = first_value(df)
                result = FieldResult(
                    ric=ric,
                    source="get_data",
                    field=field,
                    status=status,
                    rows=len(df),
                    non_null=non_null(df),
                    first_date="",
                    last_date="",
                    sample_value=safe_str(value),
                    error="",
                )
                values[field] = value
            except Exception as e:
                result = FieldResult(
                    ric=ric,
                    source="get_data",
                    field=field,
                    status="ERROR",
                    rows=0,
                    non_null=0,
                    first_date="",
                    last_date="",
                    sample_value="",
                    error=safe_str(e),
                )
                values[field] = None

            field_rows.append(asdict(result))

        bid = clean_num(values.get("BID")) or clean_num(values.get("CF_BID")) or clean_num(values.get("TR.BIDPRICE"))
        ask = clean_num(values.get("ASK")) or clean_num(values.get("CF_ASK")) or clean_num(values.get("TR.ASKPRICE"))
        last = clean_num(values.get("CF_LAST"))
        close = clean_num(values.get("CF_CLOSE")) or clean_num(values.get("TR.PriceClose"))
        iv_raw = clean_num(values.get("TR.ImpliedVolatility"))
        iv = normalize_iv(iv_raw)

        delta = clean_num(values.get("TR.Delta")) or clean_num(values.get("TR.OPWCloseDelta"))
        gamma = clean_num(values.get("TR.Gamma")) or clean_num(values.get("TR.OPWCloseGamma"))
        vega = clean_num(values.get("TR.Vega")) or clean_num(values.get("TR.OPWCloseVega"))
        theta = clean_num(values.get("TR.Theta")) or clean_num(values.get("TR.OPWCloseTheta"))
        rho = clean_num(values.get("TR.Rho")) or clean_num(values.get("TR.OPWCloseRho"))

        mid = (bid + ask) / 2 if bid is not None and ask is not None else close or last

        option_side = "UNKNOWN"
        if delta is not None:
            if delta > 0.05:
                option_side = "CALL_LIKE"
            elif delta < -0.05:
                option_side = "PUT_LIKE"
            else:
                option_side = "NEAR_ZERO_DELTA"

        warnings = []
        if bid is None:
            warnings.append("missing_bid")
        if ask is None:
            warnings.append("missing_ask")
        if iv is None:
            warnings.append("missing_iv")
        if delta is None:
            warnings.append("missing_delta")
        if iv_raw is not None and iv_raw != iv:
            warnings.append("iv_percent_normalized")

        normalized.append(
            {
                "ric": ric,
                "option_side_inferred": option_side,
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "last": last,
                "close": close,
                "implied_volatility_raw": iv_raw,
                "implied_volatility_decimal": iv,
                "delta": delta,
                "gamma": gamma,
                "vega": vega,
                "theta": theta,
                "rho": rho,
                "strike_field_raw": safe_str(values.get("TR.StrikePrice")),
                "expiry_field_raw": safe_str(values.get("TR.ExpirationDate")),
                "option_type_field_raw": safe_str(values.get("TR.OptionType")),
                "description": safe_str(values.get("TR.InstrumentDescription")),
                "warnings": "|".join(warnings),
            }
        )

    return pd.DataFrame(field_rows), pd.DataFrame(normalized)


def audit_history(ld, rics: list[str], count: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    print("\n=== HISTORY AUDIT ===")

    for i, ric in enumerate(rics, 1):
        print(f"[{i}/{len(rics)}] History {ric}")
        for field in HISTORY_FIELDS:
            try:
                df = try_get_history(ld, ric, field, count)
                status = "OK" if not df.empty else "EMPTY"
                first, last = date_range(df)
                result = FieldResult(
                    ric=ric,
                    source="get_history",
                    field=field,
                    status=status,
                    rows=len(df),
                    non_null=non_null(df),
                    first_date=first,
                    last_date=last,
                    sample_value=safe_str(first_value(df)),
                    error="",
                )
            except Exception as e:
                result = FieldResult(
                    ric=ric,
                    source="get_history",
                    field=field,
                    status="ERROR",
                    rows=0,
                    non_null=0,
                    first_date="",
                    last_date="",
                    sample_value="",
                    error=safe_str(e),
                )

            rows.append(asdict(result))

    return pd.DataFrame(rows)


def build_summaries(snapshot_norm: pd.DataFrame, hist: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    coverage_by_ric = []

    for ric, g in hist.groupby("ric"):
        bid_rows = int(g[(g["field"].isin(["BID", "TR.BIDPRICE"])) & (g["status"] == "OK")]["rows"].max() or 0)
        ask_rows = int(g[(g["field"].isin(["ASK", "TR.ASKPRICE"])) & (g["status"] == "OK")]["rows"].max() or 0)
        greek_rows = int(g[(g["field"].isin(["TR.Delta", "TR.Gamma", "TR.Vega", "TR.Theta", "TR.Rho"])) & (g["status"] == "OK")]["rows"].max() or 0)

        snap = snapshot_norm[snapshot_norm["ric"] == ric]
        coverage_by_ric.append(
            {
                "ric": ric,
                "snapshot_bidask_ok": bool((snap["bid"].notna() & snap["ask"].notna()).any()) if not snap.empty else False,
                "snapshot_iv_ok": bool(snap["implied_volatility_decimal"].notna().any()) if not snap.empty else False,
                "snapshot_greeks_ok": bool(snap[["delta", "gamma", "vega", "theta"]].notna().all(axis=1).any()) if not snap.empty else False,
                "option_side_inferred": snap["option_side_inferred"].iloc[0] if not snap.empty else "UNKNOWN",
                "bid_history_rows": bid_rows,
                "ask_history_rows": ask_rows,
                "greek_history_rows": greek_rows,
                "short_history_confirmed": bid_rows >= 5 and ask_rows >= 5,
                "long_history_confirmed": bid_rows >= 20 and ask_rows >= 20,
            }
        )

    by_ric = pd.DataFrame(coverage_by_ric)

    by_field = (
        hist.assign(ok=hist["status"].eq("OK") & hist["rows"].gt(0))
        .groupby("field")
        .agg(
            rics_tested=("ric", "nunique"),
            rics_ok=("ok", "sum"),
            max_rows=("rows", "max"),
            median_rows=("rows", "median"),
        )
        .reset_index()
    )

    manifest = {
        "generated_at_utc": utc_now(),
        "rics_tested": int(len(snapshot_norm)),
        "snapshot_bidask_confirmed_count": int(by_ric["snapshot_bidask_ok"].sum()) if not by_ric.empty else 0,
        "snapshot_iv_confirmed_count": int(by_ric["snapshot_iv_ok"].sum()) if not by_ric.empty else 0,
        "snapshot_greeks_confirmed_count": int(by_ric["snapshot_greeks_ok"].sum()) if not by_ric.empty else 0,
        "short_history_confirmed_count": int(by_ric["short_history_confirmed"].sum()) if not by_ric.empty else 0,
        "long_history_confirmed_count": int(by_ric["long_history_confirmed"].sum()) if not by_ric.empty else 0,
        "call_like_count": int((by_ric["option_side_inferred"] == "CALL_LIKE").sum()) if not by_ric.empty else 0,
        "put_like_count": int((by_ric["option_side_inferred"] == "PUT_LIKE").sum()) if not by_ric.empty else 0,
    }

    verdicts = []
    if manifest["snapshot_bidask_confirmed_count"] >= 10:
        verdicts.append("REAL_OPTION_SNAPSHOT_CONFIRMED")
    if manifest["call_like_count"] > 0 and manifest["put_like_count"] > 0:
        verdicts.append("CALL_PUT_COVERAGE_CONFIRMED")
    if manifest["short_history_confirmed_count"] >= 10:
        verdicts.append("SHORT_HISTORY_CONFIRMED")
    if manifest["long_history_confirmed_count"] >= 10:
        verdicts.append("LONG_HISTORY_CONFIRMED")
    else:
        verdicts.append("LONG_HISTORY_NOT_CONFIRMED")

    manifest["verdicts"] = verdicts
    return by_ric, by_field, manifest


def write_yaml_rics(path: Path, rics: list[str]) -> None:
    lines = ["rics:"]
    for r in rics:
        lines.append(f"  - {r}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_handoff(path: Path, manifest: dict[str, Any], out_dir: Path) -> None:
    verdicts = "\n".join([f"- {v}" for v in manifest["verdicts"]])
    text = f"""# Claude Handoff — LSEG SPY Option Historical Coverage Audit

Generated: `{manifest["generated_at_utc"]}`

## Project

Automatic Delta Hedging with Interactive Brokers API.

## Important result

We audited LSEG SPY option RIC coverage across a larger candidate set.

## Verdicts

{verdicts}

## Metrics

- RICs tested: `{manifest["rics_tested"]}`
- Snapshot bid/ask confirmed: `{manifest["snapshot_bidask_confirmed_count"]}`
- Snapshot IV confirmed: `{manifest["snapshot_iv_confirmed_count"]}`
- Snapshot Greeks confirmed: `{manifest["snapshot_greeks_confirmed_count"]}`
- Short history confirmed: `{manifest["short_history_confirmed_count"]}`
- Long history confirmed: `{manifest["long_history_confirmed_count"]}`
- Call-like options: `{manifest["call_like_count"]}`
- Put-like options: `{manifest["put_like_count"]}`

## Output folder

`{out_dir}`

Files:
- `discovered_rics.csv`
- `normalized_snapshot.csv`
- `snapshot_field_coverage.csv`
- `history_field_coverage.csv`
- `coverage_by_ric.csv`
- `coverage_by_field.csv`
- `manifest.json`
- `config/lseg_option_coverage_rics.yaml`

## Implementation instruction for Claude

Use this audit to decide the next phase.

If `LONG_HISTORY_CONFIRMED` appears:
- implement a real historical listed-options backtest only for the RIC universe with confirmed bid/ask history;
- use no look-ahead;
- choose contracts using rules available at the decision date;
- include transaction costs from bid/ask or bps fallback;
- document coverage limitations.

If `LONG_HISTORY_NOT_CONFIRMED` appears:
- do not implement a long historical listed-options backtest yet;
- first productionize the real LSEG daily hedge engine;
- keep long-backtest work behind a clearly named experimental script.

Safety:
- no IBKR live trading;
- no order placement;
- paper execution only in a later explicit phase with --paper-execute and terminal confirmation.
"""
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rics", type=int, default=120)
    parser.add_argument("--history-count", type=int, default=30)
    parser.add_argument("--manual-rics", nargs="*", default=[])
    args = parser.parse_args()

    out_dir = Path("outputs/audits") / f"lseg_option_history_handoff_{ts()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    Path("config").mkdir(exist_ok=True)

    print("=" * 90)
    print("LSEG OPTION HISTORY HANDOFF BUILDER")
    print("=" * 90)
    print(f"Output: {out_dir}")

    errors = []

    try:
        ld = import_lseg()
        ld.open_session()

        rics = discover_rics(ld, args.manual_rics, args.max_rics)
        if not rics:
            raise RuntimeError("No option RICs discovered. Add --manual-rics copied from Workspace.")

        pd.DataFrame({"ric": rics}).to_csv(out_dir / "discovered_rics.csv", index=False)
        write_yaml_rics(Path("config/lseg_option_coverage_rics.yaml"), rics)

        snapshot_fields, snapshot_norm = audit_snapshot(ld, rics)
        history_fields = audit_history(ld, rics, args.history_count)

        by_ric, by_field, manifest = build_summaries(snapshot_norm, history_fields)

        snapshot_fields.to_csv(out_dir / "snapshot_field_coverage.csv", index=False)
        snapshot_norm.to_csv(out_dir / "normalized_snapshot.csv", index=False)
        history_fields.to_csv(out_dir / "history_field_coverage.csv", index=False)
        by_ric.to_csv(out_dir / "coverage_by_ric.csv", index=False)
        by_field.to_csv(out_dir / "coverage_by_field.csv", index=False)

        with open(out_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, default=str)

        write_handoff(Path("CLAUDE_OPTION_HISTORY_HANDOFF.md"), manifest, out_dir)

        print("\n" + "=" * 90)
        print("FINAL VERDICTS")
        print("=" * 90)
        for v in manifest["verdicts"]:
            print("-", v)
        print("\nClaude handoff written to: CLAUDE_OPTION_HISTORY_HANDOFF.md")
        print(f"Audit files saved to: {out_dir}")
        return 0

    except Exception as e:
        errors.append({"error": safe_str(e, 2000), "traceback": traceback.format_exc()})
        with open(out_dir / "errors.json", "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2)
        print("FAILED:", safe_str(e, 1000))
        print(f"Errors saved to: {out_dir / 'errors.json'}")
        return 1

    finally:
        try:
            ld.close_session()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
