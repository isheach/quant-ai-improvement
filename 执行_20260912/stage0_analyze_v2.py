#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Stage 0 v2 深析：为什么 verified = 0，以及哪些 run 可被"救回"verified"""
import collections
import csv
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "stage0_provenance_v2", "provenance_inventory_v2.csv")
rows = list(csv.DictReader(io.open(P, encoding="utf-8-sig")))

L = []
L.append("# Stage 0 v2 · 深析：为什么 `verified` = 0\n")

# 1. 按 run_id 前缀分类
def prefix(r):
    t = r["run_id"]
    for p in ("OPT_", "BT_", "GD_", "JP_", "XX_", "SWT_"):
        if t.startswith(p):
            return p
    return "OTHER"

pref = collections.Counter(prefix(r) for r in rows)
L.append("## 1. 按 run_id 前缀（区分网格 pass 与单跑）\n")
L.append("| 前缀 | 记录数 | 含义 |")
L.append("|---|---:|---|")
MEAN = {"OPT_": "**网格 pass**（优化模式的 pass，无独立 ini/report/审计）",
        "BT_": "单跑（BTC）", "GD_": "单跑（黄金）", "JP_": "单跑（日元）",
        "XX_": "探针/网格原样 tag", "SWT_": "新建验收 run", "OTHER": "其他"}
for k, v in pref.most_common():
    L.append("| `%s` | %d | %s |" % (k, v, MEAN.get(k, "")))
L.append("")

# 2. 单跑（BT_/GD_/JP_/SWT_）的状态分布 —— 这些才有资格谈 verified
single = [r for r in rows if prefix(r) in ("BT_", "GD_", "JP_", "SWT_")]
L.append("## 2. **单跑**记录的状态（真正可谈 provenance 的部分）\n")
L.append("| status | 条数 |")
L.append("|---|---:|")
for k, v in collections.Counter(r["status"] for r in single).most_common():
    L.append("| `%s` | %d |" % (k, v))
L.append("")
L.append("单跑中的标记分布：")
L.append("")
L.append("| 标记 | 条数 |")
L.append("|---|---:|")
sf = collections.Counter()
for r in single:
    for x in r["flags"].split(";"):
        if x:
            sf[x] += 1
for k, v in sf.most_common():
    L.append("| `%s` | %d |" % (k, v))
L.append("")

# 3. 关键：缺 ini 的比例
noini = [r for r in rows if "NO_INI" in r["flags"]]
L.append("## 3. ★`NO_INI` 的来源（v1 没暴露这个）\n")
L.append("`NO_INI` = **找不到该 run 实际喂给 MT5 的输入文件** → 无法证明参数。")
L.append("按前缀分解：")
L.append("")
L.append("| 前缀 | NO_INI 条数 |")
L.append("|---|---:|")
for k, v in collections.Counter(prefix(r) for r in noini).most_common():
    L.append("| `%s` | %d |" % (k, v))
L.append("")

# 4. 有 ini 的单跑 —— 这些最接近 verified
has = [r for r in single if "NO_INI" not in r["flags"]]
L.append("## 4. **同时有 ini 的单跑**（最接近 `verified` 的集合）\n")
L.append("| 项 | 值 |")
L.append("|---|---|")
L.append("| 条数 | **%d** |" % len(has))
for k, v in collections.Counter(r["status"] for r in has).most_common():
    L.append("| status=`%s` | %d |" % (k, v))
L.append("")
if has:
    hf = collections.Counter()
    for r in has:
        for x in r["flags"].split(";"):
            if x:
                hf[x] += 1
    L.append("这些记录的标记分布：")
    L.append("")
    L.append("| 标记 | 条数 |")
    L.append("|---|---:|")
    for k, v in hf.most_common():
        L.append("| `%s` | %d |" % (k, v))
    L.append("")
    # 完全干净的
    clean = [r for r in has if r["flags"] in ("", "AUDIT_RECONCILE_REQUIRED")]
    L.append("**★其中标记只有 `AUDIT_RECONCILE_REQUIRED` 或空（即除审计口径外无其他问题）的：%d 条**"
             % len(clean))
    L.append("")
    if clean:
        L.append("| run_id | 品种 | 入金 | 模型 | 审计行 | mt5笔数 | position_id列 |")
        L.append("|---|---|---|---|---:|---:|---|")
        for r in clean[:30]:
            L.append("| `%s` | %s | %s | %s | %s | %s | %s |"
                     % (r["run_id"], r["symbol"], r["deposit"], r["model"],
                        r["audit_rows"], r["trade_count_mt5"], r["audit_has_position_id"]))
        L.append("")

# 5. AUDIT_RECONCILE_REQUIRED 的真相
L.append("## 5. `AUDIT_RECONCILE_REQUIRED` = 3811（占 100%）的真实原因\n")
nopid = sum(1 for r in rows if r["audit_has_position_id"] == "0")
L.append("```")
L.append("判据 = (笔数不一致) 或 (审计缺 position_id 列)")
L.append("实测：缺 position_id 列的记录 = %d / %d" % (nopid, len(rows)))
L.append("→ 因为 position_id 列是【2026-09-12 才加入】的，")
L.append("  所有历史 run 的审计都没有它 → 全部命中该标记。")
L.append("→ 这不是「新发现的错误」，而是「用新标准衡量旧数据」的必然结果。")
L.append("```")
L.append("")

# 6. 未来日期
fp = os.path.join(HERE, "stage0_provenance_v2", "future_dates.csv")
if os.path.isfile(fp):
    fd = list(csv.DictReader(io.open(fp, encoding="utf-8-sig")))
    L.append("## 6. 未来日期扫描（%d 条）\n" % len(fd))
    L.append("| 文件 | 日期 |")
    L.append("|---|---|")
    for r in fd[:20]:
        L.append("| `%s` | %s |" % (r["path"], r["date"]))
    L.append("")
    gg = [r for r in fd if "报告_032" in r["path"] or "比特币" in r["path"]]
    L.append("**★GPT 点名的 `交接\\比特币\\报告_032.md`：%s**"
             % ("命中未来日期 " + gg[0]["date"] if gg else "本次扫描未命中（需人工复核该文件）"))
    L.append("")

out = os.path.join(HERE, "stage0_provenance_v2", "analysis_v2.md")
io.open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("→", out)
print("\n".join(L[:60]))

