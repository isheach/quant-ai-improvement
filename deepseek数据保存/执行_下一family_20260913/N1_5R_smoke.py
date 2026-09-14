#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N1.5R · JSB30 真实历史工程 smoke（GPT 裁定 §N1.5R）

★与 N1.5 的区别：
  · 不再用 2014 的 0-data 窗口
  · 预先固定三组 TRAIN 内工程窗口（不根据盈利结果调整）
  · dataset_role 标记为 engineering_smoke，不混入正式 TRAIN 统计
  · smoke 的盈利/PF/胜率一律不用于策略判断或参数修改
  · 三组全部使用 V1 的正式冻结参数

三组窗口：
  Winter smoke        : 2023-01-02 ~ 2023-01-31
  DST-transition smoke: 2023-03-20 ~ 2023-04-07
  Summer smoke        : 2023-07-03 ~ 2023-07-31
"""
from __future__ import annotations

import csv
import datetime as dt
import importlib.util as iu
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))     # 执行_下一family_20260913
N0D = os.path.join(HERE, "N0_snapshot")
BASE = os.path.dirname(HERE)                           # deepseek数据保存
TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
CFGDIR = os.path.join(BASE, "mql5", "config")
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
EA_SRC = os.path.join(BASE, "mql5", "dshtools", "dsh_JSB30.mq5")
EA_EX5 = os.path.join(TDATA, "MQL5", "Experts", "dshtrend", "dsh_JSB30.ex5")
OUT = os.path.join(HERE, "smoke_r")

WINDOWS = [
    ("WINTER", "2023.01.02", "2023.01.31", "winter"),
    ("DSTTR",  "2023.03.20", "2023.04.07", "dst_transition"),
    ("SUMMER", "2023.07.03", "2023.07.31", "summer"),
]

P = {
    "InpRunTag": "", "InpMagic": "20260914",
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
    "InpOcpTolUsd": "0.05",
    "InpWriteAudit": "true", "InpWriteRejectAudit": "true", "InpRunTimeSelfcheck": "true",
    "InpLatencyMs": "0", "InpLatencyTicks": "0", "InpVerboseLog": "true",
    "InpUseGrid": "false", "InpUseMartingale": "false", "InpUseTrailingWin": "false",
}


def load(name, path):
    spec = iu.spec_from_file_location(name, path)
    m = iu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def kill_mt5():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(3)


def parse_html(path):
    """★改用仓库里 proven 的 table-based 解析器（执行_第三批/mt5_html_parser.py）。

    历史教训：手写"剥标签+正则"解析 MT5 报告极其脆弱 —— 报告里 "Symbol" 出现在
    Specification / Settings / Results 多个表，"Bars" 也出现在输入表，
    导致取到错误单元格（曾出现 HTML Net Profit 被读成 0.00 而实际为 +10.74）。
    """
    if not os.path.isfile(path):
        return {}
    try:
        # proven 解析器位于 <新量化策略>/deepseek数据保存/执行_第三批/
        for d in (os.path.join(BASE, "执行_第三批"),
                  r"D:\desktop\新量化策略\deepseek数据保存\执行_第三批"):
            if os.path.isfile(os.path.join(d, "mt5_html_parser.py")):
                if d not in sys.path:
                    sys.path.insert(0, d)
                break
        from mt5_html_parser import parse_report
        r = parse_report(path)
        kv = r.get("kv", {}) or {}
        return {k: v for k, v in kv.items() if v not in (None, "")}
    except Exception as e:
        print("  ! HTML 解析失败:", e)
        return {}


def make_ini(tag, frm, to):
    lines = [
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]", "Expert=dshtrend\\dsh_JSB30", "Symbol=USDJPYm", "Period=M1",
        "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to,
        "ForwardMode=0", "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]",
    ]
    pp = dict(P); pp["InpRunTag"] = tag
    lines += ["%s=%s" % (k, v) for k, v in pp.items()]
    path = os.path.join(CFGDIR, "run_%s.ini" % tag)
    io.open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def read_log_tail():
    ld = os.path.join(TDATA, "Tester", "logs")
    if not os.path.isdir(ld):
        return ""
    fs = [os.path.join(ld, f) for f in os.listdir(ld) if f.endswith(".log")]
    if not fs:
        return ""
    p = max(fs, key=os.path.getmtime)
    try:
        return io.open(p, encoding="utf-16-le", errors="ignore").read()
    except Exception:
        return ""


def run_one(label, tag, frm, to, jp, ci):
    print("\n" + "=" * 78)
    print("N1.5R smoke: %s  tag=%s  %s ~ %s" % (label, tag, frm, to))
    print("=" * 78)
    ini = make_ini(tag, frm, to)
    r = ci.check(EA_SRC, ini)
    print("  input schema: %s %s" % ("OK" if r["ok"] else "FAIL", r["unknown"] or ""))

    # ★每次 run 前清空审计目录，避免跨 run 累积（实测会导致 34 行 = 17×2）
    adir_pre = os.path.join(COMMON, tag)
    if os.path.isdir(adir_pre):
        shutil.rmtree(adir_pre, ignore_errors=True)
    rp_pre = os.path.join(TDATA, "report_%s.htm" % tag)
    if os.path.isfile(rp_pre):
        os.remove(rp_pre)

    kill_mt5()
    logp = os.path.join(TDATA, "Tester", "logs")
    fs = [os.path.join(logp, f) for f in os.listdir(logp) if f.endswith(".log")] if os.path.isdir(logp) else []
    off = os.path.getsize(max(fs, key=os.path.getmtime)) if fs else 0

    proc = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
    try:
        proc.wait(timeout=1800)
    except subprocess.TimeoutExpired:
        print("  ! 超时"); kill_mt5()
    time.sleep(2)

    # 新日志段
    new = ""
    if fs:
        p = max(fs, key=os.path.getmtime)
        try:
            with open(p, "rb") as f:
                f.seek(off); new = f.read().decode("utf-16-le", errors="ignore")
        except Exception:
            pass

    rep = os.path.join(TDATA, "report_%s.htm" % tag)
    adir = os.path.join(COMMON, tag)
    tp = os.path.join(adir, "trades.csv")
    rj = os.path.join(adir, "reject_audit.csv")
    sc = os.path.join(adir, "audit_selfcheck.csv")
    h = parse_html(rep)

    d = os.path.join(OUT, tag)
    os.makedirs(d, exist_ok=True)
    for f in (rep, tp, rj, sc, ini):
        if os.path.isfile(f):
            shutil.copy2(f, d)

    res = []
    def C(n, ok, det=""):
        res.append((n, bool(ok), det))

    rows0 = []
    tp0 = os.path.join(adir, "trades.csv")
    if os.path.isfile(tp0):
        with io.open(tp0, encoding="utf-8-sig", errors="ignore", newline="") as f0:
            rows0 = list(csv.DictReader(f0))

    ticks = h.get("Ticks", "")
    C("Bars > 0", h.get("Bars", "") not in ("", "0"), "Bars=%s Ticks=%s" % (h.get("Bars"), ticks))
    C("Deposit = 500", h.get("Initial Deposit", "").startswith("500"), h.get("Initial Deposit", ""))
    C("Symbol = USDJPYm", h.get("Symbol", "") == "USDJPYm", h.get("Symbol", ""))
    C("HTML Total Trades == 审计行数",
      h.get("Total Trades", "") != "" and str(len(rows0)) == str(h.get("Total Trades", "")).strip(),
      "HTML=%s 审计=%d" % (h.get("Total Trades"), len(rows0)))

    # 真实周 offset（REALWEEK 行）
    rw = [l for l in new.splitlines() if "REALWEEK 汇总" in l]
    rw_ok = None
    if rw:
        m = re.search(r"checked=(\d+) OK=(\d+) FAIL=(\d+)", rw[-1])
        if m:
            rw_ok = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    C("REALWEEK 有样本", bool(rw_ok and rw_ok[0] > 0), str(rw_ok))
    C("REALWEEK 全通过", bool(rw_ok and rw_ok[2] == 0 and rw_ok[0] > 0), str(rw_ok))
    ut = [l for l in new.splitlines() if "UNIT 汇总" in l]
    C("UNIT 三组日期全通过", any("6/6" in l for l in ut), ut[-1].split("]")[-1].strip() if ut else "无")
    of = re.findall(r"offsetFail=(\d+)", new)
    C("offsetFail=0", (of[-1] == "0") if of else None, "offsetFail=%s" % (of[-1] if of else "?"))

    # offset 只出现 +2/+3
    offs = set(re.findall(r"REALWEEK .*? off=\+(\d)", new))
    C("真实周 offset ∈ {2,3}", offs.issubset({"2", "3"}) and len(offs) > 0, "观察到 %s" % sorted(offs))

    # schema
    try:
        hdr = jp.check_header(tp, jp.EXPECTED_TRADES_COLS)
        C("trades header 唯一+列匹配", True, "%d 列" % len(hdr))
    except Exception as e:
        C("trades header 唯一+列匹配", False, str(e)[:60])
    if os.path.isfile(rj):
        try:
            jp.check_header(rj, jp.EXPECTED_REJECT_COLS)
            C("reject header 唯一+列匹配", True, "ok")
        except Exception as e:
            C("reject header 唯一+列匹配", False, str(e)[:60])

    rows = []
    if os.path.isfile(tp):
        with io.open(tp, encoding="utf-8-sig", errors="ignore", newline="") as f:
            rows = list(csv.DictReader(f))
    C("trades 行数 > 0", len(rows) > 0, "%d 笔" % len(rows))

    if rows:
        byday = {}
        for r0 in rows:
            byday[(r0.get("entry_time_utc") or "")[:10]] = byday.get((r0.get("entry_time_utc") or "")[:10], 0) + 1
        bad = {k: v for k, v in byday.items() if v > 1}
        C("每 UTC 日 <= 1 笔", not bad, "违反 %s" % (bad or "无"))

        late = [r0 for r0 in rows
                if (r0.get("exit_time_utc") or " ")[11:13].isdigit()
                and int((r0.get("exit_time_utc") or "  ")[11:13]) >= 20]
        C("无 UTC20 后持仓", not late, "越界 %d" % len(late))

        cb = []
        for r0 in rows:
            try:
                if abs((float(r0["profit"] or 0) + float(r0["swap"] or 0)
                        + float(r0["commission"] or 0)) - float(r0["net"] or 0)) > 0.005:
                    cb.append(r0.get("deal_ticket"))
            except Exception:
                cb.append(r0.get("deal_ticket"))
        C("profit+swap+comm = net", not cb, "不一致 %s" % (cb[:3] or "无"))

        tks = [r0.get("deal_ticket") for r0 in rows]
        C("ticket 无重复", len(tks) == len(set(tks)), "%d/%d" % (len(set(tks)), len(tks)))

        # ★OCP vs 独立公式
        ocpbad = []
        for r0 in rows:
            try:
                o = float(r0.get("ocp_value") or 0); fv = float(r0.get("formula_value") or 0)
                lim = max(0.05, 0.025 * abs(o))
                if abs(o - fv) > lim:
                    ocpbad.append((r0.get("deal_ticket"), round(o, 3), round(fv, 3), round(lim, 3)))
            except Exception:
                ocpbad.append(r0.get("deal_ticket"))
        C("OCP 与独立公式可对账", not ocpbad, "超容差 %s" % (ocpbad[:3] or "无"))

        anet = sum(float(r0["net"] or 0) for r0 in rows)
        try:
            rnet = float((h.get("Total Net Profit") or "0").replace(" ", "").replace(",", ""))
            tol = max(0.02, 0.001 * max(1.0, abs(rnet)))
            C("HTML 与 audit 净利可对账", abs(anet - rnet) <= tol,
              "audit %.2f / html %.2f / 差 %.2f" % (anet, rnet, anet - rnet))
        except Exception:
            C("HTML 与 audit 净利可对账", False, "报告净利无法解析")

        C("字段齐备(entry_time_utc 等)", all(
            r0.get("position_id") and r0.get("entry_time_utc")
            and r0["entry_time_utc"] != "undetermined" for r0 in rows), "ok")

    if os.path.isfile(sc):
        with io.open(sc, encoding="utf-8-sig", errors="ignore", newline="") as f:
            s = list(csv.DictReader(f))
        if s:
            C("结束无活动仓位", s[0].get("active_positions") == "0", "active=%s" % s[0].get("active_positions"))
            C("audit_failed=0", s[0].get("audit_failed") == "0", "val=%s" % s[0].get("audit_failed"))
            C("offset_undetermined=0", s[0].get("offset_undetermined") == "0", "val=%s" % s[0].get("offset_undetermined"))
            C("ocp_mismatch=0", s[0].get("ocp_mismatch", "0") == "0", "val=%s" % s[0].get("ocp_mismatch"))

    okn = sum(1 for _, o, _ in res if o)
    print("\n  --- 结果 %d/%d ---" % (okn, len(res)))
    for n, o, dd in res:
        print("  %s %-32s %s" % ("[PASS]" if o else "[FAIL]", n, dd[:44]))

    return dict(label=label, tag=tag, frm=frm, to=to, checks=res, report=h,
                trades=len(rows), ini=ini, dirn=d, selftest=ut[-1] if ut else "",
                realweek=rw[-1] if rw else "", offs=sorted(offs))


def main():
    os.makedirs(OUT, exist_ok=True)
    jp = load("jp", os.path.join(N0D, "jsb30_parser.py"))
    ci = load("ci", os.path.join(N0D, "check_inputs.py"))

    print("JSB30 N1.5R · 真实历史工程 smoke")
    print("  EA source:", EA_SRC)
    print("  windows  :", [(w[0], w[1], w[2]) for w in WINDOWS])

    results = []
    for label, frm, to, _role in WINDOWS:
        tag = "DS260914_JSB30_SMOKE_%s" % label
        results.append(run_one(label, tag, frm, to, jp, ci))

    # ---- 汇总 ----
    allc = [(r["label"], n, o, d) for r in results for (n, o, d) in r["checks"]]
    okn = sum(1 for _, _, o, _ in allc if o)
    tot = len(allc)
    tot_tr = sum(r["trades"] for r in results)

    L = ["# JSB30 · N1.5R 真实历史工程 smoke 报告\n",
         "- 时间：%s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "- 依据：GPT 裁定 `N1.5R`（不再用 2014 的 0-data 窗口）",
         "- EA 源码：`%s`" % EA_SRC,
         "- dataset_role：**engineering_smoke**（★不混入正式 TRAIN 统计）",
         "- 参数：三组全部使用 **V1 正式冻结参数**",
         "- **★smoke 的盈利/PF/胜率不用于任何策略判断或参数修改（GPT §N1.5R）**\n",
         "## 1. 三组窗口与结果\n",
         "| 组 | tag | 窗口 | Bars | Ticks | Trades | 净利(仅记录) | DD | 判定 |",
         "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for r in results:
        h = r["report"]
        ok = sum(1 for _, o, _ in r["checks"] if o); tt = len(r["checks"])
        L.append("| %s | `%s` | %s ~ %s | %s | %s | %d | %s | %s | %d/%d %s |"
                 % (r["label"], r["tag"], r["frm"], r["to"],
                    h.get("Bars", "-"), h.get("Ticks", "-"), r["trades"],
                    h.get("Total Net Profit", "-"), h.get("Equity Drawdown Relative", "-"),
                    ok, tt, "PASS" if ok == tt else "**FAIL**"))
    L += ["", "## 2. 逐项检查\n"]
    for r in results:
        L.append("### %s（`%s`）\n" % (r["label"], r["tag"]))
        L.append("| 检查项 | 结果 | 明细 |"); L.append("|---|---|---|")
        for n, o, d in r["checks"]:
            L.append("| %s | %s | %s |" % (n, "PASS" if o else "**FAIL**", d))
        L.append("")
        L.append("```")
        L.append("UNIT   : " + (r["selftest"] or "-").strip())
        L.append("REALWEEK: " + (r["realweek"] or "-").strip())
        L.append("观察到的 offset: " + ",".join("+" + x for x in r["offs"]) )
        L.append("```")
        L.append("")
    L += ["## 3. 汇总\n", "```",
          "总计: %d/%d 检查通过" % (okn, tot),
          "三组实际 closing deal 合计: %d 笔" % tot_tr,
          "★若合计为 0，则按 GPT 要求【不能宣布审计交易链 PASS】，",
          "  只能继续用预先定义的工程 probe/unit test 验证写入链。",
          "```", ""]
    io.open(os.path.join(OUT, "JSB30_N1_5R_smoke_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n" + "=" * 78)
    print("N1.5R 汇总: %d/%d 通过；实际 closing deal 合计 %d 笔" % (okn, tot, tot_tr))
    print("报告 ->", os.path.join(OUT, "JSB30_N1_5R_smoke_report.md"))
    return 0 if okn == tot else 1


if __name__ == "__main__":
    sys.exit(main())



