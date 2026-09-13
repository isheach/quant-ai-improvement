# Stage 0 · Provenance 闸门结论

生成时间：2026-09-12 22:26:54（Asia/Shanghai）

## 总览

| 项 | 值 |
|---|---|
| 清点结果数 | **519** |
| status = verified | 370 |
| status = lead_only | 149 |
| status = blocked | 0 |

## 问题分类（按出现次数）

| 标记 | 次数 | 含义 |
|---|---:|---|
| ENTRY_PARTIAL_ZERO | 204 | 审计 entry 部分为 0（券商侧止损平仓取不到开仓价） |
| TRADE_COUNT_MISMATCH | 202 | 笔数与审计不一致 |
| NO_AUDIT_FILE | 106 | 无审计 CSV（优化模式的网格普遍如此） |
| RUN_ERROR | 68 | 该 run 本身失败 |
| ENTRY_ALL_ZERO | 43 | 审计 entry 全为 0 → 无法还原入场价 |
| NO_INI | 24 | 找不到该 run 的 ini（无法证明实际喂给 MT5 的输入） |

## 逐项硬检查

- **留白段（2026-06-01~09-30）被触碰的结果数：0** ✅ 未触碰
- **非真实品种的结果数：0** ✅ 无
- **报告未来日期：0 处** ✅ 无
- **入金口径分布**：{'300': 460, '': 24, '600': 15, '1000': 12, '3000': 5, '1500': 2}
  → ★GPT 框架要求主口径为 **500 USD**；上表中凡不是 500 的结果，按 §9 只能标 `lead_only` 或 `exploratory`，**不得作为交付候选**。

## 产物

- `provenance_inventory.csv`（519 行）
- `hashes.sha256`（993 条）
- 本文件
