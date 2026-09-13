#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 2 附：编译前校验 INI [TesterInputs] 与源码 input 名称
（GPT 第三批裁定 Step 2 第 6 条：未知参数直接拒绝启动，防止 MT5 静默忽略）
"""
from __future__ import annotations

import io
import os
import re
import sys


def extract_inputs(mq5_path):
    """从源码提取全部 input 名称与类型"""
    src = io.open(mq5_path, encoding="utf-8", errors="ignore").read()
    out = {}
    for m in re.finditer(r"^\s*input\s+([A-Za-z_][\w:]*)\s+(\w+)\s*=", src, re.M):
        out[m.group(2)] = m.group(1)
    return out


def parse_ini_inputs(ini_path):
    if not os.path.isfile(ini_path):
        return None
    sect = None
    out = {}
    for line in io.open(ini_path, encoding="utf-8-sig", errors="ignore"):
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            sect = s[1:-1].lower()
            continue
        if sect == "testerinputs" and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def check(mq5_path, ini_path):
    known = extract_inputs(mq5_path)
    given = parse_ini_inputs(ini_path)
    if given is None:
        return dict(ok=False, reason="ini 不存在", missing=[], unknown=[], known=len(known), given=0)
    unknown = [k for k in given if k not in known]
    missing = [k for k in known if k not in given]
    return dict(ok=(len(unknown) == 0), reason="" if not unknown else "未知参数",
                unknown=unknown, missing=missing, known=len(known), given=len(given))


if __name__ == "__main__":
    mq5 = sys.argv[1]
    ini = sys.argv[2] if len(sys.argv) > 2 else ""
    r = check(mq5, ini)
    print("源码 input 数: %d" % r["known"])
    print("INI 参数数  : %d" % r["given"])
    print("未知参数(必须为空): %s" % (r["unknown"] or "（无）✅"))
    print("未提供(用默认值): %s" % (r["missing"] or "（无）"))
    print("判定:", "✅ 通过" if r["ok"] else "❌ 拒绝启动 —— %s" % r["reason"])
    sys.exit(0 if r["ok"] else 1)
