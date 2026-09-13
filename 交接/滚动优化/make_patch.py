#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
为 batch_run.py 生成"自定义分段（from/to 覆盖）"补丁。

背景（本线核心阻塞项）：
    当前 batch_run.py 的 run_request() 里，段的起止日期**只**来自
        ph = R.phases_for(sym)          # L139
        ini = R.make_ini(tag, phase, merged, sym, ph, dep, expert)   # L147
    请求里的 "from"/"to" 字段**完全没有被读取**（只在写回结果时从 ph 里读出来）。
    因此滚动窗口的每个窗口都会被跑成固定的 ROLL 三段：
        train 2018.02.09-2024.05.31 / valid 2024.06.01-2025.05.31 / test 2025.06.01-2026.05.31
    → 54 条请求会全部作废，且结果看起来"正常"，属于最危险的假成功。

本脚本产出 batch_run_wf_patched.py（不覆盖原文件），并用 ast.parse 验证语法。
"""
import ast
import difflib
import os

HANDOFF = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HANDOFF, "batch_run.py")
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_run_wf_patched.py")

ANCHOR = "    ini = R.make_ini(tag, phase, merged, sym, ph, dep, expert)"

PATCH = '''    # ★★ 滚动优化（walk-forward）自定义分段：请求里带 from/to 时覆盖该段默认日期。
    #    不带 from/to 的请求行为完全不变（向后兼容）。
    if req.get("from") and req.get("to"):
        ph = dict(ph)
        ph[phase] = (str(req["from"]), str(req["to"]))
    ini = R.make_ini(tag, phase, merged, sym, ph, dep, expert)'''


def main():
    with open(SRC, "r", encoding="utf-8") as fh:
        src = fh.read()

    n = src.count(ANCHOR)
    if n != 1:
        raise SystemExit("★锚点出现 %d 次（期望 1 次），拒绝打补丁" % n)
    line_no = src[:src.index(ANCHOR)].count("\n") + 1

    patched = src.replace(ANCHOR, PATCH)
    # ★原 batch_run.py 带 UTF-8 BOM，ast.parse 不能直接吃 BOM，故验证时剥掉
    ast.parse(patched.lstrip("\ufeff"))      # 语法验证

    with open(DST, "w", encoding="utf-8") as fh:
        fh.write(patched)

    diff = "".join(difflib.unified_diff(
        src.splitlines(True), patched.splitlines(True),
        "batch_run.py", "batch_run_wf_patched.py", n=4))
    with open(os.path.join(os.path.dirname(DST), "batch_run_patch.diff"), "w",
              encoding="utf-8") as fh:
        fh.write(diff)

    print("锚点位置: batch_run.py L%d（唯一匹配 ✅）" % line_no)
    print("补丁后语法: ast.parse 通过 ✅")
    print("已写出: %s" % DST)
    print("差异已写出: batch_run_patch.diff")
    print("\n--- diff ---")
    print(diff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
