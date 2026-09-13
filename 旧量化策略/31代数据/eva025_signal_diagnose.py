# -*- coding: utf-8 -*-
"""
eva025_signal_diagnose.py  ——  eva025a 新机制"反事实价值"诊断脚本
=================================================================
目的（回答一个 enrich 表本身回答不了的问题）：
    eva025a 的三个新机制（MTF 多周期确认 / ADX 强度 / EMA 间距）在本轮寻参里
    被优化器架空了（MTF=关、MinADX=10~15、EMASep=0.1~0.2）。所以"新机制是否
    真的能提高趋势判断精度"这个核心假设【还没被真正验证】。
    本脚本用你的【原始 m1 行情】离线重算这些指标，落到每一笔"趋势单/砍单"的
    入场时刻，从而在【不重跑 EA】的前提下回答：
        "如果当初真的要求 ADX≥25 / 要求 MTF 同向，会滤掉哪些信号？
         被滤掉的那批到底是该留（本来会赚）还是该滤（本来会亏）？"

方法学要点（务必理解，避免误读）：
    - 砍单(cut)自身的 net_pnl 是"砍掉那一刻网格的已实现盈亏"，不砍会怎样无法从
      成交表直接知道 → 所以【不能】直接用砍单评估"滤掉某个砍是好是坏"。
    - 但趋势单(trend)的结果是明确的：入场后自己走完盈亏。而【砍单与趋势单同信号
      同刻触发】(见 DEVLOG：状态切换瞬间既砍逆势网格又开同向趋势单)，因此
      【趋势单的对错 = 砍单的对错】。所以本脚本用【趋势单】的结果做反事实评估，
      结论可直接外推到砍单准确率。
    - 只用【已收盘】bar 的指标（shift 一根），不引入未来函数。

输入（需要你补一份原始行情；enrich 表你已有）：
    1) TRADE_CSV : 某一组的 enrich_eva025.aX/trade_enriched.csv
    2) M1_CSV    : XAUUSDm 的 1 分钟 OHLC（就是 eva_data/XAUUSDm/ 里的 m1）。
                   支持两种常见格式，脚本自动识别列名（见 _load_m1）。
                   若你的 m1 是别的列名/分隔符，改 _load_m1 里的映射即可。

不带 M1 也能跑：只做 enrich 侧的分段 + 三分类 + 尾部（相当于把我这轮的分析
    做成可复用工具，方便你直接套到"全参寻参"的新结果上）。

用法：
    python eva025_signal_diagnose.py --trade enrich_eva025.a2/trade_enriched.csv \
                                     --m1 eva_data/XAUUSDm/m1.csv
    # 不带 --m1 就是纯 enrich 分析
"""

import argparse
import sys
import numpy as np
import pandas as pd

# ============ 与 EA 对齐的指标参数（改这里即可匹配你的 .set）============
TREND_TF_MIN   = 5     # 趋势周期 = M5
FAST_EMA       = 20    # 趋势快 EMA
SLOW_EMA       = 60    # 趋势慢 EMA
ADX_PERIOD     = 14    # ADX 周期（EA 里 InpADXPeriod，寻参用了 13/17，可改）
MTF_TF_MIN     = 15    # 多周期确认 = M15
MTF_FAST_EMA   = 20
MTF_SLOW_EMA   = 60
ATR_PERIOD     = 14    # 趋势 ATR（用于 EMA 间距归一）

# 训练/验证/测试切分（与你本轮一致）
SPLITS = [
    ("训练 25.01-26.02", "2025-01-01", "2026-02-01"),
    ("验证 26.02-26.05", "2026-02-01", "2026-05-01"),
    ("测试 26.05+(真OOS)", "2026-05-01", "2027-06-01"),
]

# 砍单标签（新旧兼容）：grid 且因趋势被平
CUT_REASONS_NEW = {"trend_close_opposite_grid"}
CUT_REASONS_OLD = {"trend_state_exit"}   # 旧数据里 grid 的 trend_state_exit 才是砍单


# ---------------------------------------------------------------- enrich 侧
def _load_trades(path):
    df = pd.read_csv(path)
    df["entry_time"] = pd.to_datetime(df["entry_time"], errors="coerce")
    df["exit_time"]  = pd.to_datetime(df["exit_time"], errors="coerce")
    return df


def _is_cut(df):
    """grid 且因趋势被砍。新数据用 trend_close_opposite_grid；旧数据用 grid 的 trend_state_exit。"""
    grid = df["order_kind"] == "grid"
    if (df["exit_reason"] == "trend_close_opposite_grid").any():
        return grid & df["exit_reason"].isin(CUT_REASONS_NEW)
    return grid & df["exit_reason"].isin(CUT_REASONS_OLD)


def _bucket(df, name):
    p = df["net_pnl"]
    if len(p) == 0:
        return f"{name:8}  n=0"
    gp = p[p > 0].sum(); gl = -p[p < 0].sum()
    pf = gp / gl if gl > 0 else float("inf")
    return (f"{name:8}  净利 {p.sum():+9.1f} | 笔数 {len(p):5d} | 胜率 {(p>0).mean()*100:5.1f}% "
            f"| 单均 {p.mean():+7.3f} | PF {pf:5.2f}")


def print_enrich_report(df):
    print("=" * 78)
    print("【enrich 侧分析】", df["param_set_id"].iloc[0] if "param_set_id" in df else "")
    print("=" * 78)
    # 分段
    print("\n-- 分段表现（净利/笔数/胜率）--")
    for label, a, b in SPLITS:
        m = (df["entry_time"] >= a) & (df["entry_time"] < b)
        s = df.loc[m, "net_pnl"]
        if len(s):
            print(f"  {label:20} {s.sum():+8.0f} / {len(s):5d} / {(s>0).mean()*100:4.1f}%")
    p = df["net_pnl"]; gp = p[p > 0].sum(); gl = -p[p < 0].sum()
    print(f"  {'全程':20} {p.sum():+8.0f} / {len(p):5d} / {(p>0).mean()*100:4.1f}%   PF={gp/gl:.3f}")
    # 三分类
    print("\n-- 三分类 --")
    cut = _is_cut(df)
    grid = (df["order_kind"] == "grid") & (~cut)
    trend = df["order_kind"] == "trend"
    print("  " + _bucket(df[grid], "网格"))
    print("  " + _bucket(df[trend], "趋势"))
    print("  " + _bucket(df[cut], "砍单"))
    print("  合计净利 {:+.1f}".format(df["net_pnl"].sum()))
    # 尾部
    tail = df[(df["order_kind"] == "grid") &
              (df["exit_reason"].isin(["last_order_stop", "cutoff_line_stop"]))]
    print(f"\n-- 尾部灾难(last_order_stop+cutoff_line_stop): {tail['net_pnl'].sum():+.0f} / {len(tail)} 笔")


def print_deep_underwater(trade_csv_path):
    """
    深水单剖析：读同目录的 problem_trades.csv，量化"深水网格里多少回归、多少被砍"。
    这是砍单亏损的精确来源。找不到 problem_trades.csv 就跳过。
    """
    import os
    pt = os.path.join(os.path.dirname(trade_csv_path), "problem_trades.csv")
    if not os.path.exists(pt):
        print("\n(同目录无 problem_trades.csv，跳过深水单剖析。)")
        return
    df = pd.read_csv(pt)
    if "problem_tag" not in df.columns:
        return
    print("\n-- 深水单剖析(problem_trades.csv) --")
    for tag, g in df.groupby("problem_tag"):
        p = g["net_pnl"]
        print(f"   {tag:16} n={len(g):5d} 净{p.sum():+8.0f} 胜{(p>0).mean()*100:4.0f}%")
    dw = df[df["problem_tag"] == "deep_underwater"]
    if len(dw):
        rec = dw[(dw.order_kind == "grid") & (dw.exit_reason == "grid_tp_baseline_revert")]
        cut = dw[(dw.order_kind == "grid") &
                 (dw.exit_reason.isin(CUT_REASONS_NEW | CUT_REASONS_OLD))]
        tot = len(rec) + len(cut)
        if tot:
            print(f"   深水网格: 回归获利 {len(rec)}笔/{rec.net_pnl.sum():+.0f} ({len(rec)/tot*100:.0f}%) | "
                  f"被砍 {len(cut)}笔/{cut.net_pnl.sum():+.0f} ({len(cut)/tot*100:.0f}%)")
            print("   → 深水网格多数会回归；被砍的少数集中了砍单亏损。要少误伤靠'砍得更准'而非'砍多砍少'。")


# ---------------------------------------------------------------- 行情/指标
def _load_m1(path):
    """
    读 m1 OHLC。自动识别常见格式：
      A) 逗号 CSV，列含 time/open/high/low/close（大小写不敏感）
      B) MT5 导出：Date,Time,Open,High,Low,Close,... 或 制表符分隔
    若你的格式不同，改这里。返回 index=DatetimeIndex, 列=[open,high,low,close] 的 DataFrame。
    """
    # 先尝试标准 csv
    df = pd.read_csv(path, sep=None, engine="python")
    cols = {c.lower().strip(): c for c in df.columns}
    if "time" in cols:
        t = pd.to_datetime(df[cols["time"]], errors="coerce")
    elif "date" in cols and "time" in cols:
        t = pd.to_datetime(df[cols["date"]].astype(str) + " " + df[cols["time"]].astype(str),
                           errors="coerce")
    elif {"date"} <= set(cols):  # 只有一列日期时间
        t = pd.to_datetime(df[cols["date"]], errors="coerce")
    else:
        # 兜底：第 1 列当时间
        t = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    def col(name, alts):
        for k in [name] + alts:
            if k in cols:
                return df[cols[k]]
        raise KeyError(f"m1 缺少列 {name}")
    out = pd.DataFrame({
        "open":  pd.to_numeric(col("open",  ["o"]), errors="coerce"),
        "high":  pd.to_numeric(col("high",  ["h"]), errors="coerce"),
        "low":   pd.to_numeric(col("low",   ["l"]), errors="coerce"),
        "close": pd.to_numeric(col("close", ["c"]), errors="coerce"),
    })
    out.index = t
    out = out.dropna().sort_index()
    return out


def _resample(m1, minutes):
    r = m1.resample(f"{minutes}min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return r


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _adx(df, n):
    """标准 Wilder ADX。"""
    h, l, c = df["high"], df["low"], df["close"]
    up = h.diff(); dn = -l.diff()
    plus_dm  = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([(h - l),
                    (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False).mean()
    plus_di  = 100 * pd.Series(plus_dm,  index=df.index).ewm(alpha=1/n, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/n, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean()


def build_indicators(m1):
    m5 = _resample(m1, TREND_TF_MIN)
    m5["fast"] = _ema(m5["close"], FAST_EMA)
    m5["slow"] = _ema(m5["close"], SLOW_EMA)
    m5["adx"]  = _adx(m5, ADX_PERIOD)
    tr = pd.concat([(m5["high"] - m5["low"]),
                    (m5["high"] - m5["close"].shift()).abs(),
                    (m5["low"]  - m5["close"].shift()).abs()], axis=1).max(axis=1)
    m5["atr"] = tr.ewm(alpha=1/ATR_PERIOD, adjust=False).mean()
    m5["ema_sep_atr"] = (m5["fast"] - m5["slow"]).abs() / m5["atr"]
    # 用【已收盘】上一根，避免未来函数
    m5i = m5.shift(1)

    m15 = _resample(m1, MTF_TF_MIN)
    m15["hf"] = _ema(m15["close"], MTF_FAST_EMA)
    m15["hs"] = _ema(m15["close"], MTF_SLOW_EMA)
    m15["mtf_up"] = (m15["hf"] > m15["hs"]).astype(int)
    m15i = m15.shift(1)
    return m5i, m15i


def attach_indicators(df, m5i, m15i):
    """把 M5 指标与 M15 MTF 落到每笔入场时刻（用 asof 取入场前最近一根已收盘 bar）。"""
    d = df.sort_values("entry_time").copy()
    for col in ["adx", "ema_sep_atr", "fast", "slow"]:
        d[col + "_at_entry"] = pd.merge_asof(
            d[["entry_time"]], m5i[[col]].reset_index().rename(columns={"index": "t"}),
            left_on="entry_time", right_on="t", direction="backward")[col].values
    d["mtf_up_at_entry"] = pd.merge_asof(
        d[["entry_time"]], m15i[["mtf_up"]].reset_index().rename(columns={"index": "t"}),
        left_on="entry_time", right_on="t", direction="backward")["mtf_up"].values
    # 趋势方向：direction 或 entry_reason 里含 buy/sell
    return d


def counterfactual_report(d):
    """核心：用趋势单结果评估 ADX/MTF 过滤的反事实价值。"""
    print("\n" + "=" * 78)
    print("【反事实诊断】新机制如果真开起来，会滤掉哪些趋势/砍单信号？")
    print("（用趋势单结果评估；趋势单对错=砍单准确率，见脚本头部说明）")
    print("=" * 78)
    t = d[d["order_kind"] == "trend"].copy()
    t = t.dropna(subset=["adx_at_entry"])
    if len(t) == 0:
        print("  趋势单没有匹配到指标（检查 m1 时间范围是否覆盖交易期）。")
        return
    print(f"\n趋势单总数(已匹配指标): {len(t)}  净利 {t.net_pnl.sum():+.0f}  "
          f"胜率 {(t.net_pnl>0).mean()*100:.1f}%")

    print("\n-- 按入场 ADX 分桶（看高 ADX 是否真的更准）--")
    bins = [0, 15, 20, 25, 30, 40, 999]
    t["adx_bin"] = pd.cut(t["adx_at_entry"], bins)
    g = t.groupby("adx_bin", observed=True)["net_pnl"].agg(
        n="count", net="sum", win=lambda x: (x > 0).mean() * 100, avg="mean")
    print(g.round(2).to_string())

    print("\n-- 反事实：要求 ADX≥阈值，会移除的趋势信号的净贡献 --")
    print("   (移除集净利<0 = 这些是坏信号，过滤有价值；>0 = 误伤好信号)")
    for thr in [20, 25, 30]:
        removed = t[t["adx_at_entry"] < thr]
        kept = t[t["adx_at_entry"] >= thr]
        print(f"   ADX≥{thr:>2}: 移除 {len(removed):4d} 笔/净 {removed.net_pnl.sum():+7.0f}"
              f"(胜{ (removed.net_pnl>0).mean()*100 if len(removed) else 0:4.1f}%) | "
              f"保留 {len(kept):4d} 笔/净 {kept.net_pnl.sum():+7.0f}"
              f"(胜{ (kept.net_pnl>0).mean()*100 if len(kept) else 0:4.1f}%)")

    print("\n-- 反事实：要求 MTF(M15 EMA) 同向 --")
    t2 = t.dropna(subset=["mtf_up_at_entry"]).copy()
    # 趋势多单要求 mtf_up=1；空单要求 mtf_up=0
    is_buy = t2["direction"].astype(str).str.lower().str.contains("buy") | \
             t2["entry_reason"].astype(str).str.lower().str.contains("buy")
    aligned = np.where(is_buy, t2["mtf_up_at_entry"] == 1, t2["mtf_up_at_entry"] == 0)
    kept = t2[aligned]; removed = t2[~aligned]
    print(f"   MTF同向: 移除 {len(removed):4d} 笔/净 {removed.net_pnl.sum():+7.0f}"
          f"(胜{(removed.net_pnl>0).mean()*100 if len(removed) else 0:4.1f}%) | "
          f"保留 {len(kept):4d} 笔/净 {kept.net_pnl.sum():+7.0f}"
          f"(胜{(kept.net_pnl>0).mean()*100 if len(kept) else 0:4.1f}%)")

    print("\n结论判读：若某阈值下【移除集净利显著为负】，说明该机制确实能滤掉坏信号，")
    print("          值得在 EA 里固定开启到该阈值（并在寻参时锁死不让优化器再拉低）。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade", required=True, help="trade_enriched.csv 路径")
    ap.add_argument("--m1", default=None, help="m1 OHLC 路径(可选;不给只做enrich分析)")
    args = ap.parse_args()

    df = _load_trades(args.trade)
    print_enrich_report(df)
    print_deep_underwater(args.trade)

    if args.m1:
        print("\n加载 m1 行情并重算 M5/M15 指标 ...")
        m1 = _load_m1(args.m1)
        print(f"  m1 覆盖 {m1.index.min()} ~ {m1.index.max()}  共 {len(m1)} 根")
        m5i, m15i = build_indicators(m1)
        d = attach_indicators(df, m5i, m15i)
        counterfactual_report(d)
    else:
        print("\n(未提供 --m1，跳过反事实诊断。补一份 m1 行情即可检验新机制真实价值。)")


if __name__ == "__main__":
    main()
