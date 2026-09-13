# eva 量化策略可审计化 / 开发日志（eva_DEVLOG，v3）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 当前代际：**eva024（7 组寻参 + 关砍对照）→ 规划 eva025**。
> 本版新增：① **完整的代码运行逻辑详解（§1，逐函数/逐块）**，证明已读通整份 EA；② 用数据更正"趋势侧只是小补贴"的说法（趋势侧其实占利润 40~45%）；③ 发现并记录一个**出场原因标签 bug**；④ 把 eva025 主方案改为**你提的"双趋势"设计（方法1）**。
> 命名约定：本版起改用 **方法1 / 方法2 / 方法3**，不再用"路 A/B"。

---

## 0. 本轮对前几版的更正（审计留痕）
1. （上版已更正）"砍仓净 destructive"是错的——你的关砍对照证明砍仓有效（+$377~+$1003/组）。
2. **本版更正**："趋势侧只是 +$700~870 的小补贴、不是主要矛盾"——错。**趋势侧占全程利润 40~45%**（见 §3.1），.7 组趋势侧甚至超过网格侧。**提高趋势精度是高杠杆的**。
3. **真·样本外仅 2026-06**（2026-02~05 是寻参挑选集，天然不亏，不算外推）。

---

## 1. 代码运行逻辑详解（eva024_VolumetricPulseGrid_StateMachine.mq5，3681 行）

### 1.1 总体架构
一套"**震荡网格主体 + 趋势状态机叠加层 + 多层风控 + eva 审计落盘**"的 EA。两套独立 Magic：网格单 `InpMagicNum=123456`、趋势单 `InpTrendMagicNum=223456`，互不干扰平仓。

### 1.2 主循环 `OnTick()`（674–922）执行顺序
1. **`UpdateVolatilityRegime()`**（1103）：每根新 M1 算"百分比波动" `G_RVRatio`，再调 `UpdateActiveParams()` 刷新距离类参数。
2. **`UpdateMarketState(false)`**（1576）：每根新 M5（趋势周期）更新行情状态 RANGE/趋势涨/趋势跌；**状态切换时若 `InpCloseOppositeGridOnTrend` 为真，就在这里砍逆势网格**（1640–1647）。
3. **`ManageTrendTrailing()`**（1839）：趋势单移动止损维护。
4. **`UpdateDashboard()`**：面板（按 M1 节流）。
5. **新分钟处理**（682–706）：`MaybeResetBaselineOnReopen` → `AdjustBaseline()`（移动基线）→ `UpdateHistoricVolumeSum()`（更新成交量和）。
6. 取 ask/bid/point，算 `avg_volume_per_min`（近 `InpAvgVolumeMinutes` 分钟均量）。
7. **`GetCurrentRiskLevel()`**（2239）→ 风险等级。**L4（周五收盘前 30 分）：`CloseAllStrategyPositions()`+平趋势单，return**。
8. `BuildStrategySnapshot(snap)`（1159）：扫描网格持仓，统计 buy/sell 数、最后一单价/时间/浮盈。
9. `ClosePositionsNotAllowedByActiveProfile`：清掉当前档位不该留的仓。
10. **`CheckLastOrderStopAndCooldown(snap)`**（2084）：达最大持仓数(`InpUniMaxPos=3`)且**最后一单浮亏 ≥ `InpLastOrderLossPerLot×手数`** → 全平 + 冷静期，return。
11. **`CheckCutoffLineStopAndCooldown(snap)`**（3375）：**截止虚拟末单线硬止损**（不依赖是否达最大持仓，见 §1.6），越线 → 全平 + 冷静期，return。
12. **`ManageRiskByLevel(risk_level)`**（1268）：L2/L3 风险下平盈利/亏损单。
13. **网格篮子止盈（现金牛核心，768–780）**：
    - 有多单且 `bid ≥ G_Baseline` → `EvaSetExit("grid_tp_baseline_revert")` + `CloseAllPositions(BUY)`，return。
    - 有空单且 `ask ≤ G_Baseline` → 同理平所有空单。
    - **即"价格回到基线就把该方向整篮平掉"**，是高胜率小利的来源。
14. **`ManageTrendOrders(risk_level)`**（1896）：趋势单独立开/平（见 §1.5）。
15. 之后是开新网格的层层门闸：L2+ 禁开 / 冷静期禁开 / 档位不允许禁开 / 量不足处理 / 总持仓上限。
16. **`multiplier_a` 计算**（811–824）：`avg_volume/base_avg_volume`，取 `InpMultiplierExp` 次幂，下限 1（只放大不缩小）。
17. **逆势网格方向门闸**（826–835）：趋势涨 → `allow_grid_sell=false`；趋势跌 → `allow_grid_buy=false`（`InpBlockAgainstTrendGrid`）。
18. **开多/开空（837–921）**：见 §1.4。

### 1.3 波动率与距离模型（`UpdateVolatilityRegime`/`UpdateActiveParams`/`CalcRealizedVolPoints`）
- **百分比波动**（1117）：`G_RVRatio = 100 × RMS(每分钟收盘差, 窗口InpVolWindowMinutes) × point / price`。即把分钟波动 RMS 归一到价格百分比。
- **变指数网格因子**（992–994）：`rn = G_RVRatio/InpRefVolPct`；`grid_exp = InpGridExpLow + InpGridExpSlope×rn`；`vf_grid = rn^grid_exp`，上限 `InpVolFactorMax=40`。
- **网格基距合成**（999–1001）：
  \[
  \text{grid\_scaled}=\text{InpGridZ}\times\frac{price}{\text{InpRefPrice}}\times vf\_grid,\quad
  \text{grid\_floor}=\text{InpMinGridZ}\times\frac{price}{\text{InpRefPrice}}
  \]
  \[
  \texttt{base\_grid\_z}=\max(\text{grid\_floor},\ \text{grid\_scaled})
  \]
  - **更正上版说法**：`InpGridZ` 不是"形同虚设"。常/低波动时 `grid_floor`(=MinGridZ) 接管；**高波动时 `grid_scaled` 接管，此时 InpGridZ 是"风暴时网格扩张倍率"**——同样 vf_grid 封顶 40，InpGridZ=1000 → 风暴网格 $40，InpGridZ=4000 → $160。所以 GridZ 高低决定高波动时网格张多大，仍有实际作用。只是"参考波动下的基距"被 MinGridZ 盖住了。

### 1.4 网格开仓（837–921）
- 多单条件：`allow_grid_buy && bid < G_Baseline`，且：
  - 首单(`buy_count==0`)：`bid < G_Baseline − final_grid_distance`；
  - 加仓：`bid < last_buy_price − final_grid_distance`。
- `final_grid_distance = base_grid_z×point×multiplier_a × InpUniGridExpCoef^count`（马丁：每加一仓间距 ×`InpUniGridExpCoef`）。
- 过 `CheckAddPacingDelay`（加仓延迟门闸，2143）与总持仓上限后 → `OpenBuyOrder(lot, ask, tp_dist,...)`；`tp_dist = InpUniBaseProfit×point×mult`（设很大，实际主要靠基线回归平仓而非该 TP）。空单对称。

### 1.5 趋势状态机与趋势单
- **`EvaluateTrendSignals`**（1483）：在趋势周期(M5)上，
  - `breakout_up = close[1] > 最近 InpTrendBreakoutBars 根的最高`（向上突破）；
  - `ema_up = fast>slow 且 slow 比 slope_lb 根前高`（慢线上行）；
  - `rv_ok = G_RVRatio ≥ InpTrendMinRVRatio`；
  - **`up_signal = rv_ok && ema_up && breakout_up`**（三条全满足），down 对称；
  - `exit_up = fast<slow`（或 `InpTrendExitOnFastEMA` 时 close<fast 也退出）。
- **`UpdateMarketState`**（1576）：`up_signal` 连续 `InpTrendConfirmBars` 根 → 切 TREND_UP；否则计数清零。状态切换时（仅切换瞬间）：
  - **砍逆势网格**（1640–1647，开关 `InpCloseOppositeGridOnTrend`）：切 TREND_UP → `CloseAllPositions(SELL)`；切 TREND_DOWN → `CloseAllPositions(BUY)`。
- **`ManageTrendOrders`**（1896）：
  - 若 `InpTrendCloseOnStateExit`：状态回 RANGE → 平所有趋势单；状态翻向 → 平反向趋势单（出场原因 `trend_state_exit`）。
  - 在 TREND_UP 且无趋势多单 → `OpenTrendBuyOrder`（ATR 止损 `InpTrendSL_ATR_Mult`、移动止损 `InpTrendTrail_ATR_Mult`、`InpTrendTP_ATR_Mult=0` 即无固定止盈）。
- **关键耦合（印证你第1点）**：状态切到 TREND_UP 的**同一瞬间**，既砍空网格(1644)又会在 `ManageTrendOrders` 开趋势多单。**所以趋势单的对错=砍单的对错，趋势单胜率≈砍单准确率。**

### 1.6 风控
- **基线 `AdjustBaseline`**（1217，每新分钟）：
  - **空仓**：基线以 `move_points_b` 朝现价追（`InpMoveB×波动`）。
  - **持仓**：基线朝**亏损方向**移动 `Σ coef_c×InpCoefDecay^i`（净仓数 i）。即套牢越深、移得越多，把整篮 TP 目标拉向现价帮其出场。**这就是砍仓有效的机制根源**（见 §3.2）。
- **`last_order_stop`**（2084）：达最大持仓 + 末单浮亏超阈 → 全平+冷静期。
- **`cutoff_line_stop`**（3375）：算"满仓时末单相对基线的累计网格距 + 每手亏损缓冲"得一条**虚拟止损线**，价格越线即全平（**不需先达满仓**，专治"截止状态止损永不触发"）。关砍实验里它出现 15~36 次（深尾灾难），是砍仓帮你避免的。
- **风险分级**（2239）：量 > `InpMaxAvgVolumePerMin` 或周一重开窗 → L2(禁开)；周五收盘前 → L3/L4。

### 1.7 eva 审计落盘
- 开仓时 `EvaCaptureGridPending/EvaBindEntry` 抓拍上下文（档位/RV/state/mult/网格距…）；平仓时 `EvaOnDealAdd`（2842）落一行（含 MFE/MAE 由 py 后处理补）。
- **出场原因机制（重要 bug，见 §3.3）**：`EvaSetExit` 只写一个**全局** `G_EvaExitReason`；`EvaOnDealAdd` 落盘时，券商原因为 expert/client 则取该全局"最后值"。

---

## 2. 历代 changelog（简）
| 代际 | 改了什么 / 为什么 |
|---|---|
| eva020 | 删 pacing；尾部失控 −$1041 |
| eva021 | 删 overshoot/档位日志；网格因子 clip 钳制 |
| eva022 | 修趋势 RV 闸门量级错配 → 趋势可触发 |
| eva023 | 固化寻参值；OnTester 接入；`CloseOppositeGridOnTrend=true` → 净利首正 +$98 |
| eva024 | 网格因子改变指数(0.5/0.5)替代固定指数+clip；高位安全帽 |
| eva024 寻参/关砍 | 7 组 .3~.9 + 3 组关砍 .4f/.8f/.9f（证明砍仓有效） |
| **eva025（规划）** | **方法1 双趋势**（严格趋势专管砍仓）为主；可叠 **方法2 深度条件砍**；**方法3 修出场原因标签 bug** |

---

## 3. 本轮分析（逐组、修正版）

### 3.1 谁是主力：网格侧 vs 趋势侧（更正：趋势侧占 40~45%）
| 组 | 全程净 | 网格侧净 | 趋势侧净 | 趋势侧占比 | 趋势单胜率(=砍单准确率) |
|---|---|---|---|---|---|
| eva024.3 | +2386 | +1409 | +977 | 41% | 37.9% |
| eva024.4 | +1705 | +952 | +753 | 44% | 36.5% |
| eva024.5 | +1496 | +921 | +575 | 38% | 32.9% |
| eva024.6 | +1911 | +1105 | +807 | 42% | 37.9% |
| eva024.7 | +1486 | +694 | **+792** | **53%** | 39.1% |
| eva024.8 | +1771 | +912 | +859 | 49% | 38.7% |
| eva024.9 | +2024 | +1198 | +826 | 41% | 37.9% |
- **趋势侧是利润的近一半**（不是小补贴）。趋势单胜率 33~39%，靠不对称盈利（最大赢 +$75~89 vs 最大亏 −$23~27）。
- **你第1点的逻辑成立**：砍单与趋势单同瞬触发，**趋势胜率低=砍单准确率低**；提高趋势精度同时改善"趋势侧利润 + 砍单准确率"，是高杠杆。

### 3.2 砍仓为什么有效（机制，已用代码核实）
关砍后(.9f vs .9)：被砍的 898 笔网格大多回去回归了（回归笔数 1546→2377），**但回归账本胜率 86.5%→71.6%、利润 +$6276→+$2207**，并冒出 `cutoff_line_stop`(−$1115)+`last_order_stop`(−$692) 深尾灾难。
- 机制根源（§1.6）：逆势网格堆积 → `AdjustBaseline` 把基线朝亏损方向越拖越快 → 整篮 TP 漂移、回归质量塌、马丁逼近尾部线。砍掉逆势网格=净仓归零、基线停拖、顺势账本干净回归。

### 3.3 发现：出场原因标签 bug（§1.7 机制导致）
- 砍逆势网格（1642）先设 `"trend_close_opposite_grid"`，但 `ManageTrendOrders`（1904）**每个 tick 都把全局覆写成 `"trend_state_exit"`**，而成交落盘延迟 → **砍网格成交被错标为 `trend_state_exit`**（数据里根本无 `trend_close_opposite_grid`）。
- 影响：审计里"网格被砍"和"趋势单状态退出"混在同一标签下，难以分别归因。经济解读不变（grid+trend_state_exit 实为被砍网格），但 **eva025 应修**（方法3）。

### 3.4 真OOS(2026-06)与稳健性
- 7 组里 6 组 6 月为负；6 月是震荡假突破月，8 根突破信号误砍多（半个账本）。
- edge 真实但薄、月度 lumpy（集中于强现金牛月份）。**推实盘前需更长的真前向窗口复核。**

---

## 4. eva025 改进方案（重新讨论）

### 4.1 方法1（主方案，采纳你的设计）：双趋势 —— 宽松趋势管交易、严格趋势管砍仓
**动机**：砍单准确率低源于"砍仓用的是和开趋势单同一个（偏灵敏的）信号"。把**砍仓的触发**换成一个**更严格、更晚确认**的趋势，就能少误砍（震荡假突破不会达到严格确认），而真趋势仍会达到严格确认、照样砍掉尾部。趋势单与逆势网格禁开仍用原（宽松）信号，保留趋势侧的不对称盈利。

**实现要点（待你确认后我写代码）**：
- 新增一套"严格趋势"评估 `EvaluateStrictTrendSignals()` + 严格参数组：
  - **严格趋势突破窗口** `InpStrictBreakoutBars`（默认 50，对比宽松的 `InpTrendBreakoutBars=8`）
  - **严格趋势连续确认根数** `InpStrictConfirmBars`（默认 4，对比宽松 2）
  - **严格趋势最小RVRatio** `InpStrictMinRVRatio`（默认 0.030，对比宽松 0.019）
  - 可选 **严格趋势需高周期EMA对齐** `InpStrictUseHigherTF`（默认 false；true 时要求如 M15 EMA 同向）
- 把砍仓逻辑（现 1640–1647）从"宽松状态切换时砍"改为"**严格趋势确认时砍**"；宽松状态机继续驱动趋势单与逆势网格禁开。
- 退化兼容：把严格参数设成与宽松一致，即回到当前行为。

**预期与风险**：少砍浅亏误砍（省 §上轮 −$283~−$661/组）；但真趋势上砍得更晚→被砍的那批会更深（单笔亏更大）。**净效果须回测**——这正是要寻参/对照的点。

### 4.2 方法2（可叠加/备选）：深度条件砍
砍仓时只平**当前浮亏 ≥ 阈值**的逆势网格，浮盈/浅亏放过。新增：
- **趋势砍仓最小浮亏（ATR倍数）** `InpGridCutMinFloatLoss_ATR`（默认 0.5；=0 退回全砍）。
- 可与方法1叠加（严格确认 + 只砍深亏的），双重过滤。

### 4.3 方法3（顺手修）：出场原因标签
把单一全局 `G_EvaExitReason` 改为**按 position_id 记录待落盘原因**（砍仓时给被砍仓位单独打 `trend_close_opposite_grid`），让审计能区分"被砍网格"与"趋势单状态退出"。零策略影响、纯审计修复。

### 4.4 趋势单本身（可选）：加 ATR 止盈提胜率
`InpTrendTP_ATR_Mult` 由 0 改为如 1.5~2.0，锁小赢、牺牲大赢，提高趋势单胜率（即提升砍单"事后正确"的比例）。但会削弱不对称盈利，**须与方法1对照**，优先级中。

### 4.5 优先级与诚实预期
- **趋势侧占利润 ~45% + 砍单准确率同源** → 方法1（提精度）是当前最高杠杆方向，符合你的判断。
- 但 edge 仍薄、真OOS仅1月偏负 → 任何单一改动都"小而稳"，**最终要靠更长前向窗口验证 + 方法1/2 组合寻参**。

### 4.6 待你拍板
1. eva025 就按 **方法1（双趋势）为主 + 方法3（修标签）** 来，我直接写 `eva025_*.mq5` 并附逐行改动说明，可以吗？
2. 严格趋势是否要 **高周期EMA对齐**（`InpStrictUseHigherTF`，更严但更滞后）？还是先只用"更长突破窗+更多确认根+更高RV"三件套？
3. 是否同时叠 **方法2（深度条件砍）**，还是先单上方法1看纯效果？
4. 趋势单 ATR 止盈这轮上不上？

---

## 5. 代码 / 参数 changelog（含规划）
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva023 | EA | `CloseOppositeGridOnTrend=true` → 净利首正 +$98 |
| eva024 | EA | 网格因子变指数(0.5/0.5)替代固定指数+clip；高位安全帽防极端尖刺 |
| eva024 寻参/关砍 | 7+3 set | 寻参 .3~.9；关砍 .4f/.8f/.9f 证明砍仓有效 |
| **eva025（规划）** | **EA** | **方法1 双趋势**：新增严格趋势(`InpStrictBreakoutBars=50`/`InpStrictConfirmBars=4`/`InpStrictMinRVRatio=0.030`[/`InpStrictUseHigherTF`])，砍仓改由严格趋势触发；宽松趋势仍管趋势单与逆势禁开。**方法3**：出场原因改按仓位记录，修 `trend_close_opposite_grid` 被覆写。可选 **方法2** `InpGridCutMinFloatLoss_ATR=0.5` 深度条件砍、**趋势单 `InpTrendTP_ATR_Mult` 加止盈** |

### 本轮发现（关键，供追溯）
- 已逐块读通代码（§1）：主循环顺序、变指数距离、基线朝亏损方向拖、双尾部止损、趋势状态机、审计落盘。
- 趋势侧占利润 40~45%（非小补贴）；趋势单胜率33~39%=砍单准确率（砍单与趋势单同瞬触发）。
- 砍仓有效机制=阻断"逆势堆仓→基线被拖→回归质量塌+深尾灾难"。
- bug：单一全局出场原因被覆写 → 砍网格错标 `trend_state_exit`。
- GridZ 非无效，是高波动网格扩张倍率（更正上版）。

---

*本日志随版本更新；代际默认进位。代码/参数改动在 §5 追加。*
*（以上为工程与分析记录，不构成投资建议；改动后务必在测试器充分验证。）*
