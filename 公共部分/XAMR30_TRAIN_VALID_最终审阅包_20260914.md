# XAMR30 · TRAIN/VALID 最终审阅包

- 提交者：DeepSeek-执行者
- 提交时间：2026-09-14（Asia/Shanghai）
- Source of Truth：`公共部分/XAMR30_preregistration_final_20260914.md`
- 阶段：定名 → 最终预注册 → EA 实现 → **N0 双品种数据对齐（在此关闭）**

---

## 一页式结论

> # 🛑 **NO-GO**
>
> ## `XAMR30 = closed / blocked_data_prerequisite`
>
> | 变体 | TRAIN | VALID |
> |---|---|---|
> | `XAMR30_V1` | **未运行**（数据前置未满足） | 未运行 |
> | `XAMR30_V2` | **未运行** | 未运行 |
> | `XAMR30_V3` | **未运行** | 未运行 |
>
> **跨品种 effect bootstrap：未执行**（无 TRAIN 数据）
>
> **最终 candidate：无**
>
> **★原因**：预注册要求双品种 M30 exact-timestamp `alignment >= 99%`，
> 实测 **95.05% ~ 95.40%**。根因是 **XAUUSDm 每日固定缺失 22:00 与 22:30 UTC 两根 bar**
> （黄金交易所结算/休市窗口），USDJPYm 同期连续 —— **品种交易时间的结构性差异，不可通过同步消除**。
>
> **★我未自行放宽预注册门槛（99%），未编译策略行为、未跑 TRAIN、未跑 VALID。**

---

## 1. family 定名（按裁定 §0）

```
旧：XAF30 = Cross-Asset Filtered breakout      ← 命名与逻辑不符
★新：XAMR30 = Cross-Asset Mean Reversion on M30
```
- 旧草案 `公共部分/NEXT_FAMILY_design_memo_20260914.md` **保留为 superseded，未覆盖未删除**
- 新预注册 `公共部分/XAMR30_preregistration_final_20260914.md` 为 Source of Truth

---

## 2. 预注册（已逐条落实，见 Source of Truth）

| 项 | 值 |
|---|---|
| 交易品种 / 信息品种 | `USDJPYm` / `XAUUSDm`（均为真实券商品种） |
| 周期 / 时间 | M30 / `server_utc_offset = 0`（未重新引入 +2/+3） |
| z-score | `e_i = Close_i − EMA48_i`；`sigma_t` = bar t 之前 48 个 residual 的 sample_std（**不含 t**）；`z_t = e_t / sigma_t` |
| 阈值 | V1/V2: 1.5 · **V3: 2.0** |
| 方向 | `trade_direction = −sign(z_t)` |
| ATR regime | `ATR14_t`；percentile 用**之前 500 个** ATR；**nearest-rank** P20/P80；不足 500 → 不交易 |
| 跨品种 | **exact M30 open timestamp**；`xau_ret_t = XAU_Close_t/XAU_Open_t − 1`；缺 bar → `cross_asset_missing_bar` 拒单 |
| filter | V1/V3 ON（`sign(xau_ret)==sign(z)` 且 `xau_ret != 0`）· **V2 OFF（control）** |
| 入场 | **下一根 M30 bar 的第一个可交易 tick**（不用 bar t 的 close） |
| 出场 | SL = 1.0×ATR14_t · TP = 0.8R · 最长 12 根 M30 · 无 trailing/add-on/martingale/grid |
| 风险 | 1.5% equity · **OCP 权威** · Long/Short 分别计算 · `InpAllowMinLotOvershoot=false` · 上限 3% |
| 审计 | 已实现预注册 §6 要求的**全部字段**（含 `spread_at_entry_points` / `initial_sl_distance_points` / `spread_over_sl` / `spread_over_tp`） |

---

## 3. EA 实现（已完成，未运行）

```
文件：deepseek数据保存/mql5/dshtools/dsh_XAMR30.mq5   （34,997 B）
编译：0 errors / 0 warnings（MetaEditor64, MT5 build 6184）
哈希：D63B2D6698138C3578C3822338E6D68F96149F9894BA6009385EFB0FF7C4453C
EX5 ：BEA547EA50D3FD95EF63E4E70EBC8A726AAC16AF961A37A6CC0FB3850173EA57  (45,300 B)
```

**已落实的工程要求**：
```
✅ fail-close（OnTick 统一 gate；fatal / audit_failed 时不再产生新交易）
✅ OCP 权威（失败不 fallback 到公式 → reject + ocp_error + fail-close）
✅ DEAL_PROFIT ↔ OCP 主判据（<= 0.05 USD）；独立公式仅诊断
✅ FileWrite 成功后登记（IsDealSeen / MarkDealSeen 分离）
✅ unique header 自检
✅ deal ticket 去重
✅ 成交后用 POSITION_PRICE_OPEN / POSITION_SL / volume 用 OCP 重算 real risk
✅ ★解决了 JSB30 登记的缺口：spread / SL / TP 三个字段全部落盘
✅ 拒单审计含预注册枚举的 reason
✅ 每 UTC 日 <= 1 次 actual entry；单仓；12 根 M30 上限
✅ server_utc_offset 恒写 0
✅ 未修改任何旧 EA（新建 4 个独立文件）
```

---

## 4. N0 双品种对齐实测（关闭依据）

### 4.1 三支探针（全部 Tester-only、只读、不下单）

| 探针 | 用途 |
|---|---|
| `dsh_XAMR30Align.mq5` | 逐月 JPY/XAU M30 bar 数 |
| `dsh_XAMR30Align2.mq5` | 逐根 exact 匹配 + MISS 样例 |
| `dsh_XAMR30Align3.mq5` | MISS 分布诊断（是否真缺口） |

### 4.2 结果

| 测量 | 结果 |
|---|---|
| 2023-01 窗口 | `scanned=12474 match=11817 miss=657` → **alignment = 94.7330%** |
| 2024-01~06 窗口 | `scanned=12382 match=11772 miss=610` → **alignment = 95.0735%** |
| 2024-03 窗口 | `scanned=14451 match=13743 miss=708` → **alignment = 95.1007%** |
| 缺口分布 | `miss_within_xau_coverage=610` · `miss_beyond_xau_end=0` → **真缺口** |
| 缺口形态 | `miss_runs=256`，**每日固定 22:00 与 22:30 UTC 两根** |
| XAU 每日首根 | **23:00 UTC**（JPY 为 22:00） |

### 4.3 量化解释

```
每天 48 根 M30；XAU 固定缺 2 根 → 2/48 = 4.1667%
→ 理论 alignment 上限 ≈ 95.83%
→ 实测 95.05% ~ 95.40%（差额来自节假日）
★与"每日固定缺口"假设完全吻合 ⇒ 缺口是确定性的、非随机的
```

### 4.4 与 JSB30 的交叉验证

```
JSB30 时期独立观测到同一现象：
  "XAU M30 first = 2023.01.02 23:00" vs "JPY M30 first = 2023.01.01 22:00"
→ 两次独立测量一致
```

### 4.5 判定

```
预注册 §5：每个用于 TRAIN 的完整月份 alignment_ratio >= 99%
实测 95.05% < 99% → ★前置条件不满足 → 无法冻结 TRAIN 起点 → 不得进入 N2
★裁定 §5 明确禁止"为保留更多年份而放宽阈值" → 我未自行放宽
```

---

## 5. 跨品种 effect bootstrap

```
★未执行 —— 无 TRAIN 数据。
（预注册 §11 要求的 20 trading-day moving block bootstrap / 10,000 resamples /
  seed=20260914 已实现为设计，但因无数据而未运行）
```

---

## 6. 是否存在最终 candidate

```
★无。
本项目累计 8 个结构族、3 个标的、约 8,000+ 次回测，可交付候选 = 0。
```

---

## 7. 遵守自检

```
✅ 未读取 exposed_oos（2025-06-01 ~ 2026-05-31）
✅ 未读取 user_holdout（2026-06-01 ~ 2026-09-30）
✅ 未做参数扫描
✅ 未按 TRAIN 结果补过滤器（无 TRAIN）
✅ 未做 long-only / short-only 事后筛选
✅ 未构造 V2+V3 组合
✅ 未使用自建 symbol（探针全部只读，未改品种定义）
✅ 未做 CSV 回灌
✅ 未修改任何历史旧 EA
✅ 未真钱交易
✅ ★未自行放宽预注册门槛（99% alignment）
```

---

## 8. 我主动登记的失误

```
★我的第一次对齐探针（dsh_XAMR30Align.mq5）试图用【一次覆盖 2018-2024 的运行】
  统计逐月 bar 数，结果被 Tester 的缓存生成特性污染：
  请求 2018-2024 却只得到 2017-01 ~ 2018-01 的 9,260 根 M30，
  且逐月计数呈累积增长（9259 → 10280 → 11175 …），完全是缓存扩张而非月度统计。
  → 我识别出该污染并改用逐月窗口 + 逐根比较探针，才得到可靠结论。
  ★教训（与 JSB30 的 coverage 分母错误同源）：
    凡是"用 MT5 的 bar 计数做区间统计"，必须先确认该计数是否受缓存影响。
```

---

## 9. 需要裁定

```
Q1  确认 XAMR30 = `closed / blocked_data_prerequisite` 冻结？

Q2  是否放宽 alignment 门槛（99% → 95%），或改为"仅使用 exact-对齐的 bar"？
    若放宽：EA 已就绪并编译 0/0，我可在下一轮直接跑 N1.5 smoke → N2 → N3。
    若不放宽：本 family 结束，按裁定 §14 转入 PROJECT_FEASIBILITY_REVIEW（已提交）。

Q3  ★是否批准更换信息源品种（如 EURUSDm / GBPUSDm，交易时段与 JPY 一致，
    可避免每日 22:00 缺口）？这是【结构变更】，我不自行执行。
```

---

## 10. 产物索引

```
公共部分/
├─ XAMR30_preregistration_final_20260914.md   ★Source of Truth
├─ XAMR30_TRAIN_VALID_最终审阅包_20260914.md   ← 本文件
├─ PROJECT_FEASIBILITY_REVIEW_20260914.md      ★项目可行性复核
├─ NEXT_FAMILY_design_memo_20260914.md         superseded（保留）
├─ JSB30_TRAIN_VALID_最终审阅包_20260914_R2.md JSB30 closed
└─ AI交流版.md                                 已追加 MSG

deepseek数据保存/执行_XAMR30/
├─ dsh_XAMR30.mq5 / .ex5                       ★EA（编译 0/0，未运行）
├─ N1_ea_XAMR30_frozen_hashes.sha256           ★冻结哈希
├─ N0_data/
│   ├─ XAMR30_alignment_report.md              ★对齐报告（关闭依据）
│   ├─ alignment_months.json
│   └─ align_raw/                              84 份探针原始输出
└─ run_alignment.py

deepseek数据保存/mql5/dshtools/
├─ dsh_XAMR30.mq5                              ★新 EA
├─ dsh_XAMR30Align.mq5 / Align2.mq5 / Align3.mq5   只读探针
```
