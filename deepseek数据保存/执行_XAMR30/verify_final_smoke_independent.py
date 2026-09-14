#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XAMR30 N1R3 FINAL_SMOKE_INDEPENDENT verifier.

This is a new, independent checker.  The historical verifier remains
untouched.  The only source of the held-bar count is the frozen USDJPYm M30
bar-open timestamp set exported by the R1/R2 Probe; no calendar-minute or
weekend approximation is used.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
FAM = REPO / "deepseek数据保存" / "执行_XAMR30"
SMOKE = FAM / "smoke"
OUT = FAM / "final_smoke_independent"
MANIFEST_PATH = FAM / "doublecalc_raw_manifest.json"
sys.path.insert(0, str(REPO / "deepseek数据保存" / "执行_第三批"))

WINDOWS = {
    "WINTER": ("DS260914_XAMR30_SMOKE_WINTER", 12),
    "DSTTR": ("DS260914_XAMR30_SMOKE_DSTTR", 10),
    "SUMMER": ("DS260914_XAMR30_SMOKE_SUMMER", 15),
}
EXPECTED_RAW_SHA = "B42DDBCA49C69DD2E23D8F5D22FFD53BAC6CBE452F095EECC7BD5DC458E05F47"


def parse_time(value: str | None) -> dt.datetime | None:
    if value is None:
        return None
    value = str(value).strip()
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def parse_html(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file():
        return {}
    try:
        from mt5_html_parser import parse_report

        return {
            key: value
            for key, value in (parse_report(str(path)).get("kv") or {}).items()
            if value not in (None, "")
        }
    except Exception:
        return {}


def check(name: str, ok: bool, detail: str = "") -> dict[str, object]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def raw_identity() -> tuple[dict[str, object], list[dt.datetime]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entry = next(item for item in manifest["files"] if item["symbol"] == "USDJPYm")
    path = Path(entry["path"])
    identity: dict[str, object] = {
        "manifest_path": str(MANIFEST_PATH),
        "path": str(path),
        "expected_sha256": entry["sha256"].upper(),
        "expected_first": entry["first"],
        "expected_last": entry["last"],
        "expected_bar_count": entry["bar_count"],
        "manifest_sha256_matches_planner": entry["sha256"].upper() == EXPECTED_RAW_SHA,
    }
    if not path.is_file():
        identity.update({"status": "INVALID_RAW_REFERENCE_MISSING", "exists": False})
        return identity, []

    actual_sha = sha256_file(path)
    timestamps: list[dt.datetime] = []
    with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
        for row in csv.DictReader(handle):
            parsed = parse_time(row.get("timestamp"))
            if parsed is not None:
                timestamps.append(parsed)

    actual_first = timestamps[0].strftime("%Y.%m.%d %H:%M:%S") if timestamps else ""
    actual_last = timestamps[-1].strftime("%Y.%m.%d %H:%M:%S") if timestamps else ""
    identity.update(
        {
            "exists": True,
            "actual_sha256": actual_sha,
            "actual_first": actual_first,
            "actual_last": actual_last,
            "actual_bar_count": len(timestamps),
        }
    )
    identity["status"] = (
        "PASS"
        if identity["manifest_sha256_matches_planner"]
        and actual_sha == entry["sha256"].upper()
        and actual_first == entry["first"]
        and actual_last == entry["last"]
        and len(timestamps) == entry["bar_count"]
        else "FAIL"
    )
    return identity, timestamps


def held_bars(bar_opens: list[dt.datetime], entry: dt.datetime, exit_: dt.datetime) -> list[dt.datetime]:
    return [
        bar_open
        for bar_open in bar_opens
        if bar_open + dt.timedelta(minutes=30) > entry
        and bar_open + dt.timedelta(minutes=30) <= exit_
    ]


def window_report(
    window: str,
    directory_name: str,
    expected_trades: int,
    bar_opens: list[dt.datetime],
) -> dict[str, object]:
    directory = SMOKE / directory_name
    trades_path = directory / "trades.csv"
    rows = read_csv(trades_path) if trades_path.is_file() else []
    selfcheck_rows = read_csv(directory / "audit_selfcheck.csv") if (directory / "audit_selfcheck.csv").is_file() else []
    reject_rows = read_csv(directory / "reject_audit.csv") if (directory / "reject_audit.csv").is_file() else []
    report_files = sorted(directory.glob("report_*.htm"))
    html = parse_html(report_files[0] if report_files else None)
    selfcheck = selfcheck_rows[0] if selfcheck_rows else {}
    checks: list[dict[str, object]] = []
    held_rows: list[dict[str, object]] = []

    checks.append(check("Bars>0", number(str(html.get("Bars"))) > 0, f"Bars={html.get('Bars', '')}"))
    checks.append(check("Deposit=500", abs(number(str(html.get("Initial Deposit"))) - 500) < 0.01, str(html.get("Initial Deposit", ""))))
    checks.append(check("Symbol=USDJPYm", str(html.get("Symbol", "")).strip() == "USDJPYm", str(html.get("Symbol", ""))))
    html_trades = int(number(str(html.get("Total Trades")), -1))
    checks.append(check("HTML trades == 审计行数", html_trades == len(rows), f"HTML={html_trades} 审计={len(rows)}"))
    checks.append(check("实际产生 closing deals", len(rows) == expected_trades, f"expected={expected_trades}, actual={len(rows)}"))
    checks.append(check("fatal=0", selfcheck.get("fatal") == "0", selfcheck.get("fatal", "?")))
    checks.append(check("audit_failed=0", selfcheck.get("audit_failed") == "0", selfcheck.get("audit_failed", "?")))
    checks.append(check("active_positions=0", selfcheck.get("active_positions") == "0", selfcheck.get("active_positions", "?")))

    bad_gap: list[str] = []
    bad_sequence: list[str] = []
    sequence_count = 0
    for row in rows:
        signal_open = parse_time(row.get("signal_bar_open_time"))
        signal_close = parse_time(row.get("signal_bar_close_time"))
        entry_bar_open = parse_time(row.get("entry_bar_open_time"))
        entry = parse_time(row.get("entry_time"))
        if None in (signal_open, signal_close, entry_bar_open, entry):
            continue
        sequence_count += 1
        if entry_bar_open - signal_open != dt.timedelta(minutes=30):
            bad_gap.append(row.get("deal_ticket", ""))
        if entry < signal_close:
            bad_sequence.append(row.get("deal_ticket", ""))
    checks.append(check("入场时序 entry_bar = signal_bar+30min", not bad_gap, f"抽查={sequence_count}, 违规={bad_gap[:3] or '无'}"))
    checks.append(check("入场时序 entry_time >= signal_close", not bad_sequence, f"违规={bad_sequence[:3] or '无'}"))
    checks.append(check("时序抽查（本窗口）", sequence_count == len(rows), f"{sequence_count}/{len(rows)}"))

    for row in rows:
        entry = parse_time(row.get("entry_time"))
        exit_ = parse_time(row.get("exit_time"))
        counted = held_bars(bar_opens, entry, exit_) if entry and exit_ else []
        record = {
            "window": window,
            "deal_ticket": row.get("deal_ticket", ""),
            "position_id": row.get("position_id", ""),
            "entry_time": row.get("entry_time", ""),
            "exit_time": row.get("exit_time", ""),
            "exit_reason": row.get("exit_reason", ""),
            "full_held_bars": len(counted),
            "first_counted_bar_open": counted[0].strftime("%Y.%m.%d %H:%M:%S") if counted else "",
            "last_counted_bar_open": counted[-1].strftime("%Y.%m.%d %H:%M:%S") if counted else "",
            "counted_bar_timestamps": [x.strftime("%Y.%m.%d %H:%M:%S") for x in counted],
        }
        held_rows.append(record)

    time_exit_rows = [row for row in held_rows if row["exit_reason"] == "time_exit"]
    bad_time_exit = [row["deal_ticket"] for row in time_exit_rows if row["full_held_bars"] != 12]
    bad_other = [
        (row["deal_ticket"], row["exit_reason"], row["full_held_bars"])
        for row in held_rows
        if row["exit_reason"] != "time_exit" and row["full_held_bars"] > 12
    ]
    checks.append(
        check(
            "time_exit exactly 12 real M30 bars",
            not bad_time_exit,
            f"time_exit={len(time_exit_rows)}, bad={bad_time_exit or '无'}",
        )
    )
    checks.append(check("非 time_exit 持仓未超 12 根", not bad_other, f"越界={bad_other or '无'}"))

    tickets = [row.get("deal_ticket", "") for row in rows]
    checks.append(check("unique_deal_ticket_rows == audit_rows", len(set(tickets)) == len(tickets), f"{len(set(tickets))}/{len(tickets)}"))
    checks.append(check("duplicate_written_rows == 0", len(set(tickets)) == len(tickets), f"重复={len(tickets) - len(set(tickets))}"))
    checks.append(check("duplicate_attempts_blocked（仅 diagnostic）", True, f"dup_hits={selfcheck.get('dup_hits', '?')}"))

    by_day: dict[str, int] = {}
    for row in rows:
        day = (row.get("entry_time") or "")[:10]
        by_day[day] = by_day.get(day, 0) + 1
    day_bad = {day: count for day, count in by_day.items() if count > 1}
    checks.append(check("每 UTC day <= 1 笔", bool(by_day) and not day_bad, f"违反={day_bad or '无'}"))
    checks.append(check("全部成交 alignment_exact=1", all(row.get("alignment_exact") == "1" for row in rows), f"异常={sum(row.get('alignment_exact') != '1' for row in rows)}"))

    missing_rows = [row for row in reject_rows if row.get("reason") == "cross_asset_missing_bar"]
    stale_missing = [row.get("signal_bar_time", "") for row in missing_rows if (row.get("xau_bar_time") or "").strip()]
    checks.append(check("cross_asset_missing_bar 的 xau_bar_time 为空", not stale_missing, f"拒单={len(missing_rows)}, stale={len(stale_missing)}"))
    atr_rows = [row for row in reject_rows if row.get("reason") == "atr_out_of_regime"]
    stale_atr = [row.get("signal_bar_time", "") for row in atr_rows if (row.get("xau_bar_time") or "").strip()]
    checks.append(check("atr_out_of_regime 的 xau 值为空", not stale_atr, f"拒单={len(atr_rows)}, stale={len(stale_atr)}"))

    ocp_bad = [
        row.get("deal_ticket", "")
        for row in rows
        if abs(number(row.get("deal_profit")) - number(row.get("ocp_expected_pl"))) > 0.05
    ]
    checks.append(check("DEAL_PROFIT↔OCP<=0.05", not ocp_bad, f"超容差={ocp_bad or '无'}"))
    fields_ok = all(
        (row.get("spread_at_entry_points") or "")
        and (row.get("initial_sl_distance_points") or "")
        and (row.get("initial_tp_distance_points") or "")
        for row in rows
    ) if rows else False
    checks.append(check("spread / SL / TP 字段齐备", fields_ok, "same frozen audit schema"))
    spreads_sl = sorted(number(row.get("spread_over_sl")) for row in rows if row.get("spread_over_sl"))
    spreads_tp = sorted(number(row.get("spread_over_tp")) for row in rows if row.get("spread_over_tp"))
    median_sl = spreads_sl[len(spreads_sl) // 2] if spreads_sl else float("inf")
    median_tp = spreads_tp[len(spreads_tp) // 2] if spreads_tp else float("inf")
    checks.append(check("median spread/SL <= 30%", median_sl <= 0.30, f"median={median_sl:.4f}"))
    checks.append(check("median spread/TP <= 30%", median_tp <= 0.30, f"median={median_tp:.4f}"))

    audit_net = sum(number(row.get("net")) for row in rows)
    report_net = number(str(html.get("Total Net Profit")))
    net_tol = max(0.02, 0.001 * max(1.0, abs(report_net)))
    checks.append(check("HTML净利 == 审计净利", abs(audit_net - report_net) <= net_tol, f"audit={audit_net:.2f}, html={report_net:.2f}"))

    return {
        "window": window,
        "directory": str(directory),
        "trade_rows": len(rows),
        "reject_rows": len(reject_rows),
        "time_exit_count": len(time_exit_rows),
        "max_full_held_bars": max((row["full_held_bars"] for row in held_rows), default=0),
        "checks": checks,
        "held_bar_rows": held_rows,
        "html": {key: str(value) for key, value in html.items()},
    }


def write_report(raw: dict[str, object], windows: list[dict[str, object]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    all_checks = [check for item in windows for check in item["checks"]]
    passed = sum(1 for item in all_checks if item["ok"])
    total = len(all_checks)
    all_rows = [row for item in windows for row in item["held_bar_rows"]]
    time_exits = [row for row in all_rows if row["exit_reason"] == "time_exit"]
    weekend = [
        row
        for row in time_exits
        if (parse_time(row["exit_time"]) - parse_time(row["entry_time"])).total_seconds() > 24 * 3600
    ]
    status = "PASS" if raw.get("status") == "PASS" and passed == total and len(all_rows) == 37 else "FAIL"

    with (OUT / "hold_bar_counts.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "window", "deal_ticket", "position_id", "entry_time", "exit_time", "exit_reason",
                "full_held_bars", "first_counted_bar_open", "last_counted_bar_open", "counted_bar_timestamps",
            ],
        )
        writer.writeheader()
        for row in all_rows:
            output = dict(row)
            output["counted_bar_timestamps"] = "|".join(row["counted_bar_timestamps"])
            writer.writerow(output)

    machine = {
        "FINAL_SMOKE_INDEPENDENT": status,
        "raw_identity": raw,
        "windows": windows,
        "summary": {
            "trades": len(all_rows),
            "time_exit_count": len(time_exits),
            "hold_bar_checks": len(all_rows),
            "hold_bar_pass": sum(
                1
                for row in all_rows
                if (row["exit_reason"] == "time_exit" and row["full_held_bars"] == 12)
                or (row["exit_reason"] != "time_exit" and row["full_held_bars"] <= 12)
            ),
            "max_full_held_bars": max((row["full_held_bars"] for row in all_rows), default=0),
            "weekend_trade": weekend,
            "checks": {"passed": passed, "total": total},
        },
    }
    (OUT / "final_smoke_independent.json").write_text(json.dumps(machine, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# XAMR30 N1R3 Independent Final-Smoke Report",
        "",
        "- Same frozen N1R3 smoke evidence; no MT5 rerun.",
        "- Independent held-bar count uses only the frozen real USDJPYm M30 bar-open timestamps.",
        "- No calendar-minute or weekend approximation is used.",
        "- Old `verify_final_smoke.py` and old 68/69 provenance remain unchanged.",
        "",
        "## Identity and result",
        "",
        f"- Raw USDJPYm identity: **{raw.get('status')}**",
        f"- Trades: **{len(all_rows)}** (WINTER 12, DSTTR 10, SUMMER 15)",
        f"- Independent full-held-bar checks: **{machine['summary']['hold_bar_pass']}/{machine['summary']['hold_bar_checks']}**",
        f"- Maximum full-held bars: **{machine['summary']['max_full_held_bars']}**",
        f"- FINAL_SMOKE_INDEPENDENT: **{status}**",
        "",
        "## Window summary",
        "",
        "| Window | trades | time_exit | max full-held bars | checker |",
        "|---|---:|---:|---:|---|",
    ]
    for item in windows:
        item_ok = all(check["ok"] for check in item["checks"])
        lines.append(
            f"| {item['window']} | {item['trade_rows']} | {item['time_exit_count']} | "
            f"{item['max_full_held_bars']} | {sum(1 for c in item['checks'] if c['ok'])}/{len(item['checks'])} "
            f"{'PASS' if item_ok else 'FAIL'} |"
        )
    lines += ["", "## Independent time-exit evidence", ""]
    for row in time_exits:
        lines.append(
            f"- `{row['window']}` ticket `{row['deal_ticket']}`: `{row['entry_time']}` → `{row['exit_time']}`, "
            f"full_held_bars=`{row['full_held_bars']}`."
        )
    lines += ["", "### Disputed SUMMER cross-weekend trade", ""]
    if weekend:
        row = weekend[0]
        lines += [
            f"- deal_ticket: `{row['deal_ticket']}`",
            f"- entry_time: `{row['entry_time']}`",
            f"- exit_time: `{row['exit_time']}`",
            f"- exit_reason: `{row['exit_reason']}`",
            f"- full_held_bars: `{row['full_held_bars']}`",
            f"- first_counted_bar_open: `{row['first_counted_bar_open']}`",
            f"- last_counted_bar_open: `{row['last_counted_bar_open']}`",
            "- counted_bar_timestamps:",
        ]
        lines.extend(f"  - `{stamp}`" for stamp in row["counted_bar_timestamps"])
    else:
        lines.append("- No cross-weekend time_exit row found; this is a FAIL condition for the requested evidence.")
    lines += ["", "## Checks", ""]
    for item in windows:
        lines += [f"### {item['window']}", "", "| Check | Result | Detail |", "|---|---|---|"]
        for item_check in item["checks"]:
            detail = str(item_check["detail"]).replace("|", "\\|")
            lines.append(f"| {item_check['name']} | {'PASS' if item_check['ok'] else 'FAIL'} | {detail} |")
        lines.append("")
    lines += [
        "## Scope",
        "",
        "This is a pre-economic verifier-only closure. It does not modify the EA, rerun MT5, read profits for strategy judgment, or authorize TRAIN/VALID.",
        "",
    ]
    (OUT / "XAMR30_N1R3_FINAL_SMOKE_INDEPENDENT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    try:
        raw, bar_opens = raw_identity()
    except Exception as exc:
        raw = {"status": "FAIL", "error": f"raw identity exception: {exc}"}
        bar_opens = []
    windows = [window_report(name, directory, expected, bar_opens) for name, (directory, expected) in WINDOWS.items()]
    write_report(raw, windows)
    status = json.loads((OUT / "final_smoke_independent.json").read_text(encoding="utf-8"))["FINAL_SMOKE_INDEPENDENT"]
    print(json.dumps({
        "FINAL_SMOKE_INDEPENDENT": status,
        "trades": sum(item["trade_rows"] for item in windows),
        "time_exit_count": sum(item["time_exit_count"] for item in windows),
        "max_full_held_bars": max(item["max_full_held_bars"] for item in windows),
        "hold_bar_checks": sum(1 for item in windows for _ in item["held_bar_rows"]),
        "out": str(OUT),
    }, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
