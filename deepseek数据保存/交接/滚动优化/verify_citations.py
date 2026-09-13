#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
引用行号 / 源文件版本 的权威复核。

为什么需要它：本项目纪律要求"引用源码行号前必须先重读该行"。
子代理曾因"用推理覆盖真实代码、倒推行号"被驳回两次。
本脚本把报告里引用的每一行**重新读出来打印**，并给出各源文件的哈希，
以便报告里写明"我引用的到底是哪个版本"。

用法: python verify_citations.py
"""
import hashlib
import os

HANDOFF = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 交接
BASE = os.path.dirname(HANDOFF)                                        # deepseek数据保存

FILES = {
    "batch_run.py": os.path.join(HANDOFF, "batch_run.py"),
    "runexp.py":    os.path.join(BASE, "run_trend", "runexp.py"),
    "preflight.py": os.path.join(HANDOFF, "preflight.py"),
    "dsh_BtcSwing.mq5": os.path.join(BASE, "mql5", "dshtools", "dsh_BtcSwing.mq5"),
}

# 报告里引用的行号 → 期望内容关键词（用于自动断言，避免倒推行号）
CITES = [
    ("batch_run.py", 40,  "_ASCII ="),
    ("batch_run.py", 132, "phase = req.get"),
    ("batch_run.py", 135, "sym_key = req.get"),
    ("batch_run.py", 136, "if sym_key not in R.SYMBOLS"),
    ("batch_run.py", 139, "ph = R.phases_for(sym)"),
    ("batch_run.py", 142, "base = R.BASE_MEANREV"),
    ("batch_run.py", 147, "ini = R.make_ini"),
    ("batch_run.py", 155, "no report"),
    ("batch_run.py", 171, '"from": ph[phase][0]'),
    ("batch_run.py", 172, '"to": ph[phase][1]'),
    ("batch_run.py", 193, "who = sys.argv[1]"),
    ("runexp.py",    70,  "BASE_BTCSWING = {"),
    ("runexp.py",   126, "SYMBOLS = {"),
    ("runexp.py",   206, "def make_ini("),
    ("runexp.py",   210, "d_from, d_to = ph[phase]"),
    ("runexp.py",   223, '"Model=2"'),
    ("runexp.py",   224, '"FromDate=" + d_from'),
    ("preflight.py", 124, '"meanrev": R.BASE_MEANREV'),
    ("preflight.py", 125, '"btcswing": R.BASE_BTCSWING'),
]


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()[:16]


def main():
    print("=" * 78)
    print("源文件版本（报告必须写明引用的是哪个版本）")
    print("=" * 78)
    cache = {}
    for name, path in FILES.items():
        if not os.path.isfile(path):
            print("  %-18s ❌ 缺失 %s" % (name, path))
            continue
        lines = open(path, encoding="utf-8-sig", errors="ignore").read().splitlines()
        cache[name] = lines
        st = os.stat(path)
        print("  %-18s %6d 行  %7d B  sha256:%s  mtime=%s"
              % (name, len(lines), st.st_size, sha(path),
                 __import__("datetime").datetime.fromtimestamp(st.st_mtime)
                 .strftime("%Y-%m-%d %H:%M:%S")))

    print()
    print("=" * 78)
    print("逐条复核报告引用的行号")
    print("=" * 78)
    bad = 0
    for name, n, kw in CITES:
        lines = cache.get(name)
        if lines is None or n > len(lines):
            print("  %-18s L%-4d ❌ 文件缺失或行号越界" % (name, n))
            bad += 1
            continue
        txt = lines[n - 1]
        ok = kw in txt
        if not ok:
            bad += 1
        print("  %-18s L%-4d %s | %s" % (name, n, "✅" if ok else "❌ 期望含 %r" % kw, txt.strip()))

    print()
    print("结果: %d 条引用有问题" % bad)
    if bad == 0:
        print("→ 报告里的全部行号引用复核通过。")
    else:
        print("→ ★必须在报告里改正上面标 ❌ 的行号。")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
