# MR30 实现与静态闸门报告

时间：2026-09-13 12:53（Asia/Shanghai）  
状态：`PASS — implementation_gate_passed; train runs completed; family now closed`

## 结论

独立 EA `dsh_MR30.mq5` 已重新编译，MetaEditor 返回 **0 errors / 0 warnings**。六个固定的 TRAIN/VALID INI 已建立并通过 schema、符号、日期、模型、入金、变体映射和留白护栏检查。随后三个 TRAIN 已按清单运行；因三者均触发预注册停止条件，VALID 没有启动。

## 封存哈希

| 项 | 路径 | SHA-256 |
|---|---|---|
| 源码 | `deepseek数据保存\执行_第三批\stage3_family_preregistration\dsh_MR30.mq5` | `3B1331CCB208D2D57D97C1FD0C327F5F3153310C13B519E6817B6877C7ADC09E` |
| EX5 | `deepseek数据保存\执行_第三批\stage3_family_preregistration\dsh_MR30.ex5` | `D5CCD721B968102A6C4FF2F06A21A81A7178AC53D20BC22567A1D240CE4FE112` |
| 编译日志 | `gpt数据保存\审计\第三批_R4离线更正\compile_MR30.log` | 以文件当前哈希为准 |

## 已通过的静态检查

- 仅允许 `BTCUSDm`、M1 测试器、`Model=2`、500 USD、USD、`InpLatencyTicks=0`。
- 仅允许六个预注册 tag：`V1/V2/V3 × TRAIN/VALID`；tag 与 TP/regime 组合在 `OnInit()` 中硬锁。
- TRAIN 固定 `2018.02.09–2024.05.31`；VALID 固定 `2024.06.01–2025.05.31`。
- `2025.06.01–2026.05.31`（exposed OOS）与 `2026.06.01–2026.09.30`（用户留白）未出现在任何 planned INI。
- 风险固定 1.5%，最小手超配关闭，手数向下取整；非预注册输入会被拒绝。
- M30 由已完成 M1 桶聚合；当前未完成桶被丢弃；V3 的 ATR 分位分布只取信号 bar 之前的 500 根。
- 未发现 `Sleep`、`InpLatencyMs`、网格、马丁、移动止盈/跟踪止损或 `PositionModify`。
- 审计列 24 个且唯一，含 `deal_ticket`、`position_id`、开平时间/价、volume、profit/swap/commission/net、close_type、exit_reason、OCP 和独立公式字段。
- ticket 仅在 `FileWrite` 成功后登记；position identifier 与 position ticket 分开处理。
- `FileWrite` 返回值、OCP、合约公式和成本分解均有失败标记路径。
- portable tester 若拒绝 `FILE_COMMON`，EA 会明确记录错误并回退到 worker 沙盒的 `MQL5\Files\dshtrend\<tag>`；两种路径都由运行器收集，不能静默无审计运行。

## 六个 planned 配置

详细记录在 `mr30_planned_manifest.jsonl`。每个记录均为 `status=planned`、`run_verification=pending`、`strategy_stage=exploratory`；运行后只能追加结果字段，不能增删预注册变体或改输入。

| tag | dataset_role | TP | V3 regime | INI SHA-256 |
|---|---|---:|---|---|
| `DS260913_MR30_V1_TRAIN` | train | 1.5 ATR | off | `FEC7AD7C42734FFBF42A6B75B8B19E0ED0425271706C7ECC67C10C8D8863E9EA` |
| `DS260913_MR30_V1_VALID` | valid | 1.5 ATR | off | `58EA77F1DC7460B6F381BA95338FA771D5C7AFCDE2374249D907FA9362147D94` |
| `DS260913_MR30_V2_TRAIN` | train | 2.5 ATR | off | `A9665364A82797C3DC4754B08EEAE47CB0B35AB767984A3B416AA3905255802B` |
| `DS260913_MR30_V2_VALID` | valid | 2.5 ATR | off | `00B2BF26CBA137F4BA890F14FB56E47D90839F623043A51B403FD84787EB8EBA` |
| `DS260913_MR30_V3_TRAIN` | train | 1.5 ATR | on | `09113A0FC9B7BD8E3358BF28BFE14E0E0BA65E1D02C772E99B66BC1884E532A1` |
| `DS260913_MR30_V3_VALID` | valid | 1.5 ATR | on | `914C9162B65ED36FC02F1DDFF6FDFE887CF17D53744C2D5C2847038D9CE05C77` |

## 下一步闸门

1. 三个 TRAIN 已在隔离 MT5 worker 中串行完成，HTML、`trades.csv`、`signals.csv`、`audit_selfcheck.csv` 和日志均已归档。
2. 每个 TRAIN 均通过 HTML opening/closing deal 数、审计行、报告净利、OCP、独立合约公式、成本、DD、尾单集中度和最小手检查。
3. 三个 TRAIN 均触发停止条件，故三个 VALID 按预注册协议记为 `not_run_skipped`，不把未运行误写成缺失。
4. 不运行 exposed OOS 或用户留白；若要继续，必须另行预注册新 family。
