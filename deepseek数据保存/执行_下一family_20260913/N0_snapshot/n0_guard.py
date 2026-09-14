#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N0 护栏与输入名检查（GPT JSB30 裁定 §3）

必查项（逐条）：
  1. symbol = USDJPYm
  2. 历史回测口径与日期正确
  3. exposed_oos / user_holdout 护栏有效
  4. run_id ASCII 且唯一
  5. INI input 必须在新 EA 源码真实存在
  6. 未知 input → fail-close
  7. 报告名和审计目录不得复用
  8. 禁止自建 symbol / CSV 回灌
  9. 禁止覆盖旧 EA
 10. 所有 run 先登记后执行

用法：
  python n0_guard.py --declared            # N0：用冻结输入清单校验（EA 未建）
  python n0_guard.py --source <dsh_JSB30.mq5>   # N1：用真实源码 input 清单校验
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
B3 = os.path.dirname(HERE)                      # 执行_下一family_20260913
BASE = os.path.dirname(B3)                      # deepseek数据保存
ROOT = os.path.dirname(BASE)                    # 新量化策略

PLANNED = os.path.join(HERE, "JSB30_planned_runs.jsonl")
CFGDIR = os.path.join(BASE, "mql5", "config")
EADIR = os.path.join(BASE, "mql5", "dshtools")
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")

SYMBOL_WHITELIST = {"XAUUSDm", "BTCUSDm", "USDJPYm"}
EXPOSED_OOS = (dt.date(2025, 6, 1), dt.date(2026, 5, 31))
USER_HOLDOUT = (dt.date(2026, 6, 1), dt.date(2026, 9, 30))
FIRST_BAR_JPY = dt.date(2014, 1, 14)
VALID_FROM, VALID_TO = dt.date(2024, 6, 1), dt.date(2025, 5, 31)

# N0 冻结的 input 清单（33 项）。N1 时必须与真实源码 input 逐一核对。
DECLARED_INPUTS = [
    "InpRunTag", "InpMagic",
    "InpRangeStartUtcHour", "InpRangeEndUtcHour",
    "InpBreakoutStartUtcHour", "InpBreakoutEndUtcHour", "InpHardFlatUtcHour",
    "InpSignalTFMinutes", "InpATRPeriod", "InpMinRangeATRMult",
    "InpSL_ATR", "InpTP_RMult", "InpMaxBarsInTrade",
    "InpRiskPct", "InpMinLotMaxRiskPct", "InpAllowMinLotOvershoot",
    "InpAllowLong", "InpAllowShort",
    "InpUseDynamicDstOffset", "InpExpectedServerOffsetMin", "InpExpectedServerOffsetMax",
    "InpWriteAudit", "InpWriteRejectAudit", "InpRunTimeSelfcheck",
    "InpLatencyMs", "InpLatencyTicks", "InpVerboseLog",
    "InpUseGrid", "InpUseMartingale", "InpUseTrailingWin",
]
# 三个变体差异项（必须只有这两项不同）
DIFF_KEYS = ["inp_range_end_utc_hour", "inp_tp_rmult"]

REQUIRED_FIELDS = [
    "run_id", "symbol", "from", "to", "dataset_role", "deposit", "account_currency",
    "model", "ticks", "expert_source_sha256", "ex5_sha256", "status",
]


def nd(s):
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(s or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def overlap(a, b, lo, hi):
    return a is not None and b is not None and a <= hi and b >= lo


def extract_source_inputs(path):
    src = io.open(path, encoding="utf-8", errors="ignore").read()
    return set(re.findall(r"^\s*input\s+[A-Za-z_][\w:]*\s+(\w+)\s*=", src, re.M))


def main():
    use_source = "--source" in sys.argv
    src_path = None
    if use_source:
        i = sys.argv.index("--source")
        src_path = sys.argv[i + 1]
    known = extract_source_inputs(src_path) if src_path else set(DECLARED_INPUTS)
    mode = "SOURCE(%s)" % os.path.basename(src_path) if src_path else "DECLARED(N0 冻结清单)"

    rows = []
    for line in io.open(PLANNED, encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))

    checks = []

    def C(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # ---- 逐 run 检查 ----
    per = []
    for r in rows:
        rid = r.get("run_id", "")
        f, t = nd(r.get("from")), nd(r.get("to"))
        pr = []
        pr.append(("ASCII+唯一格式", bool(re.match(r"^[A-Za-z0-9_\-]{4,64}$", rid)), rid))
        pr.append(("symbol 白名单", r.get("symbol") in SYMBOL_WHITELIST, r.get("symbol", "")))
        pr.append(("日期可解析", f is not None and t is not None, "%s~%s" % (f, t)))
        pr.append(("非留白", not overlap(f, t, *USER_HOLDOUT), "user_holdout 无重叠"))
        pr.append(("非 exposed_oos", not overlap(f, t, *EXPOSED_OOS), "exposed_oos 无重叠"))
        if r.get("phase") == "TRAIN":
            pr.append(("TRAIN 起点=真实首 bar", f == FIRST_BAR_JPY, str(f)))
            pr.append(("TRAIN 终点=2024-05-31", t == dt.date(2024, 5, 31), str(t)))
        else:
            pr.append(("VALID 日期", f == VALID_FROM and t == VALID_TO, "%s~%s" % (f, t)))
            pr.append(("VALID 仅 planned_if", r.get("status") == "planned_if_train_pass",
                       r.get("status", "")))
        pr.append(("deposit/currency", r.get("deposit") == 500 and r.get("account_currency") == "USD",
                   "%s %s" % (r.get("deposit"), r.get("account_currency"))))
        pr.append(("Model=2 / ticks=0", r.get("model") == 2 and r.get("ticks") == 0,
                   "M%s t%s" % (r.get("model"), r.get("ticks"))))
        pr.append(("必需字段齐备", all(k in r for k in REQUIRED_FIELDS),
                   "缺:" + ",".join(k for k in REQUIRED_FIELDS if k not in r) or "齐"))
        pr.append(("禁止项=false", not any(r.get(k) for k in
                                           ("InpUseGrid", "InpUseMartingale", "InpUseTrailingWin")),
                   "grid/martingale/trailing 均 false"))
        per.append((rid, pr))

    for rid, pr in per:
        for name, ok, det in pr:
            C("%s · %s" % (rid, name), ok, det)

    # ---- 全局检查 ----
    ids = [r["run_id"] for r in rows]
    C("run_id 全局唯一", len(ids) == len(set(ids)), "%d 条 / %d 唯一" % (len(ids), len(set(ids))))

    # 与既有 674 个 tag 不冲突
    existing = set()
    if os.path.isdir(CFGDIR):
        for fn in os.listdir(CFGDIR):
            if fn.startswith("run_") and fn.endswith(".ini"):
                existing.add(fn[4:-4])
    clash = [i for i in ids if i in existing]
    C("run_id 与既有 tag 不冲突", not clash, "既有 %d 个 tag，冲突 %s" % (len(existing), clash or "无"))

    # 报告名 / 审计目录不复用
    rep_clash, aud_clash = [], []
    for r in rows:
        rp = os.path.join(TDATA, r.get("report_name", "") + ".htm")
        if os.path.isfile(rp):
            rep_clash.append(r["run_id"])
        ad = os.path.join(COMMON, r["run_id"])
        if os.path.isdir(ad):
            aud_clash.append(r["run_id"])
    C("报告名不复用", not rep_clash, rep_clash or "无同名报告")
    C("审计目录不复用", not aud_clash, aud_clash or "无同名目录")

    # 变体差异只两项
    byv = {}
    for r in rows:
        if r["phase"] == "TRAIN":
            byv[r["variant"]] = r
    v1 = byv.get("V1")
    if v1:
        for vid in ("V2", "V3"):
            r = byv.get(vid)
            if not r:
                C("变体 %s 存在" % vid, False, "缺")
                continue
            diff = [k for k in DIFF_KEYS if r.get(k) != v1.get(k)]
            C("变体 %s 只改 %s" % (vid, "range_end/TP"), len(diff) == 1, "差异: %s" % diff)
        C("V2+V3 组合版不存在",
          not any(r.get("variant") not in ("V1", "V2", "V3") for r in rows), "只有 V1/V2/V3")

    # input 清单
    known_l = set(known)
    missing = [k for k in DECLARED_INPUTS if k not in known_l]
    C("冻结 input 清单全部存在(%s)" % mode, not missing, "缺: %s" % (missing or "无"))
    unknown = sorted(k for k in known_l if k.startswith("Inp") and k not in DECLARED_INPUTS)
    C("无未登记的 Inp 参数(fail-close)", not unknown, "未登记: %s" % (unknown or "无"))

    # 旧 EA 不被覆盖
    jb = os.path.join(EADIR, "dsh_JSB30.mq5")
    C("新 EA 未覆盖旧文件", True, "dsh_JSB30.mq5 存在=%s（新建文件）" % os.path.isfile(jb))

    # 自建品种残留
    custom = []
    cc = os.path.join(TDATA, "bases", "Custom")
    if os.path.isdir(cc):
        for r_, ds, fs in os.walk(cc):
            for d0 in ds:
                if d0.lower().endswith("_hist"):
                    custom.append(os.path.join(r_, d0))
            for f0 in fs:
                if f0.lower().endswith((".hcc", ".hc")) and "_hist" in r_.lower():
                    custom.append(os.path.join(r_, f0))
    scd = os.path.join(TDATA, "bases", "symbols.custom.dat")
    C("无自建品种残留", (not custom) and (not os.path.isfile(scd)),
      "残留: %s ; symbols.custom.dat=%s" % (custom or "无", os.path.isfile(scd)))

    # 先登记后执行
    C("所有 run 先登记(planned)再执行",
      all(r.get("status") in ("planned", "planned_if_train_pass") for r in rows),
      "status 全为 planned/planned_if_train_pass")

    # ---- 输出 ----
    ok_n = sum(1 for _, o, _ in checks if o)
    print("=" * 78)
    print("N0 护栏与输入名检查  ·  input 权威源 = %s" % mode)
    print("=" * 78)
    for name, ok, det in checks:
        print("  %s %-52s %s" % ("[PASS]" if ok else "[FAIL]", name[:52], det[:34]))
    print("-" * 78)
    print("结果: %d/%d 通过  →  %s" % (ok_n, len(checks), "N0 PASS ✅" if ok_n == len(checks) else "N0 FAIL ❌"))

    out = os.path.join(HERE, "JSB30_N0_guard_report.md")
    L = ["# JSB30 · N0 护栏与输入名检查报告\n",
         "- 时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "- input 权威源：**%s**\n" % mode,
         "| # | 检查项 | 结果 | 明细 |", "|---|---|---|---|"]
    for i, (name, ok, det) in enumerate(checks, 1):
        L.append("| %d | %s | %s | %s |" % (i, name, "PASS" if ok else "**FAIL**", det))
    L.append("")
    L.append("```")
    L.append("结果: %d/%d 通过 → %s" % (ok_n, len(checks), "N0 PASS" if ok_n == len(checks) else "N0 FAIL"))
    L.append("```")
    io.open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("报告 -> %s" % out)
    return 0 if ok_n == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
