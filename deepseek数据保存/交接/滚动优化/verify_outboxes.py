#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
★回填文件完整性校验器 —— 专门抓"日期标签与底层数据不一致"这类假成功。

为什么需要它（2026-09-12 实际踩到的坑）：
    第二批回填 `outbox_grid2_滚动优化.jsonl` 的 864 行 **from/to 被标成测试段区间**
    （2025.05.01~2025.07.31 等），但**每一行的 net / trades / profit_factor / ... / xml
    都与第一批（训练段）逐位相同** —— 底层数据其实还是第一批的训练段结果，
    只是日期标签被换成了测试段。
    → 若我不做这个校验，就会把"训练段结果"当成"out-of-sample 结果"去拼 OOS 曲线，
      得出一个**完全虚假但看起来正常的交付结论**。这正是协议 §5-8 说的"假成功"。

校验逻辑：
    1. 同一 (grid_id, 参数组合) 在两个 outbox 里出现时，是否数值逐位相同
    2. `xml` 字段是否指向同一个文件（更强的证据：说明是同一份原始输出）
    3. 各 outbox 覆盖的日期区间是否互不相同（真的跑了不同段的话，区间应不同）

用法:
    python verify_outboxes.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ["outbox_grid_滚动优化.jsonl", "outbox_grid2_滚动优化.jsonl",
         "outbox_grid_v2_滚动优化.jsonl"]
COLS = ["net", "profit_factor", "expected_payoff", "recovery_factor",
        "sharpe", "dd_pct", "trades", "pass", "xml"]


def load(p):
    if not os.path.isfile(p):
        return None
    return [json.loads(l) for l in open(p, encoding="utf-8-sig") if l.strip()]


def fp(r):
    return (r.get("grid_id"), tuple(sorted((r.get("params") or {}).items())))


def main():
    data = {}
    print("=" * 78)
    print("各回填文件概览")
    print("=" * 78)
    for f in FILES:
        rows = load(os.path.join(HERE, f))
        if rows is None:
            print("  %-34s (不存在)" % f)
            continue
        data[f] = rows
        segs = sorted({(r.get("from"), r.get("to")) for r in rows})
        print("  %-34s %4d 行, 区间: %s" % (f, len(rows), segs))

    ok = True
    keys = [f for f in data if data[f]]
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            A = {fp(r): r for r in data[keys[i]]}
            B = {fp(r): r for r in data[keys[j]]}
            common = set(A) & set(B)
            if not common:
                continue
            same = [k for k in common
                    if all(str(A[k].get(c)) == str(B[k].get(c)) for c in COLS)]
            da = sorted({(A[k].get("from"), A[k].get("to")) for k in common})
            db = sorted({(B[k].get("from"), B[k].get("to")) for k in common})
            print()
            print("=" * 78)
            print("比对: %s  vs  %s" % (keys[i], keys[j]))
            print("=" * 78)
            print("  共同 (grid_id+参数) 指纹: %d" % len(common))
            print("  其中全部数值字段逐位相同: %d" % len(same))
            print("  A 侧日期: %s" % da)
            print("  B 侧日期: %s" % db)
            if same and da != db:
                ok = False
                print("  ★★ 判定：B 侧的行 = A 侧的数据 + 不同的日期标签")
                print("     → **日期标签与底层数据不一致**：B 侧声称的区间并未真正执行。")
                print("     → 不得把 B 侧当作 A 侧之外的独立结果使用。")
                # 展示一个样例
                k = same[0]
                print("     样例 grid_id=%s" % k[0])
                for c in ("net", "trades", "xml"):
                    print("       %-10s A=%s" % (c, A[k].get(c)))
                    print("       %-10s B=%s" % (c, B[k].get(c)))
            elif same:
                print("  ⚠️ 数值全同但日期也相同 → 属正常重复提交，无风险")

    print()
    print("=" * 78)
    print("结论: %s" % ("✅ 未发现日期标签与数据不一致" if ok
                     else "❌ 发现日期标签与底层数据不一致（见上）"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
