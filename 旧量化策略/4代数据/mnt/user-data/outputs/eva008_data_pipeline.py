# -*- coding: utf-8 -*-
"""
eva008_data_pipeline.py  ——  PyCharm 直接运行版 (eva008 一代内, build v3.2)

相对 v3.1 的升级：
  (1) 全程**分阶段进度 + 进度条 + 预计剩余时间(ETA)**，不再只在节点报一次；
  (2) enrich 改为**按月分组、每个月文件只读一次** + **多进程并行**，大幅加速；
  (3) 新增配置项 N_WORKERS（进程数）、PROGRESS（进度条开关）。
功能口径与 v3.1/eva006 一致：slice / enrich / aggregate / request / cache。
行情仓库结构沿用 eva008 EA：eva_data/XAUUSDm/{ticks,m1,m5,m15}/YYYY-MM.csv + meta.json
"""

import os
import json
import glob
import time
import math
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count

# =====================================================================
#                          CONFIG —— 只改这里
# =====================================================================
MODE = "enrich"              # "enrich" | "aggregate" | "slice" | "request" | "cache"

ROOT   = "eva_data"
SYMBOL = "XAUUSDm"
OUTDIR = "enriched"

POINT        = None          # None=从 meta.json 自动；或写 0.001 强制
BIG_MOVE_USD = 3.0           # “大顺向/大不利”阈值（美元）；黄金 $3≈3000点

TRADES   = "eva_audit/run_xxx/eva_trade_events.csv"
PATH_TF  = "tick"            # 算 MFE/MAE 用的路径周期；tick 缺失自动回退 m1

# ---- v3.2 新增 ----
N_WORKERS = 0                # 0=自动(CPU核数-1)；1=单进程(调试用)；>1=指定进程数
PROGRESS  = True             # 是否显示进度条/ETA

# --- slice ---
SLICE_TF="m1"; SLICE_START="2024-03-05 13:00"; SLICE_END="2024-03-05 15:00"; SLICE_OUT="seg.csv"
# --- request ---
REQUEST_FILE="my_request.json"
# =====================================================================


def log(msg):
    print(f"[eva008] {msg}", flush=True)


# ---------------------------------------------------------------------
#  极简进度条（无 tqdm 依赖；若已装 tqdm 则自动使用）
# ---------------------------------------------------------------------
try:
    from tqdm import tqdm as _tqdm
    def progress_iter(it, total, desc):
        return _tqdm(it, total=total, desc=desc, ncols=80) if PROGRESS else it
except Exception:
    class _Bar:
        def __init__(self, total, desc):
            self.total = max(total, 1); self.desc = desc; self.n = 0; self.t0 = time.time()
        def update(self, k=1):
            self.n += k
            frac = self.n / self.total
            el = time.time() - self.t0
            eta = el / frac - el if frac > 0 else 0
            bar = ("#" * int(frac * 30)).ljust(30)
            print(f"\r[eva008] {self.desc} |{bar}| {self.n}/{self.total} "
                  f"ETA {eta:5.1f}s", end="", flush=True)
        def close(self):
            print(f"\r[eva008] {self.desc} |{'#'*30}| {self.n}/{self.total} "
                  f"用时 {time.time()-self.t0:5.1f}s", flush=True)
    def progress_iter(it, total, desc):
        if not PROGRESS:
            for x in it: yield x
            return
        bar = _Bar(total, desc)
        for x in it:
            yield x; bar.update(1)
        bar.close()


# ---------------------------------------------------------------------
#  meta / point / 路径工具
# ---------------------------------------------------------------------
def read_meta(root, symbol):
    p = os.path.join(root, symbol, "meta.json"); meta = {}
    if os.path.exists(p):
        try: meta = json.load(open(p, "r", encoding="utf-8"))
        except Exception as e: log(f"meta.json 读取失败({e})，用缺省")
    if not meta.get("point"): meta["point"] = 0.001
    return meta

def resolve_point(meta):
    return float(POINT) if POINT is not None else float(meta.get("point", 0.001))

def tf_name(tf):
    return "ticks" if tf in ("tick", "ticks") else tf

def tf_dir(root, symbol, tf):
    return os.path.join(root, symbol, tf_name(tf))

def months_between(t0, t1):
    out=[]; y,m=t0.year,t0.month
    while (y<t1.year) or (y==t1.year and m<=t1.month):
        out.append(f"{y:04d}-{m:02d}")
        m+=1
        if m>12: m=1; y+=1
    return out


def _load_month_arrays(base, tf, ym):
    """读取某月 CSV → 返回 (t_ms[int64], hi[float], lo[float])，按时间排序；缺失返回 None。"""
    path = os.path.join(base, f"{ym}.csv")
    if not os.path.exists(path): return None
    try: df = pd.read_csv(path)
    except Exception: return None
    if tf_name(tf) == "ticks":
        t = pd.to_numeric(df["time_msc"], errors="coerce")
        bid = pd.to_numeric(df.get("bid"), errors="coerce")
        ask = pd.to_numeric(df.get("ask"), errors="coerce")
        hi = np.maximum(bid, ask); lo = np.minimum(bid, ask)
    else:
        if "time_iso" in df.columns:
            t = (pd.to_datetime(df["time_iso"], errors="coerce").astype("int64")//10**6)
        else:
            t = pd.to_numeric(df["time"], errors="coerce")*1000
        hi = pd.to_numeric(df["high"], errors="coerce")
        lo = pd.to_numeric(df["low"], errors="coerce")
    m = pd.notna(t) & pd.notna(hi) & pd.notna(lo)
    t = np.asarray(t[m], dtype="int64"); hi = np.asarray(hi[m]); lo = np.asarray(lo[m])
    order = np.argsort(t, kind="mergesort")
    return t[order], hi[order], lo[order]


def _mfe_mae_from_arrays(arr, t0_ms, t1_ms, entry, direction):
    if arr is None: return np.nan, np.nan, False
    t, hi, lo = arr
    a = np.searchsorted(t, t0_ms, side="left")
    b = np.searchsorted(t, t1_ms, side="right")
    if b <= a: return np.nan, np.nan, True
    H = hi[a:b].max(); L = lo[a:b].min()
    if direction >= 0: mfe, mae = H-entry, entry-L
    else:              mfe, mae = entry-L, H-entry
    return float(mfe), float(mae), True


# ---------------------------------------------------------------------
#  多进程 worker：处理“某一入场月”的全部交易
# ---------------------------------------------------------------------
def _process_month(args):
    """args=(ym_label, trade_list, cfg)。trade_list: [(idx,t0_ms,t1_ms,ym_span,entry,dir)]"""
    ym_label, trades, cfg = args
    root, symbol, ptf = cfg["root"], cfg["symbol"], cfg["ptf"]
    base_p = tf_dir(root, symbol, ptf)
    base_m1 = tf_dir(root, symbol, "m1")
    cache_p, cache_m1 = {}, {}     # 每个进程内：每月只读一次
    res = []
    for idx, t0, t1, span, entry, d in trades:
        mfe = mae = np.nan; src = "none"; ok = False
        for ym in span:                       # 首选 path_tf
            if ym not in cache_p:
                cache_p[ym] = _load_month_arrays(base_p, ptf, ym)
            f, a, g = _mfe_mae_from_arrays(cache_p[ym], t0, t1, entry, d)
            if g:
                if not ok: mfe, mae = f, a; src = ptf; ok = True
                else:      mfe = np.nanmax([mfe, f]); mae = np.nanmax([mae, a])
        if not ok and ptf in ("tick", "ticks"):   # 回退 m1
            for ym in span:
                if ym not in cache_m1:
                    cache_m1[ym] = _load_month_arrays(base_m1, "m1", ym)
                f, a, g = _mfe_mae_from_arrays(cache_m1[ym], t0, t1, entry, d)
                if g:
                    if not ok: mfe, mae = f, a; src = "m1"; ok = True
                    else:      mfe = np.nanmax([mfe, f]); mae = np.nanmax([mae, a])
        res.append((idx, mfe, mae, src if ok else "none"))
    return res


# ---------------------------------------------------------------------
#  MODE = enrich
# ---------------------------------------------------------------------
def run_enrich():
    T = time.time()
    os.makedirs(OUTDIR, exist_ok=True)

    log("[阶段 1/5] 读取 meta.json + 交易表 …")
    meta = read_meta(ROOT, SYMBOL); point = resolve_point(meta); big = float(BIG_MOVE_USD)
    tr = pd.read_csv(TRADES)
    tr["entry_time"] = pd.to_datetime(tr["entry_time"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
    tr["exit_time"]  = pd.to_datetime(tr["exit_time"],  format="%Y.%m.%d %H:%M:%S", errors="coerce")
    log(f"           交易 {len(tr)} 笔 | point={point} | big=${big} | path_tf={PATH_TF}")

    log("[阶段 2/5] 按入场月分组（每月文件只读一次）…")
    groups = {}
    for idx, r in tr.iterrows():
        t0, t1 = r["entry_time"], r["exit_time"]
        if pd.isna(t0) or pd.isna(t1):
            continue
        ym = f"{t0.year:04d}-{t0.month:02d}"
        span = months_between(t0, t1)
        rec = (idx, int(t0.value//10**6), int(t1.value//10**6), span,
               float(r["entry_price"]), int(r["direction"]))
        groups.setdefault(ym, []).append(rec)
    cfg = {"root": ROOT, "symbol": SYMBOL, "ptf": PATH_TF}
    tasks = [(ym, recs, cfg) for ym, recs in sorted(groups.items())]
    log(f"           共 {len(tasks)} 个月分组")

    nw = (max(cpu_count()-1, 1) if N_WORKERS == 0 else int(N_WORKERS))
    log(f"[阶段 3/5] 计算 MFE/MAE（进程数={nw}）…")
    out = {}
    if nw <= 1:
        for t in progress_iter(tasks, len(tasks), "MFE/MAE(单进程)"):
            for idx, f, a, s in _process_month(t):
                out[idx] = (f, a, s)
    else:
        with Pool(nw) as pool:
            for chunk in progress_iter(pool.imap_unordered(_process_month, tasks),
                                       len(tasks), "MFE/MAE(多进程)"):
                for idx, f, a, s in chunk:
                    out[idx] = (f, a, s)

    log("[阶段 4/5] 组装 + 问题单分类 …")
    tr["mfe_usd"] = [out.get(i, (np.nan,)*3)[0] for i in tr.index]
    tr["mae_usd"] = [out.get(i, (np.nan,)*3)[1] for i in tr.index]
    tr["path_source"] = [out.get(i, (None, None, "none"))[2] for i in tr.index]
    tr["realized_move_usd"] = (tr["exit_price"] - tr["entry_price"]).abs()
    tr["capture_ratio"] = np.where(tr["mfe_usd"] > 0, tr["realized_move_usd"] / tr["mfe_usd"], np.nan)

    def classify(r):
        pnl, mfe, mae = r["net_pnl"], r["mfe_usd"], r["mae_usd"]
        if not (np.isfinite(mfe) and np.isfinite(mae)): return "no_path"
        if mae >= big: return "deep_underwater"
        if pnl < 0 and mfe >= big: return "gaveback_loss"
        if pnl > 0 and np.isfinite(r["capture_ratio"]) and r["capture_ratio"] < 0.3 and mfe >= big:
            return "early_exit"
        return "normal"
    tr["problem_tag"] = tr.apply(classify, axis=1)

    log("[阶段 5/5] 写出文件 …")
    tr.to_csv(os.path.join(OUTDIR, "trade_enriched.csv"), index=False)
    prob = tr[tr["problem_tag"].isin(["deep_underwater", "gaveback_loss", "early_exit"])]
    prob.to_csv(os.path.join(OUTDIR, "problem_trades.csv"), index=False)
    _write_aggregates(tr)
    log("问题单分布: " + ", ".join(f"{k}={v}" for k, v in tr["problem_tag"].value_counts().items()))
    log(f"全部完成，总用时 {time.time()-T:.1f}s。输出目录: {OUTDIR}/")
    return tr


# ---------------------------------------------------------------------
#  聚合
# ---------------------------------------------------------------------
def _agg(g):
    pnl = g["net_pnl"]; gp = pnl[pnl>0].sum(); gl = -pnl[pnl<0].sum()
    return pd.Series({"n": len(g), "net_pnl": pnl.sum(), "win_rate": (pnl>0).mean(),
                      "avg_pnl": pnl.mean(), "max_loss": pnl.min(),
                      "profit_factor": (gp/gl) if gl>0 else np.inf})

def _write_aggregates(tr):
    os.makedirs(OUTDIR, exist_ok=True); tr = tr.copy()
    if "entry_time" in tr.columns:
        tr["year"] = pd.to_datetime(tr["entry_time"], errors="coerce").dt.year
    tr.groupby(["order_kind","entry_reason"], dropna=False).apply(_agg).reset_index() \
      .to_csv(os.path.join(OUTDIR, "signal_performance.csv"), index=False)
    cols = [c for c in ["vol_regime","real_vol_regime","market_state","year"] if c in tr.columns]
    tr.groupby(cols, dropna=False).apply(_agg).reset_index() \
      .to_csv(os.path.join(OUTDIR, "regime_performance.csv"), index=False)
    log("写出 signal_performance.csv / regime_performance.csv")

def run_aggregate():
    src = os.path.join(OUTDIR, "trade_enriched.csv")
    if not os.path.exists(src): src = TRADES
    _write_aggregates(pd.read_csv(src))


# ---------------------------------------------------------------------
#  slice / request / cache
# ---------------------------------------------------------------------
def _load_path_df(root, symbol, tf, t0, t1):
    base = tf_dir(root, symbol, tf); frames=[]; mm = months_between(t0,t1)
    for ym in progress_iter(mm, len(mm), f"load {tf}"):
        arr = _load_month_arrays(base, tf, ym)
        if arr is not None:
            t,hi,lo = arr
            frames.append(pd.DataFrame({"t_ms":t,"hi":hi,"lo":lo}))
    if not frames: return None
    d = pd.concat(frames, ignore_index=True)
    d["time"] = pd.to_datetime(d["t_ms"], unit="ms")
    m = (d["time"]>=t0)&(d["time"]<=t1)
    return d.loc[m].reset_index(drop=True)

def run_slice():
    os.makedirs(OUTDIR, exist_ok=True)
    d = _load_path_df(ROOT, SYMBOL, SLICE_TF, pd.to_datetime(SLICE_START), pd.to_datetime(SLICE_END))
    if d is None or len(d)==0: log("该区间无数据。"); return
    out = os.path.join(OUTDIR, SLICE_OUT); d.to_csv(out, index=False)
    log(f"切片 → {out}（{len(d)} 行）")

def run_request():
    os.makedirs(OUTDIR, exist_ok=True)
    spec = json.load(open(REQUEST_FILE,"r",encoding="utf-8"))
    reqs = spec.get("requests", []); log(f"请求 {len(reqs)} 条")
    for i,q in enumerate(reqs):
        d = _load_path_df(ROOT,SYMBOL,q.get("timeframe","m1"),pd.to_datetime(q["start"]),pd.to_datetime(q["end"]))
        out = os.path.join(OUTDIR, q.get("out",f"req_{i}.csv"))
        if d is None or len(d)==0: log(f"  #{i} 无数据"); continue
        d.to_csv(out, index=False); log(f"  #{i} → {out}（{len(d)} 行）")

def run_cache():
    os.makedirs(OUTDIR, exist_ok=True)
    for tf in ["ticks","m1","m5","m15"]:
        files = sorted(glob.glob(os.path.join(tf_dir(ROOT,SYMBOL,tf),"*.csv")))
        if not files: continue
        frames=[pd.read_csv(fp) for fp in progress_iter(files,len(files),f"cache {tf}")]
        big = pd.concat(frames, ignore_index=True)
        dst = os.path.join(OUTDIR, f"cache_{tf}.parquet")
        try: big.to_parquet(dst, index=False)
        except Exception:
            dst = os.path.join(OUTDIR, f"cache_{tf}.csv"); big.to_csv(dst, index=False)
        log(f"缓存 {tf}: {len(files)} 月 → {dst}（{len(big)} 行）")


def main():
    log(f"MODE = {MODE}")
    {"enrich": run_enrich, "aggregate": run_aggregate, "slice": run_slice,
     "request": run_request, "cache": run_cache}.get(
        MODE, lambda: (_ for _ in ()).throw(ValueError(f"未知 MODE: {MODE}")))()


if __name__ == "__main__":
    main()
