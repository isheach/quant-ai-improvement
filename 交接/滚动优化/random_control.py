#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
★随机选参对照 —— 判定"用验证段挑参数"是否真的优于随机

为什么需要它（`报告_004.md` §7）：
    我先做了 Spearman 检验：验证段排名 vs 测试段排名的相关 ρ 在 3/5 个窗口上 ≈0 或为负。
    **但那只能说"未发现预测力"，不能说"已证明无预测力"**（n 只有 5）。
    本脚本给出正式判定：**若"随机挑 1 个"的 OOS 分布能经常达到甚至超过
    "验证段挑最好"的 OOS，那么滚动选参这个动作就不产生价值。**

方法（不需要 MT5，纯本地重采样）：
    对每个窗口：
      候选池 = 训练段过关（trades>=25 且 net>0）且验证段/测试段都有数据的参数组合
      S_val  = 在候选池里按【验证段 net 最大】挑 1 个 → 取其测试段净利（这就是我的方法）
      S_rnd  = 在候选池里【均匀随机】挑 1 个 → 取其测试段净利（重复 N 次）
    把三个窗口的测试段净利求和 → 得到 S_val_total 与 S_rnd_total 的分布
    判定：p = P(随机 >= 我的方法)

用法: python random_control.py [--n 20000]
"""
import argparse
import collections
import json
import os
import random
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARAM = ["InpSL_ATR", "InpDonchianBars", "InpMaxBarsInTrade",
         "InpFilterEMA", "InpFilterSlopeBars"]
W = {
    "w0": {"tr": ("2024.08.01", "2025.01.31"), "va": ("2025.02.01", "2025.04.30"),
           "te": ("2025.05.01", "2025.07.31")},
    "w1": {"tr": ("2024.11.01", "2025.04.30"), "va": ("2025.05.01", "2025.07.31"),
           "te": ("2025.08.01", "2025.10.31")},
    "w2": {"tr": ("2025.02.01", "2025.07.31"), "va": ("2025.08.01", "2025.10.31"),
           "te": ("2025.11.01", "2026.01.31")},
}
MIN_TR = 25


def F(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def load():
    idx = collections.defaultdict(dict)
    for fn in ("outbox_grid_滚动优化.jsonl", "outbox_grid_v2_滚动优化.jsonl"):
        p = os.path.join(HERE, fn)
        if not os.path.isfile(p):
            continue
        for l in open(p, encoding="utf-8-sig"):
            if not l.strip():
                continue
            r = json.loads(l)
            g = r.get("grid_id", "").split("-")
            if len(g) < 4:
                continue
            win, seg, dr = g[1], g[2], g[3]
            if seg == "t":
                got = (str(r.get("from")), str(r.get("to")))
                seg = next((s for s in ("tr", "va", "te") if W.get(win, {}).get(s) == got), None)
            if seg not in ("tr", "va", "te"):
                continue
            idx[(win, seg, dr)][tuple(str((r.get("params") or {}).get(k, "")) for k in PARAM)] = r
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    a = ap.parse_args()
    rng = random.Random(20260912)          # 固定种子，结果可复现
    idx = load()

    print("=" * 84)
    print("★随机选参对照：我的方法（验证段挑最好） vs 随机挑 1 个")
    print("  重复次数 N = %d，随机种子 = 20260912" % a.n)
    print("=" * 84)

    pools = {}
    for win in W:
        for dr in ("off", "on"):
            tr, va, te = idx[(win, "tr", dr)], idx[(win, "va", dr)], idx[(win, "te", dr)]
            pool = [k for k in tr
                    if (F(tr[k].get("trades"), 0) or 0) >= MIN_TR
                    and (F(tr[k].get("net"), -1e9) or -1e9) > 0
                    and k in va and k in te]
            pools[(win, dr)] = pool
    print("\n各窗口/方向的候选池大小（训练段过关 且 va/te 都有数据）：")
    for k in sorted(pools):
        print("   %s-%-3s  %d" % (k[0], k[1], len(pools[k])))

    # ---- 我的方法：每窗口选"验证段最好"，方向取验证段更高的那支 ----
    print("\n" + "-" * 84)
    print("【我的方法】每窗口：在池里挑验证段 net 最大者；on/off 取验证段更高者")
    print("-" * 84)
    mine_total, mine_detail = 0.0, []
    for win in sorted(W):
        best = None
        for dr in ("off", "on"):
            pool = pools[(win, dr)]
            if not pool:
                continue
            k = max(pool, key=lambda k: F(idx[(win, "va", dr)][k].get("net"), -1e9) or -1e9)
            vn = F(idx[(win, "va", dr)][k].get("net"), 0)
            tn = F(idx[(win, "te", dr)][k].get("net"), 0)
            if best is None or vn > best[0]:
                best = (vn, dr, k, tn)
        if best is None:
            print("   %s: 无候选" % win)
            continue
        _, dr, k, tn = best
        mine_total += tn
        mine_detail.append((win, dr, dict(zip(PARAM, k)), tn))
        print("   %s: dir=%-3s 测试段 net=%+8.2f  %s"
              % (win, dr, tn, " ".join("%s=%s" % (p.replace("Inp", ""), k[i])
                                       for i, p in enumerate(PARAM))))
    print("   【我的方法】三窗口合计 = %+.2f" % mine_total)

    # ---- 随机对照 ----
    print("\n" + "-" * 84)
    print("【随机对照】每窗口：在池里均匀随机挑 1 个（方向也随机）")
    print("-" * 84)
    usable = [w for w in sorted(W) if pools[(w, "off")] or pools[(w, "on")]]
    dist = []
    for _ in range(a.n):
        s = 0.0
        for win in usable:
            dr = rng.choice(["off", "on"])
            if not pools[(win, dr)]:
                dr = "on" if dr == "off" else "off"
            pool = pools[(win, dr)]
            if not pool:
                continue
            k = rng.choice(pool)
            s += F(idx[(win, "te", dr)][k].get("net"), 0) or 0
        dist.append(s)
    dist.sort()
    ge = sum(1 for x in dist if x >= mine_total)
    p = ge / len(dist)
    print("   随机分布: 均值 %+.2f  中位 %+.2f  标准差 %.2f" % (st.mean(dist), st.median(dist), st.pstdev(dist)))
    print("   分位点:  5%% %+.2f | 25%% %+.2f | 50%% %+.2f | 75%% %+.2f | 95%% %+.2f"
          % (dist[int(.05 * len(dist))], dist[int(.25 * len(dist))], dist[int(.50 * len(dist))],
             dist[int(.75 * len(dist))], dist[int(.95 * len(dist))]))
    print("   最大 %+.2f   最小 %+.2f" % (dist[-1], dist[0]))
    print()
    print("   ★我的方法 = %+.2f" % mine_total)
    print("   ★P(随机 >= 我的方法) = %.3f   （随机里 %d/%d 次达到或超过）" % (p, ge, len(dist)))
    print()
    if p > 0.05:
        print("   ❌ 判定：我的方法**没有显著超过随机**（p=%.3f > 0.05）" % p)
        print("      → 【结论】『用验证段挑参数』这个动作在本参数空间下未产生可测量的价值。")
        print("      → 用户『不停按最新情况修正参数』的思路，在本设定下**未被数据支持**。")
    else:
        print("   ✅ 判定：我的方法显著超过随机（p=%.3f <= 0.05）" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
