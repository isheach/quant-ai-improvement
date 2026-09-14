#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run the read-only MT5 Probe and the independent XAMR30 double-calc."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FAMILY = REPO_ROOT / "deepseek数据保存" / "执行_XAMR30"
PROBE_SOURCE = REPO_ROOT / "deepseek数据保存" / "mql5" / "dshtools" / "dsh_XAMR30SignalProbe_v1.mq5"
PROBE_EX5 = PROBE_SOURCE.with_suffix(".ex5")
METAEDITOR = Path(r"C:\Program Files\MetaTrader 5 EXNESS\MetaEditor64.exe")
TERMINAL = Path(r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
TDATA = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "53785E099C927DB68A545C249CDBCE06"
DEPLOYED = TDATA / "MQL5" / "Experts" / "dshtrend" / "dsh_XAMR30SignalProbe_v1.ex5"
COMMON = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "dshtrend" / "XAMR30DoubleCalc"
WORK = FAMILY / "doublecalc"
MQL_OUTPUT_DIR = WORK / "mql_probe_outputs"
CONFIG_DIR = REPO_ROOT / "deepseek数据保存" / "mql5" / "config"
SAMPLE_REL = r"dshtrend\XAMR30DoubleCalc\selected_samples.csv"
USD_REL = r"dshtrend\XAMR30DoubleCalc\raw_USDJPYm_M30.csv"
XAU_REL = r"dshtrend\XAMR30DoubleCalc\raw_XAUUSDm_M30.csv"


def kill_terminals() -> None:
    subprocess.run(["taskkill", "/F", "/IM", "terminal64.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "metatester64.exe"], capture_output=True)
    time.sleep(2)


def compile_probe() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    log = WORK / "probe_compile.log"
    if PROBE_EX5.exists():
        PROBE_EX5.unlink()
    if not METAEDITOR.is_file():
        raise RuntimeError(f"MetaEditor not found: {METAEDITOR}")
    result = subprocess.run(
        [str(METAEDITOR), f"/compile:{PROBE_SOURCE}", "/log"],
        cwd=str(METAEDITOR.parent), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    pieces = [f"returncode={result.returncode}", result.stdout, result.stderr]
    for candidate in (PROBE_SOURCE.with_suffix(".log"), PROBE_SOURCE.with_suffix(".ex5.log")):
        if candidate.is_file():
            raw = candidate.read_bytes()
            pieces.append(raw.decode("utf-16-le", errors="ignore") or raw.decode("utf-8", errors="replace"))
            shutil.copy2(candidate, log)
            break
    if not log.is_file():
        log.write_text("\n".join(pieces), encoding="utf-8")
    text = log.read_bytes().decode("utf-16-le", errors="ignore") if log.stat().st_size % 2 == 0 else log.read_text(encoding="utf-8", errors="replace")
    if "0 errors" not in text.lower() or not PROBE_EX5.is_file():
        raise RuntimeError(f"Probe compile did not produce a 0-error EX5; inspect {log}")
    DEPLOYED.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROBE_EX5, DEPLOYED)
    print(f"PROBE_COMPILE=PASS EX5={PROBE_EX5} DEPLOYED={DEPLOYED}", flush=True)


def write_empty_sample() -> None:
    COMMON.mkdir(parents=True, exist_ok=True)
    (COMMON / "selected_samples.csv").write_text(
        "row_id,window,sample_type,timestamp,source_audit_file,source_ticket\n",
        encoding="utf-8",
    )


def make_ini(tag: str, window: str, output_rel: str, export_raw: bool, frm: str, to: str) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "[Common]", "Login=277335900", "Server=Exness-MT5Trial5", "KeepPrivate=1",
        "NewsEnable=0", "CertInstall=0", "[Experts]", "AllowLiveTrading=0",
        "AllowDllImport=0", "Enabled=1", "Account=0", "Profile=0",
        "[Tester]", "Expert=dshtrend\\dsh_XAMR30SignalProbe_v1", "Symbol=USDJPYm",
        "Period=M30", "Model=2", "Optimization=0", f"FromDate={frm}", f"ToDate={to}",
        "ForwardMode=0", "Deposit=500", "Currency=USD", "Leverage=1:200",
        "ExecutionMode=0", "Visual=0", f"Report=report_XAMR30_DBL_{tag}",
        "ReplaceReport=1", "ShutdownTerminal=1", "[TesterInputs]",
        f"InpRunTag=XAMR30_DBL_{tag}", f"InpWindow={window}",
        f"InpSampleFile={SAMPLE_REL}", f"InpOutputFile={output_rel}",
        f"InpExportRaw={'true' if export_raw else 'false'}", f"InpRawUsdFile={USD_REL}",
        f"InpRawXauFile={XAU_REL}", "InpRawFrom=2022.01.01 00:00:00",
        "InpRawTo=2023.08.02 00:00:00",
    ]
    path = CONFIG_DIR / f"run_XAMR30_DBL_{tag}.ini"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_tester(tag: str, window: str, export_raw: bool, frm: str, to: str) -> None:
    out_name = f"probe_{tag}_mql.csv"
    common_out = COMMON / out_name
    if common_out.exists():
        common_out.unlink()
    ini = make_ini(tag, window, rf"dshtrend\XAMR30DoubleCalc\{out_name}", export_raw, frm, to)
    kill_terminals()
    print(f"TESTER_START={tag} WINDOW={window} FROM={frm} TO={to}", flush=True)
    proc = subprocess.Popen([str(TERMINAL), f"/config:{ini}"], cwd=str(TERMINAL.parent))
    timed_out = False
    try:
        proc.wait(timeout=1800)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_terminals()
    time.sleep(3)
    if timed_out:
        raise RuntimeError(f"Tester timed out: {tag}")
    if export_raw:
        for name in ("raw_USDJPYm_M30.csv", "raw_XAUUSDm_M30.csv"):
            path = COMMON / name
            if not path.is_file() or path.stat().st_size < 100:
                raise RuntimeError(f"raw export missing/empty: {path}")
    else:
        if not common_out.is_file():
            raise RuntimeError(f"probe output missing: {common_out}")
        MQL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(common_out, MQL_OUTPUT_DIR / out_name)
    print(f"TESTER_DONE={tag} OUTPUT={common_out}", flush=True)


def run_python(mode: str) -> None:
    script = FAMILY / "doublecalc_xamr30.py"
    result = subprocess.run([sys.executable, str(script), mode], cwd=str(FAMILY), text=True)
    if result.returncode != 0:
        raise RuntimeError(f"doublecalc_xamr30.py {mode} failed: {result.returncode}")


def main() -> int:
    compile_probe()
    WORK.mkdir(parents=True, exist_ok=True)
    MQL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_empty_sample()
    # The bootstrap only exports real M30 OHLC.  It does not select samples or
    # run the strategy EA.  The tester interval supplies indicator warm-up.
    run_tester("BOOTSTRAP", "NONE", True, "2022.01.01", "2023.08.02")
    run_python("prepare")
    for window, to in (("WINTER", "2023.02.01"), ("DSTTR", "2023.04.08"), ("SUMMER", "2023.08.01")):
        run_tester(window, window, False, "2022.01.01", to)
    run_python("finalize")
    print("DOUBLECALC_RUN=COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
