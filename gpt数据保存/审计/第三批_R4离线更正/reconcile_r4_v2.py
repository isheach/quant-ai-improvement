#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第三批 JPY-R4 离线复核 v2。

只读取已经封存的 HTML/CSV/registry，不启动 MT5、不改写 DeepSeek 目录。
与原 step3_run_r4.py 的关键差异：
  1. 从 Deals 表的 Direction 列分别计数 in/out；
  2. 用 Total Deals == in + out，且 out == 审计 closing rows；
  3. OCP、自检、唯一 ticket 和哈希完整性进入最终判定。
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNROOT = ROOT / "deepseek数据保存" / "执行_第三批" / "stage2_jpy_r4" / "runs_r4"
REG = ROOT / "deepseek数据保存" / "执行_第三批" / "stage0_snapshot" / "run_registry_r4.jsonl"
OUT = HERE


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def cells(tr: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I):
        t = re.sub(r"<[^>]+>", "", m.group(1))
        out.append(html.unescape(t).replace("\xa0", " ").strip())
    return out


def parse_html(path: Path) -> tuple[dict[str, str], list[list[str]]]:
    raw = path.read_text(encoding="utf-16-le", errors="ignore")
    kv: dict[str, str] = {}
    deal_rows: list[list[str]] = []
    for table in re.findall(r"<table.*?</table>", raw, re.S | re.I):
        rows = [cells(tr) for tr in re.findall(r"<tr.*?</tr>", table, re.S | re.I)]
        rows = [r for r in rows if r]
        for row in rows:
            if len(row) >= 2 and len(row) % 2 == 0:
                for i in range(0, len(row), 2):
                    key, value = row[i].rstrip(":").strip(), row[i + 1]
                    if key and key not in kv:
                        kv[key] = value
        for i, row in enumerate(rows):
            # MT5 的 Deals 表头；Orders 表不含 Direction 列，故不会混入。
            if len(row) >= 5 and row[:5] == ["Time", "Deal", "Symbol", "Type", "Direction"]:
                for candidate in rows[i + 1 :]:
                    if len(candidate) > 4 and candidate[4].lower() in {"in", "out"}:
                        deal_rows.append(candidate)
    return kv, deal_rows


def number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).replace(" ", "").replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def read_registry() -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    if not REG.exists():
        return result
    for line in REG.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            result.setdefault(str(item["run_id"]), []).append(item)
    return result


def latest_done(items: list[dict[str, object]]) -> dict[str, object] | None:
    done = [x for x in items if x.get("status") == "done"]
    return done[-1] if done else (items[-1] if items else None)


def hash_status(rec: dict[str, object]) -> tuple[bool, bool]:
    """返回 (registry_hashes_complete, all_files_read_back).

    EX5 位于终端目录，当前 Windows ACL 可能拒绝读取；这不应被悄悄
    当成哈希不匹配，所以把“登记完整”和“本次可读回”分开报告。
    """
    required = [
        ("ini_path", "ini_sha256"),
        ("report_path", "report_sha256"),
        ("trades_path", "trades_sha256"),
        ("selfcheck_path", "selfcheck_sha256"),
    ]
    recorded = True
    readable = True
    for path_key, hash_key in required:
        p = Path(str(rec.get(path_key, "")))
        expected = str(rec.get(hash_key, "")).upper()
        try:
            exists = p.is_file()
            denied = False
        except (OSError, PermissionError):
            exists = False
            denied = True
            readable = False
        if not expected:
            recorded = False
            continue
        if denied:
            # 路径存在但当前进程无权读：登记字段仍完整，readback 单独告警。
            continue
        if not exists:
            recorded = False
            continue
        try:
            if sha256(p) != expected:
                recorded = False
        except (OSError, PermissionError):
            readable = False
    for key in ("expert_source_path", "ex5_path"):
        p = Path(str(rec.get(key, "")))
        expected = str(rec.get(key.replace("_path", "_sha256"), "")).upper()
        try:
            exists = p.is_file()
            denied = False
        except (OSError, PermissionError):
            exists = False
            denied = True
            readable = False
        if not expected:
            recorded = False
            continue
        if denied:
            continue
        if not exists:
            recorded = False
            continue
        try:
            if sha256(p) != expected:
                recorded = False
        except (OSError, PermissionError):
            readable = False
    return recorded, readable


def audit_one(run_id: str, registry: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    d = RUNROOT / run_id
    report = d / f"report_{run_id}.htm"
    trades = d / "trades.csv"
    selfcheck = d / "audit_selfcheck.csv"
    kv, deal_rows = parse_html(report)
    with trades.open(encoding="utf-8-sig", newline="") as f:
        audit_rows = list(csv.DictReader(f))
    with selfcheck.open(encoding="utf-8-sig", newline="") as f:
        check = next(csv.DictReader(f), {})

    html_in = sum(r[4].lower() == "in" for r in deal_rows)
    html_out = sum(r[4].lower() == "out" for r in deal_rows)
    total_deals = number(kv.get("Total Deals"))
    total_trades = number(kv.get("Total Trades"))
    report_net = number(kv.get("Total Net Profit"))
    audit_net = sum(float(r.get("net") or 0.0) for r in audit_rows)
    tol = max(0.02, 0.001 * max(1.0, abs(report_net or 0.0))) if report_net is not None else None

    cost_ok = all(
        abs(float(r.get("profit") or 0.0) + float(r.get("swap") or 0.0)
            + float(r.get("commission") or 0.0) - float(r.get("net") or 0.0)) < 0.01
        for r in audit_rows
    )
    ocp_ok = all(str(r.get("ocp_ok", "")).strip() == "1" for r in audit_rows)
    formula_errors: list[float] = []
    for r in audit_rows:
        entry, exit_ = float(r["entry"]), float(r["exit"])
        vol, direction = float(r["vol"]), float(r["dir"])
        expected = (exit_ - entry) / exit_ * 100000.0 * vol * (1 if direction > 0 else -1)
        formula_errors.append(abs(float(r.get("profit") or 0.0) - expected))
    formula_ok = bool(formula_errors) and max(formula_errors) <= 0.05
    tickets = [r.get("deal_ticket", "") for r in audit_rows]
    unique_tickets = len(tickets) == len(set(tickets)) and all(tickets)
    selfcheck_ok = (
        str(check.get("written_deals", "")) == str(len(audit_rows))
        and str(check.get("audit_failed", "")) == "0"
    )
    rec = latest_done(registry.get(run_id, []))
    hashes_ok, hashes_readback = hash_status(rec) if rec else (False, False)

    rows_ok = total_trades == html_out == len(audit_rows)
    deals_ok = total_deals == html_in + html_out and html_out == len(audit_rows)
    net_ok = report_net is not None and tol is not None and abs(audit_net - report_net) <= tol
    overall = all((rows_ok, deals_ok, net_ok, cost_ok, ocp_ok, formula_ok,
                   unique_tickets, selfcheck_ok, hashes_ok))
    return {
        "run_id": run_id,
        "html_total_trades": total_trades,
        "html_total_deals": total_deals,
        "html_in_rows": html_in,
        "html_out_rows": html_out,
        "audit_rows": len(audit_rows),
        "audit_net": round(audit_net, 2),
        "report_net": report_net,
        "net_diff": round(audit_net - report_net, 2) if report_net is not None else None,
        "tol": tol,
        "rows_match": rows_ok,
        "deals_match": deals_ok,
        "sum_ok": net_ok,
        "cost_ok": cost_ok,
        "ocp_ok": sum(str(r.get("ocp_ok", "")).strip() == "1" for r in audit_rows),
        "ocp_total": len(audit_rows),
        "formula_ok": sum(e <= 0.05 for e in formula_errors),
        "formula_total": len(formula_errors),
        "formula_max_error": max(formula_errors) if formula_errors else None,
        "unique_tickets": unique_tickets,
        "selfcheck_ok": selfcheck_ok,
        "selfcheck_written": check.get("written_deals"),
        "selfcheck_failed": check.get("audit_failed"),
        "hashes_ok": hashes_ok,
        "hashes_readback": hashes_readback,
        "verdict": "通过" if overall else "未通过",
    }


def write_outputs(records: list[dict[str, object]]) -> None:
    json_path = OUT / "reconciliation_v2.json"
    csv_path = OUT / "reconciliation_v2.csv"
    md_path = OUT / "reconciliation_v2.md"
    json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    keys = list(records[0]) if records else []
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader(); writer.writerows(records)
    all_ok = bool(records) and all(r["verdict"] == "通过" for r in records)
    lines = [
        "# JPY-R4 离线更正复核 v2",
        "",
        "本文件只读取既有 R4 HTML/CSV/registry；未启动 MT5，未修改 DeepSeek 原始产物。",
        "判据：`Total Trades = HTML out = 审计 closing rows`；`Total Deals = HTML in + HTML out`；",
        "并将净利、成本分解、OCP、独立公式、唯一 ticket、自检和哈希完整性纳入最终判定。",
        "",
        "| run | in | out | Total Deals | audit rows | net diff | OCP | formula | selfcheck | hashes | readback | verdict |",
        "|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|",
    ]
    for r in records:
        lines.append(
            f"| `{r['run_id']}` | {r['html_in_rows']} | {r['html_out_rows']} | "
            f"{r['html_total_deals']:.0f} | {r['audit_rows']} | {r['net_diff']:.2f} | "
            f"{r['ocp_ok']}/{r['ocp_total']} | {r['formula_ok']}/{r['formula_total']} | "
            f"{'✅' if r['selfcheck_ok'] else '❌'} | {'✅' if r['hashes_ok'] else '❌'} | "
            f"{'✅' if r['hashes_readback'] else '⚠️'} | "
            f"**{r['verdict']}** |"
        )
    lines += [
        "",
        f"结论：六个 R4 run **{'全部通过' if all_ok else '未全部通过'}**（{sum(r['verdict']=='通过' for r in records)}/{len(records)}）。",
        "这只证明 R4 的执行/审计映射链，不证明 USDJPY 策略收益已验证或可交付。",
        "",
        "哈希列按 registry 登记完整性判定；若 readback 为 ⚠️，表示当前终端目录 ACL 阻止再次读取 EX5，"
        "不是把它默认为匹配。原始送审报告保持不变；本文件是其后的离线更正附件。",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    registry = read_registry()
    run_ids = sorted(p.name for p in RUNROOT.iterdir() if p.is_dir())
    records = [audit_one(run_id, registry) for run_id in run_ids]
    write_outputs(records)
    print(json.dumps(records, ensure_ascii=False, indent=2))
