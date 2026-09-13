# Exness / MT5 量化策略开发协作摘要

## 一、当前目标

我正在使用 Exness 上的 MT5 跑量化策略。  
目前我已经有一个策略方法，并且已经调整出一组参数，可以用 MT5 做回测。

现在的问题不是单纯继续优化参数，而是希望建立一套更系统的策略开发流程：

1. 判断哪些单子本来就不应该开；
2. 判断亏损到底是参数问题、出场问题、入场逻辑问题，还是方法本身的问题；
3. 找出过去加入的哪些规则、过滤器、参数可能是无用的，可以删除；
4. 避免策略在训练集有效、测试集失效；
5. 建立一个可复用、可流水线化的回测分析系统。

---

## 二、核心共识：不要只看 MT5 最终回测报告

MT5 最终回测报告过于浓缩，只能看到：

- 开仓时间；
- 平仓时间；
- 开仓价；
- 平仓价；
- 盈亏；
- 持仓时间；
- 一些总体统计指标。

这些信息不足以判断一笔单的问题。

例如，一笔亏损单可能有几种完全不同的原因：

### 情况 1：入场逻辑错误

开仓后价格几乎立刻反向，最大浮盈很小，最大浮亏很大。

这类单子更可能是开仓逻辑有问题。

### 情况 2：入场方向对了，但出场逻辑差

开仓后曾经有很大浮盈，例如 +2R，最后却亏损出场。

这不是入场问题，更可能是止盈、移动止损、保本、出场逻辑的问题。

### 情况 3：方法没错，但参数不合适

比如止损太小，被正常波动扫掉，随后价格继续向原方向运行。

这更像是参数问题，而不是方法问题。

### 情况 4：方法只适合某类行情

比如突破策略在趋势行情有效，但在低波动震荡行情中连续亏损。

这不是简单调参数能解决的，而是需要增加市场状态识别，或者限制某些信号的使用场景。

---

## 三、需要把策略变成“可审计策略”

后续开发重点不是继续盲目加参数，而是让每一笔交易都能解释清楚：

- 为什么开这笔单？
- 是哪个 `signal_id` 触发？
- 当时趋势状态是什么？
- 当时波动状态是什么？
- 点差是多少？
- 过滤器通过了哪些？
- 开仓后价格路径如何？
- 最大浮盈 MFE 是多少？
- 最大浮亏 MAE 是多少？
- 最后是怎么出场的？
- 这笔单属于正常亏损，还是逻辑错误？

---

## 四、原始方案：EA 在回测时输出完整交易日志

最开始讨论的方案是：  
在 EA 回测过程中增加日志系统，让 EA 输出几类 CSV。

### 1. `trade_summary.csv`

一笔单一行，记录最终交易结果。

建议字段：

```csv
run_id,strategy_version,parameter_set_id,ticket,symbol,timeframe,direction,entry_time,exit_time,entry_price,exit_price,sl,tp,profit,r_multiple,signal_id,entry_reason,exit_reason,spread_at_entry,atr_at_entry,trend_state,session,mae,mfe,bars_held
```

用途：

- 看每笔单最终表现；
- 分析不同 `signal_id` 的表现；
- 找出哪些信号在测试集表现差；
- 判断哪些亏损是正常亏损，哪些是问题单。

### 2. `trade_path.csv`

一笔单多行，记录持仓期间的价格路径。

建议字段：

```csv
ticket,bar_index,time,open,high,low,close,spread,atr,ma_fast,ma_slow,rsi,unrealized_profit,unrealized_r,mfe,mae
```

用途：

- 判断开仓后是否先走对；
- 判断是否止损太近；
- 判断是否出场太差；
- 判断是否进入后马上反向；
- 判断持仓期间市场结构是否改变。

### 3. `signal_audit.csv`

记录每次信号判断，而不只是已成交订单。

建议字段：

```csv
time,symbol,timeframe,signal_id,direction,signal_strength,condition_1,condition_2,condition_3,filter_spread,filter_atr,filter_trend,allowed_to_trade,reason_if_blocked
```

用途：

- 判断哪些信号被允许开仓；
- 哪些信号被过滤器挡住；
- 哪些过滤器有价值；
- 哪些过滤器只是减少交易次数，却没有改善结果；
- 找出被错误过滤掉的好机会。

---

## 五、后来修正后的更优方案：行情数据与回测事件解耦

后来进一步讨论后，认为更好的工程化方案不是让 EA 在回测中输出所有 tick 或所有路径，而是建立独立的数据流水线。

最终建议架构：

```text
行情数据仓库
↓
MT5 回测输出交易事件
↓
后处理脚本根据交易时间切片行情
↓
生成增强版交易分析数据
↓
再进行策略诊断
```

也就是说：

- 行情数据只导出一次；
- EA 回测只输出交易事件和信号状态；
- 后处理程序根据 `entry_time` / `exit_time` 从行情数据仓库中切出对应数据；
- 分析过程和回测过程分离；
- 一台机器可以跑 MT5 回测；
- 另一台机器可以整理数据和做分析；
- 后续跑多组参数时，可以复用同一套行情数据。

---

## 六、关于“能不能直接读取 MT5 底层文件”

讨论结论：

不建议直接解析 MT5 的底层历史数据文件。

原因：

1. MT5 本地确实有历史缓存文件，例如 tick 和 K 线数据文件；
2. 但这些文件格式不是稳定的公开接口；
3. 不同 MT5 build、不同券商、不同服务器可能有差异；
4. 直接读底层文件可能和回测实际使用的数据不完全一致；
5. 后续维护成本高。

更建议使用官方接口导出数据，例如：

- MQL5 脚本使用 `CopyTicksRange()` 导出 tick；
- MQL5 脚本使用 `CopyRates()` 导出 K 线；
- 或 Python 的 MetaTrader5 包使用 `copy_ticks_range()` / `copy_rates_range()` 导出数据。

重点：

不是破解 MT5 的隐藏数据，而是通过 EA 或脚本把 MT5 本来能访问的数据导出为 CSV / Parquet，形成自己的行情数据库。

---

## 七、推荐的数据仓库结构

建议不要把所有数据导出成一个巨大 CSV，而是按品种、周期、月份分块保存。

示例：

```text
data/
  XAUUSD/
    ticks/
      2024-01.parquet
      2024-02.parquet
      2024-03.parquet
    m1/
      2024-01.parquet
      2024-02.parquet
    m5/
      2024-01.parquet
      2024-02.parquet
```

tick 数据字段建议：

```csv
time_msc,time,bid,ask,last,volume,flags,spread
```

K 线数据字段建议：

```csv
time,open,high,low,close,tick_volume,spread,real_volume
```

---

## 八、为什么不要一开始只导出 tick，也要导出 M1/M5

tick 数据适合精确计算：

- MFE；
- MAE；
- 是否扫损；
- 点差变化；
- 开仓后短时间内的反应；
- 是否先到过 TP 或 SL 附近。

但市场结构判断不一定需要 tick。

M1 / M5 更适合判断：

- 趋势状态；
- 震荡状态；
- ATR；
- 均线结构；
- 前高前低；
- 突破位置；
- K 线形态；
- 波动区间。

所以建议行情仓库同时包含：

```text
tick 数据 + M1 数据 + 当前策略周期数据
```

---

## 九、EA 回测时应该输出什么

EA 不应该输出所有 tick，而应该尽量轻量，只输出交易事件和信号状态。

### 1. `trade_events.csv`

建议字段：

```csv
run_id,strategy_version,parameter_set_id,ticket,symbol,timeframe,direction,signal_id,entry_time,entry_time_msc,entry_price,sl,tp,exit_time,exit_time_msc,exit_price,profit,commission,swap,exit_reason
```

还可以加上开仓时上下文：

```csv
entry_reason,trend_state,volatility_state,session,spread_at_entry,atr_at_entry,filter_states
```

### 2. `signal_audit.csv`

记录信号判断过程：

```csv
run_id,time,symbol,timeframe,signal_id,direction,condition_states,filter_states,allowed_to_trade,reason_if_blocked
```

### 3. `run_config.csv`

记录本次回测配置：

```csv
run_id,strategy_version,parameter_set_id,symbol,timeframe,start_date,end_date,tester_model,account_currency,initial_deposit,spread_mode,commission_model,input_parameters
```

这样后续跑多组参数不会混乱。

---

## 十、后处理程序要做什么

后处理脚本读取：

```text
trade_events.csv
行情数据仓库 tick / M1 / M5
```

然后对每一笔单做：

1. 根据 `entry_time` / `exit_time` 提取对应 tick 路径；
2. 计算 MFE / MAE；
3. 计算最大顺向价格、最大逆向价格；
4. 判断是否先浮盈后亏损；
5. 判断是否刚开仓就反向；
6. 判断是否止损过近；
7. 判断是否方向正确但出场差；
8. 合并开仓前 N 根 K 线；
9. 生成 `trade_enriched.csv`；
10. 生成 `problem_trades.csv`；
11. 生成 `signal_performance.csv`；
12. 生成 `regime_performance.csv`。

最终用于分析的核心文件：

```csv
ticket,signal_id,direction,entry_time,exit_time,profit,r,mfe_r,mae_r,max_favorable_price,max_adverse_price,path_type,problem_tag
```

---

## 十一、参数问题 vs 方法问题的判断框架

### 更像参数问题的情况

如果出现这些现象，更像是参数问题：

1. 当前参数表现一般，但附近参数也还能活；
2. 参数稍微放宽或收紧后，策略逻辑仍然成立；
3. 亏损主要来自止损太小、止盈太远、过滤阈值太严或太松；
4. 同类信号在多数市场环境下仍有正向表现；
5. 训练集和测试集差异不大，只是强弱不同；
6. 参数不是一个孤立最优点，而是附近一片区域都还可以。

示例：

```text
ATR 止损倍数 1.4、1.5、1.6、1.7 都能接受，只是 1.6 最好。
```

这说明方法可能有稳定性，只是参数需要调整。

### 更像方法问题的情况

如果出现这些现象，更像是方法问题：

1. 只有某一个非常精确的参数组合赚钱，附近参数全部不行；
2. 训练集很好，测试集明显失效；
3. 某类 `signal_id` 在测试集长期亏损；
4. 亏损集中在固定市场状态，例如低波动震荡、趋势末端、假突破；
5. 单子经常开仓后立刻反向，MFE 很小，MAE 很大；
6. 增加或减少参数都无法改善同类亏损；
7. 近期年份明显失效。

示例：

```text
breakout_v1 在训练集 PF = 1.8，但测试集 PF = 0.7，并且亏损集中在低 ATR 震荡行情。
```

这不是简单调参问题，而是开单逻辑或使用场景有问题。

---

## 十二、黄金多年数据的问题

黄金 XAUUSD 最近几年的行情和更早年份可能差异很大。  
所以不建议简单把很多年数据混在一起，找一个所谓“历史最优参数”。

不推荐：

```text
把 2018–2026 全部混在一起优化，找一组万能参数。
```

更推荐：

```text
用多年数据判断方法适合什么市场状态；
用近几年数据作为主要开发依据；
用最近一年或最近几个月做测试和 forward-like 验证；
旧年份用于压力测试，而不是直接主导参数选择。
```

示例切分方式：

```text
2018–2021：旧环境压力测试
2022–2024：主要开发区间
2025：测试集
2026：盲测 / forward test
```

或者滚动测试：

```text
训练：2021–2022
测试：2023

训练：2022–2023
测试：2024

训练：2023–2024
测试：2025

训练：2024–2025
测试：2026
```

多年数据的价值不是找到一个万能参数，而是判断：

- 策略怕不怕震荡；
- 怕不怕低波动；
- 怕不怕高波动；
- 是否只适合单边行情；
- 是否怕亚洲盘；
- 是否怕假突破；
- 是否只在某些宏观环境下有效；
- 最近市场结构变化后是否仍然有效。

---

## 十三、后续工作流程

下一步准备把 EA 代码和参数发给 ChatGPT。

第一阶段目标不是直接优化收益，而是先把 EA 改造成“可审计版本”。

计划：

```text
第 1 步：提供当前 EA 代码、参数、品种、周期、回测区间；
第 2 步：ChatGPT 保持交易逻辑不变，只增加日志输出；
第 3 步：EA 输出 trade_events.csv、signal_audit.csv、run_config.csv；
第 4 步：再设计独立的 tick / K 线数据导出脚本；
第 5 步：建立行情数据仓库；
第 6 步：用后处理脚本把交易事件和行情路径合并；
第 7 步：生成 trade_enriched.csv；
第 8 步：分析问题单；
第 9 步：判断是参数问题、出场问题、入场逻辑问题、过滤器问题，还是方法问题；
第 10 步：再决定修改策略逻辑、删除规则、还是重新调参。
```

---

## 十四、给下一轮需要提供的内容

下一轮开始时，需要提供：

1. 当前 EA 的 `.mq5` 核心代码；
2. 当前这一组参数；
3. 品种，例如 XAUUSD；
4. 时间周期，例如 M1、M5、M15；
5. 当前使用的回测模式，最好说明是否是真实 tick；
6. 训练集时间范围；
7. 测试集时间范围；
8. 当前方法的自然语言解释；
9. 最怀疑的问题，例如追单、震荡亏损、止损太近、出场太差；
10. 是否希望第一版只做日志改造，不改变交易逻辑。

下一轮目标：

```text
先让 ChatGPT 修改 EA，让它输出 trade_events.csv、signal_audit.csv、run_config.csv。
第一版尽量不改变交易逻辑。
后续再配合行情数据导出和 Python 后处理脚本。
```

---

## 十五、当前最终结论

最终选择的方向是：

```text
不直接解析 MT5 底层历史文件；
使用官方接口导出 tick / K 线数据；
建立独立行情数据仓库；
EA 回测只输出交易事件和信号状态；
后处理程序根据交易时间切片行情；
分析过程和回测过程解耦；
支持多机器并行；
支持多参数批量回测；
最终通过 trade_enriched.csv 判断问题单和策略逻辑缺陷。
```

这比让 EA 在回测过程中输出所有 tick 更优雅、更快、更可复用。

第一版开发重点：

```text
保持交易逻辑不变；
增加 run_id / parameter_set_id；
输出 trade_events.csv；
输出 signal_audit.csv；
输出 run_config.csv；
为后续数据切片和策略诊断做准备。
```
