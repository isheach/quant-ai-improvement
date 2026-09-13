#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HTML 报告表格解析器（GPT 第三批裁定 Step 1 第 1 条：按表格字段解析，不要只用模糊正则）

MT5 报告为 UTF-16LE HTML，结构：
  <table> ... <td>标题</td><td><b>值</b></td> ... </table>
本解析器按 <tr>/<td> 单元格成对提取，规避跨行/嵌套带来的正则误配。
"""
from __future__ import annotations

import html as _html
import io
import os
import re


def _cells(tr_html):
    """提取一行内的全部单元格文本"""
    out = []
    for m in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", tr_html, re.S | re.I):
        t = re.sub(r"<[^>]+>", "", m.group(1))
        t = _html.unescape(t)
        t = t.replace("\xa0", " ").strip()
        out.append(t)
    return out


def parse_report(path):
    """
    返回 dict：
      kv      : {字段名: 值}          —— 从两列/多列键值对表提取
      deals   : [ [cells...], ... ]   —— Orders/Deals 明细表的行
      tables  : [ [rows...], ... ]    —— 全部表格（调试用）
    """
    if not os.path.isfile(path):
        return None
    raw = io.open(path, encoding="utf-16-le", errors="ignore").read()
    res = {"kv": {}, "deals": [], "tables": [], "path": path}

    for tb in re.findall(r"<table.*?</table>", raw, re.S | re.I):
        rows = [_cells(tr) for tr in re.findall(r"<tr.*?</tr>", tb, re.S | re.I)]
        rows = [r for r in rows if r]
        res["tables"].append(rows)
        for r in rows:
            # 键值对：偶数格 → 标题/值 交替（MT5 常把 4 个键值放一行）
            if len(r) >= 2 and len(r) % 2 == 0:
                for i in range(0, len(r), 2):
                    k, v = r[i], r[i + 1]
                    if k and k not in res["kv"]:
                        res["kv"][k.rstrip(":")] = v
            # 明细行：首格像时间戳 或 首格像订单号
            if r and (re.match(r"^\d{4}\.\d{2}\.\d{2}", r[0]) or re.match(r"^\d+$", r[0])):
                res["deals"].append(r)
    return res


def num(s):
    """从 '451.98 (22.17%)' / '39.95% (306.80)' / '1 620.86' 这类字符串取数"""
    if s is None:
        return None
    t = str(s).replace(" ", "").replace(",", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)", t)
    return float(m.group(1)) if m else None


def pct_of(s):
    """取百分数（优先取带 % 的那个）"""
    if s is None:
        return None
    t = str(s).replace(" ", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*%", t)
    if m:
        return float(m.group(1))
    return num(s)


def count_out_rows(deals):
    """统计明细表中 direction/type 列含 'out' 的行数（closing 行）"""
    n = 0
    for r in deals:
        joined = " ".join(r).lower()
        if re.search(r"\bout\b", joined) or "out by" in joined:
            n += 1
    return n


if __name__ == "__main__":
    import sys
    p = sys.argv[1]
    r = parse_report(p)
    if not r:
        print("无法读取", p)
        sys.exit(1)
    print("表格数:", len(r["tables"]))
    for k in ("Symbol", "Period", "Initial Deposit", "Bars", "Ticks", "Total Trades",
              "Total Deals", "Total Net Profit", "Equity Drawdown Maximal",
              "Equity Drawdown Relative", "Balance Drawdown Maximal",
              "Balance Drawdown Relative", "Profit Factor", "History Quality"):
        print("  %-28s = %s" % (k, r["kv"].get(k, "(缺)")))
    print("明细行数:", len(r["deals"]))
    print("含 out 的行数:", count_out_rows(r["deals"]))
    for row in r["deals"][:3]:
        print("  样例行:", row)
    for row in r["deals"][-3:]:
        print("  末三行:", row)
