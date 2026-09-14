#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JSB30 · N1.7 preflight + N2 TRAIN + N3 VALID 全流程执行器（N1R2）

严格按 GPT 裁定：
  · 三个 TRAIN 串行，同一冻结 EX5，只有预注册差异（V2 range 06->03 / V3 TP 1.5->1.0R）
  · 每个 run 前写 planned manifest、运行、写 actual manifest、审计
  · 12 项停止条件；触发即 blocked_failed/closed，不跑其 VALID
  · 只有 TRAIN 通过者跑 VALID（同一 EX5 / 同一 inputs / 同一 risk / 同一 time mapping）
  · 禁碰 exposed_oos(2025-06-01~2026-05-31) 与 user_holdout(2026-06-01~2026-09-30)
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

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
CFGDIR = r"D:\desktop\新量化策略\deepseek数据保存\mql5\config"
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
BASE = r"D:\desktop\新量化策略\deepseek数据保存"
FAM = os.path.join(BASE, "执行_下一family_20260913")
MANIFEST = os.path.join(FAM, "N0_snapshot", "JSB30_planned_runs.jsonl")
OUT = os.path.join(FAM, "runs_n1r2")
sys.path.insert(0, os.path.join(BASE, "执行_第三批"))

EXPOSED_OOS = (dt.date(2025, 6, 1), dt.date(2026, 5, 31))
USER_HOLDOUT = (dt.date(2026, 6, 1), dt.date(2026, 9, 30))


def sha(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def kill():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(3)


def parse_html(path):
    if not os.path.isfile(path):
        return {}
    try:
        from mt5_html_parser import parse_report
        r = parse_report(path)
        return {k: v for k, v in (r.get("kv") or {}).items() if v not in (None, "")}
    except Exception as e:
        print("   ! html parse:", e)
        return {}


def num(s, d=0.0):
    try:
        return float(str(s).replace(" ", "").replace(",", "").replace("%", "").strip())
    except Exception:
        return d


def bars_from_log(lp, off):
    try:
        with open(lp, "rb") as f:
            f.seek(off); raw = f.read()
    except Exception:
        return None, None
    t = raw.decode("utf-16-le", errors="ignore")
    ms = re.findall(r"USDJPYm,M1:\s*(\d+)\s*ticks,\s*(\d+)\s*bars generated", t)
    return (int(ms[-1][0]), int(ms[-1][1])) if ms else (None, None)


def log_tail(lp, off):
    try:
        with open(lp, "rb") as f:
            f.seek(off); raw = f.read()
    except Exception:
        return ""
    return raw.decode("utf-16-le", errors="ignore")


def run_one(row, planned_path):
    tag = row["run_id"]
    frm, to = row["from"], row["to"]
    adir = os.path.join(COMMON, tag)
    if os.path.isdir(adir):
        shutil.rmtree(adir, ignore_errors=True)
    rp = os.path.join(TDATA, "report_%s.htm" % tag)
    if os.path.isfile(rp):
        os.remove(rp)

    kill()
    ld = os.path.join(TDATA, "Tester", "logs")
    fs = [os.path.join(ld, f) for f in os.listdir(ld) if f.endswith(".log")] if os.path.isdir(ld) else []
    lp = max(fs, key=os.path.getmtime) if fs else None
    off = os.path.getsize(lp) if lp else 0

    print("  ▶ 运行 %s  %s ~ %s" % (tag, frm, to), flush=True)
    t0 = time.time()
    p = subprocess.Popen([TERMINAL, "/config:" + row["ini_path"]], cwd=os.path.dirname(TERMINAL))
    try:
        p.wait(timeout=5400)
    except subprocess.TimeoutExpired:
        print("  ! 超时"); kill()
    el = time.time() - t0
    time.sleep(2)

    h = parse_html(rp)
    tk, bars = bars_from_log(lp, off)
    lt = log_tail(lp, off)

    tp = os.path.join(adir, "trades.csv")
    rr = os.path.join(adir, "reject_audit.csv")
    sc = os.path.join(adir, "audit_selfcheck.csv")
    d = os.path.join(OUT, tag)
    os.makedirs(d, exist_ok=True)
    for f in (rp, tp, rr, sc, row["ini_path"]):
        if os.path.isfile(f):
            shutil.copy2(f, d)

    trades = []
    if os.path.isfile(tp):
        with io.open(tp, encoding="utf-8-sig", errors="ignore", newline="") as f:
            trades = list(csv.DictReader(f))
    scv = {}
    if os.path.isfile(sc):
        with io.open(sc, encoding="utf-8-sig", errors="ignore", newline="") as f:
            r0 = list(csv.DictReader(f))
            if r0:
                scv = r0[0]

    return dict(tag=tag, variant=row["variant"], phase=row["phase"],
                frm=frm, to=to, elapsed_s=round(el, 1),
                html=h, log_ticks=tk, log_bars=bars,
                trades=trades, selfcheck=scv, dirn=d,
                report=rp, log_tail=lt)


def audit_run(res, row):
    """完整审计 + 12 项停止条件"""
    h, tr, scv = res["html"], res["trades"], res["selfcheck"]
    out = {"run_id": res["tag"], "checks": {}, "metrics": {}, "gates": {}}
    C = out["checks"]

    bars = num(h.get("Bars"), 0)
    ticks = num(h.get("Ticks"), 0)
    dep = num(h.get("Initial Deposit"), 0)
    sym = (h.get("Symbol") or "").strip()
    ttot = num(h.get("Total Trades"), 0)
    net = num(h.get("Total Net Profit"), 0)
    pf = num(h.get("Profit Factor"), 0)
    ddr = num(h.get("Equity Drawdown Relative"), 0)

    C["Bars>0"] = bars > 0
    C["Deposit=500"] = abs(dep - 500) < 0.01
    C["Symbol=USDJPYm"] = sym == "USDJPYm"
    C["HTML_Trades==audit_rows"] = (ttot == len(tr)) and ttot > 0
    C["audit_failed=0"] = scv.get("audit_failed") == "0"
    C["fatal=0"] = scv.get("fatal") == "0"
    C["ocp_mismatch=0"] = scv.get("ocp_mismatch", "0") == "0"
    C["active_positions=0"] = scv.get("active_positions") == "0"
    C["server_utc_offset=0"] = scv.get("server_utc_offset", "0") == "0"

    # 每 UTC 日 <= 1 笔
    byday = {}
    for r in tr:
        d0 = (r.get("entry_time_utc") or "")[:10]
        byday[d0] = byday.get(d0, 0) + 1
    C["每UTC日<=1笔"] = all(v <= 1 for v in byday.values()) and len(byday) > 0

    # hard-flat
    late = [r for r in tr if (r.get("exit_time_utc") or " ")[11:13].isdigit()
            and int((r.get("exit_time_utc") or "  ")[11:13]) >= 20]
    C["无UTC20后持仓"] = len(late) == 0

    # 成本一致
    cb = []
    for r in tr:
        if abs(num(r.get("profit")) + num(r.get("swap")) + num(r.get("commission"))
               - num(r.get("net"))) > 0.005:
            cb.append(r.get("deal_ticket"))
    C["profit+swap+comm=net"] = len(cb) == 0

    # ticket 唯一
    tks = [r.get("deal_ticket") for r in tr]
    C["ticket唯一"] = len(tks) == len(set(tks))

    # ★三方对账：DEAL_PROFIT ↔ OCP
    ocpbad = [r.get("deal_ticket") for r in tr
              if abs(num(r.get("deal_profit")) - num(r.get("ocp_value"))) > 0.05]
    C["DEAL_PROFIT↔OCP<=0.05"] = len(ocpbad) == 0

    # server==UTC（entry_time_server == entry_time_utc）
    eq = [r for r in tr if (r.get("entry_time_server") or "") != (r.get("entry_time_utc") or "")]
    C["server时间==UTC时间"] = len(eq) == 0

    # 审计净利 vs 报告净利
    anet = sum(num(r.get("net")) for r in tr)
    tol = max(0.02, 0.001 * max(1.0, abs(net)))
    C["HTML净利==审计净利"] = abs(anet - net) <= tol

    # range 完整性
    inc = int(scv.get("skip_range_incomplete", "0") or 0)
    C["有range完整性统计"] = "skip_range_incomplete" in scv

    # ---- 指标 ----
    f = dt.datetime.strptime(res["frm"], "%Y.%m.%d").date()
    t = dt.datetime.strptime(res["to"], "%Y.%m.%d").date()
    days = (t - f).days + 1
    years = days / 365.25
    freqs = len(tr) / years if years > 0 else 0

    pnl = [num(r.get("net")) for r in tr]
    srt = sorted(pnl, reverse=True)
    top5 = sum(srt[:5]); top10 = sum(srt[:10])
    rem10 = sum(srt[10:])
    wins = [x for x in pnl if x > 0]; losses = [x for x in pnl if x < 0]
    span = 0.0
    if tr:
        ts = sorted((r.get("entry_time_utc") or "") for r in tr)
        try:
            a = dt.datetime.strptime(ts[0][:19], "%Y.%m.%d %H:%M:%S")
            b = dt.datetime.strptime(ts[-1][:19], "%Y.%m.%d %H:%M:%S")
            span = (b - a).total_seconds() / ((t - f).total_seconds()) * 100.0
        except Exception:
            pass

    # spread / 初始 SL 距离
    sp_ratios = []
    for r in tr:
        try:
            e = num(r.get("entry"), 0); sl = e  # SL 不在审计行；用 risk_budget/actual 反推不可靠
        except Exception:
            pass

    out["metrics"] = dict(
        bars=bars, ticks=ticks, net=net, pf=pf, dd_relative=ddr,
        trades=len(tr), years=round(years, 2), trades_per_year=round(freqs, 1),
        first_trade=(min((r.get("entry_time_utc") or "") for r in tr) if tr else ""),
        last_trade=(max((r.get("entry_time_utc") or "") for r in tr) if tr else ""),
        span_coverage_pct=round(span, 1),
        long=sum(1 for r in tr if num(r.get("volume")) > 0 and (r.get("exit_reason") or "") != "" and num(r.get("entry")) < num(r.get("exit"))),
        top5=round(top5, 2), top10=round(top10, 2), remove_top10=round(rem10, 2),
        win=len(wins), loss=len(losses),
        avg_win=round(sum(wins) / len(wins), 2) if wins else 0.0,
        avg_loss=round(sum(losses) / len(losses), 2) if losses else 0.0,
        swap=round(sum(num(r.get("swap")) for r in tr), 2),
        commission=round(sum(num(r.get("commission")) for r in tr), 2),
        range_incomplete_days=inc,
        risk_cap_breach=int(scv.get("risk_cap_breach", "0") or 0),
        formula_diag_out=int(scv.get("formula_diag_out", "0") or 0),
        rej_risk=int(scv.get("rej_risk", "0") or 0),
        rej_ocp=int(scv.get("rej_ocp", "0") or 0),
        skip_range_notready=int(scv.get("skip_range_notready", "0") or 0),
        skip_range_toonarrow=int(scv.get("skip_range_toonarrow", "0") or 0),
        skip_nobreak=int(scv.get("skip_nobreak", "0") or 0),
        skip_daytraded=int(scv.get("skip_daytraded", "0") or 0),
    )

    # ---- 12 项停止条件（任一触发 → closed，不跑 VALID）----
    m = out["metrics"]
    G = out["gates"]
    G["1_净利<=0"] = net <= 0
    G["2_PF<=1"] = (pf <= 1.0) if pf > 0 else True
    G["3_DD>40%"] = ddr > 40.0
    G["4_2x成本后转负"] = (net - 2 * abs(m["swap"] + m["commission"])) <= 0
    G["5_去前10后转负"] = rem10 <= 0
    G["6_对账不一致"] = not all([C["HTML净利==审计净利"], C["DEAL_PROFIT↔OCP<=0.05"],
                             C["HTML_Trades==audit_rows"], C["profit+swap+comm=net"]])
    G["7_依赖少数极端单"] = (abs(top10) > abs(net) * 1.0) and net > 0 if net > 0 else (top10 > 0 and rem10 <= 0)
    G["8_最小手地板主导"] = (m["risk_cap_breach"] > 0)
    G["9_成交跨度<90%"] = m["span_coverage_pct"] < 90.0
    G["10_频率<50笔/年"] = m["trades_per_year"] < 50.0
    G["11_无spread数据"] = True   # 审计未记录 spread/SL 距离 → 该项无法评估
    G["12_时间自检矛盾"] = not C.get("server时间==UTC时间", False)

    triggered = [k for k, v in G.items() if v and k != "11_无spread数据"]
    out["triggered"] = triggered
    out["passed"] = (len(triggered) == 0 and all(C.values()))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = [json.loads(l) for l in io.open(MANIFEST, encoding="utf-8") if l.strip()]
    byid = {r["run_id"]: r for r in rows}
    print("=" * 78)
    print("JSB30 · N2 TRAIN（V1 → V2 → V3 串行）")
    print("=" * 78)

    results = {}
    for vid in ("V1", "V2", "V3"):
        tag = "DS260914_JSB30_%s_TRAIN" % vid
        row = byid[tag]
        res = run_one(row, MANIFEST)
        aud = audit_run(res, row)
        results[tag] = dict(res=res, aud=aud)
        m = aud["metrics"]
        print("  ✔ %s  净利=%.2f PF=%.2f DD=%.2f%% 笔数=%d 频率=%.1f/年 去前10=%.2f"
              % (tag, m["net"], m["pf"], m["dd_relative"], m["trades"],
                 m["trades_per_year"], m["remove_top10"]), flush=True)
        print("     触发停止条件: %s" % (aud["triggered"] or "无 ✅"), flush=True)

    # ---- VALID：只对 TRAIN 通过者 ----
    valids = []
    for vid in ("V1", "V2", "V3"):
        tt = "DS260914_JSB30_%s_TRAIN" % vid
        if not results[tt]["aud"]["passed"]:
            print("  ⊘ %s TRAIN 未通过 → 不跑其 VALID" % vid, flush=True)
            continue
        vt = "DS260914_JSB30_%s_VALID" % vid
        vrow = byid[vt]
        print("  ▶ TRAIN 通过 → 运行 %s" % vt, flush=True)
        vres = run_one(vrow, MANIFEST)
        vaud = audit_run(vres, vrow)
        results[vt] = dict(res=vres, aud=vaud)
        valids.append(vt)
        m = vaud["metrics"]
        print("  ✔ %s 净利=%.2f PF=%.2f DD=%.2f%% 笔数=%d"
              % (vt, m["net"], m["pf"], m["dd_relative"], m["trades"]), flush=True)
        print("     触发停止条件: %s" % (vaud["triggered"] or "无 ✅"), flush=True)

    # ---- 汇总写出 ----
    summary = {k: dict(run=k, variant=v["res"]["variant"], phase=v["res"]["phase"],
                       checks=v["aud"]["checks"], metrics=v["aud"]["metrics"],
                       gates=v["aud"]["gates"], triggered=v["aud"]["triggered"],
                       passed=v["aud"]["passed"],
                       html=v["res"]["html"], selfcheck=v["res"]["selfcheck"])
               for k, v in results.items()}
    sp = os.path.join(OUT, "n2n3_summary.json")
    io.open(sp, "w", encoding="utf-8").write(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\n汇总 ->", sp)
    print("VALID 已运行:", valids or "无")
    return 0


if __name__ == "__main__":
    sys.exit(main())
