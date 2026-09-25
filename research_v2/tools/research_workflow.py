from __future__ import annotations

"""Research workflow gates.

The workflow deliberately separates engineering/quick-screen evidence from
MT5 final-validation evidence.  A Python replay can never be promoted to a
final strategy conclusion by this module.
"""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent / "_repo_量化交易ai改进"
STATUS = ROOT / "CURRENT_STATUS.json"
LOG = ROOT / "TASK_LOG.jsonl"
LOCK = ROOT / ".engineering_run.lock"
REQUIRED = (
    "CURRENT_STATUS.json",
    "TASK_LOG.jsonl",
    "protocol/APPROVAL.json",
    "inventory/XAUUSDm_ALLOWED_VALIDATION.json",
)
FINAL_MODES = {"mt5_final", "mt5_holdout"}
QUICK_MODES = {"quick_screen", "parameter_feedback"}


def utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(args: list[str]) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()


def atomic_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(obj, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_json(path: Path, default: object | None = None) -> object:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def load_status() -> dict:
    value = load_json(STATUS, {})
    return value if isinstance(value, dict) else {}


def append_log(event: dict) -> None:
    with LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def next_seq() -> int:
    seq = 0
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                seq = max(seq, int(json.loads(line).get("seq", 0)))
            except Exception:
                continue
    return seq + 1


def approval() -> dict:
    value = load_json(ROOT / "protocol" / "APPROVAL.json", {})
    return value if isinstance(value, dict) else {}


def historical_authorized() -> bool:
    value = approval()
    return bool(value.get("historical_replay_authorized") is True)


def verify_required_files() -> None:
    missing = [name for name in REQUIRED if not (ROOT / name).exists()]
    if missing:
        raise SystemExit("VERIFY FAIL: missing " + ",".join(missing))


def verify_gate() -> None:
    verify_required_files()
    status = load_status()
    if LOCK.exists():
        raise SystemExit("VERIFY FAIL: active workflow lock exists")
    if status.get("authorization_status") == "ENGINEERING_REPAIR_ONLY_HISTORICAL_REPLAY_FALSE":
        print("VERIFY PASS: engineering-only gate is active; historical and MT5 runs remain blocked.")
    else:
        print("VERIFY PASS: required records and approval gate are present.")


def reserve(
    run_id: str,
    mode: str = "engineering",
    protocol_hash: str = "UNKNOWN",
    plan_hash: str = "UNKNOWN",
    engine_hash: str = "UNKNOWN",
    data_identity: str = "engineering_only",
    parameters: dict | None = None,
    command: str = "workflow",
    process_identity: str = "UNKNOWN",
) -> dict:
    if mode not in QUICK_MODES | FINAL_MODES | {"engineering"}:
        raise RuntimeError(f"unknown workflow mode: {mode}")
    if mode in QUICK_MODES | FINAL_MODES and not historical_authorized():
        raise RuntimeError("BLOCKED: historical replay requires protocol/APPROVAL.json authorization")
    if mode in FINAL_MODES and data_identity != "mt5_strategy_tester":
        raise RuntimeError("BLOCKED: final modes require data_identity=mt5_strategy_tester")
    run_root = ROOT / "runs" / ("engineering" if mode == "engineering" else "workflow")
    target = run_root / run_id
    if target.exists():
        existing = load_json(target / "run_state.json", {})
        if isinstance(existing, dict) and existing.get("status") == "COMPLETED":
            return existing
        raise RuntimeError("BLOCKED: output exists with non-completed or unknown state")
    if LOCK.exists():
        raise RuntimeError("BLOCKED: active workflow lock exists")
    target.mkdir(parents=True, exist_ok=True)
    LOCK.mkdir()
    state = {
        "run_id": run_id,
        "status": "RESERVED",
        "mode": mode,
        "evidence_class": "MT5_FINAL" if mode in FINAL_MODES else "ENGINEERING_OR_QUICK",
        "protocol_hash": protocol_hash,
        "plan_hash": plan_hash,
        "engine_hash": engine_hash,
        "data_identity": data_identity,
        "parameters": parameters or {},
        "command": command,
        "start_time": utc(),
        "process_identity": process_identity,
        "execution_attempt": 1,
        "final_claim_allowed": False,
    }
    atomic_json(target / "run_state.json", state)
    append_log({
        "seq": next_seq(),
        "timestamp_utc": utc(),
        "stage": "WORKFLOW",
        "step_id": "RESERVE",
        "event": "RUN_RESERVED",
        "mode": mode,
        "input_identity": data_identity,
        "output_paths": [str((target / "run_state.json").relative_to(ROOT))],
        "result": "OK",
    })
    return state


def finish(run_id: str, status: str = "COMPLETED", **extra: object) -> dict:
    engineering_target = ROOT / "runs" / "engineering" / run_id
    target = engineering_target if engineering_target.exists() else ROOT / "runs" / "workflow" / run_id
    state = load_json(target / "run_state.json", {})
    if not isinstance(state, dict):
        raise RuntimeError("run state is invalid")
    state.update(status=status, end_time=utc(), **extra)
    atomic_json(target / "run_state.json", state)
    if LOCK.exists():
        LOCK.rmdir()
    append_log({
        "seq": next_seq(),
        "timestamp_utc": utc(),
        "stage": "WORKFLOW",
        "step_id": "FINISH",
        "event": "RUN_" + status,
        "mode": state.get("mode"),
        "input_identity": state.get("data_identity"),
        "result": status,
    })
    return state


def validate_mt5_evidence(report: Path, manifest: Path) -> dict:
    if not report.exists():
        raise RuntimeError("BLOCKED: MT5 report does not exist")
    if report.suffix.lower() not in {".htm", ".html", ".json"}:
        raise RuntimeError("BLOCKED: final evidence must be an MT5 HTML/JSON report")
    value = load_json(manifest, {})
    if not isinstance(value, dict):
        raise RuntimeError("BLOCKED: invalid MT5 manifest")
    required = {"tester", "symbol", "model", "from", "to", "initial_deposit", "history_source"}
    missing = sorted(required - set(value))
    if missing:
        raise RuntimeError("BLOCKED: MT5 manifest missing " + ",".join(missing))
    if value.get("tester") != "MetaTrader5_StrategyTester":
        raise RuntimeError("BLOCKED: evidence is not from MT5 Strategy Tester")
    if value.get("history_source") != "broker_native_symbol":
        raise RuntimeError("BLOCKED: final validation must identify a broker-native symbol")
    return value


def cmd_status(_: argparse.Namespace) -> None:
    print(json.dumps(load_status(), ensure_ascii=False, indent=2))


def cmd_verify(_: argparse.Namespace) -> None:
    verify_gate()


def cmd_run(args: argparse.Namespace) -> None:
    if args.mode == "engineering" and not args.synthetic:
        raise SystemExit("BLOCKED: engineering runs require --synthetic")
    state = reserve(
        args.run_id,
        mode=args.mode,
        data_identity="synthetic_only" if args.synthetic else args.data_identity,
        parameters={"synthetic": args.synthetic},
        command=" ".join(args.command) if args.command else "workflow",
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_finish(args: argparse.Namespace) -> None:
    if args.mode in FINAL_MODES:
        validate_mt5_evidence(Path(args.report), Path(args.manifest))
        print(json.dumps(finish(args.run_id, final_claim_allowed=True), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(finish(args.run_id), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    run = sub.add_parser("run")
    run.add_argument("--run-id", required=True)
    run.add_argument("--mode", choices=sorted(QUICK_MODES | FINAL_MODES | {"engineering"}), default="engineering")
    run.add_argument("--synthetic", action="store_true")
    run.add_argument("--data-identity", default="engineering_only")
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(fn=cmd_run)
    done = sub.add_parser("finish")
    done.add_argument("--run-id", required=True)
    done.add_argument("--mode", choices=sorted(QUICK_MODES | FINAL_MODES), default="quick_screen")
    done.add_argument("--report", default="")
    done.add_argument("--manifest", default="")
    done.set_defaults(fn=cmd_finish)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
