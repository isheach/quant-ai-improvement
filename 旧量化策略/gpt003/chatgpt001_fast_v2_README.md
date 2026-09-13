# chatgpt001_fast_v2 修复说明

## 1. 这次排查到的问题

你反馈从 2025 年到现在完全不开单，这不是正常现象。  
我重新检查 `chatgpt001_fast` 后，发现主要有三个问题。

### 问题 1：趋势 RV 阈值严重过高

上一版默认：

```text
InpTrendMinRVPct = 0.020
InpStrictMinRVPct = 0.030
```

代码里的 RV 是：

```text
ATR / close
```

也就是说 `0.020` 等于要求 M5 ATR 达到价格的 2%。  
黄金价格如果是 3000，M5 ATR 要达到 60 美元才会触发趋势，这几乎不可能。  
所以趋势单基本被锁死。

v2 改为：

```text
InpTrendMinRVPct = 0.00035   // 0.035%
InpStrictMinRVPct = 0.00055  // 0.055%
```

并在 `.set` 中给出：

```text
InpTrendMinRVPct: 0.00015 ~ 0.00100
InpStrictMinRVPct: 0.00020 ~ 0.00150
```

### 问题 2：网格默认距离过宽，并且强依赖 points

上一版默认：

```text
InpGridBasePoints = 8000
InpGridMinPoints = 2500
```

不同 Exness 黄金符号的 `_Point` 可能是 0.01 或 0.001，points 距离会产生很大差异。  
如果 `_Point=0.01`，8000 points 就是 80 美元，几乎不开网格。

v2 默认改成 ATR/美元距离模式：

```text
InpGridUseATRPriceDistance = true
InpGridATRMult = 1.00
InpGridMinPriceDistance = 1.50
InpGridMaxPriceDistance = 7.50
```

也就是说，默认网格距离按黄金实际价格距离算，而不是完全依赖点数。

### 问题 3：基线先追价再判断开仓，抹掉了偏离

上一版 OnTick 顺序是：

```text
先 UpdateBaseline()
再 ManageGridEntries()
```

这会导致价格偏离刚出现时，基线先向价格移动，然后开仓条件被削弱。

v2 改为：

```text
先用上一根基线判断出场 / 入场
最后再 UpdateBaseline()
```

这样基线会更像“滞后均值”，更适合网格触发。

---

## 2. v2 的核心变化

```text
1. 修复 RV 阈值量级错误
2. 默认使用 ATR/美元距离网格
3. 网格默认距离显著降低
4. 基线更新顺序改为交易后更新
5. 基线追价速度降低
6. 趋势入场允许 EMA + slope 的软趋势模式
7. 趋势确认默认从 2 根改为 1 根，方便先验证是否开单
8. 趋势入场距离 fast EMA 上限从 1.20 ATR 放宽到 2.80 ATR
9. ADX rising 默认在 set 中不优化，避免过早过滤
```

---

## 3. 当前默认逻辑

### 网格开仓

```text
如果价格偏离上一根基线达到动态网格距离：
    低于基线 → BUY 网格
    高于基线 → SELL 网格
```

默认动态网格距离：

```text
max(1.50 USD, ATR × 1.00)，并限制在 7.50 USD 内
```

### 趋势开仓

宽松趋势满足任意一种：

```text
EMA 同向 + 突破过去 N 根高低点
或
EMA 同向 + 慢 EMA 斜率达到 ATR 的一定比例
```

并且：

```text
ATR / close >= InpTrendMinRVPct
价格不能离 fast EMA 超过 InpTrendEntryMaxDistATR
```

默认更容易先开单，方便验证策略流程。

### 严格趋势 / 保护 / 砍仓

严格趋势仍然更保守，用于：

```text
保护性趋势单
趋势分批砍逆势网格
```

---

## 4. 建议你先这样测试

第一轮只验证是否开单，不要马上优化收益：

```text
InpGridUseATRPriceDistance = true
InpGridATRMult = 1.00
InpGridMinPriceDistance = 1.50
InpGridMaxPriceDistance = 7.50

InpTrendMinRVPct = 0.00035
InpTrendConfirmBars = 1
InpTrendAllowEMASlopeEntry = true
InpTrendEntryMaxDistATR = 2.80
```

如果还不开单，临时进一步放宽：

```text
InpGridMinPriceDistance = 0.80
InpGridATRMult = 0.60
InpTrendMinRVPct = 0.00015
InpTrendSlopeMinATR = 0.02
InpTrendEntryMaxDistATR = 4.50
```

如果这样仍然不开单，优先检查：

```text
1. 品种是否允许 EA 交易
2. 是否选择了真实 tick 数据
3. Expert 日志是否有 trade disabled / invalid volume / market closed
4. InpMaxSpreadPoints 是否过低
5. 黄金符号的最小手数是否大于 0.01
```

---

## 5. 重要提醒

v2 的默认参数是“先确保交易链路能跑起来”的参数，不是最终盈利最优参数。  
等确认能正常开单后，再逐步收紧：

```text
提高 InpGridMinPriceDistance
提高 InpTrendMinRVPct
提高 InpStrictMinRVPct
提高 InpCutADXMin
提高 InpCutMinLossPerLot
```

---

## 6. 和 v1/v2 的区别

| 项目 | fast v1 | fast v2 |
|---|---:|---:|
| 趋势 RV 默认 | 0.020 | 0.00035 |
| 严格 RV 默认 | 0.030 | 0.00055 |
| 网格默认 | points | ATR/USD |
| 默认最小网格 | 2500 points | 1.50 USD |
| 基线顺序 | 先更新再开仓 | 先交易后更新 |
| 趋势确认 | 2 根 | 1 根 |
| 趋势入场距离 | 1.20 ATR | 2.80 ATR |
| 软趋势入场 | 无 | 有 |
