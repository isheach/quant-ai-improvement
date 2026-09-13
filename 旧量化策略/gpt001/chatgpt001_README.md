# chatgpt001 使用说明：Exness XAUUSD 自适应趋势网格 EA

## 0. 重要说明

`chatgpt001` 是基于你原始 `eva025b_VolumetricPulseGrid_StateMachine.mq5` 思路改造的新版本。  
目标不是承诺盈利，而是让策略更适合系统化回测、分模块观察、参数优化和后续实盘灰度测试。

当前默认场景：

| 项目 | 默认设定 |
|---|---|
| 交易品种 | Exness XAUUSD / XAUUSDm / 黄金差价合约 |
| 初始资金 | 约 400 USD |
| 测试阶段手数 | 固定 0.01 手 |
| 利滚利 | 保留，但默认关闭 |
| 趋势单 | 保留，默认开启 |
| 保护性趋势单 | 默认开启 |
| 趋势砍仓 | 默认使用严格趋势 + ADX + 篮子压力 + 分批减仓 |
| 日志 / 面板 | 默认关闭，提升优化速度 |

我无法在当前环境内调用 MetaEditor 编译 `.mq5`。请你导入 MT5 后先编译一次；如有编译报错，把报错行号和错误信息发我，我可以继续按行号修复。

---

## 1. 策略核心思想

旧逻辑容易出现的问题是：

```text
趋势确认 → 立即平掉所有逆势网格
```

`chatgpt001` 改成：

```text
宽松趋势 → 开 Alpha 趋势单 + 禁止逆势新网格
严格趋势 → 检查逆势网格篮子压力
压力较浅 → 冻结，不砍
压力中等 → 优先开保护性趋势单
压力继续扩大 → 分批减仓
账户级风险失控 → 硬风控接管
```

整体结构：

```text
Grid Engine            负责震荡回归现金流
Alpha Trend Engine     负责低胜率高赔率趋势收益
Protective Trend       负责逆势网格压力下的顺势保护
Trend Cut Engine       负责分层处理逆势网格风险
Risk Engine            负责严重风险和系统硬保护
```

---

## 2. 主交易流程

EA 主要在 M1 新分钟节奏上运行，趋势识别默认使用 M5。

简化流程：

```text
1. 更新波动率、基线、趋势状态、ADX
2. 检查系统硬冷静期 / 净值峰值硬保护
3. 处理风险4强制退出
4. 构建网格持仓快照
5. 执行原有网格止损、虚拟末单线止损
6. 执行风险等级管理
7. 网格回归基线平仓
8. 管理已有趋势单：保本、移动止损、时间止损、状态退出
9. 宽松趋势下开 Alpha 趋势单
10. 严格趋势下执行保护性趋势单 / 分批减仓
11. 若风险允许，执行网格开仓
```

---

## 3. 网格交易逻辑

网格仍然是策略的现金流核心。

### 开 BUY 网格

```text
价格低于基线，且距离达到动态网格间距
并且没有被趋势状态、风险状态、冷静期、点差过滤阻止
```

### 开 SELL 网格

```text
价格高于基线，且距离达到动态网格间距
并且没有被趋势状态、风险状态、冷静期、点差过滤阻止
```

### 网格平仓

```text
BUY 网格：价格回到基线以上，平 BUY 网格
SELL 网格：价格回到基线以下，平 SELL 网格
```

### 趋势状态下的网格门控

```text
宽松上涨趋势：禁止新开 SELL 网格
宽松下跌趋势：禁止新开 BUY 网格
```

已有逆势网格不会因为宽松趋势直接全平。

---

## 4. Alpha 趋势单逻辑

Alpha 趋势单是保留的赚钱模块，负责捕捉大趋势。

### 入场

```text
G_MarketState = TREND_UP   → 尝试开 BUY 趋势单
G_MarketState = TREND_DOWN → 尝试开 SELL 趋势单
```

入场过滤：

```text
1. 当前不是系统硬冷静期
2. 同方向趋势单不存在
3. 趋势单数量未超过 InpTrendMaxPositions
4. 与上一次趋势开单间隔达到 InpTrendMinBarsBetweenEntries
5. 价格距离 fast EMA 没有太远
6. 点差低于 InpMaxSpreadPoints
7. 可选 ADX 软过滤通过
```

### 手数

测试默认：

```text
InpTrendUseGridLot = true
InpTrendUseRiskLot = false
```

也就是趋势单默认沿用当前网格固定手数 0.01。

实盘利滚利或风险手数模式可以后续启用：

```text
InpUseDynamicLot = true
或
InpTrendUseRiskLot = true
```

---

## 5. 趋势单退出 / 持仓管理

趋势单使用 ATR 初始止损：

```text
SL = ATR × InpTrendSL_ATR_Mult
```

移动止损不是一开仓就启动，而是分层：

```text
浮盈 < InpTrendBreakEvenR：
    不移动止损，给趋势发育空间

浮盈 >= InpTrendBreakEvenR：
    止损推到保本附近

浮盈 >= InpTrendTrailStartR：
    启动 ATR trailing
```

如果趋势状态回到 RANGE：

```text
亏损或小盈利趋势单：可以平掉
盈利超过 InpTrendRunnerMinR 的趋势 runner：继续持有，交给 trailing
```

如果出现反向趋势确认：

```text
平掉原方向趋势单
```

时间止损：

```text
开仓后 InpTrendTimeStopBars 根趋势K线内，
如果有利移动不足 InpTrendTimeStopMinMoveATR × ATR，
说明趋势没有展开，可以提前退出。
```

---

## 6. 保护性趋势单

保护性趋势单不是普通 Alpha 单，而是用于“逆势网格有压力，但还不想直接砍仓”的过渡层。

例子：

```text
严格上涨趋势确认
账户里存在 SELL 网格
SELL 网格已经中等浮亏
→ 优先开 BUY 保护趋势单
→ 不立刻全平 SELL 网格
```

保护趋势手数：

```text
保护趋势手数 = 逆势网格总手数 × InpProtectiveTrendHedgeRatio
```

并受 `InpProtectiveTrendMaxLot` 限制。

默认：

```text
InpProtectiveTrendHedgeRatio = 0.30
InpProtectiveTrendMaxLot = 0.03
```

---

## 7. 自适应趋势砍仓

趋势砍仓不再是一刀切。

砍仓评估必须同时看：

```text
1. 严格趋势是否成立
2. ADX 强度是否足够
3. DI 方向是否和趋势方向一致
4. 逆势网格持仓数是否足够多
5. 逆势篮子每手浮亏是否足够大
6. 价格不利偏离是否达到 ATR 倍数
7. 不利偏离是否达到虚拟网格跨度比例
8. 严格趋势确认后是否额外等待
```

动作优先级：

```text
条件不足：冻结逆势加仓
条件中等：开保护性趋势单
条件继续恶化：分批减仓，每次默认只平 1 单
极端情况：可选全平，但默认关闭，交给硬风控
```

默认：

```text
InpCutAllowFullClose = false
```

意思是趋势砍仓引擎默认不做“趋势一来就全平”，而是以保护趋势单和分批减仓为主。

---

## 8. 冷静期逻辑

原代码已有普通冷静期和大冷静期，`chatgpt001` 没有简单粗暴地“一亏就全部停”。

趋势单的冷静期响应由：

```text
InpTrendCooldownMode
```

控制。

枚举含义：

```text
0 = TREND_COOLDOWN_IGNORE_GRID
    趋势单忽略网格冷静期

1 = TREND_COOLDOWN_RESPECT_BIG_ONLY
    普通冷静期不影响趋势单，大冷静期才限制 Alpha 趋势单
    默认推荐

2 = TREND_COOLDOWN_RESPECT_ALL
    所有冷静期都限制趋势单，最保守
```

保护性趋势单如果 `InpProtectiveIgnoreBigCooldown=true`，在大冷静期也可以继续开，用于保护逆势网格。

系统硬冷静期不同：

```text
净值峰值回撤硬保护触发后，所有新开仓都会被禁止
```

---

## 9. 利滚利 / 动态手数

默认关闭：

```text
InpUseDynamicLot = false
InpLotSize = 0.01
```

保留利滚利开关：

| 参数 | 含义 | 建议 |
|---|---|---|
| `InpUseDynamicLot` | 是否启用动态手数 | 测试阶段 false，实盘灰度后再 true |
| `InpLotByEquity` | 动态手数按余额还是净值 | 保守用 false；敏感用 true |
| `InpDynBaseCapital` | 第一档手数资金基准 | 400 USD |
| `InpDynBaseLotStep` | 每档增加手数 | 0.01 |
| `InpDynLevelCoef` | 档位资金门槛放大系数 | 1.2~2.0 |
| `InpDynMaxLot` | 动态手数上限 | 小账户建议 0.03~0.05 |

推荐实盘前测试顺序：

```text
1. 固定 0.01 手
2. 固定 0.02 手
3. 动态手数 + InpDynMaxLot = 0.03
4. 动态手数 + 更高上限
```

不要直接用动态手数优化总收益，否则很容易把回撤放大误认为策略变好。

---

## 10. 主要参数说明与建议范围

### A. 核心网格参数

| 参数 | 默认 | 建议范围 | 含义 |
|---|---:|---:|---|
| `InpRefPrice` | 3000 | 2500~4500 | 黄金参考价，建议接近回测区间均价 |
| `InpRefVolPct` | 0.024 | 0.015~0.045 | 参考百分比波动 |
| `InpGridZ` | 8000 | 5000~12000 | 基础网格距离 |
| `InpMinGridZ` | 2500 | 1500~4500 | 最小网格距离 |
| `InpMoveB` | 130 | 80~260 | 空仓基线追价速度 |
| `InpCoefC` | 63 | 30~120 | 持仓基线移动速度 |
| `InpCoefDecay` | 0.85 | 0.70~0.95 | 加仓后基线移动衰减 |
| `InpUniGridExpCoef` | 1.40 | 1.15~1.70 | 网格扩展倍数 |
| `InpUniMaxPos` | 3 | 2~4 | 最大网格持仓数 |

### B. 网格风控

| 参数 | 默认 | 建议范围 | 含义 |
|---|---:|---:|---|
| `InpRiskL3LossPerLot` | 900 | 500~1500 | 风险3亏损阈值 |
| `InpLastOrderLossPerLot` | 900 | 500~1600 | 最新单亏损止损阈值 |
| `InpUseCutoffLineStop` | true | true/false | 是否启用虚拟末单线硬止损 |
| `InpCooldownMinutes` | 120 | 30~240 | 普通冷静期 |
| `InpBigCooldownMinutes` | 840 | 360~1440 | 大冷静期 |

### C. 宽松趋势信号

| 参数 | 默认 | 建议范围 | 含义 |
|---|---:|---:|---|
| `InpTrendTimeframe` | M5 | M1~M15 | 趋势识别周期 |
| `InpTrendFastEMAPeriod` | 20 | 10~40 | 快 EMA |
| `InpTrendSlowEMAPeriod` | 60 | 40~100 | 慢 EMA |
| `InpTrendBreakoutBars` | 30 | 15~60 | 突破窗口 |
| `InpTrendMinRVRatio` | 0.020 | 0.010~0.045 | 趋势最小百分比波动 |
| `InpTrendConfirmBars` | 2 | 1~4 | 宽松趋势确认根数 |
| `InpBlockAgainstTrendGrid` | true | true/false | 趋势时禁止逆势新网格 |

### D. Alpha 趋势单

| 参数 | 默认 | 建议范围 | 含义 |
|---|---:|---:|---|
| `InpEnableTrendOrders` | true | true/false | 是否启用趋势单 |
| `InpTrendSL_ATR_Mult` | 2.20 | 1.60~3.20 | 初始止损 ATR 倍数 |
| `InpTrendTrail_ATR_Mult` | 2.80 | 1.80~4.20 | trailing ATR 倍数 |
| `InpTrendEntryMaxDistATR` | 1.20 | 0.60~2.00 | 入场距离 fast EMA 最大 ATR |
| `InpTrendTrailStartR` | 1.00 | 0.50~2.00 | 几 R 后启动 trailing |
| `InpTrendBreakEvenR` | 1.00 | 0.50~1.50 | 几 R 后推保本 |
| `InpTrendRunnerMinR` | 1.00 | 0.50~2.00 | RANGE 退出时保留 runner 的最小 R |
| `InpTrendTimeStopBars` | 8 | 4~16 | 时间止损观察窗口 |

### E. 严格趋势 / 保护 / 砍仓

| 参数 | 默认 | 建议范围 | 含义 |
|---|---:|---:|---|
| `InpCutUseStrictTrend` | true | true/false | 砍仓/保护是否用严格趋势 |
| `InpStrictBreakoutBars` | 50 | 40~100 | 严格突破窗口 |
| `InpStrictConfirmBars` | 4 | 3~8 | 严格趋势确认根数 |
| `InpStrictMinRVRatio` | 0.030 | 0.020~0.060 | 严格趋势 RV 门槛 |
| `InpStrictUseHigherTF` | true | true/false | 是否要求高周期同向 |
| `InpCutADXMin` | 22 | 16~30 | ADX 固定最低门槛 |
| `InpCutADXMeanMult` | 1.20 | 0.90~1.50 | ADX 动态均值倍数 |
| `InpCutMinLossPerLot` | 350 | 150~900 | 逆势篮子每手亏损门槛 |
| `InpCutMinAdverseATR` | 1.00 | 0.50~2.50 | 不利偏离 ATR 倍数 |
| `InpCutMinAdverseGridFrac` | 0.45 | 0.25~0.85 | 不利偏离占虚拟网格跨度比例 |
| `InpCutPartialOrders` | 1 | 1~2 | 每次分批减仓单数 |
| `InpCutAllowFullClose` | false | false/true | 是否允许趋势引擎全平逆势网格 |

### F. 保护性趋势单

| 参数 | 默认 | 建议范围 | 含义 |
|---|---:|---:|---|
| `InpEnableProtectiveTrend` | true | true/false | 是否启用保护趋势单 |
| `InpProtectiveTrendHedgeRatio` | 0.30 | 0.10~0.60 | 保护单手数比例 |
| `InpProtectiveTrendMaxLot` | 0.03 | 0.01~0.05 | 保护趋势单最大手数 |
| `InpProtectiveMinBasketLossPerLot` | 250 | 150~700 | 触发保护单的篮子亏损 |
| `InpProtectiveMinAdverseATR` | 0.80 | 0.50~1.75 | 触发保护单的偏离 ATR |

---

## 11. 建议优化流程

不要一次优化所有参数。建议分阶段。

### 阶段 1：固定手数观察机制

```text
InpUseDynamicLot=false
InpLotSize=0.01
InpEnableTradeAudit=false
InpShowDashboard=false
```

只看：

```text
总收益
最大回撤
浮亏持续时间
网格盈亏
趋势单盈亏
保护趋势单触发次数
趋势分批减仓次数
```

### 阶段 2：网格参数寻优

优先优化：

```text
InpGridZ
InpMinGridZ
InpUniGridExpCoef
InpUniMaxPos
InpCoefC
InpCoefDecay
InpX_Minutes
```

### 阶段 3：趋势 Alpha 寻优

优先优化：

```text
InpTrendFastEMAPeriod
InpTrendSlowEMAPeriod
InpTrendBreakoutBars
InpTrendMinRVRatio
InpTrendSL_ATR_Mult
InpTrendTrail_ATR_Mult
InpTrendEntryMaxDistATR
InpTrendTrailStartR
InpTrendBreakEvenR
```

### 阶段 4：趋势砍仓 / 保护寻优

优先优化：

```text
InpStrictBreakoutBars
InpStrictConfirmBars
InpStrictMinRVRatio
InpCutADXMin
InpCutADXMeanMult
InpCutMinLossPerLot
InpCutMinAdverseATR
InpCutMinAdverseGridFrac
InpProtectiveTrendHedgeRatio
```

### 阶段 5：利滚利压力测试

只在固定手数表现稳定后开启：

```text
InpUseDynamicLot=true
InpDynMaxLot=0.03
```

然后观察动态手数是否显著放大最大回撤。

---

## 12. 回测对照实验

建议至少跑：

```text
A. 纯网格：InpEnableTrendOrders=false，InpCloseOppositeGridOnTrend=false
B. 纯趋势：InpEnableGrid=false
C. 网格 + Alpha 趋势单，不砍网格
D. C + 禁开逆势网格
E. D + 自适应趋势砍仓
F. E + 保护性趋势单
G. F + 固定 0.02 手
H. F + 动态手数
```

核心比较：

```text
Grid PnL
Alpha Trend PnL
Protective Trend PnL
最大回撤
收益回撤比
趋势单最大单笔盈利
趋势单连续亏损阶段网格是否能覆盖
趋势砍仓是否减少极端浮亏
趋势砍仓是否误砍高胜率网格
```

---

## 13. 安装方式

1. 把 `chatgpt001.mq5` 放到：

```text
MQL5/Experts/
```

2. 把 `chatgpt001_XAUUSD_400USD_ranges.set` 放到你方便加载的位置，或在策略测试器里手动加载。

3. 打开 MetaEditor 编译 `chatgpt001.mq5`。

4. 策略测试器建议：

```text
Symbol: XAUUSD 或 Exness 对应黄金符号
Deposit: 400 USD
Model: Every tick based on real ticks（如果数据足够）
Timeframe: M1 挂载 EA
Trend timeframe: 默认 M5
```

5. 先固定手数跑样本内/样本外，再考虑利滚利。

---

## 14. 训练速度优化点

本版本默认关闭：

```text
InpEnableLog=false
InpEnableStateMachineLog=false
InpCutDecisionLog=false
InpEnableTesterLog=false
InpShowDashboard=false
InpShowBaselineLine=false
InpEnableTradeAudit=false
```

代码层面保留了原有的按新分钟处理、趋势指标缓存、ADX 缓存和优化时自动关闭审计的设计。  
大量 CSV 审计建议只在少量单次回测时开启，不建议在大规模优化时开启。

---

## 15. 风险提醒

400 美元做 XAUUSD 属于小账户高敏感场景。  
即使用 0.01 手，连续趋势、跳空、点差扩大和滑点都可能导致较大净值波动。  
建议先做固定手数、长样本、多年份、多点差压力测试，再考虑实盘小资金灰度。
