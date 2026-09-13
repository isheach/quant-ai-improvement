#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Independent post-run reconciliation and diagnostics for one MR30 capture."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "deepseek数据保存" / "执行_第三批"))
from mt5_html_parser import count_out_rows, num, parse_report, pct_of  # noqa: E402


def read_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def f(row, key):
    try:
        return float(row.get(key, "") or 0)
    except (TypeError, ValueError):
        return 0.0


def html_deal_counts(deals):
    ins = outs = 0
    for row in deals:
        text = " ".join(row).lower()
        if re.search(r"\bin\b", text):
            ins += 1
        if re.search(r"\bout\b", text) or "out by" in text:
            outs += 1
    return ins, outs


def parse_report_metrics(report: Path):
    parsed = parse_report(str(report))
    if not parsed:
        raise RuntimeError(f"cannot parse report: {report}")
    kv = parsed["kv"]
    return parsed, {
        "initial_deposit": num(kv.get("Initial Deposit")),
        "total_net_profit": num(kv.get("Total Net Profit")),
        "gross_profit": num(kv.get("Gross Profit")),
        "gross_loss": num(kv.get("Gross Loss")),
        "profit_factor": num(kv.get("Profit Factor")),
        "expected_payoff": num(kv.get("Expected Payoff")),
        "equity_dd_maximal": pct_of(kv.get("Equity Drawdown Maximal")),
        "equity_dd_relative": pct_of(kv.get("Equity Drawdown Relative")),
        "balance_dd_maximal": pct_of(kv.get("Balance Drawdown Maximal")),
        "balance_dd_relative": pct_of(kv.get("Balance Drawdown Relative")),
        "total_trades": num(kv.get("Total Trades")),
        "total_deals": num(kv.get("Total Deals")),
        "bars": num(kv.get("Bars")),
        "ticks": num(kv.get("Ticks")),
        "history_quality": kv.get("History Quality"),
        "sharpe": num(kv.get("Sharpe Ratio")),
        "long_trades": kv.get("Long Trades (won %)"),
        "short_trades": kv.get("Short Trades (won %)"),
    }


def analyze(run_dir: Path) -> dict:
    report = run_dir / "report.htm"
    trades = run_dir / "trades.csv"
    signals = run_dir / "signals.csv"
    selfcheck = run_dir / "audit_selfcheck.csv"
    for p in (report, trades, signals, selfcheck):
        if not p.is_file():
            raise RuntimeError(f"missing output: {p}")
    rows = read_rows(trades)
    sig = read_rows(signals)
    parsed, metrics = parse_report_metrics(report)
    html_in, html_out = html_deal_counts(parsed["deals"])
    audit_net = sum(f(r, "net") for r in rows)
    audit_profit = sum(f(r, "profit") for r in rows)
    audit_swap = sum(f(r, "swap") for r in rows)
    audit_commission = sum(f(r, "commission") for r in rows)
    cost_residuals = [f(r, "profit") + f(r, "swap") + f(r, "commission") - f(r, "net") for r in rows]
    formula_abs = [abs(f(r, "formula_diff")) for r in rows]
    ocp_residuals = [f(r, "ocp_value") - f(r, "profit") for r in rows if r.get("ocp_ok") == "1"]
    tickets = Counter(r.get("deal_ticket", "") for r in rows)
    positions = Counter(r.get("position_id", "") for r in rows)
    signal_ids = Counter(r.get("signal_id", "") for r in rows)
    reasons = Counter(r.get("exit_reason", "") for r in rows)
    dirs = Counter(r.get("dir", "") for r in rows)
    vols = Counter(r.get("volume", "") for r in rows)
    wins = [f(r, "net") for r in rows if f(r, "net") > 0]
    losses = [f(r, "net") for r in rows if f(r, "net") <= 0]
    sorted_nets = sorted((f(r, "net") for r in rows), reverse=True)
    top10 = sum(sorted_nets[:10])
    result = {
        "run_dir": str(run_dir),
        "metrics": metrics,
        "audit": {
            "rows": len(rows), "net": round(audit_net, 8), "profit": round(audit_profit, 8),
            "swap": round(audit_swap, 8), "commission": round(audit_commission, 8),
            "cost_max_abs_residual": max((abs(x) for x in cost_residuals), default=0.0),
            "ocp_rows": len(ocp_residuals), "ocp_max_abs_residual": max((abs(x) for x in ocp_residuals), default=0.0),
            "formula_max_abs_diff": max(formula_abs, default=0.0),
            "ticket_unique": len(tickets), "ticket_duplicate_groups": sum(v > 1 for v in tickets.values()),
            "position_unique": len(positions), "signal_unique": len(signal_ids),
            "exit_reasons": dict(reasons), "directions": dict(dirs), "volumes": dict(vols),
            "win_rows": len(wins), "loss_rows": len(losses),
            "best_net": max(wins, default=0.0), "worst_net": min(losses, default=0.0),
            "top10_net": round(top10, 8),
            "net_ex_top10": round(audit_net - top10, 8),
        },
        "html": {
            "parsed_deal_rows": len(parsed["deals"]), "opening_rows": html_in, "closing_rows": html_out,
            "total_trades": metrics["total_trades"], "total_deals": metrics["total_deals"],
        },
        "signals": {
            "rows": len(sig), "decisions": dict(Counter(x.get("decision", "") for x in sig)),
            "reasons": dict(Counter(x.get("reason", "") for x in sig)),
            "accepted": sum(x.get("decision") == "accepted" for x in sig),
            "rejected": sum(x.get("decision") == "rejected" for x in sig),
            "blocked": sum(x.get("decision") == "blocked" for x in sig),
        },
    }
    checks = {
        "report_has_data": bool(metrics["bars"] and metrics["ticks"] and metrics["initial_deposit"]),
        "report_audit_net_match": metrics["total_net_profit"] is not None and abs(audit_net - metrics["total_net_profit"]) <= max(0.02, 0.001 * max(1.0, abs(metrics["total_net_profit"]))),
        "trades_match_html_out": metrics["total_trades"] is not None and int(metrics["total_trades"]) == html_out == len(rows),
        "deals_match_html_in_out": metrics["total_deals"] is not None and int(metrics["total_deals"]) == html_in + html_out,
        "cost_decomposition": max((abs(x) for x in cost_residuals), default=0.0) < 0.011,
        "ocp_consistent": len(ocp_residuals) == len(rows) and max((abs(x) for x in ocp_residuals), default=999.0) <= 0.02,
        "formula_consistent": max(formula_abs, default=999.0) <= 0.05,
        "tickets_unique": all(v == 1 for v in tickets.values()),
        "fields_nonempty": all(all(r.get(k) not in (None, "") for k in ("deal_ticket", "position_id", "entry_time", "exit_time", "entry", "exit", "volume", "net")) for r in rows),
        "selfcheck_no_audit_failure": False,
    }
    sc = read_rows(selfcheck)
    if sc:
        last = sc[-1]
        checks["selfcheck_no_audit_failure"] = last.get("audit_failed") == "0" and last.get("signal_write_failed") == "0"
        result["selfcheck"] = last
    result["checks"] = checks
    result["all_execution_checks_pass"] = all(checks.values())
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    result = analyze(args.run_dir)
    out = args.out or args.run_dir / "reconciliation.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["all_execution_checks_pass"] else 1)


if __name__ == "__main__":
    main()
