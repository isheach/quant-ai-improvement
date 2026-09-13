# -*- coding: utf-8 -*-
"""
analyze_batch4.py —— 0 tick vs 1 tick 的对照分析：报告_002 里哪些数字要重述

背景：报告_002 的全部数据跑在 InpLatencyTicks=1（≈60 秒延迟）。
      grid4 = 与 W0 逐项相同、仅 InpLatencyTicks 1→0 的重测。
      本脚本把两者并排算，逐条判定"哪些结论变了、哪些没变"。
输出 analysis_batch4.txt
"""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = []
def P(s=""): OUT.append(str(s))

PARAMS = ["InpEntrySigma", "InpExitFrac", "InpMaxER", "InpStopATR"]
SEGNAME = {"tr": "训练段", "va": "验证段", "te": "测试段(OOS)"}


def load(p):
    rows = []
    for ln in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("pass") is None:
            continue
        r["_net"] = float(r.get("net") or 0)
        r["_pf"] = float(r.get("profit_factor") or 0)
        r["_tr"] = float(r.get("trades") or 0)
        r["_dd"] = float(r.get("dd_pct") or 0)
        g = r["grid_id"]
        r["_tf"] = "m5" if g.endswith("m5") or g.endswith("m5-0t") else "m15"
        r["_seg"] = g.split("-")[1][2:]           # w0tr -> tr
        r["_tick"] = 0 if g.endswith("-0t") else 1
        rows.append(r)
    return rows


one = load(HERE / "outbox_日元滚动.jsonl")            # 1 tick（原 W0）
zero = load(HERE / "outbox_日元滚动_grid4.jsonl")      # 0 tick（grid4）
P("=" * 104)
P("0 tick vs 1 tick 对照分析（InpLatencyTicks 1→0，其余逐项相同）")
P("=" * 104)
P(f"1 tick 行数 = {len(one)}   0 tick 行数 = {len(zero)}")
P()


def med(v):
    v = sorted(v)
    if not v: return 0.0
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


# ---------------------------------------------------------------- §1 并排
P("=" * 104)
P("§1 【事实】逐网格并排：盈利数 / net / PF / 笔数 / dd")
P("=" * 104)
P(f"{'网格':<18}{'tick':>5}{'盈利数':>7}{'net中位':>10}{'net最好':>10}{'net最差':>10}"
  f"{'PF最好':>9}{'笔数中位':>9}{'dd中位':>9}")
P("-" * 104)
for tf in ("m5", "m15"):
    for seg in ("tr", "va", "te"):
        for tk, ds in ((1, one), (0, zero)):
            g = [r for r in ds if r["_tf"] == tf and r["_seg"] == seg]
            if not g: continue
            P(f"{'w0'+seg+'-'+tf:<18}{tk:>5}{sum(1 for r in g if r['_net']>0):>7}"
              f"{med([r['_net'] for r in g]):>10.2f}{max(r['_net'] for r in g):>10.2f}"
              f"{min(r['_net'] for r in g):>10.2f}{max(r['_pf'] for r in g):>9.3f}"
              f"{med([r['_tr'] for r in g]):>9.0f}{med([r['_dd'] for r in g]):>9.1f}")
P()

# ---------------------------------------------------------------- §2 ρ
def rank(v):
    idx = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0]*len(v); i = 0
    while i < len(idx):
        j = i
        while j+1 < len(idx) and v[idx[j+1]] == v[idx[i]]: j += 1
        avg = (i+j)/2.0 + 1.0
        for k in range(i, j+1): r[idx[k]] = avg
        i = j+1
    return r


def spearman(a, b):
    if len(a) < 3: return None
    ra, rb = rank(a), rank(b); n = len(a)
    ma, mb = sum(ra)/n, sum(rb)/n
    cov = sum((ra[i]-ma)*(rb[i]-mb) for i in range(n))
    va = sum((x-ma)**2 for x in ra)**0.5; vb = sum((x-mb)**2 for x in rb)**0.5
    return None if va == 0 or vb == 0 else cov/(va*vb)


P("=" * 104)
P("§2 ★★★【事实】ρ 解剖在 0 tick 下的重算（这是报告_002 §B 的核心）")
P("=" * 104)
P("口径：候选 = 训练段 trades>=25（>=50 笔/年）的同空间配置；三段按 pass 对齐")
P()
for tk, ds in ((1, one), (0, zero)):
    P(f"——— InpLatencyTicks = {tk} ———")
    for tf in ("m5", "m15"):
        tr = {r["pass"]: r for r in ds if r["_tf"] == tf and r["_seg"] == "tr"}
        va = {r["pass"]: r for r in ds if r["_tf"] == tf and r["_seg"] == "va"}
        te = {r["pass"]: r for r in ds if r["_tf"] == tf and r["_seg"] == "te"}
        if not tr or not va or not te:
            continue
        cand = [r for r in tr.values() if r["_tr"] >= 25]
        if len(cand) < 5:
            P(f"  {tf.upper()}: 候选 {len(cand)} 太少"); continue
        a = [va[r["pass"]]["_net"] for r in cand]
        b = [te[r["pass"]]["_net"] for r in cand]
        c = [tr[r["pass"]]["_net"] for r in cand]
        P(f"  {tf.upper()}  n={len(cand):<4} ρ(验证,测试)={spearman(a,b):+.3f}   "
          f"ρ(训练,测试)={spearman(c,b):+.3f}   ρ(训练,验证)={spearman(c,a):+.3f}")
        # 组内（固定 EntrySigma）
        grp = []
        for sig in ("1.2", "1.7", "2.2", "2.7"):
            gg = [r for r in cand if r["params"].get("InpEntrySigma") == sig]
            if len(gg) >= 5:
                rho = spearman([va[r["pass"]]["_net"] for r in gg],
                               [te[r["pass"]]["_net"] for r in gg])
                if rho is not None: grp.append((sig, rho, len(gg)))
        if grp:
            P("        组内(固定EntrySigma) ρ: " +
              "  ".join(f"σ{s}={v:+.3f}(n={n})" for s, v, n in grp) +
              f"   → 均值 {sum(v for _, v, _ in grp)/len(grp):+.3f}")
        # 验证段选参 vs 随机
        cand_pos = [r for r in cand if r["_net"] > 0]
        if cand_pos:
            win = max(cand_pos, key=lambda r: va[r["pass"]]["_net"])
            oos = [te[r["pass"]]["_net"] for r in cand_pos]
            wv = te[win["pass"]]["_net"]
            better = sum(1 for x in oos if x > wv)
            P(f"        验证段选参(pass={win['pass']}) → 测试 {wv:+.2f}；"
              f"候选里测试段优于它的比例 = {better}/{len(oos)} = {better/len(oos)*100:.1f}%")
            trbest = max(cand_pos, key=lambda r: r["_net"])
            P(f"        对照【跳过验证段，用训练段第1名】pass={trbest['pass']} → 测试 {te[trbest['pass']]['_net']:+.2f}")
        else:
            P("        训练段无 net>0 候选 → 预登记选参规则结构性无法启动")
    P()

# ---------------------------------------------------------------- §3 段效应
P("=" * 104)
P("§3 【事实】段效应 vs 参数效应（0 tick 下重算）")
P("=" * 104)
for tk, ds in ((1, one), (0, zero)):
    P(f"——— InpLatencyTicks = {tk} ———")
    for tf in ("m5", "m15"):
        sub = [r for r in ds if r["_tf"] == tf]
        if not sub: continue
        segs_present = [s for s in ("tr", "va", "te") if any(r["_seg"] == s for r in sub)]
        if len(segs_present) < 3:
            P(f"  {tf.upper()}  只跑了 {segs_present} 段 → 段效应无法分解（跳过，不算 0）")
            continue
        allv = [r["_net"] for r in sub]; gm = sum(allv)/len(allv)
        sst = sum((x-gm)**2 for x in allv)
        ssb = 0.0
        for seg in ("tr", "va", "te"):
            g = [r["_net"] for r in sub if r["_seg"] == seg]
            if g: ssb += len(g)*((sum(g)/len(g))-gm)**2
        groups = defaultdict(list)
        for r in sub:
            groups[tuple(r["params"].get(k) for k in PARAMS)].append(r["_net"])
        ssp = sum(len(v)*((sum(v)/len(v))-gm)**2 for v in groups.values())
        means = {s: (sum(r['_net'] for r in sub if r['_seg'] == s) /
                     max(1, len([r for r in sub if r['_seg'] == s]))) for s in ("tr", "va", "te")}
        P(f"  {tf.upper()}  总体均值={gm:+.2f}  段间方差={ssb/sst*100:.1f}%  参数间方差={ssp/sst*100:.1f}%")
        P(f"        段均值: 训练 {means['tr']:+.2f}  验证 {means['va']:+.2f}  测试 {means['te']:+.2f}"
          f"   → 最好的是【{'训练' if means['tr']==max(means.values()) else ('验证' if means['va']==max(means.values()) else '测试')}段】")
    P()

(HERE / "analysis_batch4.txt").write_text("\n".join(OUT), encoding="utf-8")
print("=" * 84)
for tk, ds in ((1, one), (0, zero)):
    n = sum(1 for r in ds if r["_net"] > 0)
    print(f"ticks={tk}: {len(ds)} pass, 盈利 {n}")
print(f"report -> {HERE/'analysis_batch4.txt'}")
print("=" * 84)
