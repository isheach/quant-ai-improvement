# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG）

> 标的：XAUUSD（黄金），平台：Exness / MT5。
> 本日志记录从“项目共识”到本轮交付的全部工作，并对每一版代码说明**改了什么、为什么改**。
> 命名约定：所有新代码用 `eva001 / eva002 / …` 标注先后顺序。

---

## 0. 一句话总览

```
eva001  导出行情(tick + M1/M5/M15)，按 品种/周期/月 分块成 CSV 仓库
eva002  在原 EA 上叠加“可审计日志”层（交易逻辑零改动，优化时自动关闭）
eva003  Python 流水线：切片 / 交易增强(MFE·MAE·问题单) / 按请求文件出数
eva004  数据请求文件格式：分析方(含 AI)想要更多数据时按此格式生成，交给 eva003
```

数据流：

```
eva001 → 行情仓库(CSV)
                    ┐
eva002 回测 → trade_events.csv / decision_audit.csv / run_config.csv
                    ┘
            ↓ (eva003 enrich：按交易时间从仓库切路径)
        trade_enriched.csv + problem_trades.csv + signal/regime_performance.csv
                    ↓ (分析 → 需要更多数据)
            eva004 请求文件 → (eva003 request) → 指定切片
```

这套结构落实了项目共识里的关键决策：**不解析 MT5 底层私有文件**；**用官方接口导出**；**EA 回测只输出交易事件与信号状态，保持轻量**；**行情与回测事件解耦，后处理用 Python 按交易时间切片**；**支持多机器、多参数复用同一份行情仓库**。

---

## 1. 此前工作回顾（项目共识，来自 `exness_mt5_strategy_project_summary.md`）

- 目标不是继续盲目调参，而是建立**可复用、可流水线化**的策略开发与诊断流程：判断哪些单本不该开、亏损归因（入场/出场/参数/方法）、识别无用过滤器、避免训练集有效测试集失效。
- 核心共识：**不要只看 MT5 浓缩回测报告**，要把每笔单变成“可审计”——能解释 signal、趋势/波动状态、点差、过滤器、开仓后价格路径、MFE/MAE、出场方式、属正常亏损还是逻辑错误。
- 架构决策：行情数据只导一次；EA 回测只输出交易事件+信号状态；后处理按 `entry_time/exit_time` 从仓库切片；分析与回测解耦；多机并行；多参数批量复用。
- 数据仓库按 `品种/周期/月份` 分块；同时保留 tick（算 MFE/MAE/扫损/点差）与 M1/M5（判结构/趋势/ATR/均线）。
- 参数问题 vs 方法问题的判别框架、黄金多年数据分段（旧年份压力测试、近年为主、最近做前向）等，作为后续分析阶段的判据，已纳入 eva003 的聚合产物设计中（signal/regime_performance 便于按档位/状态切片对比）。
- 第一阶段目标：**保持交易逻辑不变，先把 EA 改造成可审计版本**，输出 `trade_events / signal_audit / run_config`。本轮 eva002 即完成这一步。

被分析的现有策略 `VolumetricPulseGrid_StateMachine v1.00`：波动率三档(低/中/高)状态机 + 行情状态机(震荡/趋势) 的**网格/马丁**策略，外加独立趋势单模块；出场由基线回归、分级风险、冷静期、若干硬止损共同决定。当前参数集 `true01_2.set`（RegimeMode=AUTO、固定长周期RV=1000点@参照价4500、Lot 0.01、Magic 123456）。

---

## 2. 本轮交付物清单

| 文件 | 类型 | 作用 |
|---|---|---|
| `eva001_TickDataExporter.mq5` | MT5 脚本(Script) | 导出 tick + M1/M5/M15，按 品种/周期/月 分块 CSV |
| `eva002_VolumetricPulseGrid_StateMachine.mq5` | MT5 EA | 原策略 + 可审计日志层（逻辑不变） |
| `eva003_data_pipeline.py` | Python | 切片 / 交易增强 / 请求处理 / parquet 缓存 |
| `eva004_data_request_template.json` | JSON | 二次取数的请求文件格式（模板+示例） |
| `eva_DEVLOG.md` | 文档 | 本日志 |

---

## 3. 每版代码变更记录（changelog）

### eva001_TickDataExporter.mq5 — v1.00（新建）

**做了什么**
- 新建一个 MT5 脚本：拖到 XAUUSD 图表上运行，弹窗设置 `起止年月 + 要导出的周期`，即把历史导出为 CSV。
- 目录结构：`<OutRoot>/XAUUSD/{ticks,m1,m5,m15}/YYYY-MM.csv`。
- tick 用 `CopyTicksRange(COPY_TICKS_ALL)`，**按天分片**循环（避免一次性请求整月 tick 撑爆内存）。
- K 线用 `CopyRates` 按月取。
- 默认写 `Common\Files`（跨终端/跨机器可取），可切回本地沙箱。
- 支持 `覆盖/跳过`（断点续传、增量补月）、`跳过空月`。

**为什么这么做**
- 满足共识里“只用官方接口导出、不碰底层私有文件、行情只导一次可复用”。
- 按月分块便于后处理只读需要的月份，也利于多机协作。
- **精度无损**：`time_msc` 写**毫秒整数**；价格按品种 `Digits` 全精度（黄金一般 2 位；可用 `InpPricePrecision` 覆盖）。tick 额外带 `spread_pts`，K 线带 `spread/real_volume`。

**字段**
- ticks：`time_msc,time_iso,bid,ask,last,volume,volume_real,flags,spread_pts`
- bars：`time,time_iso,open,high,low,close,tick_volume,spread,real_volume`

> 备注：tick 数为 0 通常是该券商历史中心没有对应真实 tick；可先在“品种→导入/下载历史”后重试。Parquet 不在 MQL5 端直接生成（MQL5 不原生支持），由 eva003 的 `cache` 子命令把 CSV 转 parquet 加速。

---

### eva002_VolumetricPulseGrid_StateMachine.mq5 — 基于 v1.00，build 标记 1.01（“审计层”）

**总原则：交易逻辑与原 v1.00 完全一致，只新增“记录”。** 所有新增动作都被总开关短路；优化模式强制关闭。

**新增 1：输入参数组 `=== eva002 审计日志 ===`**
- `InpEnableTradeAudit`(默认 false)：总开关。
- `InpAuditDecisions`(默认 true)：是否同时输出开仓决策审计。
- `InpRunTag / InpParamSetId / InpStrategyVersion`：运行与参数组标识，写进每行，便于多参数批量回测对账。
- `InpAuditUseCommonFile`(默认 true)：写 Common\Files 还是本地沙箱。

**新增 2：数据结构与全局**
- `EvaPendingCtx`（下单瞬间抓拍的上下文）、`EvaOpenRec`（持仓记录，等平仓落盘）、文件句柄、`G_EvaOpen[]` 持仓表、`G_EvaExitReason`、`G_EvaActive` 等。

**新增 3：审计模块函数（文件末尾 `=== eva002 审计日志模块 ===`）**
- `EvaInit/EvaDeinit`：建目录、开/关 3 个 CSV、写 `run_config`、收尾统计。
- `EvaCaptureGridPending/EvaCaptureTrendPending`：在下单点抓拍方向/加仓序号/倍数/网格距/止盈距 + 环境快照(档位/状态/RV/点差/ATR/均量/基线/风险级)。
- `EvaBindEntry`：下单成功后用 `trade.ResultOrder()`(对冲账户=持仓号) 把上下文**绑定到 position_id**，并读该仓的 SL/TP。
- `EvaOnDealAdd`：在 `OnTradeTransaction` 里处理成交——进场兜底补绑、**出场时落盘一行**（含盈亏/净盈亏/持仓时长/出场原因）。
- `EvaSetExit`：EA 主动平仓前设置细分出场原因。
- `EvaWriteDecisionAudit`：网格触发开仓时记录“放行/被过滤(满仓/节奏)”。

**新增 4：插桩点（均为最小侵入，不改变任何分支条件）**
- `OnInit` 末尾：`EvaInit()`；`OnDeinit`：`EvaDeinit()`。
- `OnTradeTransaction` 开头：`EvaOnDealAdd(deal)`（原有逻辑保留）。
- `OnTick`：缓存当轮均量 `G_EvaAvgVolForLog`；在多/空开仓决策点抓拍上下文并写决策审计。
- `OpenBuyOrder/OpenSellOrder` 成功后：`EvaBindEntry(InpMagicNum)`。
- `OpenTrendBuyOrder/OpenTrendSellOrder` 成功后：`EvaCaptureTrendPending(...)+EvaBindEntry(InpTrendMagicNum)`。
- 10 个平仓点前各设一次 `EvaSetExit("…")`：基线回归、risk2/3/4、最后单止损、截止线止损、越界止损、节奏恐慌平、趋势状态退出、趋势确认清逆势网格。
- 出场原因优先取测试器/券商的 `DEAL_REASON`（tp/sl/stopout），EA 主动平仓才用上面设置的细分原因。

**为什么这么设计（针对“优化时可能出问题”的诉求）**
- **更优解：总开关 + 优化模式自动失效。** `EvaInit` 检测 `MQLInfoInteger(MQL_OPTIMIZATION)`，优化时即便忘了关也强制不写文件——这样调用 MT5 自带优化器跑多参数时，不会出现“多 pass 抢同一文件 / 拖慢优化器 / 文件错乱”。单次回测才输出明细。
- 写文件用**流式**：每笔单平仓即写一行并 `FileFlush`，即便中途异常也已落盘。
- 用 `position_id` 作主键、`DEAL_REASON` 兜底，**不依赖 OnTradeTransaction 的时序**，对冲/部分平仓也稳。
- 完全没有改动任何 `if` 条件、阈值、下单/平仓的触发逻辑——回测结果与 v1.00 一致，只是多了三个 CSV。

**产物（默认 `Common\Files\eva_audit\<run_id>\`）**
- `eva_trade_events.csv`（主表，43 列，见 §6）
- `eva_decision_audit.csv`（开仓决策放行/拦截）
- `eva_run_config.csv`（本次回测配置+键参数快照，一行）

---

### eva003_data_pipeline.py — v1.0（新建）

**做了什么**：4 个子命令
- `slice`：按 `周期 + 区间` 切一段行情落盘（tick/m1/m5/m15）。
- `enrich`：读 `eva_trade_events.csv`，对每笔单从仓库切持仓期间路径，算 **MFE/MAE(点&R)**、`path_type`（clean_win/grind_win/clean_loss/immediate_reverse/gave_back）、`problem_tag`（bad_entry/bad_exit/stopped_out/normal_loss/normal），输出 `trade_enriched.csv` + `problem_trades.csv` + `signal_performance.csv` + `regime_performance.csv`。tick 缺失自动回退 M1。
- `request`：读 eva004 请求文件，批量产出（range / around_time / trade_path）并写 `manifest.json`。
- `cache`：CSV→parquet 缓存，加速大区间反复读取。

**为什么这么做**
- 把“算 MFE/MAE、判断问题单”放到 Python 后处理（按交易时间切 tick），**让 EA 保持轻量**——正是共识里修正后的更优方案。
- 聚合表 `signal_performance / regime_performance` 直接服务于“哪个 signal/档位/状态在测试集长期亏”“哪些过滤器只减少交易数却没改善结果”等判断。
- `R` 仅在该单有止损价或显式给 `--default-r-pts` 时计算（网格单常无 SL，避免编造 R）。

---

### eva004_data_request_template.json — v1（新建）

**做了什么**：定义“二次取数请求”的 JSON 结构（`request_id/symbol/point/default_timeframe/trade_events/outputs[]`），`outputs` 支持三型：`range`（固定区间）、`around_time`（某时刻前后）、`trade_path`（按 position_id 或 filter 选单，进出场前后可延伸）。附可直接运行的示例。

**为什么这么做**
- 形成**分析方(含 AI) ↔ 数据**的标准接口：我看完初步数据后，只需按此格式吐一个 JSON，你/eva003 就能精确把对应区间或某些问题单的 tick 路径切出来，闭环“想看更多→给更多”。

---

## 4. 端到端运行手册（XAUUSD）

**第 1 步 导出行情（eva001）**
1. MT5 打开 XAUUSD 图表，确保历史已下载（视图→品种→下载/导入）。
2. 把 `eva001_TickDataExporter.mq5` 放进 `MQL5/Scripts` 并编译。
3. 拖到图表→设区间(如 2018-01 ~ 2026-12)与周期→确定。
4. 产物在 `…/MetaQuotes/Terminal/Common/Files/eva_data/XAUUSD/…`。把整个 `eva_data` 拷给做分析的机器。

**第 2 步 可审计回测（eva002）**
1. 用 `eva002_…mq5` 替换原 EA 编译。
2. 加载参数 `true01_2.set`，把 `InpEnableTradeAudit=true`（**仅单次回测；优化时无需手动关，会自动失效**）。
3. 跑回测。产物在 `Common\Files\eva_audit\<run_id>\`。

**第 3 步 交易增强诊断（eva003 enrich）**
```bash
pip install pandas pyarrow
python eva003_data_pipeline.py enrich \
  --root eva_data --symbol XAUUSD \
  --trades eva_audit/<run_id>/eva_trade_events.csv \
  --outdir enriched --path-tf tick
```
看 `enriched/problem_trades.csv`、`signal_performance.csv`、`regime_performance.csv`。

**第 4 步 二次取数（eva004 + eva003 request）**
按 `eva004_data_request_template.json` 改出你要的区间/问题单，然后：
```bash
python eva003_data_pipeline.py request \
  --file my_request.json --root eva_data --symbol XAUUSD \
  --trades eva_audit/<run_id>/eva_trade_events.csv --outdir req_out
```

**可选 切片 / 缓存**
```bash
python eva003_data_pipeline.py slice --root eva_data --symbol XAUUSD \
  --timeframe m1 --start "2024-03-05 13:00" --end "2024-03-05 15:00" --out seg.csv
python eva003_data_pipeline.py cache --root eva_data --symbol XAUUSD
```

---

## 5. 已做的自测

- eva002：静态检查通过——大括号配平(295/295)，所有 `Eva*` 调用均有定义，`trade_events` 表头与数据行均 43 列一致。逻辑分支零改动。
- eva003：用合成 tick/m1 + 两笔样本单跑通 `slice / enrich / request`：多单(MFE≫MAE,盈)→clean_win/normal；空单(MAE≫MFE,亏,last_order_stop)→clean_loss/stopped_out；request 的 range/around_time/trade_path(filter 与 指定 position_id) 全部出数并写 manifest。

---

## 6. 字段字典（eva_trade_events.csv，43 列）

`run_id, strategy_version, param_set_id, symbol, timeframe, position_id, deal_in, deal_out, order_kind(grid/trend), direction(±1), entry_reason(grid_buy/grid_sell/trend_buy/trend_sell), exit_reason, deal_reason_raw(tp/sl/expert/…), order_number(网格加仓序号), entry_time, entry_time_msc, entry_price, exit_time, exit_time_msc, exit_price, volume, sl_price, tp_price, profit, commission, swap, net_pnl, holding_seconds, vol_regime(0低1中2高), real_vol_regime, regime_open_allowed, market_state(0震荡1涨2跌), rv_short_pts, rv_long_pts, rv_ratio, multiplier_a, grid_dist_pts, tp_dist_pts, baseline_at_entry, risk_level_at_entry, avg_vol_per_min, spread_pts_at_entry, atr_at_entry`

`exit_reason` 取值：`tp / sl / stopout / grid_tp_baseline_revert / risk2_take_profit / risk3_take_profit / risk3_cut_loss / risk4_force_exit / last_order_stop / cutoff_line_stop / overshoot_stop / pacing_panic_stop / trend_state_exit / trend_close_opposite_grid / expert_close`。

---

## 7. 待确认 / 后续

1. **黄金报价位数**：eva001 自动按品种 `Digits`；eva003 默认 `--point 0.01`(2 位)。若你的 Exness XAUUSD 是 **3 位**，请运行 eva003 时加 `--point 0.001`（否则 MFE/MAE 点数与 R 会差 10 倍）。
2. tick 仓库较大；建议先用 `cache` 转 parquet。
3. 下一阶段(分析)：用 `signal_performance / regime_performance` 按“档位×状态×年份”切片，落实共识里的参数问题 vs 方法问题判别框架与多年数据分段(旧年压力测试 / 近年开发 / 最近前向)。
4. 如需把 `decision_audit` 也接入 enrich（量化“被过滤却本可盈利”的机会成本），可在下一版 eva003 增加 `--audit` 输入做联合分析。

---

*本日志随代码版本更新；新增/修改代码请在 §3 追加条目，写明改了什么、为什么。*
