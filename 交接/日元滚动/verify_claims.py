# -*- coding: utf-8 -*-
"""verify_claims.py —— 核验 报告_001 里的两处事实断言（不核验就不许写进报告）"""
import json
from collections import Counter
from pathlib import Path

OUT = Path(r"D:\desktop\新量化策略\deepseek数据保存\交接\outbox_日元.jsonl")

rows = []
for ln in OUT.read_text(encoding="utf-8", errors="replace").splitlines():
    ln = ln.strip()
    if not ln:
        continue
    try:
        rows.append(json.loads(ln))
    except Exception:
        pass

grid = [r for r in rows if r.get("grid_id") and r.get("trades") is not None]
single = [r for r in rows if r.get("req_id")]

print(f"总解析行      : {len(rows)}")
print(f"grid pass 行  : {len(grid)}")
print(f"逐条运行行    : {len(single)}")
print()

# --- 断言 A：691 个 grid pass 全部 expert == jpyrev（或含 trend 的 jpyg-025/012/002 等）---
print("--- 断言A：grid pass 的 expert 分布 ---")
c = Counter(r.get("expert", "<缺失>") for r in grid)
for k, v in c.most_common():
    print(f"    expert={k:<10} {v}")
print()

# --- 断言 B：没有任何 grid pass 的 to 晚于 2022.05.31 ---
print("--- 断言B：grid pass 的 from/to 分布 ---")
spans = Counter((r.get("from"), r.get("to")) for r in grid)
for (f, t), v in spans.most_common():
    print(f"    {f} → {t}   n={v}")
late = [r for r in grid if (r.get("to") or "") > "2022.05.31"]
print(f"    ★ to 晚于 2022.05.31 的 grid pass 数 = {len(late)}")
for r in late[:10]:
    print("       ", r.get("grid_id"), r.get("pass"), r.get("from"), r.get("to"))
print()

# --- 断言 C：逐条运行（req_id）的窗口分布（这批覆盖到 2024.05.31，但成交只从 2017.04 起）---
print("--- 断言C：逐条运行的 from/to 分布 ---")
spans2 = Counter((r.get("from"), r.get("to")) for r in single)
for (f, t), v in spans2.most_common(10):
    print(f"    {f} → {t}   n={v}")
print()

# --- 断言 D：前一条线"两族无正期望"的复核（≥50 笔/年的最好 PF）---
print("--- 断言D：复核 报告_005 §1.1（≥50 笔/年 的最好 PF 与 PF>1 的数量）---")
WINDOW_YEARS = 5.41
best = None
n_over50 = 0
n_pf_gt1 = 0
for r in grid:
    try:
        tr = float(r["trades"])
        pf = float(r["profit_factor"]) if r.get("profit_factor") not in ("", None) else 0.0
    except Exception:
        continue
    py = tr / WINDOW_YEARS
    if py >= 50.0:
        n_over50 += 1
        if best is None or pf > best[0]:
            best = (pf, r.get("grid_id"), r.get("pass"), tr, py,
                    r.get("net"), r.get("params"))
        if pf > 1.0:
            n_pf_gt1 += 1
print(f"    ≥50 笔/年 的 pass 数 = {n_over50}")
print(f"    其中 PF>1.0 的数量   = {n_pf_gt1}")
if best:
    print(f"    最高 PF = {best[0]:.4f}  ({best[1]} pass {best[2]})  笔数={best[3]:.0f}  笔/年={best[4]:.1f}  "
          f"net={best[5]}  params={best[6]}")
print(f"    （报告_005 声称：298 个 / PF>1 = 0 / 最高 PF 0.859）")
print()

# --- 断言 E：jpyg-034 pass3 是否真的是旧窗口最好 PF ---
print("--- 断言E：jpyg-034 pass3 的实际值（报告_001 §3.2 的复现锚点）---")
for r in grid:
    if r.get("grid_id") == "jpyg-034" and str(r.get("pass")) == "3":
        print("   ", json.dumps({k: r.get(k) for k in
              ("grid_id","pass","params","net","profit_factor","trades","dd_pct","from","to")},
              ensure_ascii=False))
ranked = []
for r in grid:
    try:
        pf = float(r["profit_factor"]) if r.get("profit_factor") not in ("", None) else 0.0
        tr = float(r["trades"])
    except Exception:
        continue
    ranked.append((pf, tr, r.get("grid_id"), r.get("pass"), r.get("params"), r.get("dd_pct")))
ranked.sort(reverse=True)
print("    全 691 pass 里 PF 最高的 5 个：")
for pf, tr, gid, ps, pa, dd in ranked[:5]:
    print(f"      PF={pf:.4f} trades={tr:.0f} dd={dd} {gid} pass {ps} {pa}")
print("    其中 trades>=200 的最高 3 个：")
k = 0
for pf, tr, gid, ps, pa, dd in ranked:
    if tr >= 200:
        print(f"      PF={pf:.4f} trades={tr:.0f} dd={dd} {gid} pass {ps} {pa}")
        k += 1
        if k >= 3:
            break
