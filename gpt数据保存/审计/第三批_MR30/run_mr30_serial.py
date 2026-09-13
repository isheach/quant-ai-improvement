#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the six already-planned MR30 MT5 tests, one at a time.

The runner does not alter the legacy strategy directory, does not optimize, and
refuses tags/dates outside the frozen manifest.  It uses the isolated w01
portable worker and copies outputs into the GPT audit directory.  A tag is
never overwritten: an existing output directory is a hard stop.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "deepseek数据保存" / "mt5workers" / "w01"
TERMINAL = WORKER / "terminal64.exe"
EX5_SRC = ROOT / "deepseek数据保存" / "执行_第三批" / "stage3_family_preregistration" / "dsh_MR30.ex5"
EXPERT_DIR = WORKER / "MQL5" / "Experts" / "dshtrend"
INI_DIR = ROOT / "gpt数据保存" / "mt5_runs" / "mr30"
OUT_ROOT = ROOT / "gpt数据保存" / "审计" / "第三批_MR30" / "runs"
COMMON_ROOT = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal" / "Common" / "Files" / "dshtrend"
TAGS = [
    "DS260913_MR30_V1_TRAIN", "DS260913_MR30_V1_VALID",
    "DS260913_MR30_V2_TRAIN", "DS260913_MR30_V2_VALID",
    "DS260913_MR30_V3_TRAIN", "DS260913_MR30_V3_VALID",
]
MAX_SECONDS = 45 * 60
LOCAL_TZ = timezone(timedelta(hours=8))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest().upper()


def now_local() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def find_files(root: Path, names: set[str]) -> list[Path]:
    if not root.is_dir():
        return []
    return [p for p in root.rglob("*") if p.is_file() and p.name in names]


def copy_if_present(src: Path, dst: Path) -> bool:
    if not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def run_one(tag: str) -> dict:
    ini = INI_DIR / f"{tag}.ini"
    out = OUT_ROOT / tag
    if tag not in TAGS:
        raise RuntimeError(f"tag not in frozen manifest: {tag}")
    if not ini.is_file():
        raise RuntimeError(f"missing planned INI: {ini}")
    # A failed tester initialization is evidence and must not be deleted.  If
    # a corrected binary is retried, keep the original attempt and place the
    # new capture beside it with an explicit retry suffix.
    attempt = 1
    if out.exists():
        attempt = 2
        while (OUT_ROOT / f"{tag}__retry{attempt}").exists():
            attempt += 1
        out = OUT_ROOT / f"{tag}__retry{attempt}"
    if not TERMINAL.is_file() or not EX5_SRC.is_file():
        raise RuntimeError("isolated terminal or sealed EX5 is missing")
    text = ini.read_text(encoding="utf-8-sig")
    required = {
        "Symbol=BTCUSDm", "Period=M1", "Model=2", "Optimization=0",
        "Deposit=500", "Currency=USD", "InpLatencyTicks=0",
        "InpAllowMinLotOvershoot=false", f"InpRunTag={tag}",
    }
    missing = sorted(x for x in required if x not in text)
    if missing:
        raise RuntimeError(f"INI guard failed for {tag}: {missing}")
    if "2025.06" in text or "2026.05" in text or "2026.06" in text or "2026.09" in text:
        raise RuntimeError(f"exposed/holdout date found in {ini}")

    out.mkdir(parents=True)
    # Copy the exact sealed binary and exact INI bytes used by the worker.
    copy_if_present(EX5_SRC, EXPERT_DIR / EX5_SRC.name)
    worker_ini = WORKER / "config" / f"run_{tag}.ini"
    copy_if_present(ini, worker_ini)
    start = now_local()
    start_epoch = time.time()
    cmd = [str(TERMINAL), "/portable", "/config:" + str(worker_ini)]
    print(f"[{start}] START {tag}", flush=True)
    print("  command:", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, cwd=str(WORKER), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rc = None
    timed_out = False
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        elapsed = int(time.time() - start_epoch)
        if elapsed > MAX_SECONDS:
            timed_out = True
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=20)
            rc = proc.returncode
            break
        if elapsed and elapsed % 30 == 0:
            print(f"  {tag}: still running ({elapsed}s)", flush=True)
        time.sleep(2)
    time.sleep(3)

    out_names = {"trades.csv", "signals.csv", "audit_selfcheck.csv", f"report_mr30_{tag}.htm",
                 f"mr30_{tag}.htm"}
    # FILE_COMMON is normally the AppData common directory.  Portable builds
    # may also leave a copy under the worker; search both without deleting data.
    candidates = find_files(COMMON_ROOT / tag, {"trades.csv", "signals.csv", "audit_selfcheck.csv"})
    candidates += find_files(WORKER, out_names)
    copied: dict[str, str] = {}
    seen: set[Path] = set()
    for src in candidates:
        src = src.resolve()
        if src in seen:
            continue
        seen.add(src)
        if src.name in {"trades.csv", "signals.csv", "audit_selfcheck.csv"}:
            dst = out / src.name
        elif src.suffix.lower() == ".htm":
            dst = out / "report.htm"
        else:
            continue
        if dst.exists():
            continue
        shutil.copy2(src, dst)
        copied[dst.name] = str(dst)

    # Preserve the most recent worker log as evidence of terminal/tester state.
    log_files = [p for p in (WORKER / "logs").glob("*.log") if p.is_file()]
    if log_files:
        newest = max(log_files, key=lambda p: p.stat().st_mtime)
        copy_if_present(newest, out / "terminal_latest.log")

    meta = {
        "tag": tag, "attempt": attempt, "started_at_local": start, "finished_at_local": now_local(),
        "returncode": rc, "timed_out": timed_out, "elapsed_seconds": round(time.time() - start_epoch, 1),
        "worker": str(WORKER), "command": cmd, "ini_path": str(ini),
        "ini_sha256": sha256(ini), "ex5_sha256": sha256(EX5_SRC),
        "copied_outputs": copied,
    }
    (out / "runner_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[{meta['finished_at_local']}] END {tag} rc={rc} timeout={timed_out} outputs={sorted(copied)}", flush=True)
    return meta


def main(argv: list[str]) -> int:
    selected = argv[1:] or TAGS
    for tag in selected:
        run_one(tag)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except Exception as exc:
        print(f"RUNNER_STOP: {exc}", file=sys.stderr)
        raise SystemExit(2)
