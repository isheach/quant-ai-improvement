# -*- coding: utf-8 -*-
"""
eva015_rank_robust_params.py —— 稳健参数挑选（回应"别只挑测试集最好的"）

背景：穷举寻优里，"挑测试集得分最高的一组"等于把测试集也用来训练了（数据泄漏）。
正确做法：要求 训练分 与 测试分 同时为正，并按"两者都好"来排——
本工具同时给三种稳健排序：
  - min(train,test)   ← 最稳：看最差的一头（强烈推荐做主排序）
  - geomean           ← 几何平均（你说的"乘积"的同量纲版本，不被单边量级带偏）
  - product           ← 你提议的 train×test
并标出"如果只挑测试集最高会选哪行"作对照（通常 ≠ 稳健解，即泄漏的证据）。

用法：MT5 优化时打开 Forward(前进/样本外)，把"优化结果"标签页右键导出成 CSV，
      填好下面 CONFIG 的列名，直接 Run。
"""
import pandas as pd, numpy as np

# ===================== CONFIG：只改这里 =====================
INPUT_CSV  = "opt_results.csv"   # MT5 导出的优化结果（含训练分与Forward分）
TRAIN_COL  = "Result"            # 训练段(样本内)得分列名
TEST_COL   = "Forward Result"    # 测试段(Forward/样本外)得分列名
MIN_BOTH   = 0.0                 # 训练分、测试分都必须 >= 此值（默认0：都不为负）
TOP_N      = 15
OUT_CSV    = "robust_ranked.csv"
# ===========================================================

def main():
    df = pd.read_csv(INPUT_CSV)
    if TRAIN_COL not in df.columns or TEST_COL not in df.columns:
        print(f"[err] 找不到列：{TRAIN_COL} / {TEST_COL}。现有列：{list(df.columns)}"); return
    tr = pd.to_numeric(df[TRAIN_COL], errors="coerce")
    te = pd.to_numeric(df[TEST_COL], errors="coerce")
    df = df.assign(_train=tr, _test=te).dropna(subset=["_train","_test"]).reset_index(drop=True)
    n0 = len(df)

    # 对照：只挑测试集最高（这是"泄漏"的错误做法）
    leak = df.loc[df["_test"].idxmax()]
    print(f"[对照] 只挑测试集最高那行：train={leak['_train']:.3f}, test={leak['_test']:.3f}"
          f"（若 train 很低，就是只为测试集过拟合的证据）")

    # 稳健过滤：两者都 >= MIN_BOTH
    ok = df[(df["_train"]>=MIN_BOTH) & (df["_test"]>=MIN_BOTH)].copy()
    print(f"[过滤] 总 {n0} 组 → 训练&测试都≥{MIN_BOTH} 的有 {len(ok)} 组")
    if len(ok)==0:
        print("⚠ 没有任何一组在两段都不为负 —— 这是'无稳健边缘'的强信号（见日志建议）。"); return

    ok["min_both"] = ok[["_train","_test"]].min(axis=1)
    ok["geomean"]  = np.sqrt(ok["_train"].clip(lower=0) * ok["_test"].clip(lower=0))
    ok["product"]  = ok["_train"] * ok["_test"]

    ok = ok.sort_values(["min_both","geomean"], ascending=False).reset_index(drop=True)
    show = [c for c in ok.columns if c not in ("_train","_test")]
    ok.to_csv(OUT_CSV, index=False)
    print(f"\n=== 稳健排序 Top{TOP_N}（按 min(train,test) 主排序）===")
    cols = ["_train","_test","min_both","geomean","product"]
    print(ok.head(TOP_N)[cols].round(3).to_string())
    best = ok.iloc[0]
    print(f"\n[推荐] 最稳一组：train={best['_train']:.3f}, test={best['_test']:.3f}, "
          f"min={best['min_both']:.3f}")
    print(f"明细（含参数列）→ {OUT_CSV}")

if __name__ == "__main__":
    main()
