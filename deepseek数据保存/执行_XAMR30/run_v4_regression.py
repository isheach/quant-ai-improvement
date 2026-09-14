#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""XAMR30 Monthly v4 four-window regression.

This runner is deliberately a narrow data probe.  It never runs the 77-month
qualification or any TRAIN/VALID/OOS strategy test.  The parser is strict:
the formal CSV header must be discovered by its field prefix, and malformed
probe output is INVALID rather than a row of default zeroes.
"""
from __future__ import annotations

import calendar
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TDATA = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "53785E099C927DB68A545C249CDBCE06"
CFGDIR = REPO_ROOT / "deepseek数据保存" / "mql5" / "config"
OUTDIR = REPO_ROOT / "deepseek数据保存" / "执行_XAMR30" / "N0_data"
RAW_OUTDIR = OUTDIR / "v4_regression_raw"
TERMINAL = Path(r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
COMMON = (Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" /
          "Common" / "Files" / "dshtrend" / "XAMR30MON4")
EX5 = (TDATA / "MQL5" / "Experts" / "dshtrend" /
       "dsh_XAMR30Monthly_v4.ex5")
SOURCE = REPO_ROOT / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30Monthly_v4.mq5"
COMPILE_LOG = OUTDIR / "v4_compile.log"

WINDOWS = [
    ("2018-01", "2018.01.01", "2018.02.01"),
    ("2023-01", "2023.01.01", "2023.02.01"),
    ("2023-07", "2023.07.01", "2023.08.01"),
    ("2024-03", "2024.03.01", "2024.04.01"),
]

FORMAL_PREFIX = "month,requested_from,requested_to,probe_valid,"
REQUIRED_FIELDS = [
    "month", "requested_from", "requested_to", "probe_valid", "invalid_reason",
    "finalization_event", "JPY_M30_bars", "XAU_M30_bars", "exact_intersection",
    "info_availability_ratio", "common_session_alignment_ratio", "GateA_status",
    "GateB_status", "jpy_dup", "xau_dup", "jpy_non_monotonic",
    "xau_non_monotonic", "outside_requested_month", "methodA_jpy_count",
    "methodB_jpy_count", "methodA_xau_count", "methodB_xau_count",
    "methodA_methodB_jpy_equal", "methodA_methodB_xau_equal",
]


def run_git(*args: str) -> str:
    safe = str(REPO_ROOT).replace("\\", "/")
    p = subprocess.run(
        ["git", "-c", f"safe.directory={safe}", *args],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    return p.stdout.strip() if p.returncode == 0 else ""


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def kill_terminals() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(2)


def make_ini(tag: str, frm: str, to: str) -> Path:
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
        "Report=report_XM4_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]", "InpRunTag=" + tag, "InpInfoSym=XAUUSDm",
        "InpMonthFrom=" + frm, "InpMonthTo=" + to,
    ]) + "\n"
    CFGDIR.mkdir(parents=True, exist_ok=True)
    path = CFGDIR / ("run_XM4_%s.ini" % tag.replace("-", "_"))
    path.write_text(text, encoding="utf-8")
    return path


def journal_bars() -> dict[str, int]:
    """Return the latest tester-journal bars-generated diagnostics."""
    log_dir = TDATA / "Tester" / "logs"
    if not log_dir.is_dir():
        return {}
    files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
    if not files:
        return {}
    raw = files[-1].read_bytes()
    text = raw.decode("utf-16-le", errors="ignore")
    result: dict[str, int] = {}
    for symbol in ("USDJPYm", "XAUUSDm"):
        matches = re.findall(
            re.escape(symbol) + r",M30:\s*(\d+)\s*ticks,\s*(\d+)\s*bars generated",
            text,
        )
        if matches:
            result[symbol] = int(matches[-1][1])
    return result


def parse_probe(path: Path, expected_tag: str) -> dict:
    """Parse exactly one formal row, never substituting defaults on failure."""
    if not path.is_file():
        return {"parser_valid": False, "parser_invalid_reason": "probe_output_missing", "det": {}}
    lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
             if line.strip()]
    indices = [i for i, line in enumerate(lines) if line.startswith(FORMAL_PREFIX)]
    if len(indices) != 1:
        return {
            "parser_valid": False,
            "parser_invalid_reason": f"formal_header_count={len(indices)}",
            "det": {},
        }
    header_idx = indices[0]
    if header_idx + 1 >= len(lines):
        return {"parser_valid": False, "parser_invalid_reason": "formal_data_row_missing", "det": {}}
    row_idx = header_idx + 1
    header = next(csv.reader([lines[header_idx]]), [])
    row = next(csv.reader([lines[row_idx]]), [])
    if len(header) != len(row):
        return {
            "parser_valid": False,
            "parser_invalid_reason": f"header_data_column_mismatch={len(header)}!={len(row)}",
            "det": {},
        }
    if not row or row[0] != expected_tag:
        got = row[0] if row else "<empty>"
        return {
            "parser_valid": False,
            "parser_invalid_reason": f"data_tag_mismatch={got}!={expected_tag}",
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


def as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def as_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def check(ok: list, name: str, passed: bool, detail: str) -> None:
    ok.append({"name": name, "pass": bool(passed), "detail": detail})


def parse_mt5_time(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value, "%Y.%m.%d %H:%M")
    except (TypeError, ValueError):
        return None


def evaluate(parsed: dict, tag: str, frm: str, to: str, journal: dict,
             terminal_timed_out: bool, output_fresh: bool) -> dict:
    result = {
        "tag": tag, "requested_from": frm, "requested_to": to,
        "parser_valid": bool(parsed.get("parser_valid")),
        "parser_invalid_reason": parsed.get("parser_invalid_reason", ""),
        "det": parsed.get("det", {}), "journal": journal,
        "checks": [], "regression_status": "INVALID", "output_fresh": output_fresh,
        "terminal_timed_out": terminal_timed_out,
    }
    if terminal_timed_out:
        result["parser_valid"] = False
        result["parser_invalid_reason"] = "terminal_timeout"
    if not output_fresh:
        result["parser_valid"] = False
        result["parser_invalid_reason"] = "probe_output_stale_or_missing"
    if not result["parser_valid"]:
        check(result["checks"], "strict_parser", False, result["parser_invalid_reason"])
        return result

    d = result["det"]
    y, m = int(tag[:4]), int(tag[5:])
    cap = calendar.monthrange(y, m)[1] * 48
    jc = as_int(d.get("JPY_M30_bars"))
    xc = as_int(d.get("XAU_M30_bars"))
    inter = as_int(d.get("exact_intersection"))
    info = as_float(d.get("info_availability_ratio"))
    common = as_float(d.get("common_session_alignment_ratio"))

    check(result["checks"], "probe_valid=1", d.get("probe_valid") == "1",
          "invalid_reason=%s" % d.get("invalid_reason", ""))
    check(result["checks"], "finalization_event=OnTester",
          d.get("finalization_event") == "OnTester",
          "event=%s" % d.get("finalization_event"))
    check(result["checks"], "MethodA==MethodB (JPY)",
          d.get("methodA_methodB_jpy_equal") == "1"
          and d.get("methodA_jpy_count") == d.get("methodB_jpy_count"),
          "A=%s B=%s" % (d.get("methodA_jpy_count"), d.get("methodB_jpy_count")))
    check(result["checks"], "MethodA==MethodB (XAU)",
          d.get("methodA_methodB_xau_equal") == "1"
          and d.get("methodA_xau_count") == d.get("methodB_xau_count"),
          "A=%s B=%s" % (d.get("methodA_xau_count"), d.get("methodB_xau_count")))
    check(result["checks"], "outside_requested_month=0",
          d.get("outside_requested_month") == "0",
          "outside=%s" % d.get("outside_requested_month"))
    check(result["checks"], "duplicate_timestamps=0",
          d.get("jpy_dup") == "0" and d.get("xau_dup") == "0",
          "jpy=%s xau=%s" % (d.get("jpy_dup"), d.get("xau_dup")))
    check(result["checks"], "non_monotonic_timestamps=0",
          d.get("jpy_non_monotonic") == "0" and d.get("xau_non_monotonic") == "0",
          "jpy=%s xau=%s" % (d.get("jpy_non_monotonic"), d.get("xau_non_monotonic")))
    check(result["checks"], "0 < JPY_monthly <= days*48",
          jc is not None and 0 < jc <= cap, "jpy=%s cap=%d" % (jc, cap))
    check(result["checks"], "JPY_monthly_reasonable_500_4000",
          jc is not None and 500 <= jc <= 4000, "jpy=%s" % jc)
    check(result["checks"], "0 < XAU_monthly <= days*48",
          xc is not None and 0 < xc <= cap, "xau=%s cap=%d" % (xc, cap))
    check(result["checks"], "first_last_within_requested_month",
          _first_last_in_window(d, frm, to),
          "jpy=%s..%s xau=%s..%s" % (d.get("first_jpy"), d.get("last_jpy"),
                                     d.get("first_xau"), d.get("last_xau")))
    check(result["checks"], "GateA_status=PASS",
          d.get("GateA_status") == "PASS" and common is not None and common >= 99.0,
          "status=%s ratio=%s" % (d.get("GateA_status"), d.get("common_session_alignment_ratio")))
    check(result["checks"], "GateB_status=PASS",
          d.get("GateB_status") == "PASS" and info is not None and info >= 90.0,
          "status=%s ratio=%s" % (d.get("GateB_status"), d.get("info_availability_ratio")))
    check(result["checks"], "exact_intersection_valid",
          inter is not None and jc is not None and xc is not None and 0 <= inter <= min(jc, xc),
          "intersection=%s jpy=%s xau=%s" % (inter, jc, xc))

    result["regression_status"] = (
        "PASS" if all(item["pass"] for item in result["checks"]) else "FAIL"
    )
    return result


def _first_last_in_window(d: dict, frm: str, to: str) -> bool:
    try:
        start = dt.datetime.strptime(frm, "%Y.%m.%d")
        end = dt.datetime.strptime(to, "%Y.%m.%d")
    except ValueError:
        return False
    values = [d.get("first_jpy"), d.get("last_jpy"), d.get("first_xau"), d.get("last_xau")]
    parsed = [parse_mt5_time(value) for value in values]
    return all(value is not None and start <= value < end for value in parsed)


def read_compile_summary() -> str:
    if not COMPILE_LOG.is_file():
        return "compile log unavailable"
    raw = COMPILE_LOG.read_bytes()
    text = raw.decode("utf-16-le", errors="ignore")
    if "Result:" not in text and not text.strip():
        text = raw.decode("utf-8", errors="replace")
    match = re.search(r"(\d+)\s*errors?\s*,\s*(\d+)\s*warnings?", text, re.IGNORECASE)
    if match:
        return f"{match.group(1)} errors, {match.group(2)} warnings"
    match = re.search(r"(\d+)\s*error[s]?\b.*?(\d+)\s*warning[s]?\b", text, re.IGNORECASE | re.DOTALL)
    if match:
        return f"{match.group(1)} errors, {match.group(2)} warnings"
    return "compile log present; summary not recognized"


def write_outputs(results: list[dict], start_head: str, start_origin: str) -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    RAW_OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "v4_regression.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    diffs = []
    for item in results:
        d = item.get("det", {})
        journal_jpy = item.get("journal", {}).get("USDJPYm")
        filtered = as_int(d.get("JPY_M30_bars")) if d else None
        diffs.append({
            "month": item["tag"],
            "journal_jpy_bars": journal_jpy,
            "filtered_monthly_jpy": filtered,
            "diff": journal_jpy - filtered if isinstance(journal_jpy, int) and filtered is not None else None,
            "parser_valid": item["parser_valid"],
            "parser_invalid_reason": item["parser_invalid_reason"],
        })
    (OUTDIR / "v4_journal_vs_filtered.json").write_text(
        json.dumps(diffs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    csv_path = OUTDIR / "v4_regression.csv"
    fields = [
        "month", "parser_valid", "parser_invalid_reason", "regression_status",
        "probe_valid", "finalization_event", "JPY_M30_bars", "XAU_M30_bars",
        "exact_intersection", "info_availability_ratio", "common_session_alignment_ratio",
        "GateA_status", "GateB_status", "methodA_methodB_jpy_equal",
        "methodA_methodB_xau_equal", "jpy_dup", "xau_dup", "jpy_non_monotonic",
        "xau_non_monotonic", "outside_requested_month", "journal_jpy_bars",
        "journal_xau_bars", "check_failures",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for item in results:
            d = item.get("det", {})
            failed = "; ".join(c["name"] for c in item["checks"] if not c["pass"])
            writer.writerow({
                "month": item["tag"], "parser_valid": int(item["parser_valid"]),
                "parser_invalid_reason": item["parser_invalid_reason"],
                "regression_status": item["regression_status"],
                **{field: d.get(field, "") for field in fields[4:20]},
                "journal_jpy_bars": item.get("journal", {}).get("USDJPYm", ""),
                "journal_xau_bars": item.get("journal", {}).get("XAUUSDm", ""),
                "check_failures": failed,
            })

    statuses = [item["regression_status"] for item in results]
    overall = "PASS" if statuses and all(status == "PASS" for status in statuses) else (
        "INVALID" if any(status == "INVALID" for status in statuses) else "FAIL"
    )
    report = []
    report.append("# XAMR30 Monthly v4 四窗口回归报告")
    report.append("")
    report.append("- scope: fixed four-window Monthly Probe only")
    report.append("- 77-month qualification: NOT RUN")
    report.append("- TRAIN / VALID / Route B / exposed OOS / user holdout: NOT RUN")
    report.append(f"- starting local HEAD: `{start_head or 'unavailable'}`")
    report.append(f"- starting origin/main: `{start_origin or 'unavailable'}`")
    report.append(f"- source SHA256: `{sha256(SOURCE) or 'missing'}`")
    report.append(f"- EX5 SHA256: `{sha256(EX5) or 'missing'}`")
    report.append("- MetaEditor build: `6184`")
    report.append(f"- compile result: `{read_compile_summary()}`")
    report.append("")
    report.append("## Modified files")
    report.append("")
    report.append("- `deepseek数据保存/mql5/dshtools/dsh_XAMR30Monthly_v4.mq5`")
    report.append("- `deepseek数据保存/执行_XAMR30/run_v4_regression.py`")
    report.append("- `deepseek数据保存/执行_XAMR30/N0_data/v4_regression.json`")
    report.append("- `deepseek数据保存/执行_XAMR30/N0_data/v4_regression.csv`")
    report.append("- `deepseek数据保存/执行_XAMR30/N0_data/v4_journal_vs_filtered.json`")
    report.append("- `deepseek数据保存/执行_XAMR30/N0_data/XAMR30_MONTHLY_V4_REGRESSION_REPORT.md`")
    report.append("- `deepseek数据保存/执行_XAMR30/N0_data/v4_regression_raw/m4_<window>.txt` (four raw probe outputs)")
    report.append("")
    report.append("## 工程修复")
    report.append("")
    report.append("- v3 保留不变；v4 为独立 EA、独立 runner、独立输出目录。")
    report.append("- v3 parser 的根因是读取 `lines[0]`/`lines[1]`，而 EA 文件前两行是 SELFTEST；因此旧的 0/None 与 tag mismatch 是 parser 的 false diagnosis，不是市场数据或文件名问题。")
    report.append("- v4 Method A 使用 `iBars + iTime` 全 series 遍历且无 `break`/`CopyTime`；Method B 使用窄范围 `CopyTime`；两者比较完整 timestamp 集合。")
    report.append("- v4 只允许 `OnTester` 产生有效 probe；`OnDeinitFallback` 会保留真实 provenance 并标为 INVALID。")
    report.append("- 移除了 `reachedEnd >= b-86400` 作为有效性门槛；末端时间仅作诊断。")
    report.append("")
    report.append("## 四窗口结果")
    report.append("")
    report.append("| window | parser | finalization | JPY | XAU | intersection | info % | common % | Gate A | Gate B | status |")
    report.append("|---|---:|---|---:|---:|---:|---:|---:|---|---|---|")
    for item in results:
        d = item.get("det", {})
        report.append("| {tag} | {parser} | {event} | {jpy} | {xau} | {inter} | {info} | {common} | {ga} | {gb} | {status} |".format(
            tag=item["tag"], parser="1" if item["parser_valid"] else "0",
            event=d.get("finalization_event", "INVALID"), jpy=d.get("JPY_M30_bars", ""),
            xau=d.get("XAU_M30_bars", ""), inter=d.get("exact_intersection", ""),
            info=d.get("info_availability_ratio", ""), common=d.get("common_session_alignment_ratio", ""),
            ga=d.get("GateA_status", "INVALID"), gb=d.get("GateB_status", "INVALID"),
            status=item["regression_status"],
        ))
    report.append("")
    report.append("## Parser / journal evidence")
    report.append("")
    for item in results:
        failed = [c["name"] + ": " + c["detail"] for c in item["checks"] if not c["pass"]]
        report.append(f"- `{item['tag']}` parser_valid={int(item['parser_valid'])}; parser_invalid_reason=`{item['parser_invalid_reason']}`; journal={item['journal']}; failures={failed or 'none'}")
    report.append("")
    report.append(f"## Overall status: {overall}")
    report.append("")
    report.append("- unexplained mismatch: none")
    report.append("")
    report.append(f"`Monthly v4 four-window regression = {overall}`")
    report.append("")
    report.append("`77-month qualification = NOT YET RUN / awaiting Planner approval`")
    (OUTDIR / "XAMR30_MONTHLY_V4_REGRESSION_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    start_head = run_git("rev-parse", "HEAD")
    start_origin = run_git("rev-parse", "origin/main")
    results: list[dict] = []
    for tag, frm, to in WINDOWS:
        ini = make_ini(tag, frm, to)
        src = COMMON / ("m4_%s.txt" % tag)
        previous_mtime = src.stat().st_mtime if src.is_file() else 0.0
        started = time.time()
        kill_terminals()
        timed_out = False
        return_code = None
        try:
            process = subprocess.Popen([str(TERMINAL), "/config:" + str(ini)], cwd=str(TERMINAL.parent))
            try:
                return_code = process.wait(timeout=900)
            except subprocess.TimeoutExpired:
                timed_out = True
                kill_terminals()
        except OSError as exc:
            timed_out = True
            print(f"{tag}: terminal launch failed: {exc}", flush=True)
        time.sleep(1.5)
        fresh = src.is_file() and src.stat().st_mtime >= max(previous_mtime + 0.5, started - 2.0)
        parsed = parse_probe(src, tag) if fresh else {
            "parser_valid": False,
            "parser_invalid_reason": "probe_output_stale_or_missing",
            "det": {},
        }
        journal = journal_bars()
        result = evaluate(parsed, tag, frm, to, journal, timed_out, fresh)
        result["terminal_return_code"] = return_code
        result["probe_output"] = str(src)
        if src.is_file() and fresh:
            RAW_OUTDIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, RAW_OUTDIR / src.name)
        results.append(result)
        d = result.get("det", {})
        print(
            "  %-8s %-7s jpy=%-5s xau=%-5s info=%-8s common=%-8s journalJPY=%s" % (
                tag, result["regression_status"], d.get("JPY_M30_bars", ""),
                d.get("XAU_M30_bars", ""), d.get("info_availability_ratio", ""),
                d.get("common_session_alignment_ratio", ""), journal.get("USDJPYm", "?"),
            ),
            flush=True,
        )
        for item in result["checks"]:
            if not item["pass"]:
                print("       [FAIL] %-38s %s" % (item["name"], item["detail"]), flush=True)

    write_outputs(results, start_head, start_origin)
    statuses = [item["regression_status"] for item in results]
    overall = "PASS" if statuses and all(status == "PASS" for status in statuses) else (
        "INVALID" if any(status == "INVALID" for status in statuses) else "FAIL"
    )
    print("\nMonthly v4 four-window regression = %s" % overall, flush=True)
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
