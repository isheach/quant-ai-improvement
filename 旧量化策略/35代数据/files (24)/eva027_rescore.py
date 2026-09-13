#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eva027_rescore.py  ——  eva027 评分V2 的"外部第二层复评"脚本

用途
----
读取 enriched 的 trade_enriched.csv，重建"逐笔平仓余额曲线"，用与 EA 内
OnTester_ScoreV2() 完全一致的公式复算评分。可对多套候选参数(每套一个
enriched 目录)统一打分、排序、对照。

它不是用来"找最赚钱的评分权重"的
--------------------------------
评分权重代表【用户的风险偏好】，应当【先验固定】，不能用历史数据拟合。
本脚本只用于"校准量级"：在选定真实 deposit 后，观察各扣分项
(ProfitScore / MaxDDPenalty / UnderwaterPenalty / TooManyTradesPenalty /
TailExitPenalty ...) 的大小，确认没有某一项完全压倒其它、也没有某个关键
风险项几乎不起作用。调好后固定权重，再用 MT5 优化【交易参数】，最后对
Top-N 参数在"去训练年验证区间"上用本脚本复评定参。

口径差异(务必读)
----------------
· 水下时间定义 = 当前权益低于"历史最高权益"的持续时间。不是"账户亏损时间"，
  也不是"持仓浮亏时间"。例：账户 2000→2300→2250，虽仍盈利，但因未回到
  上一峰值 2300，仍算处于水下。
· 本脚本回撤/水下基于"逐笔平仓余额曲线"(只含已实现盈亏)，会【低估】真实
  回撤/水下——深水网格单平仓前的浮亏不体现在余额曲线上。EA 内则基于采样
  Equity(含浮动盈亏)，更接近真实。最大回撤真值以 MT5 tester 的 Equity DD% 为准。
· 尾损口径(与 EA 内三出场点一致)：同一个风险出口事件内部，先算该事件关闭前整组
  持仓的净浮动 PnL；事件净 PnL<0 才累计该事件亏损，事件净 PnL≥0 则该事件不产生
  TailLoss。即"事件内部可净额计算，不同风险事件之间不允许正负抵消"。

时间跨度(年/月)
--------------
· 提供 --start/--end 时用【完整回测区间】计算 years/months(推荐)。
· 未提供时回退到"首笔~末笔成交"跨度，并在输出中告警——若测试区间首尾有
  空窗，该跨度会偏短，导致年化收益/月均交易/水下比/尾损年化全部失真。
· --start / --end 只定义"完整回测评价区间"，用于年化、TPM、水下比、尾损年化的
  时间【分母】，【不会】自动过滤交易行。传入的 trade_enriched.csv 必须本身就已经是
  对应该回测区间的数据。
  (--start/--end define the full backtest evaluation window for annualization, TPM,
   underwater ratio, and tail-loss annualization. They do NOT filter trade rows
   automatically. The input trade_enriched.csv must already correspond to the
   intended backtest window.)

用法示例
--------
  python3 eva027_rescore.py --deposit 2000 \
      --start 2023-01-01 --end 2026-07-01 \
      --label train2024  path/to/enrich_eva026_train2024

可选：用 --config score_config.json 或命令行 --w-tail/--max-tpm/... 覆盖裁判规则。
"""

import argparse, csv, datetime, json, math, os

TAIL_LAST   = "last_order_stop"
TAIL_CUTOFF = "cutoff_line_stop"
TAIL_CUT    = "trend_close_opposite_grid"


class ScoreCfg:
    """裁判规则(风险偏好)，先验固定。与 EA 内 InpScore* 默认值一一对应。"""
    def __init__(self):
        self.target_annual   = 0.20
        self.min_total       = 30
        self.free_maxdd      = 0.20
        self.free_episode    = 0.10
        self.free_underwater = 0.15
        self.min_tpm         = 8.0
        self.max_tpm         = 45.0
        self.w_profit        = 100.0
        self.w_loss          = 100.0
        self.w_maxdd         = 150.0
        self.w_episode       = 30.0
        self.w_underwater    = 50.0
        self.w_lowfreq       = 20.0
        self.w_highfreq      = 50.0
        self.w_tail          = 50.0
        self.p_loss          = 2.0
        self.p_maxdd         = 2.0
        self.p_episode       = 1.5
        self.p_underwater    = 1.5
        self.p_freq          = 2.0
        self.p_tail          = 1.5
        self.cut_weight      = 0.5
        self.tail_event_tol  = 5.0   # 秒：同reason且时间相邻≤tol的成交并为一个"出场事件"

    def apply_dict(self, d):
        alias = {
            "w_tail": "w_tail", "w-tail": "w_tail",
            "w_maxdd": "w_maxdd", "w-maxdd": "w_maxdd",
            "w_underwater": "w_underwater", "w-underwater": "w_underwater",
            "max_tpm": "max_tpm", "max-tpm": "max_tpm",
            "min_tpm": "min_tpm", "min-tpm": "min_tpm",
            "free_maxdd": "free_maxdd", "free-maxdd": "free_maxdd",
            "cut_weight": "cut_weight", "cut-weight": "cut_weight",
        }
        for k, v in d.items():
            attr = alias.get(k, k)
            if hasattr(self, attr) and v is not None:
                setattr(self, attr, float(v))


def parse_dt(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S",
                "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.datetime.strptime(s[:19] if len(s) >= 19 else s, fmt)
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
                "t": t, "net": net,
                "exit":  (r.get("exit_reason")  or "").strip(),
                "entry": (r.get("entry_reason") or "").strip(),
            })
    rows = [r for r in rows if r["t"] is not None]
    rows.sort(key=lambda x: x["t"])
    return rows


def balance_curve_stats(rows, total_span_sec):
    """逐笔平仓余额曲线：最大回撤($)、各回撤事件深度($)、最长水下秒。
    水下 = 权益低于历史最高权益的持续时间(不是亏损时间)。
    水下比分母用【完整回测跨度 total_span_sec】(而非首末成交跨度)。"""
    bal = peak = trough = 0.0
    peak_t = rows[0]["t"]
    max_dd_amt = 0.0
    max_uw = 0.0
    episodes = []
    in_dd = False
    ep_peak = 0.0
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
    uw_ratio = (max_uw / total_span_sec) if total_span_sec > 0 else 0.0
    return {"net": bal, "max_dd_amt": max_dd_amt, "episodes_amt": episodes,
            "max_uw_sec": max_uw, "uw_ratio": uw_ratio}


def tail_event_losses(rows, cfg):
    """逐事件亏损累计：同一 exit_reason 且成交时间相邻(≤tol秒)的成交合并为一个出场事件。
    事件内部按【净额】计算(同事件内盈利成交会抵消亏损成交)；事件净 PnL<0 才累计其亏损，
    事件净 PnL≥0 则该事件不产生 TailLoss。不同风险出口事件之间【不允许】正负抵消。"""
    d = {TAIL_LAST: 0.0, TAIL_CUTOFF: 0.0, TAIL_CUT: 0.0}
    ev_cnt = {TAIL_LAST: 0, TAIL_CUTOFF: 0, TAIL_CUT: 0}
    tol = cfg.tail_event_tol
    by_reason = {k: [] for k in d}
    for r in rows:
        if r["exit"] in d:
            by_reason[r["exit"]].append(r)
    for reason, lst in by_reason.items():
        lst.sort(key=lambda x: x["t"])
        i = 0
        while i < len(lst):
            j = i
            ev = lst[i]["net"]
            t0 = lst[i]["t"]
            while j + 1 < len(lst) and (lst[j + 1]["t"] - t0).total_seconds() <= tol:
                j += 1
                ev += lst[j]["net"]
            if ev < 0:
                d[reason] += -ev
                ev_cnt[reason] += 1
            i = j + 1
    return d, ev_cnt


def compute_score(rows, deposit, cfg, start=None, end=None):
    n_trades = len(rows)
    if n_trades == 0:
        return {"score": -1e6, "reject": "no trades"}

    # ---- 时间跨度：优先完整回测区间 ----
    if start and end:
        total_span_sec = (end - start).total_seconds()
        span_source = "回测区间[start,end]"
    else:
        total_span_sec = (rows[-1]["t"] - rows[0]["t"]).total_seconds()
        span_source = "⚠首末成交跨度(非完整回测,可能偏短→年化失真)"
    total_span_sec = max(total_span_sec, 1.0)
    years  = max(1e-3, total_span_sec / (365.25 * 86400))
    months = max(1e-3, years * 12.0)

    st = balance_curve_stats(rows, total_span_sec)
    net = st["net"]

    if n_trades < cfg.min_total:
        return {"score": -1e6 + n_trades, "reject": f"trades<{cfg.min_total}"}

    # ---- (0) 收益：CAGR 年化 → log 平滑 ----
    return_pct = net / deposit
    final_equity = deposit + net
    if final_equity <= 0.0:
        annual = -1.0
    else:
        annual = (final_equity / deposit) ** (1.0 / years) - 1.0
    profit_score = cfg.w_profit * math.log(1.0 + max(0.0, annual) / cfg.target_annual)

    # ---- (1) 最终亏损 ----
    loss_pct = min(0.999, max(0.0, -net / deposit))
    final_loss = cfg.w_loss * (loss_pct / max(1e-6, 1 - loss_pct)) ** cfg.p_loss if loss_pct > 0 else 0.0

    # ---- (2) 最大回撤(余额口径,低估;真值以tester Equity DD%为准) ----
    max_dd_pct = min(0.999, st["max_dd_amt"] / deposit)
    ex = max(0.0, max_dd_pct - cfg.free_maxdd)
    maxdd_pen = cfg.w_maxdd * (ex / max(1e-6, 1 - max_dd_pct)) ** cfg.p_maxdd if ex > 0 else 0.0

    # ---- (3) 回撤事件 ----
    episode_raw = 0.0
    ep_cnt = 0
    for e_amt in st["episodes_amt"]:
        ep_dd = min(0.999, max(0.0, e_amt / deposit))
        exx = max(0.0, ep_dd - cfg.free_episode)
        if exx > 0:
            episode_raw += (exx / max(1e-6, 1 - ep_dd)) ** cfg.p_episode
            ep_cnt += 1
    episode_pen = cfg.w_episode * episode_raw

    # ---- (5) 水下时间 ----
    uw_ratio = st["uw_ratio"]
    exu = max(0.0, uw_ratio - cfg.free_underwater)
    underwater_pen = cfg.w_underwater * (exu ** cfg.p_underwater) if exu > 0 else 0.0

    # ---- (4) 频次区间 ----
    tpm = n_trades / months
    toofew = cfg.w_lowfreq * max(0.0, cfg.min_tpm / max(1e-6, tpm) - 1.0) ** cfg.p_freq
    toomany = cfg.w_highfreq * max(0.0, tpm / cfg.max_tpm - 1.0) ** cfg.p_freq

    # ---- (6) 尾部出口(逐事件亏损,年化) ----
    tl, tl_cnt = tail_event_losses(rows, cfg)
    loss_last, loss_cutoff, loss_cut = tl[TAIL_LAST], tl[TAIL_CUTOFF], tl[TAIL_CUT]
    tail_pct = (loss_last + loss_cutoff + cfg.cut_weight * loss_cut) / deposit / years
    tail_pen = cfg.w_tail * (max(0.0, tail_pct) ** cfg.p_tail)

    score = (profit_score - final_loss - maxdd_pen - episode_pen
             - underwater_pen - toofew - toomany - tail_pen)

    return {
        "score": score, "reject": "", "span_source": span_source,
        "net": net, "n_trades": n_trades, "years": years, "months": months,
        "return_pct": return_pct, "annual": annual,
        "profit_score": profit_score, "final_loss": final_loss,
        "max_dd_pct": max_dd_pct, "maxdd_pen": maxdd_pen,
        "episode_cnt": ep_cnt, "episode_pen": episode_pen,
        "uw_ratio": uw_ratio, "uw_days": st["max_uw_sec"] / 86400.0,
        "underwater_pen": underwater_pen,
        "tpm": tpm, "toofew": toofew, "toomany": toomany,
        "loss_last": loss_last, "loss_cutoff": loss_cutoff, "loss_cut": loss_cut,
        "ev_last": tl_cnt[TAIL_LAST], "ev_cutoff": tl_cnt[TAIL_CUTOFF], "ev_cut": tl_cnt[TAIL_CUT],
        "tail_pct": tail_pct, "tail_pen": tail_pen,
    }


def fmt(r, label, deposit, cfg):
    if r.get("reject"):
        return f"[{label}] 拒绝: {r['reject']}"
    return (
        f"====== [{label}] eva027-V2 复评  (归一资金 deposit = {deposit:,.0f}) ======\n"
        f"  最终评分 SCORE           = {r['score']:.3f}\n"
        f"  跨度来源                  = {r['span_source']}  → {r['years']:.2f}年 / {r['months']:.1f}月\n"
        f"  ---- 收益 ----\n"
        f"  期末净利                  = {r['net']:,.2f}\n"
        f"  收益率 / CAGR年化         = {r['return_pct']*100:.2f}%  /  {r['annual']*100:.2f}%\n"
        f"  ProfitScore(+)           = {r['profit_score']:.2f}\n"
        f"  ---- 风险惩罚(均为减项) ----\n"
        f"  最终亏损惩罚              = {r['final_loss']:.2f}\n"
        f"  最大回撤{r['max_dd_pct']*100:.1f}%(余额口径,低估)→惩罚 = {r['maxdd_pen']:.2f}\n"
        f"  回撤事件数(>{cfg.free_episode*100:.0f}%) = {r['episode_cnt']}  → 惩罚 = {r['episode_pen']:.2f}\n"
        f"  最长水下 {r['uw_days']:.0f}天({r['uw_ratio']*100:.1f}%)→惩罚 = {r['underwater_pen']:.2f}\n"
        f"  月均交易 {r['tpm']:.1f}(区间{cfg.min_tpm:.0f}~{cfg.max_tpm:.0f})→ 过少-{r['toofew']:.2f} 过密-{r['toomany']:.2f}\n"
        f"  年化尾损%={r['tail_pct']*100:.2f} 逐事件亏损:末单-{r['loss_last']:.0f}({r['ev_last']}次) "
        f"截止-{r['loss_cutoff']:.0f}({r['ev_cutoff']}次) 砍单-{r['loss_cut']:.0f}({r['ev_cut']}次)×{cfg.cut_weight}"
        f"→惩罚 = {r['tail_pen']:.2f}\n"
    )


def main():
    ap = argparse.ArgumentParser(description="eva027 评分V2 外部复评(量级校准/去训练年定参)")
    ap.add_argument("--deposit", type=float, required=True,
                    help="归一资金=实盘计划分配给本EA的资金(务必真实);所有百分比按它归一")
    ap.add_argument("--start", type=str, default=None,
                    help="回测区间起 YYYY-MM-DD(用于年化;不过滤交易行,CSV须已是该区间数据)")
    ap.add_argument("--end", type=str, default=None,
                    help="回测区间止 YYYY-MM-DD(用于年化;不过滤交易行,CSV须已是该区间数据)")
    ap.add_argument("--config", type=str, default=None, help="裁判规则JSON(可覆盖权重/阈值)")
    ap.add_argument("--label", action="append", default=[])
    # 命令行覆盖(仅用于量级校准,勿用历史拟合)
    for k in ("w-tail", "w-maxdd", "w-underwater", "max-tpm", "min-tpm", "free-maxdd", "cut-weight"):
        ap.add_argument(f"--{k}", type=float, default=None)
    ap.add_argument("dirs", nargs="+")
    args = ap.parse_args()

    cfg = ScoreCfg()
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            cfg.apply_dict(json.load(f))
    cli = {k.replace("-", "_"): getattr(args, k.replace("-", "_"))
           for k in ("w-tail", "w-maxdd", "w-underwater", "max-tpm", "min-tpm", "free-maxdd", "cut-weight")}
    cfg.apply_dict(cli)

    start = parse_dt(args.start) if args.start else None
    end   = parse_dt(args.end)   if args.end else None
    if bool(start) ^ bool(end):
        print("⚠ 只提供了 start/end 之一，忽略；请同时提供两者以使用完整回测跨度。\n")
        start = end = None
    if not (start and end):
        print("⚠ 未提供 --start/--end：年化将用【首末成交跨度】近似，若测试区间首尾有空窗会失真。\n")

    print(f"[归一资金 deposit = {args.deposit:,.0f}]  ← 必须等于真实计划分配资金，否则百分比被稀释、评分虚高\n")

    results = []
    labels = args.label if len(args.label) == len(args.dirs) else \
        [os.path.basename(d.rstrip("/")) for d in args.dirs]
    for label, d in zip(labels, args.dirs):
        rows = load_trades(d)
        r = compute_score(rows, args.deposit, cfg, start, end)
        results.append((label, r))
        print(fmt(r, label, args.deposit, cfg))

    print("==== 排序(评分从高到低) ====")
    for label, r in sorted(results, key=lambda x: -x[1]["score"]):
        print(f"  {label:16s} SCORE={r['score']:.3f}")


if __name__ == "__main__":
    main()
