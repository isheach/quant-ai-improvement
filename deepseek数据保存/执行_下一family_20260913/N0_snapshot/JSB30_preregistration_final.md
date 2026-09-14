# `JSB30` 正式预注册（Preregistration · Final）

- 生成者：DeepSeek-执行者
- 生成时间：2026-09-14（Asia/Shanghai）
- **Source of Truth**：`公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md`（GPT 裁定）
- 前身：`deepseek数据保存/执行_下一family_20260913/JSB30_design_memo.md`（草案，已被本文件取代）
- **状态：`preregistered_final`。运行后不得增删变体、不得改参数、不得追加过滤器。**

---

## 0. GPT 裁定与本文件的关系

本文件是 GPT 裁定 §2 的**逐字落实**，并记录**相对草案的两处关键修正**（GPT §0）：

| # | 草案原方案 | **GPT 裁定（本文件执行）** |
|---|---|---|
| **1** | TRAIN 起点定在 `2017-01-02`，**刻意避开** 2014–2016 静默期 | **TRAIN 必须从真实可用起点 `2014-01-14` 开始**；2014–2016 保留并作为 **TRAIN 内部独立诊断段** |
| **2** | 在 `OnInit` **只推导一次** `server_offset` 用于整段回测 | **否决整段固定 offset**。必须**按历史日期/交易周动态**确定 DST offset 并缓存 |

**其余裁定**：Q2 维持「每日最多一笔」（不许提高频率）；Q4 不修改历史 R4 文件、只在新代码修复并加 header 唯一性自检。

---

## 1. 研究结构（固定）

```
名称    : JSB30 = JPY Session Breakout on M30
品种    : USDJPYm（真实券商品种，Exness-MT5Trial5）
结构    : M30 时段突破（time-of-day session breakout）
仓位    : 单仓；每个 UTC 日最多一笔实际成交
禁止    : 网格、马丁、加仓、移动盈利止损、long-only/short-only 切换
```

### 1.1 固定窗口（UTC 定义，服务器时间执行）

| 变体 | range | breakout | TP | 相对 V1 的唯一差异 |
|---|---|---|---|---|
| **V1**（baseline） | UTC 00:00–06:00 | UTC 07:00–12:00 | **1.5R** | — |
| **V2** | **UTC 00:00–03:00** | UTC 07:00–12:00 | 1.5R | **只改 range end（06:00→03:00）** |
| **V3** | UTC 00:00–06:00 | UTC 07:00–12:00 | **1.0R** | **只改 TP（1.5R→1.0R）** |

```
hard-flat : UTC 20:00（无论盈亏必须平仓，exit_reason = window_end）
```
**★禁止构造 V2+V3 组合版**（GPT §2）。

### 1.2 固定研究输入（沿用草案，GPT §2 确认）

```
ATR 周期        : 14（M30）
信号周期        : M30
min range       : 0.5 × ATR14
止损            : 1.0 × ATR14（固定，不移动）
时间退出        : 最长 16 根 M30
风险模型        : InpRiskPct = 1.5；InpMinLotMaxRiskPct = 3.0；
                  InpAllowMinLotOvershoot = false
方向            : long / short 同时开放
```

---

## 2. 入场 / 出场规则（逐字固定）

```
【每日预计算】（UTC 日 D）
  R_hi(D) = max(high) over M30 bars 且 bar_close_time ∈ [D 00:00, D 06:00)  (V2: [D 00:00, D 03:00))
  R_lo(D) = min(low)  同区间
  ★只用【已收盘】的 M30 bar；当前未收盘 bar 不进入统计（GPT §4）

【入场】（仅在 breakout 窗内，且当日未成交）
  · 前置条件：range 宽度 (R_hi - R_lo) ≥ 0.5 × ATR14
  · M30 收盘价 > R_hi → 做多；M30 收盘价 < R_lo → 做空
  · 每个 UTC 日最多一笔；有仓时不看新信号
  · 风险预算不足（最小手超出）→ 拒单并写 reject_reason

【出场】（优先级从上到下）
  1. 止损：entry ∓ 1.0 × ATR14（该笔入场时的 ATR14）
  2. 止盈：entry ± 1.5R（V1/V2）或 ± 1.0R（V3），R = 该笔止损距离
  3. 时间退出：持仓满 16 根 M30 → exit_reason = time_exit
  4. hard-flat：UTC 20:00 前必须平仓 → exit_reason = window_end
```

---

## 3. 时间系统（GPT §4 的核心要求）

### 3.1 三条硬性要求

```
① UTC 定义，server 时间执行
② 按历史日期/交易周【动态】确定 DST offset，并缓存
   ★禁止整段固定 offset（GPT Q1 明确否决）
③ UTC 日切换不能用 server midnight 代替；
   DST 切换日不能重复或漏掉 UTC 日
```

### 3.2 实现方式（按交易周推导 + 缓存）

```
· 每一周由「该周第一个 M1/M30 bar 的 server 时间」推导 server_utc_offset：
    offset = known_utc_hour_of_week_open - observed_server_hour
  其中星期开盘的 UTC 时刻按外汇市场惯例为周日 22:00 UTC
· 每周只允许得到 +2 或 +3
· 推导失败 / 矛盾 / 得到其他值 → 该周标记 offset_undetermined
  → 【fail-close】：整段回测标 environment_error 并停止
  → 【不得使用默认 offset】（GPT Q1）
· offset 按周缓存（缓存键 = 周编号），供后续 bar 换算复用
```

### 3.3 round-trip 自测（N1 必须完成，GPT Q1）

必须覆盖**三类周**，每类都要 `utc -> inferred offset -> server -> recovered utc` 全一致：

```
① 冬令周
② 夏令周
③ DST 切换附近周
```
**→ 三类全部一致才能进入 N2。**

---

## 4. 数据口径与日期（GPT §1 Q3）

| 段 | 日期 | 标签 | 状态 |
|---|---|---|---|
| **TRAIN** | **2014-01-14 ~ 2024-05-31** | `train` | 运行（若 MT5 实际首 bar 稍晚，以实际首 bar 为准并登记原因） |
| **VALID** | **2024-06-01 ~ 2025-05-31** | `valid` | 仅对 TRAIN 通过者运行 |
| — | 2025-06-01 ~ 2026-05-31 | **`exposed_oos`** | **★本流程禁止读取和运行** |
| — | 2026-06-01 ~ 2026-09-30 | **`user_holdout`** | **★AI 禁止读取、回测、调参** |

### 4.1 ★2014–2016 独立诊断段（GPT Q3 要求）

```
2014–2016 不删除，作为 TRAIN 内部独立诊断段。
必须报告：
  · bars
  · 有效 range day
  · signal 数
  · reject 数
  · actual trade 数
  · ★no-trade reason（为什么没有交易或交易稀少）
```

---

## 5. 停止条件（GPT §6，逐条固定）

**任一出现即关闭该变体，不跑其 VALID**：

```
 1. 净利 <= 0
 2. PF <= 1
 3. official Equity DD > 40%
 4. 2× 成本压力后转负
 5. 去前 10 大盈利单后转负
 6. 报告 / audit / 成本对账不一致
 7. 主要收益依赖少数极端单
 8. 最小手风险地板主导结果
 9. 成交跨度 < 90% 且无法解释为正常市场可交易性
10. 平均频率 < 50 笔/年
11. spread / initial SL distance 中位数 > 30%
12. 真实 run 的 DST / time selfcheck 出现矛盾
```

**DD 分级（仅描述，不改变停止条件）**：
```
DD <= 20%        : 首选候选
20% < DD <= 40%  : high-risk candidate（即使继续 VALID 也只能标这个）
DD > 40%         : 失败
```

---

## 6. TRAIN 必报指标（GPT §6）

```
net profit · PF · official Equity DD · trades/year · first/last trade · span coverage
逐年：净利 / PF / 笔数
long vs short
持仓时间
spread / 初始 SL 距离
swap / commission
reject reason 分布
1.0× / 1.5× / 2.0× 成本压力
top5 / top10 收益集中度
remove-top-10 结果
2014–2016 no-trade 原因
```

---

## 7. 审计字段（GPT §4 指定的唯一字段集）

```
deal_ticket, position_id,
entry_time_server, entry_time_utc,
exit_time_server,  exit_time_utc,
entry, exit, volume,
profit, swap, commission, net,
close_type, exit_reason,
risk_budget, actual_sl_risk, reject_reason,
server_utc_offset
```

### 7.1 必须 selfcheck（GPT §4）

```
· header 唯一（★修复 R4 的重复 entry_time bug）
· closing deal ticket 唯一
· position 可回溯
· HTML 与 audit 净利一致
· 成本字段相加一致（profit + swap + commission = net）
· 结束时无活动仓位
· 每个 UTC 日 actual trade <= 1
· window_end 可追踪
· ★FileWrite 成功后才登记为已写
```

### 7.2 下游解析器（GPT §4 Q4）

```
· 历史 R4 文件【不修改、不重导】
· 新解析器发现【重复 header 立即失败】（fail-close）
· 报告注明：历史 R4 存在此 bug，JSB30 已修复
```

---

## 8. 编译与冻结要求（GPT §4）

```
· 0 errors / 0 warnings
· 记录 source SHA-256
· 记录 EX5 SHA-256
· ★三个 TRAIN 使用【同一 EX5】，仅预注册输入不同
· 任何影响策略行为或经济审计字段的修复 → 必须重新 N1、重新 hash、重新登记
```

---

## 9. 闸门顺序（GPT §9）

```
N0    只读快照与护栏（本文件 + 3 份配套）           ← 当前阶段
N1    新 EA（dsh_JSB30.mq5）+ 静态审计 + round-trip 自测 + 编译冻结
N1.5  最小工程 smoke（只验时间系统/DST/CSV schema/FileWrite/每日一笔/hard-flat/审计链）
N2    串行跑 V1 TRAIN → V2 TRAIN → V3 TRAIN（每段后立即裁决）
N3    只对 TRAIN 通过者跑 VALID（2024-06-01~2025-05-31）
N3 后 停止，生成最终审阅包
```

### 9.1 N1.5 的禁区（GPT §5）

```
✗ 用 smoke 盈利调整参数
✗ 用 smoke 选择时段
✗ 用 smoke 比较 V1/V2/V3
✗ 读取 exposed_oos 或 user_holdout
```

---

## 10. 全局禁止事项

```
✗ 参数扫描
✗ 读取 exposed_oos（2025-06-01~2026-05-31）
✗ 读取用户留白（2026-06-01~2026-09-30）
✗ 修改任何旧 EA
✗ 重开 MR30 / C1 / C2 / C3
✗ 根据 TRAIN 结果新增 long-only / short-only / 星期或月度过滤 / 额外指标 / 新 ATR 门槛
✗ 构造 V2+V3 组合版
✗ 真钱下单
```

---

## 11. 本轮研究目的（GPT §末段）

> **本轮目的不是把 JSB30 调到盈利，而是对一个低自由度的新 family 做可复核、可证伪的历史研究。
> 若被否证，就关闭，不根据结果补规则。**

**★这条是本文件所有条款的最终依据。**
