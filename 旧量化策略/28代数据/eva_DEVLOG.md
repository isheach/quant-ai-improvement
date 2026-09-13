# eva 量化策略可审计化 / 开发日志（eva_DEVLOG，v5）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 当前代际：**eva025（分叉为 A / B 两条独立路线）**。
> 本版产物（统一 eva025 前缀，便于溯源）：
> - `eva025a_VolumetricPulseGrid_StateMachine.mq5`：**分叉A——给趋势判断增加新机制**（让单一趋势更准）。
> - `eva025b_VolumetricPulseGrid_StateMachine.mq5`：**分叉B——专门的砍单严格趋势**（双趋势）。
> - `eva025_data_pipeline.py`：enrich 跑完直接打印"网格/趋势/砍单"三项汇总。
> 命名约定：方法/路线称 分叉A、分叉B。

---

## 0. 本轮要点（按你反馈修正）
1. **"提高趋势胜率"=加新机制，不是调参** → 分叉A 增加了 3 个新的趋势确认机制（MTF / ADX / EMA间距），而非收紧旧窗口。
2. **eva025b 的输入组重命名并拆分**：原"纯趋势开关/双趋势砍仓"名字误导，已拆为「网格总开关（纯趋势诊断）」+「砍逆势网格的触发方式（双趋势）」两组，后者明确是控制**砍单**的。
3. **两条路线不兼容 → 分叉成两个独立文件**（A=新机制、B=专门砍单趋势），分别实验；哪个好用哪个，都好再结合，也避免代码互相干扰出错。
4. **所有同批文件统一 eva025 前缀**（py 也改名为 `eva025_data_pipeline.py`），方便你溯源是哪一代生成。

---

## 1. 历代 changelog（简）
| 代际 | 改了什么 / 为什么 |
|---|---|
| eva023 | `CloseOppositeGridOnTrend=true` → 净利首正 +$98 |
| eva024 | 网格因子改变指数(0.5/0.5)替代固定指数+clip |
| eva024 寻参/关砍 | 7 组 .3~.9 + 关砍 .4f/.8f/.9f → 证明砍仓有效 |
| **eva025a** | **趋势判断加新机制(MTF多周期/ADX强度/EMA间距)；+纯趋势开关;+修标签** |
| **eva025b** | **双趋势:砍单专用严格趋势(更长突破窗/更多确认/更高RV/可选高周期EMA);+纯趋势开关;+修标签** |
| **eva025 py** | enrich 末尾打印 网格/趋势/砍单 三项 |

---

## 2. 关键结论回顾（前几轮，供恢复对话）
- **三分类**（数据逐组确认）：网格挣钱(胜率84~89%)、趋势挣钱(33~39%)、砍单亏钱(14~20%)；砍单亏但避免网格亏更多(关砍实验净正)。
- **趋势侧占利润~40~45%**；趋势单与砍单同信号同刻触发 → **趋势单胜率=砍单准确率** → 提高趋势精度是高杠杆(同时改善趋势侧利润与砍单准确率)。
- 砍仓有效机制：逆势网格堆积→基线被拖着追趋势→回归账本质量塌+深尾灾难；砍掉逆势仓=基线干净重置。
- 真OOS(仅2026-06)偏负、edge 薄、月度 lumpy → 改动"小而稳"，最终靠更长前向窗口定稿。

---

## 3. 分叉A（eva025a）逐处代码改动记录

### 3.1 目标
不改旧趋势窗口，而是**增加新机制**让"单一趋势"判得更准。新机制 AND 进原 `up_signal/down_signal`，因为单一趋势同时驱动趋势单与砍单，所以**同时提升趋势单胜率与砍单准确率**。三机制各自独立开关，全关即回到 eva024。

### 3.2 新增机制（什么/为什么/怎么改）
1. **多周期(MTF)趋势确认** `InpUseMTFConfirm`(默认 true)
   - 为什么：M5 的趋势常被更大级别证伪；要求高周期 EMA 同向可滤掉"逆大势的 M5 假趋势"。
   - 怎么改：新增 `InpMTFTimeframe`(M15)、`InpMTFFastEMA`(20)、`InpMTFSlowEMA`(60)；新建句柄 `G_MTFFastHandle/G_MTFSlowHandle`；`EvaluateTrendSignals` 里要求 `mtf_up = 高周期快EMA>慢EMA`(down 反之)。
2. **ADX 趋势强度过滤** `InpUseADXFilter`(默认 true)
   - 为什么：ADX 是经典"是否在趋势"的强度指标；震荡期 ADX 低，可直接滤掉震荡假突破(6月误砍的主因)。
   - 怎么改：新增 `InpADXPeriod`(14)、`InpMinADX`(25)；新建 `G_ADXHandle=iADX(趋势周期)`；要求 `ADX主线 ≥ InpMinADX`。
3. **EMA 间距强度过滤** `InpUseEMASepFilter`(默认 false)
   - 为什么：快慢 EMA 粘合时方向不可靠；要求 `|快-慢|≥k×ATR` 才认，确保趋势已展开。
   - 怎么改：新增 `InpMinEMASepATR`(0.5)；用 `GetTrendATR` 取 ATR，判 `MathAbs(fast-slow)≥k×ATR`。

### 3.3 公共改动（与分叉B相同）
- **纯趋势开关** `InpEnableGrid`(默认 true)：`OnTick` 中 `ManageTrendOrders` 后 `if(!InpEnableGrid) return;` → 关网格只跑趋势单。组名「网格总开关（纯趋势诊断用）」。
- **修出场标签 bug**：`EvaOpenRec` 加 `pending_exit`；新增 `EvaTagExitByType`/`CutOppositeGrid`(砍仓按仓位打 `trend_close_opposite_grid`)；`EvaOnDealAdd` 优先取按仓位记录；砍仓块改走 `CutOppositeGrid`。

### 3.4 寻参建议（分叉A）
- 先各机制单独开/调，再组合：
  - `InpUseADXFilter=true`，搜 `InpMinADX` ∈ {20,25,30}（最可能见效，先调它）。
  - `InpUseMTFConfirm=true`，搜 `InpMTFTimeframe` ∈ {M15,H1}。
  - `InpUseEMASepFilter` 视情况开，搜 `InpMinEMASepATR` ∈ {0.3,0.5,0.8}。
- 用 py 三分类看：砍单那栏笔数/亏损是否变小、胜率是否变高；趋势那栏胜率是否变高。

---

## 4. 分叉B（eva025b）逐处代码改动记录

### 4.1 目标
**双趋势**：宽松趋势(原参数)继续管趋势单开/平与逆势网格禁开；**新增一套更严格的趋势，专门触发砍仓**——只有它确认才砍逆势网格，少砍震荡假突破的误砍，真趋势仍会确认照砍尾部。

### 4.2 改动（什么/为什么/怎么改）
- **输入组拆分重命名**（按你反馈）：
  - 「=== eva025：网格总开关（纯趋势诊断用，与砍单无关）===」：`InpEnableGrid`。
  - 「=== eva025b：砍逆势网格的触发方式（双趋势：宽松管交易/严格管砍单）===」：下列严格参数。
- **新增**：`InpCutUseStrictTrend`(默认 false)、`InpStrictBreakoutBars`(50)、`InpStrictConfirmBars`(4)、`InpStrictMinRVRatio`(0.030)、`InpStrictUseHigherTF`(false)、`InpStrictHigherTF`(M15)、`InpStrictHTFFastEMA/SlowEMA`(20/60)。
- 新增全局 `G_StrictState/G_StrictUpConfirm/G_StrictDownConfirm/G_StrictHTFFastHandle/G_StrictHTFSlowHandle`；新增 `EvaluateStrictTrendSignals`(复用宽松EMA方向+更长突破窗+更高RV+可选高周期EMA对齐)。
- `UpdateMarketState`：宽松砍仓仅 `!InpCutUseStrictTrend` 时按宽松状态切换砍；其后新增严格状态机，`InpCutUseStrictTrend=true` 时由它(达 `StrictConfirmBars` 确认)触发砍仓。
- 同样含**纯趋势开关**与**修标签**(`CutOppositeGrid`/`EvaTagExitByType`/`pending_exit`)。
- 退化兼容：`InpCutUseStrictTrend=false` 即等同 eva024 砍仓行为。

### 4.3 寻参建议（分叉B）
- `InpCutUseStrictTrend=true`，宽松参数保持现状(BreakoutBars=8/ConfirmBars=2)；搜：
  - `InpStrictBreakoutBars` ∈ {30,50,80}、`InpStrictConfirmBars` ∈ {3,4,6}、`InpStrictMinRVRatio` ∈ {0.025,0.030,0.040}、`InpStrictUseHigherTF` ∈ {false,true}。

---

## 5. py 改动（eva025_data_pipeline.py）
- 新增 `_print_three_buckets`/`_bucket_line`，`run_enrich` 末尾自动打印：
  - 网格(grid 且非砍仓出场) / 趋势(全 trend 单) / 砍单(grid 且出场∈{trend_close_opposite_grid,旧trend_state_exit})。
  - 每类 净利/笔数/胜率/单均/PF + 合计对账。新旧标签兼容。
- 实测 eva024.9：网格+6179.6 / 趋势+826.0 / 砍单−4981.6 / 合计+2023.9（对得上）。

---

## 6. 双机并行实验安排
| 机器 | 文件 | 关键设置 | 看什么 |
|---|---|---|---|
| 先快跑(任意) | 任一eva025 | `InpEnableGrid=false` | 纯趋势能否挣钱(隔离趋势侧) |
| 机器A | **eva025a** | 开 ADX/MTF，搜其阈值 | 新机制是否提升趋势单胜率+砍单准确率 |
| 机器B | **eva025b** | `InpCutUseStrictTrend=true`，搜严格参数 | 专门砍单趋势是否减少误砍 |
- 三条线都跑完，比 全程净利 / PF / 真OOS(2026-06) / 最大回撤 + py 三分类(砍单是否变小、网格是否变大)。
- 哪条好用哪条；若 A、B 都有可取之处，下一代(eva026)再把"新机制 + 专门砍单趋势"结合。

---

## 7. 代码 / 参数 changelog（含本轮）
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva024 | EA | 网格因子变指数替代固定指数+clip |
| **eva025a** | **EA(分叉A)** | 趋势加新机制：`InpUseMTFConfirm`(多周期EMA同向)+`InpUseADXFilter`(`InpMinADX=25`)+`InpUseEMASepFilter`(`InpMinEMASepATR`)，AND进up/down信号(全关=eva024)；+`InpEnableGrid`纯趋势开关；+修标签(`pending_exit`/`CutOppositeGrid`/`EvaTagExitByType`) |
| **eva025b** | **EA(分叉B)** | 双趋势：`InpCutUseStrictTrend`+严格趋势参数,砍仓由严格趋势触发,宽松仍管趋势单与逆势禁开,新增`EvaluateStrictTrendSignals`/严格状态机；输入组拆分重命名(网格总开关 / 砍单触发);+纯趋势开关;+修标签 |
| **eva025 py** | py | enrich 末尾三分类汇总(网格/趋势/砍单) |

### 本轮发现/决策（供追溯）
- 分叉两条路线避免互相干扰：A=新机制(MTF/ADX/EMA间距)让单一趋势更准；B=专门严格砍单趋势。
- 输入组重命名：纯趋势开关与砍单触发分开，名字明确。
- 文件统一 eva025 前缀(含 py)便于溯源。
- 两版均含纯趋势开关与标签修复；均向下兼容 eva024(新机制全关 / `InpCutUseStrictTrend=false`)。

---

## 8. 待你反馈
1. 我无法在此编译 MQL；请在 MetaEditor 各编译一次 eva025a / eva025b，报错把行号发我即修。
2. 分叉A 的三机制默认 ADX+MTF 开、EMA间距关——是否同意先这样试？
3. 实验跑完把各自 set + enrich(含三分类) 发我，定 eva026。

---

*本日志随版本更新；代际默认进位。代码/参数改动在 §7 追加。*
*（以上为工程与分析记录，不构成投资建议；改动后务必在测试器充分验证。）*
