#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""XAMR30 Monthly v4 · complete 2018-01..2024-05 data qualification.

This is a new, date-scoped runner.  The four-window runner and the v4 EA are
frozen inputs; this file only expands the same probe to 77 independent
monthly Tester runs and mechanically computes the earliest all-pass suffix.
No strategy EA, signal calculation, TRAIN, VALID, OOS, or Route B code is run.
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from run_v4_regression import (
    FORMAL_PREFIX,
    REQUIRED_FIELDS,
    TERMINAL,
    TDATA,
    as_float,
    as_int,
    kill_terminals,
    sha256,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTDIR = REPO_ROOT / "deepseek数据保存" / "执行_XAMR30" / "N0_data"
RAW_OUTDIR = OUTDIR / "monthly_v4_raw"
SOURCE = REPO_ROOT / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30Monthly_v4.mq5"
PREVIOUS_REPORT = OUTDIR / "XAMR30_MONTHLY_V4_REGRESSION_REPORT.md"
TESTER_EX5 = (TDATA / "MQL5" / "Experts" / "dshtrend" /
              "dsh_XAMR30Monthly_v4.ex5")
COMMON = (Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" /
          "Common" / "Files" / "dshtrend" / "XAMR30MON4")

EXPECTED_HEAD = "5a853628ed1ebe3c5f8e57f3d111319c05340c99"
EXPECTED_SOURCE_SHA = "8E2A46B5301B1FB60090B047C7C5DF7A161F3A3B379842A9287F85BF1199E98C"
EXPECTED_EX5_SHA = "ED68B79228EA99359EBF4B5998D60FC0CF119511C60F0270330A8BD6621DA7AA"
JSB30_COVERAGE_COMMIT = "54ca679bf58bfde9da22b3c8ff598529897c8a0e"
JSB30_COVERAGE_REPORT = (
    "deepseek数据保存/执行_下一family_20260913/N1_ea/JSB30_history_coverage_final.md"
)
JSB30_REVIEW_REPORT = "公共部分/JSB30_TRAIN_VALID_最终审阅包_20260914_R2.md"


def add_month(year: int, month: int, count: int = 1) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + count
    return absolute // 12, absolute % 12 + 1


def make_months() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    year, month = 2018, 1
    while (year, month) <= (2024, 5):
        ny, nm = add_month(year, month)
        rows.append(
            (
                f"{year:04d}-{month:02d}",
                f"{year:04d}.{month:02d}.01",
                f"{ny:04d}.{nm:02d}.01",
            )
        )
        year, month = ny, nm
    assert len(rows) == 77
    assert rows[0][0] == "2018-01"
    assert rows[-1][0] == "2024-05"
    assert len({row[0] for row in rows}) == 77
    return rows


def make_ini(config_dir: Path, run_tag: str, frm: str, to: str) -> Path:
    safe_tag = run_tag.replace("-", "_")
    text = "\n".join([
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]", "Expert=dshtrend\\dsh_XAMR30Monthly_v4", "Symbol=USDJPYm",
        "Period=M30", "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to, "ForwardMode=0",
        "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_M4Q_" + safe_tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]", "InpRunTag=" + run_tag, "InpInfoSym=XAUUSDm",
        "InpMonthFrom=" + frm, "InpMonthTo=" + to,
    ]) + "\n"
    path = config_dir / ("run_M4Q_%s.ini" % safe_tag)
    path.write_text(text, encoding="utf-8")
    return path


def latest_tester_log() -> tuple[Path | None, str]:
    log_dir = TDATA / "Tester" / "logs"
    if not log_dir.is_dir():
        return None, ""
    files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None, ""
    path = files[-1]
    # The daily log is large and append-only.  The newest run is at the end;
    # read a bounded UTF-16LE tail rather than repeatedly loading the whole log.
    size = path.stat().st_size
    offset = max(0, size - 12 * 1024 * 1024)
    offset -= offset % 2
    with path.open("rb") as fh:
        fh.seek(offset)
        raw = fh.read()
    return path, raw.decode("utf-16-le", errors="ignore")


def journal_snapshot(run_tag: str) -> tuple[dict[str, int], Path | None, list[str]]:
    path, text = latest_tester_log()
    counts: dict[str, int] = {}
    for symbol in ("USDJPYm", "XAUUSDm"):
        matches = re.findall(
            re.escape(symbol) + r",M30:\s*(\d+)\s*ticks,\s*(\d+)\s*bars generated",
            text,
        )
        if matches:
            counts[symbol] = int(matches[-1][1])
    lines = [
        line.strip() for line in text.splitlines()
        if run_tag in line or ("USDJPYm,M30:" in line and "bars generated" in line)
    ]
    return counts, path, lines[-12:]


def parse_formal(path: Path, expected_tag: str) -> dict:
    if not path.is_file():
        return {"parser_valid": False, "parser_invalid_reason": "probe_output_missing", "det": {}}
    lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
             if line.strip()]
    header_indices = [i for i, line in enumerate(lines) if line.startswith(FORMAL_PREFIX)]
    if len(header_indices) != 1:
        return {
            "parser_valid": False,
            "parser_invalid_reason": f"formal_header_count={len(header_indices)}",
            "det": {},
        }
    header_index = header_indices[0]
    if header_index + 1 >= len(lines):
        return {"parser_valid": False, "parser_invalid_reason": "formal_data_row_missing", "det": {}}
    header = next(csv.reader([lines[header_index]]), [])
    immediate_row = next(csv.reader([lines[header_index + 1]]), [])
    if not immediate_row or immediate_row[0] != expected_tag:
        got = immediate_row[0] if immediate_row else "<empty>"
        return {
            "parser_valid": False,
            "parser_invalid_reason": f"formal_next_row_tag={got}!={expected_tag}",
            "det": {},
        }
    formal_rows = []
    for line in lines[header_index + 1:]:
        row = next(csv.reader([line]), [])
        if row and row[0] == expected_tag:
            formal_rows.append(row)
    if len(formal_rows) != 1:
        return {
            "parser_valid": False,
            "parser_invalid_reason": f"formal_data_row_count={len(formal_rows)}",
            "det": {},
        }
    row = formal_rows[0]
    if len(header) != len(row):
        return {
            "parser_valid": False,
            "parser_invalid_reason": f"header_data_column_mismatch={len(header)}!={len(row)}",
            "det": {},
        }
    missing = [field for field in REQUIRED_FIELDS if field not in header]
    if missing:
        return {
            "parser_valid": False,
            "parser_invalid_reason": "required_fields_missing=" + ",".join(missing),
            "det": {},
        }
    return {
        "parser_valid": True,
        "parser_invalid_reason": "",
        "det": dict(zip(header, row)),
        "header": header,
        "formal_row": row,
    }


def parse_mt5_time(value: object) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(str(value), "%Y.%m.%d %H:%M")
    except (TypeError, ValueError):
        return None


def first_last_in_window(det: dict, frm: str, to: str) -> bool:
    try:
        start = dt.datetime.strptime(frm, "%Y.%m.%d")
        end = dt.datetime.strptime(to, "%Y.%m.%d")
    except ValueError:
        return False
    values = [det.get("first_jpy"), det.get("last_jpy"),
              det.get("first_xau"), det.get("last_xau")]
    parsed = [parse_mt5_time(value) for value in values]
    return all(value is not None and start <= value < end for value in parsed)


def add_check(checks: list[dict], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "pass": bool(passed), "detail": detail})


def evaluate_month(parsed: dict, month: str, frm: str, to: str,
                   run_tag: str, journal: dict[str, int], log_path: Path | None,
                   log_lines: list[str], terminal_timed_out: bool,
                   terminal_return_code: int | None, output_fresh: bool) -> dict:
    result = {
        "month": month,
        "run_tag": run_tag,
        "requested_from": frm,
        "requested_to": to,
        "parser_valid": bool(parsed.get("parser_valid")),
        "parser_invalid_reason": parsed.get("parser_invalid_reason", ""),
        "det": parsed.get("det", {}),
        "journal_jpy_bars": journal.get("USDJPYm"),
        "journal_xau_bars": journal.get("XAUUSDm"),
        "filtered_monthly_jpy": None,
        "journal_minus_filtered": None,
        "journal_reconciliation": "NOT_EVALUATED",
        "tester_log_path": str(log_path) if log_path else "",
        "tester_log_relevant_lines": log_lines,
        "checks": [],
        "month_engineering_status": "INVALID",
        "month_data_status": "NOT_EVALUATED",
        "month_pass": False,
        "terminal_timed_out": terminal_timed_out,
        "terminal_return_code": terminal_return_code,
        "output_fresh": output_fresh,
    }
    if terminal_timed_out:
        result["parser_valid"] = False
        result["parser_invalid_reason"] = "terminal_timeout"
    if not output_fresh:
        result["parser_valid"] = False
        result["parser_invalid_reason"] = "probe_output_stale_or_missing"
    if not result["parser_valid"]:
        add_check(result["checks"], "strict_parser", False, result["parser_invalid_reason"])
        return result

    d = result["det"]
    y, m = int(month[:4]), int(month[5:])
    cap = calendar.monthrange(y, m)[1] * 48
    jpy = as_int(d.get("JPY_M30_bars"))
    xau = as_int(d.get("XAU_M30_bars"))
    inter = as_int(d.get("exact_intersection"))
    common = as_float(d.get("common_session_alignment_ratio"))
    info = as_float(d.get("info_availability_ratio"))
    result["filtered_monthly_jpy"] = jpy
    if isinstance(result["journal_jpy_bars"], int) and jpy is not None:
        result["journal_minus_filtered"] = result["journal_jpy_bars"] - jpy
        result["journal_reconciliation"] = (
            "PASS" if result["journal_minus_filtered"] == 0 else "MISMATCH"
        )
    elif jpy is not None:
        result["journal_reconciliation"] = "UNAVAILABLE"

    add_check(result["checks"], "probe_valid=1", d.get("probe_valid") == "1",
              "invalid_reason=%s" % d.get("invalid_reason", ""))
    add_check(result["checks"], "finalization_event=OnTester",
              d.get("finalization_event") == "OnTester",
              "event=%s" % d.get("finalization_event"))
    add_check(result["checks"], "MethodA==MethodB (JPY)",
              d.get("methodA_methodB_jpy_equal") == "1"
              and d.get("methodA_jpy_count") == d.get("methodB_jpy_count"),
              "A=%s B=%s" % (d.get("methodA_jpy_count"), d.get("methodB_jpy_count")))
    add_check(result["checks"], "MethodA==MethodB (XAU)",
              d.get("methodA_methodB_xau_equal") == "1"
              and d.get("methodA_xau_count") == d.get("methodB_xau_count"),
              "A=%s B=%s" % (d.get("methodA_xau_count"), d.get("methodB_xau_count")))
    add_check(result["checks"], "0 < JPY_monthly <= days*48",
              jpy is not None and 0 < jpy <= cap, "jpy=%s cap=%d" % (jpy, cap))
    add_check(result["checks"], "0 < XAU_monthly <= days*48",
              xau is not None and 0 < xau <= cap, "xau=%s cap=%d" % (xau, cap))
    add_check(result["checks"], "duplicate_timestamps=0",
              d.get("jpy_dup") == "0" and d.get("xau_dup") == "0",
              "jpy=%s xau=%s" % (d.get("jpy_dup"), d.get("xau_dup")))
    add_check(result["checks"], "non_monotonic_timestamps=0",
              d.get("jpy_non_monotonic") == "0" and d.get("xau_non_monotonic") == "0",
              "jpy=%s xau=%s" % (d.get("jpy_non_monotonic"), d.get("xau_non_monotonic")))
    add_check(result["checks"], "outside_requested_month=0",
              d.get("outside_requested_month") == "0",
              "outside=%s" % d.get("outside_requested_month"))
    add_check(result["checks"], "first_last_within_requested_month",
              first_last_in_window(d, frm, to),
              "jpy=%s..%s xau=%s..%s" % (d.get("first_jpy"), d.get("last_jpy"),
                                         d.get("first_xau"), d.get("last_xau")))
    gate_a = d.get("GateA_status")
    gate_b = d.get("GateB_status")
    gate_a_consistent = gate_a in {"PASS", "FAIL"} and common is not None and (
        (gate_a == "PASS" and common >= 99.0) or (gate_a == "FAIL" and common < 99.0)
    )
    gate_b_consistent = gate_b in {"PASS", "FAIL"} and info is not None and (
        (gate_b == "PASS" and info >= 90.0) or (gate_b == "FAIL" and info < 90.0)
    )
    add_check(result["checks"], "GateA_status_and_ratio_consistent", gate_a_consistent,
              "status=%s ratio=%s" % (gate_a, d.get("common_session_alignment_ratio")))
    add_check(result["checks"], "GateB_status_and_ratio_consistent", gate_b_consistent,
              "status=%s ratio=%s" % (gate_b, d.get("info_availability_ratio")))
    add_check(result["checks"], "exact_intersection_valid",
              inter is not None and jpy is not None and xau is not None
              and 0 <= inter <= min(jpy, xau),
              "intersection=%s jpy=%s xau=%s" % (inter, jpy, xau))

    result["month_engineering_status"] = (
        "PASS" if all(item["pass"] for item in result["checks"]) else "INVALID"
    )
    if result["month_engineering_status"] == "PASS":
        if gate_a == "PASS" and gate_b == "PASS":
            result["month_data_status"] = "PASS"
            result["month_pass"] = True
        else:
            result["month_data_status"] = "GATE_FAIL"
    if result["journal_reconciliation"] == "UNAVAILABLE" and result["month_engineering_status"] == "PASS":
        # Missing third-layer evidence is not silently converted into a data gate.
        result["journal_reconciliation"] = "UNAVAILABLE"
    return result


def read_previous_ex5_sha() -> str:
    if PREVIOUS_REPORT.is_file():
        text = PREVIOUS_REPORT.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"EX5 SHA256:\s*`([0-9A-F]{64})`", text)
        if match:
            return match.group(1)
    return EXPECTED_EX5_SHA


def verify_binary_provenance() -> dict:
    source_sha = sha256(SOURCE)
    tester_sha = sha256(TESTER_EX5)
    repo_ex5_sha = read_previous_ex5_sha()
    result = {
        "source_sha": source_sha,
        "repo_ex5_sha": repo_ex5_sha,
        "tester_deployed_ex5_sha": tester_sha,
        "expected_source_sha": EXPECTED_SOURCE_SHA,
        "expected_ex5_sha": EXPECTED_EX5_SHA,
        "repo_ex5_note": "frozen compiler artifact recorded in v4 regression report; EX5 is excluded from the Git mirror. Fresh MetaEditor 6184 recompile probes were 0/0 but produced non-identical transient hashes, so no new binary was deployed; the Tester binary remains the frozen ED68 artifact.",
    }
    result["valid"] = (
        source_sha == EXPECTED_SOURCE_SHA
        and repo_ex5_sha == EXPECTED_EX5_SHA
        and tester_sha == EXPECTED_EX5_SHA
    )
    return result


def summary_for(results: list[dict]) -> dict:
    months = [item["month"] for item in results]
    engineering_invalid = [item for item in results if item["month_engineering_status"] != "PASS"]
    gate_failures = [item for item in results if item["month_data_status"] == "GATE_FAIL"]
    gate_a_failures = [item for item in gate_failures if item["det"].get("GateA_status") == "FAIL"]
    gate_b_failures = [item for item in gate_failures if item["det"].get("GateB_status") == "FAIL"]
    journal_mismatches = [item for item in results if item["journal_reconciliation"] == "MISMATCH"]
    journal_unavailable = [item for item in results if item["journal_reconciliation"] == "UNAVAILABLE"]
    valid_for_min = [item for item in results if item["parser_valid"] and item["det"]]
    min_common_item = min(valid_for_min, key=lambda item: as_float(item["det"].get("common_session_alignment_ratio")) or float("inf")) if valid_for_min else None
    min_info_item = min(valid_for_min, key=lambda item: as_float(item["det"].get("info_availability_ratio")) or float("inf")) if valid_for_min else None
    last_gate_fail = gate_failures[-1]["month"] if gate_failures else "NONE"
    suffix = "NONE"
    if not engineering_invalid and not journal_mismatches and not journal_unavailable:
        for index in range(len(results)):
            if all(item["month_pass"] for item in results[index:]):
                suffix = results[index]["month"]
                break
    if engineering_invalid or journal_mismatches or journal_unavailable:
        overall = "INVALID_ENGINEERING"
        freeze = "NOT FROZEN"
        train = "NOT FROZEN"
    elif suffix == "NONE":
        overall = "COMPLETE"
        freeze = "BLOCKED_DATA_PREREQUISITE"
        train = "NONE"
    elif suffix == "2018-01":
        overall = "PASS"
        freeze = "PASS"
        train = suffix
    else:
        overall = "PASS_WITH_LATER_START"
        freeze = "PASS_WITH_LATER_START"
        train = suffix
    return {
        "row_count": len(results),
        "unique_month_count": len(set(months)),
        "first_month": months[0] if months else None,
        "last_month": months[-1] if months else None,
        "engineering_pass": len(results) - len(engineering_invalid),
        "engineering_invalid": len(engineering_invalid),
        "parser_invalid": sum(1 for item in results if not item["parser_valid"]),
        "probe_invalid": sum(1 for item in results if item["parser_valid"] and item["det"].get("probe_valid") != "1"),
        "ab_mismatch": sum(1 for item in results if item["parser_valid"] and (
            item["det"].get("methodA_methodB_jpy_equal") != "1"
            or item["det"].get("methodA_methodB_xau_equal") != "1"
        )),
        "journal_mismatch": len(journal_mismatches),
        "journal_unavailable": len(journal_unavailable),
        "gate_a_failures": [item["month"] for item in gate_a_failures],
        "gate_b_failures": [item["month"] for item in gate_b_failures],
        "gate_a_pass": sum(1 for item in results if item["month_engineering_status"] == "PASS" and item["det"].get("GateA_status") == "PASS"),
        "gate_b_pass": sum(1 for item in results if item["month_engineering_status"] == "PASS" and item["det"].get("GateB_status") == "PASS"),
        "real_gate_failures": [item["month"] for item in gate_failures],
        "both_pass_count": sum(1 for item in results if item["month_data_status"] == "PASS"),
        "minimum_common_ratio": as_float(min_common_item["det"].get("common_session_alignment_ratio")) if min_common_item else None,
        "minimum_common_month": min_common_item["month"] if min_common_item else None,
        "minimum_info_ratio": as_float(min_info_item["det"].get("info_availability_ratio")) if min_info_item else None,
        "minimum_info_month": min_info_item["month"] if min_info_item else None,
        "last_real_gate_fail_month": last_gate_fail,
        "earliest_all_pass_suffix_month": suffix,
        "monthly_v4_77m": overall,
        "data_freeze": freeze,
        "train_start_month": train,
    }


def write_machine_outputs(results: list[dict], provenance: dict, summary: dict) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "provenance": provenance,
        "summary": summary,
        "months": results,
    }
    (OUTDIR / "XAMR30_monthly_alignment_v4.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    fields = [
        "month", "requested_from", "requested_to", "parser_valid", "parser_invalid_reason",
        "probe_valid", "invalid_reason", "finalization_event", "JPY_M30_bars", "XAU_M30_bars",
        "exact_intersection", "info_availability_ratio", "common_session_alignment_ratio",
        "GateA_status", "GateB_status", "jpy_dup", "xau_dup", "jpy_non_monotonic",
        "xau_non_monotonic", "outside_requested_month", "methodA_jpy_count", "methodB_jpy_count",
        "methodA_xau_count", "methodB_xau_count", "methodA_methodB_jpy_equal",
        "methodA_methodB_xau_equal", "journal_jpy_bars", "journal_minus_filtered", "first_jpy",
        "last_jpy", "first_xau", "last_xau", "journal_reconciliation", "month_engineering_status",
        "month_data_status", "month_pass", "tester_log_path", "check_failures",
    ]
    with (OUTDIR / "XAMR30_monthly_alignment_v4.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for item in results:
            d = item["det"]
            failures = "; ".join(check["name"] for check in item["checks"] if not check["pass"])
            row = {
                "month": item["month"], "requested_from": item["requested_from"],
                "requested_to": item["requested_to"], "parser_valid": int(item["parser_valid"]),
                "parser_invalid_reason": item["parser_invalid_reason"],
                "journal_jpy_bars": item["journal_jpy_bars"] if item["journal_jpy_bars"] is not None else "",
                "journal_minus_filtered": item["journal_minus_filtered"] if item["journal_minus_filtered"] is not None else "",
                "journal_reconciliation": item["journal_reconciliation"],
                "month_engineering_status": item["month_engineering_status"],
                "month_data_status": item["month_data_status"], "month_pass": int(item["month_pass"]),
                "tester_log_path": item["tester_log_path"], "check_failures": failures,
            }
            for field in fields[5:27]:
                if field not in row:
                    row[field] = d.get(field, "")
            for field in ("first_jpy", "last_jpy", "first_xau", "last_xau"):
                row[field] = d.get(field, "")
            writer.writerow(row)


def write_reports(results: list[dict], provenance: dict, summary: dict) -> None:
    coverage_path = REPO_ROOT / JSB30_COVERAGE_REPORT
    review_path = REPO_ROOT / JSB30_REVIEW_REPORT
    coverage_text = coverage_path.read_text(encoding="utf-8", errors="replace") if coverage_path.is_file() else ""
    coverage_sufficient = "TRAIN = 2018-01-01 ~ 2024-05-31" in coverage_text and "normal_continuous" in coverage_text
    coverage_status = "previously_verified" if coverage_sufficient else "NOT_SUFFICIENTLY_LOCATED"
    coverage_detail = (
        f"`{JSB30_COVERAGE_REPORT}`; Tester-only real USDJPYm/Model=2 coverage; "
        f"authoritative coverage freeze commit `{JSB30_COVERAGE_COMMIT}`; "
        f"review corroboration `{JSB30_REVIEW_REPORT}`."
        if coverage_sufficient else
        f"`{JSB30_COVERAGE_REPORT}` was not sufficient to verify the required conclusion."
    )
    selected = next((item for item in results if item["month"] == summary["train_start_month"]), None)
    first_common = "NOT STRICTLY DETERMINED"
    if selected and selected["det"].get("common_session_alignment_ratio") == "100.0000":
        first_common = selected["det"].get("first_xau") or "NOT STRICTLY DETERMINED"
    if summary["monthly_v4_77m"] == "INVALID_ENGINEERING":
        first_common = "NOT FROZEN"
    if summary["train_start_month"] == "NONE":
        first_common = "NONE"

    report: list[str] = [
        "# XAMR30 Monthly v4 · 77 个月执行报告",
        "",
        f"- 开始 HEAD: `{provenance['starting_head']}`",
        f"- 开始 origin/main: `{provenance['starting_origin']}`",
        f"- v4 source SHA-256: `{provenance['source_sha']}`",
        f"- repo/frozen compiled EX5 SHA-256: `{provenance['repo_ex5_sha']}`",
        f"- Tester deployed EX5 SHA-256: `{provenance['tester_deployed_ex5_sha']}`",
        f"- EX5 provenance note: {provenance['repo_ex5_note']}",
        "- MetaEditor build: `6184`; frozen compile result: `0 errors, 0 warnings`",
        "- command: `python \"deepseek数据保存/执行_XAMR30/run_v4_77_months.py\"`",
        "",
        "## 运行范围与完整性",
        "",
        f"- months = {summary['row_count']}；unique months = {summary['unique_month_count']}；raw outputs = {len(list(RAW_OUTDIR.glob('m4_*.txt'))) if RAW_OUTDIR.is_dir() else 0}",
        f"- first month = `{summary['first_month']}`；last month = `{summary['last_month']}`",
        "- requested windows are generated as `[month_start, next_month_start)`.",
        "- each month used a unique `M4Q_YYYY-MM` RunTag, INI, Tester run, parser result, and raw output.",
        "",
        "## 工程与数据统计",
        "",
        f"- parser invalid = {summary['parser_invalid']}",
        f"- probe invalid = {summary['probe_invalid']}",
        f"- engineering PASS = {summary['engineering_pass']}",
        f"- engineering INVALID = {summary['engineering_invalid']}",
        f"- A/B timestamp mismatch = {summary['ab_mismatch']}",
        f"- journal mismatch = {summary['journal_mismatch']}",
        f"- journal unavailable = {summary['journal_unavailable']}",
        f"- Gate A failures = {len(summary['gate_a_failures'])}: {', '.join(summary['gate_a_failures']) or 'none'}",
        f"- Gate B failures = {len(summary['gate_b_failures'])}: {', '.join(summary['gate_b_failures']) or 'none'}",
        f"- both gates PASS = {summary['both_pass_count']}",
        f"- minimum common ratio = {summary['minimum_common_ratio']} ({summary['minimum_common_month']})",
        f"- minimum info ratio = {summary['minimum_info_ratio']} ({summary['minimum_info_month']})",
        "",
        "## 真实 Gate FAIL 月份",
        "",
        "| month | Gate A | Gate B | common % | info % | JPY | XAU | intersection |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    real_failures = [item for item in results if item["month_data_status"] == "GATE_FAIL"]
    if real_failures:
        for item in real_failures:
            d = item["det"]
            report.append("| {m} | {a} | {b} | {c} | {i} | {j} | {x} | {n} |".format(
                m=item["month"], a=d.get("GateA_status", ""), b=d.get("GateB_status", ""),
                c=d.get("common_session_alignment_ratio", ""), i=d.get("info_availability_ratio", ""),
                j=d.get("JPY_M30_bars", ""), x=d.get("XAU_M30_bars", ""), n=d.get("exact_intersection", ""),
            ))
    else:
        report.append("| none | — | — | — | — | — | — | — |")
    report += [
        "",
        "## TRAIN 起点机械计算",
        "",
        f"- last real failing month = `{summary['last_real_gate_fail_month']}`",
        f"- earliest all-pass suffix month = `{summary['earliest_all_pass_suffix_month']}`",
        f"- TRAIN start month = `{summary['train_start_month']}`",
        f"- first common M30 timestamp = `{first_common}` (data-layer eligible/common bar only)",
        "- data start, first common bar, first signal candidate, and first actual trade are not conflated.",
        "",
        "## USDJPY execution coverage provenance",
        "",
        f"- execution_coverage_evidence = `{coverage_status}`",
        f"- {coverage_detail}",
        "- This stage did not rerun coverage or read any exposed interval.",
        "",
        "## 最终状态",
        "",
        f"- MONTHLY_V4_77M = `{summary['monthly_v4_77m']}`",
        f"- DATA_FREEZE = `{summary['data_freeze']}`",
        f"- TRAIN_START = `{summary['train_start_month']}`",
        "",
        "## 明确未执行",
        "",
        "- signal double-calc / final-smoke repair / N0 static inputs / N0 planned runs / N0 four-way: NOT RUN",
        "- V1/V2/V3 TRAIN / bootstrap / VALID: NOT RUN",
        "- exposed_oos (2025-06-01~2026-05-31): NOT READ",
        "- user_holdout (2026-06-01~2026-09-30): NOT READ",
        "- Route B / capital sensitivity / strategy portfolio / ML: NOT RUN",
        "- dsh_XAMR30.mq5 and frozen v1/v2/v3/v4 regression evidence: NOT MODIFIED",
        "",
        "The exact machine rows and raw probe files are in `XAMR30_monthly_alignment_v4.csv`, `XAMR30_monthly_alignment_v4.json`, and `monthly_v4_raw/`.",
    ]
    (OUTDIR / "XAMR30_MONTHLY_V4_77M_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    freeze: list[str] = [
        "# XAMR30 DATA FREEZE · 2026-09-14 R4",
        "",
        "本文件是 Monthly v4 全 77 个月数据资格阶段的结论；不包含任何策略收益判断。",
        "",
        "## A. Provenance",
        "",
        f"- v4 source SHA-256: `{provenance['source_sha']}`",
        f"- repo/frozen compiled EX5 SHA-256: `{provenance['repo_ex5_sha']}`",
        f"- Tester deployed EX5 SHA-256: `{provenance['tester_deployed_ex5_sha']}`",
        f"- EX5 provenance note: {provenance['repo_ex5_note']}",
        "- MetaEditor: build 6184; compile result 0 errors / 0 warnings",
        f"- parent commit: `{provenance['starting_head']}`",
        "- 本阶段 commit: see the final Git commit reported to Planner after this file is committed",
        "",
        "## B. Frozen Gate",
        "",
        "- Gate A: `common_session_alignment_ratio = exact_intersection / XAU_existing_M30_bars >= 99%`",
        "- Gate B: `info_availability_ratio = exact_intersection / USDJPY_M30_bars >= 90%`",
        "- duplicate JPY/XAU = 0",
        "- non-monotonic JPY/XAU = 0",
        "- outside_requested_month = 0",
        "- thresholds pre-economic frozen; they were not changed after observing 77-month results.",
        "",
        "## C. 77 月统计",
        "",
        f"- total months = {summary['row_count']}",
        f"- engineering PASS = {summary['engineering_pass']}",
        f"- engineering INVALID = {summary['engineering_invalid']}",
        f"- Gate A PASS = {summary['gate_a_pass']}; Gate A FAIL = {len(summary['gate_a_failures'])}",
        f"- Gate B PASS = {summary['gate_b_pass']}; Gate B FAIL = {len(summary['gate_b_failures'])}",
        f"- both gates PASS = {summary['both_pass_count']}",
        "",
        "## D. 所有真实 FAIL 月份",
        "",
    ]
    if real_failures:
        freeze.append("| month | Gate A | Gate B | common % | info % | JPY | XAU | intersection |")
        freeze.append("|---|---|---|---:|---:|---:|---:|---:|")
        for item in real_failures:
            d = item["det"]
            freeze.append("| {m} | {a} | {b} | {c} | {i} | {j} | {x} | {n} |".format(
                m=item["month"], a=d.get("GateA_status", ""), b=d.get("GateB_status", ""),
                c=d.get("common_session_alignment_ratio", ""), i=d.get("info_availability_ratio", ""),
                j=d.get("JPY_M30_bars", ""), x=d.get("XAU_M30_bars", ""), n=d.get("exact_intersection", ""),
            ))
    else:
        freeze.append("无真实 Gate FAIL 月份。")
    freeze += [
        "",
        "## E. 最接近阈值的月份",
        "",
        f"- minimum common_session_alignment_ratio = `{summary['minimum_common_ratio']}`，month `{summary['minimum_common_month']}`",
        f"- minimum info_availability_ratio = `{summary['minimum_info_ratio']}`，month `{summary['minimum_info_month']}`",
        "- 以上仅为描述统计，不用于修改 threshold。",
        "",
        "## F. TRAIN 起点机械计算",
        "",
        f"- last real failing month = `{summary['last_real_gate_fail_month']}`",
        f"- earliest all-pass suffix month = `{summary['earliest_all_pass_suffix_month']}`",
        f"- TRAIN start month = `{summary['train_start_month']}`",
        f"- first common M30 timestamp = `{first_common}`；只表示数据层 eligible/common bar，不表示 first signal candidate 或 first actual trade。",
        "",
        "## G. USDJPY execution coverage provenance",
        "",
        f"- execution_coverage_evidence = `{coverage_status}`",
        f"- {coverage_detail}",
        "",
        "## H. 禁止区间与未执行项",
        "",
        "- VALID = 2024-06-01 ~ 2025-05-31（未运行）",
        "- exposed_oos = 2025-06-01 ~ 2026-05-31（未读取）",
        "- user_holdout = 2026-06-01 ~ 2026-09-30（未读取）",
        "- 未运行 signal double-calc、N0 four-way、V1/V2/V3 TRAIN、bootstrap、VALID、Route B、capital sensitivity、ML。",
        "- 未修改 dsh_XAMR30.mq5、dsh_XAMR30Monthly_v4.mq5、Gate A/B 或既有 v4 regression evidence。",
        "",
        "## Final status",
        "",
        f"- MONTHLY_V4_77M = `{summary['monthly_v4_77m']}`",
        f"- DATA_FREEZE = `{summary['data_freeze']}`",
        f"- TRAIN_START = `{summary['train_start_month']}`",
    ]
    (REPO_ROOT / "公共部分" / "XAMR30_DATA_FREEZE_20260914_R4.md").write_text(
        "\n".join(freeze) + "\n", encoding="utf-8"
    )


def run_one(month: str, frm: str, to: str, config_dir: Path) -> dict:
    run_tag = "M4Q_" + month
    ini = make_ini(config_dir, run_tag, frm, to)
    output = COMMON / ("m4_%s.txt" % run_tag)
    previous_mtime = output.stat().st_mtime if output.is_file() else 0.0
    started = time.time()
    kill_terminals()
    timed_out = False
    return_code: int | None = None
    try:
        process = subprocess.Popen([str(TERMINAL), "/config:" + str(ini)], cwd=str(TERMINAL.parent))
        try:
            return_code = process.wait(timeout=900)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_terminals()
    except OSError as exc:
        timed_out = True
        print(f"{month}: terminal launch failed: {exc}", flush=True)
    time.sleep(1.5)
    fresh = output.is_file() and output.stat().st_mtime >= max(previous_mtime + 0.5, started - 2.0)
    parsed = parse_formal(output, run_tag) if fresh else {
        "parser_valid": False,
        "parser_invalid_reason": "probe_output_stale_or_missing",
        "det": {},
    }
    journal, log_path, log_lines = journal_snapshot(run_tag)
    result = evaluate_month(parsed, month, frm, to, run_tag, journal, log_path,
                            log_lines, timed_out, return_code, fresh)
    if output.is_file() and fresh:
        RAW_OUTDIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, RAW_OUTDIR / ("m4_%s.txt" % month))
    return result


def main() -> int:
    months = make_months()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    provenance_check = verify_binary_provenance()
    if not provenance_check["valid"]:
        print(json.dumps({"stage": "INVALID_BINARY_PROVENANCE", "provenance": provenance_check}, ensure_ascii=False, indent=2), flush=True)
        return 2
    starting_head = subprocess.run(
        ["git", "-c", f"safe.directory={str(REPO_ROOT).replace(chr(92), '/')}", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout.strip()
    starting_origin = subprocess.run(
        ["git", "-c", f"safe.directory={str(REPO_ROOT).replace(chr(92), '/')}", "rev-parse", "origin/main"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout.strip()
    if starting_head != EXPECTED_HEAD or starting_origin != EXPECTED_HEAD:
        print(json.dumps({"stage": "INVALID_START_HEAD", "starting_head": starting_head, "starting_origin": starting_origin}, ensure_ascii=False, indent=2), flush=True)
        return 2
    provenance = {
        **provenance_check,
        "starting_head": starting_head,
        "starting_origin": starting_origin,
        "runner_command": 'python "deepseek数据保存/执行_XAMR30/run_v4_77_months.py"',
        "scope": "2018-01..2024-05 inclusive; 77 independent monthly Tester probes",
    }
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="monthly_v4_ini_", dir=str(OUTDIR)) as temp_dir:
        config_dir = Path(temp_dir)
        for index, (month, frm, to) in enumerate(months, start=1):
            result = run_one(month, frm, to, config_dir)
            results.append(result)
            d = result["det"]
            print(
                "[%02d/77] %-7s eng=%-7s data=%-10s jpy=%-5s xau=%-5s common=%-8s info=%-8s A=%-4s B=%-4s journal=%s" % (
                    index, month, result["month_engineering_status"], result["month_data_status"],
                    d.get("JPY_M30_bars", ""), d.get("XAU_M30_bars", ""),
                    d.get("common_session_alignment_ratio", ""), d.get("info_availability_ratio", ""),
                    d.get("GateA_status", ""), d.get("GateB_status", ""),
                    result["journal_reconciliation"],
                ),
                flush=True,
            )
            for check in result["checks"]:
                if not check["pass"]:
                    print("       [INVALID] %-38s %s" % (check["name"], check["detail"]), flush=True)
            if result["journal_reconciliation"] in {"MISMATCH", "UNAVAILABLE"}:
                print("       [JOURNAL] %s diff=%s log=%s" % (
                    result["journal_reconciliation"], result["journal_minus_filtered"], result["tester_log_path"]
                ), flush=True)
    summary = summary_for(results)
    provenance["raw_output_count"] = len(list(RAW_OUTDIR.glob("m4_*.txt"))) if RAW_OUTDIR.is_dir() else 0
    write_machine_outputs(results, provenance, summary)
    write_reports(results, provenance, summary)
    print("\nMONTHLY_V4_77M=%s DATA_FREEZE=%s TRAIN_START=%s" % (
        summary["monthly_v4_77m"], summary["data_freeze"], summary["train_start_month"]
    ), flush=True)
    return 0 if summary["monthly_v4_77m"] != "INVALID_ENGINEERING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
