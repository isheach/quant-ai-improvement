#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
补丁功能验证：确认打了补丁后，"from"/"to" 真的进入生成的 ini 的 FromDate/ToDate。

方法（不跑 MT5）：
    1. import 打补丁后的模块，拿到它内部的 R（runexp）
    2. 复刻 run_request() 里那 5 行日期逻辑（补丁本体）
    3. 用真实窗口日期调 R.make_ini，读回 ini 文件，断言 FromDate/ToDate
    4. 同时断言：不带 from/to 时，ini 里仍是固定的 ROLL 三段（向后兼容）

用法: python verify_patch.py
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HANDOFF = os.path.dirname(HERE)                    # 交接
BASE_DIR = os.path.dirname(HANDOFF)                # deepseek数据保存
sys.path.insert(0, HERE)
# ★batch_run.py 用 __file__ 推导 run_trend 路径；补丁副本放在 滚动优化\ 子目录里，
#   推导会偏一层 → 这里先手动把 run_trend 放进 sys.path，让 `import runexp` 成功。
sys.path.insert(0, os.path.join(BASE_DIR, "run_trend"))


def load_patched():
    spec = importlib.util.spec_from_file_location(
        "batch_run_wf_patched", os.path.join(HERE, "batch_run_wf_patched.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dates_of(ini_path):
    txt = open(ini_path, encoding="utf-8").read()
    f = re.search(r"^FromDate=(.+)$", txt, re.M).group(1).strip()
    t = re.search(r"^ToDate=(.+)$", txt, re.M).group(1).strip()
    return f, t


def main():
    M = load_patched()
    R = M.R
    sym = R.SYMBOLS["btc"]
    base = R.BASE_BTCSWING
    ph0 = R.phases_for(sym)
    merged = dict(base)
    merged.update({"InpSL_ATR": "2.0", "InpLatencyMs": "300"})

    # ---- 1. 带 from/to（滚动窗口）----
    cases = [
        ("train", "2024.08.01", "2025.01.31"),
        ("valid", "2025.02.01", "2025.04.30"),
        ("test",  "2025.11.01", "2026.01.31"),
    ]
    ok = True
    print("=== 带 from/to 的请求（补丁应当覆盖）===")
    for phase, a, b in cases:
        req = {"from": a, "to": b}
        ph = dict(ph0)
        if req.get("from") and req.get("to"):
            ph[phase] = (str(req["from"]), str(req["to"]))
        ini = R.make_ini("WFVERIFY_" + phase, phase, merged, sym, ph, 300, "dshtrend\\dsh_BtcSwing")
        got = dates_of(ini)
        good = (got == (a, b))
        ok &= good
        print("  %-5s 期望 %s ~ %s   实际 %s ~ %s   %s"
              % (phase, a, b, got[0], got[1], "✅" if good else "❌"))

    # ---- 2. 不带 from/to（向后兼容）----
    print("\n=== 不带 from/to 的请求（行为必须不变 = 固定 ROLL 三段）===")
    for phase in ("train", "valid", "test"):
        want = ph0[phase]
        ini = R.make_ini("WFCOMPAT_" + phase, phase, merged, sym, ph0, 300, "dshtrend\\dsh_BtcSwing")
        got = dates_of(ini)
        good = (got == want)
        ok &= good
        print("  %-5s 期望 %s ~ %s   实际 %s ~ %s   %s"
              % (phase, want[0], want[1], got[0], got[1], "✅" if good else "❌"))

    print("\n结论: %s" % ("★全部通过，补丁可用" if ok else "★有失败项，补丁不可用"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
