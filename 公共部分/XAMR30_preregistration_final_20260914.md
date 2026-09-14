# `XAMR30` 正式预注册（Source of Truth）

- 提交者：DeepSeek-执行者
- 时间：2026-09-14（Asia/Shanghai）
- 依据：GPT 对 `XAF30` 草案的修订裁定
- **状态：`preregistered`。运行后不得增删变体、不得改参数、不得追加过滤器。**
- 前身（**superseded，不覆盖不删除**）：`公共部分/NEXT_FAMILY_design_memo_20260914.md`

---

## 0. family 正式定名

```
旧名（superseded）：XAF30 = Cross-Asset Filtered breakout   ← 命名与逻辑不符
★正式名：XAMR30 = Cross-Asset Mean Reversion on M30
```
理由：策略本质是**均值回归**（z-score 偏离 → 反向入场），不是 breakout。

---

## 1. 信号精确定义（实现时不得自行解释）

### 1.0 基本口径

```
交易品种   : USDJPYm   （真实券商品种）
信息品种   : XAUUSDm   （真实券商品种）
周期       : M30
时间       : server_utc_offset = 0（沿用 JSB30 实测裁定）
             ★不得重新引入 +2/+3 动态时区系统
★所有计算只使用【已经收盘】的 M30 bar
```

### 1.1 USDJPY 均值回归信号

```
对于刚收盘的 USDJPY bar t：

  EMA48_t  = EMA(48) of Close，可用截至 bar t 收盘的历史
  e_i      = Close_i − EMA48_i                        (residual)
  e_t      = Close_t − EMA48_t

  sigma_t  = sample_std( e_{t−48}, …, e_{t−1} )
             ★只使用 bar t 之前的 48 个已收盘 residual，
               不把当前 e_t 放入 sigma

  z_t      = e_t / sigma_t

  ★sigma_t <= 0  → 当天信号无效

阈值：
  V1 / V2 : |z_t| >= 1.5
  V3      : |z_t| >= 2.0
```

**交易方向**：
```
z_t > 0 → USDJPY 高于均值 → mean-reversion SHORT
z_t < 0 → USDJPY 低于均值 → mean-reversion LONG
等价于：trade_direction = −sign(z_t)
```

### 1.2 ATR regime

```
ATR14_t = ATR(14) on M30，取【已收盘】bar t 的值，用于 SL

★ATR percentile reference 不得包含当前 bar：
   使用 bar t 之前的 500 个已收盘 M30 ATR14 值
   percentile = ★nearest-rank（预注册确定）

只有  P20 <= ATR14_t <= P80  才允许产生 base signal
★500 个历史 ATR 不足 → 不交易
★不得运行以后修改 percentile 范围
```

### 1.3 XAU 跨品种信息

```
必须取得与 USDJPY signal bar t 【完全相同 M30 open timestamp】的 XAUUSDm bar

★禁止：nearest bar / forward fill / back fill / 未收盘 bar / 下一根 XAU bar

  xau_ret_t = XAU_Close_t / XAU_Open_t − 1

★若 exact timestamp bar 不存在 → signal reject：cross_asset_missing_bar
  （不得猜测）

V1 / V3 启用 cross-asset confirmation：
  z_t > 0（准备 SHORT） 要求 xau_ret_t > 0
  z_t < 0（准备 LONG）  要求 xau_ret_t < 0
  ⇒ 代码表达等价于：sign(xau_ret_t) == sign(z_t)  且  xau_ret_t != 0

V2 关闭此 filter

★注意：比较的是【USDJPY z-score 的符号】与 XAU return，
  不是比较 USDJPY 当前 bar return 与 XAU bar return。
```

---

## 2. 三个唯一允许的预注册变体

| 变体 | z threshold | cross-asset filter | TP |
|---|---|---|---|
| **`XAMR30_V1`** | **1.5** | **ON** | **0.8R** |
| **`XAMR30_V2`** | **1.5** | **OFF**（★control group） | **0.8R** |
| **`XAMR30_V3`** | **2.0** | **ON** | **0.8R** |

**❌ 禁止**：V2+V3 组合 · 额外 z threshold · 新 TP · long-only · short-only ·
weekday filter · month filter · 第三品种 · 新增技术指标

---

## 3. 执行与退出

```
★信号在 M30 bar t 【收盘以后】才能确定
★实际入场：USDJPY 下一根 M30 bar 的第一个可交易 tick
   —— 不得用 bar t 的 close 作为无滑点未来成交价

单仓
★每个 UTC 日最多一次 actual entry

SL = 1.0 × ATR14_t
TP = 0.8 × initial_SL_distance
最长持仓 = 12 根完整 M30 bar

无 trailing · 无 add-on · 无 martingale · 无 grid
```

---

## 4. 风险模型（修正原 XAF30 草案）

```
★不使用原 memo 的"固定 0.01 手"。
沿用 JSB30 已验证的统一风险框架：

目标风险        : 1.5% current equity
权威计算        : OrderCalcProfit（★Long/Short 必须分别计算）
volume step     : 券商真实规格
minimum lot     : 0.01
InpAllowMinLotOvershoot = false
若理想风险手数 < 0.01 → reject：min_lot_risk_reject
   ★不得为了增加交易数强行 0.01
最大 actual SL risk : 3% equity
OCP 失败        : fatal / audit_failed / fail-close
★成交后按 POSITION_PRICE_OPEN / POSITION_SL / actual volume 用 OCP 重算真实 initial risk
```

---

## 5. 两品种数据覆盖冻结（先于任何 TRAIN）

```
USDJPY 执行数据起点已有 2018-01-01，但 XAUUSDm 是新信息源
→ ★正式 TRAIN 起点必须按【双品种共同可用性】重新冻结
★不得手工选择"看起来漂亮"的年份

方法：Tester-only（★禁止 terminal chart CopyRates 作为权威深历史来源）
      ★禁止 CustomSymbol / CSV 回灌

对 2018-01 ~ 2024-05 的【每个月】计算：
  · USDJPY M30 bar 数
  · XAUUSD M30 bar 数
  · exact timestamp intersection 数
  · alignment_ratio = intersection / USDJPY_M30_bars

要求：每个用于 TRAIN 的完整月份 alignment_ratio >= 99%
任何 exact XAU bar 缺失 → 对应信号不可用（cross_asset_missing_bar）

★共同 TRAIN 起点（机械定义）：
  不早于 2018-01-01，找到最早一个月，使从该月起到 2024-05
  所有完整月份 alignment >= 99%，且 USDJPY 执行 M1 coverage 正常
  TRAIN start = 该月第一个实际共同可用交易 bar
★冻结后不得根据策略盈利移动

VALID = 2024-06-01 ~ 2025-05-31
★绝对禁止：2025-06-01~2026-05-31（exposed_oos）· 2026-06-01~09-30（user_holdout）
```

---

## 6. EA 与审计字段

```
新建独立 EA：dsh_XAMR30.mq5（★不得修改 JSB30 或其他旧 EA）
沿用已验证：fail-close / OCP / FileWrite 成功后登记 / unique header /
            deal ticket 去重 / 四方 source-static-INI-manifest 一致
```

### 6.1 审计字段（必须全部落盘）

```
run_tag, symbol, deal_ticket, position_id,
signal_bar_time,
entry_time, exit_time,
z_score, ema48, residual, sigma48,
atr14, atr_p20, atr_p80,
xau_bar_time, xau_open, xau_close, xau_return,
cross_asset_filter_enabled, cross_asset_filter_pass, alignment_exact,
trade_direction,
spread_at_entry_points, initial_sl_distance_points, initial_tp_distance_points,
spread_over_sl, spread_over_tp,
risk_budget, actual_initial_sl_risk,
ocp_expected_pl, deal_profit, formula_value, formula_diff,
close_type, exit_reason,
server_utc_offset
```

**★本轮必须解决 JSB30 已登记的缺口**：`spread_at_entry / initial_SL_distance`
**不得再次出现停止条件无法计算。**

### 6.2 拒单审计字段

```
run_tag, symbol, utc_day, signal_bar_time, reason,
z_score, atr14, atr_p20, atr_p80,
xau_bar_time, xau_return,
raw_lot, final_lot, risk_budget, actual_risk, ocp_err
```
`reason` 取值（预注册枚举）：
```
sigma_invalid · atr_insufficient · atr_out_of_regime ·
cross_asset_missing_bar · cross_asset_filter_fail ·
min_lot_risk_reject · risk_cap_reject · ocp_failure · day_already_traded
```

---

## 7. N0 四方 guard

```
沿用并泛化 n0_guard.py / n0_fourway.py：
  source ↔ static input table ↔ resolved INI [TesterInputs] ↔ planned manifest
名称集合完全一致 · 数值完全一致 · 未知 input fail-close
所有 run 必须先 planned 再执行
每个 run：独立 tag · 独立报告 · 独立 audit directory · 不覆盖旧结果
```

---

## 8. N1.5 engineering smoke（预先固定三窗口，只用 V1）

```
WINTER          : 2023-01-02 ~ 2023-01-31
DST-transition  : 2023-03-20 ~ 2023-04-07
SUMMER          : 2023-07-03 ~ 2023-07-31
```

**只验证工程，不评价 profitability。★必须实际产生 closing deals 才可宣称审计链 PASS。**

必查清单：
```
exact cross-symbol timestamp alignment
没有 future bar
z-score 只用已收盘数据
ATR percentile 无 look-ahead
下一 bar 才入场
OCP sizing
DEAL_PROFIT ↔ OCP <= 0.05 USD
spread 字段 / SL 字段 / TP 字段
单日 <= 1 trade
max hold 12 bars
audit reconciliation
active position = 0
fatal = 0
```

---

## 9. TRAIN（三个版本一次跑完）

```
V1 TRAIN → V2 TRAIN → V3 TRAIN（串行）
★一个版本失败不影响其他预注册 TRAIN
★全部使用同一冻结 EX5；除预注册差异外不允许其他参数不同
```

**每个 TRAIN 必须输出**：
```
net profit · PF · official Equity DD · trade count · trades/year
first/last trade · span coverage
yearly result · monthly result
long/short · win rate · avg win · avg loss · realized payoff ratio
expectancy USD/trade · expectancy R/trade
holding duration
spread/SL · spread/TP
swap · commission
risk rejects · cross_asset_missing_bar · ATR rejects
1.0x / 1.5x / 2.0x cost stress
top5/top10 winning concentration · remove top10 winning trades
top5/top10 losing concentration · remove worst10 losing trades
OCP reconciliation · alignment statistics
```

---

## 10. 策略自身停止条件（每个 variant 独立裁定）

```
沿用核心 gates：
  1  净利 > 0
  2  PF > 1
  3  official Equity DD <= 40%
  4  2× cost 后仍 > 0
  5  remove top10 winners 后仍 > 0
  6  审计完全一致
  7  不依赖少数极端单
  8  min-lot floor 不主导
  9  trade span >= 90%
 10  frequency >= 50/year
 11  median spread/SL <= 30%
 12  时间与数据自检无矛盾

XAMR30 新增：
 13  risk reject rate <= 30%
 14  双品种 exact timestamp alignment >= 99%
 15  median spread/TP <= 30%
```

**★任何硬 gate 失败 → 该 variant = `closed`，不跑它的 VALID。**

---

## 11. V1 vs V2 控制组分析（★与"策略通过"分开）

```
★删除旧草案的"|net差| < 20% 就叫差异不显著"—— 那不是统计显著性。

方法（cross_asset_effect_analysis）：
  · 把 TRAIN 每一个 UTC trading day 对齐
  · 每版本：daily_return = 当日 net P/L / 当日起始 equity
  · delta_day = V1_daily_return − V2_daily_return
  · ★20 trading-day moving block bootstrap，10,000 resamples
  · ★固定 random seed = 20260914
  · 报告：mean delta · median delta · 95% bootstrap CI

判定：
  mean delta > 0  且  95% CI lower bound > 0
     → cross_asset_effect_supported
  否则
     → cross_asset_effect_unproven

★该统计结论与单个策略的 candidate gate 【分开】：
  · V2 自己所有策略 gate 通过 → 即使跨品种假设失败，V2 仍可作独立候选进入 VALID
  · V1 自己通过但 bootstrap CI 含 0 → V1 仍可进入 VALID，
    但必须注明"策略候选成立，但不能把优势归因于 XAU filter"
★不得为了证明 cross-asset 有效而事后改变 filter
```

---

## 12. VALID（自动执行，不停下来请求批准）

```
所有 TRAIN 自身 gate 通过的 variant → 自动进入 2024-06-01 ~ 2025-05-31 VALID

必须同一：source hash · EX5 hash · inputs · risk · signal · cross-asset rule
仅允许改变：run tag · 日期 · dataset_role

VALID 失败 → 直接关闭；★禁止重新调参
```

---

## 13. 最终交付

```
生成：公共部分/XAMR30_TRAIN_VALID_最终审阅包_20260914.md
更新：公共部分/AI交流版.md（追加新 MSG）
提交 GitHub

报告必须明确给出：
  XAMR30_V1/V2/V3 各自的 TRAIN / VALID 状态
  跨品种 effect bootstrap 结论
  是否存在最终 candidate
```

---

## 14. 若 XAMR30 全部失败

```
正式：XAMR30 = closed / blocked_failed
★不要立即设计并运行第八、第九个简单规则 family
改为生成：公共部分/PROJECT_FEASIBILITY_REVIEW_20260914.md
  只使用已完成的历史实验，总结 8000+ runs、所有 family、主要失败机制、
  cost drag、min-lot floor、DD、tail dependence、risk rejection、frequency、不同标的结果
  重点回答：在 500 USD / 1:200 / 真实 retail spread / 0.01 min lot /
            禁止 exposed_oos 与 holdout 的约束下，
            "继续换简单规则 family" 是否还有足够实验依据
  提出最多 3 个下一层研究方向（只做研究设计，★不再自动启动 MT5）
若任一 VALID 真正通过 → 停止在候选审阅阶段，不做新 family
```

---

## 15. 全局禁止

```
✗ exposed_oos（2025-06-01~2026-05-31）· user_holdout（2026-06-01~09-30）
✗ 参数扫描 ✗ 按 TRAIN 结果补过滤器 ✗ long-only / short-only 事后筛选
✗ V2+V3 组合 ✗ 自建 symbol ✗ CSV 回灌 ✗ 修改历史旧 EA ✗ 真钱交易
```
