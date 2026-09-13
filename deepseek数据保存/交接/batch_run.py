#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
批次执行器：读 inbox_<品种>.jsonl 的请求 → 串行跑 MT5 → 写 outbox_<品种>.jsonl

用法:
    python batch_run.py 黄金
    python batch_run.py 黄金 --limit 10         # 只跑前 N 条
    python batch_run.py 黄金 --dry              # 只列出，不跑

设计要点（见 交接\MT5运行请求协议.md）:
  * MT5 独占 → 必须串行（逐条 subprocess.wait）
  * 每条请求参数只覆盖该 EA 的基线（EXPERTS / BASE_PARAMS / BASE_MEANREV）
  * 已跑过的 req_id 跳过（可重入，中断后接着跑）
  * 结果里带报告路径 + 审计路径 + 回撤事件统计
r"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(HERE)                      # deepseek数据保存
sys.path.insert(0, os.path.join(BASE_DIR, "run_trend"))   # runexp.py 在这
sys.path.insert(0, HERE)

import runexp as R  # noqa: E402  (需要通过 sys.path 指向 run_trend)

BASE = R.BASE
HANDOFF = os.path.join(BASE, "交接")
TERMINAL = R.TERMINAL
COMMON = os.path.join(
    os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal", "Common", "Files", "dshtrend")


# ★中文/非 ASCII 不能进 MT5 的 Report= / InpRunTag=（实测：测试 2.4 秒就"successfully finished"，
#   报告和审计文件都拿不到）。所以 tag 一律转成 ASCII。
_ASCII = {"黄金": "GD", "比特币": "BT", "日元": "JP", "gold": "GD", "btc": "BT", "jpy": "JP"}


def ascii_tag(who, rid):
    pre = _ASCII.get(who, "XX")
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in str(rid))
    return "%s_%s" % (pre, safe)


def load_jsonl(path):
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                print("  [warn] 无法解析一行: %s (%s)" % (e, line[:80]))
    return out


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def parse_dd_events(tag):
    r"""从 dd_episodes.csv / dd_monthly.csv 汇总"一年几次、每次多深、多久恢复"。r"""
    ep = os.path.join(COMMON, tag, "dd_episodes.csv")
    mo = os.path.join(COMMON, tag, "dd_monthly.csv")
    res = {}
    if os.path.isfile(ep):
        rows = []
        with open(ep, "r", encoding="utf-8-sig") as f:
            hdr = f.readline()
            for line in f:
                p = line.rstrip("\n").split(",")
                if len(p) >= 10:
                    rows.append(p)
        rec = [r for r in rows if r[1] == "recovered"]
        opn = [r for r in rows if r[1] == "still_open"]
        def fnum(x):
            try:
                return float(x)
            except Exception:
                return 0.0
        depths = [fnum(r[8]) for r in rec]
        recs = [fnum(r[9]) for r in rec]
        res = {
            "recovered": len(rec),
            "still_open": len(opn),
            "avg_depth": round(sum(depths) / len(depths), 2) if depths else None,
            "worst": round(max(depths), 2) if depths else None,
            "over10": sum(1 for d in depths if d >= 10),
            "over15": sum(1 for d in depths if d >= 15),
            "over20": sum(1 for d in depths if d >= 20),
            "over25": sum(1 for d in depths if d >= 25),
            "over30": sum(1 for d in depths if d >= 30),
            "avg_recover_h": round(sum(recs) / len(recs), 1) if recs else None,
            "max_recover_h": round(max(recs), 1) if recs else None,
        }
        # 把未恢复的事件深度也算进去（它是真实的回撤）
        if opn:
            od = [fnum(r[8]) for r in opn]
            res["open_depth"] = round(max(od), 2)
    if os.path.isfile(mo):
        rows = []
        with open(mo, "r", encoding="utf-8-sig") as f:
            f.readline()
            for line in f:
                p = line.rstrip("\n").split(",")
                if len(p) >= 6:
                    rows.append(p)
        try:
            dp = [float(r[5]) for r in rows]
            res["months"] = len(dp)
            res["months_over8"] = sum(1 for d in dp if d >= 8)
            res["months_over20"] = sum(1 for d in dp if d >= 20)
            res["worst_month"] = round(max(dp), 2) if dp else None
        except Exception:
            pass
    return res


def run_request(req, tag):
    expert = R.EXPERTS.get(req.get("expert", "trend"))
    if expert is None:
        return {"status": "rejected", "reason": "unknown expert %s" % req.get("expert")}
    phase = req.get("phase", "train")
    if phase == "hold":
        return {"status": "rejected", "reason": "hold 段是用户留白，禁止运行"}
    sym_key = req.get("symbol", "gold")
    if sym_key not in R.SYMBOLS:
        return {"status": "rejected", "reason": "unknown symbol %s" % sym_key}
    sym = R.SYMBOLS[sym_key]
    ph = R.phases_for(sym)
    # ★2026-09-12 修复：支持请求级 from/to 覆盖时间窗口（滚动优化必需）
    #   在此之前 req["from"]/req["to"] 全链路无人读取 → 54 条会静默跑成固定三段。
    #   硬标准：outbox 里的 from/to 必须等于请求里的日期。
    if req.get("from") and req.get("to"):
        ph = dict(ph)
        ph[phase] = (str(req["from"]), str(req["to"]))
    # ★2026-09-12 二次修复：支持 window:{from,to} 字段（黄金线发现 081/082 的窗口被忽略）
    #   事故：子代理在 `why` 里写了窗口区间，但只有文字、从未被解析 → 实际跑的是 phase 的默认区间。
    #   硬标准：outbox 里的 from/to 必须等于请求里显式指定的窗口。
    w = req.get("window") or {}
    if isinstance(w, dict) and w.get("from") and w.get("to"):
        ph = dict(ph)
        ph[phase] = (str(w["from"]), str(w["to"]))
    dep = req.get("deposit", 300)
    params = req.get("params") or {}
    base = {"meanrev": R.BASE_MEANREV, "btcswing": R.BASE_BTCSWING,
            "jpyrev": getattr(R, "BASE_JPYREV", {})}.get(req.get("expert", "trend"), R.BASE_PARAMS)

    merged = dict(base)
    merged.update({k: str(v) for k, v in params.items()})

    ini = R.make_ini(tag, phase, merged, sym, ph, dep, expert)
    t0 = time.time()
    p = subprocess.Popen([TERMINAL, "/config:" + ini])
    p.wait()
    el = round(time.time() - t0, 1)

    d = R.read_report("rep_" + tag)
    if d is None:
        return {"status": "error", "reason": "no report (测试器可能没跑起来)", "elapsed_s": el}

    net = R.num(d.get("Total Net Profit"))
    eqdd, eqddpct = R.pctpair(d.get("Equity Drawdown Maximal"))
    trades = R.num(d.get("Total Trades"))
    pf = R.num(d.get("Profit Factor"))
    years = R.phase_years(phase, ph)
    ann = round(net / float(dep) / years * 100, 2) if (net is not None and years) else None
    ret_dd = round(net / eqdd, 2) if (net and eqdd and eqdd > 0) else None

    return {
        "status": "done",
        "tag": tag,
        "symbol": sym,
        "expert": req.get("expert", "trend"),
        "phase": phase,
        "from": ph[phase][0],
        "to": ph[phase][1],
        "deposit": dep,
        "params": {k: str(v) for k, v in params.items()},
        "net": net,
        "pf": pf,
        "trades": trades,
        "dd_usd": eqdd,
        "dd_pct": eqddpct,
        "ann_pct": ann,
        "ret_dd": ret_dd,
        "dd_events": parse_dd_events(tag),
        "report": os.path.join(R.TERMDIR, "rep_%s.htm" % tag),
        "audit": os.path.join(COMMON, tag, "trades.csv"),
        "elapsed_s": el,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    who = sys.argv[1]
    limit = None
    dry = False
    only = None
    args = sys.argv[2:]
    for i, a in enumerate(args):
        if a == "--limit":
            limit = int(args[i + 1])
        if a == "--only":
            only = args[i + 1]
        if a == "--dry":
            dry = True

    inbox = os.path.join(HANDOFF, "inbox_%s.jsonl" % who)
    outbox = os.path.join(HANDOFF, "outbox_%s.jsonl" % who)
    reqs = load_jsonl(inbox)
    done = {r.get("req_id") for r in load_jsonl(outbox) if r.get("status") == "done"}
    # ★过滤（2026-09-12 修复，我的失误根因）：
    #   1) 网格行（有 grid_id）不是逐条请求 —— 以前会被当请求跑并报"缺字段"错
    #   2) --only 白名单：让调用方精确指定 req_id，不再把旧待跑条目一起捡进来
    todo = [r for r in reqs
            if r.get("req_id") and not r.get("grid_id") and r.get("req_id") not in done]
    if only:
        want = set(x.strip() for x in only.split(",") if x.strip())
        todo = [r for r in todo if r.get("req_id") in want]
    if limit:
        todo = todo[:limit]

    print("inbox 共 %d 条, 已完成 %d 条, 本次待跑 %d 条" % (len(reqs), len(done), len(todo)))
    if not todo:
        print("没有待跑的请求。")
        return 0

    ok = 0
    for i, req in enumerate(todo, 1):
        rid = req.get("req_id", "no-id")
        tag = ascii_tag(who, rid)
        if dry:
            print("[%d/%d] %s (dry)" % (i, len(todo), rid))
            continue
        print("[%d/%d] %s ..." % (i, len(todo), rid), end=" ", flush=True)
        try:
            res = run_request(req, tag)
        except Exception as e:
            res = {"status": "error", "reason": "exception: %s" % e}
        res["req_id"] = rid
        res["why"] = req.get("why", "")
        append_jsonl(outbox, res)
        if res.get("status") == "done":
            ok += 1
            print("net=%s pf=%s n=%s dd=%s%% ann=%s%% (%ss)" % (
                res["net"], res["pf"], res["trades"], res["dd_pct"], res["ann_pct"],
                res.get("elapsed_s")))
        else:
            print("FAILED: %s" % res.get("reason"))
    print("\n完成 %d/%d，结果已写入 %s" % (ok, len(todo), outbox))
    return 0


if __name__ == "__main__":
    sys.exit(main())



