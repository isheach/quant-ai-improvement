## 深度分析

### A. 入金口径 vs GPT 主口径（500 USD）

| 入金 | 结果数 | 占比 | 对 GPT 框架的含义 |
|---|---:|---:|---|
| 300 | 460 | 88.6% | ⚠️ 非主口径 → 只能 `lead_only`/`exploratory` |
| (空) | 24 | 4.6% | ⚠️ 未记录 → 只能 `lead_only` |
| 600 | 15 | 2.9% | ⚠️ 非主口径 → 只能 `lead_only`/`exploratory` |
| 1000 | 12 | 2.3% | ⚠️ 非主口径 → 只能 `lead_only`/`exploratory` |
| 3000 | 5 | 1.0% | ⚠️ 非主口径 → 只能 `lead_only`/`exploratory` |
| 1500 | 2 | 0.4% | ⚠️ 非主口径 → 只能 `lead_only`/`exploratory` |
| 50000 | 1 | 0.2% | ⚠️ 非主口径 → 只能 `lead_only`/`exploratory` |

**★结论：符合 GPT 主口径（500 USD）的结果数 = 0。**
→ 按框架 §9，**现有全部结果都不能直接作为 `deliverable_candidate`**；它们最多是 `lead_only`。这不是「结果错了」，而是**口径不是主线**。

### B. `entry=0` 的两种情形（必须分开）

| 情形 | 条数 | 含义 | 严重性 |
|---|---:|---|---|
| `ENTRY_ALL_ZERO` | **43** | 该 run 的审计**每一行** `entry` 都是 0 | ★**致命**：无法还原入场价 |
| `ENTRY_PARTIAL_ZERO` | 204 | 部分行 `entry=0`（券商侧止损平仓只有 exit deal） | 中：`pnl`/`risk_money`/`exit` 仍可用 |

`ENTRY_ALL_ZERO` 的品种分布：`{'BTCUSDm': 26, 'XAUUSDm': 16, 'USDJPYm': 1}`

`ENTRY_ALL_ZERO` 的来源线：`{'比特币': 26, '黄金': 16, '日元': 1}`

`ENTRY_ALL_ZERO` 的 run 前缀：`{'BT_btc': 26, 'GD_gold': 16, 'JP_jpy': 1}`

**★注意**：`ENTRY_ALL_ZERO` 集中在早期 run（说明当时审计写入尚未完善），而后期 run 是 `ENTRY_PARTIAL_ZERO`。这不是「EA 一直坏」，而是**审计实现分两个阶段**。

### C. `TRADE_COUNT_MISMATCH` 的性质判定

`mt5_trades / audit_rows` 比值分布：**中位 0.962** · 最小 0.611 · 最大 1.042 · n=202

**★判定：中位比值 0.96 ≈ 1.0 → 两套计数【基本一致】**，202 条 mismatch 是**小幅偏差**，不是系统缺失。

差值来源（按可能性排序）：
1. **部分平仓** → 一个持仓产生多行 deal → 审计行数 > MT5 笔数；
2. **`OUT_BY` 拆笔** → 同一次平仓被记成多行；
3. 结尾未平仓头寸 → 审计有开仓行、MT5 不计为完整 trade。

差值分布：`|差值|≤2` 的 61 条 / 202；`|差值|>5` 的 80 条；最大差 230（`BT_btc-117`: mt5=362 / audit=592）。

→ **`TRADE_COUNT_MISMATCH`【不构成】provenance 阻断**（比值≈1，非系统性缺失）。但框架 §2 要求两数一致 —— 建议在 manifest 中**显式注明口径**（`trade_count_mt5` = MT5 报告口径；`trade_count_audit` = 审计 deal 行数）。

### D. 延迟口径分布

| `InpLatencyMs` / `InpLatencyTicks` | 条数 | 含义 |
|---|---:|---|
| `/` | 290 | 两键都未写入 ini → **未能证明任何延迟口径**（早期 run） |
| `0/1` | 152 | 0 ms + 1 tick → **约『次根 K 线压力』口径**（当前主口径） |
| `300/` | 46 | 300 ms + 无 tick → `Sleep` 空操作 → **实为 0 延迟**（除非该 EA 已移植 tick 延迟） |
| `300/1` | 18 | 300 ms + 1 tick → tick 有效，Ms 无效 |
| `300/0` | 11 | 300 ms + 0 tick → **实为 0 延迟** |
| `0/0` | 1 | 0 ms + 0 tick → 纯 0 延迟基线 |
| `0/5` | 1 |  |

**★按 GPT 框架 §1**：`InpLatencyTicks=0` 是基线、`=1` 是『约下一根 K 线压力测试』，**都不得写成 300ms**。上表 `300/` 与 `300/0` 两类必须重新标注。

### E. 模型与品种

- 模型分布：`{'2': 495, '': 24}` → **全部 `Model=2`**（符合框架要求，但须承认它约每根 M1 一个合成 tick）
- 品种分布：`{'BTCUSDm': 296, 'XAUUSDm': 102, 'USDJPYm': 97, '': 24}` → **全部为真实券商品种** ✅
- 留白段触碰：**0 条** ✅

