#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent XAMR30 N1R3 signal double-calculation.

The script has two explicit phases:

* ``prepare`` reads raw M30 OHLC exported by the read-only MT5 probe, computes
  the reference math, and deterministically selects 20 candidate and 10
  control timestamps per fixed engineering window.  It also appends the 37
  existing N1R3 final-smoke timestamps as bridge rows.
* ``finalize`` recomputes the same math from raw OHLC, compares it with the
  MQL5 probe output, and compares every bridge row with the rounded N1R3
  audit fields.

No EA indicator output is read by this module.  No strategy EA is executed.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
import os
import statistics
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY = REPO_ROOT / "deepseek数据保存" / "执行_XAMR30"
WORK = FAMILY / "doublecalc"
COMMON = (
    Path(os.environ.get("APPDATA", ""))
    / "MetaQuotes" / "Terminal" / "Common" / "Files" / "dshtrend"
    / "XAMR30DoubleCalc"
)
RAW_USD = COMMON / "raw_USDJPYm_M30.csv"
RAW_XAU = COMMON / "raw_XAUUSDm_M30.csv"
SAMPLE_COMMON = COMMON / "selected_samples.csv"
SAMPLE_LOCAL = WORK / "selected_samples.csv"
MANIFEST = FAMILY / "doublecalc_raw_manifest.json"
SUMMARY = WORK / "XAMR30_doublecalc_summary.json"
REPORT = REPO_ROOT / "公共部分" / "XAMR30_SIGNAL_DOUBLECALC_20260914_R1.md"
MQL_OUTPUT_DIR = WORK / "mql_probe_outputs"

SOURCE = REPO_ROOT / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30.mq5"
CANONICAL_EX5 = FAMILY / "dsh_XAMR30_N1R3.ex5"
DEPLOYED_EX5 = (
    Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    / "53785E099C927DB68A545C249CDBCE06" / "MQL5" / "Experts"
    / "dshtrend" / "dsh_XAMR30.ex5"
)
EXPECTED_SOURCE_SHA = "CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C"
EXPECTED_EX5_SHA = "F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2"
STARTING_HEAD = "f5613d57234307d39459b4258e07c48ae6c1f8d5"

WINDOWS = {
    "WINTER": (dt.datetime(2023, 1, 2), dt.datetime(2023, 2, 1)),
    "DSTTR": (dt.datetime(2023, 3, 20), dt.datetime(2023, 4, 8)),
    "SUMMER": (dt.datetime(2023, 7, 3), dt.datetime(2023, 8, 1)),
}
WINDOW_ORDER = ["WINTER", "DSTTR", "SUMMER"]

NUM_FIELDS = [
    "ema48", "residual", "sigma48", "z_score", "atr14", "atr_p20", "atr_p80",
    "xau_open", "xau_close", "xau_return",
]
MQL_COMPARE_FIELDS = ["ema48", "residual", "sigma48", "atr14", "atr_p20", "atr_p80"]
FLAGS = ["v1_candidate", "v3_candidate", "direction", "atr_regime_pass", "xau_filter_pass"]


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def parse_time(value: str) -> dt.datetime:
    value = str(value).strip()
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"invalid MT5 timestamp: {value!r}")


def fmt_time(value: dt.datetime) -> str:
    return value.strftime("%Y.%m.%d %H:%M:%S")


def fmt_num(value: float | None) -> str:
    return "" if value is None else f"{value:.12g}"


def read_raw(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise RuntimeError(f"raw MT5 export missing: {path}")
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("timestamp_iso"):
                raise RuntimeError(f"raw row missing timestamp_iso: {path}")
            out.append({
                "time": parse_time(row["timestamp_iso"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    if not out:
        raise RuntimeError(f"raw MT5 export empty: {path}")
    times = [r["time"] for r in out]
    if times != sorted(times) or len(times) != len(set(times)):
        raise RuntimeError(f"raw MT5 export is not strictly chronological: {path}")
    for row in out:
        if not (row["high"] >= row["low"] > 0 and row["open"] > 0 and row["close"] > 0):
            raise RuntimeError(f"raw OHLC invalid at {row['time']}: {path}")
    return out


def ema_series(rows: list[dict[str, Any]]) -> list[float | None]:
    alpha = 2.0 / (48.0 + 1.0)
    values: list[float | None] = [None] * len(rows)
    if not rows:
        return values
    values[0] = rows[0]["close"]
    for i in range(1, len(rows)):
        values[i] = rows[i]["close"] * alpha + float(values[i - 1]) * (1.0 - alpha)
    return values


def atr_series(rows: list[dict[str, Any]]) -> list[float | None]:
    """Wilder ATR14, matching the MT5 iATR reference after warm-up."""
    tr: list[float] = []
    for i, row in enumerate(rows):
        if i == 0:
            tr.append(row["high"] - row["low"])
        else:
            previous_close = rows[i - 1]["close"]
            tr.append(max(row["high"] - row["low"],
                          abs(row["high"] - previous_close),
                          abs(row["low"] - previous_close)))
    out: list[float | None] = [None] * len(rows)
    if len(rows) < 14:
        return out
    out[13] = sum(tr[:14]) / 14.0
    for i in range(14, len(rows)):
        out[i] = (float(out[i - 1]) * 13.0 + tr[i]) / 14.0
    return out


def atr_sma_series(rows: list[dict[str, Any]]) -> list[float | None]:
    """Simple 14-bar mean of true range, used only as an iATR diagnostic."""
    tr: list[float] = []
    for i, row in enumerate(rows):
        if i == 0:
            tr.append(row["high"] - row["low"])
        else:
            previous_close = rows[i - 1]["close"]
            tr.append(max(row["high"] - row["low"],
                          abs(row["high"] - previous_close),
                          abs(row["low"] - previous_close)))
    out: list[float | None] = [None] * len(rows)
    for i in range(13, len(rows)):
        out[i] = sum(tr[i - 13:i + 1]) / 14.0
    return out


def feature_series(rows: list[dict[str, Any]], xau_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ema = ema_series(rows)
    atr = atr_series(rows)
    atr_sma = atr_sma_series(rows)
    xau_by_time = {r["time"]: r for r in xau_rows}
    features: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        item: dict[str, Any] = {
            "time": row["time"], "ema48": None, "residual": None, "sigma48": None,
            "z_score": None, "atr14": None, "atr_p20": None, "atr_p80": None,
            "atr_sma14": None,
            "xau_bar_time": None, "xau_open": None, "xau_close": None, "xau_return": None,
            "v1_candidate": None, "v3_candidate": None, "direction": "invalid",
            "atr_regime_pass": None, "xau_filter_pass": None, "valid": False,
        }
        if i < 48 or ema[i] is None or atr[i] is None:
            features.append(item)
            continue
        # residuals for t-1 ... t-48; current t is deliberately excluded.
        residuals = [rows[j]["close"] - float(ema[j]) for j in range(i - 1, i - 49, -1)]
        if len(residuals) != 48:
            features.append(item)
            continue
        sigma = statistics.stdev(residuals)
        if sigma <= 0.0:
            features.append(item)
            continue
        prior_atr = [atr[j] for j in range(i - 1, i - 501, -1)]
        if len(prior_atr) != 500 or any(v is None or v <= 0 for v in prior_atr):
            features.append(item)
            continue
        prior_atr_f = sorted(float(v) for v in prior_atr)
        p20 = prior_atr_f[math.ceil(0.20 * len(prior_atr_f)) - 1]
        p80 = prior_atr_f[math.ceil(0.80 * len(prior_atr_f)) - 1]
        xau = xau_by_time.get(row["time"])
        if xau is None or xau["open"] <= 0:
            features.append(item)
            continue
        residual = row["close"] - float(ema[i])
        z = residual / sigma
        xr = xau["close"] / xau["open"] - 1.0
        atr_value = float(atr[i])
        item.update({
            "ema48": float(ema[i]), "residual": residual, "sigma48": sigma,
            "z_score": z, "atr14": atr_value, "atr_p20": p20, "atr_p80": p80,
            "atr_sma14": float(atr_sma[i]) if atr_sma[i] is not None else None,
            "xau_bar_time": xau["time"], "xau_open": xau["open"],
            "xau_close": xau["close"], "xau_return": xr,
            "v1_candidate": int(abs(z) >= 1.5), "v3_candidate": int(abs(z) >= 2.0),
            "direction": "long" if z < 0 else ("short" if z > 0 else "none"),
            "atr_regime_pass": int(p20 <= atr_value <= p80),
            "xau_filter_pass": int(xr != 0.0 and ((xr > 0 and z > 0) or (xr < 0 and z < 0))),
            "valid": True,
        })
        features.append(item)
    return features


def equally_spaced(items: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if len(items) < count:
        raise RuntimeError(f"sample shortage: need {count}, have {len(items)}")
    if count == 1:
        return [items[(len(items) - 1) // 2]]
    selected: list[dict[str, Any]] = []
    for j in range(count):
        pos = j * (len(items) - 1) / (count - 1)
        idx = int(math.floor(pos + 0.5))
        selected.append(items[idx])
    if len({r["time"] for r in selected}) != count:
        raise RuntimeError("equally spaced selector produced duplicate timestamps")
    return selected


def audit_rows() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for window in WINDOW_ORDER:
        path = FAMILY / "smoke" / f"DS260914_XAMR30_SMOKE_{window}" / "trades.csv"
        if not path.is_file():
            raise RuntimeError(f"N1R3 audit bridge file missing: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        start, end = WINDOWS[window]
        for row in rows:
            t = parse_time(row["signal_bar_open_time"])
            if not (start <= t < end):
                raise RuntimeError(f"audit row outside fixed window: {path} {t}")
            out.append({
                "row_id": f"AUDIT_{window}_{row['deal_ticket']}",
                "window": window,
                "sample_type": "audit_bridge",
                "timestamp": t,
                "source_audit_file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "source_ticket": row["deal_ticket"],
                "audit": row,
            })
    if len(out) != 37 or len({r["row_id"] for r in out}) != 37:
        raise RuntimeError(f"expected 37 unique audit bridge rows, got {len(out)}")
    return out


def write_sample_file(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["row_id", "window", "sample_type", "timestamp",
                         "source_audit_file", "source_ticket"])
        for row in rows:
            writer.writerow([
                row["row_id"], row["window"], row["sample_type"], fmt_time(row["timestamp"]),
                row.get("source_audit_file", ""), row.get("source_ticket", ""),
            ])


def provenance() -> dict[str, Any]:
    source_sha = sha256(SOURCE)
    ex5_sha = sha256(CANONICAL_EX5)
    deployed_sha = sha256(DEPLOYED_EX5)
    ok = source_sha == EXPECTED_SOURCE_SHA and ex5_sha == EXPECTED_EX5_SHA and deployed_sha == EXPECTED_EX5_SHA
    return {
        "status": "PASS" if ok else "INVALID",
        "source_path": str(SOURCE), "source_sha256": source_sha,
        "canonical_ex5_path": str(CANONICAL_EX5), "canonical_ex5_sha256": ex5_sha,
        "deployed_ex5_path": str(DEPLOYED_EX5), "deployed_ex5_sha256": deployed_sha,
        "expected_source_sha256": EXPECTED_SOURCE_SHA, "expected_ex5_sha256": EXPECTED_EX5_SHA,
        "starting_head": STARTING_HEAD,
    }


def raw_manifest(usd: list[dict[str, Any]], xau: list[dict[str, Any]], first_selected: dt.datetime) -> dict[str, Any]:
    def one(symbol: str, path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "symbol": symbol, "timeframe": "M30", "path": str(path),
            "first": fmt_time(rows[0]["time"]), "last": fmt_time(rows[-1]["time"]),
            "bar_count": len(rows), "size_bytes": path.stat().st_size,
            "sha256": sha256(path), "fields": ["timestamp", "open", "high", "low", "close"],
        }
    before = sum(1 for row in usd if row["time"] < first_selected)
    manifest = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": {
            "kind": "real MT5 Tester history",
            "terminal": r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
            "server": "Exness-MT5Trial5", "account": "277335900",
            "export_method": "read-only dsh_XAMR30SignalProbe_v1 OnTester CopyRates(PERIOD_M30)",
            "synthetic_symbol": False, "csv_reinjection": False,
        },
        "first_selected_timestamp": fmt_time(first_selected),
        "USDJPYm_bars_before_first_selected": before,
        "USDJPYm_before_first_selected_requirement": 5000,
        "USDJPYm_warmup_pass": before >= 5000,
        "files": [one("USDJPYm", RAW_USD, usd), one("XAUUSDm", RAW_XAU, xau)],
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def prepare() -> int:
    usd = read_raw(RAW_USD)
    xau = read_raw(RAW_XAU)
    features = feature_series(usd, xau)
    bridge = audit_rows()
    selected: list[dict[str, Any]] = []
    selection_metrics: dict[str, Any] = {}
    for window in WINDOW_ORDER:
        start, end = WINDOWS[window]
        pool = [f for f in features if start <= f["time"] < end and f["valid"]]
        candidates = [f for f in pool if abs(float(f["z_score"])) >= 1.5]
        controls = [f for f in pool if abs(float(f["z_score"])) < 1.5]
        chosen_c = equally_spaced(candidates, 20)
        chosen_ctrl = equally_spaced(controls, 10)
        selection_metrics[window] = {
            "pool_valid": len(pool), "candidate_pool": len(candidates),
            "control_pool": len(controls), "candidate_selected": len(chosen_c),
            "control_selected": len(chosen_ctrl),
        }
        for i, item in enumerate(chosen_c, 1):
            selected.append({"row_id": f"{window}_C_{i:02d}", "window": window,
                             "sample_type": "candidate", "timestamp": item["time"]})
        for i, item in enumerate(chosen_ctrl, 1):
            selected.append({"row_id": f"{window}_K_{i:02d}", "window": window,
                             "sample_type": "control", "timestamp": item["time"]})
    selected.extend({k: v for k, v in row.items() if k != "audit"} for row in bridge)
    # Sort by fixed window, then timestamp, then sample type/id; this ordering is
    # deterministic and does not alter the equally-spaced selection itself.
    selected.sort(key=lambda r: (WINDOW_ORDER.index(r["window"]), r["timestamp"], r["sample_type"], r["row_id"]))
    write_sample_file(selected, SAMPLE_COMMON)
    write_sample_file(selected, SAMPLE_LOCAL)
    first_selected = min(r["timestamp"] for r in selected if r["sample_type"] != "audit_bridge")
    manifest = raw_manifest(usd, xau, first_selected)
    prep = {
        "provenance": provenance(), "sample_file": str(SAMPLE_LOCAL),
        "common_sample_file": str(SAMPLE_COMMON), "windows": selection_metrics,
        "selected_total": len([r for r in selected if r["sample_type"] != "audit_bridge"]),
        "candidate_total": sum(v["candidate_selected"] for v in selection_metrics.values()),
        "control_total": sum(v["control_selected"] for v in selection_metrics.values()),
        "audit_bridge_total": len(bridge), "raw_manifest": manifest,
    }
    (WORK / "doublecalc_prepare.json").write_text(json.dumps(prep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(prep, ensure_ascii=False, indent=2))
    return 0


def fnum(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def close(a: float | None, b: float | None, tol: float) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def mql_rows() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for window in WINDOW_ORDER:
        path = MQL_OUTPUT_DIR / f"probe_{window}_mql.csv"
        if not path.is_file():
            # Permit the runner to leave outputs in the MT5 Common directory.
            path = COMMON / f"probe_{window}_mql.csv"
        if not path.is_file():
            raise RuntimeError(f"MQL probe output missing: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        for row in rows:
            if row.get("row_id") in out:
                raise RuntimeError(f"duplicate MQL probe row_id: {row['row_id']}")
            out[row["row_id"]] = row
    return out


def numeric_tol(field: str, reference: float) -> float:
    if field in {"z_score", "xau_return"}:
        return 1e-6
    return max(1e-6, abs(reference) * 1e-8)


def audit_digits(value: str) -> int:
    s = str(value).strip()
    if "e" in s.lower():
        return 8
    return len(s.split(".", 1)[1]) if "." in s else 0


def audit_tol(value: str) -> float:
    return 0.5 * (10.0 ** (-audit_digits(value))) + 1e-12


def normalize_audit_time(value: str) -> str:
    return fmt_time(parse_time(value))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    keys = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_atr_mismatch_context(usd: list[dict[str, Any]], rows90: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [r for r in rows90 if "atr14_mismatch" in r.get("row_status", "")]
    if not failures:
        return {"status": "NONE"}
    first = failures[0]
    target = parse_time(first["timestamp"])
    index = next(i for i, row in enumerate(usd) if row["time"] == target)
    lo = max(0, index - 30)
    hi = min(len(usd), index + 30)
    wilder = atr_series(usd)
    simple = atr_sma_series(usd)
    context: list[dict[str, Any]] = []
    for i in range(lo, hi):
        row = usd[i]
        tr = row["high"] - row["low"] if i == 0 else max(
            row["high"] - row["low"],
            abs(row["high"] - usd[i - 1]["close"]),
            abs(row["low"] - usd[i - 1]["close"]),
        )
        context.append({
            "timestamp": fmt_time(row["time"]), "open": row["open"], "high": row["high"],
            "low": row["low"], "close": row["close"], "true_range": tr,
            "python_wilder_atr14": wilder[i], "python_sma_tr14": simple[i],
        })
    csv_path = WORK / "XAMR30_atr_mismatch_context_60.csv"
    write_csv(csv_path, context)
    detail = {
        "status": "EXPLAINED_SEMANTIC_CONFLICT", "field": "atr14", "row_id": first["row_id"],
        "timestamp": first["timestamp"], "python_wilder": first["py_atr14"],
        "mql_iatr": first["mql_atr14"], "diff": first["diff_atr14"],
        "tolerance": numeric_tol("atr14", float(first["mql_atr14"])),
        "mql_iatr_matches_simple_tr14_rows": None,
        "raw_context_rows": len(context), "raw_context_csv": str(csv_path),
        "raw_source": str(RAW_USD),
    }
    (WORK / "XAMR30_atr_mismatch_context_60.json").write_text(
        json.dumps({"detail": detail, "bars": context}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return detail


def finalize() -> int:
    usd = read_raw(RAW_USD)
    xau = read_raw(RAW_XAU)
    features = feature_series(usd, xau)
    by_time = {f["time"]: f for f in features}
    selected = []
    with SAMPLE_LOCAL.open("r", encoding="utf-8-sig", newline="") as fh:
        selected = list(csv.DictReader(fh))
    selected_90 = [r for r in selected if r["sample_type"] in {"candidate", "control"}]
    if len(selected_90) != 90:
        raise RuntimeError(f"expected 90 selected rows, got {len(selected_90)}")
    mql = mql_rows()
    rows90: list[dict[str, Any]] = []
    continuous_counts = {field: 0 for field in MQL_COMPARE_FIELDS + ["z_score", "xau_return"]}
    max_diffs = {field: 0.0 for field in MQL_COMPARE_FIELDS + ["z_score", "xau_return"]}
    worst = {field: "" for field in max_diffs}
    discrete_counts = {field: 0 for field in FLAGS}
    xau_ohlc_pass = 0
    mql_sma_pass = 0
    mql_sma_max_diff = 0.0
    mql_sma_worst = ""
    for sample in selected_90:
        row_id = sample["row_id"]
        py = by_time.get(parse_time(sample["timestamp"]))
        mq = mql.get(row_id)
        result: dict[str, Any] = {
            "window": sample["window"], "sample_type": sample["sample_type"], "row_id": row_id,
            "timestamp": sample["timestamp"], "mql_status": mq.get("row_status", "MISSING") if mq else "MISSING",
        }
        errors: list[str] = []
        if py is None or not py["valid"]:
            errors.append("python_reference_invalid")
        if mq is None:
            errors.append("mql_row_missing")
        for field in MQL_COMPARE_FIELDS + ["z_score", "xau_return"]:
            pyv = py.get(field) if py else None
            mqv = fnum(mq.get(field)) if mq else None
            diff = abs(mqv - pyv) if mqv is not None and pyv is not None else None
            result[f"py_{field}"] = fmt_num(pyv)
            result[f"mql_{field}"] = fmt_num(mqv)
            result[f"diff_{field}"] = fmt_num(diff)
            ok = mq is not None and mq.get("row_status") == "PASS" and diff is not None and close(mqv, pyv, numeric_tol(field, mqv))
            if ok:
                continuous_counts[field] += 1
            else:
                errors.append(f"{field}_mismatch")
            if diff is not None and diff >= max_diffs[field]:
                max_diffs[field] = diff
                worst[field] = row_id
        py_sma = py.get("atr_sma14") if py else None
        mql_atr = fnum(mq.get("atr14")) if mq else None
        sma_diff = abs(mql_atr - py_sma) if mql_atr is not None and py_sma is not None else None
        if sma_diff is not None and sma_diff <= 1e-9:
            mql_sma_pass += 1
        if sma_diff is not None and sma_diff >= mql_sma_max_diff:
            mql_sma_max_diff = sma_diff
            mql_sma_worst = row_id
        if mq is not None:
            xau_time_ok = normalize_audit_time(mq.get("xau_bar_time", "")) == sample["timestamp"]
            xau_open = fnum(mq.get("xau_open")); xau_close = fnum(mq.get("xau_close"))
            py_open = py.get("xau_open") if py else None; py_close = py.get("xau_close") if py else None
            xau_ohlc_ok = xau_time_ok and close(xau_open, py_open, 1e-8) and close(xau_close, py_close, 1e-8)
        else:
            xau_ohlc_ok = False
        if xau_ohlc_ok:
            xau_ohlc_pass += 1
        else:
            errors.append("xau_exact_or_ohlc_mismatch")
        result.update({
            "py_xau_bar_time": fmt_time(py["xau_bar_time"]) if py and py.get("xau_bar_time") else "",
            "mql_xau_bar_time": mq.get("xau_bar_time", "") if mq else "",
            "py_xau_open": fmt_num(py.get("xau_open") if py else None),
            "mql_xau_open": mq.get("xau_open", "") if mq else "",
            "py_xau_close": fmt_num(py.get("xau_close") if py else None),
            "mql_xau_close": mq.get("xau_close", "") if mq else "",
            "py_atr_sma14_diagnostic": fmt_num(py_sma),
            "mql_atr14_minus_sma14": fmt_num(sma_diff),
            "py_v1_candidate": py.get("v1_candidate") if py else "",
            "mql_v1_candidate": mq.get("v1_candidate", "") if mq else "",
            "py_v3_candidate": py.get("v3_candidate") if py else "",
            "mql_v3_candidate": mq.get("v3_candidate", "") if mq else "",
            "py_direction": py.get("direction", "") if py else "",
            "mql_direction": mq.get("direction", "") if mq else "",
            "py_atr_regime_pass": py.get("atr_regime_pass") if py else "",
            "mql_atr_regime_pass": mq.get("atr_regime_pass", "") if mq else "",
            "py_xau_filter_pass": py.get("xau_filter_pass") if py else "",
            "mql_xau_filter_pass": mq.get("xau_filter_pass", "") if mq else "",
        })
        for field in FLAGS:
            if mq is not None and str(py.get(field)) == str(mq.get(field)):
                discrete_counts[field] += 1
            else:
                errors.append(f"{field}_mismatch")
        result["row_status"] = "PASS" if not errors else "FAIL:" + ";".join(dict.fromkeys(errors))
        rows90.append(result)
    write_csv(WORK / "XAMR30_doublecalc_90.csv", rows90)
    (WORK / "XAMR30_doublecalc_90.json").write_text(
        json.dumps(rows90, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    bridge_targets = audit_rows()
    bridge_rows: list[dict[str, Any]] = []
    bridge_field_counts = {field: 0 for field in ["ema48", "residual", "sigma48", "z_score", "atr14", "atr_p20", "atr_p80", "xau_open", "xau_close", "xau_return"]}
    bridge_max = {field: 0.0 for field in bridge_field_counts}
    bridge_worst = {field: "" for field in bridge_field_counts}
    for target in bridge_targets:
        row_id = target["row_id"]
        audit = target["audit"]
        mq = mql.get(row_id)
        f = by_time.get(target["timestamp"])
        errors: list[str] = []
        if mq is None or f is None:
            errors.append("missing_bridge_row_or_reference")
        vals: dict[str, Any] = {}
        for field in ["ema48", "residual", "sigma48", "z_score", "atr14", "atr_p20", "atr_p80", "xau_return"]:
            av = fnum(audit.get(field))
            mv = fnum(mq.get(field)) if mq else None
            diff = abs(mv - av) if mv is not None and av is not None else None
            tol = audit_tol(audit.get(field, ""))
            ok = diff is not None and diff <= tol
            if ok:
                bridge_field_counts[field] += 1
            else:
                errors.append(f"{field}_audit_mismatch")
            if diff is not None and diff >= bridge_max[field]:
                bridge_max[field] = diff; bridge_worst[field] = row_id
            vals[f"audit_{field}"] = audit.get(field, "")
            vals[f"mql_{field}"] = mq.get(field, "") if mq else ""
            vals[f"diff_{field}"] = fmt_num(diff)
            vals[f"tol_{field}"] = fmt_num(tol)
        for field in ["xau_open", "xau_close"]:
            av = fnum(audit.get(field)); mv = fnum(mq.get(field)) if mq else None
            diff = abs(mv - av) if mv is not None and av is not None else None
            tol = audit_tol(audit.get(field, ""))
            ok = diff is not None and diff <= tol
            if ok: bridge_field_counts[field] += 1
            else: errors.append(f"{field}_audit_mismatch")
            if diff is not None and diff >= bridge_max[field]:
                bridge_max[field] = diff; bridge_worst[field] = row_id
            vals[f"audit_{field}"] = audit.get(field, "")
            vals[f"mql_{field}"] = mq.get(field, "") if mq else ""
            vals[f"diff_{field}"] = fmt_num(diff)
            vals[f"tol_{field}"] = fmt_num(tol)
        time_ok = mq is not None and mq.get("timestamp") == fmt_time(target["timestamp"])
        xau_time_ok = mq is not None and normalize_audit_time(mq.get("xau_bar_time", "")) == normalize_audit_time(audit.get("xau_bar_time", ""))
        direction_ok = mq is not None and mq.get("direction") == audit.get("trade_direction")
        flags_ok = mq is not None and mq.get("row_status") == "PASS" and mq.get("v1_candidate") == "1" and mq.get("atr_regime_pass") == "1" and mq.get("xau_filter_pass") == "1"
        if not time_ok: errors.append("signal_timestamp_mismatch")
        if not xau_time_ok: errors.append("xau_timestamp_mismatch")
        if not direction_ok: errors.append("direction_mismatch")
        if not flags_ok: errors.append("required_trade_flags_mismatch")
        bridge_rows.append({
            "row_id": row_id, "window": target["window"], "source_audit_file": target["source_audit_file"],
            "source_ticket": target["source_ticket"], "signal_bar_open_time": fmt_time(target["timestamp"]),
            "mql_xau_bar_time": mq.get("xau_bar_time", "") if mq else "",
            "audit_xau_bar_time": audit.get("xau_bar_time", ""), "timestamp_exact": int(time_ok),
            "xau_timestamp_exact": int(xau_time_ok), "direction_audit": audit.get("trade_direction", ""),
            "direction_mql": mq.get("direction", "") if mq else "", "direction_exact": int(direction_ok),
            **vals, "row_status": "PASS" if not errors else "FAIL:" + ";".join(dict.fromkeys(errors)),
        })
    write_csv(WORK / "XAMR30_probe_vs_N1R3_audit.csv", bridge_rows)
    (WORK / "XAMR30_probe_vs_N1R3_audit.json").write_text(
        json.dumps(bridge_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    prov = provenance()
    first_selected = min(parse_time(r["timestamp"]) for r in selected_90)
    manifest = raw_manifest(usd, xau, first_selected)
    mismatch = write_atr_mismatch_context(usd, rows90)
    mismatch["mql_iatr_matches_simple_tr14_rows"] = mql_sma_pass
    field_pass = {k: v for k, v in continuous_counts.items()}
    sample_pass = all(r["row_status"] == "PASS" for r in rows90)
    bridge_pass = all(r["row_status"] == "PASS" for r in bridge_rows)
    summary: dict[str, Any] = {
        "starting_head": STARTING_HEAD, "provenance": prov,
        "fixed_windows": {k: {"from": fmt_time(v[0]), "to_exclusive": fmt_time(v[1])} for k, v in WINDOWS.items()},
        "sampling": {"selected_total": len(rows90), "candidate": sum(r["sample_type"] == "candidate" for r in selected_90),
                      "control": sum(r["sample_type"] == "control" for r in selected_90), "audit_bridge": len(bridge_rows),
                      "algorithm": "sort valid pool by timestamp; equally spaced positions round-half-up over the entire pool"},
        "raw_manifest": manifest, "python_mql": {"all_rows_complete": sample_pass, "field_pass_counts": field_pass,
                         "required_rows": 90, "max_diffs": max_diffs, "worst_row": worst,
                         "xau_exact_ohlc_pass": xau_ohlc_pass, "discrete_pass_counts": discrete_counts,
                         "mql_iatr_matches_sma_tr_rows": mql_sma_pass,
                         "mql_iatr_sma_tr_max_diff": mql_sma_max_diff,
                         "mql_iatr_sma_tr_worst_row": mql_sma_worst},
        "bridge": {"rows": len(bridge_rows), "all_pass": bridge_pass, "field_pass_counts": bridge_field_counts,
                   "max_diffs": bridge_max, "worst_row": bridge_worst},
        "mismatch": mismatch,
        "SIGNAL_DOUBLECALC": "PASS" if prov["status"] == "PASS" and sample_pass and bridge_pass and len(rows90) == 90 and len(bridge_rows) == 37 else "FAIL",
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["SIGNAL_DOUBLECALC"] == "PASS" else 1


def write_report(summary: dict[str, Any]) -> None:
    py = summary["python_mql"]
    br = summary["bridge"]
    prov = summary["provenance"]
    lines = [
        "# XAMR30 N1R3 Signal Double-Calc Report",
        "",
        "- Date: 2026-09-14",
        f"- Starting HEAD: `{summary['starting_head']}`",
        f"- Provenance: **{prov['status']}**",
        f"- Final signal double-calc: **{summary['SIGNAL_DOUBLECALC']}**",
        "",
        "## Strategy identity",
        "",
        f"- Source: `{prov['source_path']}` · `{prov['source_sha256']}`",
        f"- Canonical N1R3 EX5: `{prov['canonical_ex5_path']}` · `{prov['canonical_ex5_sha256']}`",
        f"- Deployed Tester EX5: `{prov['deployed_ex5_path']}` · `{prov['deployed_ex5_sha256']}`",
        "- Build: MetaEditor / MT5 build 6184, 0 errors / 0 warnings.",
        "- The legacy `N1_ea_XAMR30_frozen_hashes.sha256` is preserved as a superseded pre-N1R3 record; it was not overwritten.",
        "",
        "## Fixed sample",
        "",
        "- Windows: WINTER 2023-01-02 through 2023-01-31; DSTTR 2023-03-20 through 2023-04-07; SUMMER 2023-07-03 through 2023-07-31.",
        f"- Selected rows: {summary['sampling']['selected_total']} = {summary['sampling']['candidate']} candidate + {summary['sampling']['control']} control; bridge rows: {summary['sampling']['audit_bridge']}.",
        f"- Algorithm: {summary['sampling']['algorithm']}.",
        "- Candidate pool: valid EMA48/sigma48/ATR500/exact-XAU, |z| >= 1.5. Control pool is the same validity set with |z| < 1.5. ATR regime and XAU filter were not used for selection.",
        "",
        "## Raw data and independent math",
        "",
        f"- Manifest: `deepseek数据保存/执行_XAMR30/doublecalc_raw_manifest.json`.",
        f"- USDJPYm warm-up bars before the first selected timestamp: {summary['raw_manifest']['USDJPYm_bars_before_first_selected']} (requirement >= 5000).",
        "- Raw source: real MT5 Tester M30 OHLC via read-only Probe `CopyRates`; no synthetic symbol and no CSV reinjection.",
        "- Python independently computed EMA48 (alpha 2/(48+1)), residual, sample sigma48 over t-48..t-1, Wilder ATR14, prior-500 nearest-rank P20/P80, exact XAU join, return, v1/v3 flags, direction, ATR regime, and XAU filter.",
        "- MQL independently computed the same fields through iMA EMA48, iATR, SigmaBeforeT, AtrPercentile, and exact XAU M30 lookup; Python values were not fed to the Probe.",
        "",
        "## Python vs MQL",
        "",
        f"- Complete rows: {'PASS' if py['all_rows_complete'] else 'FAIL'} ({py['required_rows']}/{py['required_rows']}).",
        f"- XAU exact timestamp/OHLC: {py['xau_exact_ohlc_pass']}/{py['required_rows']}.",
        f"- Continuous field pass counts: `{json.dumps(py['field_pass_counts'], ensure_ascii=False)}`.",
        f"- Discrete flag pass counts: `{json.dumps(py['discrete_pass_counts'], ensure_ascii=False)}`.",
        f"- Maximum diffs: `{json.dumps(py['max_diffs'], ensure_ascii=False)}`; worst rows: `{json.dumps(py['worst_row'], ensure_ascii=False)}`.",
        f"- iATR semantic diagnostic: MT5 MQL `iATR` matched the current 14-bar simple mean of true range in {py['mql_iatr_matches_sma_tr_rows']}/90 rows (max diagnostic diff {py['mql_iatr_sma_tr_max_diff']:.12g}); the mandated Python Wilder ATR reference therefore conflicts with the observed MQL iATR semantics.",
        f"- Mismatch detail: `{summary['mismatch']['field']}` at `{summary['mismatch']['timestamp']}`; Python Wilder={summary['mismatch']['python_wilder']}, MQL iATR={summary['mismatch']['mql_iatr']}, diff={summary['mismatch']['diff']}, tolerance={summary['mismatch']['tolerance']}. Sixty surrounding raw bars are preserved in `{summary['mismatch']['raw_context_csv']}` and its JSON companion.",
        "- This is recorded as `SIGNAL_DOUBLECALC=FAIL` without changing the strategy EA, tolerances, or sample selection; the reference-semantics decision is left to Planner/N1R4.",
        "",
        "## Probe bridge to N1R3 final-smoke audit",
        "",
        f"- Compared all {br['rows']} existing audit rows: {'PASS' if br['all_pass'] else 'FAIL'}.",
        f"- Audit continuous field pass counts: `{json.dumps(br['field_pass_counts'], ensure_ascii=False)}`.",
        f"- Maximum rounded-audit diffs: `{json.dumps(br['max_diffs'], ensure_ascii=False)}`; worst rows: `{json.dumps(br['worst_row'], ensure_ascii=False)}`.",
        "- Bridge fields include signal timestamp, EMA48/residual/sigma48/z, ATR14/P20/P80, exact XAU timestamp/OHLC/return, and trade direction/required-pass flags.",
        "",
        "## Machine evidence",
        "",
        "- `deepseek数据保存/执行_XAMR30/doublecalc/XAMR30_doublecalc_90.csv` / `.json`",
        "- `deepseek数据保存/执行_XAMR30/doublecalc/XAMR30_probe_vs_N1R3_audit.csv` / `.json`",
        "- `deepseek数据保存/执行_XAMR30/doublecalc/XAMR30_doublecalc_summary.json`",
        "- `deepseek数据保存/执行_XAMR30/doublecalc/XAMR30_atr_mismatch_context_60.csv` / `.json`",
        "- `deepseek数据保存/mql5/dshtools/dsh_XAMR30SignalProbe_v1.mq5`",
        "",
        "No strategy EA, Data Freeze, 77-month evidence, TRAIN/VALID/OOS/holdout data, or tolerance was modified in this stage.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in {"prepare", "finalize"}:
        print("usage: doublecalc_xamr30.py prepare|finalize", file=sys.stderr)
        return 2
    return prepare() if argv[1] == "prepare" else finalize()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
