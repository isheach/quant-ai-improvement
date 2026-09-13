#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eva027_rescore.py  ——  eva027 评分V2 的"外部第二层复评"脚本

用途
----
读取 enriched 的 trade_enriched.csv，重建"逐笔平仓余额曲线"，用与 EA 内
OnTester_ScoreV2() 完全一致的公式复算评分。可对多套候选参数(每套一个
enriched 目录)统一打分、排序、对照。

为什么需要它(两层评分)
----------------------
· 第一层 = MT5 OnTester(eva027-V2)：优化时对每个 pass 打分，用于粗筛。
  其净值曲线来自"按间隔采样"，回撤事件/水下时间是近似值。
· 第二层 = 本脚本：对第一层选出的少量候选，用完整成交明细复评，可按
  exit_reason 精确拆分尾损，并明确标注"余额曲线"口径的局限。

重要口径说明(务必读)
--------------------
· 本脚本的回撤/水下时间基于"逐笔平仓余额曲线"(只含已实现盈亏)，
  会【低估】真实回撤——深水网格单在平仓前的浮亏不体现在余额曲线上。
  真实最大回撤%请以 MT5 tester 报告的 Equity DD% 为准；本脚本值仅作
  "按出场原因归因 + 相对排序"用途。
· 初始资金 InitialBalance 从 enriched 无法得知，需用 --deposit 传入(默认
  沿用 EA 优化时的 STAT_INITIAL_DEPOSIT)。年化收益/各百分比项都依赖它。

用法
----
  python3 eva027_rescore.py --deposit 2000 \
      --label train2023  path/to/enrich_eva026_train2023 \
      --label train2024  path/to/enrich_eva026_train2024
"""

import argparse, csv, datetime, math, os, sys

TAIL_LAST   = "last_order_stop"
TAIL_CUTOFF = "cutoff_line_stop"
TAIL_CUT    = "trend_close_opposite_grid"


# ---- 与 EA 内 OnTester_ScoreV2 完全一致的默认权重/幂次/阈值 ----
class ScoreCfg:
    target_annual   = 0.20
    min_total       = 30
    free_maxdd      = 0.20
    free_episode    = 0.10
    free_underwater = 0.15
    min_tpm         = 8.0
    max_tpm         = 45.0
    w_profit        = 100.0
    w_loss          = 100.0
    w_maxdd         = 150.0
    w_episode       = 30.0
    w_underwater    = 50.0
    w_lowfreq       = 20.0
    w_highfreq      = 50.0
    w_tail          = 50.0
    p_loss          = 2.0
    p_maxdd         = 2.0
    p_episode       = 1.5
    p_underwater    = 1.5
    p_freq          = 2.0
    p_tail          = 1.5
    cut_weight      = 0.5


def parse_dt(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(s[:19], fmt)
        except ValueError:
            pass
    return None


def load_trades(enrich_dir):
    path = os.path.join(enrich_dir, "trade_enriched.csv")
    rows = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            t = parse_dt(r.get("exit_time")) or parse_dt(r.get("entry_time"))
            try:
                net = float(r.get("net_pnl") or 0.0)
            except ValueError:
                net = 0.0
            rows.append({
                "t": t,
                "net": net,
                "exit": (r.get("exit_reason") or "").strip(),
                "entry": (r.get("entry_reason") or "").strip(),
            })
    rows = [r for r in rows if r["t"] is not None]
    rows.sort(key=lambda x: x["t"])
    return rows


def balance_curve_stats(rows):
    """逐笔平仓余额曲线：最大回撤(金额)、回撤事件深度序列($)、最长水下秒、span秒。"""
    bal = 0.0
    peak = 0.0
    peak_t = rows[0]["t"]
    max_dd_amt = 0.0
    max_uw = 0
    episodes = []          # 每段回撤深度($)
    in_dd = False
    ep_peak = 0.0
    trough = 0.0
    for r in rows:
        bal += r["net"]
        if bal >= peak:
            if in_dd:
                episodes.append(ep_peak - trough)
                in_dd = False
            peak = bal
            peak_t = r["t"]
            trough = bal
        else:
            if (peak - bal) > max_dd_amt:
                max_dd_amt = peak - bal
            if not in_dd:
                in_dd = True
                ep_peak = peak
                trough = bal
            elif bal < trough:
                trough = bal
            uw = (r["t"] - peak_t).total_seconds()
            if uw > max_uw:
                max_uw = uw
    if in_dd:
        episodes.append(ep_peak - trough)
    span = (rows[-1]["t"] - rows[0]["t"]).total_seconds()
    return {
        "net": bal, "max_dd_amt": max_dd_amt, "episodes_amt": episodes,
        "max_uw_sec": max_uw, "span_sec": span,
    }


def tail_losses(rows):
    d = {TAIL_LAST: 0.0, TAIL_CUTOFF: 0.0, TAIL_CUT: 0.0}
    for r in rows:
        if r["exit"] in d:
            d[r["exit"]] += r["net"]
    return d


def compute_score(rows, deposit, cfg=ScoreCfg):
    st = balance_curve_stats(rows)
    net = st["net"]
    n_trades = len(rows)
    years = max(1e-3, st["span_sec"] / (365.25 * 86400))
    months = max(1e-3, years * 12.0)

    if n_trades < cfg.min_total:
        return {"score": -1e6 + n_trades, "reject": "trades<min"}

    # ---- profit ----
    return_pct = net / deposit
    annual = return_pct / years
    profit_score = cfg.w_profit * math.log(1.0 + max(0.0, annual) / cfg.target_annual)

    # ---- final loss ----
    loss_pct = min(0.999, max(0.0, -net / deposit))
    final_loss = 0.0
    if loss_pct > 0:
        final_loss = cfg.w_loss * (loss_pct / max(1e-6, 1 - loss_pct)) ** cfg.p_loss

    # ---- max DD (余额曲线口径; 真实值以tester Equity DD%为准) ----
    max_dd_pct = min(0.999, st["max_dd_amt"] / deposit)
    maxdd_pen = 0.0
    ex = max(0.0, max_dd_pct - cfg.free_maxdd)
    if ex > 0:
        maxdd_pen = cfg.w_maxdd * (ex / max(1e-6, 1 - max_dd_pct)) ** cfg.p_maxdd

    # ---- episodes ----
    episode_raw = 0.0
    ep_cnt = 0
    for e_amt in st["episodes_amt"]:
        ep_dd = min(0.999, max(0.0, e_amt / deposit))
        exx = max(0.0, ep_dd - cfg.free_episode)
        if exx > 0:
            episode_raw += (exx / max(1e-6, 1 - ep_dd)) ** cfg.p_episode
            ep_cnt += 1
    episode_pen = cfg.w_episode * episode_raw

    # ---- underwater ----
    uw_ratio = st["max_uw_sec"] / st["span_sec"] if st["span_sec"] > 0 else 0.0
    underwater_pen = 0.0
    exu = max(0.0, uw_ratio - cfg.free_underwater)
    if exu > 0:
        underwater_pen = cfg.w_underwater * (exu ** cfg.p_underwater)

    # ---- freq band ----
    tpm = n_trades / months
    toofew = cfg.w_lowfreq * max(0.0, cfg.min_tpm / max(1e-6, tpm) - 1.0) ** cfg.p_freq
    toomany = cfg.w_highfreq * max(0.0, tpm / cfg.max_tpm - 1.0) ** cfg.p_freq

    # ---- tail exits ----
    tl = tail_losses(rows)
    loss_last = max(0.0, -tl[TAIL_LAST])
    loss_cutoff = max(0.0, -tl[TAIL_CUTOFF])
    loss_cut = max(0.0, -tl[TAIL_CUT])
    # 年化：尾损为全程求和量，÷years 与年化收益同尺度(否则长回测虚高)
    tail_pct = (loss_last + loss_cutoff + cfg.cut_weight * loss_cut) / deposit / years
    tail_pen = cfg.w_tail * (max(0.0, tail_pct) ** cfg.p_tail)

    score = (profit_score - final_loss - maxdd_pen - episode_pen
             - underwater_pen - toofew - toomany - tail_pen)

    return {
        "score": score, "reject": "",
        "net": net, "n_trades": n_trades, "years": years, "months": months,
        "return_pct": return_pct, "annual": annual,
        "profit_score": profit_score, "final_loss": final_loss,
        "max_dd_pct": max_dd_pct, "maxdd_pen": maxdd_pen,
        "episode_cnt": ep_cnt, "episode_pen": episode_pen,
        "uw_ratio": uw_ratio, "uw_days": st["max_uw_sec"] / 86400.0,
        "underwater_pen": underwater_pen,
        "tpm": tpm, "toofew": toofew, "toomany": toomany,
        "loss_last": loss_last, "loss_cutoff": loss_cutoff, "loss_cut": loss_cut,
        "tail_pct": tail_pct, "tail_pen": tail_pen,
    }


def fmt(r, label):
    if r.get("reject"):
        return f"[{label}] 拒绝: {r['reject']}"
    return (
        f"====== [{label}] eva027-V2 复评 ======\n"
        f"  最终评分 SCORE           = {r['score']:.3f}\n"
        f"  ---- 收益 ----\n"
        f"  期末净利                  = {r['net']:,.2f}\n"
        f"  收益率 / 年化             = {r['return_pct']*100:.2f}%  /  {r['annual']*100:.2f}%\n"
        f"  ProfitScore(+)           = {r['profit_score']:.2f}\n"
        f"  ---- 风险惩罚(均为减项) ----\n"
        f"  最终亏损惩罚              = {r['final_loss']:.2f}\n"
        f"  最大回撤{r['max_dd_pct']*100:.1f}%(余额口径)→惩罚 = {r['maxdd_pen']:.2f}\n"
        f"  回撤事件数(>{ScoreCfg.free_episode*100:.0f}%) = {r['episode_cnt']}  → 惩罚 = {r['episode_pen']:.2f}\n"
        f"  最长水下 {r['uw_days']:.0f}天({r['uw_ratio']*100:.1f}%)→惩罚 = {r['underwater_pen']:.2f}\n"
        f"  月均交易 {r['tpm']:.1f}(区间{ScoreCfg.min_tpm:.0f}~{ScoreCfg.max_tpm:.0f})→ 过少-{r['toofew']:.2f} 过密-{r['toomany']:.2f}\n"
        f"  尾损%={r['tail_pct']*100:.2f} (末单-{r['loss_last']:.0f} 截止-{r['loss_cutoff']:.0f} "
        f"砍单-{r['loss_cut']:.0f}×{ScoreCfg.cut_weight})→惩罚 = {r['tail_pen']:.2f}\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deposit", type=float, required=True,
                    help="初始资金(=EA优化时STAT_INITIAL_DEPOSIT)。用于所有百分比归一。")
    ap.add_argument("--label", action="append", default=[])
    ap.add_argument("dirs", nargs="+")
    args = ap.parse_args()

    labels = args.label if len(args.label) == len(args.dirs) else \
        [os.path.basename(d.rstrip("/")) for d in args.dirs]

    results = []
    for label, d in zip(labels, args.dirs):
        rows = load_trades(d)
        r = compute_score(rows, args.deposit)
        results.append((label, r))
        print(fmt(r, label))

    print("\n==== 排序(评分从高到低) ====")
    for label, r in sorted(results, key=lambda x: -x[1]["score"]):
        print(f"  {label:16s} SCORE={r['score']:.3f}")


if __name__ == "__main__":
    main()
