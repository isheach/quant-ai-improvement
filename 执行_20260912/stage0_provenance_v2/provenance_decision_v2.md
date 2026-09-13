# Stage 0 **v2** · Provenance 证据重建结论

依据：GPT 复核意见 §3.1–§3.5 / 阶段 A。**本文件取代 v1 的结论。**

## 1. v1 的六处修正

| # | v1 的问题 | v2 的处理 |
|---|---|---|
| ① | 按 `req_id` 首次去重 → 519 是「唯一 ID 数」 | 改用**复合键** `req_id\|tag\|config_hash`；保留 lineage |
| ② | `RUN_ERROR` 未纳入 `lead_only` | **error 一律 `lead_only`**；区分 `RUN_ERROR` / `RUN_ERROR_RETRIED` |
| ③ | 空字段被当作「无违规」 | 空 symbol/deposit/model/date → **`provenance_unknown`** |
| ④ | 留白只查端点 | 改为**区间重叠** `from<=09-30 AND to>=06-01`；并扫描全部文本 |
| ⑤ | 笔数差未分离口径 | 分离 `trade_count_mt5` / `audit_rows`；差异或无 `position_id` → **`audit_reconcile_required`** |
| ⑥ | manifest 未更新 | 新记录只追加（见 §5） |

## 2. 总览

| 项 | 值 |
|---|---|
| **run/pass 记录数（复合键）** | **3811** |
| status = `verified` | 0 |
| status = `lead_only` | 498 |
| status = `provenance_unknown` | 3313 |
| status = `blocked` | 0 |
| 有重试/重复出现的键 | 45 |

## 3. 标记分布

| 标记 | 次数 |
|---|---:|
| `AUDIT_RECONCILE_REQUIRED` | 3811 |
| `NO_AUDIT_FILE` | 3348 |
| `NOT_DONE` | 3342 |
| `NO_INI` | 3313 |
| `NO_REPORT` | 3313 |
| `TRADE_COUNT_MISMATCH` | 230 |
| `RUN_ERROR` | 67 |
| `RUN_ERROR_RETRIED` | 1 |

| 未知字段 | 次数 |
|---|---:|
| `deposit` | 3313 |
| `model` | 3313 |
| `symbol` | 38 |
| `dates` | 38 |
| `holdout_undecidable` | 38 |

## 4. ★硬检查（v2 措辞已收紧）

- **确认触碰留白的 run：0** （无）
- **留白不可判定的 run：38**（缺日期）→ **不能声称「全部未触碰」**
- **非真实品种：0** （无）
- 入金口径：`{'(空)': 3313, '300': 462, '600': 15, '1000': 13, '3000': 5, '1500': 2}`
- 模型口径：`{'(空)': 3313, '2': 498}`

**★结论**：v1 的「三项硬检查全部通过」表述**不成立** —— 
正确表述是「在可判定的 run 中，无一条确认触碰留白；但有 38 条因缺日期不可判定」。

## 5. 文本扫描：未来日期

| 文件 | 日期 | 上下文 |
|---|---|---|
| `交接\inbox_比特币.jsonl` | 2026-09-14 | ≥50，则它是全新的可行区","priority":"high"} {"req_id":"btc-268","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 47.01% 压进 40%","priority":"high"} {"req_id":"btc-269","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 器，而不再兼任'拒单闸门'","priority":"high"} {"req_id":"btc-270","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 益改进，则本金就是本线的解","priority":"high"} {"req_id":"btc-271","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 是空集结论被打破的直接可能","priority":"high"} {"req_id":"btc-272","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 频率跌破的临界本金在哪一档","priority":"high"} {"req_id":"btc-273","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 金/收紧锁)的首次组合","priority":"normal"} {"req_id":"btc-274","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 一直接检验该棘轮假设的条目","priority":"high"} {"req_id":"btc-275","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 金1000'成为三段解候选","priority":"high"} {"req_id":"btc-276","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 1000'在三段上都有希望","priority":"high"} {"req_id":"btc-277","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | '这条组合在三段上的可行性","priority":"high"} {"req_id":"btc-278","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | edge存在性'的直接检验","priority":"high"} {"req_id":"btc-279","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 更强的cap约束】才能盈利","priority":"high"} {"req_id":"btc-280","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 到valid的可行cap区","priority":"high"} {"req_id":"btc-281","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 应、valid段无edge","priority":"high"} {"req_id":"btc-282","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 同参,仅入金改为1000)","priority":"high"} {"req_id":"btc-283","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | '模式下至少test段成立","priority":"high"} {"req_id":"btc-284","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 态在比例配仓下是否仍成立'","priority":"high"} {"req_id":"btc-285","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 1手）而非任何cap筛选'","priority":"high"} {"req_id":"btc-286","ts":"2026-09-14… |
| `交接\inbox_比特币.jsonl` | 2026-09-14 | 无edge的段'的关键对照","priority":"high"} {"req_id":"btc-287","ts":"2026-09-14… |
| `交接\MT5运行请求协议.md` | 2026.09.30 | 5.31** | 最终检验（含 2026-01 大行情，压测） | | **留白** | **2026.06.01 – 2026.09.30… |
| `交接\日元滚动\报告_001.md` | 2026.09.30 | d` 必含 `InpLatencyMs=300`**（硬约束） ③ 日期**绝不触及留白段** `2026.06.01–2026.09.30… |
| `交接\比特币\报告_001.md` | 2026.09.30 | *（本批 27 条全部 `phase:"train"`；未使用验证/测试/留白） | | 留白段 2026.06.01–2026.09.30… |
| `交接\比特币\报告_002.md` | 2026.09.30 |  2024.05.31**；批量2 全部 22 条 `phase:"train"` | | 留白 2026.06.01–2026.09.30… |
| `交接\比特币\报告_029.md` | 2026-09-14 | 景** ＋ 改用**本金**作为杠杆（批 7 条）  - 报告编号：报告_029 - 作者：比特币线研究代理 - 时间：2026-09-14… |

**★注意**：GPT 复核指出 `交接\比特币\报告_032.md` 写有 `2026-09-14`，
而当前为 **2026-09-13** → 该报告至少 `lead_only`。上表为该扫描的实际结果。

## 6. 产物

- `provenance_inventory_v2.csv`（3811 行）
- `hashes_v2.sha256`（950 条）
- `future_dates.csv`（34 条）
- 本文件
