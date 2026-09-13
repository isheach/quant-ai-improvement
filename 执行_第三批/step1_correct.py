#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 1 · 离线更正 R1 / R3（GPT 第三批裁定 §4 Step 1）

1) R1：用 HTML 表格解析器取 Total Trades / Total Deals / 每个 out 行（含 end of test），
   与审计 closing rows 比对 → jpy_r1_corrected.md/.csv
2) R3：修复 DD 解析 —— 官方 Equity Drawdown Maximal（金额/百分比）与 Relative；
   缺失标 not_evaluated，绝不判通过 → c1_r3_corrected.md/.json

★不改写任何原报告、原 CSV；只生成更正文件并保留原路径与原哈希。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mt5_html_parser import parse_report, num, pct_of, count_out_rows  # noqa

OUT = os.path.join(HERE, "stage1_offline_correction")
os.makedirs(OUT, exist_ok=True)
EXEC12 = os.path.join(os.path.dirname(HERE), "执行_20260912")
RUNS3 = os.path.join(EXEC12, "runs_r3")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")

JPY_RUNS = ["DS260913_JPYR3_LONG_A", "DS260913_JPYR3_LONG_B",
            "DS260913_JPYR3_SHORT_A", "DS260913_JPYR3_SHORT_B",
            "DS260913_JPYR3_PARTIAL_A", "DS260913_JPYR3_PARTIAL_B"]
C1_RUNS = [("DS260913_C1R3_TRAIN", "train"), ("DS260913_C1R3_VALID", "valid")]


def sha256(p):
    if not p or not os.path.isfile(p):
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def find_report(tag):
    for p in (os.path.join(RUNS3, tag, "report_%s.htm" % tag),
              os.path.join(TDATA, "report_%s.htm" % tag),
              os.path.join(RUNS3, tag, "rep_%s.htm" % tag)):
        if os.path.isfile(p):
            return p
    return ""


def find_trades(tag):
    for p in (os.path.join(RUNS3, tag, "trades.csv"),
              os.path.join(COMMON, tag, "trades.csv")):
        if os.path.isfile(p):
            return p
    return ""


def fnum(x, d=0.0):
    try:
        return float(str(x).strip())
    except Exception:
        return d


# ==================== R1 更正 ====================
def correct_r1():
    L = []
    L.append("# Step 1 · R1 更正报告（USDJPY 六次控制回测）\n")
    L.append("**解析器**：`执行_第三批\\mt5_html_parser.py` v1（按 `<tr>/<td>` 单元格成对解析，非模糊正则）\n")
    L.append("**性质**：本文件是对 `执行_20260912\\stage2_usdjpy_pnl_r3\\jpy_r3_reconciliation.md` 的**更正**；")
    L.append("原报告与原 CSV **不改写**，原哈希见 §3。\n")
    L.append("## 1. ★更正的核心结论\n")
    L.append("我原报告写「逐笔 6/6 达 100%、报告 closing deal 与审计一一对应」——**这四行是错的**。\n")
    L.append("逐层复核后发现：**4 个 run 各缺一行 `end of test` 强制平仓 deal**。\n")

    rows = []
    for tag in JPY_RUNS:
        rp = find_report(tag)
        tp = find_trades(tag)
        if not rp or not tp:
            rows.append(dict(run_id=tag, note="缺报告或审计"))
            continue
        r = parse_report(rp)
        kv = r["kv"]
        n_audit = sum(1 for _ in io.open(tp, encoding="utf-8-sig", errors="ignore")) - 1
        html_trades = num(kv.get("Total Trades"))
        html_deals = num(kv.get("Total Deals"))
        out_rows = count_out_rows(r["deals"])
        end_rows = [x for x in r["deals"] if "end of test" in " ".join(x).lower()]
        audit_net = 0.0
        with io.open(tp, encoding="utf-8-sig", errors="ignore", newline="") as f:
            for d in csv.DictReader(f):
                audit_net += fnum(d.get("pnl"))
        rep_net = num(kv.get("Total Net Profit"))
        rows.append(dict(
            run_id=tag, report_path=rp, report_sha256=sha256(rp),
            trades_path=tp, trades_sha256=sha256(tp),
            html_trades=html_trades, html_deals=html_deals,
            html_out_rows=out_rows, audit_rows=n_audit,
            missing=int(html_trades - n_audit) if html_trades is not None else None,
            end_of_test_rows=len(end_rows),
            end_of_test_amount=(num(end_rows[-1][10]) if end_rows and len(end_rows[-1]) > 10 else None),
            audit_net=round(audit_net, 2), report_net=rep_net,
            net_diff=round((audit_net - rep_net), 2) if rep_net is not None else None,
            verdict="一致" if (html_trades == n_audit) else "★审计缺 %s 行" % (html_trades - n_audit),
        ))

    L.append("| run_id | HTML Trades | HTML Deals | HTML out 行 | 审计行 | 缺 | end-of-test 行 | 差额 USD | 审计净 | 报告净 | 判定 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    for x in rows:
        if "note" in x:
            L.append("| `%s` | — | — | — | — | — | — | — | — | — | %s |" % (x["run_id"], x["note"]))
            continue
        L.append("| `%s` | %s | %s | %s | %d | **%s** | %s | %s | %.2f | %s | %s |"
                 % (x["run_id"], x["html_trades"], x["html_deals"], x["html_out_rows"],
                    x["audit_rows"], x["missing"], x["end_of_test_rows"],
                    ("%.2f" % x["end_of_test_amount"]) if x["end_of_test_amount"] is not None else "—",
                    x["audit_net"], ("%.2f" % x["report_net"]) if x["report_net"] is not None else "—",
                    x["verdict"]))
    L.append("")

    bad = [x for x in rows if "note" not in x and x["missing"]]
    L.append("## 2. 更正后的判定\n")
    L.append("```")
    L.append("完整一致（HTML Trades == 审计行）: %d / %d" % (len(rows) - len(bad), len(rows)))
    for x in bad:
        L.append("  ★ %s 缺 %d 行 end-of-test 平仓，净利差 %.2f USD"
                 % (x["run_id"], x["missing"], x["end_of_test_amount"] or 0))
    L.append("→ 原报告「逐笔 6/6 一一对应」更正为【%d/6 完整一致、%d/6 缺结束平仓】"
             % (len(rows) - len(bad), len(bad)))
    L.append("→ JPY 维持 blocked_mapping（严格汇总容差 max(0.02, 0.1%%×|net|) 不变）")
    L.append("→ 状态统一改标 audit_reconcile_required / blocked_mapping")
    L.append("```")
    L.append("")
    L.append("**★我的原判定为什么错**：")
    L.append("```")
    L.append("我的 r1_exec.py 条件②实际只检查了「审计内部公式逐笔通过」，")
    L.append("没有解析 HTML 的 closing-deal 集合 → 无法发现审计【少了整行】。")
    L.append("逐笔残差小（中位 0.0026 USD）并不能抵销【汇总漏记 0.70】。")
    L.append("→ 这正说明四方对账必须真的做四方，缺一方就会漏掉「整行缺失」这类错误。")
    L.append("```")
    L.append("")
    L.append("## 3. 原文件哈希（保留以便追溯，未改写）\n")
    L.append("| 文件 | SHA-256 |")
    L.append("|---|---|")
    for x in rows:
        if "note" in x:
            continue
        L.append("| `%s` | `%s` |" % (x["run_id"] + "/report.htm", x["report_sha256"]))
        L.append("| `%s` | `%s` |" % (x["run_id"] + "/trades.csv", x["trades_sha256"]))
    L.append("")
    io.open(os.path.join(OUT, "jpy_r1_corrected.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    if rows and "note" not in rows[0]:
        with io.open(os.path.join(OUT, "jpy_r1_corrected.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows([x for x in rows if "note" not in x])
    return "\n".join(L)


# ==================== R3 更正 ====================
def correct_r3():
    L = []
    L.append("# Step 1 · R3 更正报告（BTC C1-R3 官方 DD）\n")
    L.append("**性质**：更正 `执行_20260912\\stage4_candidates_r3\\r3_diagnostics.md` 中的 DD 部分；")
    L.append("原文件不改写。\n")
    L.append("## 1. ★更正的核心结论\n")
    L.append("我原报告把官方 DD 写成**空字符串**，并用 `dd is None or dd <= 40` 判定 → **「未取到」被错误地显示为 ✅**。")
    L.append("**HTML 里其实有完整数值。**\n")
    res = {}
    for tag, role in C1_RUNS:
        rp = find_report(tag)
        if not rp:
            res[role] = {"error": "无报告"}
            continue
        r = parse_report(rp)
        kv = r["kv"]
        edn_m = kv.get("Equity Drawdown Maximal")
        edr = kv.get("Equity Drawdown Relative")
        bdm = kv.get("Balance Drawdown Maximal")
        bdr = kv.get("Balance Drawdown Relative")
        res[role] = dict(
            report_path=rp, report_sha256=sha256(rp),
            equity_dd_maximal_raw=edn_m, equity_dd_maximal_usd=num(edn_m), equity_dd_maximal_pct=pct_of(edn_m),
            equity_dd_relative_raw=edr, equity_dd_relative_pct=pct_of(edr), equity_dd_relative_usd=num(edr),
            balance_dd_maximal_pct=pct_of(bdm), balance_dd_relative_pct=pct_of(bdr),
            total_trades=num(kv.get("Total Trades")), total_deals=num(kv.get("Total Deals")),
            net=num(kv.get("Total Net Profit")), pf=num(kv.get("Profit Factor")),
            bars=num(kv.get("Bars")), ticks=num(kv.get("Ticks")),
        )
    L.append("| 段 | Equity DD Maximal | **Equity DD Relative（风险门槛主值）** | Balance DD Maximal | Balance DD Relative |")
    L.append("|---|---|---|---|---|")
    for role in ("train", "valid"):
        d = res.get(role, {})
        if "error" in d:
            L.append("| %s | — | — | — | — |" % role)
            continue
        L.append("| **%s** | `%s` | **`%s`** | `%s`%% | `%s`%% |"
                 % (role, d["equity_dd_maximal_raw"], d["equity_dd_relative_raw"],
                    d["balance_dd_maximal_pct"], d["balance_dd_relative_pct"]))
    L.append("")
    L.append("## 2. 与 GPT 独立复核的对照\n")
    L.append("| 段 | GPT 复核值 | 我的解析值 | 一致 |")
    L.append("|---|---|---|---|")
    for role in ("train", "valid"):
        d = res.get(role, {})
        gpt = "451.98 (22.17%) / 39.95% (306.80)" if role == "train" else "118.13 (18.60%) / 18.60% (118.13)"
        mine = "%s / %s" % (d.get("equity_dd_maximal_raw"), d.get("equity_dd_relative_raw"))
        L.append("| %s | `%s` | `%s` | %s |" % (role, gpt, mine, "✅" if mine == gpt else "⚠️ 需核对"))
    L.append("")
    L.append("## 3. 解析器修复\n")
    L.append("```")
    L.append("旧：dd is None or dd <= 40   → 空值判定为【通过】   ❌ 错误")
    L.append("新：数值缺失 → not_evaluated，【绝不通过】        ✅")
    L.append("    能读到 → 以 Equity Drawdown Relative 为风险门槛主值，")
    L.append("             同时保留 Maximal 的金额与百分比")
    L.append("```")
    L.append("")
    L.append("## 4. 对 C1 结论的影响\n")
    L.append("```")
    L.append("★C1 状态不变（仍为 blocked_failed）——关闭条件由【尾部稳健性】触发：")
    L.append("  train: 净利 +3280.42 → 去前10大单 −354.74（前10占比 110.8%）")
    L.append("  valid: 净利  +187.48 → 去前10大单 −247.67（前10占比 232.1%）")
    L.append("DD 更正只影响【DD 门槛那一项的取值】，不改变关闭判定。")
    L.append("补充：即使按官方 Equity DD Relative 看，train 39.95% 也逼近 40% 上限。")
    L.append("```")
    L.append("")
    L.append("## 5. 产物\n")
    L.append("- `c1_r3_corrected.md` / `c1_r3_corrected.json`")
    L.append("- 解析器 `执行_第三批\\mt5_html_parser.py` v1")
    L.append("")
    io.open(os.path.join(OUT, "c1_r3_corrected.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    io.open(os.path.join(OUT, "c1_r3_corrected.json"), "w", encoding="utf-8").write(
        json.dumps(res, ensure_ascii=False, indent=1))
    return "\n".join(L)


if __name__ == "__main__":
    a = correct_r1()
    b = correct_r3()
    print(a)
    print("\n" + "=" * 70 + "\n")
    print(b)
