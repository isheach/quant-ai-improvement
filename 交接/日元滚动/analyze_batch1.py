# -*- coding: utf-8 -*-
"""
analyze_batch1.py —— 日元滚动线 第一批回填分析
输入：outbox_日元滚动.jsonl（648 pass = 6 网格 × 108）、outbox_日元滚动_grid1.jsonl（25 pass）
规则：★预登记（报告_001 §4 + 滚动优化线 报告_002 §5.3），不事后改
输出：analysis_batch1.txt（UTF-8），控制台只打 ASCII 摘要
"""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
WF = HERE / "outbox_日元滚动.jsonl"
GS = HERE / "outbox_日元滚动_grid1.jsonl"
OUT = []
YRS_6MO = 0.5           # 训练/验证/测试段各 6 个月中的 3 个月 → 见下
SEG_MONTHS = {"tr": 6, "va": 3, "te": 3}


def P(s=""):
    OUT.append(str(s))


def load(path):
    rows = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            pass
    return rows


def num(v, d=0.0):
    try:
        if v in ("", None):
            return d
        return float(v)
    except Exception:
        return d


# ---------------------------------------------------------------- 载入
PARAMS = ["InpEntrySigma", "InpExitFrac", "InpMaxER", "InpStopATR"]
wf = [r for r in load(WF) if r.get("pass") is not None]
gs = [r for r in load(GS) if r.get("pass") is not None]
for r in wf + gs:
    r["_net"] = num(r.get("net"))
    r["_pf"] = num(r.get("profit_factor"))
    r["_tr"] = num(r.get("trades"))
    r["_dd"] = num(r.get("dd_pct"))
    r["_seg"] = r["grid_id"].split("-")[1]      # w0tr / w0va / w0te
    r["_tf"] = r["grid_id"].split("-")[-1]      # m5 / m15
    r["_months"] = SEG_MONTHS.get(r["_seg"][2:], 6)
    r["_py"] = r["_tr"] / (r["_months"] / 12.0)  # 笔/年

P("=" * 100)
P("日元滚动线 · 第一批回填分析")
P("=" * 100)
P(f"WF pass = {len(wf)}（6 网格 × 108）   网格冒烟 pass = {len(gs)}")
P()


# ---------------------------------------------------------------- Spearman
def rank(vals):
    """平均秩（处理并列）"""
    idx = sorted(range(len(vals)), key=lambda i: vals[i])
    r = [0.0] * len(vals)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and vals[idx[j + 1]] == vals[idx[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[idx[k]] = avg
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((ra[i] - ma) * (rb[i] - mb) for i in range(n))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((x - mb) ** 2 for x in rb) ** 0.5
    if va == 0 or vb == 0:
        return None
    return cov / (va * vb)


# ---------------------------------------------------------------- §1 三段门槛全景
P("=" * 100)
P("§1 【事实】W0 三段的频率与盈利分布")
P("=" * 100)
P(f"{'网格':<16}{'pass':>5}{'盈利数':>7}{'0笔':>5}{'笔数min':>9}{'笔数中位':>9}{'笔数max':>9}{'笔/年中位':>10}{'net中位':>9}{'net max':>9}{'PF max':>8}")
P("-" * 100)


def med(v):
    v = sorted(v)
    if not v:
        return 0.0
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


for tf in ("m5", "m15"):
    for seg in ("tr", "va", "te"):
        g = [r for r in wf if r["_tf"] == tf and r["_seg"] == f"w0{seg}"]
        if not g:
            continue
        P(f"{'w0'+seg+'-'+tf:<16}{len(g):>5}"
          f"{sum(1 for r in g if r['_net'] > 0):>7}"
          f"{sum(1 for r in g if r['_tr'] == 0):>5}"
          f"{min(r['_tr'] for r in g):>9.0f}{med([r['_tr'] for r in g]):>9.0f}"
          f"{max(r['_tr'] for r in g):>9.0f}{med([r['_py'] for r in g]):>10.0f}"
          f"{med([r['_net'] for r in g]):>9.2f}{max(r['_net'] for r in g):>9.2f}"
          f"{max(r['_pf'] for r in g):>8.3f}")
P()
P("★读法：")
P("  · m5 三个段的笔/年中位在数百到上千 —— 频率远远过 50 笔/年门槛，但同时逼近/超过 churn 门槛（2000/年）")
P("  · m5 的训练段【盈利数 = 0】→ 下一节的选参规则在 m5 上【结构性无法启动】")
P("  · m15 的笔/年低一个量级，训练段有 17 个盈利 pass")
P()


# ---------------------------------------------------------------- §2 预登记选参规则
P("=" * 100)
P("§2 【事实】按【预登记规则】执行 W0 选参（规则在看数据之前写死）")
P("=" * 100)
P("规则：①训练段 trades >= 25（>=50 笔/年）②训练段 net > 0 ③按训练段 net 降序取前 30")
P("      ④在候选里选【验证段 net 最大】者 ⑤它的测试段 net = 本窗口 OOS ⑥对照：随机选参")
P()

RESULT = {}
for tf in ("m5", "m15"):
    tr = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0tr"}
    va = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0va"}
    te = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0te"}

    P(f"--- {tf.upper()} ---")
    # ① 频率门槛
    passFreq = [r for r in tr.values() if r["_tr"] >= 25]
    P(f"  ① 训练段 trades>=25（>=50 笔/年）: {len(passFreq)}/108")
    # ② 训练段 net>0
    cand = [r for r in passFreq if r["_net"] > 0]
    P(f"  ② 其中训练段 net>0            : {len(cand)}/108")
    if not cand:
        P(f"  ★★ {tf.upper()} 结构性失败：训练段【没有任何】同时满足频率与正收益的配置")
        P(f"     → 滚动优化的第一步（用训练段挑候选）就无从下手。这不是'挑得不好'，是'没有可挑的'。")
        RESULT[tf] = None
        P()
        continue
    # ③ top30
    cand.sort(key=lambda r: -r["_net"])
    top = cand[:30]
    P(f"  ③ 按训练段 net 降序取前 30    : {len(top)} 个")
    # ④ 验证段 net 最大
    top_va = sorted(top, key=lambda r: -va[r["pass"]]["_net"])
    win = top_va[0]
    P(f"  ④ 验证段 net 最大者 pass={win['pass']}  params={win['params']}")
    P(f"     训练 net={win['_net']:+.2f} 验证 net={va[win['pass']]['_net']:+.2f} "
      f"→ 测试(OOS) net={te[win['pass']]['_net']:+.2f}  trades={te[win['pass']]['_tr']:.0f} "
      f"PF={te[win['pass']]['_pf']:.3f}  dd={te[win['pass']]['_dd']:.2f}%")
    # ⑤ 对照：只用训练段最优（跳过验证段）
    trbest = top[0]
    P(f"  ⑤ 对照A【跳过验证段，直接用训练段第1名】pass={trbest['pass']}")
    P(f"     训练 net={trbest['_net']:+.2f} → 测试(OOS) net={te[trbest['pass']]['_net']:+.2f}")
    # ⑥ 对照：训练段 net 最优（不加频率门槛）
    trbest_nogate = sorted(tr.values(), key=lambda r: -r["_net"])[0]
    P(f"  ⑥ 对照B【不加频率门槛，训练段 net 第1名】pass={trbest_nogate['pass']} "
      f"trades={trbest_nogate['_tr']:.0f}({trbest_nogate['_py']:.0f}笔/年)")
    P(f"     训练 net={trbest_nogate['_net']:+.2f} → 测试(OOS) net={te[trbest_nogate['pass']]['_net']:+.2f}")
    RESULT[tf] = dict(win=win, te=te, va=va, tr=tr, cand=cand)
    P()


# ---------------------------------------------------------------- §3 ρ
P("=" * 100)
P("§3 ★★【事实】验证段选参 有没有预测力（Spearman ρ：验证段 net 排名 vs 测试段 net 排名）")
P("=" * 100)
for tf, d in RESULT.items():
    if d is None:
        P(f"--- {tf.upper()} ---  训练段无候选 → 无法计算 ρ")
        continue
    cand = d["cand"]
    a = [d["va"][r["pass"]]["_net"] for r in cand]
    b = [d["te"][r["pass"]]["_net"] for r in cand]
    rho = spearman(a, b)
    n = len(cand)
    # top5 命中
    va_top5 = {r["pass"] for r in sorted(cand, key=lambda r: -d["va"][r["pass"]]["_net"])[:5]}
    te_top5 = {r["pass"] for r in sorted(cand, key=lambda r: -d["te"][r["pass"]]["_net"])[:5]}
    hit = len(va_top5 & te_top5)
    P(f"--- {tf.upper()} ---  n={n} 候选")
    P(f"    Spearman ρ(验证段, 测试段) = {rho:+.3f}" if rho is not None else "    ρ 无法计算")
    P(f"    验证段 top5 与测试段 top5 的重合 = {hit}/5   （随机期望 ≈ {5*5/n:.2f}/5）")
    # 训练段 vs 测试段（作为对照：轮动到底有没有用）
    a2 = [d["tr"][r["pass"]]["_net"] for r in cand]
    rho2 = spearman(a2, b)
    P(f"    对照 ρ(训练段, 测试段) = {rho2:+.3f}" if rho2 is not None else "    对照 ρ 无法计算")
    # 训练段 vs 验证段
    rho3 = spearman(a2, a)
    P(f"    对照 ρ(训练段, 验证段) = {rho3:+.3f}" if rho3 is not None else "    对照 ρ 无法计算")
    # 随机选参分布
    import random
    random.seed(20260912)
    oos = [d["te"][r["pass"]]["_net"] for r in cand]
    rand_means = []
    for _ in range(5000):
        rand_means.append(sum(random.sample(oos, 1)) )
    rand_sorted = sorted(oos)
    win_oos = d["te"][d["win"]["pass"]]["_net"]
    better = sum(1 for x in oos if x > win_oos)
    P(f"    ★随机选参对照：从这 {n} 个候选里随机挑 1 个，它的测试段 net 优于【验证段选参结果】的概率 = "
      f"{better/n*100:.1f}%")
    P(f"      候选的测试段 net：中位 {med(oos):+.2f}  最好 {max(oos):+.2f}  最差 {min(oos):+.2f}")
P()


# ---------------------------------------------------------------- §3b 更大候选集
P("=" * 100)
P("§3b ★【事实】把候选集放宽到【只过频率门槛】（不加 net>0）—— ρ 的统计功效大得多")
P("=" * 100)
P("  理由：M15 只有 17 个 net>0 候选。n=17 时 Spearman 的 5% 临界值约 |ρ|>=0.49，−0.480 刚好卡在边缘。")
P("        改用只过频率门槛的候选集，n 大数倍，结论稳健得多。")
P()
for tf in ("m5", "m15"):
    tr = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0tr"}
    va = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0va"}
    te = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0te"}
    cand2 = [r for r in tr.values() if r["_tr"] >= 25]
    if len(cand2) < 5:
        P(f"--- {tf.upper()} ---  n={len(cand2)} 太少，跳过")
        continue
    a = [va[r["pass"]]["_net"] for r in cand2]
    b = [te[r["pass"]]["_net"] for r in cand2]
    c = [tr[r["pass"]]["_net"] for r in cand2]
    P(f"--- {tf.upper()} ---  n={len(cand2)}（只过频率门槛 trades>=25/6个月）")
    P(f"    ρ(验证段, 测试段) = {spearman(a,b):+.3f}")
    P(f"    ρ(训练段, 测试段) = {spearman(c,b):+.3f}")
    P(f"    ρ(训练段, 验证段) = {spearman(c,a):+.3f}")
    va5 = {r["pass"] for r in sorted(cand2, key=lambda r: -va[r["pass"]]["_net"])[:5]}
    te5 = {r["pass"] for r in sorted(cand2, key=lambda r: -te[r["pass"]]["_net"])[:5]}
    P(f"    验证段 top5 ∩ 测试段 top5 = {len(va5 & te5)}/5   （随机期望 ≈ {25.0/len(cand2):.2f}/5）")
    ranked_va = sorted(cand2, key=lambda r: -va[r["pass"]]["_net"])
    dec = ranked_va[:max(1, len(cand2) // 10)]
    te_rank = {r["pass"]: i for i, r in enumerate(sorted(cand2, key=lambda r: -te[r["pass"]]["_net"]))}
    P(f"    ★验证段最好的一成（{len(dec)} 个）在测试段的【平均排名】= "
      f"{sum(te_rank[r['pass']] for r in dec)/len(dec)+1:.1f} / {len(cand2)}"
      f"   （随机期望 {(len(cand2)+1)/2:.1f}）")
    P()


# ---------------------------------------------------------------- §3c 控制 EntrySigma
P("=" * 100)
P("§3c ★★★【事实】M5 的 ρ=+0.844 是真预测力，还是『EntrySigma 单调主效应』的假象？")
P("=" * 100)
P("  怀疑：M5 上 EntrySigma 越大→笔数越少→成本拖累越小，三个段都单调。")
P("        → 段间排名一致可能只是『EntrySigma 的排序在每段都一样』，与『预测力』无关。")
P("  检验：把 EntrySigma 固定住（组内 n=27），再算 ρ(验证段, 测试段)。若组内 ρ 掉到 ~0，则怀疑成立。")
P()
for tf in ("m5", "m15"):
    tr = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0tr"}
    va = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0va"}
    te = {r["pass"]: r for r in wf if r["_tf"] == tf and r["_seg"] == "w0te"}
    P(f"--- {tf.upper()} ---")
    pooled_rho = []
    for sig in ("1.2", "1.7", "2.2", "2.7"):
        g = [r for r in tr.values() if r["params"].get("InpEntrySigma") == sig and r["_tr"] >= 25]
        if len(g) < 5:
            P(f"    EntrySigma={sig:<5} n={len(g)} 太少")
            continue
        aa = [va[r["pass"]]["_net"] for r in g]
        bb = [te[r["pass"]]["_net"] for r in g]
        rho = spearman(aa, bb)
        if rho is not None:
            pooled_rho.append(rho)
        P(f"    EntrySigma={sig:<5} n={len(g):<4} ρ(验证,测试) = {rho:+.3f}" if rho is not None
          else f"    EntrySigma={sig:<5} n={len(g):<4} ρ 无法计算")
    if pooled_rho:
        P(f"    ★组内 ρ 的均值 = {sum(pooled_rho)/len(pooled_rho):+.3f}   （未控制时是全样本 ρ）")
    P()


P("=" * 100)
P("§1c ★【事实】净利差异里，『时段』与『参数』各占多少？（这决定 OOS 曲线能不能信）")
P("=" * 100)
for tf in ("m5", "m15"):
    sub = [r for r in wf if r["_tf"] == tf]
    allnet = [r["_net"] for r in sub]
    gm = sum(allnet) / len(allnet)
    sst = sum((x - gm) ** 2 for x in allnet)
    # 段间
    ssb_seg = 0.0
    for seg in ("w0tr", "w0va", "w0te"):
        g = [r["_net"] for r in sub if r["_seg"] == seg]
        ssb_seg += len(g) * ((sum(g) / len(g)) - gm) ** 2
    # 参数（用 (sigma,exitfrac,maxer,stopatr) 组合分组）
    groups = defaultdict(list)
    for r in sub:
        key = tuple(r["params"].get(k) for k in PARAMS)
        groups[key].append(r["_net"])
    ssb_par = 0.0
    for k, v in groups.items():
        ssb_par += len(v) * ((sum(v) / len(v)) - gm) ** 2
    P(f"--- {tf.upper()} ---  总体均值 = {gm:+.2f}")
    P(f"    段间方差占比   = {ssb_seg/sst*100:.1f}%     （只有 3 个段）")
    P(f"    参数间方差占比 = {ssb_par/sst*100:.1f}%     （{len(groups)} 个参数组合 × 3 段）")
    P(f"    段均值：训练 {sum(r['_net'] for r in sub if r['_seg']=='w0tr')/108:+.2f}  "
      f"验证 {sum(r['_net'] for r in sub if r['_seg']=='w0va')/108:+.2f}  "
      f"测试 {sum(r['_net'] for r in sub if r['_seg']=='w0te')/108:+.2f}")
    P()


# ---------------------------------------------------------------- §5b 毛边际 vs 点差
P("=" * 100)
P("§5b ★★★【事实】把【点差成本】从网格结果里剥出来：毛边际 与 点差 谁大？")
P("=" * 100)
USD_PER_POINT_PER_001LOT = 0.01 * 0.001 * (100000.0 / 154.099)
SPREAD_USD = 10.0 * USD_PER_POINT_PER_001LOT          # 每平掉一层（0.01 手）的往返点差成本
P(f"  口径：每平掉 1 层（0.01 手，往返 10 点）= ${SPREAD_USD:.4f}（按 154.099 折算）")
P(f"  毛边际/笔 = MT5 的 expected_payoff + ${SPREAD_USD:.4f}")
P()
P(f"{'pass':>5}{'step':>6}{'tp':>6}{'trades':>8}{'exp_payoff':>12}{'毛边际/笔':>12}{'毛边际>点差?':>14}{'总点差$':>10}{'net':>10}")
P("-" * 100)
n_pos = 0
for r in sorted(gs, key=lambda r: -num(r.get("expected_payoff"))):
    ep = num(r.get("expected_payoff"))
    gross = ep + SPREAD_USD
    if gross > 0:
        n_pos += 1
    p = r["params"]
    P(f"{r['pass']:>5}{p.get('InpGridStepPoints',''):>6}{p.get('InpTPPoints',''):>6}"
      f"{r['_tr']:>8.0f}{ep:>12.4f}{gross:>12.4f}"
      f"{('是' if gross > SPREAD_USD else '否'):>14}"
      f"{r['_tr']*SPREAD_USD:>10.1f}{r['_net']:>10.2f}")
P()
P(f"★ 25 组里【毛边际为正】的数量 = {n_pos}/25")
P(f"★ 25 组里【毛边际大于点差】（= 扣掉点差后仍有正期望）的数量 = "
  f"{sum(1 for r in gs if num(r.get('expected_payoff')) + SPREAD_USD > SPREAD_USD)}/25  "
  f"← 即 expected_payoff>0，也就是【净盈利】的数量 = {sum(1 for r in gs if r['_net']>0)}")
P()
P("  同理看 WF 的 M15 训练段（108 组）：毛边际为正的数量 = "
  f"{sum(1 for r in wf if r['_tf']=='m15' and r['_seg']=='w0tr' and r['_net']/max(r['_tr'],1) + SPREAD_USD > 0)}/108")


# ---------------------------------------------------------------- §4 参数边际
P("=" * 100)
P("§4 【事实】单参数边际效应（按参数值聚合，训练段/测试段分别看）")
P("=" * 100)
for tf in ("m5", "m15"):
    P(f"--- {tf.upper()} ---")
    for p in PARAMS:
        vals = defaultdict(lambda: {"tr": [], "te": [], "va": [], "py": []})
        for r in wf:
            if r["_tf"] != tf:
                continue
            v = r["params"].get(p)
            if v is None:
                continue
            vals[v]["tr" if r["_seg"] == "w0tr" else ("te" if r["_seg"] == "w0te" else "va")].append(r["_net"])
            if r["_seg"] == "w0tr":
                vals[v]["py"].append(r["_py"])
        P(f"  {p}:")
        for v in sorted(vals, key=lambda x: float(x)):
            d = vals[v]
            P(f"    {v:<8} 训练中位={med(d['tr']):>7.2f}  验证中位={med(d['va']):>7.2f}  "
              f"测试中位={med(d['te']):>7.2f}  训练笔/年中位={med(d['py']):>6.0f}  "
              f"训练盈利数={sum(1 for x in d['tr'] if x>0)}/{len(d['tr'])}")
    P()


# ---------------------------------------------------------------- §5 网格冒烟
P("=" * 100)
P("§5 【事实】网格 EA 冒烟 jyrg-g-smokeL（25 pass，2022.06–2023.05，只做多）")
P("=" * 100)
P(f"pass 总数 = {len(gs)}   其中 net>0 = {sum(1 for r in gs if r['_net']>0)}")
P(f"trades: min={min(r['_tr'] for r in gs):.0f}  中位={med([r['_tr'] for r in gs]):.0f}  max={max(r['_tr'] for r in gs):.0f}")
P(f"trades==0 的 pass 数 = {sum(1 for r in gs if r['_tr']==0)}")
P(f"net : min={min(r['_net'] for r in gs):.2f}  中位={med([r['_net'] for r in gs]):.2f}  max={max(r['_net'] for r in gs):.2f}")
P(f"PF  : max={max(r['_pf'] for r in gs):.3f}")
P(f"dd% : min={min(r['_dd'] for r in gs):.2f}  中位={med([r['_dd'] for r in gs]):.2f}  max={max(r['_dd'] for r in gs):.2f}")
P()
P(f"{'pass':>5}{'step':>7}{'tp':>6}{'trades':>8}{'net':>9}{'PF':>8}{'dd%':>8}{'exp_payoff':>11}")
P("-" * 100)
for r in sorted(gs, key=lambda r: -r["_net"]):
    p = r["params"]
    P(f"{r['pass']:>5}{p.get('InpGridStepPoints',''):>7}{p.get('InpTPPoints',''):>6}"
      f"{r['_tr']:>8.0f}{r['_net']:>9.2f}{r['_pf']:>8.3f}{r['_dd']:>8.2f}{num(r.get('expected_payoff')):>11.4f}")
P()

(HERE / "analysis_batch1.txt").write_text("\n".join(OUT), encoding="utf-8")
print("=" * 90)
print(f"WF passes      : {len(wf)}")
print(f"m5  train profit: {sum(1 for r in wf if r['_tf']=='m5' and r['_seg']=='w0tr' and r['_net']>0)}/108")
print(f"m15 train profit: {sum(1 for r in wf if r['_tf']=='m15' and r['_seg']=='w0tr' and r['_net']>0)}/108")
print(f"grid smoke     : {len(gs)} pass, net>0 = {sum(1 for r in gs if r['_net']>0)}, "
      f"trades median = {med([r['_tr'] for r in gs]):.0f}, net max = {max(r['_net'] for r in gs):.2f}")
print(f"report -> {HERE / 'analysis_batch1.txt'}")
print("=" * 90)
