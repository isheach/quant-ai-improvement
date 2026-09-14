#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N1.5 · JSB30 最小工程 smoke（GPT JSB30 裁定 §5）

只验证工程链，不产生任何收益结论：
  1. EA 加载
  2. UTC/server round-trip（EA 内 SELFTEST 输出）
  3. DST（三类周）
  4. CSV schema（重复 header fail-close + 列匹配）
  5. 文件写入（FileWrite 成功）
  6. 每日最多一笔
  7. hard-flat
  8. 审计链（净利一致 / 成本相加一致 / 无活动仓位）

★禁区：不用 smoke 盈利调整参数、不选时段、不比较 V1/V2/V3、
        不读取 exposed_oos(2025-06-01~2026-05-31) 或 user_holdout(2026-06-01~2026-09-30)
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))   # 执行_下一family_20260913
N0 = HERE
BASE = os.path.dirname(HERE)                         # deepseek数据保存
ROOT = os.path.dirname(BASE)                         # 新量化策略
sys.path.insert(0, os.path.join(N0, "N0_snapshot"))

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
CFGDIR = os.path.join(BASE, "mql5", "config")
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
EA_SRC = os.path.join(BASE, "mql5", "dshtools", "dsh_JSB30.mq5")
EA_EX5 = os.path.join(TDATA, "MQL5", "Experts", "dshtrend", "dsh_JSB30.ex5")
OUT = os.path.join(HERE, "smoke")
os.makedirs(OUT, exist_ok=True)

TAG = "DS260914_JSB30_SMOKE_V1"
# ★短历史片段，必须落在 TRAIN 内（2014-01-14 ~ 2024-05-31）
SMOKE_FROM, SMOKE_TO = "2014.01.14", "2014.02.14"
DEPOSIT = 500

P = {
    "InpRunTag": TAG, "InpMagic": "20260914",
    "InpRangeStartUtcHour": "0", "InpRangeEndUtcHour": "6",
    "InpBreakoutStartUtcHour": "7", "InpBreakoutEndUtcHour": "12",
    "InpHardFlatUtcHour": "20",
    "InpSignalTFMinutes": "30", "InpATRPeriod": "14", "InpMinRangeATRMult": "0.5",
    "InpSL_ATR": "1.0", "InpTP_RMult": "1.5", "InpMaxBarsInTrade": "16",
    "InpRiskPct": "1.5", "InpMinLotMaxRiskPct": "3.0",
    "InpAllowMinLotOvershoot": "false",
    "InpAllowLong": "true", "InpAllowShort": "true",
    "InpUseDynamicDstOffset": "true",
    "InpExpectedServerOffsetMin": "2", "InpExpectedServerOffsetMax": "3",
    "InpWriteAudit": "true", "InpWriteRejectAudit": "true", "InpRunTimeSelfcheck": "true",
    "InpLatencyMs": "0", "InpLatencyTicks": "0", "InpVerboseLog": "true",
    "InpUseGrid": "false", "InpUseMartingale": "false", "InpUseTrailingWin": "false",
}


def sha256(p):
    import hashlib
    if not os.path.isfile(p):
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def make_ini():
    lines = [
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]", "Expert=dshtrend\\dsh_JSB30", "Symbol=USDJPYm", "Period=M1",
        "Model=2", "Optimization=0",
        "FromDate=" + SMOKE_FROM, "ToDate=" + SMOKE_TO,
        "ForwardMode=0", "Deposit=" + str(DEPOSIT), "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_" + TAG, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]",
    ]
    lines += ["%s=%s" % (k, v) for k, v in P.items()]
    path = os.path.join(CFGDIR, "run_%s.ini" % TAG)
    io.open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def kill_mt5():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(3)


def parse_html(path):
    if not os.path.isfile(path):
        return {}
    s = io.open(path, encoding="utf-16-le", errors="ignore").read()
    t = re.sub(r"<[^>]+>", "|", s)
    t = re.sub(r"\|+", "|", t)
    out = {}
    for k in ("Bars", "Ticks", "Initial Deposit", "Total Trades", "Total Deals",
              "Total Net Profit", "Profit Factor", "Equity Drawdown Relative",
              "Equity Drawdown Maximal", "History Quality", "Symbol", "Period"):
        m = re.search(re.escape(k) + r"\|([^|]{0,40})", t)
        if m:
            out[k] = m.group(1).strip()
    return out


def main():
    res = []
    def C(name, ok, det=""):
        res.append((name, bool(ok), det))

    print("=" * 78)
    print("N1.5 · JSB30 最小工程 smoke")
    print("  tag    = %s" % TAG)
    print("  窗口   = %s ~ %s（TRAIN 内）" % (SMOKE_FROM, SMOKE_TO))
    print("  口径   = USDJPYm / %d USD / Model=2 / ticks=0" % DEPOSIT)
    print("=" * 78)

    ini = make_ini()
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "guard", os.path.join(N0, "N0_snapshot", "check_inputs.py"))
    ci = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(ci)
    except Exception:
        ci = None
    if ci:
        r = ci.check(EA_SRC, ini)
        C("input schema 校验", r["ok"], "未知: %s" % (r["unknown"] or "无"))

    kill_mt5()
    print("\n启动 MT5 ...")
    proc = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
    try:
        proc.wait(timeout=900)
    except subprocess.TimeoutExpired:
        print("! 超时"); kill_mt5()
    time.sleep(2)

    rep = os.path.join(TDATA, "report_%s.htm" % TAG)
    h = parse_html(rep)
    adir = os.path.join(COMMON, TAG)
    tp = os.path.join(adir, "trades.csv")
    rj = os.path.join(adir, "reject_audit.csv")
    sc = os.path.join(adir, "audit_selfcheck.csv")

    d = os.path.join(OUT, TAG)
    os.makedirs(d, exist_ok=True)
    for f in (rep, tp, rj, sc, ini):
        if os.path.isfile(f):
            shutil.copy2(f, d)

    print("\n--- 1) EA 加载 / 报告 ---")
    C("EA 加载（报告存在）", os.path.isfile(rep), rep.split("\\")[-1])
    bars = h.get("Bars", "")
    C("Bars > 0（非 environment_error）", bars not in ("", "0"), "Bars=%s" % bars)
    C("Ticks > 0", h.get("Ticks", "") not in ("", "0"), "Ticks=%s" % h.get("Ticks"))
    C("Initial Deposit = 500", h.get("Initial Deposit", "").startswith("500"),
      "dep=%s" % h.get("Initial Deposit"))
    C("Symbol = USDJPYm", h.get("Symbol", "") == "USDJPYm", h.get("Symbol", ""))

    print("\n--- 2/3) UTC 自测与 DST（EA 日志）---")
    log = os.path.join(TDATA, "Tester", "logs")
    latest = None
    if os.path.isdir(log):
        fs = sorted((os.path.join(log, f) for f in os.listdir(log) if f.endswith(".log")),
                    key=os.path.getmtime)
        latest = fs[-1] if fs else None
    selftest_lines, offfail = [], None
    if latest:
        try:
            txt = io.open(latest, encoding="utf-16-le", errors="ignore").read()
            if "SELFTEST" not in txt:
                txt = io.open(latest, encoding="utf-8", errors="ignore").read()
            selftest_lines = [l for l in txt.splitlines() if "SELFTEST" in l]
            # 取本 tag 的
            selftest_lines = [l for l in selftest_lines if TAG in l] or selftest_lines
            m = re.findall(r"offsetFail=(\d+)", txt)
            offfail = m[-1] if m else None
        except Exception as e:
            print("   读取日志失败:", e)
    okN = None
    for l in selftest_lines:
        mm = re.search(r"SELFTEST 汇总：(\d+)/(\d+)", l)
        if mm:
            okN = (int(mm.group(1)), int(mm.group(2)))
    C("round-trip 自测执行", bool(selftest_lines), "%d 行 SELFTEST" % len(selftest_lines))
    if okN:
        C("round-trip 全通过", okN[0] == okN[1], "%d/%d" % okN)
    else:
        # 回退：从行内统计
        nok = sum(1 for l in selftest_lines if "roundtrip=OK" in l)
        tot = sum(1 for l in selftest_lines if "roundtrip=" in l and "汇总" not in l)
        C("round-trip 全通过", tot > 0 and nok == tot, "%d/%d（行内统计）" % (nok, tot))
    C("offset 推导无失败", offfail in (None, "0"), "offsetFail=%s" % offfail)

    print("\n--- 4) CSV schema（重复 header fail-close）---")
    if ci:
        pass
    try:
        import importlib.util as iu
        spec2 = iu.spec_from_file_location("jp", os.path.join(N0, "N0_snapshot", "jsb30_parser.py"))
        jp = iu.module_from_spec(spec2)
        spec2.loader.exec_module(jp)
        hdr = jp.check_header(tp, jp.EXPECTED_TRADES_COLS)
        C("trades.csv header 唯一且列匹配", True, "%d 列" % len(hdr))
        if os.path.isfile(rj):
            hr = jp.check_header(rj, jp.EXPECTED_REJECT_COLS)
            C("reject_audit.csv header 唯一且列匹配", True, "%d 列" % len(hr))
        else:
            C("reject_audit.csv 存在", False, "无文件（本片段可能无拒单）")
    except Exception as e:
        C("trades.csv header 唯一且列匹配", False, str(e)[:70])

    print("\n--- 5) 文件写入 ---")
    C("trades.csv 已写出", os.path.isfile(tp), "%d B" % (os.path.getsize(tp) if os.path.isfile(tp) else 0))
    C("audit_selfcheck.csv 已写出", os.path.isfile(sc), "%d B" % (os.path.getsize(sc) if os.path.isfile(sc) else 0))

    print("\n--- 6/7/8) 交易约束与审计链 ---")
    rows = []
    if os.path.isfile(tp):
        with io.open(tp, encoding="utf-8-sig", errors="ignore", newline="") as f:
            rows = list(csv.DictReader(f))
    C("trades 行数 > 0", len(rows) > 0, "%d 笔" % len(rows))

    # 每日最多一笔（按 entry_time_utc 的日期）
    byday = {}
    for r in rows:
        k = (r.get("entry_time_utc") or "")[:10]
        byday[k] = byday.get(k, 0) + 1
    bad = {k: v for k, v in byday.items() if v > 1}
    C("每个 UTC 日 <= 1 笔", not bad, "违反: %s" % (bad or "无"))

    # hard-flat：出场 UTC 时间应 < 20:00
    late = [r for r in rows if (r.get("exit_time_utc") or " ")[11:13].isdigit()
            and int((r.get("exit_time_utc") or "  ")[11:13]) >= 20]
    C("hard-flat（出场 UTC < 20:00）", not late, "越界 %d 笔" % len(late))

    # 成本一致
    costbad = []
    for r in rows:
        try:
            pr = float(r["profit"] or 0); sw = float(r["swap"] or 0)
            cm = float(r["commission"] or 0); nt = float(r["net"] or 0)
            if abs((pr + sw + cm) - nt) > 0.005:
                costbad.append(r.get("deal_ticket"))
        except Exception:
            costbad.append(r.get("deal_ticket"))
    C("profit+swap+commission = net", not costbad, "不一致: %s" % (costbad[:5] or "无"))

    # ticket 唯一
    tks = [r.get("deal_ticket") for r in rows]
    C("deal_ticket 唯一", len(tks) == len(set(tks)), "%d/%d" % (len(set(tks)), len(tks)))

    # position 可回溯 / 字段非空
    miss = [r.get("deal_ticket") for r in rows
            if not r.get("position_id") or not r.get("entry_time_utc")
            or r.get("entry_time_utc") == "undetermined"]
    C("position/schema 字段齐备", not miss, "缺: %s" % (miss[:5] or "无"))

    # 审计净利 vs 报告净利
    anet = sum(float(r["net"] or 0) for r in rows)
    rnet = None
    try:
        rnet = float((h.get("Total Net Profit") or "0").replace(" ", "").replace(",", ""))
    except Exception:
        pass
    if rnet is not None:
        tol = max(0.02, 0.001 * max(1.0, abs(rnet)))
        C("审计净利 == 报告净利", abs(anet - rnet) <= tol,
          "审计 %.2f / 报告 %.2f / 差 %.2f / 容差 %.3f" % (anet, rnet, anet - rnet, tol))
    else:
        C("报告净利可解析", False, "无法解析")

    # 结束时无活动仓位（selfcheck 列）
    if os.path.isfile(sc):
        with io.open(sc, encoding="utf-8-sig", errors="ignore", newline="") as f:
            s = list(csv.DictReader(f))
        if s:
            s0 = s[0]
            C("结束时无活动仓位", s0.get("active_positions") == "0",
              "active=%s" % s0.get("active_positions"))
            C("offset_undetermined = 0", s0.get("offset_undetermined") == "0",
              "val=%s" % s0.get("offset_undetermined"))
            C("audit_failed = 0", s0.get("audit_failed") == "0", "val=%s" % s0.get("audit_failed"))

    # ---- 汇总 ----
    okn = sum(1 for _, o, _ in res if o)
    print("\n" + "=" * 78)
    for n, o, dd in res:
        print("  %s %-40s %s" % ("[PASS]" if o else "[FAIL]", n, dd[:50]))
    print("-" * 78)
    print("N1.5 结果: %d/%d  →  %s" % (okn, len(res), "PASS ✅" if okn == len(res) else "FAIL ❌"))

    L = ["# JSB30 · N1.5 最小工程 smoke 报告\n",
         "- 时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "- tag：`%s`" % TAG,
         "- 窗口：`%s ~ %s`（TRAIN 内短片段）" % (SMOKE_FROM, SMOKE_TO),
         "- 口径：`USDJPYm` / %d USD / Model=2 / ticks=0" % DEPOSIT,
         "- EA：源码 `%s` / EX5 `%s`\n" % (sha256(EA_SRC)[:32] + "…", sha256(EA_EX5)[:32] + "…"),
         "**★本轮只验证工程链；不使用 smoke 盈利做任何参数/时段调整（GPT §5）。**\n",
         "| # | 检查项 | 结果 | 明细 |", "|---|---|---|---|"]
    for i, (n, o, dd) in enumerate(res, 1):
        L.append("| %d | %s | %s | %s |" % (i, n, "PASS" if o else "**FAIL**", dd))
    L += ["", "```", "N1.5: %d/%d → %s" % (okn, len(res), "PASS" if okn == len(res) else "FAIL"), "```", "",
          "## 原始报告数值（仅供工程核对，不作为收益结论）", "",
          "| 字段 | 值 |", "|---|---|"]
    for k in ("Bars", "Ticks", "Initial Deposit", "Total Trades", "Total Deals",
              "Total Net Profit", "Profit Factor", "Equity Drawdown Relative", "History Quality"):
        L.append("| %s | %s |" % (k, h.get(k, "")))
    L += ["", "## SELFTEST 原始输出（UTC/DST round-trip）", "", "```"]
    L += (selftest_lines or ["（无 SELFTEST 行）"])
    L += ["```", ""]
    io.open(os.path.join(OUT, "JSB30_N1_5_smoke_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("报告 -> %s" % os.path.join(OUT, "JSB30_N1_5_smoke_report.md"))
    return 0 if okn == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
