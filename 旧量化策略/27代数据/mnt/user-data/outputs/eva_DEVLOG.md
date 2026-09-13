# eva 量化策略可审计化 / 开发日志（eva_DEVLOG，v4）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 当前代际：**eva025（已出代码）**。
> 本版产物：
> - `eva025_VolumetricPulseGrid_StateMachine.mq5`（新功能见 §4 逐处改动记录）
> - `eva013_data_pipeline.py`（enrich 跑完直接打印"网格/趋势/砍单"三项汇总）
> 命名约定：方法1 / 方法2 / 方法3（不用"路 A/B"）。

---

## 0. 本轮要点与对话恢复
- 已**逐行读通整份 EA**（§2 代码运行逻辑详解保留为参考）。
- 用数据**确认你的三分类理解正确**（§3.1）：网格挣钱、趋势挣钱、砍单亏钱（但砍单避免网格亏更多）。
- **趋势侧占利润约 40~45%**（非小补贴），趋势单胜率=砍单准确率（同信号同刻触发）→ 提高趋势精度是高杠杆。
- eva025 已实现你要的三件事：**①纯趋势开关（关网格）②双趋势严格砍仓 ③修出场标签 bug**；并按你要求**给出"提高趋势胜率(单一更严格趋势)"与"双趋势"两套寻参方案**，可在两台机器并行（§5）。

---

## 1. 历代 changelog（简）
| 代际 | 改了什么 / 为什么 |
|---|---|
| eva023 | `CloseOppositeGridOnTrend=true` → 净利首正 +$98 |
| eva024 | 网格因子改变指数(0.5/0.5)替代固定指数+clip；高位安全帽 |
| eva024 寻参/关砍 | 7 组 .3~.9 + 关砍 .4f/.8f/.9f → 证明砍仓有效(+$377~+$1003/组) |
| **eva025** | **①`InpEnableGrid` 纯趋势开关；②双趋势 `InpCutUseStrictTrend`（严格趋势专管砍仓）；③修出场原因标签 bug（按仓位记录）；④py 三分类汇总** |

---

## 2. 代码运行逻辑详解（参考，已读通）
- **主循环 `OnTick`**：算百分比波动 `G_RVRatio` → 更新M5趋势状态(状态切换砍逆势网格) → 趋势单移动止损 → 新分钟移动基线 → 量/风险等级(L4全平) → 持仓快照 → `last_order_stop`/`cutoff_line_stop` 两道尾部硬止损 → **网格篮子止盈(`bid≥基线`平多/`ask≤基线`平空,现金牛)** → `ManageTrendOrders` → 一串开仓门闸 → 按 `bid<基线−网格距` 开逆势网格(马丁×`InpUniGridExpCoef`)。
- **网格距**：`base_grid_z=max(MinGridZ×价缩放, GridZ×价缩放×变指数因子)`；常波动由 MinGridZ 地板接管，**高波动由 GridZ×因子接管(GridZ=高波动扩张倍率)**；因子 `rn^(0.5+0.5rn)` 封顶 40。
- **基线 `AdjustBaseline`**：有持仓时基线朝亏损方向移 `Σcoef_c×decay^i`(套牢越深移越多)→ 逆势堆仓会把基线拖着追趋势跑(砍仓有效的机制根源)。
- **趋势状态机**：M5 `up=rv_ok&ema_up&breakout_up`，连续 `ConfirmBars` 根切状态；状态切换瞬间砍逆势网格 + 开同向趋势单(故趋势单胜率≈砍单准确率)。
- **尾部**：`last_order_stop`(满仓+末单亏超阈)、`cutoff_line_stop`(虚拟末单线越线即全平,不需满仓)。
- **审计**：开仓抓拍上下文，平仓 `EvaOnDealAdd` 落盘；出场原因机制见 §4.3（本轮修复对象）。

---

## 3. 本轮分析（数据确认）

### 3.1 三分类(逐组,确认你的理解正确)
| 组 | 网格(网开网平) | 趋势(全趋势单) | 砍单(网开趋平) |
|---|---|---|---|
| .3 | +6576/87% | +977/38% | −5167/20% |
| .4 | +6224/85% | +753/37% | −5272/15% |
| .5 | +8650/89% | +575/33% | −7730/14% |
| .6 | +6629/87% | +807/38% | −5524/18% |
| .7 | +6272/86% | +792/39% | −5578/17% |
| .8 | +4112/84% | +859/39% | −3200/20% |
| .9 | +6180/86% | +826/38% | −4982/20% |
- **网格挣钱(胜率84~89%)、趋势挣钱(胜率33~39%)、砍单亏钱(胜率14~20%)**——三类定义与你完全一致。
- 砍单亏，但关砍实验证明它避免了网格在单边里亏更多(净正)。

### 3.2 谁是主力 / 趋势胜率=砍单准确率
- 趋势侧占全程利润 **40~45%**(.7 组53%)；趋势单胜率33~39%(靠不对称:最大赢+$75~89 vs 最大亏−$23~27)。
- 代码层面：状态切到TREND_UP同一刻，砍空网格(`CutOppositeGrid`)+开趋势多单(`ManageTrendOrders`)→ **趋势单对错=砍单对错**。提精度同时改善"趋势侧~45%利润 + 砍单准确率"。

---

## 4. eva025 逐处代码改动记录（什么/为什么/怎么改）

### 4.1 方法①：纯趋势开关 `InpEnableGrid`（关网格，隔离趋势侧盈亏）
- **为什么**：你要先看"纯趋势能否挣钱"。需要一个能关掉网格、只留趋势单的开关。
- **改了什么**：
  - 新增输入 **是否启用网格** `InpEnableGrid`（默认 true）。
  - `OnTick` 中、在 `ManageTrendOrders(risk_level)` 之后插入 `if(!InpEnableGrid) return;`。该处之后全部是网格开仓逻辑，直接 return 即"趋势单照常开/平/移动止损，网格完全不开"。
- **怎么用**：`InpEnableGrid=false` + 当前参数跑一遍 → 控制台/审计即为纯趋势盈亏。

### 4.2 方法②：双趋势严格砍仓（你的设计）
- **为什么**：砍单准确率低，是因为"砍仓用的是和开趋势单同一个偏灵敏信号(breakout=8)"。用一个**更严格、更晚确认**的趋势专门触发砍仓，可减少震荡假突破的误砍；宽松趋势仍管趋势单开/平与逆势禁开。
- **改了什么**：
  - 新增输入：**砍仓改用严格趋势** `InpCutUseStrictTrend`(默认 false)、**严格趋势突破窗口** `InpStrictBreakoutBars`(50)、**严格趋势连续确认根数** `InpStrictConfirmBars`(4)、**严格趋势最小RVRatio** `InpStrictMinRVRatio`(0.030)、**严格趋势需高周期EMA对齐** `InpStrictUseHigherTF`(false)、**严格趋势高周期** `InpStrictHigherTF`(M15)、**高周期快/慢EMA** `InpStrictHTFFastEMA/SlowEMA`(20/60)。
  - 新增全局：`G_StrictState / G_StrictUpConfirm / G_StrictDownConfirm / G_StrictHTFFastHandle / G_StrictHTFSlowHandle`。
  - 新增函数 `EvaluateStrictTrendSignals()`：复用宽松状态机本根已算的快/慢EMA方向，叠加"更长突破窗 + 更高RV + 可选高周期EMA同向"。
  - `UpdateMarketState`：原砍仓块改为**仅 `!InpCutUseStrictTrend` 时按宽松状态切换砍**；并在其后新增**严格趋势独立状态机**，`InpCutUseStrictTrend=true` 时由它(达 `StrictConfirmBars` 确认)触发砍仓；严格趋势退出沿用快EMA穿回回到震荡(允许后续再砍)。
  - `InitTrendIndicators/ReleaseTrendIndicators`：按需创建/释放高周期EMA句柄。
  - 退化兼容：把严格参数设成与宽松一致即回到原行为；`InpCutUseStrictTrend=false` 即完全等同 eva024 的砍仓。

### 4.3 方法③：修出场原因标签 bug
- **为什么**：出场原因是**单个全局** `G_EvaExitReason`；`ManageTrendOrders` 每个 tick 把它覆写成 `trend_state_exit`，而成交落盘延迟 → 砍网格的成交被错标为 `trend_state_exit`(数据里根本没有 `trend_close_opposite_grid`)，审计无法区分"被砍网格"与"趋势单状态退出"。
- **改了什么**：
  - `EvaOpenRec` 新增字段 `string pending_exit`（按仓位记录待落盘原因）。
  - 新增 `EvaTagExitByType(type,reason)`：把指定方向的网格仓位逐个按 `POSITION_IDENTIFIER` 找到审计槽位、写入 `pending_exit`。
  - 新增 `CutOppositeGrid(type)`：先 `EvaTagExitByType(type,"trend_close_opposite_grid")` 再平仓（砍仓统一走它）。
  - `EvaOnDealAdd` 落盘：expert/client/other 时**优先取该仓位的 `pending_exit`**，无则回退全局。
  - 槽位分配/绑定处(`EvaNewOpenSlot`/`EvaBindEntry`/entry-IN)均初始化 `pending_exit=""`，防槽位复用串味。
- **效果**：eva025 起，被砍网格正确落 `trend_close_opposite_grid`，趋势单状态退出仍为 `trend_state_exit`，两者分开可审计。

### 4.4 方法④：py 三分类汇总（enrich 跑完直接看）
- **为什么**：你想跑完直接看网格/趋势/砍单三项，不用我再统计。
- **改了什么**（`eva013_data_pipeline.py`）：
  - 新增 `_print_three_buckets(tr)` 与 `_bucket_line()`，在 `run_enrich` 末尾调用，打印三类的 净利/笔数/胜率/单均/PF + 合计对账。
  - 分类：网格=grid且非砍仓出场；砍单=grid且出场∈{`trend_close_opposite_grid`,`trend_state_exit`}(新旧标签兼容)；趋势=trend。
  - 已用 eva024.9 实测：网格+6179.6 / 趋势+826.0 / 砍单−4981.6 / 合计+2023.9（对得上）。

---

## 5. 双机并行寻参方案（你有两台电脑）

> 均用同一个 `eva025_*.mq5`，不同参数配置即可。

### 实验0（任意机器，先快跑）：纯趋势诊断
- **是否启用网格** `InpEnableGrid=false`，其余用 eva024 当前任一组(如 .9)。
- 看趋势侧单独能否挣钱、回撤形态如何。**回答你第1点。**

### 实验1（机器A）：方法1 = 提高趋势胜率（单一更严格趋势，你之前想先试的"换窗口"）
- 砍仓仍走宽松：**砍仓改用严格趋势** `InpCutUseStrictTrend=false`。
- **收紧这套唯一趋势**(同时驱动趋势单+砍仓)，寻参范围：
  - **趋势确认突破窗口** `InpTrendBreakoutBars`：8 → 搜 [30, 40, 50]
  - **趋势连续确认根数** `InpTrendConfirmBars`：2 → 搜 [3, 4]
  - **趋势确认最小RVRatio** `InpTrendMinRVRatio`：0.019 → 搜 [0.025, 0.030, 0.035]
  - 可选 **趋势单ATR止盈** `InpTrendTP_ATR_Mult`：0 → 搜 [0, 1.5, 2.0]（锁小赢提趋势单胜率）
- 预期：趋势单胜率↑ = 砍单准确率↑，误砍↓。但趋势触发更少→趋势侧利润可能↓，**需对照总净利与真OOS**。

### 实验2（机器B）：方法2 = 双趋势
- **砍仓改用严格趋势** `InpCutUseStrictTrend=true`；宽松趋势保持当前(BreakoutBars=8/ConfirmBars=2/MinRVRatio≈0.019)→ 趋势单照常多开、保留不对称盈利。
- 搜严格(只管砍仓)的参数：
  - **严格趋势突破窗口** `InpStrictBreakoutBars`：搜 [30, 50, 80]
  - **严格趋势连续确认根数** `InpStrictConfirmBars`：搜 [3, 4, 6]
  - **严格趋势最小RVRatio** `InpStrictMinRVRatio`：搜 [0.025, 0.030, 0.040]
  - **严格趋势需高周期EMA对齐** `InpStrictUseHigherTF`：搜 {false, true}（true 更准但更滞后→砍得更晚更深）
- 预期：砍仓更挑剔→浅亏误砍↓；但真趋势上砍得更晚→被砍那批更深。**净效果对照实验1与关砍基准。**

### 对照与判读
- 三条线都跑完，比 **全程净利 / PF / 真OOS(2026-06)/ 最大回撤**，并用 py 三分类看"砍单"那栏是否变小、"网格"那栏是否变大。
- 诚实预期：edge 薄、真OOS仅1月，单一改动"小而稳"；最终靠更长前向窗口定稿。

---

## 6. 代码 / 参数 changelog（含本轮）
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva024 | EA | 网格因子变指数(0.5/0.5)替代固定指数+clip |
| eva024 寻参/关砍 | 7+3 set | 寻参 .3~.9；关砍证明砍仓有效 |
| **eva025** | **EA** | **①`InpEnableGrid`(纯趋势开关,OnTick关网格)；②双趋势`InpCutUseStrictTrend`+严格趋势参数(`InpStrictBreakoutBars=50`/`InpStrictConfirmBars=4`/`InpStrictMinRVRatio=0.030`/可选`InpStrictUseHigherTF`),砍仓由严格趋势触发,宽松仍管趋势单与逆势禁开,新增`EvaluateStrictTrendSignals`/严格状态机；③修标签:`EvaOpenRec.pending_exit`按仓位记录+`CutOppositeGrid`/`EvaTagExitByType`,砍网格正确落`trend_close_opposite_grid`** |
| **eva025** | **py** | enrich 末尾 `_print_three_buckets`：网格/趋势/砍单三项净利/胜率/PF直接打印 |

### 本轮发现/确认（供追溯）
- 三分类全组确认：网格+(84~89%胜)、趋势+(33~39%胜)、砍单−(14~20%胜)；趋势侧占利润~45%。
- 趋势单胜率=砍单准确率(同信号同刻)；提精度高杠杆。
- 出场标签 bug 根因=单一全局被 `ManageTrendOrders` 每tick覆写 → 已按仓位记录修复。
- GridZ=高波动网格扩张倍率(非无效)。

---

## 7. 待你反馈
1. 实验0/1/2 三条线开跑后，把各自的 set + enrich 结果(含三分类打印)发我，我据此定 eva026 方向。
2. 若纯趋势(实验0)单独能稳定盈利，可考虑把趋势侧独立成更简单的策略并行；要的话我做。
3. 编译若报错(我无法在此编译 MQL)，把报错行号发我即修。

---

*本日志随版本更新；代际默认进位。代码/参数改动在 §6 追加。*
*（以上为工程与分析记录，不构成投资建议；改动后务必在测试器充分验证。）*
