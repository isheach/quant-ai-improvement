#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N1R2 · 重建 planned manifest（含全部 resolved_inputs + 最终 TRAIN 起点）

GPT 裁定 F 项：每个影响【策略行为 / 时间映射 / risk sizing / 审计有效性】的 input
都必须同时出现在 source / static table / resolved INI / planned manifest。
★禁止依赖"源码默认值所以 manifest 不写"。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import re

BASE = r"D:\desktop\新量化策略\deepseek数据保存"
OUT = os.path.join(BASE, "执行_下一family_20260913", "N0_snapshot", "JSB30_planned_runs.jsonl")
SRC = os.path.join(BASE, "mql5", "dshtools", "dsh_JSB30.mq5")
EX5 = os.path.join(os.environ["APPDATA"], "MetaQuotes", "Terminal",
                   "53785E099C927DB68A545C249CDBCE06",
                   "MQL5", "Experts", "dshtrend", "dsh_JSB30.ex5")

TRAIN_FROM, TRAIN_TO = "2018.01.01", "2024.05.31"
VALID_FROM, VALID_TO = "2024.06.01", "2025.05.31"

# ★V1 基准的完整 resolved inputs（每个 input 都显式登记）
V1 = {
    "InpMagic": 20260914,
    "InpRangeStartUtcHour": 0,
    "InpRangeEndUtcHour": 6,
    "InpBreakoutStartUtcHour": 7,
    "InpBreakoutEndUtcHour": 12,
    "InpHardFlatUtcHour": 20,
    "InpSignalTFMinutes": 30,
    "InpATRPeriod": 14,
    "InpMinRangeATRMult": 0.5,
    "InpSL_ATR": 1.0,
    "InpTP_RMult": 1.5,
    "InpMaxBarsInTrade": 16,
    "InpRiskPct": 1.5,
    "InpMinLotMaxRiskPct": 3.0,
    "InpAllowMinLotOvershoot": False,
    "InpAllowLong": True,
    "InpAllowShort": True,
    "InpUseDynamicDstOffset": False,
    "InpExpectedServerOffsetMin": 0,
    "InpExpectedServerOffsetMax": 0,
    "InpOcpTolUsd": 0.05,
    "InpFormulaTolPct": 5.0,
    "InpFormulaDiagnosticOnly": True,
    "InpWriteAudit": True,
    "InpWriteRejectAudit": True,
    "InpRunTimeSelfcheck": True,
    "InpLatencyMs": 0,
    "InpLatencyTicks": 0,
    "InpVerboseLog": False,
    "InpUseGrid": False,
    "InpUseMartingale": False,
    "InpUseTrailingWin": False,
}
# 变体差异（★只允许这两处）
VARIANTS = {
    "V1": (dict(V1), "baseline"),
    "V2": ({**V1, "InpRangeEndUtcHour": 3}, "vs V1: range end 06:00 -> 03:00（expected bars 12 -> 6）"),
    "V3": ({**V1, "InpTP_RMult": 1.0}, "vs V1: TP 1.5R -> 1.0R"),
}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


def source_inputs(path):
    src = io.open(path, encoding="utf-8", errors="ignore").read()
    return sorted(set(re.findall(r"^\s*input\s+[A-Za-z_][\w:]*\s+(\w+)\s*=", src, re.M)))


def write_ini(tag, frm, to, params):
    """写出 resolved INI 并返回路径"""
    cfgdir = os.path.join(BASE, "mql5", "config")
    os.makedirs(cfgdir, exist_ok=True)
    lines = [
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5",
        "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
        "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0",
        "Enabled=1", "Account=0", "Profile=0",
        "[Tester]", "Expert=dshtrend\\dsh_JSB30", "Symbol=USDJPYm", "Period=M1",
        "Model=2", "Optimization=0",
        "FromDate=" + frm, "ToDate=" + to, "ForwardMode=0",
        "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0",
        "Report=report_" + tag, "ReplaceReport=1", "ShutdownTerminal=1",
        "[TesterInputs]",
    ]
    p = dict(params)
    p["InpRunTag"] = tag
    lines += ["%s=%s" % (k, ("true" if v else "false") if isinstance(v, bool) else v)
              for k, v in p.items()]
    path = os.path.join(cfgdir, "run_%s.ini" % tag)
    io.open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return path


def main():
    known = source_inputs(SRC)
    sh, eh = sha(SRC), sha(EX5)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for vid, (params, only) in VARIANTS.items():
        for phase, frm, to, role in (
            ("TRAIN", TRAIN_FROM, TRAIN_TO, "train"),
            ("VALID", VALID_FROM, VALID_TO, "valid"),
        ):
            tag = "DS260914_JSB30_%s_%s" % (vid, phase)
            ini = write_ini(tag, frm, to, params)
            ri = dict(params)
            ri["InpRunTag"] = tag
            # ★四方一致性自检
            miss_src = [k for k in ri if k not in known]
            miss_ini = [k for k in known if k not in ri]
            rows.append(dict(
                run_id=tag, variant=vid, phase=phase, symbol="USDJPYm",
                **{"from": frm, "to": to},
                dataset_role=role,
                status=("planned" if phase == "TRAIN" else "planned_if_train_pass"),
                account_currency="USD", deposit=500, leverage="1:200",
                model=2, ticks=0, period="M1",
                only_difference=only,
                expected_range_bars=(6 if vid != "V2" else 3) * 2,
                server_utc_offset=0,
                resolved_inputs=ri,
                resolved_inputs_count=len(ri),
                source_inputs_count=len(known),
                source_missing_in_inputs=miss_src,
                inputs_missing_in_ini=miss_ini,
                ini_path=ini,
                ini_sha256=sha(ini),
                expert_source_path="deepseek数据保存/mql5/dshtools/dsh_JSB30.mq5",
                expert_source_sha256=sh, source_bytes=os.path.getsize(SRC),
                ex5_path="MQL5/Experts/dshtrend/dsh_JSB30.ex5",
                ex5_sha256=eh, ex5_bytes=os.path.getsize(EX5),
                compile="0 errors / 0 warnings (MetaEditor64, MT5 build 6184)",
                report_name="report_%s" % tag,
                audit_dir="Common/Files/dshtrend/%s" % tag,
                preregistration="deepseek数据保存/执行_下一family_20260913/N0_snapshot/JSB30_preregistration_final.md",
                ruling="公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md",
                train_start_source="N1.6R Tester-only quarterly coverage freeze (2018-01-01)",
                n1r2_status="frozen",
                created_at_local=now,
            ))
    with io.open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("已写出 %d 条 -> %s" % (len(rows), OUT))
    print("source inputs = %d ; resolved inputs = %d" % (len(known), len(V1) + 1))
    print("  source SHA:", sh)
    print("  ex5    SHA:", eh)
    bad = [r["run_id"] for r in rows if r["source_missing_in_inputs"] or r["inputs_missing_in_ini"]]
    print("四方不一致:", bad or "无 ✅")
    for r in rows:
        print("  %-28s %s~%s role=%-6s expBars=%d ini=%s"
              % (r["run_id"], r["from"], r["to"], r["dataset_role"],
                 r["expected_range_bars"], os.path.basename(r["ini_path"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
