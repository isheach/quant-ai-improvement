#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eva008_data_pipeline.py  （第3代/eva008；功能与 eva006 相同，仅按‘同代同编号’重新统一命名）
================================================================
行情数据流水线 / 交易诊断后处理（配合 eva005/eva008 行情仓库 + eva002 回测审计 CSV）

相对 eva003 的改动（详见 eva_DEVLOG.md / eva006 条目）：
  - 点值自动识别：优先读取 <root>/<symbol>/meta.json 里的 point（由 eva005 写）；
    没有 meta 时默认 0.001（黄金 3 位）。命令行 --point 仍可强制覆盖。
  - 黄金 3 位报价适配：MFE/MAE 的点数、R 倍数随 point 自动正确，不再写死 0.01。

它做三件事：
  1) slice    : 按周期(tick/m1/m5/m15) + 时间区间，切出一段行情并落盘。
  2) enrich   : 读取 eva002 的 eva_trade_events.csv，对每一笔单切出持仓期间
                的价格路径，计算 MFE/MAE/path_type/problem_tag，生成
                trade_enriched.csv 及若干汇总表。
  3) request  : 读取一个“数据请求文件”(eva004 JSON 格式)，按其中描述的若干
                请求(区间 / 某笔单路径 / 某时刻附近)批量输出数据。

数据仓库目录结构(由 eva001 生成)：
    <root>/XAUUSD/ticks/2024-01.csv
    <root>/XAUUSD/m1/2024-01.csv
    <root>/XAUUSD/m5/2024-01.csv
    <root>/XAUUSD/m15/2024-01.csv

依赖：pandas（必须）；pyarrow（可选，用于 parquet 缓存/输出）。
    pip install pandas pyarrow

时间约定：所有时间按“服务器时间”原样处理（与 MT5 导出一致），不做时区转换。
价格点值：黄金 2 位报价 point=0.01；3 位报价 point=0.001。用 --point 指定，
         默认 0.01。R 倍数仅在该单有止损价(sl_price>0)或显式给定 --default-r-pts
         时才计算。
================================================================
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

# ----------------------------------------------------------------------
# 常量与小工具
# ----------------------------------------------------------------------
TF_DIR = {"tick": "ticks", "ticks": "ticks", "m1": "m1", "m5": "m5", "m15": "m15"}
TICK_COLS = ["time_msc", "time_iso", "bid", "ask", "last",
             "volume", "volume_real", "flags", "spread_pts"]
BAR_COLS = ["time", "time_iso", "open", "high", "low", "close",
            "tick_volume", "spread", "real_volume"]


def log(*a):
    print("[eva008]", *a, file=sys.stderr)


def load_meta(root, symbol):
    """读取 eva005 写的 <root>/<symbol>/meta.json，返回 dict 或 {}。"""
    p = os.path.join(root, symbol, "meta.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as ex:
            log(f"读取 meta.json 失败: {ex}")
    return {}


def resolve_point(args):
    """点值解析优先级：命令行 --point(>0) > meta.json point > 默认 0.001。"""
    if getattr(args, "point", 0) and args.point > 0:
        return float(args.point)
    meta = load_meta(getattr(args, "root", "eva_data"), getattr(args, "symbol", "XAUUSD"))
    if meta.get("point"):
        log(f"point 来自 meta.json = {meta['point']}（digits={meta.get('output_digits')}）")
        return float(meta["point"])
    log("未找到 meta.json，point 采用默认 0.001（黄金3位）；如为2位请用 --point 0.01")
    return 0.001


def parse_dt(s):
    """容忍多种时间写法：'2024-03-05 14:00:00' / '2024.03.05 14:00' / epoch / ms。"""
    if isinstance(s, (int, float)):
        v = int(s)
        # 13 位视作毫秒，10 位视作秒
        if v > 10_000_000_000:
            return pd.Timestamp(v, unit="ms")
        return pd.Timestamp(v, unit="s")
    s = str(s).strip()
    if s.isdigit():
        return parse_dt(int(s))
    s2 = s.replace(".", "-", 2) if s[:4].isdigit() else s
    return pd.Timestamp(s2)


def month_range(start: pd.Timestamp, end: pd.Timestamp):
    """生成覆盖 [start, end] 的 (year, month) 列表。"""
    y, m = start.year, start.month
    out = []
    while (y < end.year) or (y == end.year and m <= end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1
    return out


# ----------------------------------------------------------------------
# 数据加载
# ----------------------------------------------------------------------
def _month_path(root, symbol, tf, y, m, ext="csv"):
    sub = TF_DIR[tf]
    return os.path.join(root, symbol, sub, f"{y:04d}-{m:02d}.{ext}")


def load_timeframe(root, symbol, tf, start, end, point=0.01):
    """
    加载 [start, end] 区间内某周期的数据，返回带 'ts'(pandas Timestamp) 的 DataFrame。
    自动拼接覆盖区间的 YYYY-MM 文件；优先读取 parquet 缓存(若存在)。
    """
    tf = tf.lower()
    if tf not in TF_DIR:
        raise ValueError(f"未知周期: {tf}")
    is_tick = TF_DIR[tf] == "ticks"

    frames = []
    for (y, m) in month_range(start, end):
        pq = _month_path(root, symbol, tf, y, m, "parquet")
        cs = _month_path(root, symbol, tf, y, m, "csv")
        if os.path.exists(pq):
            df = pd.read_parquet(pq)
        elif os.path.exists(cs):
            df = pd.read_csv(cs)
        else:
            continue
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    if is_tick:
        df["ts"] = pd.to_datetime(df["time_msc"], unit="ms")
    else:
        df["ts"] = pd.to_datetime(df["time"], unit="s")

    df = df[(df["ts"] >= start) & (df["ts"] <= end)].reset_index(drop=True)
    df.sort_values("ts", inplace=True, kind="mergesort")
    return df.reset_index(drop=True)


# ----------------------------------------------------------------------
# 子命令 1：slice
# ----------------------------------------------------------------------
def cmd_slice(args):
    args.point = resolve_point(args)
    start = parse_dt(args.start)
    end = parse_dt(args.end)
    df = load_timeframe(args.root, args.symbol, args.timeframe, start, end, args.point)
    if df.empty:
        log(f"无数据：{args.symbol} {args.timeframe} {start} ~ {end}")
        return
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    _write(df, args.out)
    log(f"slice 完成 {len(df)} 行 → {args.out}")


def _write(df, path):
    if path.lower().endswith(".parquet"):
        df.to_parquet(path, index=False)
    else:
        df.to_csv(path, index=False)


# ----------------------------------------------------------------------
# MFE / MAE / 路径分类
# ----------------------------------------------------------------------
def compute_path_metrics(path_df, direction, entry_price, point, is_tick):
    """
    返回 dict：mfe_pts, mae_pts, max_favorable_price, max_adverse_price, n_points
    direction: +1 多 / -1 空
    多单：用 bid(tick)/low,high(bar) 评估；空单：用 ask(tick)。
    """
    if path_df.empty:
        return dict(mfe_pts=0.0, mae_pts=0.0,
                    max_favorable_price=entry_price, max_adverse_price=entry_price,
                    n_points=0)

    if is_tick:
        if direction > 0:  # 多：顺向看 bid 最高，逆向看 bid 最低
            fav = path_df["bid"].max()
            adv = path_df["bid"].min()
        else:              # 空：顺向看 ask 最低，逆向看 ask 最高
            fav = path_df["ask"].min()
            adv = path_df["ask"].max()
    else:
        hi = path_df["high"].max()
        lo = path_df["low"].min()
        if direction > 0:
            fav, adv = hi, lo
        else:
            fav, adv = lo, hi

    mfe_pts = (fav - entry_price) / point * direction
    mae_pts = (entry_price - adv) / point * direction
    # 规范化：MFE>=0 表示曾顺向，MAE>=0 表示曾逆向
    mfe_pts = max(0.0, mfe_pts)
    mae_pts = max(0.0, mae_pts)
    return dict(mfe_pts=float(mfe_pts), mae_pts=float(mae_pts),
                max_favorable_price=float(fav), max_adverse_price=float(adv),
                n_points=int(len(path_df)))


def classify_path(net, mfe_pts, mae_pts, mfe_big_pts, immediate_k):
    """粗分类，阈值可调。"""
    win = net > 0
    if not win and mfe_pts < immediate_k * max(mae_pts, 1e-9) and mfe_pts < mfe_big_pts * 0.3:
        return "immediate_reverse"
    if mfe_pts >= mfe_big_pts and net <= 0:
        return "gave_back"
    if win and mae_pts < 0.3 * max(mfe_pts, 1e-9):
        return "clean_win"
    if win:
        return "grind_win"
    return "clean_loss"


STOP_REASONS = {"sl", "last_order_stop", "cutoff_line_stop",
                "overshoot_stop", "pacing_panic_stop", "risk3_cut_loss",
                "risk4_force_exit"}


def tag_problem(row, mfe_pts, mae_pts, path_type, mfe_big_pts):
    net = row.get("net_pnl", 0.0)
    exit_reason = str(row.get("exit_reason", ""))
    if path_type == "immediate_reverse":
        return "bad_entry"
    if path_type == "gave_back" or (mfe_pts >= mfe_big_pts and net <= 0):
        return "bad_exit"
    if net < 0 and exit_reason in STOP_REASONS:
        return "stopped_out"
    if net < 0:
        return "normal_loss"
    return "normal"


# ----------------------------------------------------------------------
# 子命令 2：enrich
# ----------------------------------------------------------------------
def _load_trade_events(path):
    df = pd.read_csv(path)
    df["entry_time"] = pd.to_datetime(df["entry_time"], errors="coerce")
    df["exit_time"] = pd.to_datetime(df["exit_time"], errors="coerce")
    if "entry_time_msc" in df:
        m = df["entry_time_msc"] > 0
        df.loc[m, "entry_time"] = pd.to_datetime(df.loc[m, "entry_time_msc"], unit="ms")
    if "exit_time_msc" in df:
        m = df["exit_time_msc"] > 0
        df.loc[m, "exit_time"] = pd.to_datetime(df.loc[m, "exit_time_msc"], unit="ms")
    return df


def cmd_enrich(args):
    te = _load_trade_events(args.trades)
    if te.empty:
        log("trade_events 为空")
        return

    symbol = args.symbol or (te["symbol"].iloc[0] if "symbol" in te else None)
    if not symbol:
        raise ValueError("无法确定 symbol，请用 --symbol 指定")

    args.symbol = symbol
    point = resolve_point(args)
    # “大顺向”阈值优先用价格(美元)表达，随 point 自动换算为点数，保证 2/3 位通用
    if getattr(args, "mfe_big_pts", 0) and args.mfe_big_pts > 0:
        mfe_big_pts = float(args.mfe_big_pts)
    else:
        mfe_big_pts = float(args.mfe_big_price) / point
    log(f"mfe_big 阈值 = {mfe_big_pts:.0f} 点 (≈{mfe_big_pts*point:.2f} 价格单位)")
    use_tf = args.path_tf.lower()
    is_tick = TF_DIR[use_tf] == "ticks"

    # 预加载覆盖所有交易的时间窗（一次性，避免逐单读盘）
    gmin = te["entry_time"].min() - timedelta(seconds=args.pre_seconds + 5)
    gmax = te["exit_time"].max() + timedelta(seconds=args.post_seconds + 5)
    log(f"加载路径数据 {symbol} {use_tf} {gmin} ~ {gmax} ...")
    market = load_timeframe(args.root, symbol, use_tf, gmin, gmax, point)
    fallback_used = False
    if market.empty and is_tick:
        log("tick 数据缺失，回退到 m1。")
        use_tf = "m1"; is_tick = False; fallback_used = True
        market = load_timeframe(args.root, symbol, "m1", gmin, gmax, point)
    if market.empty:
        log("路径数据为空，仅输出基础字段（不含 MFE/MAE）。")

    rows = []
    for _, r in te.iterrows():
        direction = int(r["direction"]) if str(r["direction"]).lstrip("-").isdigit() else (
            1 if str(r.get("direction", "")).lower().startswith("b") else -1)
        et, xt = r["entry_time"], r["exit_time"]
        entry_price = float(r["entry_price"])

        seg = market
        if not market.empty:
            seg = market[(market["ts"] >= et) & (market["ts"] <= xt)]

        metrics = compute_path_metrics(seg, direction, entry_price, point, is_tick) \
            if not market.empty else dict(mfe_pts=float("nan"), mae_pts=float("nan"),
                                          max_favorable_price=float("nan"),
                                          max_adverse_price=float("nan"), n_points=0)

        # R 倍数
        sl = float(r.get("sl_price", 0) or 0)
        r_pts = abs(entry_price - sl) / point if sl > 0 else (args.default_r_pts or float("nan"))
        mfe_r = metrics["mfe_pts"] / r_pts if r_pts and r_pts == r_pts else float("nan")
        mae_r = metrics["mae_pts"] / r_pts if r_pts and r_pts == r_pts else float("nan")

        ptype = classify_path(float(r.get("net_pnl", 0)), metrics["mfe_pts"] if metrics["mfe_pts"] == metrics["mfe_pts"] else 0,
                              metrics["mae_pts"] if metrics["mae_pts"] == metrics["mae_pts"] else 0,
                              mfe_big_pts, args.immediate_k) if not market.empty else ""
        ptag = tag_problem(r, metrics["mfe_pts"] if metrics["mfe_pts"] == metrics["mfe_pts"] else 0,
                           metrics["mae_pts"] if metrics["mae_pts"] == metrics["mae_pts"] else 0,
                           ptype, mfe_big_pts) if not market.empty else ""

        rows.append({
            "position_id": r.get("position_id"),
            "signal_id": r.get("entry_reason"),
            "order_kind": r.get("order_kind"),
            "direction": direction,
            "entry_time": et, "exit_time": xt,
            "holding_seconds": r.get("holding_seconds"),
            "entry_price": entry_price, "exit_price": r.get("exit_price"),
            "net_pnl": r.get("net_pnl"), "profit": r.get("profit"),
            "r_pts": r_pts,
            "mfe_pts": metrics["mfe_pts"], "mae_pts": metrics["mae_pts"],
            "mfe_r": mfe_r, "mae_r": mae_r,
            "max_favorable_price": metrics["max_favorable_price"],
            "max_adverse_price": metrics["max_adverse_price"],
            "path_type": ptype, "problem_tag": ptag,
            "exit_reason": r.get("exit_reason"),
            "vol_regime": r.get("vol_regime"), "market_state": r.get("market_state"),
            "rv_ratio": r.get("rv_ratio"), "multiplier_a": r.get("multiplier_a"),
            "order_number": r.get("order_number"),
            "spread_pts_at_entry": r.get("spread_pts_at_entry"),
            "path_source": ("none" if market.empty else use_tf),
        })

    enr = pd.DataFrame(rows)
    os.makedirs(args.outdir, exist_ok=True)
    p_enr = os.path.join(args.outdir, "trade_enriched.csv")
    enr.to_csv(p_enr, index=False)
    log(f"trade_enriched 写出 {len(enr)} 行 → {p_enr}")

    # 问题单
    prob = enr[~enr["problem_tag"].isin(["normal", ""])]
    prob.to_csv(os.path.join(args.outdir, "problem_trades.csv"), index=False)

    # 信号表现：按 signal_id × vol_regime × market_state 聚合
    if not enr.empty:
        _agg(enr, ["signal_id", "vol_regime", "market_state"],
             os.path.join(args.outdir, "signal_performance.csv"))
        _agg(enr, ["vol_regime", "market_state"],
             os.path.join(args.outdir, "regime_performance.csv"))
    log(f"问题单 {len(prob)} 笔；汇总表已生成于 {args.outdir}")


def _agg(df, keys, out):
    g = df.groupby(keys, dropna=False)
    res = g.agg(
        n=("net_pnl", "size"),
        wins=("net_pnl", lambda s: (pd.to_numeric(s, errors="coerce") > 0).sum()),
        net_sum=("net_pnl", lambda s: pd.to_numeric(s, errors="coerce").sum()),
        gross_profit=("net_pnl", lambda s: pd.to_numeric(s, errors="coerce").clip(lower=0).sum()),
        gross_loss=("net_pnl", lambda s: (-pd.to_numeric(s, errors="coerce").clip(upper=0)).sum()),
        avg_mfe=("mfe_pts", "mean"),
        avg_mae=("mae_pts", "mean"),
        avg_hold_s=("holding_seconds", lambda s: pd.to_numeric(s, errors="coerce").mean()),
    ).reset_index()
    res["winrate"] = (res["wins"] / res["n"]).round(3)
    res["profit_factor"] = (res["gross_profit"] /
                            res["gross_loss"].replace(0, float("nan"))).round(3)
    res.to_csv(out, index=False)


# ----------------------------------------------------------------------
# 子命令 3：request（读取 eva004 JSON 请求文件）
# ----------------------------------------------------------------------
def cmd_request(args):
    with open(args.file, "r", encoding="utf-8") as f:
        req = json.load(f)

    root = args.root or req.get("data_root")
    symbol = args.symbol or req.get("symbol")
    args.root, args.symbol = root, symbol
    if req.get("point"):
        point = float(req["point"])
    else:
        point = resolve_point(args)
    default_tf = req.get("default_timeframe", "tick")
    outdir = args.outdir or req.get("outdir") or "eva_request_out"
    os.makedirs(outdir, exist_ok=True)

    trades = None
    if req.get("trade_events"):
        trades = _load_trade_events(req["trade_events"])
    elif args.trades:
        trades = _load_trade_events(args.trades)

    manifest = {"request_id": req.get("request_id"), "symbol": symbol, "outputs": []}

    for i, o in enumerate(req.get("outputs", [])):
        name = o.get("name") or f"out_{i:03d}"
        tf = (o.get("timeframe") or default_tf).lower()
        otype = o.get("type")
        try:
            if otype == "range":
                start, end = parse_dt(o["from"]), parse_dt(o["to"])
                df = load_timeframe(root, symbol, tf, start, end, point)
                _emit(df, outdir, name, manifest, dict(type=otype, tf=tf,
                      **{"from": str(start), "to": str(end)}))

            elif otype == "around_time":
                c = parse_dt(o["center"])
                start = c - timedelta(seconds=int(o.get("pre_seconds", 300)))
                end = c + timedelta(seconds=int(o.get("post_seconds", 300)))
                df = load_timeframe(root, symbol, tf, start, end, point)
                _emit(df, outdir, name, manifest, dict(type=otype, tf=tf,
                      center=str(c), **{"from": str(start), "to": str(end)}))

            elif otype == "trade_path":
                if trades is None:
                    raise ValueError("trade_path 需要 trade_events（请在请求文件里给 trade_events 或用 --trades）")
                sub = _select_trades(trades, o)
                pre = int(o.get("pre_seconds", 0))
                post = int(o.get("post_seconds", 0))
                wrote = 0
                lim = int(o.get("limit", 20))
                for _, tr in sub.head(lim).iterrows():
                    s = pd.to_datetime(tr["entry_time"]) - timedelta(seconds=pre)
                    e = pd.to_datetime(tr["exit_time"]) + timedelta(seconds=post)
                    df = load_timeframe(root, symbol, tf, s, e, point)
                    fn = f"{name}_pos{tr['position_id']}"
                    _emit(df, outdir, fn, manifest, dict(type=otype, tf=tf,
                          position_id=int(tr["position_id"]),
                          entry_time=str(tr["entry_time"]), exit_time=str(tr["exit_time"])))
                    wrote += 1
                log(f"{name}: 输出 {wrote} 笔单路径")
            else:
                log(f"跳过未知 output type: {otype}")
        except Exception as ex:
            log(f"output {name} 失败: {ex}")
            manifest["outputs"].append(dict(name=name, error=str(ex)))

    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
    log(f"request 完成，清单 → {os.path.join(outdir, 'manifest.json')}")


def _select_trades(trades, o):
    sub = trades
    if "position_id" in o:
        ids = o["position_id"] if isinstance(o["position_id"], list) else [o["position_id"]]
        sub = sub[sub["position_id"].isin(ids)]
    for k, v in (o.get("filter") or {}).items():
        if k in sub.columns:
            vals = v if isinstance(v, list) else [v]
            sub = sub[sub[k].astype(str).isin([str(x) for x in vals])]
    if o.get("only_problem"):
        pass  # trade_events 不含 problem_tag；如需按问题单筛选请先 enrich 再喂 enriched
    return sub


def _emit(df, outdir, name, manifest, meta):
    if df is None or df.empty:
        manifest["outputs"].append(dict(name=name, rows=0, note="empty", **meta))
        log(f"{name}: 空")
        return
    path = os.path.join(outdir, f"{name}.csv")
    df.to_csv(path, index=False)
    manifest["outputs"].append(dict(name=name, rows=int(len(df)), file=os.path.basename(path), **meta))
    log(f"{name}: {len(df)} 行 → {path}")


# ----------------------------------------------------------------------
# 子命令 4：cache（CSV → parquet，加速后续读取，可选）
# ----------------------------------------------------------------------
def cmd_cache(args):
    n = 0
    for cs in glob.glob(os.path.join(args.root, args.symbol, "**", "*.csv"), recursive=True):
        pq = cs[:-4] + ".parquet"
        if os.path.exists(pq) and not args.force:
            continue
        try:
            pd.read_csv(cs).to_parquet(pq, index=False)
            n += 1
        except Exception as ex:
            log(f"缓存失败 {cs}: {ex}")
    log(f"cache 完成，转换 {n} 个文件。")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(description="eva003 行情/交易数据流水线")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--root", default="eva_data", help="行情仓库根目录(eva001 输出)")
        sp.add_argument("--symbol", default="XAUUSD")
        sp.add_argument("--point", type=float, default=0.0,
                        help="每点价格；0=自动(读 meta.json，缺省0.001/黄金3位)。2位=0.01,3位=0.001")

    s = sub.add_parser("slice", help="切出某周期某区间的行情")
    common(s)
    s.add_argument("--timeframe", required=True, choices=list(TF_DIR.keys()))
    s.add_argument("--start", required=True)
    s.add_argument("--end", required=True)
    s.add_argument("--out", required=True, help="输出文件(.csv 或 .parquet)")
    s.set_defaults(func=cmd_slice)

    e = sub.add_parser("enrich", help="对回测交易做 MFE/MAE/问题单诊断")
    common(e)
    e.add_argument("--trades", required=True, help="eva_trade_events.csv 路径")
    e.add_argument("--outdir", default="eva_enriched")
    e.add_argument("--path-tf", default="tick", choices=list(TF_DIR.keys()),
                   help="计算路径用的周期(默认 tick，缺失自动回退 m1)")
    e.add_argument("--pre-seconds", type=int, default=0)
    e.add_argument("--post-seconds", type=int, default=0)
    e.add_argument("--default-r-pts", type=float, default=0.0,
                   help="无止损单的 R 基准点数(0=不算 R)")
    e.add_argument("--mfe-big-price", type=float, default=3.0,
                   help="判定'吃到大顺向后回吐'的 MFE 阈值(价格单位/美元)，随 point 自动换算为点数")
    e.add_argument("--mfe-big-pts", type=float, default=0.0,
                   help="同上但直接给点数；>0 时覆盖 --mfe-big-price")
    e.add_argument("--immediate-k", type=float, default=0.25,
                   help="判定'开仓即反向'的 MFE/MAE 比例阈值")
    e.set_defaults(func=cmd_enrich)

    r = sub.add_parser("request", help="按 eva004 JSON 请求文件批量输出数据")
    common(r)
    r.add_argument("--file", required=True, help="请求 JSON 文件(eva004 格式)")
    r.add_argument("--trades", default=None, help="trade_events.csv(供 trade_path 用)")
    r.add_argument("--outdir", default=None)
    r.set_defaults(func=cmd_request)

    c = sub.add_parser("cache", help="把 CSV 月文件转 parquet 缓存(加速)")
    c.add_argument("--root", default="eva_data")
    c.add_argument("--symbol", default="XAUUSD")
    c.add_argument("--force", action="store_true")
    c.set_defaults(func=cmd_cache)

    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
