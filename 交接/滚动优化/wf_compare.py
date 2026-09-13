#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
滚动优化线 —— 三项核心对比

1. **漂移 vs 锁定**：walk-forward 选出的参数（每窗口不同） vs 一套固定参数跑全程
2. **on/off 归一性检查**：总调度报告 wf-w0-te / wf-w1-va 的 on/off 逐位相同 —— 查是否因为"该窗口没有空单信号"
3. **in-sample vs out-of-sample 落差**：训练段/验证段挑得漂亮，测试段还剩多少

用法: python wf_compare.py
"""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PARAM_KEYS = ["InpSL_ATR", "InpDonchianBars", "InpMaxBarsInTrade",
              "InpFilterEMA", "InpFilterSlopeBars"]
FIXED_ROBUST = {"InpSL_ATR": "1.0", "InpDonchianBars": "48", "InpMaxBarsInTrade": "240",
                "InpFilterEMA": "50", "InpFilterSlopeBars": "5"}
WINDOWS = {
    "w0": {"tr": ("2024.08.01", "2025.01.31"), "va": ("2025.02.01", "2025.04.30"),
           "te": ("2025.05.01", "2025.07.31")},
    "w1": {"tr": ("2024.11.01", "2025.04.30"), "va": ("2025.05.01", "2025.07.31"),
           "te": ("2025.08.01", "2025.10.31")},
    "w2": {"tr": ("2025.02.01", "2025.07.31"), "va": ("2025.08.01", "2025.10.31"),
           "te": ("2025.11.01", "2026.01.31")},
}


def F(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def load(fn):
    p = os.path.join(HERE, fn)
    if not os.path.isfile(p):
        return []
    return [json.loads(l) for l in open(p, encoding="utf-8-sig") if l.strip()]


def key(r):
    g = r.get("grid_id", "").split("-")
    if len(g) < 4:
        return None
    win, seg, dr = g[1], g[2], g[3]
    if seg == "t":
        got = (str(r.get("from")), str(r.get("to")))
        seg = next((s for s in ("tr", "va", "te") if WINDOWS.get(win, {}).get(s) == got), None)
    return (win, seg, dr) if seg else None


def pk(r):
    return tuple(str((r.get("params") or {}).get(k, "")) for k in PARAM_KEYS)


def main():
    v2 = load("outbox_grid_v2_滚动优化.jsonl")
    tr1 = load("outbox_grid_滚动优化.jsonl")
    idx = collections.defaultdict(dict)
    for r in tr1 + v2:
        k = key(r)
        if k:
            idx[k][pk(r)] = r

    # ================= 2. on/off 归一性 =================
    print("=" * 92)
    print("★检查 1：on/off 逐位相同的网格 —— 是否因为该窗口没有空单信号？")
    print("=" * 92)
    print("  判据：若 AllowShort 无效，则 on/off 的**笔数应完全相同**；")
    print("        若只是该窗口没有空单，则笔数相同、且 on 侧不可能比 off 侧有更多成交。")
    print()
    print("  %-12s %-8s %8s %8s   %s" % ("网格", "方向", "net范围", "笔数范围", "on-off 差异"))
    for w in ("w0", "w1", "w2"):
        for seg in ("va", "te"):
            a = idx.get((w, seg, "on"), {})
            b = idx.get((w, seg, "off"), {})
            if not a or not b:
                continue
            same = sum(1 for k in a if k in b
                       and all(str(a[k].get(c)) == str(b[k].get(c))
                               for c in ("net", "trades", "profit_factor", "dd_pct")))
            difftr = sum(1 for k in a if k in b
                         and F(a[k].get("trades"), 0) != F(b[k].get("trades"), 0))
            difnet = sum(1 for k in a if k in b
                         and F(a[k].get("net"), 0) != F(b[k].get("net"), 0))
            n = len(set(a) & set(b))
            na = [F(x.get("net"), 0) for x in a.values()]
            ta = [F(x.get("trades"), 0) for x in a.values()]
            print("  wf-%s-%-6s %-8s [%6.1f,%6.1f] [%3d,%3d]   共同%d组: 全同%d, 笔数不同%d, net不同%d"
                  % (w, seg, "on", min(na), max(na), int(min(ta)), int(max(ta)),
                     n, same, difftr, difnet))
    print()
    print("  → 解读：若某网格『笔数不同 = 0』，说明 on/off 的交易集合完全一样，")
    print("     即该窗口内**没有任何一笔空单成交**（不是 AllowShort 失效）。")

    # ================= 1. 漂移 vs 锁定 =================
    print()
    print("=" * 92)
    print("★检查 2：漂移（walk-forward，每窗口选参） vs 锁定（一套固定参数跑全程）")
    print("=" * 92)
    SEL = {   # 来自 wf_analysis.py 的输出（预登记规则选出）
        "w0": ("on", {"InpSL_ATR": "1.5", "InpDonchianBars": "48", "InpMaxBarsInTrade": "48",
                      "InpFilterEMA": "50", "InpFilterSlopeBars": "5"}),
        "w1": ("on", {"InpSL_ATR": "1.0", "InpDonchianBars": "48", "InpMaxBarsInTrade": "240",
                      "InpFilterEMA": "125", "InpFilterSlopeBars": "10"}),
        "w2": ("on", {"InpSL_ATR": "1.5", "InpDonchianBars": "72", "InpMaxBarsInTrade": "48",
                      "InpFilterEMA": "125", "InpFilterSlopeBars": "5"}),
    }
    for label, sel in (("漂移版(walk-forward选参)", "SEL"), ("锁定版(固定参数)", "FIX")):
        pass

    print("\n  【A】漂移版 = 每窗口用自己选出的参数")
    print("  %-6s %-4s %-24s %9s %7s %7s" % ("win", "dir", "测试段区间", "net", "tr", "pf"))
    tot_a = tot_a_tr = 0
    for w in sorted(WINDOWS):
        d, p = SEL[w]
        row = idx.get((w, "te", d), {}).get(tuple(p[k] for k in PARAM_KEYS))
        if row is None:
            print("  %-6s %-4s 缺失" % (w, d))
            continue
        net, tr = F(row.get("net"), 0), F(row.get("trades"), 0)
        tot_a += net
        tot_a_tr += tr
        print("  %-6s %-4s %-24s %+9.2f %7d %7s"
              % (w, d, "%s~%s" % WINDOWS[w]["te"], net, tr, row.get("profit_factor")))
    print("  %-6s %-4s %-24s %+9.2f %7d" % ("合计", "", "", tot_a, tot_a_tr))

    print("\n  【B】锁定版 = 全部窗口用同一套 %s"
          % " ".join("%s=%s" % (k.replace("Inp", ""), v) for k, v in FIXED_ROBUST.items()))
    print("  %-6s %-4s %-24s %9s %7s %7s" % ("win", "dir", "测试段区间", "net", "tr", "pf"))
    tot_b = tot_b_tr = 0
    for w in sorted(WINDOWS):
        row = idx.get((w, "te", "off"), {}).get(tuple(FIXED_ROBUST[k] for k in PARAM_KEYS))
        if row is None:
            print("  %-6s %-4s 缺失" % (w, "off"))
            continue
        net, tr = F(row.get("net"), 0), F(row.get("trades"), 0)
        tot_b += net
        tot_b_tr += tr
        print("  %-6s %-4s %-24s %+9.2f %7d %7s"
              % (w, "off", "%s~%s" % WINDOWS[w]["te"], net, tr, row.get("profit_factor")))
    print("  %-6s %-4s %-24s %+9.2f %7d" % ("合计", "", "", tot_b, tot_b_tr))

    months = 9.0
    print("\n  → 漂移版 %+.2f (%d 笔, %.0f 笔/年)   锁定版 %+.2f (%d 笔, %.0f 笔/年)   差 %+.2f"
          % (tot_a, tot_a_tr, tot_a_tr / months * 12, tot_b, tot_b_tr, tot_b_tr / months * 12,
             tot_a - tot_b))

    # ================= 3. in-sample vs OOS =================
    print()
    print("=" * 92)
    print("★检查 3：in-sample（训练/验证挑出来的好看数字） vs out-of-sample（测试段真实结果）")
    print("=" * 92)
    print("  %-6s %-30s %-30s %-30s" % ("win", "训练段(6个月)", "验证段(3个月)", "测试段(3个月) OOS"))
    for w in sorted(WINDOWS):
        d, p = SEL[w]
        k = tuple(p[x] for x in PARAM_KEYS)
        cells = []
        for seg in ("tr", "va", "te"):
            row = idx.get((w, seg, d), {}).get(k)
            cells.append("net%+7.2f tr%3d" % (F(row.get("net"), 0), F(row.get("trades"), 0))
                         if row else "缺失")
        print("  %-6s %-30s %-30s %-30s" % (w, cells[0], cells[1], cells[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
