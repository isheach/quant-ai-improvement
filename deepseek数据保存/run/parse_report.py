#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
parse_report.py — 解析 MT5 策略测试器 HTML 报告，输出关键指标。

MT5 报告结构：<td colspan="3">Key:</td><td><b>Value</b></td>
所以键和值不一定相邻 —— 用「键 td 之后第一个非键 td」来取值。
用法： python parse_report.py <report.htm> [...] [--json]
"""
import argparse
import json
import os
import re
import sys

TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")


def clean(s):
    t = TAG.sub("", s)
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&")
          .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
    return " ".join(t.split()).strip()


def read_html(path):
    """MT5 的 HTML 报告是 UTF-16LE（带 BOM）；也兼容 UTF-8。"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-16", "utf-8-sig", "utf-8", "cp1252"):
        try:
            t = raw.decode(enc)
            if "<td" in t.lower() or "<html" in t.lower():
                return t
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse(path):
    html = read_html(path)

    cells = [clean(m.group(1)) for m in TD.finditer(html)]

    d, inputs = {}, {}
    for i, t in enumerate(cells):
        m = re.match(r"^(Inp[A-Za-z0-9_]+)=(.*)$", t)
        if m:
            inputs[m.group(1)] = m.group(2)
    d["_inputs"] = inputs
    d["_file"] = os.path.basename(path)

    # 键值配对：键 = 以 ':' 结尾的 td；值 = 其后第一个非空且不以 ':' 结尾的 td
    for i, t in enumerate(cells):
        if not t.endswith(":"):
            continue
        key = t[:-1].strip()
        if not key or key in d or key.startswith("Inp"):
            continue
        for j in range(i + 1, min(i + 4, len(cells))):
            v = cells[j]
            if not v or v.endswith(":"):
                continue
            d[key] = v
            break
    return d


NUM = re.compile(r"^-?[\d\s.,]+$")


def num(s):
    if s is None:
        return None
    s = s.replace("\xa0", "").replace(" ", "").replace(",", "")
    s = s.replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--table", action="store_true")
    args = ap.parse_args()

    res = [parse(p) for p in args.reports]
    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.table:
        keys = ["Initial Deposit", "Total Net Profit", "Profit Factor",
                "Expected Payoff", "Recovery Factor", "Sharpe Ratio",
                "Equity Drawdown Maximal", "Equity Drawdown Relative",
                "Balance Drawdown Maximal", "Total Trades",
                "Profit Trades (% of total)", "Largest loss trade",
                "Bars", "Ticks"]
        print("%-26s" % "EXP", end="")
        for k in keys:
            print("%14s" % k[:14], end="")
        print()
        for d in res:
            print("%-26s" % d["_file"][:26], end="")
            for k in keys:
                v = d.get(k, "-")
                print("%14s" % str(v)[:14], end="")
            print()
        return 0

    for d in res:
        print("=" * 78)
        print("REPORT: %s" % d["_file"])
        print("=" * 78)
        for k, v in d.items():
            if k.startswith("_"):
                continue
            print("  %-42s %s" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
