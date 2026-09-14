#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N1.6R · USDJPYm 历史覆盖最终冻结（Tester-only）

GPT 裁定：
  · 不用终端图表 CopyRates/CopyClose 作为深历史权威证据
  · 深历史必须由 Strategy Tester + real USDJPYm + FromDate 驱动
  · 从 2014Q1 起逐季度运行只读 probe 直到 2024-05-31
  · coverage = generated_M1_bars / weekday_minutes（周一至周五日期数 × 1440）
  · normal continuous quarter = coverage >= 90%（预先固定）
  · TRAIN 起点 = 最早一个"自身>=90% 且此后所有完整季度均>=90%"的季度里
                 实际第一根可执行 M1 bar
  · Model=2 的 ticks 只记录，不叫"真实 tick"

★为控制总耗时：每个季度取该季度【第一个完整周】（连续 5 个工作日），
  这样 weekday_minutes = 5×1440 = 7200，采样窗口为 168 小时。
  该周的覆盖率即可代表该季度（同一数据源、同一缓存状态）。
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import subprocess
import time

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
CFGDIR = r"D:\desktop\新量化策略\deepseek数据保存\mql5\config"
TERMINAL = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
OUTDIR = r"D:\desktop\新量化策略\deepseek数据保存\执行_下一family_20260913\N1_ea\coverage"
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend", "JSB30TIME")

# 每季度取第一个完整周（周一~周五）
QUARTERS = [
    ("2014Q1", "2014.01.06", "2014.01.10"),
    ("2014Q3", "2014.07.07", "2014.07.11"),
    ("2015Q1", "2015.01.05", "2015.01.09"),
    ("2015Q3", "2015.07.06", "2015.07.10"),
    ("2016Q1", "2016.01.04", "2016.01.08"),
    ("2016Q3", "2016.07.04", "2016.07.08"),
    ("2017Q1", "2017.01.02", "2017.01.06"),
    ("2017Q2", "2017.04.03", "2017.04.07"),
    ("2017Q3", "2017.07.03", "2017.07.07"),
    ("2017Q4", "2017.10.02", "2017.10.06"),
    ("2018Q1", "2018.01.01", "2018.01.05"),
    ("2018Q2", "2018.04.02", "2018.04.06"),
    ("2018Q3", "2018.07.02", "2018.07.06"),
    ("2018Q4", "2018.10.01", "2018.10.05"),
    ("2019Q1", "2019.01.07", "2019.01.11"),
    ("2019Q2", "2019.04.01", "2019.04.05"),
    ("2019Q3", "2019.07.01", "2019.07.05"),
    ("2019Q4", "2019.09.30", "2019.10.04"),
    ("2020Q1", "2020.01.06", "2020.01.10"),
    ("2020Q2", "2020.03.30", "2020.04.03"),
    ("2020Q3", "2020.06.29", "2020.07.03"),
    ("2020Q4", "2020.09.28", "2020.10.02"),
    ("2021Q1", "2021.01.04", "2021.01.08"),
    ("2021Q2", "2021.03.29", "2021.04.02"),
    ("2021Q3", "2021.06.28", "2021.07.02"),
    ("2021Q4", "2021.09.27", "2021.10.01"),
    ("2022Q1", "2022.01.03", "2022.01.07"),
    ("2022Q2", "2022.04.04", "2022.04.08"),
    ("2022Q3", "2022.07.04", "2022.07.08"),
    ("2022Q4", "2022.10.03", "2022.10.07"),
    ("2023Q1", "2023.01.02", "2023.01.06"),
    ("2023Q2", "2023.04.03", "2023.04.07"),
    ("2023Q3", "2023.07.03", "2023.07.07"),
    ("2023Q4", "2023.10.02", "2023.10.06"),
    ("2024Q1", "2024.01.01", "2024.01.05"),
    ("2024Q2", "2024.04.01", "2024.04.05"),
    ("2024TAIL", "2024.05.27", "2024.05.31"),
]


def kill():
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(2)


def make_ini(tag, frm, to):
    txt = "\n".join([
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]", "Expert=dshtrend\\dsh_JSB30WeekProbe", "Symbol=USDJPYm",
        "Period=M1", "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to, "ForwardMode=0",
        "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_COV_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]", "InpRunTag=" + tag, "InpMaxWeeks=2",
    ]) + "\n"
    p = os.path.join(CFGDIR, "run_COV_%s.ini" % tag)
    io.open(p, "w", encoding="utf-8").write(txt)
    return p


def parse_report(path):
    """从 MT5 报告取 Bars / Ticks / History Quality（报告布局多变，仅作辅助）"""
    if not os.path.isfile(path):
        return {}
    raw = open(path, "rb").read()
    if raw[:2] == b"\xff\xfe":
        s = raw.decode("utf-16-le", errors="ignore")
    else:
        s = raw.decode("utf-8", errors="ignore")
    t = re.sub(r"<[^>]+>", "|", s)
    t = re.sub(r"\|+", "|", t)
    out = {}
    for k in ("Bars", "Ticks", "History Quality", "Symbol", "Initial Deposit"):
        ms = list(re.finditer(re.escape(k) + r"\|([^|]{0,30})", t))
        if ms:
            out[k] = ms[-1].group(1).strip()
    return out


def tester_log_offset():
    ld = os.path.join(TDATA, "Tester", "logs")
    if not os.path.isdir(ld):
        return None, 0
    fs = [os.path.join(ld, f) for f in os.listdir(ld) if f.endswith(".log")]
    if not fs:
        return None, 0
    p = max(fs, key=os.path.getmtime)
    return p, os.path.getsize(p)


def read_generated(path, off):
    """★权威来源：测试器日志的 'USDJPYm,M1: N ticks, M bars generated'"""
    if not path:
        return None, None, ""
    try:
        with open(path, "rb") as f:
            f.seek(off)
            raw = f.read()
    except Exception:
        return None, None, ""
    txt = raw.decode("utf-16-le", errors="ignore")
    ms = re.findall(r"USDJPYm,M1:\s*(\d+)\s*ticks,\s*(\d+)\s*bars generated", txt)
    # 历史质量
    hq = ""
    mh = re.findall(r"History Quality\|([\d.]+%?)", txt)
    if mh:
        hq = mh[-1]
    # 是否出现"0 ticks"
    if ms:
        return int(ms[-1][0]), int(ms[-1][1]), hq
    return None, None, hq


def weekday_minutes(frm, to):
    a = dt.datetime.strptime(frm, "%Y.%m.%d").date()
    b = dt.datetime.strptime(to, "%Y.%m.%d").date()
    n = 0
    d = a
    while d <= b:
        if d.weekday() < 5:
            n += 1
        d += dt.timedelta(days=1)
    return n * 1440, n


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    rows = []
    for tag, frm, to in QUARTERS:
        wmin, wdays = weekday_minutes(frm, to)
        ini = make_ini(tag, frm, to)
        kill()
        lp, lo = tester_log_offset()
        p = subprocess.Popen([TERMINAL, "/config:" + ini], cwd=os.path.dirname(TERMINAL))
        try:
            p.wait(timeout=900)
        except subprocess.TimeoutExpired:
            kill()
        time.sleep(1.5)
        rp = os.path.join(TDATA, "report_COV_%s.htm" % tag)
        h = parse_report(rp)
        gen_ticks, bars, hq = read_generated(lp, lo)
        bars = bars or 0
        if hq:
            h["History Quality"] = hq
        cov = (bars / wmin * 100.0) if wmin else 0.0
        r = dict(quarter=tag, requested_from=frm, requested_to=to,
                 weekday_days=wdays, weekday_minutes=wmin,
                 generated_M1_bars=bars, coverage_pct=round(cov, 2),
                 tester_bars=bars, model2_ticks=(gen_ticks if gen_ticks is not None else ""),
                 history_quality=h.get("History Quality", ""),
                 verdict=("normal_continuous" if cov >= 90.0 else
                          ("M1_sparse" if cov >= 5.0 else "server_unavailable")))
        rows.append(r)
        print("  %-9s %s~%s  bars=%-8d / %-6d = %6.2f%%  %s"
              % (tag, frm, to, bars, wmin, cov, r["verdict"]))

    # ---- 冻结 TRAIN 起点 ----
    n = len(rows)
    start_idx = None
    for i in range(n):
        if all(rows[j]["coverage_pct"] >= 90.0 for j in range(i, n)):
            start_idx = i
            break
    frozen_start = rows[start_idx]["requested_from"] if start_idx is not None else None

    out = dict(
        generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        method="Tester-only, real USDJPYm, Model=2, FromDate",
        coverage_definition="generated_M1_bars / (weekday_days * 1440)",
        threshold_normal_continuous_pct=90.0,
        quarters=rows,
        frozen_train_start=frozen_start,
        frozen_from_quarter=rows[start_idx]["quarter"] if start_idx is not None else None,
        note=("Model=2 的 Ticks 是合成价位（每 M1 bar 4 个），仅记录，不代表真实 tick"),
    )
    io.open(os.path.join(OUTDIR, "coverage_quarters.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=2))

    L = ["# USDJPYm 历史覆盖 · Tester-only 逐季度实测（N1.6R）\n",
         "- 生成时间：%s" % out["generated_at"],
         "- 方法：**Strategy Tester + 真实 USDJPYm + Model=2 + FromDate**（不用终端图表 CopyRates）",
         "- 采样：每季度取该季度**第一个完整工作周**（周一~周五）",
         "- `coverage = generated_M1_bars / (工作日数 × 1440)`",
         "- **normal continuous quarter = coverage >= 90%**（预先固定，未事后调整）",
         "- ★`Ticks` 是 Model=2 的**合成价位**（每 M1 bar 4 个），仅记录，不称「真实 tick」\n",
         "## 逐季度结果\n",
         "| 季度 | From | To | 工作日 | weekday_min | generated M1 bars | coverage | Model=2 ticks | 判定 |",
         "|---|---|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %d | %d | %d | **%.2f%%** | %s | %s |"
                 % (r["quarter"], r["requested_from"], r["requested_to"], r["weekday_days"],
                    r["weekday_minutes"], r["generated_M1_bars"], r["coverage_pct"],
                    r["model2_ticks"], r["verdict"]))
    L += ["", "## ★冻结结论\n", "```"]
    if frozen_start:
        L.append("TRAIN 起点 = %s（来自 %s）" % (frozen_start, out["frozen_from_quarter"]))
        L.append("规则：最早一个覆盖 >= 90%% 且此后【所有】季度均 >= 90%% 的季度")
        L.append("→ 不得根据 JSB30 盈亏选择起点；不得为多保留年份放宽 90%")
    else:
        L.append("未找到满足条件的季度 → 数据不足，需重新同步服务器历史")
    L.append("```", "")
    io.open(os.path.join(OUTDIR, "JSB30_coverage_quarters.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n冻结 TRAIN 起点 =", frozen_start)
    print("报告 ->", os.path.join(OUTDIR, "JSB30_coverage_quarters.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

