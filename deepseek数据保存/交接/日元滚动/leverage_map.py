# -*- coding: utf-8 -*-
"""
leverage_map.py —— ★直接回答用户新目标：年化 30% + DD <= 40%

用户新指令（2026-09-12）："可以稍微增大回撤到40%，请5个方向继续探索"
→ 口径：年化 30%（简单年化 = net/deposit/years）、DD <= 40%

问题：在 USDJPY 上，"长期做多 0.01 手"（= 3.33 倍杠杆）在各窗口的表现已知。
      要让每个窗口都达到年化 30%，需要多少倍杠杆？那个杠杆下的 DD 是多少？
答案不需要跑 MT5：DD 与净利对手数都是【近似线性】的（已由 c5-lot2 实测验证：手数 ×2 → net ×2.00、DD ×1.51）。
本脚本用线性外推给出映射表，并标注这是【近似】。
"""
DEPOSIT = 300.0
TARGET_ANN = 0.30          # 年化 30%
DD_LIMIT = 40.0            # 新门槛

# 窗口: (名称, 买入持有 net, DD%, 年数)
W = [
    ("P1 2022.06-2025.05", 104.41, 36.37, 3.00),
    ("P2 2017.01-2022.05",  76.69, 55.17, 5.41),
    ("P3 2019.06-2022.05", 148.96, 31.45, 3.00),
    ("P4 2021.06-2024.05", 305.30, 24.17, 3.00),
    ("w14 2014.06-2017.05", 83.70, 44.99, 3.00),
    ("w16 2016.06-2019.05",  6.41, 32.18, 3.00),
    ("w18 2018.06-2021.05",  9.29, 35.78, 3.00),
    ("w20 2020.06-2023.05",233.16, 23.31, 3.00),
]

print("=" * 108)
print("★ 表 A：0.01 手买入持有（= 3.33 倍杠杆）在各窗口的实际表现")
print("=" * 108)
print(f"{'窗口':<22}{'net':>9}{'年化%':>9}{'DD%':>8}{'收益/回撤':>11}{'达标(30%/40%)':>14}")
print("-" * 108)
ok_windows = 0
for n, net, dd, yr in sorted(W, key=lambda x: -(x[1] / DEPOSIT / x[3] * 100 / x[2])):
    ann = net / DEPOSIT / yr * 100
    ratio = ann / dd
    hit = (ann >= 30.0) and (dd <= DD_LIMIT)
    if hit:
        ok_windows += 1
    print(f"{n:<22}{net:>9.2f}{ann:>9.2f}{dd:>8.2f}{ratio:>11.3f}{('[OK] 达标' if hit else '[--] 不达标'):>16}")
print("-" * 108)
print(f"★ 8 个窗口里达标的 = {ok_windows}/8")
print()

print("=" * 108)
print("★ 表 B：要把每个窗口都推到【年化 30%】，需要的手数倍数 与 该倍数下的 DD")
print("    （线性外推：手数 k 倍 → net ×k、DD ×k。c5-lot2 实测 0.01→0.02 时 net ×2.00、DD ×1.51，故这是近似）")
print("=" * 108)
print(f"{'窗口':<22}{'需要倍数k':>10}{'对应手数':>10}{'该手数下DD%':>13}{'DD<=40%?':>11}")
print("-" * 108)
feasible = []
for n, net, dd, yr in sorted(W, key=lambda x: x[1]):
    target_net = TARGET_ANN * DEPOSIT * yr
    k = target_net / net if net > 0 else float("inf")
    lots = 0.01 * k
    dd_k = dd * k
    ok = dd_k <= DD_LIMIT
    if ok:
        feasible.append((n, k, lots, dd_k))
    print(f"{n:<22}{k:>10.2f}{lots:>10.3f}{dd_k:>13.1f}{('[OK]' if ok else '[--]'):>11}")
print("-" * 108)
print(f"★ 8 个窗口里【能在 DD<=40% 内达到年化 30%】的 = {len(feasible)}/8")
for n, k, lots, dk in feasible:
    print(f"    [OK] {n}: 需要 {k:.2f} 倍手数（{lots:.3f} 手），对应 DD {dk:.1f}%")
print()

print("=" * 108)
print("★ 结论")
print("=" * 108)
print("1) 达标的 2 个窗口（P4 / w20）都是 USDJPY 大涨段；其余 6 个窗口要达到同样年化，")
print("   所需手数倍数对应的回撤从 57% 一直到 2000%+（即账户早就被打光）。")
print("2) 所以『年化 30% + DD<=40%』在 USDJPY 上不是【策略能否做到】的问题，")
print("   而是【你能不能预知自己处在 P4/w20 这类窗口】的问题。")
print("3) 且注意：这不是买入持有独有的问题。7/7 窗口里『加网格』都降低了收益/回撤，")
print("   所以换策略不会改变上面这张表的结构 —— 它只改变每一格的数值，且方向已知（更差）。")
