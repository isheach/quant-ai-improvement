#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段 A 补漏：把【绕过 JSONL 协议】直接跑 runexp.py 的 run 补进 provenance 与 manifest。

发现：P4C*/P4D*/S1CHK*/S1SIG 这批是我直接用 runexp.py 跑的，
      它们有 run_<tag>.ini + 审计 CSV，但【没有 inbox/outbox 记录】→ v2 扫不到。
      这是"绕过协议"的真实缺口（GPT 阶段 A 第 1 条要求以实际文件链为准）。
修法：从 mql5\config\run_*.ini 反查全部 run，不依赖 JSONL。
"""
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
CFGDIR = os.path.join(BASE, "mql5", "config")
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
EADIR = os.path.join(BASE, "mql5", "dshtools")
MANIFEST = os.path.join(os.path.dirname(os.path.dirname(HERE)), "gpt数据保存",
                        "mt5_runs", "run_manifest.jsonl")
OUT = os.path.join(HERE, "stage0_provenance_v2")
os.makedirs(OUT, exist_ok=True)

HO_FROM, HO_TO = dt.date(2026, 6, 1), dt.date(2026, 9, 30)


def sha256(p):
    if not p or not os.path.isfile(p):
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def parse_ini(p):
    t, inp = {}, {}
    sect = None
    for line in io.open(p, encoding="utf-8-sig", errors="ignore"):
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            sect = s[1:-1].lower(); continue
        if "=" in s:
            k, v = s.split("=", 1)
            (t if sect == "tester" else inp)[k.strip()] = v.strip()
    return t, inp


def nd(s):
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# 1) 枚举全部 run_*.ini
inis = sorted(f for f in os.listdir(CFGDIR) if f.startswith("run_") and f.endswith(".ini"))
recs = []
for f in inis:
    tag = f[4:-4]
    t, inp = parse_ini(os.path.join(CFGDIR, f))
    ar = os.path.join(COMMON, tag, "trades.csv")
    n = None
    has_pid = False
    if os.path.isfile(ar):
        rows = list(csv.DictReader(io.open(ar, encoding="utf-8-sig", errors="ignore")))
        n = len(rows)
        has_pid = bool(rows) and ("position_id" in (rows[0] or {}))
    rep = os.path.join(TDATA, "rep_%s.htm" % tag)
    sym = t.get("Symbol", "")
    a, b = nd(t.get("FromDate")), nd(t.get("ToDate"))
    recs.append(dict(
        tag=tag, symbol=sym, deposit=t.get("Deposit", ""), model=t.get("Model", ""),
        period=t.get("Period", ""), d_from=str(a or ""), d_to=str(b or ""),
        expert_input=inp.get("_expert", ""),
        latency="%s/%s" % (inp.get("InpLatencyMs", "?"), inp.get("InpLatencyTicks", "?")),
        audit_rows=(n if n is not None else ""),
        has_position_id=("1" if has_pid else "0"),
        has_report=("1" if os.path.isfile(rep) else "0"),
        ini_sha=sha256(os.path.join(CFGDIR, f)),
        holdout=("YES" if (a and b and a <= HO_TO and b >= HO_FROM) else "no"),
        mtime=dt.datetime.fromtimestamp(os.path.getmtime(os.path.join(CFGDIR, f))).strftime("%Y-%m-%d %H:%M"),
        sa=("1" if inp.get("InpAllowMinLotOvershoot", "").lower() == "true" else "0"),
    ))

# 2) 哪些不在 v2 里
v2 = list(csv.DictReader(io.open(os.path.join(OUT, "provenance_inventory_v2.csv"),
                                 encoding="utf-8-sig")))
known_tags = {r["run_id"].replace("BT_", "").replace("GD_", "").replace("JP_", "") for r in v2}
known_tags |= {r["run_id"] for r in v2}
orphan = [r for r in recs if r["tag"] not in known_tags]

L = []
L.append("# 阶段 A 补漏 · 绕过 JSONL 协议的 run\n")
L.append("## 发现\n")
L.append("`P4C*` / `P4D*` / `S1CHK*` / `S1SIG` 这批 run 是我**直接用 `runexp.py`** 跑的：")
L.append("它们有 `run_<tag>.ini` 与审计 CSV，但**没有写入任何 `inbox/outbox`** → ")
L.append("v1 与 v2 都扫不到它们。**这是「绕过协议」的真实缺口。**")
L.append("")
L.append("## 修法\n")
L.append("不再依赖 JSONL，改为**从 `mql5\\config\\run_*.ini` 反查全部 run**（文件链为准）。")
L.append("")
L.append("| 项 | 值 |")
L.append("|---|---|")
L.append("| `run_*.ini` 总数 | **%d** |" % len(recs))
L.append("| 其中已在 v2 中 | %d |" % (len(recs) - len(orphan)))
L.append("| **★v2 漏掉的（orphan）** | **%d** |" % len(orphan))
L.append("")
if orphan:
    L.append("## 漏掉的 run（%d 条）\n" % len(orphan))
    L.append("| run_tag | 品种 | 入金 | 模型 | 审计行 | position_id | 报告 | 留白 | 超配 |")
    L.append("|---|---|---|---|---:|---|---|---|---|")
    for r in orphan:
        L.append("| `%s` | %s | %s | %s | %s | %s | %s | %s | %s |"
                 % (r["tag"], r["symbol"], r["deposit"], r["model"], r["audit_rows"],
                    r["has_position_id"], r["has_report"], r["holdout"], r["sa"]))
    L.append("")
    nopid = sum(1 for r in orphan if r["has_position_id"] == "0")
    L.append("**★其中审计含 `position_id` 列（= 新格式、可对账）：%d / %d**"
             % (len(orphan) - nopid, len(orphan)))
    L.append("")
    L.append("| 入金分布 | 值 |")
    L.append("|---|---|")
    for k, v in collections.Counter(r["deposit"] for r in orphan).most_common():
        L.append("| %s | %d |" % (k, v))
    L.append("")

# 3) 追加 manifest（★只追加）
ADD = []
for r in orphan:
    status = "verified" if (r["has_position_id"] == "1" and r["has_report"] == "1"
                            and r["holdout"] == "no" and r["audit_rows"] != "") else "lead_only"
    ADD.append(dict(
        run_id="ds260913_%s" % r["tag"],
        status=status,
        symbol=r["symbol"] or "BTCUSDm",
        account_currency="USD", deposit=r["deposit"] or "500", leverage="200",
        **{"from": r["d_from"], "to": r["d_to"]},
        model=r["model"] or "2", period=r["period"],
        latency_label=r["latency"], tester_mode="single",
        expert_source_path="deepseek数据保存/mql5/dshtools/dsh_BtcSwing.mq5",
        expert_source_sha256=sha256(os.path.join(EADIR, "dsh_BtcSwing.mq5")),
        ex5_sha256=sha256(os.path.join(TDATA, "MQL5", "Experts", "dshtrend", "dsh_BtcSwing.ex5")),
        set_or_ini_path="mql5/config/run_%s.ini" % r["tag"],
        set_or_ini_sha256=r["ini_sha"],
        report_path="rep_%s.htm" % r["tag"] if r["has_report"] == "1" else "",
        report_sha256=sha256(os.path.join(TDATA, "rep_%s.htm" % r["tag"])),
        audit_path="Common/Files/dshtrend/%s/trades.csv" % r["tag"],
        audit_sha256=sha256(os.path.join(COMMON, r["tag"], "trades.csv")),
        first_trade="", last_trade="",
        trade_count_mt5="", trade_count_audit=r["audit_rows"],
        spread_or_cost_mode="snapshot",
        created_at_local=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        notes="阶段A补漏（绕过JSONL，从ini反查）；overshoot=%s" % r["sa"],
    ))

before = after = 0
if ADD:
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    if os.path.isfile(MANIFEST):
        before = sum(1 for l in io.open(MANIFEST, encoding="utf-8") if l.strip())
    with io.open(MANIFEST, "a", encoding="utf-8") as f:
        for a in ADD:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    after = sum(1 for l in io.open(MANIFEST, encoding="utf-8") if l.strip())

L.append("## manifest 追加（只追加，旧行不动）\n")
L.append("| 项 | 值 |")
L.append("|---|---|")
L.append("| 追加前 | %d 行 |" % before)
L.append("| 追加 | **%d 行** |" % len(ADD))
L.append("| 追加后 | %d 行 |" % after)
L.append("| 其中 `verified` | %d |" % sum(1 for a in ADD if a["status"] == "verified"))
L.append("")
L.append("路径：`%s`" % MANIFEST)
L.append("")
L.append("## 产物\n")
L.append("- `orphan_runs.csv`")
L.append("- 本文件")
L.append("")

io.open(os.path.join(OUT, "orphan_analysis.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
if recs:
    with io.open(os.path.join(OUT, "orphan_runs.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(recs[0].keys()))
        w.writeheader(); w.writerows(recs)
print("\n".join(L))
