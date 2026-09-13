#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
滚动优化线 —— 选参与拼接分析流水线（walk-forward analysis）

设计目标：
    1. 选参规则**写成代码而不是散文** —— 规则必须在看到 OOS 结果之前就固定，否则等于事后凑规则
    2. 数据缺失时**明确报缺**，绝不拿别的段的数据顶替
       （2026-09-12 实际踩过：outbox_grid2 的 864 行是训练段数据 + 测试段日期标签，
        见 报告_003.md §5 与 verify_outboxes.py）
    3. 回填一到就能一键出结果

段命名契约（必须严格一致）：
    wf-<win>-tr-<dir>   训练段
    wf-<win>-va-<dir>   验证段
    wf-<win>-te-<dir>   测试段
    dir ∈ {on, off}

选参规则（★预登记，见 报告_002.md §5.3）：
    ① 频率门槛：训练段 trades >= MIN_TRADES_TRAIN（6 个月窗口 → 笔/年 = trades*2）
    ② 训练段按 net 降序取前 TOP_K
    ③ 在这 TOP_K 的参数区域内，选**验证段 net 最大**者
    ④ on/off 两支路各走 ①-③，取验证段 net 更高者作为该窗口的最终配置
    ⑤ 该配置的**测试段**结果 = 该窗口的 out-of-sample 收益
    ⑥ 三个窗口的测试段首尾相接 = 拼接 OOS 曲线

用法:
    python wf_analysis.py                # 完整分析（缺数据会明确报缺）
    python wf_analysis.py --stage train  # 只做训练段选参（现在就能跑）
"""
import argparse
import collections
import json
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 各段数据来源（按段分开，避免串用）
SRC = {
    "tr": "outbox_grid_滚动优化.jsonl",      # 训练段（第一批，864 行）
    "va": "outbox_grid_v2_滚动优化.jsonl",   # 验证段（待回填）
    "te": "outbox_grid_v2_滚动优化.jsonl",   # 测试段（待回填）
}

WINDOWS = {
    "w0": {"tr": ("2024.08.01", "2025.01.31"), "va": ("2025.02.01", "2025.04.30"),
           "te": ("2025.05.01", "2025.07.31")},
    "w1": {"tr": ("2024.11.01", "2025.04.30"), "va": ("2025.05.01", "2025.07.31"),
           "te": ("2025.08.01", "2025.10.31")},
    "w2": {"tr": ("2025.02.01", "2025.07.31"), "va": ("2025.08.01", "2025.10.31"),
           "te": ("2025.11.01", "2026.01.31")},
}

# ---- ★预登记的规则参数（改这里等于改规则，必须记录在报告里）----
MIN_TRADES_TRAIN = 25     # 6 个月 → >=50 笔/年（用户门槛）
TOP_K = 30                # 训练段按 net 取前 K，再进验证段

PARAM_KEYS = ["InpSL_ATR", "InpDonchianBars", "InpMaxBarsInTrade",
              "InpFilterEMA", "InpFilterSlopeBars"]
AXES = ["InpSL_ATR", "InpDonchianBars", "InpMaxBarsInTrade",
        "InpFilterEMA", "InpFilterSlopeBars"]


def F(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def load(name):
    p = os.path.join(HERE, name)
    if not os.path.isfile(p):
        return None, p
    rows = []
    for l in open(p, encoding="utf-8-sig"):
        l = l.strip()
        if l:
            rows.append(json.loads(l))
    return rows, p


def key_of(r):
    """(window, segment, direction) + 参数指纹

    ★名称归一化（重要）：
      第一批的 grid_id 是 `wf-w0-t-on`（当年 `-t-` 表示 train），
      新约定是 `wf-w0-tr-on` / `wf-w0-va-on` / `wf-w0-te-on`。
      此处把两者统一成 tr/va/te，避免"同一个 `-t-` 同时被当成 train 与 test"再次发生
      （该命名冲突就是 2026-09-12 那次假成功的源头，见 报告_003.md §5）。
    """
    gid = r.get("grid_id", "")
    parts = gid.split("-")
    if len(parts) < 4 or parts[0] != "wf":
        return None, None
    win, seg, dr = parts[1], parts[2], parts[3]
    # 旧名 `t` → 按 from/to 判定到底属于哪一段（不靠猜）
    if seg == "t":
        got = (str(r.get("from")), str(r.get("to")))
        seg = None
        for s in ("tr", "va", "te"):
            if WINDOWS.get(win, {}).get(s) == got:
                seg = s
                break
        if seg is None:
            return None, None       # 日期不属于任何已知段 → 拒绝，不猜
    if seg not in ("tr", "va", "te"):
        return None, None
    pk = tuple(str((r.get("params") or {}).get(k, "")) for k in PARAM_KEYS)
    return (win, seg, dr), pk


def index_rows(rows):
    """-> {(win,seg,dir): {paramkey: row}}"""
    out = collections.defaultdict(dict)
    for r in rows:
        k, pk = key_of(r)
        if k:
            out[k][pk] = r
    return out


def check_segment_consistency(rows, seg, label):
    """★校验：该段的行，其 from/to 必须与 WINDOWS 里该段的期望区间一致。"""
    bad = collections.Counter()
    for r in rows:
        k, _ = key_of(r)
        if not k:
            continue
        win, s, _d = k
        if s != seg:
            continue
        exp = WINDOWS.get(win, {}).get(seg)
        if exp and (str(r.get("from")), str(r.get("to"))) != exp:
            bad[(win, str(r.get("from")), str(r.get("to")), exp)] += 1
    if bad:
        print("  ❌ %s 段存在日期不匹配的行：" % label)
        for k, n in bad.items():
            print("     win=%s 实际=%s~%s 期望=%s  (%d 行)" % (k[0], k[1], k[2], k[3], n))
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["all", "train"])
    a = ap.parse_args()

    print("=" * 78)
    print("滚动优化线 —— 选参与拼接分析")
    print("规则: 训练段 trades>=%d 且 net>0 → 前 %d 名 → 验证段 net 最大 → 测试段为 OOS"
          % (MIN_TRADES_TRAIN, TOP_K))
    print("=" * 78)

    # ---- 载入三段 ----
    data, present = {}, {}
    for seg in ("tr", "va", "te"):
        rows, p = load(SRC[seg])
        # 只保留该段自己的行（同一文件可能同时含 va/te）
        rows = [r for r in (rows or []) if (key_of(r)[0] or ("", "", ""))[1] == seg]
        data[seg] = rows
        present[seg] = bool(rows)
        print("\n[%s] %s" % (seg, SRC[seg]))
        if not rows:
            print("   ⚠️ 无数据（或文件不存在）→ 本段相关结论不可产出")
            continue
        print("   %d 行" % len(rows))
        ok = check_segment_consistency(rows, seg, seg)
        if ok:
            print("   ✅ 该段所有行的 from/to 与窗口契约一致")

    if not present["tr"]:
        print("\n★训练段数据缺失，无法继续。")
        return 2

    idx = {seg: index_rows(data[seg]) for seg in ("tr", "va", "te")}

    # ---- 逐窗口选参 ----
    print("\n" + "=" * 78)
    print("★逐窗口选参（只用 tr + va；te 绝不参与选择）")
    print("=" * 78)
    selection = {}
    for w in sorted(WINDOWS):
        print("\n### 窗口 %s" % w.upper())
        best = None
        for d in ("off", "on"):
            trk = (w, "tr", d)
            if trk not in idx["tr"]:
                print("   dir=%-3s 训练段无数据" % d)
                continue
            cands = [r for r in idx["tr"][trk].values()
                     if (F(r.get("trades"), 0) or 0) >= MIN_TRADES_TRAIN
                     and (F(r.get("net"), -1e9) or -1e9) > 0]
            if not cands:
                print("   dir=%-3s ❌ 无候选通过频率门槛 (trades>=%d 且 net>0)"
                      % (d, MIN_TRADES_TRAIN))
                continue
            cands.sort(key=lambda r: -(F(r.get("net"), 0) or 0))
            topk = cands[:TOP_K]
            print("   dir=%-3s 训练段过关 %d 组 → 取前 %d 名" % (d, len(cands), len(topk)))

            vak = (w, "va", d)
            if vak in idx["va"]:
                vmap = idx["va"][vak]
                scored = []
                for r in topk:
                    pk = tuple(str((r.get("params") or {}).get(k, "")) for k in PARAM_KEYS)
                    vr = vmap.get(pk)
                    if vr is not None:
                        scored.append((F(vr.get("net"), -1e9) or -1e9, r, vr))
                if not scored:
                    print("        ⚠️ 验证段网格里找不到这 %d 名的参数组合（取值不在验证网格范围内）" % len(topk))
                    pick, vrow = topk[0], None
                else:
                    scored.sort(key=lambda x: -x[0])
                    _, pick, vrow = scored[0]
                    print("        验证段可比对 %d 组；选中验证段 net=%+.1f"
                          % (len(scored), scored[0][0]))
            else:
                print("        ⚠️ 验证段无数据 → 退化为『只用训练段选参』（合法但少一道确认）")
                pick, vrow = topk[0], None

            pk = pick.get("params", {})
            print("        → 选中: %s | 训练 net=%+.1f tr=%s"
                  % (" ".join("%s=%s" % (k.replace("Inp", ""), pk.get(k)) for k in PARAM_KEYS),
                     F(pick.get("net"), 0), pick.get("trades")))
            if vrow is not None:
                print("          验证 net=%+.1f tr=%s" % (F(vrow.get("net"), 0), vrow.get("trades")))

            vnet = F(vrow.get("net"), None) if vrow is not None else None
            rank = vnet if vnet is not None else (F(pick.get("net"), 0) or 0)
            if best is None or rank > best[0]:
                best = (rank, d, pick, vrow)

        if best is None:
            print("   ★该窗口无可用配置 → 记为「空仓窗口」（不下单）")
            selection[w] = None
        else:
            _, d, pick, vrow = best
            selection[w] = {"dir": d, "tr": pick, "va": vrow}
            print("   ★该窗口最终方向: AllowShort=%s" % ("true" if d == "on" else "false"))

    # ---- 测试段（OOS）----
    print("\n" + "=" * 78)
    print("★拼接 out-of-sample 曲线（各窗口用自己选出的参数）")
    print("=" * 78)
    if not present["te"]:
        print("\n⚠️ 测试段无数据 → **拼接 OOS 曲线不可产出**。")
        print("   需要的文件: %s（网格 id: wf-<win>-te-<dir>）" % SRC["te"])
        print("   在拿到测试段之前，我不会用训练段数据顶替（见 报告_003.md §5）。")
        return 0

    total_net, total_tr, legs = 0.0, 0, []
    print("  %-6s %-5s %-12s %10s %8s %8s" % ("win", "dir", "测试段区间", "net", "trades", "pf"))
    for w in sorted(WINDOWS):
        sel = selection.get(w)
        if sel is None:
            print("  %-6s %-5s %-12s %10s %8s %8s" % (w.upper(), "-", "-", "空仓", 0, "-"))
            continue
        pk = tuple(str((sel["tr"].get("params") or {}).get(k, "")) for k in PARAM_KEYS)
        tek = (w, "te", sel["dir"])
        trow = idx["te"].get(tek, {}).get(pk)
        if trow is None:
            print("  %-6s %-5s %-12s ★测试段找不到该参数组合 → 缺失" % (w.upper(), sel["dir"], ""))
            continue
        net = F(trow.get("net"), 0) or 0
        tr = F(trow.get("trades"), 0) or 0
        total_net += net
        total_tr += tr
        legs.append((w, net, tr))
        print("  %-6s %-5s %-12s %+10.2f %8d %8s"
              % (w.upper(), sel["dir"], "%s~%s" % (WINDOWS[w]["te"]), net, tr,
                 trow.get("profit_factor")))
    print("\n合计 OOS net = %+.2f   总笔数 = %d" % (total_net, total_tr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
