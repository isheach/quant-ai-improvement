# 环境变更登记（GPT 第三批裁定 Step 0 第 3 条）

- 记录者：DeepSeek-执行者
- 时间：2026-09-13（Asia/Shanghai）
- **本阶段原则：只登记，不再做任何新的删除**

## 1. 已移出活动终端的残留（上一轮操作，本阶段仅登记）

| 项 | 原位置 | 现状 | 备份位置 |
|---|---|---|---|
| `symbols.custom.dat`（4 KB） | `<Terminal>\bases\symbols.custom.dat` | **已移出活动环境** | `执行_20260912\_backup_custom_symbols\symbols.custom.dat` |
| `selected-277335900.dat`（11.9 KB） | `<Terminal>\bases\Exness-MT5Trial5\symbols\` | 已备份 | `...\_backup_custom_symbols\selected-277335900.dat` |
| `JPYUSD_HIST`（历史目录） | `<Terminal>\bases\Custom\history\JPYUSD_HIST\` | **已移出** | `...\_backup_custom_symbols\JPYUSD_HIST_history\2026.hcc` |
| Tester cache（453 MB） | `<Terminal>\Tester\cache\` | **已移出** | `...\_backup_tester_cache\cache\` |

## 2. 该残留的故障机制（已实测确认）

```
自建品种 JPYUSD_HIST 曾由 eva028 线创建（dsh_TrendCore 使用过）
→ 用户删除自建品种数据后，MT5 的 symbols.custom.dat 仍保留其定义
→ 测试器每次启动都尝试同步该品种
→ "no data synchronized, 37 bytes read"
→ "symbol JPYUSD_HIST history synchronization error"
→ "no prices for symbol JPYUSD_HIST (1970.01.01 ...)"
→ ★ 测试器【整体中止】→ 报告 Bars=0 / Ticks=0 / Initial Deposit=0.00
→ 而测试器日志显示 EA 已成功下单（易被误判为"策略无成交"）
```

**处置前对照**：同一配置审计 **0 行** → 处置后 **1900 行**

## 3. 仍留在磁盘但未使用的内容（按裁定不删除）

| 项 | 位置 | 大小 | 说明 |
|---|---|---|---|
| `XAUUSD_HIST_M1.csv` | `<Terminal>\MQL5\Files\dshtools\` | 76.8 MB | eva028 线自建品种数据；按裁定 Q4「不删证据」保留 |

## 4. 本阶段承诺

```
✗ 本阶段不做任何新的删除
✗ 不使用 XAUUSD_HIST / BTCUSD_HIST / JPYUSD_HIST 或任何 CSV 回灌
✅ 所有 run 必须先写 planned manifest 才可启动 MT5
✅ 报告名与 run_id 唯一（r0_guard 强制）
```
