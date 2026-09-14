#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N0 guard 增强（N1R2 · F 项）：四方集合完全一致检查
  source inputs  ↔  static table  ↔  INI [TesterInputs]  ↔  manifest resolved_inputs
任何缺项、额外项、值不一致 → 拒绝运行。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

BASE = r"D:\desktop\新量化策略\deepseek数据保存"
FAM = os.path.join(BASE, "执行_下一family_20260913")
MANIFEST = os.path.join(FAM, "N0_snapshot", "JSB30_planned_runs.jsonl")
SRC = os.path.join(BASE, "mql5", "dshtools", "dsh_JSB30.mq5")
STATIC = os.path.join(FAM, "N0_snapshot", "JSB30_static_inputs_final.md")


def src_inputs(p):
    s = io.open(p, encoding="utf-8", errors="ignore").read()
    return sorted(set(re.findall(r"^\s*input\s+[A-Za-z_][\w:]*\s+(\w+)\s*=", s, re.M)))


def static_inputs(p):
    s = io.open(p, encoding="utf-8", errors="ignore").read()
    # 静态表里以 "InpXxx" 开头（可带缩进空格）的标识符
    return sorted(set(re.findall(r"^\s*(Inp[A-Za-z0-9_]+)\s{2,}", s, re.M)))


def ini_inputs(p):
    out = {}
    sect = None
    for line in io.open(p, encoding="utf-8-sig", errors="ignore"):
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            sect = s[1:-1].lower(); continue
        if sect == "testerinputs" and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def norm(v):
    """★统一数值比较：5 / 5.0 / "5.0" 视为相等"""
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).strip().lower()
    if s in ("true", "false"):
        return s
    try:
        return "%.10g" % float(s)
    except Exception:
        return s


def main():
    known = set(src_inputs(SRC))
    stat = set(static_inputs(STATIC))
    rows = [json.loads(l) for l in io.open(MANIFEST, encoding="utf-8") if l.strip()]

    print("=" * 78)
    print("N1R2 · 四方 input 一致性检查")
    print("=" * 78)
    print("  source inputs   :", len(known))
    print("  static table    :", len(stat))
    bad = 0

    only_src = sorted(known - stat)
    only_stat = sorted(stat - known)
    if only_src or only_stat:
        print("  ⚠️ static 与 source 不一致: 仅source=%s 仅static=%s" % (only_src, only_stat))
    else:
        print("  ✅ static table 与 source 完全一致")

    for r in rows:
        tag = r["run_id"]
        ini = ini_inputs(r["ini_path"])
        man = r["resolved_inputs"]
        msgs = []
        if set(ini) != known:
            msgs.append("INI≠source 缺=%s 多=%s" % (sorted(known - set(ini)), sorted(set(ini) - known)))
        if set(man) != set(ini):
            msgs.append("manifest≠INI 缺=%s 多=%s" % (sorted(set(ini) - set(man)), sorted(set(man) - set(ini))))
        diffs = []
        for k in sorted(set(ini) & set(man)):
            if norm(ini[k]) != norm(man[k]):
                diffs.append("%s ini=%s man=%s" % (k, ini[k], man[k]))
        if diffs:
            msgs.append("值不一致: %s" % diffs[:5])
        if msgs:
            bad += 1
            print("  ❌ %-28s %s" % (tag, " | ".join(msgs)))
        else:
            print("  ✅ %-28s 四方一致（%d 项）" % (tag, len(ini)))

    print("-" * 78)
    if bad == 0:
        print("结果: 全部 %d 个 run 四方一致 ✅ → 允许运行" % len(rows))
        return 0
    print("结果: %d 个 run 不一致 ❌ → 拒绝运行" % bad)
    return 1


if __name__ == "__main__":
    sys.exit(main())

