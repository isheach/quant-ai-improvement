#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
预检器：在跑 MT5 之前，静态检查请求是否可执行。

为什么需要它（实测教训）：
  * JPYRev 的 24 条请求**全部 no report**，因为 EA 的 OnInit 失败、
    而我把参数名校验交给了"跑完看结果" —— 浪费了整整一轮机时。
  * 子代理自建 EA 时容易漏 `FILE_COMMON`（审计文件写错位置）
    或漏 `OnTradeTransaction`（券商侧止损不入审计）。

本脚本只做静态检查，不启动 MT5：
  1. 请求 JSON 是否合法、必备字段是否齐全
  2. expert 是否已注册、对应 .mq5 是否存在
  3. **参数名是否真的在 EA 的 input 列表里**（这是 JPYRev 那次失败的关键）
  4. EA 是否有 `FILE_COMMON`（审计路径）
  5. EA 是否有 `OnTradeTransaction`（止损平仓是否入审计）
  6. 是否误用留白段

用法:
    python preflight.py 比特币
    python preflight.py 日元 --fix-report     # 只报告，不改任何文件
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BASE_DIR, "run_trend"))
sys.path.insert(0, HERE)

import runexp as R  # noqa: E402

EA_DIR = os.path.join(BASE_DIR, "mql5", "dshtools")


def ea_inputs(ea_path):
    """从 .mq5 里抽出所有 input 名（含 group）。"""
    if not os.path.isfile(ea_path):
        return None
    names = set()
    with open(ea_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r"\s*input\s+(?:group\s+)?(?:\w+\s+)*?(\w+)\s*=", line)
            if m:
                names.add(m.group(1))
    return names


def ea_source(ea_path):
    if not os.path.isfile(ea_path):
        return ""
    with open(ea_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def check(who):
    inbox = os.path.join(HERE, "inbox_%s.jsonl" % who)
    if not os.path.isfile(inbox):
        print("没有 inbox 文件: %s" % inbox)
        return 1

    reqs = []
    with open(inbox, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                reqs.append(json.loads(line))
            except Exception as e:
                print("  [错误] 第 %d 行 JSON 非法: %s" % (i, e))

    print("=" * 70)
    print("预检: %s   共 %d 条请求" % (who, len(reqs)))
    print("=" * 70)

    # EA 静态特征只查一次
    ea_info = {}
    for name, path in R.EXPERTS.items():
        full = os.path.join(EA_DIR, os.path.basename(path.replace("\\", "/")) + ".mq5")
        src = ea_source(full)
        ei = ea_inputs(full)
        ea_info[name] = {
            "path": full,
            "exists": os.path.isfile(full),
            "inputs": ei,
            "file_common": "FILE_COMMON" in src,
            "on_trade_tx": "OnTradeTransaction" in src,
            "latency": "InpLatencyMs" in src,
        }

    print("\n--- EA 静态特征 ---")
    for name, ei in ea_info.items():
        if not ei["exists"]:
            print("  %-9s ❌ 源文件缺失: %s" % (name, ei["path"]))
            continue
        print("  %-9s input=%d 个 | FILE_COMMON=%s | OnTradeTransaction=%s | 延迟参数=%s"
              % (name, len(ei["inputs"] or []),
                 "✅" if ei["file_common"] else "❌缺失",
                 "✅" if ei["on_trade_tx"] else "❌缺失",
                 "✅" if ei["latency"] else "❌缺失"))

    print("\n--- 逐条检查 ---")
    bad = 0
    for r in reqs:
        rid = r.get("req_id", "?")
        problems = []

        for k in ("req_id", "expert", "symbol", "phase", "deposit"):
            if k not in r:
                problems.append("缺字段 %s" % k)

        exp = r.get("expert", "trend")
        if exp not in R.EXPERTS:
            problems.append("expert 未注册: %s" % exp)
        else:
            ei = ea_info[exp]
            if not ei["exists"]:
                problems.append("EA 源文件缺失")
            else:
                base = {"meanrev": R.BASE_MEANREV,
                        "btcswing": R.BASE_BTCSWING,
                        "jpyrev": getattr(R, "BASE_JPYREV", {})}.get(exp, R.BASE_PARAMS)
                allowed = ei["inputs"] or set()
                for pk in (r.get("params") or {}):
                    if pk == "InpRunTag":
                        continue
                    if pk not in allowed:
                        problems.append("参数名 EA 不认: %s" % pk)

        ph = r.get("phase")
        if ph == "hold":
            problems.append("★使用了留白段（禁止）")
        if ph not in ("train", "valid", "test", "hold"):
            problems.append("phase 非法: %s" % ph)

        if problems:
            bad += 1
            print("  %-11s ❌ %s" % (rid, "; ".join(problems)))
        else:
            print("  %-11s ✅" % rid)

    print("\n结果: %d/%d 条有问题" % (bad, len(reqs)))
    if bad == 0:
        print("→ 可以安全提交给 MT5。")
    else:
        print("→ ★请把上面的问题回给子代理修正后再跑（避免整批 no report）。")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(check(sys.argv[1]))
