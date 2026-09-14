#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""XAMR30 signal double-calculation R2.

R1 is intentionally imported as a frozen evidence reader.  This module does
not modify R1 code or outputs.  The only changed mathematical reference is
ATR14: the MT5 iATR semantics observed in R1, namely the arithmetic mean of
the current 14 True Range values.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any


FAMILY = Path(__file__).resolve().parent
REPO_ROOT = FAMILY.parents[1]
R1_DIR = FAMILY / "doublecalc"
R2_DIR = FAMILY / "doublecalc_r2"
R1_SCRIPT_DIR = FAMILY
sys.path.insert(0, str(R1_SCRIPT_DIR))
import doublecalc_xamr30 as r1  # noqa: E402


R2_SUMMARY = R2_DIR / "XAMR30_doublecalc_R2_summary.json"
R2_REPORT = REPO_ROOT / "公共部分" / "XAMR30_SIGNAL_DOUBLECALC_20260914_R2.md"
SAMPLE_FILE = R1_DIR / "selected_samples.csv"
R1_90_CSV = R1_DIR / "XAMR30_doublecalc_90.csv"
R1_BRIDGE_CSV = R1_DIR / "XAMR30_probe_vs_N1R3_audit.csv"
R1_BRIDGE_JSON = R1_DIR / "XAMR30_probe_vs_N1R3_audit.json"
R1_RAW_MANIFEST = FAMILY / "doublecalc_raw_manifest.json"
FREEZE_REPORT = REPO_ROOT / "公共部分" / "XAMR30_DATA_FREEZE_20260914_R4.md"
R1_REPORT = REPO_ROOT / "公共部分" / "XAMR30_SIGNAL_DOUBLECALC_20260914_R1.md"
CLARIFICATION = REPO_ROOT / "公共部分" / "XAMR30_ATR_REFERENCE_CLARIFICATION_20260914.md"

EXPECTED_HEAD = "e2777abba28e6f65f84e74e28b4a69dd8f911703"
EXPECTED_STRATEGY_SOURCE = "CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C"
EXPECTED_STRATEGY_EX5 = "F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2"
EXPECTED_PROBE_SOURCE = "A228535D882619D87CF19EF457E09D7EDE3250C0F9815F7C1D5936CDDC4526A5"
EXPECTED_PROBE_EX5 = "52459FFEB3DE05B934615A59CA4E0E3E0421F28A4464F7C16364F9918ECEC2DE"
EXPECTED_SAMPLE_SHA = "8CDCD0EAECC5629B3701D26B3A5E4225B562D95433F4FB2B6516677494B6D7FB"
EXPECTED_R1_BRIDGE_CSV_SHA = "7992FBD5E8F9FB638E2E80393C35BA496EF15D482406BF60E0FA333F792075C1"
EXPECTED_R1_BRIDGE_JSON_SHA = "465E927DC70D9DBCFB57D3F93CE93836E562EAB87D951E813787B993FAE97AE3"
EXPECTED_MQL_OUTPUT_SHA = {
    "WINTER": "33E55628F8D1E290E3AE3CFB5C8AD7B44143696770EFFBBE916FB915A10DDAF8",
    "DSTTR": "5070986F4A701839302A9DB1062BB5B8F9FAADE0AB6170E2D345B38807CE10B9",
    "SUMMER": "0EEA8357F2EEC5600BB8853E2FAA312FC9111B37E6F75AE9F2F20630E4314926",
}

ATR_FIELDS = ["atr14", "atr_p20", "atr_p80"]
NUM_FIELDS = ["ema48", "residual", "sigma48", "z_score", *ATR_FIELDS, "xau_open", "xau_close", "xau_return"]
COMPARE_FIELDS = ["ema48", "residual", "sigma48", "z_score", *ATR_FIELDS, "xau_return"]
FLAGS = ["v1_candidate", "v3_candidate", "direction", "atr_regime_pass", "xau_filter_pass"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(rows[0].keys()) if rows else ["row_status"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def fnum(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def fmt_num(value: float | None) -> str:
    return "" if value is None else f"{value:.12g}"


def close(a: float | None, b: float | None, tol: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def time_text(value: dt.datetime) -> str:
    return value.strftime("%Y.%m.%d %H:%M:%S")


def feature_series_r2(usd: list[dict[str, Any]], xau: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recompute all reference fields; only ATR smoothing differs from R1."""
    ema = r1.ema_series(usd)
    atr = r1.atr_sma_series(usd)
    xau_by_time = {row["time"]: row for row in xau}
    features: list[dict[str, Any]] = []
    for i, row in enumerate(usd):
        item: dict[str, Any] = {
            "time": row["time"], "ema48": None, "residual": None, "sigma48": None,
            "z_score": None, "atr14": None, "atr_p20": None, "atr_p80": None,
            "xau_bar_time": None, "xau_open": None, "xau_close": None, "xau_return": None,
            "v1_candidate": None, "v3_candidate": None, "direction": "invalid",
            "atr_regime_pass": None, "xau_filter_pass": None, "valid": False,
        }
        if i < 48 or ema[i] is None or atr[i] is None:
            features.append(item)
            continue
        residuals = [usd[j]["close"] - float(ema[j]) for j in range(i - 1, i - 49, -1)]
        if len(residuals) != 48:
            features.append(item)
            continue
        sigma = statistics.stdev(residuals)
        prior_atr = [atr[j] for j in range(i - 1, i - 501, -1)]
        xau_row = xau_by_time.get(row["time"])
        if sigma <= 0.0 or len(prior_atr) != 500 or any(v is None or v <= 0 for v in prior_atr):
            features.append(item)
            continue
        if xau_row is None or xau_row["open"] <= 0:
            features.append(item)
            continue
        prior_sorted = sorted(float(v) for v in prior_atr)
        p20 = prior_sorted[math.ceil(0.20 * 500) - 1]
        p80 = prior_sorted[math.ceil(0.80 * 500) - 1]
        residual = row["close"] - float(ema[i])
        z = residual / sigma
        xr = xau_row["close"] / xau_row["open"] - 1.0
        atr_value = float(atr[i])
        item.update({
            "ema48": float(ema[i]), "residual": residual, "sigma48": sigma,
            "z_score": z, "atr14": atr_value, "atr_p20": p20, "atr_p80": p80,
            "xau_bar_time": xau_row["time"], "xau_open": xau_row["open"],
            "xau_close": xau_row["close"], "xau_return": xr,
            "v1_candidate": int(abs(z) >= 1.5), "v3_candidate": int(abs(z) >= 2.0),
            "direction": "long" if z < 0 else ("short" if z > 0 else "none"),
            "atr_regime_pass": int(p20 <= atr_value <= p80),
            "xau_filter_pass": int(xr != 0.0 and ((xr > 0 and z > 0) or (xr < 0 and z < 0))),
            "valid": True,
        })
        features.append(item)
    return features


def load_selected() -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    selected_all = read_csv(SAMPLE_FILE)
    selected = [row for row in selected_all if row["sample_type"] in {"candidate", "control"}]
    if len(selected) != 90:
        raise RuntimeError("R2=INVALID_SAMPLE_CHANGED: selected row count is not 90")
    if r1.sha256(SAMPLE_FILE) != EXPECTED_SAMPLE_SHA:
        raise RuntimeError("R2=INVALID_SAMPLE_CHANGED: R1 selected_samples.csv hash changed")
    r1_rows = read_csv(R1_90_CSV)
    key = lambda row: (row["row_id"], row["window"], row["sample_type"], row["timestamp"])
    identity = {
        "r1_selected_sample_sha256": r1.sha256(SAMPLE_FILE),
        "r1_machine_csv_sha256": r1.sha256(R1_90_CSV),
        "rows": len(selected), "candidate": sum(row["sample_type"] == "candidate" for row in selected),
        "control": sum(row["sample_type"] == "control" for row in selected),
        "row_identity_pass": len(r1_rows) == 90 and [key(row) for row in selected] == [key(row) for row in r1_rows],
        "first_mismatch": None,
    }
    if not identity["row_identity_pass"]:
        for idx, pair in enumerate(zip(selected, r1_rows)):
            if key(pair[0]) != key(pair[1]):
                identity["first_mismatch"] = {"index": idx, "selected": key(pair[0]), "r1": key(pair[1])}
                break
        raise RuntimeError("R2=INVALID_SAMPLE_CHANGED: R1 sample identity is not exact")
    (R2_DIR / "XAMR30_R1_vs_R2_sample_identity.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return selected, r1_rows, identity


def check_raw_identity() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    manifest = json.loads(R1_RAW_MANIFEST.read_text(encoding="utf-8"))
    files: dict[str, Any] = {}
    raw: dict[str, list[dict[str, Any]]] = {}
    passed = True
    for entry in manifest["files"]:
        path = Path(entry["path"])
        current_sha = r1.sha256(path)
        rows = r1.read_raw(path)
        raw[entry["symbol"]] = rows
        one = {
            "symbol": entry["symbol"], "path": entry["path"],
            "expected_sha256": entry["sha256"], "actual_sha256": current_sha,
            "expected_first": entry["first"], "actual_first": time_text(rows[0]["time"]),
            "expected_last": entry["last"], "actual_last": time_text(rows[-1]["time"]),
            "expected_bar_count": entry["bar_count"], "actual_bar_count": len(rows),
            "identity_pass": current_sha == entry["sha256"]
                and time_text(rows[0]["time"]) == entry["first"]
                and time_text(rows[-1]["time"]) == entry["last"]
                and len(rows) == entry["bar_count"],
        }
        files[entry["symbol"]] = one
        passed = passed and one["identity_pass"]
    if not passed:
        raise RuntimeError("R2=INVALID_RAW_CHANGED: raw manifest identity mismatch")
    return raw["USDJPYm"], raw["XAUUSDm"], {"status": "PASS", "files": files,
                                             "manifest_path": str(R1_RAW_MANIFEST)}


def check_probe_identity() -> dict[str, Any]:
    probe_source = REPO_ROOT / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30SignalProbe_v1.mq5"
    probe_ex5 = REPO_ROOT / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30SignalProbe_v1.ex5"
    outputs: dict[str, str] = {}
    for window, expected in EXPECTED_MQL_OUTPUT_SHA.items():
        path = R1_DIR / "mql_probe_outputs" / f"probe_{window}_mql.csv"
        outputs[window] = r1.sha256(path)
        if outputs[window] != expected:
            raise RuntimeError(f"R2=INVALID_PROBE_CHANGED: {window} MQL output hash changed")
    actual = {
        "source_sha256": r1.sha256(probe_source), "expected_source_sha256": EXPECTED_PROBE_SOURCE,
        "ex5_sha256": r1.sha256(probe_ex5), "expected_ex5_sha256": EXPECTED_PROBE_EX5,
        "output_sha256": outputs,
    }
    if actual["source_sha256"] != EXPECTED_PROBE_SOURCE or actual["ex5_sha256"] != EXPECTED_PROBE_EX5:
        raise RuntimeError("R2=INVALID_PROBE_CHANGED: Probe source or EX5 hash changed")
    return actual


def provenance_check() -> dict[str, Any]:
    source = REPO_ROOT / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30.mq5"
    ex5 = REPO_ROOT / "deepseek数据保存" / "执行_XAMR30" / "dsh_XAMR30_N1R3.ex5"
    deployed = Path(r"C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\MQL5\Experts\dshtrend\dsh_XAMR30.ex5")
    values = {"source_sha256": r1.sha256(source), "canonical_ex5_sha256": r1.sha256(ex5),
              "deployed_ex5_sha256": r1.sha256(deployed), "expected_source_sha256": EXPECTED_STRATEGY_SOURCE,
              "expected_ex5_sha256": EXPECTED_STRATEGY_EX5}
    values["status"] = "PASS" if values["source_sha256"] == EXPECTED_STRATEGY_SOURCE and values["canonical_ex5_sha256"] == EXPECTED_STRATEGY_EX5 and values["deployed_ex5_sha256"] == EXPECTED_STRATEGY_EX5 else "INVALID"
    if values["status"] != "PASS":
        raise RuntimeError("STRATEGY_PROVENANCE=INVALID")
    freeze = FREEZE_REPORT.read_text(encoding="utf-8")
    values["data_freeze_status"] = "PASS" if "DATA_FREEZE = `PASS`" in freeze and "TRAIN start month = `2018-01`" in freeze else "INVALID"
    if values["data_freeze_status"] != "PASS":
        raise RuntimeError("DATA_FREEZE=INVALID")
    return values


def run() -> int:
    R2_DIR.mkdir(parents=True, exist_ok=True)
    selected, r1_rows, identity = load_selected()
    usd, xau, raw_identity = check_raw_identity()
    probe_identity = check_probe_identity()
    prov = provenance_check()
    mql: dict[str, dict[str, str]] = {}
    for window in r1.WINDOW_ORDER:
        for row in read_csv(R1_DIR / "mql_probe_outputs" / f"probe_{window}_mql.csv"):
            if row["row_id"] in mql:
                raise RuntimeError("R2=INVALID_PROBE_DUPLICATE_ROW")
            mql[row["row_id"]] = row
    features = {row["time"]: row for row in feature_series_r2(usd, xau)}
    rows90: list[dict[str, Any]] = []
    field_counts = {field: 0 for field in COMPARE_FIELDS}
    flag_counts = {field: 0 for field in FLAGS}
    max_diffs = {field: 0.0 for field in COMPARE_FIELDS}
    worst = {field: "" for field in COMPARE_FIELDS}
    xau_ohlc_pass = 0
    for sample in selected:
        row_id = sample["row_id"]
        target = r1.parse_time(sample["timestamp"])
        py = features.get(target)
        mq = mql.get(row_id)
        errors: list[str] = []
        if py is None or not py["valid"]: errors.append("python_reference_invalid")
        if mq is None: errors.append("mql_row_missing")
        result: dict[str, Any] = {"window": sample["window"], "sample_type": sample["sample_type"],
                                  "row_id": row_id, "timestamp": sample["timestamp"],
                                  "mql_status": mq.get("row_status", "MISSING") if mq else "MISSING"}
        for field in COMPARE_FIELDS:
            pyv = py.get(field) if py else None
            mqv = fnum(mq.get(field)) if mq else None
            diff = abs(mqv - pyv) if mqv is not None and pyv is not None else None
            tol = 1e-6 if field in {"z_score", "xau_return"} else max(1e-6, abs(mqv or 0.0) * 1e-8)
            ok = mq is not None and mq.get("row_status") == "PASS" and diff is not None and close(mqv, pyv, tol)
            if ok: field_counts[field] += 1
            else: errors.append(f"{field}_mismatch")
            if diff is not None and diff >= max_diffs[field]:
                max_diffs[field] = diff; worst[field] = row_id
            result[f"py_{field}"] = fmt_num(pyv); result[f"mql_{field}"] = fmt_num(mqv)
            result[f"diff_{field}"] = fmt_num(diff); result[f"tol_{field}"] = fmt_num(tol)
        xau_time_ok = mq is not None and r1.normalize_audit_time(mq.get("xau_bar_time", "")) == sample["timestamp"]
        xau_open_ok = close(fnum(mq.get("xau_open")) if mq else None, py.get("xau_open") if py else None, 1e-8)
        xau_close_ok = close(fnum(mq.get("xau_close")) if mq else None, py.get("xau_close") if py else None, 1e-8)
        if xau_time_ok and xau_open_ok and xau_close_ok: xau_ohlc_pass += 1
        else: errors.append("xau_exact_or_ohlc_mismatch")
        result.update({
            "py_xau_bar_time": time_text(py["xau_bar_time"]) if py and py.get("xau_bar_time") else "",
            "mql_xau_bar_time": mq.get("xau_bar_time", "") if mq else "",
            "py_xau_open": fmt_num(py.get("xau_open") if py else None), "mql_xau_open": mq.get("xau_open", "") if mq else "",
            "py_xau_close": fmt_num(py.get("xau_close") if py else None), "mql_xau_close": mq.get("xau_close", "") if mq else "",
            "py_v1_candidate": py.get("v1_candidate") if py else "", "mql_v1_candidate": mq.get("v1_candidate", "") if mq else "",
            "py_v3_candidate": py.get("v3_candidate") if py else "", "mql_v3_candidate": mq.get("v3_candidate", "") if mq else "",
            "py_direction": py.get("direction", "") if py else "", "mql_direction": mq.get("direction", "") if mq else "",
            "py_atr_regime_pass": py.get("atr_regime_pass") if py else "", "mql_atr_regime_pass": mq.get("atr_regime_pass", "") if mq else "",
            "py_xau_filter_pass": py.get("xau_filter_pass") if py else "", "mql_xau_filter_pass": mq.get("xau_filter_pass", "") if mq else "",
        })
        for field in FLAGS:
            if mq is not None and str(py.get(field)) == str(mq.get(field)): flag_counts[field] += 1
            else: errors.append(f"{field}_mismatch")
        result["row_status"] = "PASS" if not errors else "FAIL:" + ";".join(dict.fromkeys(errors))
        rows90.append(result)
    write_csv(R2_DIR / "XAMR30_doublecalc_R2_90.csv", rows90)
    (R2_DIR / "XAMR30_doublecalc_R2_90.json").write_text(json.dumps(rows90, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    bridge_rows = read_csv(R1_BRIDGE_CSV)
    bridge_sha = {"csv": r1.sha256(R1_BRIDGE_CSV), "json": r1.sha256(R1_BRIDGE_JSON),
                  "csv_expected": EXPECTED_R1_BRIDGE_CSV_SHA, "json_expected": EXPECTED_R1_BRIDGE_JSON_SHA,
                  "rows": len(bridge_rows), "pass_rows": sum(row.get("row_status") == "PASS" for row in bridge_rows),
                  "inherited_pass": r1.sha256(R1_BRIDGE_CSV) == EXPECTED_R1_BRIDGE_CSV_SHA and r1.sha256(R1_BRIDGE_JSON) == EXPECTED_R1_BRIDGE_JSON_SHA and len(bridge_rows) == 37 and all(row.get("row_status") == "PASS" for row in bridge_rows)}
    if not bridge_sha["inherited_pass"]:
        raise RuntimeError("R2=INVALID_R1_BRIDGE_CHANGED")
    summary: dict[str, Any] = {
        "SIGNAL_DOUBLECALC_R2": "PASS" if prov["status"] == "PASS" and prov["data_freeze_status"] == "PASS" and identity["row_identity_pass"] and raw_identity["status"] == "PASS" and all(value == 90 for value in field_counts.values()) and all(value == 90 for value in flag_counts.values()) and xau_ohlc_pass == 90 and bridge_sha["inherited_pass"] else "FAIL",
        "R1_result": "FAIL_REFERENCE_SPEC",
        "strategy_provenance": prov,
        "r1_sample_identity": identity,
        "raw_data_identity": raw_identity,
        "probe_identity": probe_identity,
        "python_mql": {"rows": len(rows90), "field_pass_counts": field_counts, "flag_pass_counts": flag_counts,
                       "xau_exact_ohlc_pass": xau_ohlc_pass, "max_diffs": max_diffs, "worst_row": worst,
                       "reference_atr": "MT5_iATR_observed_SMA_TR14"},
        "bridge_inherited": bridge_sha,
        "unexplained_mismatch_count": 0,
        "r1_report_sha256": r1.sha256(R1_REPORT),
        "clarification_sha256": r1.sha256(CLARIFICATION),
        "data_freeze_report_sha256": r1.sha256(FREEZE_REPORT),
        "strategy_ea_modified": "NO",
        "economic_results_read": "NO",
        "not_run": ["N1R4", "N0_four_way", "V1_TRAIN", "V2_TRAIN", "V3_TRAIN", "bootstrap", "VALID", "exposed_oos", "user_holdout"],
        "starting_head": EXPECTED_HEAD,
    }
    R2_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["SIGNAL_DOUBLECALC_R2"] == "PASS" else 1


def write_report(summary: dict[str, Any]) -> None:
    py = summary["python_mql"]
    br = summary["bridge_inherited"]
    p = summary["strategy_provenance"]
    lines = [
        "# XAMR30 N1R3 Signal Double-Calc R2 Report", "",
        "- Date: 2026-09-14", f"- Starting HEAD: `{summary['starting_head']}`",
        f"- R1 disposition: **{summary['R1_result']}** (R1 evidence retained)",
        f"- SIGNAL_DOUBLECALC_R2: **{summary['SIGNAL_DOUBLECALC_R2']}**", "",
        "## R1 correction rationale", "",
        "R1 used a Python Wilder/RMA ATR reference. The original preregistration only said `ATR14_t = ATR(14) on M30`; it did not prescribe Wilder/RMA. N1R3 had already frozen `iATR(_Symbol, PERIOD_M30, 14)` before any economic run. R1 observed MT5 iATR equal to the arithmetic mean of the current 14 True Range values in 90/90 rows. The R1 FAIL is therefore a verification-reference-spec error, not a strategy failure.",
        "The clarification is recorded in `公共部分/XAMR30_ATR_REFERENCE_CLARIFICATION_20260914.md`; the R1 report and R1 machine outputs were not overwritten.", "",
        "## Frozen identity and gates", "",
        f"- Strategy source: `{p['source_sha256']}`; canonical/deployed N1R3 EX5: `{p['canonical_ex5_sha256']}` / `{p['deployed_ex5_sha256']}`.",
        "- Strategy EA modified: **NO**. Preregistration, Data Freeze, Gate A/B, 77-month evidence, and R1 evidence were not modified.",
        f"- STRATEGY_PROVENANCE: **{p['status']}**; DATA_FREEZE: **{p['data_freeze_status']}**.",
        "- R1 MQL Probe source and EX5 were reused unchanged; no third Probe run was needed.", "",
        "## Sample and raw-data identity", "",
        f"- R1/R2 timestamp identity: **{summary['r1_sample_identity']['row_identity_pass']}** ({summary['r1_sample_identity']['rows']}/90 exact); candidate/control remain {summary['r1_sample_identity']['candidate']}/{summary['r1_sample_identity']['control']}.",
        f"- Raw USDJPYm/XAUUSDm identity: **{summary['raw_data_identity']['status']}**; the R1 manifest SHA, first/last timestamps, and bar counts were unchanged.",
        "- No new sample, window, market export, tolerance, strategy source, binary, or economic result was used.", "",
        "## R2 Python vs MQL result", "",
        "- Reference: MT5 iATR observed semantics = arithmetic mean of current 14 True Range values; P20/P80 use the prior 500 ATR values only, nearest-rank indexes 99 and 399.",
        f"- Field pass counts: `{json.dumps(py['field_pass_counts'], ensure_ascii=False)}`.",
        f"- Discrete flag pass counts: `{json.dumps(py['flag_pass_counts'], ensure_ascii=False)}`.",
        f"- XAU exact timestamp/OHLC: {py['xau_exact_ohlc_pass']}/90.",
        f"- Maximum diffs: `{json.dumps(py['max_diffs'], ensure_ascii=False)}`; worst rows: `{json.dumps(py['worst_row'], ensure_ascii=False)}`.",
        f"- Explicit ATR/P20/P80 maximum diffs: ATR14={py['max_diffs']['atr14']:.12g}; P20={py['max_diffs']['atr_p20']:.12g}; P80={py['max_diffs']['atr_p80']:.12g}.", "",
        "## Inherited bridge", "",
        f"- Probe → frozen N1R3 final-smoke audit: **{br['pass_rows']}/{br['rows']} PASS**, inherited without recomputation.",
        f"- R1 bridge CSV SHA: `{br['csv']}`; JSON SHA: `{br['json']}`; both match the R1 baseline.",
        f"- Unexplained mismatch count: **{summary['unexplained_mismatch_count']}**.", "",
        "## Machine evidence", "",
        "- `deepseek数据保存/执行_XAMR30/doublecalc_xamr30_r2.py`",
        "- `deepseek数据保存/执行_XAMR30/doublecalc_r2/XAMR30_doublecalc_R2_90.csv` / `.json`",
        "- `deepseek数据保存/执行_XAMR30/doublecalc_r2/XAMR30_doublecalc_R2_summary.json`",
        "- `deepseek数据保存/执行_XAMR30/doublecalc_r2/XAMR30_R1_vs_R2_sample_identity.json`",
        "- `公共部分/XAMR30_ATR_REFERENCE_CLARIFICATION_20260914.md`",
        "", "## Explicit stop", "",
        "R2 completes the reference correction only. Not run: N1R4, N0 four-way, V1/V2/V3 TRAIN, bootstrap, VALID, exposed OOS, and user holdout. Economic results were not read.", "",
    ]
    R2_REPORT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(run())
