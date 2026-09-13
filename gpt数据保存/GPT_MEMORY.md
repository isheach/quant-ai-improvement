# GPT 唤醒记忆（2026-09-11）

> 交接规则：如果不知道当前进度，先读本文件，再读 `审计\旧代码与DeepSeek输出复核_2026-09-11.md` 和 `大纲\后续改进大纲.md`。本文件只记录 GPT 已核验的状态，不替代原始报告。

## 1. 用户目标与硬约束

- 研究 Exness/MT5 上的黄金、比特币、美元兑日元量化策略，本金约 500 美元。
- 旧策略目录 `D:\desktop\新量化策略\旧量化策略` 只读；不覆盖、不删除其中材料。
- 以后回测只允许使用 MT5 真实券商品种：`XAUUSDm`、`BTCUSDm`、`USDJPYm`；禁止自建品种、CSV 灌入品种、用图表 `CopyRates` 凑历史。
- 公共目录只放精简交接信息；详细中间产物放本目录。
- 2026-06～2026-09 是用户保留的独立留白，研究不得消耗。
- 研究阶段默认按更保守的最大回撤 20% 评估；历史文档另有 30～40% 口径，尚未统一，不能混用。

## 2. 已读旧代码后的可靠理解

最新旧版位于：
`旧量化策略\36代数据\eva028_STAGE1_PACKAGE_v2\eva028_VolumetricPulseGrid_CoreRiskV1.mq5`

核心是“均值回归网格 + 独立趋势单”的混合 EA：固定/递增网格仓位、M5 趋势状态机、Vol-Gate、篮子止损、日损、高水位回撤锁和审计文件。历史代际从 eva000～eva028 及 gpt001～003 分支演化，参数、数据口径和实验阶段并不天然同质。

旧代码的关键风险：网格/加仓的尾部损失与 0.01 手最小手限制冲突；趋势与网格的盈亏经常没有被严格隔离；不同版本的输入默认值和报告口径不一致。

## 3. 已独立复核的 DeepSeek 结果

原始证据目录：`deepseek数据保存\run\...`、`deepseek数据保存\analysis\out\trend_results.jsonl`。

- `b1_baseline`：审计 CSV 484 笔，净利 `272.60`。
- `b1a_pure_grid`：0 笔；`b1b_pure_trend`：484 笔且净利 `272.60`，证明该组实际只跑出趋势侧。
- `base_locked`：102 笔、`+76.56`；`base_locked_valid`：103 笔、`+242.89`。
- `v_baseline`：45 笔、`-44.12`。
- 网格隔离：`g_pg_z1000` 308 笔、`-72.55`；`g_pg_z7000` 46 笔、`-1.00`；`g_pg_z10000` 7 笔、`+43.28`，样本极少。

这些数字与审计 CSV 的 `profit` 合计一致，但多数属于旧的 `XAUUSD_HIST`/Model=2 实验，不能转述为当前真实品种的上线证明。

补充证据：stage1 `.set` 实际使用 `InpGridZ=20000`、`InpMinGridZ=11500`，并非源码默认 7000/2000；两项仍可优化。`b1_baseline` 的退出构成只有 433 次趋势状态退出和 51 次 SL，没有任何网格成交。

## 4. 当前代码审计结论

`deepseek数据保存\mql5\dshtools\dsh_TrendCore.mq5` 当前 SHA-256：
`4BAA127C395D058910A29E1AB31C50C2976FA7748D3D74E961B46F0507349E51`

- 编译成功不等于策略正确；当前代码仍把关键研究参数定义为 `input`，并未真正锁定。
- `AlignLot()` 用 `MathFloor(lot / step + 0.5)` 四舍五入，可能向上取整并超过风险预算；必须改为向下取整后重新计算风险。
- `ClosePosition(reason)` 将原因写入请求 comment，但 `RecordExitDeal` 读取成交历史时未证明能稳定还原内部原因；`exit_reason` 不能默认视为精确可靠。
- 源码启动日志仍写“止损=…ATR(M5)”，而实验参数常用 M30；代码、文档和实验周期需要统一。
- `run_trend\runexp.py` 默认 `DEPOSIT="300"`，而历史记录混有 500/1000/其他入金；默认值不能代表全部结果。
- 编排器固定写 `Model=2`，且源码注释明确面向自定义品种；这与用户最新“只用真实 MT5 品种”指令冲突，必须重建实验协议。
- 报告的 `98% History Quality` 不代表整段都是真实 tick；现有证据显示真实 `.tkc` 仅覆盖近月，较早部分由 MT5 合成。

## 5. 未解决问题

1. 用真实 `XAUUSDm/BTCUSDm/USDJPYm` 直接由测试器取服务器历史，重新做同口径三段实验。
2. 通过 `OrderCalcProfit`、合约规格和独立公式四方对账 USDJPY；暂不把“143 倍错误”写成永久事实或直接排除该品种。
3. 处理组合账户风险：三个 EA 不能各自读取总权益却只管理自己的仓位。
4. 保持 2026-06～09 留白，任何试验都写清起止日期和数据来源。

## 6. 下一步入口

按 `大纲\后续改进大纲.md` 的 P0→P4 顺序执行。任何新结果都必须有唯一 run_id、源码/EX5 哈希、真实 symbol、入金、模型、时间段、输入参数和报告哈希；没有这些字段的数字只作线索，不作结论。

## 7. 本轮 MT5 实际运行与新时间口径

- 真实服务器探针：`XAUUSDm`，2023-01-05～2023-02-05，30,071 M1 / 120,280 ticks / History Quality 100%。
- 真实策略烟雾：`XAUUSDm`，2023-01-05～2023-04-01，净利 +42.16、7 笔、PF 3.30、权益 DD 4.81%；只作链路验证。
- `eva008_TickDataExporterEA` 分析导出：`XAUUSDm`，2026-09-08～09-10，11,024 ticks、3,495 bars；没有回灌回测。
- 用户新口径：2026-06～09 留白；测试 2025-06～2026-05；验证 2024-06～2025-05；训练至 2024-05-31。
- 第一候选：`BTCUSDm` 单仓 M30 趋势突破，目标观察年化 50%～100%，不预设结果。
- 详细记录：`公共部分\AI交流版.md`、`gpt数据保存\会话快照_2026-09-11.md`、`gpt数据保存\mt5_runs\run_manifest.jsonl`。

## 8. 2026-09-12 DeepSeek 结果复核（GPT）

- 公共部分已出现新的 DeepSeek 总结与详细报告；本轮复核文件为：`gpt数据保存\审计\DeepSeek结果复核与下一阶段框架_20260912.md`。
- 当前判断仍是“无可交付策略”。DeepSeek 的黄金 585 次、BTC 约 1,400+ 次、JPY/滚动线的大量结果，主要价值是识别最小手地板、静默拒单、延迟口径、审计缺口和滚动选参不稳健；不能直接替代 500 USD 主口径的正式候选。
- BTC 原始 outbox 中 `btc-282…287` 有 `status=done`，但 300 USD 的正收益依赖地板；1000 USD 的验证段 `btc-282` 为负。`报告_032.md` 内部时间写成 2026-09-14，晚于本记忆时间，需先做 provenance 对齐。
- `dsh_BtcSwing.mq5` 当前审计出场行仍写 `entry=0.0` 并使用全局风险/ATR状态，必须按 position/deal 反查后才能做逐笔 R、点差和持仓时长分析。
- `Model=2` 下约 1 个合成 tick/M1；`InpLatencyMs=300` 的 `Sleep` 不代表真实 300ms，`InpLatencyTicks=1` 应标作约 60 秒/次根压力，不得写成 300ms 已模拟。
- `run_manifest.jsonl` 仍未覆盖 DeepSeek 新结果；所有未有完整 provenance 的数字只标 `lead_only`。2026-06～09 留白继续禁止使用。
- 恢复工作的优先级：证据闸门 → 执行/审计修复 → USDJPY P&L 四方对账 → 500 USD 固定协议 → 少量预注册结构实验；暂停无止境参数扫描。

## 9. 2026-09-12 下一步执行协议已发布

- 面向 DeepSeek 的可执行协议：`公共部分\GPT下一步执行框架_20260912.md`。
- 协议顺序固定为 P0 provenance → P1 手数/成交审计修复 → P2 USDJPY 四方 P&L 对账 → P3 固定 500 USD 主口径 → P4 最多三个预注册结构变体 → P5 冻结测试/留白后前向。
- 公共留言已追加 `MSG-20260912-010`；DeepSeek 恢复时必须先读取留言板和协议，先做 P0，不得直接启动无边界参数扫描。
- 详细中间产物统一放 `deepseek数据保存\执行_20260912\`；旧量化策略只读；2026-06～09 留白继续禁止使用。

## 10. 2026-09-13 阅读提示词复核与新执行入口

- 复核文件：`gpt数据保存\审计\给GPT提示词复核与下一步流程_20260913.md`。
- 公共留言：`公共部分\AI交流版.md` 的 `MSG-20260913-013`。
- 重要更正：P0 的 519 是唯一请求/网格 ID，不是全部结果；outbox 约 3780 条记录。首次去重、error→done lineage、网格 pass、空字段和未来日期扫描均需重做。`RUN_ERROR` 不得标 verified；`TRADE_COUNT_MISMATCH` 只能先标 `audit_reconcile_required`。
- P2 当前不通过：`XX_jyrg-c0-base` 审计/公式约 203.18/203.16，但 MT5 报告净利 77.64；现有脚本没有完成严格四方（尤其没有 `OrderCalcProfit`）对账。
- P1 报告哈希已过时：当前 `dsh_BtcSwing.mq5` SHA256 为 `51F8626BB491AAF800D5C78B0B057ACB9E31D7CE7A91257DE3C1E64CDAA6C43A`，需重新编译封存后再认可 C1。
- 下一步顺序固定为：P0 v2 → P1-R2 → P2-R2 → C1 train/valid 预测试闸门；在前三阶段完成前不跑新参数、不跑测试集；C2/C3 当前家族关闭。

## 11. 2026-09-13 第二批裁定与最新执行入口

- 详细审计：`审计\第二批提示词裁定与新执行流程_20260913.md`。
- 公共执行文件：`公共部分\GPT新执行流程_第二批裁定_20260913.md`；留言为 `MSG-20260913-016`。
- P1-R2 的 `SB_R2_500` 只证明 BTC valid 单次运行的审计链通过：500 USD、52 笔、净利 187.48、PF 1.62、DD 18.60%、`overshoot=false`。这是约 37.50% 的单段收益，不是策略交付结论。
- C1 新封存证据只有 valid；旧 `P4C1_train` 使用 `overshoot=true`，不得拼接。必须用 P1-R2 封存源码/EX5和完全相同输入重跑 train/valid。
- USDJPY 仍为 `blocked_mapping`：3 个旧 JPY run 只有 1 个汇总与报告一致；新起 3 场景×2 重复的 6 次唯一 run 对账，通过前不做 JPY 策略排名。
- 原测试段 2025-06-01～2026-05-31 已暴露：当前 656 份 INI 中至少 113 份与其重叠且有同名报告，后续标签为 `exposed_oos`，不能再称完全独立测试。
- 2026-06～09 继续对 AI 硬禁止，但全项目并非完全未见：自建黄金数据实际到 2026-06-30，早期 `eva008` 已导出真实黄金 2026-09-08～10。用户日期定义不擅自改动，旧文件只登记不删除；真正独立证据改由冻结后的未来 demo 前向提供。
- 新顺序：R0 强制登记/品种白名单/日期护栏 → R1 JPY-R3 → R2 BTC C1-R3 train/valid → R3 十项零调参诊断 → R4 冻结 → R5 原测试段一次 `exposed_oos` → R6 用户测试与未来 demo。
- 以后拆分状态：`run_verification=execution_verified/...` 与 `strategy_stage=deliverable_candidate/acceptable_candidate/exploratory/blocked_failed`。DD≤20% 为首选；20%～40% 仅为高风险可接受候选；>40% 失败。年收益 50% 是目标、100% 是延伸目标，不能靠加风险硬凑。

## 12. 2026-09-13 第三批 R0–R3 审阅裁定

- 审阅文件：`公共部分\给GPT的提示词_第三批_R0R3审阅_20260913.md`；详细裁定：`gpt数据保存\审计\第三批提示词裁定与R4执行流程_20260913.md`；给 DeepSeek 的执行单：`公共部分\GPT下一步执行流程_第三批裁定_20260913.md`。
- 独立复核更正了 R1：`DS260913_JPYR3_SHORT_A/B` 的 HTML `Total Trades=399`、审计 398 行；`DS260913_JPYR3_PARTIAL_A/B` 的 HTML `Total Trades=791`、审计 790 行。四个报告各有最后 `end of test` 平仓 `-0.70 USD` 未落入审计；原“6/6 closing deal 一致”不成立。JPY 保持 `blocked_mapping`，不放宽汇总容差。
- 独立从 BTC C1 HTML 读到官方权益 DD：train `Equity Drawdown Maximal=451.98 (22.17%)`、`Equity Drawdown Relative=39.95%`；valid `118.13 (18.60%)`、`18.60%`。`r3_diagnostics.py` 的空值通过逻辑必须修复为 `not_evaluated`；不为已关闭 C1 重跑。
- C1 仍为 `blocked_failed`：去前十单后 train/valid 净利 `-354.74/-247.67`，收益依赖尾单；R4/R5/R6 不执行。C2/C3 正式关闭。
- 裁定允许一个结构不同的新 family，但只能预注册、最多三个固定变体、500 USD、真实 `BTCUSDm`/MT5 历史、只跑 train/valid；未完成 Step 0–3 前不启动新参数扫描或测试段。
- 新执行顺序：快照/暴露登记 → 离线 R1/R3 更正 → 新 EA 修复并做 JPY 六次控制 → 封存 C1/C2/C3 状态 → 新 family 预注册 → train/valid → 通过后才考虑 `exposed_oos` 和用户 demo。2026-06-01～09-30 留白继续由用户保留，AI 不读取、不回测、不调参。

## 13. 2026-09-13 MR30 family 收尾（当前最新状态）

- MR30 预注册、源码/EX5 编译、输入与无未来泄漏静态闸门均已通过；封存源码 SHA-256 `3B1331CCB208D2D57D97C1FD0C327F5F3153310C13B519E6817B6877C7ADC09E`，EX5 SHA-256 `D5CCD721B968102A6C4FF2F06A21A81A7178AC53D20BC22567A1D240CE4FE112`。
- 三个有效 TRAIN 均为真实 `BTCUSDm`、500 USD、Model=2、M1 驱动/M30 信号、2018-02-09～2024-05-31：
  - V1（TP 1.5×ATR）：净利 `-392.47`、PF `0.83`、官方 Equity DD Relative `78.86%`、1714 笔；
  - V2（TP 2.5×ATR）：净利 `-394.71`、PF `0.83`、官方 Equity DD Relative `79.80%`、1640 笔；
  - V3（TP 1.5×ATR + ATR P20–P80）：净利 `-319.21`、PF `0.87`、官方 Equity DD Relative `65.72%`、1264 笔。
- 三个有效运行的 MT5 HTML、审计 CSV、OrderCalcProfit、独立合约公式、成本分解和 ticket/selfcheck 均一致；`run_verification=execution_verified`，但 `strategy_stage=blocked_failed/closed`。三者均触发净利≤0、PF≤1、DD>40% 停止条件；`V1/V2/V3_VALID` 是明确的 `not_run_skipped`，不是缺失结果。
- V1 的前两次尝试是工程性 `invalid`（`FILE_COMMON` 不可用、误读 `FileWrite()` 返回值），不与有效结果合并；详细证据在 `gpt数据保存\\审计\\第三批_MR30\\`。
- MR30 不重开、不继续扫描 TP/SL/周期、不运行 exposed OOS（2025-06-01～2026-05-31），也不读取/回测用户留白 2026-06-01～2026-09-30。年化 50%/100% 仍只是目标，不能用提高风险掩盖失败。
- 当前入口：先阅读 `公共部分\\AI交流版.md`、本节和 `gpt数据保存\\大纲\\MR30收尾与下一阶段唤醒_20260913.md`；若继续研究，只允许一个结构不同的新 family，最多三个预注册变体，先过 provenance/编译/静态闸门再按 train→valid 串行运行。
