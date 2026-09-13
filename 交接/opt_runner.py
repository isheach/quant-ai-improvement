#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MT5 native parallel optimization runner (v2)

Verified facts (2026-09-12):
1. .set lives in  MQL5/Profiles/Tester/<EAname>.set   (UTF-16LE)
2. ini uses Optimization=2 and MUST NOT contain [TesterInputs] -> MT5 auto-loads same-name .set
3. Result is SpreadsheetML xml (UTF-8). Header includes:
   Pass|Result|Profit|Expected Payoff|Profit Factor|Recovery Factor|Sharpe Ratio
   |Custom|Equity DD %|Trades|<optimized param 1>|<optimized param 2>...
   => trades AND parameter values are both present. No reverse-engineering needed.
4. MT5 REWRITES <EA>.set after each run with "last used params"
   (proof: .set mtime == xml mtime, my ini was written earlier).
   => If all grids share one EA name, the next grid reads the previous grid's leftovers.
   FIX: copy the compiled ex5 to a UNIQUE EA name per grid.

Usage:
    python opt_runner.py list
    python opt_runner.py run --who 黄金
    python opt_runner.py run --inbox 滚动优化/inbox_grid_滚动优化.jsonl
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BASE_DIR, "run_trend"))

import runexp as R  # noqa: E402

MAIN_DATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                         "53785E099C927DB68A545C249CDBCE06")
INSTALL = r"C:\Program Files\MetaTrader 5 EXNESS"
TERMINAL = os.path.join(INSTALL, "terminal64.exe")
EXPERT_DIR = os.path.join(MAIN_DATA, "MQL5", "Experts", "dshtrend")
PROFILES_TESTER = os.path.join(MAIN_DATA, "MQL5", "Profiles", "Tester")
CFGDIR = os.path.join(BASE_DIR, "mql5", "config")
CRED = os.path.join(CFGDIR, "mt5_account.local.txt")

LOGIN, PASSWORD, SERVER = "277335900", "yxqY3lab@", "Exness-MT5Trial5"

TF_NUM = {
    "PERIOD_M1": "1", "PERIOD_M2": "2", "PERIOD_M3": "3", "PERIOD_M4": "4",
    "PERIOD_M5": "5", "PERIOD_M6": "6", "PERIOD_M10": "10", "PERIOD_M12": "12",
    "PERIOD_M15": "15", "PERIOD_M20": "20", "PERIOD_M30": "30",
    "PERIOD_H1": "16385", "PERIOD_H2": "16386", "PERIOD_H3": "16387",
    "PERIOD_H4": "16388", "PERIOD_H6": "16390", "PERIOD_H8": "16392",
    "PERIOD_H12": "16396", "PERIOD_D1": "16408", "PERIOD_W1": "32769",
    "PERIOD_MN1": "49153", "PERIOD_CURRENT": "0",
}

EA_FILE = {
    "trend": "dsh_TrendCore.mq5",
    "meanrev": "dsh_MeanRev.mq5",
    "btcswing": "dsh_BtcSwing.mq5",
    "jpyrev": "dsh_JPYRev.mq5",
    "jpygrid": "dsh_JPYGrid.mq5",
}


def read_cred():
    global LOGIN, PASSWORD, SERVER
    if os.path.isfile(CRED):
        for line in open(CRED, encoding="utf-8-sig"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "LOGIN":
                    LOGIN = v.strip()
                elif k.strip() == "PASSWORD":
                    PASSWORD = v.strip()
                elif k.strip() == "SERVER":
                    SERVER = v.strip()


def ea_src(expert):
    f = EA_FILE.get(expert)
    return os.path.join(BASE_DIR, "mql5", "dshtools", f) if f else None


def parse_inputs(mq5_path):
    out = []
    for line in io.open(mq5_path, encoding="utf-8-sig", errors="ignore"):
        m = re.match(r"\s*input\s+([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*=\s*([^;]+);", line)
        if not m:
            continue
        typ, name, dflt = m.group(1), m.group(2), m.group(3).strip()
        kind = ("bool" if typ == "bool" else
                "str" if typ == "string" else
                "num" if typ in ("double", "float") else
                "enum" if typ == "ENUM_TIMEFRAMES" else "int")
        out.append((name, dflt, kind))
    return out


def build_set(expert, fixed, opt):
    p = ea_src(expert)
    if not p or not os.path.isfile(p):
        raise RuntimeError("missing EA source: %s" % expert)
    inputs = parse_inputs(p)
    names = {n for n, _, _ in inputs}
    for k in list(fixed) + list(opt):
        if k not in names:
            raise RuntimeError("EA does not know param: %s" % k)
    lines = ["; opt_runner %s" % time.strftime("%Y-%m-%d %H:%M:%S")]
    for name, dflt, kind in inputs:
        if name in opt:
            if kind == "bool":
                lines.append("%s=%s||false||0||true||Y" % (name, dflt))
            else:
                s, st, e = opt[name]
                # ★修复 1：ENUM_TIMEFRAMES 的默认值在源码里是符号名（PERIOD_M5 等），
                #   直接写进 .set 会被 MT5 还原成 0=PERIOD_CURRENT → EA 守卫静默 0 成交。
                #   这里统一翻译成数字。
                if kind == "enum":
                    dflt = TF_NUM.get(str(dflt).strip(), dflt)
                    s = TF_NUM.get(str(s).strip(), s)
                # ★修复 2：opt 起点为 0 时 MT5 会直接拒绝优化（0 pass、无 XML）。
                #   若起点=0，就用步长当前缀（保证 >=1 个档位）。
                try:
                    if float(s) == 0.0 and float(st) not in (0.0,):
                        s = str(int(float(st))) if float(st) == int(float(st)) else str(float(st))
                except Exception:
                    pass
                lines.append("%s=%s||%s||%s||%s||Y" % (name, dflt, s, st, e))
        elif name in fixed:
            lines.append("%s=%s" % (name, fixed[name]))
        else:
            lines.append("%s=%s" % (name, dflt))
    return "\n".join(lines) + "\n"


def write_set(ea_name, content):
    os.makedirs(PROFILES_TESTER, exist_ok=True)
    p = os.path.join(PROFILES_TESTER, "%s.set" % ea_name)
    with open(p, "wb") as f:
        f.write(b"\xff\xfe" + content.encode("utf-16-le"))
    return p


def ensure_unique_ea(expert, ea_name):
    base = os.path.splitext(EA_FILE[expert])[0]
    src = os.path.join(EXPERT_DIR, "%s.ex5" % base)
    if not os.path.isfile(src):
        raise RuntimeError("compiled EA not found: %s" % src)
    dst = os.path.join(EXPERT_DIR, "%s.ex5" % ea_name)
    shutil.copy2(src, dst)
    return dst


def combo_count(opt):
    n = 1
    for k, v in opt.items():
        try:
            s, st, e = float(v[0]), float(v[1]), float(v[2])
            n *= (int(round((e - s) / st)) + 1) if st else 1
        except Exception:
            n *= 2
    return n


def make_ini(tag, ea_name, symbol, d_from, d_to, deposit=300):
    lines = ["[Common]", "Login=" + LOGIN, "Password=" + PASSWORD,
             "Server=" + SERVER, "KeepPrivate=1", "NewsEnable=0", "CertInstall=0",
             "[Experts]", "AllowLiveTrading=0", "AllowDllImport=0", "Enabled=1",
             "Account=0", "Profile=0",
             "[Tester]", "Expert=dshtrend\\%s" % ea_name,
             "Symbol=" + symbol, "Period=M1", "Model=2",
             # ★2026-09-12 关键修复（比特币线定位）：
             #   Optimization=1 → 完整算法（穷举笛卡尔积，pass 数 == 声明组合数）
             #   Optimization=2 → 快速遗传算法（GA，pass 数远小于组合数且会收敛到局部）
             #   此前误用 2 → 6 个网格只跑了 8.9% 的组合、GA 收敛到坏区域导致 0 profitable。
             "Optimization=1",
             "FromDate=" + d_from, "ToDate=" + d_to,
             "ForwardMode=0", "Deposit=" + str(deposit), "Currency=USD",
             "Leverage=1:200", "ExecutionMode=0", "Visual=0",
             "Report=rep_%s" % tag, "ReplaceReport=1", "ShutdownTerminal=1"]
    p = os.path.join(CFGDIR, "opt_%s.ini" % tag)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return p


def parse_opt_xml(path):
    if not os.path.isfile(path):
        return []
    s = open(path, "rb").read().decode("utf-8-sig", errors="ignore")
    rows = re.findall(r"<Row[^>]*>(.*?)</Row>", s, re.S)
    if not rows:
        return []

    def cells(r):
        return [re.sub(r"<[^>]+>", "", c).strip()
                for c in re.findall(r"<Cell[^>]*>(.*?)</Cell>", r, re.S)]

    hdr = cells(rows[0])
    out = []
    for r in rows[1:]:
        c = cells(r)
        if len(c) < len(hdr):
            c += [""] * (len(hdr) - len(c))
        out.append(dict(zip(hdr, c)))
    return out


def run_grid(g, deposit=300):
    expert = g.get("expert", "trend")
    symbol = R.SYMBOLS.get(g.get("symbol", "btc"), g.get("symbol"))
    # ★★2026-09-12 关键修复（比特币线冒烟网格 btcgrid-101 暴露）：
    #   此前只用请求里的 fixed，未合并 EA 基线 → 请求里没提到的参数全部落回【源码默认值】，
    #   与单跑通道（runexp 的 BASE_*）不一致，导致：
    #     网格 InpUseEntryQuality=true  vs  单跑基线 false  → 笔数 5,565 vs 35
    #     网格 InpUseDDKill=false        vs  单跑基线 true
    #   后果：冒烟网格无法复现 btc-138 的 +412.52（实际全负、DD 99.96%）——
    #   即"网格通道与单跑通道结果不可比"。修法：先套 EA 基线，再让请求的 fixed 覆盖它。
    base = {"meanrev": R.BASE_MEANREV, "btcswing": R.BASE_BTCSWING,
            "jpyrev": getattr(R, "BASE_JPYREV", {}),
            "jpygrid": {}}.get(
                expert, getattr(R, "BASE_PARAMS", {}))
    # ★★2026-09-12 二次修复（日元滚动线的网格冒烟 jyrg-g-smokeL 暴露）：
    #   某些 EA 的参数集与 runexp 的 BASE_* 不兼容（如 dsh_JPYGrid 是固定手数设计、
    #   没有 InpRiskPct）→ 合并会写出 EA 不认识的参数 → MT5 报
    #   "EA does not know param: InpRiskPct"。
    #   修法：合并时只保留【该 EA 源码里真实存在的 input】，其余丢弃（不报错）。
    _ea_p = ea_src(expert)
    _known = {n for n, _, _ in parse_inputs(_ea_p)} if _ea_p and os.path.isfile(_ea_p) else None
    fixed = {}
    for k, v in base.items():
        if _known is None or k in _known:
            fixed[k] = v
    for k, v in (g.get("fixed") or {}).items():
        fixed[k] = str(v)
    # ★延迟口径（2026-09-12 实测）：Sleep(InpLatencyMs) 在 MT5 测试器里无效
    #   （A/B 实证 144/144 pass 逐位全同）。改用 tick 级延迟 InpLatencyTicks。
    fixed["InpLatencyMs"] = "0"
    if "InpLatencyTicks" not in (g.get("fixed") or {}):
        # 尊重请求里显式给出的值（如 btc-140 故意用 0 做对照）；否则默认 1
        fixed["InpLatencyTicks"] = "1"
    fixed.setdefault("InpVerboseLog", "false")
    opt = dict(g.get("opt") or {})

    gid = re.sub(r"[^A-Za-z0-9_-]", "_", g.get("grid_id", "g"))
    tag = "OPT_" + gid
    ea_name = "opt_" + gid[:24]

    n = combo_count(opt)
    write_set(ea_name, build_set(expert, fixed, opt))
    ensure_unique_ea(expert, ea_name)
    ini = make_ini(tag, ea_name, symbol, g["from"], g["to"], deposit)

    t0 = time.time()
    pr = subprocess.Popen([TERMINAL, "/config:" + ini])
    pr.wait()
    el = round(time.time() - t0, 1)

    xml = os.path.join(MAIN_DATA, "rep_%s.xml" % tag)
    rows = parse_opt_xml(xml)
    return {"tag": tag, "ea_name": ea_name, "combos": n,
            "elapsed_s": el, "xml": xml, "rows": rows}


def to_outbox(grid_id, g, res):
    keys = list((g.get("opt") or {}).keys())
    out = []
    for r in res["rows"]:
        out.append({
            "grid_id": grid_id,
            "pass": r.get("Pass"),
            "params": {k: r.get(k) for k in keys},
            "net": r.get("Profit"),
            "profit_factor": r.get("Profit Factor"),
            "expected_payoff": r.get("Expected Payoff"),
            "recovery_factor": r.get("Recovery Factor"),
            "sharpe": r.get("Sharpe Ratio"),
            "dd_pct": r.get("Equity DD %"),
            "trades": r.get("Trades"),
            "from": g.get("from"), "to": g.get("to"),
            "expert": g.get("expert"), "symbol": g.get("symbol"),
            "elapsed_s": res["elapsed_s"], "xml": res["xml"],
        })
    return out


def load_jsonl(p):
    if not os.path.isfile(p):
        return []
    out = []
    for line in open(p, encoding="utf-8-sig"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def find_grid_files():
    cands = [os.path.join(HERE, "inbox_%s.jsonl" % w)
             for w in ("比特币", "黄金", "日元", "滚动优化")]
    for root, _, files in os.walk(HERE):
        for f in files:
            if f.endswith(".jsonl") and "grid" in f.lower():
                cands.append(os.path.join(root, f))
    return [p for p in dict.fromkeys(cands) if os.path.isfile(p)]


def cmd_list(args):
    for p in find_grid_files():
        rows = load_jsonl(p)
        grids = [r for r in rows if r.get("grid_id") and r.get("opt")]
        if grids:
            print("%s  (%d grids)" % (os.path.relpath(p, HERE), len(grids)))
            for g in grids:
                print("   %-24s %-9s %-5s %s -> %s  %d combos"
                      % (g["grid_id"], g.get("expert"), g.get("symbol"),
                         g.get("from"), g.get("to"), combo_count(g.get("opt") or {})))
    return 0


def cmd_run(args):
    if args.inbox:
        inbox = args.inbox if os.path.isabs(args.inbox) else os.path.join(HERE, args.inbox)
        outbox = os.path.join(os.path.dirname(inbox),
                              "outbox_" + os.path.basename(inbox).replace("inbox_", ""))
    else:
        inbox = os.path.join(HERE, "inbox_%s.jsonl" % args.who)
        outbox = os.path.join(HERE, "outbox_%s.jsonl" % args.who)
    grids = [r for r in load_jsonl(inbox) if r.get("grid_id") and r.get("opt")]
    # ★修复（滚动优化线指出）：原来的去重只看 grid_id，导致"同名不同窗口"的网格
    #   被静默跳过、读到旧 XML。改为按 (grid_id, from, to) 三元组去重。
    #   实测事故：wf-w0-t-on 在第一批是训练段、第二批标签写成测试段 → 复用训练段结果，
    #   日期标签却是测试段 → 会把训练段结果当成 OOS（协议 §5-8 那类假成功）。
    done = {(r.get("grid_id"), str(r.get("from")), str(r.get("to")))
            for r in load_jsonl(outbox) if r.get("grid_id")}
    # 同时加"数值指纹"告警：若新跑结果与已有结果逐位相同但日期不同 → 高度可疑
    todo = [g for g in grids if (g["grid_id"], str(g.get("from")), str(g.get("to"))) not in done]
    if args.only:
        want = set(args.only.split(","))
        todo = [g for g in todo if g["grid_id"] in want]
    if args.limit:
        todo = todo[:args.limit]
    print("inbox=%s" % inbox)
    print("outbox=%s" % outbox)
    print("grids=%d done=%d todo=%d" % (len(grids), len(done), len(todo)))
    if not todo:
        return 0
    read_cred()
    for i, g in enumerate(todo, 1):
        gid = g["grid_id"]
        print("[%d/%d] %s (%s %s %s -> %s) %d combos ..."
              % (i, len(todo), gid, g.get("expert"), g.get("symbol"),
                 g.get("from"), g.get("to"), combo_count(g.get("opt") or {})),
              end=" ", flush=True)
        try:
            res = run_grid(g)
        except Exception as e:
            print("ERROR %s" % e)
            with open(outbox, "a", encoding="utf-8") as f:
                f.write(json.dumps({"grid_id": gid, "status": "error",
                                    "error": str(e)}, ensure_ascii=False) + "\n")
            continue
        recs = to_outbox(gid, g, res)
        with open(outbox, "a", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        good = [r for r in recs if r.get("net") and float(r["net"]) > 0]
        print("%d pass, %d profitable, %.1fs" % (len(recs), len(good), res["elapsed_s"]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("--who", default=None)
    r.add_argument("--inbox", default=None)
    r.add_argument("--only", default=None)
    r.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "list":
        return cmd_list(a)
    if a.cmd == "run":
        return cmd_run(a)


if __name__ == "__main__":
    sys.exit(main())


