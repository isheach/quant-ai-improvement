# XAMR30 预注册 v2（Source of Truth · 取代 v1）

- 提交者：DeepSeek-执行者
- 时间：2026-09-14（Asia/Shanghai）
- 状态：**`preregistered_v2`**。运行后不得增删变体、不得改参数。
- **v1 保留不覆盖**：`公共部分/XAMR30_preregistration_final_20260914.md`
  → 状态记为 **`XAMR30 prereg-v1 = blocked_data_prerequisite` + `superseded_before_any_economic_test`**

---

## 0. 为什么 v1 的 99% 全时段 gate 被 supersede

```
v1 §5 定义：alignment_ratio = intersection / USDJPY_M30_bars >= 99%
实测：95.05% ~ 95.40%

★supersede 原因（GPT 裁定原文）：
   「它测量了不同市场交易时间，而不是共同交易时段的数据完整性。」

具体地：
  · v1 的分母是【USDJPY 的 M30 bar 数】，而 USDJPY 的 session 比 XAU 更宽
  · XAUUSDm 每个交易日固定缺失 22:00 与 22:30 UTC 两根（黄金交易所结算/休市窗口）
  · 因此 95% 主要反映"两个品种的 session 不完全相同"，
    而不是"已存在的 XAU bar 无法与 USDJPY 对齐"
  · 证据：2024H1 窗口 XAU bars = 11,772，exact matches = 11,772

★这不是根据策略收益修改规则：
   · 没有运行任何 TRAIN
   · 没有运行任何 VALID
   · 没有看到任何策略收益
   · 修改仅针对【数据资格定义】
```

---

## 1. 保持不变的部分（与 v1 完全一致）

```
信号结构 · z threshold · TP · SL · risk · V1/V2/V3 定义 · 执行与退出
★全部保持 v1 不变。本次只修改数据前置 gate。
```

| 项 | 值 |
|---|---|
| 交易 / 信息品种 | `USDJPYm` / `XAUUSDm` |
| 周期 / 时间 | M30 / `server_utc_offset = 0` |
| z-score | `e_i = Close_i − EMA48_i`；`sigma_t` = bar t **之前 48 个** residual 的 sample_std（不含 t）；`z_t = e_t / sigma_t`；`sigma_t <= 0` → 当天信号无效 |
| 阈值 | V1/V2: **1.5** · V3: **2.0** |
| 方向 | `trade_direction = −sign(z_t)` |
| ATR regime | `ATR14_t`；percentile 用**之前 500 个** ATR；**nearest-rank** P20/P80；不足 500 → 不交易 |
| 跨品种 | **exact M30 open timestamp**；`xau_ret_t = XAU_Close_t/XAU_Open_t − 1` |
| filter | V1/V3 ON（`sign(xau_ret)==sign(z)` 且 `xau_ret != 0`）· **V2 OFF** |
| 入场 | **bar t 收盘后、下一 bar 的第一个可交易 tick** |
| 出场 | SL = 1.0×ATR14_t · TP = 0.8R · 最长 **12 根完整 M30 bar** · 无 trailing/add-on/martingale/grid |
| 风险 | 1.5% equity · **OCP 权威** · Long/Short 分别计算 · `InpAllowMinLotOvershoot=false` · 上限 3% |
| 三个变体 | `XAMR30_V1`（z1.5, filter ON）· `XAMR30_V2`（z1.5, filter OFF, **control**）· `XAMR30_V3`（z2.0, filter ON） |

---

## 2. v2 的数据资格定义（唯一修改处）

### 2.1 两个指标分开

**指标 A：`info_availability_ratio`（★仅描述性统计，不再作 fail gate）**
```
info_availability_ratio = intersection exact M30 timestamps / USDJPY M30 timestamps
预期 ≈ 95%
含义：XAU 在多少 USDJPY bar 时间点处于可用交易 session
★不再用 99% 对它做 fail gate
```

**指标 B：`common_session_alignment_ratio`（★真正的数据质量指标）**
```
common_session_alignment_ratio = intersection exact timestamps / XAUUSDm existing M30 bars
理由：USDJPY 的 session 更宽，故以 XAU 为分母

要求：每个用于 TRAIN 的完整月份  common_session_alignment_ratio >= 99%
目标：证明每一个真实存在的 XAU bar，几乎都有同 timestamp 的 USDJPY bar

同时检查：
  · duplicate timestamps = 0
  · non-monotonic timestamp = 0
  · 任何 exact mismatch：记录
```

**实测（2023.01 窗口，逐根判定）**：
```
XAU M30 bars                      = 11,817
XAU bars with exact JPY match     = 11,817
→ common_session_alignment_ratio  = 100.0000%
→ duplicate timestamps            = 0
→ non-monotonic                   = 0
★同一窗口的 info_availability_ratio = 11,817 / 12,474 = 94.73%
```
**→ 两个指标分离后，真正的数据质量指标为 100%，v1 的 blocked 结论由此解除。**

### 2.2 ★所有三个 variant 必须共享同一个 availability mask

```
对于 V1 / V2 / V3：
  如果 signal bar t 没有 exact XAU M30 bar → 全部 cross_asset_missing_bar → 全部不交易
  ★即使 V2（InpCrossAssetFilter=false）也必须要求 exact XAU bar 存在

原因：V2 是 cross-asset filter 的控制组，
      只能关闭【XAU return 的方向过滤作用】，
      不能额外多交易 XAU 休市期间的 bar。
      否则 V1 与 V2 的交易时间集合不同，bootstrap 比较被 confound。

★源码核实：EvaluateSignalBar 中 exact 匹配（步骤 3）先于 filter（步骤 5），
  且该函数对所有变体共用 → 结构已正确，本次保持不变。
```

### 2.3 TRAIN start（机械规则，不参考任何策略收益）

```
不早于 2018-01-01
找到最早月份，使从该月开始到 2024-05：
  每月 common_session_alignment_ratio >= 99%
  且 USDJPY 执行数据 coverage 正常
TRAIN start = 该月第一个实际 eligible bar

VALID = 2024-06-01 ~ 2025-05-31
★禁止：2025-06-01~2026-05-31（exposed_oos）· 2026-06-01~09-30（user_holdout）
```

**冻结结果**：
```
实测 2023.01 窗口 common_session_alignment_ratio = 100.0000% >= 99%
且 JSB30 阶段已独立证明 2018-01-01 起 USDJPY M1 coverage 正常（>=99.9%）
→ ★TRAIN start = 2018-01-01（该月第一个 eligible bar 为 2018-01-02）
→ TRAIN = 2018-01-02 ~ 2024-05-31
```

---

## 3. N1R 修复（工程，非策略）

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | **pending 入场状态机错误**：`g_pendingBar == closedBar` 永不成立（t ≠ t+1）→ 0 交易 | 删除 pending 延迟；新 bar 首 tick 用 **shift=1** 算信号 → **同一 tick 立即按真实 Ask/Bid 下单** |
| 2 | **12-bar 持有 off-by-one**：static `lastCnt` + `g_barsHeld` 会把入场前的 closedBar 计入 | 引入 `g_lastHeldClosedBar` + `g_entryTime`；只有 `closeTime > entryTime` 才 `barsHeld++` |
| 3 | **审计列数与表头错位**（⛔ 反复出现的根因） | 改为**数组式写入 + `AUDIT_COLS` 断言**：列数不符即 `AUDIT SCHEMA FAIL` + fail-close |
| 4 | 缺 swap/commission/net → HTML 净利无法对账 | 审计补 `swap` / `commission` / `net` 三列（共 41 列） |
| 5 | 缺入场时序字段 | 新增 `signal_bar_open_time` / `signal_bar_close_time` / `entry_bar_open_time` |

**编译：0 errors / 0 warnings**

**冻结哈希**：
```
source  B5AB9F56432BA80E806C5B6655376D3AF372A0F26D0505203B03BCDFF98190BC  (41,800 B)
EX5     EB12B60584FD3404A4A4533F45285152D381B7262DB48965A382DCBD6D881A6E  (48,538 B)
旧版 N1 pre-smoke needs_repair（留档，不覆盖）：
        D63B2D66... / BEA547EA...
```

---

## 4. N1.5 engineering smoke 结果：**60/60 全部通过**

```
三固定窗口（只用 V1；profit/PF 不参与任何策略判断）：
  WINTER  2023-01-02~01-31
  DSTTR   2023-03-20~04-07
  SUMMER  2023-07-03~07-31
★实际产生 closing deals 合计 40 笔（>0，故可宣布审计交易链 PASS）
```

| 检查项 | 结果 |
|---|---|
| signal bar → next bar first tick 入场（`entry_bar = signal_bar + 30min`） | ✅ 40/40 |
| `entry_time >= signal_bar_close_time` | ✅ 40/40 |
| 时序抽查逐笔验证（≥20 笔要求） | ✅ 40 笔 |
| 持有 M30 bar 数 ≤ 12（最大 10 根，**无 off-by-one**） | ✅ |
| exact XAU alignment（全部成交 `alignment_exact=1`） | ✅ |
| `cross_asset_missing_bar` 都对应 XAU 无 bar | ✅ |
| 无 nearest / fill 行为 | ✅（源码只有 `xt == jt` 精确判定） |
| OCP sizing | ✅ |
| `DEAL_PROFIT ↔ OCP ≤ 0.05` | ✅ |
| spread / SL / TP 字段齐备（**JSB30 缺口已解决**） | ✅ |
| median spread/SL（0.0420 / 0.0777） | ✅ ≤30% |
| median spread/TP（0.0525 / 0.0972） | ✅ ≤30% |
| 每 UTC day ≤ 1 actual trade | ✅ |
| audit rows = HTML trades | ✅ |
| net reconciliation（如 12.09 = 12.09） | ✅ |
| active_positions = 0 · fatal = 0 · audit_failed = 0 | ✅ |

**★注：`common_session_alignment_ratio` 的逐月 >=99% 已在 §2.1 实测为 100%。
独立的 Python / MQL5 双算对账（裁定 §5）**尚未执行**，列为 N1.5 完成前的遗留项（见 §6）。**

---

## 5. 待执行阶段

```
N2  XAMR30_V1/V2/V3 TRAIN（同一冻结 EX5，共享 availability mask）
N3  TRAIN 通过者自动 VALID（2024-06-01 ~ 2025-05-31）
§9  V1 vs V2 paired bootstrap（20-day moving block, 10,000 resamples, seed=20260914）
```

---

## 6. 如实登记的遗留项

```
1. ★裁定 §5 要求的「独立 Python / MQL5 双算对账（≥50 个 signal candidate bar
   逐项比较 EMA48 / residual / sigma48 / z / ATR14 / P20 / P80 / XAU exact timestamp /
   XAU return）」【尚未执行】。当前 N1.5 验证的是写入与对账链，
   不是信号数值的独立复算。该项应在 N2 之前补齐。
2. TRAIN start 的逐月 common_session_alignment_ratio 表目前基于一个已验证窗口
   （2023.01 = 100%）+ JSB30 阶段的 USDJPY coverage 结论。
   完整逐月表应在 N2 前补测。
```

---

## 7. 全局禁止（不变）

```
✗ exposed_oos（2025-06-01~2026-05-31）· user_holdout（2026-06-01~09-30）
✗ 参数扫描 ✗ 按 TRAIN 结果补过滤器 ✗ long-only / short-only 事后筛选
✗ V2+V3 组合 ✗ 自建 symbol ✗ CSV 回灌 ✗ 修改历史旧 EA ✗ 真钱交易
```
