# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG，v3）

> 标的：XAUUSDm（Exness 黄金，3 位报价 point=0.001），平台：Exness / MT5。
> 本日志含从“项目共识”至今的全部工作，并对每一版代码说明**改了什么、为什么改**。

---

## ★ 命名约定（再次更正，务必照此执行）

规则：**同一代（同一轮）的所有代码共用一个编号**，文件名 = `eva<代号>_<功能>`。

| 代 | 应有编号 | 实际产出（历史） | 包含文件 |
|---|---|---|---|
| 第1代 | 应统一 `eva001` | 误用 eva001/002/003/004 | 导出器/EA审计层/Python/请求格式 |
| 第2代 | 应统一 `eva005` | 误用 eva005/006/007 | 导出器v2/Python v2/请求格式v2 |
| **第3代（本轮）** | **`eva008`** | **已统一 eva008** | 见下 |

- 历史文件不改名（你手里已有）；**从本轮起，每一代只用一个编号**。
- **第3代 eva008 交付物**：
  - `eva008_TickDataExporterEA.mq5` —— 新增：**测试器版导出 EA**（解决“只导到近月”的根因）
  - `eva008_data_pipeline.py` —— 与 eva006 功能相同，仅按规则统一改名
  - `eva008_data_request_template.json` —— 与 eva007 格式相同，仅统一改名
- 可审计 EA（第1代的 `eva002`）本轮不变；价格全程 `_Digits`，3 位自动适配。

---

## ★ 本轮两点反馈的处理

**1）编号** —— 已按“同代同编号”更正，本轮全部用 `eva008`。

**2）数据下载（核心，已找到正解）**

你截图里的事实：实时跑 eva005 脚本时，预检显示 **M1 仅 2026-03、M5 仅 2025-01、tick 仅 2026-01**，2014 全年“无数据”。但回测时明明能用到 2014 起的数据。

- **数据是真实存在的，不是不存在。** 策略测试器会为回测区间**装载完整历史**(2014→今)，所以回测能用；而 eva005 是**脚本挂在实时图表上**，读的是**终端实时历史缓存**——这个缓存深度有限、深层历史不会自动拉满，故只看到近几个月。**两套缓存互不相通。**
- **你上次“先跑 real ticks 回测、再跑脚本”为何没用**：real-ticks 回测只把 tick 缓存进**测试器缓存**，脚本读的是**实时终端缓存**，所以脚本依旧只看到近月。
- **正解（=你提出的方案，正确）**：把导出器做成 **EA，在策略测试器里单次运行（Optimization 选 Disabled），逐 tick/逐 bar“收一个写一个”**。EA 在测试器里能看到测试器装载的**完整历史**，且 EA 在测试器里**可以写文件**。→ 这就是 `eva008_TickDataExporterEA.mq5`。
- **关于“量”**：你用的 `tick_volume` = **价格变化次数**（不是真实成交量）。EA 在测试器里取的是 **Exness 历史 K 线的 `tick_volume`**，与实盘一致；真实 tick 模型下还能拿到逐 tick。**全程是 Exness 自己的数据，不脱离实盘**——这也是不建议换 Dukascopy 等外部源的原因（它们的 tick_volume 口径不同，会脱离你策略所依赖的“量”）。

---

## ★ eva008 EA 导出器 —— 使用方法（重要）

两种典型跑法（在“策略测试器”里，品种选 **XAUUSDm**，Optimization=**Disabled**）：

- **A) 导完整 M1/M5（推荐先做，覆盖 2014→今，最稳）**
  - 模型选 **“1 minute OHLC”**；日期 2014.01.01 ~ 今；
  - `InpExportM1=true, InpExportM5=true, InpExportTicks=false`；开始。
  - 说明：M1/M5 在**任何模型**下都来自真实历史，含真实 `tick_volume`；M1 OHLC 模型最快。
- **B) 导真实 tick（按需，文件巨大，建议只取近几年）**
  - 模型选 **“Every tick based on real ticks”**；日期设近几年（如 2022~今）；
  - `InpExportTicks=true`（bar 可同时导，也可关）；可用 `InpTickFromDate/InpTickToDate` 进一步限定；开始。
  - 说明：只有 real-ticks 模型下导出的 tick 才是真实 tick；其他模型会是合成 tick（不要用）。

产物：`Common/Files/eva_data/XAUUSDm/{ticks,m1,m5,m15}/YYYY-MM.csv` + `meta.json`，与 eva005 同构，`eva008_data_pipeline.py` 直接可读。

> 若 A 跑出来 M1 仍偏少：确认测试器“日期”起点确实设到了 2014.01.01，且该品种在 Exness 历史中心确有那么久的数据（黄金通常有）。EA 进度日志会按月打印“当前 2014-01 / 2014-02 …”，可据此确认推进。

---

## 0. 总览与数据流

```
eva008(EA,测试器)  导出 完整 tick + M1/M5/M15 → 行情仓库 CSV + meta.json
eva002(EA)         原策略 + 可审计日志层（交易逻辑零改动，优化自动关闭）
eva008(py)         切片 / 交易增强(MFE·MAE·问题单) / 按请求文件出数 / 点值自动识别
eva008(json)       数据请求文件格式（二次取数）
```

```
eva008-EA(测试器) → 行情仓库(CSV)+meta.json
                          ┐
eva002 回测 → eva_trade_events.csv / eva_decision_audit.csv / eva_run_config.csv
                          ┘
              ↓ (eva008-py enrich：按交易时间切路径)
   trade_enriched.csv + problem_trades.csv + signal/regime_performance.csv
                          ↓ (分析→需要更多数据)
            eva008 请求文件 → (eva008-py request) → 指定切片
```

---

## 1. 此前工作回顾（项目共识）

- 目标：建立**可复用、可流水线化**的开发与诊断流程（哪些单不该开、亏损归因、识别无用过滤器、避免训练有效测试失效）。
- 让每笔单“可审计”：signal、趋势/波动状态、点差、过滤器、开仓后路径、MFE/MAE、出场方式、属正常亏损还是逻辑错误。
- 架构：行情只导一次；EA 只输出交易事件+信号状态；后处理按时间切片；分析与回测解耦；多机/多参数复用。
- 仓库按 `品种/周期/月` 分块；tick（算 MFE/MAE/扫损/点差）+ M1/M5（判结构/趋势/ATR/均线）。
- 被分析策略 `VolumetricPulseGrid_StateMachine v1.00`：波动率三档状态机 + 行情状态机 的网格/马丁 + 独立趋势单；参数 `true01_2.set`。

---

## 2. 每版代码变更记录（changelog）

### 第1代
- **eva001_TickDataExporter.mq5 v1.00**：首版脚本导出器。问题：未等待 MT5 异步下载，只导到近月。
- **eva002_VolumetricPulseGrid_StateMachine.mq5 build1.01（审计层，沿用至今）**：原 v1.00 逻辑零改动，新增 trade_events(43列)/decision_audit/run_config 三类 CSV；进场抓拍上下文按 position_id 绑定、出场在 OnTradeTransaction 落盘；出场原因优先 DEAL_REASON，10 个平仓点打细分标签；**优化模式自动关闭**避免多 pass 抢文件；价格用 `_Digits` 自动适配位数。
- **eva003_data_pipeline.py v1.0**：slice/enrich/request/cache。问题：point 写死 0.01、阈值按点写死。
- **eva004_data_request_template.json v1**：请求格式 v1，point 必填。

### 第2代
- **eva005_TickDataExporter.mq5 v2.00**：脚本导出器，加“强制下载+等待重试”、tick/K线区间分离、预检打印可用最早日期、位数 `max(Digits,3)`、写 meta.json。
  - **本轮实测发现其局限**：实时脚本读“终端实时缓存”，深层历史拉不满 → 仍只到近月（见上文“数据下载”分析）。故第3代改用测试器 EA。eva005 仍可用于**快速拉取近月数据**。
- **eva006_data_pipeline.py v2.0**：point 自动读 meta.json（缺省 0.001）；“大顺向”阈值改按价格（默认 $3，随 point 换算）→ 2/3 位通用，问题单不再因位数误判。
- **eva007_data_request_template.json v2**：point 改为可省略（自动识别）。

### 第3代（本轮，eva008）
- **eva008_TickDataExporterEA.mq5 v3.00（新增，核心）**
  - **改了什么**：把导出器从“实时脚本”改为“**策略测试器里运行的 EA**”。在 OnTick 里逐 tick 写（real-ticks 模型）+ 逐 bar（M1/M5/M15，任何模型，含真实 tick_volume）写；按月自动轮转文件；OnDeinit 收尾写最后一根 bar 并生成 meta.json；优化模式自动禁用；可用 `InpTickFromDate/InpTickToDate` 限定 tick 范围；进度按月打印。
  - **为什么**：实时脚本读的“终端实时缓存”深层历史拉不满，只能拿到近月；而测试器会装载**完整历史**(2014→今)，EA 在测试器里能看到每个 tick/bar 且能写文件——这是拿到完整 Exness 数据的可靠途径。`tick_volume` 沿用 Exness 口径，不脱离实盘。
- **eva008_data_pipeline.py（=eva006 功能，改名统一代号）**：仅日志标识 `[eva008]`、文档与命令示例更新；逻辑不变（point 自动识别、MFE/MAE、问题单、聚合表、request、cache 均与 eva006 一致）。
- **eva008_data_request_template.json（=eva007 格式，改名统一代号）**：内容/字段不变，文档引用改为 eva008。

---

## 3. 端到端运行手册（XAUUSDm）

**第 1 步 导出完整行情（eva008 EA，测试器）**
1. `eva008_TickDataExporterEA.mq5` 放进 `MQL5/Experts` 并编译。
2. 策略测试器 → 品种 XAUUSDm → **Optimization=Disabled**。
3. **A 跑（M1/M5 全程）**：模型 *1 minute OHLC*，日期 2014.01.01~今，`InpExportM1/M5=true, InpExportTicks=false` → 开始。
4. **B 跑（真实 tick，近几年）**：模型 *Every tick based on real ticks*，日期 2022~今，`InpExportTicks=true` → 开始。
5. 产物在 `…/Common/Files/eva_data/XAUUSDm/`（含 meta.json）。整个 `eva_data` 可拷给分析机。

**第 2 步 可审计回测（eva002，不变）**
- 加载 `true01_2.set`，`InpEnableTradeAudit=true`（仅单次回测；优化自动失效）。产物在 `Common\Files\eva_audit\<run_id>\`。

**第 3 步 交易增强诊断（eva008-py enrich）**
```bash
pip install pandas pyarrow
python eva008_data_pipeline.py enrich \
  --root eva_data --symbol XAUUSDm \
  --trades eva_audit/<run_id>/eva_trade_events.csv \
  --outdir enriched --path-tf tick
# 点值自动取 meta.json；可加 --point 0.001 强制
```

**第 4 步 二次取数（eva008 请求文件 + request）**
```bash
python eva008_data_pipeline.py request \
  --file my_request.json --root eva_data --symbol XAUUSDm \
  --trades eva_audit/<run_id>/eva_trade_events.csv --outdir req_out
```

**可选 切片 / 缓存**
```bash
python eva008_data_pipeline.py slice --root eva_data --symbol XAUUSDm \
  --timeframe m1 --start "2024-03-05 13:00" --end "2024-03-05 15:00" --out seg.csv
python eva008_data_pipeline.py cache --root eva_data --symbol XAUUSDm
```

---

## 4. 本轮自测
- eva008 EA：MQL5 语法/结构审阅通过（大括号配平 26/26，函数齐全；月轮转/收尾/meta/优化禁用逻辑完整）。本机无 MT5，请在 MetaEditor 编译确认。
- eva008-py：`py_compile` 通过；用 3 位合成数据 + meta.json 实测 enrich 正常（自动 point=0.001，阈值 $3=3000 点，分类正确）。

---

## 5. 字段字典
- **行情 CSV**：tick `time_msc,time_iso,bid,ask,last,volume,volume_real,flags,spread_pts`；bar `time,time_iso,open,high,low,close,tick_volume,spread,real_volume`。
- **meta.json**（eva008 EA 写）：`symbol, symbol_digits, output_digits, point, exported_by, bar_first_date, bar_last_date, tick_first_date, tick_last_date, total_ticks, total_bars, generated`。
- **eva_trade_events.csv（43 列）**：`run_id, strategy_version, param_set_id, symbol, timeframe, position_id, deal_in, deal_out, order_kind, direction, entry_reason, exit_reason, deal_reason_raw, order_number, entry_time, entry_time_msc, entry_price, exit_time, exit_time_msc, exit_price, volume, sl_price, tp_price, profit, commission, swap, net_pnl, holding_seconds, vol_regime, real_vol_regime, regime_open_allowed, market_state, rv_short_pts, rv_long_pts, rv_ratio, multiplier_a, grid_dist_pts, tp_dist_pts, baseline_at_entry, risk_level_at_entry, avg_vol_per_min, spread_pts_at_entry, atr_at_entry`。
- `exit_reason`：`tp/sl/stopout/grid_tp_baseline_revert/risk2_take_profit/risk3_take_profit/risk3_cut_loss/risk4_force_exit/last_order_stop/cutoff_line_stop/overshoot_stop/pacing_panic_stop/trend_state_exit/trend_close_opposite_grid/expert_close`。

---

## 6. 待确认 / 后续
1. 用 eva008 EA 按 A 跑先把 **M1/M5 全程**导出（最关键，分析够用）；看 EA 日志按月推进到 2014 否。若到不了 2014，多半是该品种在 Exness 历史中心的最早可用日期就晚于 2014（可在测试器把日期起点设到“数据存在的最早处”）。
2. 真实 tick 只导近几年即可（够算近年的 MFE/MAE）；老年份 MFE/MAE 由 eva008-py 自动用 M1 近似（path_source=m1）。
3. 数据到位后进入分析：用 `signal_performance/regime_performance` 按“档位×状态×年份”切片，落实参数问题 vs 方法问题判别框架与多年数据分段（旧年压力测试 / 近年开发 / 最近前向）。

---

*本日志随版本更新；新增/修改代码请在 §2 追加条目，写明改了什么、为什么。下一代请用 eva009 统一编号。*
