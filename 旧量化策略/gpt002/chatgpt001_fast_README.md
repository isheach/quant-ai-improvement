# chatgpt001_fast 说明文件

## 1. 为什么重写

上一版 `chatgpt001.mq5` 仍然保留了太多原始代码结构：审计 CSV、图表面板、Tester 评分、状态日志、重复持仓扫描、历史遗留风控分支等。  
这些内容对研究很有用，但对 MT5 优化器非常不友好，尤其是 Exness XAUUSD 小账户参数寻优时，会显著拖慢速度。

`chatgpt001_fast` 是一次瘦身重写，不再在原文件上堆补丁。

## 2. 删除的内容

已删除或不再实现：

```text
1. CSV 审计日志
2. decision_audit / trade_events
3. 图表 Dashboard
4. 基线画线对象
5. OnTester 自定义评分打印
6. 大量 Print 状态机日志
7. 周末复杂处理
8. 旧版本输入参数残留
9. 多重历史兼容逻辑
10. 重复遍历仓位的辅助函数
11. 与核心交易无关的可视化和调试逻辑
```

## 3. 保留的核心逻辑

```text
1. 固定手数测试，默认 0.01 手
2. 利滚利 / 动态手数功能保留，但默认关闭
3. 动态基线
4. 波动率缩放网格距离
5. 宽松趋势：开 Alpha 趋势单 + 禁止逆势新网格
6. 严格趋势：用于保护趋势单和分批砍仓
7. ADX 趋势强度闸门
8. 保护性趋势单
9. 分批趋势砍仓
10. 普通 / 大 / 系统冷静期
11. 趋势单 ATR SL、保本、trailing、时间止损
```

## 4. 速度优化点

```text
1. 默认只在 M1 新 K 线运行一次：InpProcessOnNewM1BarOnly=true
2. 趋势指标只在趋势周期新 K 线更新
3. 持仓扫描集中为 BuildGridSideStats()
4. 不写文件
5. 不画图
6. 不输出日志
7. 不使用 OnTester 自定义复杂计算
8. 网格、趋势、砍仓全部轻量化判断
```

## 5. 主流程

```text
OnTick
 └─ 如果不是新 M1 K 线，直接 return
 └─ 更新趋势快照
 └─ 系统硬风控
 └─ 扫描 BUY / SELL 网格篮子
 └─ 更新基线
 └─ 管理趋势单退出和 trailing
 └─ 管理网格基线出场和网格止损
 └─ 重新扫描网格
 └─ 开 Alpha 趋势单
 └─ 管理保护性趋势单和趋势分批砍仓
 └─ 重新扫描网格
 └─ 网格开仓
```

## 6. 默认场景

```text
品种：Exness XAUUSD / XAUUSDm
初始资金：400 USD
测试手数：固定 0.01
利滚利：保留但关闭
趋势单：开启
保护趋势单：开启
趋势全平：默认关闭，只做分批
```

## 7. 参数说明

### 基础参数

| 参数 | 默认 | 含义 |
|---|---:|---|
| `InpFixedLot` | 0.01 | 固定手数，测试阶段建议固定 |
| `InpUseDynamicLot` | false | 利滚利开关 |
| `InpDynBaseCapital` | 400 | 动态手数参考资金 |
| `InpDynMaxLot` | 0.03 | 动态手数上限 |
| `InpProcessOnNewM1BarOnly` | true | 只在 M1 新 K 线运行，极大提速 |

### 网格参数

| 参数 | 默认 | 范围建议 | 含义 |
|---|---:|---:|---|
| `InpGridBasePoints` | 8000 | 5000~12000 | 基础网格距离 |
| `InpGridMinPoints` | 2500 | 1500~4500 | 最小网格距离 |
| `InpGridVolRefPct` | 0.024 | 0.015~0.045 | ATR/价格参考波动率 |
| `InpGridExpCoef` | 1.35 | 1.10~1.70 | 加仓网格扩张倍数 |
| `InpGridMaxPositionsPerSide` | 3 | 2~4 | 单边最大网格数量 |
| `InpBaselineFreeAlpha` | 0.12 | 0.05~0.25 | 空仓时基线追价速度 |
| `InpBaselineHoldAlpha` | 0.025 | 0.005~0.060 | 持仓时基线追价速度 |
| `InpGridMinMinutesBetweenAdds` | 12 | 5~40 | 同边加仓最小间隔 |

### 趋势信号参数

| 参数 | 默认 | 范围建议 | 含义 |
|---|---:|---:|---|
| `InpTrendTF` | M5 | M1~M15 | 趋势判断周期 |
| `InpTrendFastEMA` | 20 | 10~40 | 快 EMA |
| `InpTrendSlowEMA` | 60 | 40~100 | 慢 EMA |
| `InpTrendBreakoutBars` | 30 | 15~60 | 宽松趋势突破窗口 |
| `InpTrendMinRVPct` | 0.020 | 0.010~0.045 | 趋势最小 ATR/价格 |
| `InpTrendConfirmBars` | 2 | 1~4 | 宽松趋势确认根数 |

### Alpha 趋势单参数

| 参数 | 默认 | 范围建议 | 含义 |
|---|---:|---:|---|
| `InpEnableTrendOrders` | true | true/false | 开启趋势单 |
| `InpTrendSL_ATR_Mult` | 2.20 | 1.60~3.20 | 趋势初始止损 ATR 倍数 |
| `InpTrendTrail_ATR_Mult` | 2.80 | 1.80~4.20 | 趋势移动止损 ATR 倍数 |
| `InpTrendEntryMaxDistATR` | 1.20 | 0.60~2.00 | 入场不能离 fast EMA 太远 |
| `InpTrendBreakEvenR` | 1.00 | 0.50~1.50 | 盈利几 R 推保本 |
| `InpTrendTrailStartR` | 1.00 | 0.50~2.00 | 盈利几 R 启动 trailing |
| `InpTrendTimeStopBars` | 8 | 4~16 | 趋势不展开时的时间止损 |

### 保护趋势单参数

| 参数 | 默认 | 范围建议 | 含义 |
|---|---:|---:|---|
| `InpEnableProtectiveTrend` | true | true/false | 开启保护趋势单 |
| `InpProtectiveHedgeRatio` | 0.30 | 0.10~0.60 | 保护单手数 = 逆势网格手数 × 比例 |
| `InpProtectiveMaxLot` | 0.03 | 0.01~0.05 | 保护趋势单最大手数 |
| `InpProtectiveMinLossPerLot` | 250 | 150~700 | 触发保护单的篮子亏损 |
| `InpProtectiveMinAdverseATR` | 0.80 | 0.50~1.75 | 触发保护单的偏离 ATR |

### 趋势砍仓参数

| 参数 | 默认 | 范围建议 | 含义 |
|---|---:|---:|---|
| `InpEnableAdaptiveTrendCut` | true | true/false | 开启自适应趋势砍仓 |
| `InpCutADXMin` | 22 | 16~30 | ADX 最低门槛 |
| `InpCutADXMeanMult` | 1.20 | 0.90~1.50 | ADX 动态均值倍数 |
| `InpCutMinSidePositions` | 2 | 1~3 | 至少几笔逆势网格才砍 |
| `InpCutMinLossPerLot` | 350 | 150~900 | 逆势篮子每手亏损门槛 |
| `InpCutMinAdverseATR` | 1.00 | 0.50~2.50 | 逆势偏离 ATR 倍数 |
| `InpCutMinAdverseGridFrac` | 0.45 | 0.25~0.85 | 偏离占虚拟网格跨度比例 |
| `InpCutPartialOrders` | 1 | 1~2 | 每次分批平几单 |
| `InpCutAllowFullClose` | false | false/true | 是否允许趋势引擎全平逆势网格 |

## 8. 与上一版的关键差异

| 项目 | 上一版 chatgpt001 | 新版 chatgpt001_fast |
|---|---|---|
| 行数 | 约 4857 行 | 约 1000~1500 行 |
| 审计 CSV | 有 | 删除 |
| 图表面板 | 有 | 删除 |
| 状态日志 | 多 | 默认无 |
| Tester 评分 | 有 | 删除 |
| 每 tick 计算 | 多 | 默认 M1 新 K 执行 |
| 代码目标 | 功能完整 | 优化器速度优先 |
| 策略逻辑 | 多历史兼容 | 核心逻辑重写 |

## 9. 建议测试顺序

```text
1. 先编译 chatgpt001_fast.mq5
2. 固定 0.01 手跑 XAUUSD 近 3~6 个月
3. 确认交易数量和速度
4. 再跑 2~3 年长样本
5. 再启用 ranges.set 分阶段寻参
6. 固定手数稳定后，才测试 InpUseDynamicLot=true
```

## 10. 如果速度仍然慢

可进一步关闭：

```text
InpEnableTrendOrders=false
InpEnableProtectiveTrend=false
InpEnableAdaptiveTrendCut=false
InpStrictUseHTF=false
InpCutRequireADXRising=false
```

其中提速最明显的是：

```text
InpProcessOnNewM1BarOnly=true
InpStrictUseHTF=false
```

但关闭趋势和保护逻辑会改变策略本质，只建议用于拆分测试。
