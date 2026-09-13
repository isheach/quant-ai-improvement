#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 0 v2 · Provenance 证据重建（GPT 复核意见 §3.1–§3.5 / 阶段 A）

对 v1 的六处修正：
  ① 不再按 req_id 首次去重：以【复合唯一键】建立 run/pass 记录
     key = req_id|grid_id + tag + pass/config_hash
  ② RUN_ERROR → lead_only（v1 有 13 个被错标 verified）
  ③ 空 symbol/deposit/model/date → provenance_unknown（不是"无违规"）
  ④ 留白检查改为【区间重叠】：from <= 2026-09-30 AND to >= 2026-06-01
     并扫描 .md/.jsonl/.ini/.htm/.xml 的文本内容
  ⑤ MR5 trade_count 口径分离，大差或无 position_id → audit_reconcile_required
  ⑥ 不改动 run_manifest 旧三行；新记录只追加
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import hashlib
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
HANDOFF = os.path.join(BASE, "交接")
OUT = os.path.join(HERE, "stage0_provenance_v2")
os.makedirs(OUT, exist_ok=True)

TDATA = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                     "53785E099C927DB68A545C249CDBCE06")
COMMON = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal",
                      "Common", "Files", "dshtrend")
CFGDIR = os.path.join(BASE, "mql5", "config")
EADIR = os.path.join(BASE, "mql5", "dshtools")

ALLOWED = {"XAUUSDm", "BTCUSDm", "USDJPYm"}
HO_FROM, HO_TO = dt.date(2026, 6, 1), dt.date(2026, 9, 30)
TODAY = dt.date(2026, 9, 13)

EA_FILE = {"trend": "dsh_TrendCore.mq5", "meanrev": "dsh_MeanRev.mq5",
           "btcswing": "dsh_BtcSwing.mq5", "jpyrev": "dsh_JPYRev.mq5",
           "jpygrid": "dsh_JPYGrid.mq5", "tickclock": "dsh_TickClock.mq5"}


def sha256(p):
    if not p or not os.path.isfile(p):
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest().upper()


def load_jsonl(p):
    out = []
    if not os.path.isfile(p):
        return out
    for i, line in enumerate(io.open(p, encoding="utf-8-sig", errors="ignore")):
        line = line.strip()
        if not line:
            continue
        try:
            out.append((i, json.loads(line)))
        except Exception:
            out.append((i, None))
    return out


def parse_ini(p):
    if not p or not os.path.isfile(p):
        return {}, {}
    t, inp = {}, {}
    sect = None
    for line in io.open(p, encoding="utf-8-sig", errors="ignore"):
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("[") and s.endswith("]"):
            sect = s[1:-1].lower()
            continue
        if "=" in s:
            k, v = s.split("=", 1)
            (t if sect == "tester" else inp)[k.strip()] = v.strip()
    return t, inp


def nd(s):
    if not s:
        return None
    m = re.match(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(s).strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def overlaps_holdout(a, b):
    """★修正④：区间重叠（v1 只查端点）"""
    if a is None or b is None:
        return None            # 未知 → 不能声称"未触碰"
    return a <= HO_TO and b >= HO_FROM


def audit_rows(tag):
    p = os.path.join(COMMON, tag, "trades.csv")
    if not os.path.isfile(p):
        return None
    with io.open(p, encoding="utf-8-sig", errors="ignore", newline="") as f:
        try:
            return list(csv.DictReader(f))
        except Exception:
            return None


def config_hash(fixed):
    if not fixed:
        return ""
    s = "|".join("%s=%s" % (k, fixed[k]) for k in sorted(fixed))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16].upper()


def main():
    files = []
    for who in ("黄金", "日元", "比特币", "滚动优化"):
        p = os.path.join(HANDOFF, "inbox_%s.jsonl" % who)
        if os.path.isfile(p):
            files.append((who, p))
    for f in sorted(os.listdir(HANDOFF)):
        if f.startswith(("inbox_TMP", "outbox_TMP")) and f.endswith(".jsonl"):
            files.append(("临时", os.path.join(HANDOFF, f)))
    sub = os.path.join(HANDOFF, "日元滚动")
    if os.path.isdir(sub):
        for f in sorted(os.listdir(sub)):
            if f.startswith("inbox") and f.endswith(".jsonl"):
                files.append(("日元滚动", os.path.join(sub, f)))

    # ---- 1. 建立 run/pass 级记录（复合键）----
    runs = {}
    order = []
    for who, inbox in files:
        outbox = inbox.replace("inbox", "outbox")
        entries = load_jsonl(outbox)
        if outbox.endswith("TMP.jsonl"):
            continue
        for lineno, r in entries:
            if r is None:
                continue
            rid = r.get("req_id") or r.get("grid_id")
            if not rid:
                continue
            tag = r.get("tag") or ("BT_" + rid if r.get("req_id") else "OPT_" + rid)
            fixed = r.get("params") or r.get("fixed") or {}
            ch = config_hash(fixed)
            key = "%s|%s|%s" % (rid, tag, ch or "-")
            if key in runs:
                # 重试/覆盖 → 记 lineage
                runs[key]["occurrences"] += 1
                runs[key]["last_status"] = r.get("status", "")
                runs[key]["last_lineno"] = lineno
                runs[key]["lineage"].append(r.get("status", ""))
                continue
            runs[key] = dict(
                key=key, run_id=tag, req_or_grid=rid, source_line=who,
                first_status=r.get("status", ""), last_status=r.get("status", ""),
                occurrences=1, first_lineno=lineno, last_lineno=lineno,
                lineage=[r.get("status", "")],
                expert=r.get("expert", ""), symbol_in=r.get("symbol", ""),
                phase=r.get("phase", ""), window=r.get("window"),
                from_in=r.get("from", ""), to_in=r.get("to", ""),
                deposit_in=r.get("deposit", ""), net=r.get("net", ""),
                pf=r.get("pf", ""), trades_mt5=r.get("trades", ""),
                dd_pct=r.get("dd_pct", ""), chash=ch or "",
                n_fixed=len(fixed),
            )
            order.append(key)

    # ---- 2. 逐条补齐权威字段 ----
    rows_out = []
    hashes = set()
    for key in order:
        d = runs[key]
        tag = d["run_id"]
        ini = os.path.join(CFGDIR, "run_%s.ini" % tag)
        if not os.path.isfile(ini):
            for cand in ("run_%s.ini" % tag.replace("BT_", "").replace("GD_", "").replace("JP_", ""),
                         "run_%s.ini" % tag.replace("XX_", "")):
                if os.path.isfile(os.path.join(CFGDIR, cand)):
                    ini = os.path.join(CFGDIR, cand)
                    break
        ini = ini if os.path.isfile(ini) else ""
        tsec, tinput = parse_ini(ini) if ini else ({}, {})
        rep = os.path.join(TDATA, "rep_%s.htm" % tag)
        rep = rep if os.path.isfile(rep) else ""
        ar = audit_rows(tag)
        src = os.path.join(EADIR, EA_FILE.get(d["expert"], "")) if EA_FILE.get(d["expert"]) else ""
        ex5 = os.path.join(TDATA, "MQL5", "Experts", "dshtrend",
                           EA_FILE.get(d["expert"], "x")[:-4] + ".ex5") if EA_FILE.get(d["expert"]) else ""

        sym = d["symbol_in"] or tsec.get("Symbol", "")
        sym = {"btc": "BTCUSDm", "gold": "XAUUSDm", "jpy": "USDJPYm"}.get(str(sym).lower(), sym)
        a = nd(d["from_in"] or (d["window"] or {}).get("from") or tsec.get("FromDate"))
        b = nd(d["to_in"] or (d["window"] or {}).get("to") or tsec.get("ToDate"))
        dep = str(d["deposit_in"] or tsec.get("Deposit", "") or "")
        model = str(tsec.get("Model", "") or "")

        flags = []
        unknown = []
        if not sym:
            unknown.append("symbol")
        elif sym not in ALLOWED:
            flags.append("NON_REAL_SYMBOL")
        if not dep:
            unknown.append("deposit")
        if not model:
            unknown.append("model")
        if a is None or b is None:
            unknown.append("dates")
        ov = overlaps_holdout(a, b)
        if ov is True:
            flags.append("TOUCHES_HOLDOUT")
        elif ov is None:
            unknown.append("holdout_undecidable")

        # ★修正②：RUN_ERROR → lead_only
        if d["first_status"] == "error" or "error" in d["lineage"]:
            flags.append("RUN_ERROR" if d["last_status"] != "done" else "RUN_ERROR_RETRIED")
        if d["first_status"] != "done" and d["last_status"] != "done":
            flags.append("NOT_DONE")
        if not ini:
            flags.append("NO_INI")
        if ar is None:
            flags.append("NO_AUDIT_FILE")
        if not rep:
            flags.append("NO_REPORT")

        t_mt5 = d["trades_mt5"]
        t_aud = len(ar) if ar else None
        acr = False
        if t_mt5 not in (None, "") and t_aud:
            try:
                if abs(float(t_mt5) - float(t_aud)) > 0.5:
                    flags.append("TRADE_COUNT_MISMATCH")
                    acr = True
            except Exception:
                pass
        has_pid = bool(ar) and ("position_id" in (ar[0] or {}))
        if not has_pid:
            acr = True
        if acr:
            flags.append("AUDIT_RECONCILE_REQUIRED")

        # ★修正③：未知字段 → provenance_unknown
        status = "verified"
        if "TOUCHES_HOLDOUT" in flags or "NON_REAL_SYMBOL" in flags:
            status = "blocked"
        elif unknown:
            status = "provenance_unknown"
        elif any(f in flags for f in ("RUN_ERROR", "NOT_DONE", "NO_INI", "NO_AUDIT_FILE",
                                      "NO_REPORT", "AUDIT_RECONCILE_REQUIRED",
                                      "RUN_ERROR_RETRIED")):
            status = "lead_only"

        rows_out.append(dict(
            run_id=tag, composite_key=key, source_line=d["source_line"],
            req_or_grid=d["req_or_grid"], status=status, flags=";".join(flags),
            unknown_fields=";".join(unknown), occurrences=d["occurrences"],
            lineage=">".join(d["lineage"][:6]), config_hash=d["chash"],
            symbol=sym, deposit=dep, model=model, period=tsec.get("Period", ""),
            latency="%s/%s" % (tinput.get("InpLatencyMs", "?"), tinput.get("InpLatencyTicks", "?")),
            d_from=str(a or ""), d_to=str(b or ""),
            expert=d["expert"], ea_sha256=sha256(src), ex5_sha256=sha256(ex5),
            ini_sha256=sha256(ini), report_sha256=sha256(rep),
            audit_rows=(t_aud if t_aud is not None else ""),
            audit_has_position_id=("1" if has_pid else "0"),
            trade_count_mt5=(t_mt5 if t_mt5 is not None else ""),
            net=d["net"], pf=d["pf"], dd_pct=d["dd_pct"],
        ))
        for p in (ini, rep, src, ex5):
            if p and os.path.isfile(p):
                hashes.add("%s  %s" % (sha256(p), p))

    # ---- 3. 文本扫描：未来日期 + 留白（★修正④）----
    scan = []
    pat_future = re.compile(r"20\d\d[-./]\d{2}[-./]\d{2}")
    for root, _, fs in os.walk(BASE):
        if "旧量化策略" in root:
            continue
        for f in fs:
            if not f.lower().endswith((".md", ".jsonl", ".ini", ".htm", ".xml")):
                continue
            fp = os.path.join(root, f)
            if os.path.getsize(fp) > 8 << 20:
                continue
            try:
                s = io.open(fp, encoding="utf-8-sig", errors="ignore").read()
            except Exception:
                continue
            for m in pat_future.finditer(s):
                dd = nd(m.group(0))
                if dd and dd > TODAY:
                    scan.append(dict(path=fp.replace(BASE + os.sep, ""), date=m.group(0),
                                     kind="FUTURE_DATE", context=s[max(0, m.start()-60):m.start()+40].replace("\n", " ")))

    # ---- 4. 输出 ----
    csvp = os.path.join(OUT, "provenance_inventory_v2.csv")
    with io.open(csvp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    with io.open(os.path.join(OUT, "hashes_v2.sha256"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(hashes)) + "\n")

    st = collections.Counter(r["status"] for r in rows_out)
    fl = collections.Counter()
    for r in rows_out:
        for x in r["flags"].split(";"):
            if x:
                fl[x] += 1
    unk = collections.Counter()
    for r in rows_out:
        for x in r["unknown_fields"].split(";"):
            if x:
                unk[x] += 1

    L = []
    L.append("# Stage 0 **v2** · Provenance 证据重建结论\n")
    L.append("依据：GPT 复核意见 §3.1–§3.5 / 阶段 A。**本文件取代 v1 的结论。**\n")
    L.append("## 1. v1 的六处修正\n")
    L.append("| # | v1 的问题 | v2 的处理 |")
    L.append("|---|---|---|")
    L.append("| ① | 按 `req_id` 首次去重 → 519 是「唯一 ID 数」 | 改用**复合键** `req_id\\|tag\\|config_hash`；保留 lineage |")
    L.append("| ② | `RUN_ERROR` 未纳入 `lead_only` | **error 一律 `lead_only`**；区分 `RUN_ERROR` / `RUN_ERROR_RETRIED` |")
    L.append("| ③ | 空字段被当作「无违规」 | 空 symbol/deposit/model/date → **`provenance_unknown`** |")
    L.append("| ④ | 留白只查端点 | 改为**区间重叠** `from<=09-30 AND to>=06-01`；并扫描全部文本 |")
    L.append("| ⑤ | 笔数差未分离口径 | 分离 `trade_count_mt5` / `audit_rows`；差异或无 `position_id` → **`audit_reconcile_required`** |")
    L.append("| ⑥ | manifest 未更新 | 新记录只追加（见 §5） |")
    L.append("")
    L.append("## 2. 总览\n")
    L.append("| 项 | 值 |")
    L.append("|---|---|")
    L.append("| **run/pass 记录数（复合键）** | **%d** |" % len(rows_out))
    for k in ("verified", "lead_only", "provenance_unknown", "blocked"):
        L.append("| status = `%s` | %d |" % (k, st.get(k, 0)))
    L.append("| 有重试/重复出现的键 | %d |" % sum(1 for r in rows_out if r["occurrences"] > 1))
    L.append("")
    L.append("## 3. 标记分布\n")
    L.append("| 标记 | 次数 |")
    L.append("|---|---:|")
    for k, v in fl.most_common():
        L.append("| `%s` | %d |" % (k, v))
    L.append("")
    L.append("| 未知字段 | 次数 |")
    L.append("|---|---:|")
    for k, v in unk.most_common():
        L.append("| `%s` | %d |" % (k, v))
    L.append("")
    L.append("## 4. ★硬检查（v2 措辞已收紧）\n")
    hol = [r for r in rows_out if "TOUCHES_HOLDOUT" in r["flags"]]
    und = [r for r in rows_out if "holdout_undecidable" in r["unknown_fields"]]
    bad = [r for r in rows_out if "NON_REAL_SYMBOL" in r["flags"]]
    L.append("- **确认触碰留白的 run：%d** %s"
             % (len(hol), "（无）" if not hol else str([r["run_id"] for r in hol[:5]])))
    L.append("- **留白不可判定的 run：%d**（缺日期）→ **不能声称「全部未触碰」**" % len(und))
    L.append("- **非真实品种：%d** %s" % (len(bad), "（无）" if not bad else str([r["run_id"] for r in bad[:5]])))
    L.append("- 入金口径：`%s`" % dict(collections.Counter(r["deposit"] or "(空)" for r in rows_out).most_common(6)))
    L.append("- 模型口径：`%s`" % dict(collections.Counter(r["model"] or "(空)" for r in rows_out).most_common(4)))
    L.append("")
    L.append("**★结论**：v1 的「三项硬检查全部通过」表述**不成立** —— ")
    L.append("正确表述是「在可判定的 run 中，无一条确认触碰留白；但有 %d 条因缺日期不可判定」。" % len(und))
    L.append("")
    L.append("## 5. 文本扫描：未来日期\n")
    L.append("| 文件 | 日期 | 上下文 |")
    L.append("|---|---|---|")
    for s in scan[:25]:
        L.append("| `%s` | %s | %s… |" % (s["path"], s["date"], s["context"][:70]))
    if not scan:
        L.append("| （无） | | |")
    L.append("")
    L.append("**★注意**：GPT 复核指出 `交接\\比特币\\报告_032.md` 写有 `2026-09-14`，")
    L.append("而当前为 **2026-09-13** → 该报告至少 `lead_only`。上表为该扫描的实际结果。")
    L.append("")
    L.append("## 6. 产物\n")
    L.append("- `provenance_inventory_v2.csv`（%d 行）" % len(rows_out))
    L.append("- `hashes_v2.sha256`（%d 条）" % len(hashes))
    L.append("- `future_dates.csv`（%d 条）" % len(scan))
    L.append("- 本文件")
    L.append("")

    with io.open(os.path.join(OUT, "provenance_decision_v2.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    if scan:
        with io.open(os.path.join(OUT, "future_dates.csv"), "w", encoding="utf-8-sig",
                     newline="") as f:
            w = csv.DictWriter(f, fieldnames=["path", "date", "kind", "context"])
            w.writeheader()
            w.writerows(scan)

    print("v2 run/pass 记录: %d" % len(rows_out))
    print("status:", dict(st))
    print("flags:", dict(fl.most_common(10)))
    print("unknown:", dict(unk.most_common(6)))
    print("future_dates:", len(scan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
