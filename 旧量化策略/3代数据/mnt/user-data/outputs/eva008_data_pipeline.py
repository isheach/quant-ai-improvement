# -*- coding: utf-8 -*-
"""
eva008_data_pipeline.py  ——  PyCharm 直接运行版 (eva008 一代内的修订, build v3.1)

与上一版（命令行 argparse 版 = eva006/eva008）功能完全一致：
    切片(slice) / 交易增强(enrich, 含 MFE·MAE·问题单) / 聚合(aggregate) /
    按请求文件出数(request) / 缓存(cache)。
唯一区别：**不再用命令行参数**。所有参数集中在下面的 CONFIG 区，
在 PyCharm 里改好 MODE 和对应参数，直接点绿色三角 Run 即可。

点值 point 自动从 meta.json 读取（缺省 0.001）；“大顺向”阈值按价格(美元)判定，
2/3 位通用。行情仓库结构沿用 eva008 EA 导出：
    eva_data/XAUUSDm/{ticks,m1,m5,m15}/YYYY-MM.csv  + meta.json
"""

import os
import json
import glob
import math
import pandas as pd
import numpy as np

# =====================================================================
#                          CONFIG —— 只改这里
# =====================================================================
# 选择要跑的模式： "enrich" | "aggregate" | "slice" | "request" | "cache"
MODE = "enrich"

# --- 公共路径 ---
ROOT   = "eva_data"          # 行情仓库根目录（里面是 <SYMBOL>/{ticks,m1,m5,m15}）
SYMBOL = "XAUUSDm"
OUTDIR = "enriched"          # 输出目录（自动创建）

# --- 点值与阈值（一般不用改）---
POINT        = None          # None=从 meta.json 自动读取；或写 0.001 强制覆盖
BIG_MOVE_USD = 3.0           # “大顺向/大不利”阈值，单位=美元（黄金 $3 ≈ 3000 点）

# --- enrich / aggregate 用 ---
TRADES   = "eva_audit/run_xxx/eva_trade_events.csv"   # 可审计回测产出的交易事件表
PATH_TF  = "tick"            # 算 MFE/MAE 用哪个周期的路径："tick" 缺失时自动回退 "m1"

# --- slice 用（手动切一段行情看）---
SLICE_TF    = "m1"
SLICE_START = "2024-03-05 13:00"
SLICE_END   = "2024-03-05 15:00"
SLICE_OUT   = "seg.csv"

# --- request 用（请求文件二次取数）---
REQUEST_FILE = "my_request.json"
# =====================================================================


# ---------------------------------------------------------------------
#  基础工具
# ---------------------------------------------------------------------
def log(msg):
    print(f"[eva008] {msg}")


def read_meta(root, symbol):
    """读取 meta.json，返回 point 等信息；缺失则给出安全缺省。"""
    meta_path = os.path.join(root, symbol, "meta.json")
    meta = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            log(f"meta.json 读取失败({e})，使用缺省值")
    if "point" not in meta or not meta.get("point"):
        meta["point"] = 0.001
    return meta


def resolve_point(meta):
    if POINT is not None:
        return float(POINT)
    return float(meta.get("point", 0.001))


def tf_dir(root, symbol, tf):
    # 兼容 "tick"/"ticks"
    name = "ticks" if tf in ("tick", "ticks") else tf
    return os.path.join(root, symbol, name)


def months_between(t0, t1):
    """返回 [t0, t1] 跨越的 YYYY-MM 列表。"""
    out = []
    y, m = t0.year, t0.month
    while (y < t1.year) or (y == t1.year and m <= t1.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _read_month_csv(path):
    if not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path)
    except Exception as e:
        log(f"读取 {path} 失败: {e}")
        return None


def load_path(root, symbol, tf, t_start, t_end):
    """加载 [t_start, t_end] 区间的行情，返回统一列：time(datetime), price(中间价/收盘价)。
    tick 用 (bid+ask)/2；bar 用 close，同时保留 high/low 以便取极值。"""
    name = "ticks" if tf in ("tick", "ticks") else tf
    base = tf_dir(root, symbol, tf)
    frames = []
    for ym in months_between(t_start, t_end):
        df = _read_month_csv(os.path.join(base, f"{ym}.csv"))
        if df is not None and len(df):
            frames.append(df)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)

    if name == "ticks":
        # 列: time_msc,time_iso,bid,ask,last,...
        df["time"] = pd.to_datetime(df["time_msc"], unit="ms")
        bid = pd.to_numeric(df.get("bid"), errors="coerce")
        ask = pd.to_numeric(df.get("ask"), errors="coerce")
        df["price"] = (bid + ask) / 2.0
        df["hi"] = df[["bid", "ask"]].max(axis=1)
        df["lo"] = df[["bid", "ask"]].min(axis=1)
    else:
        # 列: time,time_iso,open,high,low,close,...
        if "time_iso" in df.columns:
            df["time"] = pd.to_datetime(df["time_iso"])
        else:
            df["time"] = pd.to_datetime(df["time"], unit="s")
        df["price"] = pd.to_numeric(df["close"], errors="coerce")
        df["hi"] = pd.to_numeric(df["high"], errors="coerce")
        df["lo"] = pd.to_numeric(df["low"], errors="coerce")

    df = df.dropna(subset=["time", "price"]).sort_values("time").reset_index(drop=True)
    m = (df["time"] >= t_start) & (df["time"] <= t_end)
    return df.loc[m, ["time", "price", "hi", "lo"]].reset_index(drop=True)


# ---------------------------------------------------------------------
#  MODE = enrich   逐笔交易增强：MFE / MAE / 问题单分类
# ---------------------------------------------------------------------
def parse_trade_times(tr):
    tr = tr.copy()
    tr["entry_time"] = pd.to_datetime(tr["entry_time"], format="%Y.%m.%d %H:%M:%S", errors="coerce")
    tr["exit_time"]  = pd.to_datetime(tr["exit_time"],  format="%Y.%m.%d %H:%M:%S", errors="coerce")
    return tr


def compute_mfe_mae(path, entry_price, direction):
    """direction: 1=多, -1=空。返回 (mfe_usd, mae_usd)。
    多: 顺向=价格上行；不利=下行。空相反。"""
    if path is None or len(path) == 0 or not np.isfinite(entry_price):
        return np.nan, np.nan
    hi = path["hi"].max()
    lo = path["lo"].min()
    if direction >= 0:
        mfe = hi - entry_price
        mae = entry_price - lo
    else:
        mfe = entry_price - lo
        mae = hi - entry_price
    return float(mfe), float(mae)


def run_enrich():
    os.makedirs(OUTDIR, exist_ok=True)
    meta = read_meta(ROOT, SYMBOL)
    point = resolve_point(meta)
    big = float(BIG_MOVE_USD)
    log(f"point={point}  big_move=${big}  path_tf={PATH_TF}")

    tr = parse_trade_times(pd.read_csv(TRADES))
    log(f"载入交易 {len(tr)} 笔；逐笔切路径并计算 MFE/MAE …")

    mfes, maes, srcs = [], [], []
    for i, r in tr.iterrows():
        t0, t1 = r["entry_time"], r["exit_time"]
        ep = float(r["entry_price"])
        d = int(r["direction"])
        src = PATH_TF
        path = None
        if pd.notna(t0) and pd.notna(t1):
            path = load_path(ROOT, SYMBOL, PATH_TF, t0, t1)
            if (path is None or len(path) == 0) and PATH_TF in ("tick", "ticks"):
                path = load_path(ROOT, SYMBOL, "m1", t0, t1)   # tick 缺失自动回退 m1
                src = "m1"
        mfe, mae = compute_mfe_mae(path, ep, d)
        mfes.append(mfe); maes.append(mae); srcs.append(src if path is not None else "none")
        if (i + 1) % 200 == 0:
            log(f"  进度 {i+1}/{len(tr)}")

    tr["mfe_usd"] = mfes
    tr["mae_usd"] = maes
    tr["path_source"] = srcs
    # 实现盈亏对应的价格行程（美元）：用 |exit-entry|
    tr["realized_move_usd"] = (tr["exit_price"] - tr["entry_price"]).abs()
    # 顺向兑现率：实际拿到的 / 最大可拿到的
    tr["capture_ratio"] = np.where(tr["mfe_usd"] > 0, tr["realized_move_usd"] / tr["mfe_usd"], np.nan)

    # ---- 问题单分类（互斥优先级）----
    def classify(r):
        pnl = r["net_pnl"]; mfe = r["mfe_usd"]; mae = r["mae_usd"]
        if not np.isfinite(mfe) or not np.isfinite(mae):
            return "no_path"
        # 1) 深度浮亏（马丁危险）：不利行程很大，即便最后没亏
        if mae >= big:
            tag = "deep_underwater"
        # 2) 大顺向却亏损：本该赚却亏（出场逻辑/方向问题）
        elif pnl < 0 and mfe >= big:
            return "gaveback_loss"
        # 3) 顺向到位却兑现很少（提前跑/TP 太近）
        elif pnl > 0 and np.isfinite(r["capture_ratio"]) and r["capture_ratio"] < 0.3 and mfe >= big:
            return "early_exit"
        else:
            return "normal"
        return tag

    tr["problem_tag"] = tr.apply(classify, axis=1)

    out_all = os.path.join(OUTDIR, "trade_enriched.csv")
    tr.to_csv(out_all, index=False)
    prob = tr[tr["problem_tag"].isin(["deep_underwater", "gaveback_loss", "early_exit"])]
    out_prob = os.path.join(OUTDIR, "problem_trades.csv")
    prob.to_csv(out_prob, index=False)

    log(f"写出 {out_all}（{len(tr)} 行）")
    log(f"写出 {out_prob}（问题单 {len(prob)} 行）")
    log("问题单分布: " + ", ".join(f"{k}={v}" for k, v in tr["problem_tag"].value_counts().items()))

    # 顺带产出聚合表
    _write_aggregates(tr)
    return tr


# ---------------------------------------------------------------------
#  聚合表：signal_performance / regime_performance
# ---------------------------------------------------------------------
def _agg(g):
    pnl = g["net_pnl"]
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return pd.Series({
        "n": len(g),
        "net_pnl": pnl.sum(),
        "win_rate": (pnl > 0).mean(),
        "avg_pnl": pnl.mean(),
        "max_loss": pnl.min(),
        "profit_factor": (gp / gl) if gl > 0 else np.inf,
    })


def _write_aggregates(tr):
    os.makedirs(OUTDIR, exist_ok=True)
    if "entry_time" in tr.columns:
        tr = tr.copy()
        tr["year"] = pd.to_datetime(tr["entry_time"], errors="coerce").dt.year

    sig = tr.groupby(["order_kind", "entry_reason"], dropna=False).apply(_agg).reset_index()
    sig.to_csv(os.path.join(OUTDIR, "signal_performance.csv"), index=False)

    cols = [c for c in ["vol_regime", "real_vol_regime", "market_state", "year"] if c in tr.columns]
    reg = tr.groupby(cols, dropna=False).apply(_agg).reset_index()
    reg.to_csv(os.path.join(OUTDIR, "regime_performance.csv"), index=False)
    log(f"写出 signal_performance.csv / regime_performance.csv")


def run_aggregate():
    """对已有的 trade_enriched.csv（或原始 trade_events）单独跑聚合。"""
    src = os.path.join(OUTDIR, "trade_enriched.csv")
    if not os.path.exists(src):
        src = TRADES
    tr = pd.read_csv(src)
    _write_aggregates(tr)
    return tr


# ---------------------------------------------------------------------
#  MODE = slice
# ---------------------------------------------------------------------
def run_slice():
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = pd.to_datetime(SLICE_START)
    t1 = pd.to_datetime(SLICE_END)
    path = load_path(ROOT, SYMBOL, SLICE_TF, t0, t1)
    out = os.path.join(OUTDIR, SLICE_OUT)
    if path is None or len(path) == 0:
        log("该区间无数据。")
        return None
    path.to_csv(out, index=False)
    log(f"切片 {SLICE_TF} {SLICE_START}~{SLICE_END} → {out}（{len(path)} 行）")
    return path


# ---------------------------------------------------------------------
#  MODE = request   （请求文件二次取数）
#  请求文件格式（与 eva008 json 一致）：
#  {"requests":[{"timeframe":"m1","start":"2024-03-05 13:00","end":"2024-03-05 15:00","out":"seg1.csv"}]}
#  point 可省略（自动识别）。
# ---------------------------------------------------------------------
def run_request():
    os.makedirs(OUTDIR, exist_ok=True)
    with open(REQUEST_FILE, "r", encoding="utf-8") as f:
        spec = json.load(f)
    reqs = spec.get("requests", [])
    log(f"请求文件 {REQUEST_FILE}：{len(reqs)} 条")
    for i, q in enumerate(reqs):
        tf = q.get("timeframe", "m1")
        t0 = pd.to_datetime(q["start"]); t1 = pd.to_datetime(q["end"])
        out = q.get("out", f"req_{i}.csv")
        path = load_path(ROOT, SYMBOL, tf, t0, t1)
        dst = os.path.join(OUTDIR, out)
        if path is None or len(path) == 0:
            log(f"  #{i} 无数据：{tf} {t0}~{t1}")
            continue
        path.to_csv(dst, index=False)
        log(f"  #{i} {tf} {t0}~{t1} → {dst}（{len(path)} 行）")


# ---------------------------------------------------------------------
#  MODE = cache   （把每个周期所有月份拼成单一 parquet/csv，加速后续）
# ---------------------------------------------------------------------
def run_cache():
    os.makedirs(OUTDIR, exist_ok=True)
    for tf in ["ticks", "m1", "m5", "m15"]:
        base = tf_dir(ROOT, SYMBOL, tf)
        files = sorted(glob.glob(os.path.join(base, "*.csv")))
        if not files:
            continue
        frames = [pd.read_csv(fp) for fp in files]
        big = pd.concat(frames, ignore_index=True)
        dst = os.path.join(OUTDIR, f"cache_{tf}.parquet")
        try:
            big.to_parquet(dst, index=False)
        except Exception:
            dst = os.path.join(OUTDIR, f"cache_{tf}.csv")
            big.to_csv(dst, index=False)
        log(f"缓存 {tf}: {len(files)} 月 → {dst}（{len(big)} 行）")


# ---------------------------------------------------------------------
#  入口分发
# ---------------------------------------------------------------------
def main():
    log(f"MODE = {MODE}")
    if MODE == "enrich":
        run_enrich()
    elif MODE == "aggregate":
        run_aggregate()
    elif MODE == "slice":
        run_slice()
    elif MODE == "request":
        run_request()
    elif MODE == "cache":
        run_cache()
    else:
        raise ValueError(f"未知 MODE: {MODE}（可选 enrich/aggregate/slice/request/cache）")
    log("完成。")


if __name__ == "__main__":
    main()
