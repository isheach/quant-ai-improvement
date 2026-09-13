#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 0 · Provenance 闸门（GPT 执行框架 §3）

目标：把已有结果分成「可复核正式记录」和「仅供参考的线索」，避免把不同本金、
不同品种、不同模型拼成一个候选。

对每一个已有结果生成一行 provenance 记录，逐项检查：
  1. 真实符号（只允许 XAUUSDm / BTCUSDm / USDJPYm）
  2. 日期是否触碰留白（2026-06-01 ~ 2026-09-30）
  3. 报告内部日期是否晚于当前时间
  4. outbox 状态是否与文件存在性一致
  5. 交易笔数是否与审计一致
  6. 源码/EX5/报告/审计的 SHA-256

输出：
  stage0_provenance/provenance_inventory.csv
  stage0_provenance/provenance_decision.md
  stage0_provenance/hashes.sha256
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)                      # deepseek数据保存
HANDOFF = os.path.join(BASE, "交接")
OUT = os.path.join(HERE, "stage0_provenance")
os.makedirs(OUT, exist_ok=True)

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
CFGDIR = os.path.join(BASE, "mql5", "config")
EADIR = os.path.join(BASE, "mql5", "dshtools")

ALLOWED = {"XAUUSDm", "BTCUSDm", "USDJPYm"}
HOLDOUT_FROM = dt.date(2026, 6, 1)
HOLDOUT_TO = dt.date(2026, 9, 30)
NOW = dt.datetime.now()

# 内部日期异常：报告里出现的、明显晚于真实的日期
SUSPECT_DATES = ["2026.09.14", "2026-09-14"]


def sha256(p):
    if not p or not os.path.isfile(p):
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest().upper()


def parse_ini(p):
    """读 ini 的 [Tester] 与 [TesterInputs]"""
    if not os.path.isfile(p):
        return {}, {}
    t, inp = {}, {}
    sect = None
    for line in io.open(p, encoding="utf-8-sig", errors="ignore"):
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            sect = s[1:-1].lower()
            continue
        if "=" in s:
            k, v = s.split("=", 1)
            (t if sect == "tester" else inp)[k.strip()] = v.strip()
    return t, inp


def norm_date(s):
    """把 2024.01.01 / 2024-01-01 / 20240101 归一成 date"""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def touches_holdout(d):
    return d is not None and HOLDOUT_FROM <= d <= HOLDOUT_TO


def load_jsonl(p):
    if not os.path.isfile(p):
        return []
    out = []
    for line in io.open(p, encoding="utf-8-sig", errors="ignore"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def trade_rows(csv_path):
    if not os.path.isfile(csv_path):
        return None
    try:
        with io.open(csv_path, encoding="utf-8-sig", errors="ignore", newline="") as f:
            r = list(csv.DictReader(f))
        return r
    except Exception:
        return None


def audit_stats(tag):
    """返回 (行数, entry非零数, 首笔时间, 末笔时间, 目录是否存在)"""
    d = os.path.join(COMMON, tag)
    f = os.path.join(d, "trades.csv")
    rows = trade_rows(f)
    if rows is None:
        return None
    nz = sum(1 for x in rows if str(x.get("entry", "0")).strip() not in ("", "0", "0.0", "0.00", "0.000"))
    times = [str(x.get("time", "")) for x in rows if x.get("time")]
    return {
        "rows": len(rows),
        "entry_nonzero": nz,
        "first": min(times) if times else "",
        "last": max(times) if times else "",
    }


def find_ini_for(tag):
    """找该 run 的 ini（多个候选名）"""
    for pat in ("run_%s.ini" % tag, "run_%s.ini" % tag.replace("BT_", ""), "opt_%s.ini" % tag):
        p = os.path.join(CFGDIR, pat)
        if os.path.isfile(p):
            return p
    return ""


def find_report_for(tag):
    """在 MT5 数据目录找报告（htm/xml）"""
    for ext in (".htm", ".xml"):
        p = os.path.join(TDATA, "rep_%s%s" % (tag, ext))
        if os.path.isfile(p):
            return p
    return ""


def check_report_date(path):
    """报告内部日期是否晚于当前时间（粗暴检查 SUSPECT_DATES）"""
    if not path or not os.path.isfile(path):
        return False
    for enc in ("utf-16-le", "utf-8-sig"):
        try:
            s = io.open(path, encoding=enc, errors="ignore").read()
        except Exception:
            continue
        for d in SUSPECT_DATES:
            if d in s:
                return True
    return False


def expert_meta(expert):
    f = {"trend": "dsh_TrendCore.mq5", "meanrev": "dsh_MeanRev.mq5",
         "btcswing": "dsh_BtcSwing.mq5", "jpyrev": "dsh_JPYRev.mq5",
         "jpygrid": "dsh_JPYGrid.mq5", "tickclock": "dsh_TickClock.mq5"}.get(expert)
    if not f:
        return "", "", ""
    src = os.path.join(EADIR, f)
    ex5 = os.path.join(TDATA, "MQL5", "Experts", "dshtrend", f[:-4] + ".ex5")
    return src, ex5, f


def main():
    rows_out = []
    hashes = []
    problems = []

    files = []
    for who in ("黄金", "日元", "比特币", "滚动优化"):
        p = os.path.join(HANDOFF, "inbox_%s.jsonl" % who)
        if os.path.isfile(p):
            files.append((who, p))
    for root, _, fs in os.walk(os.path.join(HANDOFF, "日元滚动")):
        for f in fs:
            if f.startswith("inbox") and f.endswith(".jsonl"):
                files.append(("日元滚动", os.path.join(root, f)))

    seen = set()
    for who, inbox in files:
        outbox = inbox.replace("inbox", "outbox")
        results = load_jsonl(outbox)
        for r in results:
            rid = r.get("req_id") or r.get("grid_id")
            if not rid or rid in seen:
                continue
            seen.add(rid)

            tag = r.get("tag") or ("BT_" + rid if r.get("req_id") else "OPT_" + str(r.get("grid_id")))
            ini = r.get("ini") or find_ini_for(tag)
            tsec, tinput = parse_ini(ini) if ini else ({}, {})
            rep = r.get("report") or find_report_for(tag)
            src, ex5, eafile = expert_meta(r.get("expert", ""))

            sym = r.get("symbol") or tsec.get("Symbol", "")
            if sym and sym.lower() in ("btc", "gold", "jpy"):
                sym = {"btc": "BTCUSDm", "gold": "XAUUSDm", "jpy": "USDJPYm"}[sym.lower()]

            d_from = norm_date(r.get("from") or tsec.get("FromDate"))
            d_to = norm_date(r.get("to") or tsec.get("ToDate"))
            dep = r.get("deposit") or tsec.get("Deposit", "")
            model = tsec.get("Model", "")

            ast = audit_stats(tag)
            flags = []

            if sym and sym not in ALLOWED:
                flags.append("NON_REAL_SYMBOL")
            if touches_holdout(d_from) or touches_holdout(d_to):
                flags.append("TOUCHES_HOLDOUT")
            if rep and check_report_date(rep):
                flags.append("REPORT_FUTURE_DATE")
            if ast is None:
                flags.append("NO_AUDIT_FILE")
            else:
                if ast["entry_nonzero"] == 0:
                    flags.append("ENTRY_ALL_ZERO")
                elif ast["entry_nonzero"] < ast["rows"]:
                    flags.append("ENTRY_PARTIAL_ZERO")
            if r.get("status") == "done" and not rep:
                flags.append("STATUS_OK_BUT_NO_REPORT")
            if not ini:
                flags.append("NO_INI")
            if r.get("status") == "error":
                flags.append("RUN_ERROR")

            t_mt5 = r.get("trades")
            t_aud = ast["rows"] if ast else None
            if t_mt5 not in (None, "") and t_aud is not None:
                try:
                    if abs(float(t_mt5) - float(t_aud)) > 0.5:
                        flags.append("TRADE_COUNT_MISMATCH(%s/%s)" % (t_mt5, t_aud))
                except Exception:
                    pass

            # 判定
            if "TOUCHES_HOLDOUT" in flags or "NON_REAL_SYMBOL" in flags:
                status = "blocked"
            elif flags and any(f.startswith(("NO_AUDIT", "NO_INI", "ENTRY_ALL", "REPORT_FUTURE")) for f in flags):
                status = "lead_only"
            else:
                status = "verified"

            rows_out.append(dict(
                run_id=tag, source_line=who, req_or_grid=rid,
                status=status, flags=";".join(flags),
                symbol=sym, deposit=dep, leverage=tsec.get("Leverage", ""),
                model=model, period=tsec.get("Period", ""),
                latency_label="%s/%s" % (tinput.get("InpLatencyMs", ""), tinput.get("InpLatencyTicks", "")),
                d_from=str(d_from or ""), d_to=str(d_to or ""),
                expert=r.get("expert", ""), ea_file=eafile,
                ea_sha256=sha256(src), ex5_sha256=sha256(ex5),
                ini_path=ini, ini_sha256=sha256(ini),
                report_path=rep, report_sha256=sha256(rep),
                audit_rows=(ast["rows"] if ast else ""),
                audit_entry_nonzero=(ast["entry_nonzero"] if ast else ""),
                audit_first=(ast["first"] if ast else ""),
                audit_last=(ast["last"] if ast else ""),
                trade_count_mt5=(t_mt5 if t_mt5 is not None else ""),
                trade_count_audit=(t_aud if t_aud is not None else ""),
                net=r.get("net", ""), pf=r.get("pf", ""), dd_pct=r.get("dd_pct", ""),
            ))
            for p in (ini, rep, src, ex5):
                if p and os.path.isfile(p):
                    hashes.append("%s  %s" % (sha256(p), p))

    # 写 CSV
    csvp = os.path.join(OUT, "provenance_inventory.csv")
    if rows_out:
        with io.open(csvp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
            w.writeheader()
            w.writerows(rows_out)

    # 写 hashes
    with io.open(os.path.join(OUT, "hashes.sha256"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(set(hashes))) + "\n")

    # 统计
    from collections import Counter
    st = Counter(r["status"] for r in rows_out)
    fl = Counter()
    for r in rows_out:
        for x in r["flags"].split(";"):
            if x:
                fl[re.sub(r"\(.*\)", "", x)] += 1

    lines = []
    lines.append("# Stage 0 · Provenance 闸门结论\n")
    lines.append("生成时间：%s（Asia/Shanghai）\n" % NOW.strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("## 总览\n")
    lines.append("| 项 | 值 |")
    lines.append("|---|---|")
    lines.append("| 清点结果数 | **%d** |" % len(rows_out))
    for k in ("verified", "lead_only", "blocked"):
        lines.append("| status = %s | %d |" % (k, st.get(k, 0)))
    lines.append("")
    lines.append("## 问题分类（按出现次数）\n")
    lines.append("| 标记 | 次数 | 含义 |")
    lines.append("|---|---:|---|")
    MEAN = {
        "NO_AUDIT_FILE": "无审计 CSV（优化模式的网格普遍如此）",
        "ENTRY_ALL_ZERO": "审计 entry 全为 0 → 无法还原入场价",
        "ENTRY_PARTIAL_ZERO": "审计 entry 部分为 0（券商侧止损平仓取不到开仓价）",
        "NO_INI": "找不到该 run 的 ini（无法证明实际喂给 MT5 的输入）",
        "STATUS_OK_BUT_NO_REPORT": "outbox 标 done 但报告文件不存在",
        "RUN_ERROR": "该 run 本身失败",
        "TOUCHES_HOLDOUT": "★触碰留白段（2026-06-01~09-30）",
        "NON_REAL_SYMBOL": "★非真实券商品种",
        "REPORT_FUTURE_DATE": "★报告内部日期晚于当前时间",
        "TRADE_COUNT_MISMATCH": "笔数与审计不一致",
    }
    for k, v in fl.most_common():
        lines.append("| %s | %d | %s |" % (k, v, MEAN.get(k, "")))
    lines.append("")

    # 关键单项核查
    lines.append("## 逐项硬检查\n")
    hol = [r for r in rows_out if "TOUCHES_HOLDOUT" in r["flags"]]
    sym_bad = [r for r in rows_out if "NON_REAL_SYMBOL" in r["flags"]]
    fut = [r for r in rows_out if "REPORT_FUTURE_DATE" in r["flags"]]
    lines.append("- **留白段（2026-06-01~09-30）被触碰的结果数：%d** %s"
                 % (len(hol), "✅ 未触碰" if not hol else "❌ " + str([r["run_id"] for r in hol[:5]])))
    lines.append("- **非真实品种的结果数：%d** %s"
                 % (len(sym_bad), "✅ 无" if not sym_bad else "❌ " + str([r["run_id"] for r in sym_bad[:5]])))
    lines.append("- **报告未来日期：%d 处** %s"
                 % (len(fut), "✅ 无" if not fut else "⚠️ " + str([r["run_id"] for r in fut[:5]])))
    dep = Counter(str(r["deposit"]) for r in rows_out)
    lines.append("- **入金口径分布**：%s" % dict(dep.most_common(6)))
    lines.append("  → ★GPT 框架要求主口径为 **500 USD**；上表中凡不是 500 的结果，"
                 "按 §9 只能标 `lead_only` 或 `exploratory`，**不得作为交付候选**。")
    lines.append("")
    lines.append("## 产物\n")
    lines.append("- `provenance_inventory.csv`（%d 行）" % len(rows_out))
    lines.append("- `hashes.sha256`（%d 条）" % len(set(hashes)))
    lines.append("- 本文件")
    lines.append("")

    with io.open(os.path.join(OUT, "provenance_decision.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("清点 %d 条结果 → %s" % (len(rows_out), csvp))
    print("status:", dict(st))
    print("flags:", dict(fl.most_common(8)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
