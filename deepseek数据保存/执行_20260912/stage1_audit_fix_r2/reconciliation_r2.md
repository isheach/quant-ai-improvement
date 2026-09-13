# Stage B (P1-R2) · 四方对账与可追溯性

配置：`BTCUSDm` / **500 USD** / valid(2024-06-01~2025-05-31) / `Model=2` / `ticks=0` / 
`InpAllowMinLotOvershoot=false` / run_tag `SB_R2_500`

## 1. 逐笔成本分解（GPT §4-B4）

| 项 | 值 |
|---|---|
| 审计行数 | **52** |
| `profit + swap + commission == pnl` 成立 | **52 / 52** |
| 不成立 | 0 |

- Σprofit = **192.93**
- Σswap   = **-5.45**
- Σcommission = **0.00**
- **Σpnl = 187.48**（应为三者之和）

## 2. 合约公式对账（第三方）

| 项 | 值 |
|---|---|
| 可比对笔数 | 52 |
| `pnl / 公式` 中位 | **0.9999** |
| 区间 | 0.9204 ~ 1.0499 |
| 落在 ±2% 内 | **45 / 52** |

**★说明**：`pnl` 已含 swap/commission，而公式只算价差 → 比值会略偏离 1，
偏离量应等于 `(swap+commission)/公式`。下表验证这一点：

- `|pnl − 公式 − (swap+commission)|` 最大 = **0.0093**，中位 = **0.0033**
  → ✅ 若接近 0，说明三方（审计 / 公式 / 成本分解）**完全自洽**

## 3. 可追溯性（GPT §4-B3）

| 字段 | 非空率 | 判定 |
|---|---|---|
| `entry` | 52/52 | ✅ |
| `exit` | 52/52 | ✅ |
| `vol` | 52/52 | ✅ |
| `position_id` | 52/52 | ✅ |
| `close_type` | 52/52 | ✅ |
| `exit_reason` | 52/52 | ✅ |

- `position_id` 唯一数 = **52**（应 == 行数，除非有部分平仓）
- `close_type` 分布 = `{'full': 52}`
- `exit_reason` 分布 = `{'sl': 49, 'time_exit': 3}`
- **`expert` 退化行数 = 0**（GPT 判据：大量 expert 直接失败）

## 4. MT5 报告汇总对账

| 来源 | 值 |
|---|---|
| 审计 Σpnl | **187.48** |
| MT5 报告 net profit | **187.48** |
| 差 | 0.00 |
| 容差 `max(0.02, 0.1%×|net|)` | 0.1875 |
| **判定** | **✅ 通过** |

报告路径：`C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\rep_SB_R2_500.htm`

## 5. signals.csv（逐笔拒单）

| 项 | 值 |
|---|---|
| 拒单行数 | **121** |
| 拒单原因分布 | `{'no_overshoot': 117, 'cap_exceeded_normal': 4}` |
| 含 `allow_overshoot` 列 | ✅ |

前 3 行：

| time | reason | raw_lot | final_lot | final_risk | risk% | cap% |
|---|---|---:|---:|---:|---:|---:|
| 2024.06.28 20:00:00 | no_overshoot | 0.0072 | 0.01 | 6.20 | 1.246 | 2.500 |
| 2024.07.04 02:00:00 | no_overshoot | 0.0050 | 0.01 | 8.82 | 1.815 | 2.500 |
| 2024.07.04 09:00:00 | no_overshoot | 0.0043 | 0.01 | 10.15 | 2.089 | 2.500 |

## 6. 结论

**四方对账**：
```
① EA 审计逐笔      ✅ 行数 52，字段齐全
② 合约公式重算      ✅ 中位比值 0.9999
③ 成本分解          ✅（profit+swap+commission==pnl：52/52）
④ MT5 报告汇总      ✅ 在容差内
```

