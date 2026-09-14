#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JSB30 审计解析器（下游）

★GPT JSB30 裁定 §1-Q4 要求：
  · 发现【重复 header】立即失败（fail-close）
  · 报告注明历史 R4 存在重复 entry_time bug，JSB30 已修复

用法：
  python jsb30_parser.py check-header <trades.csv|reject_audit.csv>
  python jsb30_parser.py dump <trades.csv>
"""
from __future__ import annotations

import collections
import csv
import io
import os
import sys

EXPECTED_TRADES_COLS = [
    "run_tag", "symbol", "deal_ticket", "position_id",
    "entry_time_server", "entry_time_utc", "exit_time_server", "exit_time_utc",
    "entry", "exit", "volume", "profit", "swap", "commission", "net",
    "close_type", "exit_reason", "risk_budget", "actual_sl_risk",
    "reject_reason", "server_utc_offset",
    # ★N1R 新增：OrderCalcProfit 与独立合约公式的对照列
    "ocp_value", "formula_value", "ocp_err", "ocp_diff", "ocp_lim",
]
EXPECTED_REJECT_COLS = [
    "run_tag", "symbol", "utc_day", "server_time", "utc_time", "server_utc_offset",
    "reason", "range_hi", "range_lo", "atr", "range_atr_mult",
    "raw_lot", "final_lot", "risk_budget", "actual_risk",
]


class DuplicateHeaderError(Exception):
    pass


class SchemaError(Exception):
    pass


def read_header(path):
    with io.open(path, encoding="utf-8-sig", errors="ignore", newline="") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if line.strip():
                return next(csv.reader([line]))
    return []


def check_header(path, expected=None):
    """★重复 header 立即失败"""
    hdr = read_header(path)
    dup = [h for h, c in collections.Counter(hdr).items() if c > 1]
    if dup:
        raise DuplicateHeaderError(
            "★重复 header 列：%s  (file=%s)\n"
            "   → 按裁定 §1-Q4，下游解析器必须 fail-close。\n"
            "   → 注：历史 R4 文件（R4_JPY_*_A/trades.csv）存在此 bug（entry_time 出现两次），\n"
            "     JSB30 已修复；历史文件不修改、不重导。" % (dup, path))
    if expected is not None:
        miss = [c for c in expected if c not in hdr]
        extra = [c for c in hdr if c not in expected]
        if miss or extra:
            raise SchemaError("列不匹配 file=%s\n  缺:%s\n  多:%s" % (path, miss, extra))
    return hdr


def read_rows(path, expected=None):
    hdr = check_header(path, expected)
    out = []
    with io.open(path, encoding="utf-8-sig", errors="ignore", newline="") as f:
        r = csv.reader(f)
        next(r, None)
        for line in r:
            if len(line) != len(hdr):
                raise SchemaError("行字段数 %d != header %d file=%s" % (len(line), len(hdr), path))
            out.append(dict(zip(hdr, line)))
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    cmd, path = sys.argv[1], sys.argv[2]
    exp = EXPECTED_TRADES_COLS if "reject" not in os.path.basename(path).lower() else EXPECTED_REJECT_COLS
    try:
        if cmd == "check-header":
            h = check_header(path, exp)
            print("OK  header 唯一且列匹配（%d 列）: %s" % (len(h), path))
            return 0
        if cmd == "dump":
            rows = read_rows(path, exp)
            print("行数: %d" % len(rows))
            for r in rows[:5]:
                print("  " + " | ".join("%s=%s" % (k, r[k]) for k in list(r)[:8]))
            return 0
    except DuplicateHeaderError as e:
        print("FAIL(duplicate-header): %s" % e)
        return 1
    except SchemaError as e:
        print("FAIL(schema): %s" % e)
        return 1
    print("未知命令: %s" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())

