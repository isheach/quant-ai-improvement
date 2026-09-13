# Stage 0 v2 · 深析：为什么 `verified` = 0

## 1. 按 run_id 前缀（区分网格 pass 与单跑）

| 前缀 | 记录数 | 含义 |
|---|---:|---|
| `OPT_` | 3289 | **网格 pass**（优化模式的 pass，无独立 ini/report/审计） |
| `BT_` | 340 | 单跑（BTC） |
| `GD_` | 97 | 单跑（黄金） |
| `JP_` | 46 | 单跑（日元） |
| `XX_` | 39 | 探针/网格原样 tag |

## 2. **单跑**记录的状态（真正可谈 provenance 的部分）

| status | 条数 |
|---|---:|
| `lead_only` | 459 |
| `provenance_unknown` | 24 |

单跑中的标记分布：

| 标记 | 条数 |
|---|---:|
| `AUDIT_RECONCILE_REQUIRED` | 483 |
| `TRADE_COUNT_MISMATCH` | 211 |
| `NO_AUDIT_FILE` | 58 |
| `RUN_ERROR` | 53 |
| `NOT_DONE` | 53 |
| `NO_INI` | 24 |
| `NO_REPORT` | 24 |
| `RUN_ERROR_RETRIED` | 1 |

## 3. ★`NO_INI` 的来源（v1 没暴露这个）

`NO_INI` = **找不到该 run 实际喂给 MT5 的输入文件** → 无法证明参数。
按前缀分解：

| 前缀 | NO_INI 条数 |
|---|---:|
| `OPT_` | 3289 |
| `BT_` | 24 |

## 4. **同时有 ini 的单跑**（最接近 `verified` 的集合）

| 项 | 值 |
|---|---|
| 条数 | **459** |
| status=`lead_only` | 459 |

这些记录的标记分布：

| 标记 | 条数 |
|---|---:|
| `AUDIT_RECONCILE_REQUIRED` | 459 |
| `TRADE_COUNT_MISMATCH` | 211 |
| `NO_AUDIT_FILE` | 34 |
| `RUN_ERROR` | 29 |
| `NOT_DONE` | 29 |
| `RUN_ERROR_RETRIED` | 1 |

**★其中标记只有 `AUDIT_RECONCILE_REQUIRED` 或空（即除审计口径外无其他问题）的：201 条**

| run_id | 品种 | 入金 | 模型 | 审计行 | mt5笔数 | position_id列 |
|---|---|---|---|---:|---:|---|
| `GD_gold-001` | XAUUSDm | 300 | 2 | 17 | 17.0 | 0 |
| `GD_gold-002` | XAUUSDm | 300 | 2 | 22 | 22.0 | 0 |
| `GD_gold-003` | XAUUSDm | 300 | 2 | 23 | 23.0 | 0 |
| `GD_gold-004` | XAUUSDm | 300 | 2 | 17 | 17.0 | 0 |
| `GD_gold-005` | XAUUSDm | 300 | 2 | 1 | 1.0 | 0 |
| `GD_gold-006` | XAUUSDm | 300 | 2 | 3 | 3.0 | 0 |
| `GD_gold-007` | XAUUSDm | 300 | 2 | 14 | 14.0 | 0 |
| `GD_gold-008` | XAUUSDm | 300 | 2 | 2 | 2.0 | 0 |
| `GD_gold-009` | XAUUSDm | 300 | 2 | 27 | 27.0 | 0 |
| `GD_gold-010` | XAUUSDm | 300 | 2 | 12 | 12.0 | 0 |
| `GD_gold-011` | XAUUSDm | 300 | 2 | 54 | 54.0 | 0 |
| `GD_gold-012` | XAUUSDm | 300 | 2 | 40 | 40.0 | 0 |
| `GD_gold-013` | XAUUSDm | 300 | 2 | 23 | 23.0 | 0 |
| `GD_gold-014` | XAUUSDm | 300 | 2 | 23 | 23.0 | 0 |
| `GD_gold-015` | XAUUSDm | 300 | 2 | 21 | 21.0 | 0 |
| `GD_gold-016` | XAUUSDm | 300 | 2 | 72 | 72.0 | 0 |
| `GD_gold-017` | XAUUSDm | 300 | 2 | 24 | 24.0 | 0 |
| `GD_gold-018` | XAUUSDm | 300 | 2 | 83 | 83.0 | 0 |
| `GD_gold-019` | XAUUSDm | 300 | 2 | 690 | 690.0 | 0 |
| `GD_gold-020` | XAUUSDm | 300 | 2 | 6 | 6.0 | 0 |
| `GD_gold-021` | XAUUSDm | 300 | 2 | 212 | 212.0 | 0 |
| `GD_gold-022` | XAUUSDm | 1000 | 2 | 30 | 30.0 | 0 |
| `GD_gold-023` | XAUUSDm | 300 | 2 | 17 | 17.0 | 0 |
| `GD_gold-024` | XAUUSDm | 300 | 2 | 17 | 17.0 | 0 |
| `GD_gold-025` | XAUUSDm | 300 | 2 | 17 | 17.0 | 0 |
| `GD_gold-026` | XAUUSDm | 300 | 2 | 226 | 226.0 | 0 |
| `GD_gold-027` | XAUUSDm | 300 | 2 | 195 | 195.0 | 0 |
| `GD_gold-028` | XAUUSDm | 300 | 2 | 167 | 167.0 | 0 |
| `GD_gold-029` | XAUUSDm | 300 | 2 | 151 | 151.0 | 0 |
| `GD_gold-030` | XAUUSDm | 300 | 2 | 415 | 415.0 | 0 |

## 5. `AUDIT_RECONCILE_REQUIRED` = 3811（占 100%）的真实原因

```
判据 = (笔数不一致) 或 (审计缺 position_id 列)
实测：缺 position_id 列的记录 = 3811 / 3811
→ 因为 position_id 列是【2026-09-12 才加入】的，
  所有历史 run 的审计都没有它 → 全部命中该标记。
→ 这不是「新发现的错误」，而是「用新标准衡量旧数据」的必然结果。
```

## 6. 未来日期扫描（34 条）

| 文件 | 日期 |
|---|---|
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |
| `交接\inbox_比特币.jsonl` | 2026-09-14 |

**★GPT 点名的 `交接\比特币\报告_032.md`：命中未来日期 2026-09-14**

