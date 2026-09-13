# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG，v2）

> 标的：XAUUSD（黄金），平台：Exness / MT5。
> 本日志记录从“项目共识”到 v2 的全部工作，并对每一版代码说明**改了什么、为什么改**。

---

## ★ 命名约定（按你的澄清更正）

- `evaNNN_` 中的 `NNN` 代表**第几代**：`eva005_TickDataExporter` = 导出器的新一代。
- 上一轮我误把 eva001~004 当成四个并列工具来用；为避免混乱，**本轮起从 eva005 顺延编号**。
- 对应关系：
  - 导出器：`eva001`(旧/有问题) → **`eva005`(本轮修复版)**
  - Python 流水线：`eva003`(旧) → **`eva006`(本轮)**
  - 请求文件格式：`eva004`(旧) → **`eva007`(本轮)**
  - 可审计 EA：`eva002` **无需改**（价格全程用 `_Digits`，2/3 位自动适配，详见下文第 2 点）。

---

## ★ 本轮针对你四点反馈的处理

**1）编号含义** —— 已按“第几代”理解，本轮从 eva005 起。见上。

**2）黄金位数（你看到输出是 2 位）** ——
- 旧 eva001 用 `DoubleToString(price, SYMBOL_DIGITS)`。**输出几位完全取决于 MT5 报给该品种的 `SYMBOL_DIGITS`**：你看到 2 位，说明**你当时所在图表的那个黄金品种，MT5 报的就是 2 位**（point=0.01）。这不是代码 bug，而是“按品种位数如实输出”。
- Exness 有多个黄金变体，不同账户/后缀位数可能不同（常见 XAUUSD 为 3 位 point=0.001，也有 2 位变体）。所以“应该是 3 位”要看你具体那个品种。
- **新 eva005 的做法**：输出位数 = `max(品种Digits, InpForceMinDigits=3)`。
  - 若该品种其实是 3 位，3 位精度**完整保留**；
  - 若该品种确为 2 位，仅多一个无害的尾零（不会凭空造出精度）；
  - 开头会**明确打印** `SYMBOL_DIGITS=? SYMBOL_POINT=? 输出位数=?`，请以这行为准核对。若打印是 2，请确认你图表上的黄金是不是 3 位的那个（换成 3 位品种再导）。
- **eva005 还会写 `meta.json`**（含 digits/point），eva006 自动读取，后续 Python 不必手填点值。

**3）数据只导出到部分历史（最关键）** ——
- **根因**：`CopyRates`/`CopyTicksRange` **只返回终端本地已下载好的历史**；MT5 历史是**异步后台下载**的。脚本一次性调用时，只抓到当时缓存里已有的那部分，剩下仍在下载的就被跳过——所以你得到的是“最近若干月、各周期数量还不一致”。**和你拖图、用默认参数无关。**
- **两条硬约束**：
  - 真实 tick 的历史深度由**券商**决定，Exness 黄金真实 tick 通常只回溯**最近几年**，2014 年的真实 tick 大概率根本不存在；
  - M1/M5 **K 线**一般能回溯很久（黄金常到 2010 年代初）。
- **“是否要写成回测里运行”**：不需要，也做不到——**脚本不能在策略测试器里运行**（测试器只跑 EA）。正解是在脚本里加“强制下载 + 等待重试”。
- **eva005 的修复**：
  1. 预检阶段先**触发后台下载并循环等待**（`Bars()/CopyRates` 触发同步，`SeriesInfoInteger(SERIES_FIRSTDATE)` 判断是否回溯到位），并打印每个周期**实际可用最早日期**；
  2. 每个月/天的 `CopyRates/CopyTicksRange` 都带**重试+Sleep**，直到下载到或超时；
  3. **tick 与 K 线区间分开**：K 线可全程（如 2014→今），tick 默认只取近几年（避免在不存在的老 tick 上空等数小时）；并自动跳过早于“券商可用 tick 起点”的月份。
- **若仍偏少的兜底办法**（已写进脚本结束提示）：① 确认终端已连线；② `Tools→Options→Charts` 把 *Max bars in chart* 设为 *Unlimited*；③ 想要更久的**真实 tick**，先在测试器用 **“Every tick based on real ticks”** 模式跑一遍该区间（这会把真实 tick 缓存到本地），再运行 eva005 导出。
  - 顺带解释你的现象：你之前那次 2014→今的回测“有下载提示”，但若用的不是 *real ticks* 模型（而是 *1 minute OHLC* / *Open price only*），就**不会**缓存真实 tick，只会缓存对应 K 线——这正是 tick 很少、各周期数量不一的来源之一。

**4）位数变了，同步更新其他文件** ——
- EA（eva002）：价格全程用 `_Digits`，3 位自动适配，**无需改**。
- Python：新 **eva006** 自动从 `meta.json` 取 point（缺省 0.001/3 位）；并把“吃到大顺向后回吐”的阈值由**按点写死(300)** 改为**按价格(美元)表达**（默认 `--mfe-big-price 3.0`，随 point 自动换算成点数），确保 2 位/3 位通用、不会因位数变化误判问题单。
- 请求格式：新 **eva007** 的 `point` 字段改为**可省略**（自动识别），示例更新为 3 位。

---

## 0. 总览与数据流

```
eva005  导出行情(tick + M1/M5/M15)，强制下载+等待，按 品种/周期/月 分块 CSV，并写 meta.json
eva002  原 EA + “可审计日志”层（交易逻辑零改动，优化时自动关闭）—— 本轮不变
eva006  Python：切片 / 交易增强(MFE·MAE·问题单) / 按请求文件出数 / parquet 缓存；点值自动识别
eva007  数据请求文件格式：分析方(含 AI)想要更多数据时按此生成，交给 eva006
```

```
eva005 → 行情仓库(CSV)+meta.json
                    ┐
eva002 回测 → eva_trade_events.csv / eva_decision_audit.csv / eva_run_config.csv
                    ┘
            ↓ (eva006 enrich：按交易时间从仓库切路径)
   trade_enriched.csv + problem_trades.csv + signal/regime_performance.csv
                    ↓ (分析 → 需要更多数据)
        eva007 请求文件 → (eva006 request) → 指定切片
```

落实的项目共识：不解析 MT5 底层私有文件；用官方接口导出；EA 回测只输出交易事件与信号状态（轻量）；行情与回测解耦，Python 按交易时间切片；支持多机/多参数复用同一行情仓库。

---

## 1. 此前工作回顾（项目共识）

- 目标不是盲目调参，而是建立**可复用、可流水线化**的开发与诊断流程：判断哪些单本不该开、亏损归因（入场/出场/参数/方法）、识别无用过滤器、避免训练集有效测试集失效。
- 核心共识：不要只看浓缩回测报告，要让每笔单“可审计”（signal、趋势/波动状态、点差、过滤器、开仓后路径、MFE/MAE、出场方式、属正常亏损还是逻辑错误）。
- 架构：行情只导一次；EA 只输出交易事件+信号状态；后处理按 `entry_time/exit_time` 切片；分析与回测解耦；多机并行；多参数复用。
- 仓库按 `品种/周期/月` 分块；同时留 tick（算 MFE/MAE/扫损/点差）与 M1/M5（判结构/趋势/ATR/均线）。
- 第一阶段：保持交易逻辑不变，先把 EA 改成可审计版本（eva002 已完成）。

被分析策略 `VolumetricPulseGrid_StateMachine v1.00`：波动率三档(低/中/高)状态机 + 行情状态机(震荡/趋势) 的**网格/马丁**策略 + 独立趋势单；出场由基线回归、分级风险、冷静期、若干硬止损决定。当前参数 `true01_2.set`（RegimeMode=AUTO、固定长周期RV=1000点@参照价4500、Lot 0.01、Magic 123456）。

---

## 2. 每版代码变更记录（changelog）

### eva001_TickDataExporter.mq5 — v1.00（已被 eva005 取代）
- 首版导出器：拖到图表运行，按 品种/周期/月 导出 CSV。
- **问题**：直接 `CopyRates/CopyTicksRange` 一次性取数，未等待 MT5 异步下载 → 只导出本地已缓存的近月数据（即你遇到的现象）。位数按 `SYMBOL_DIGITS` 输出。

### eva002_VolumetricPulseGrid_StateMachine.mq5 — build 1.01（“审计层”，本轮不变）
- 在原 v1.00 上**只加记录、不改逻辑**：
  - 输入组 `=== eva002 审计日志 ===`：`InpEnableTradeAudit`(总开关,默认false)、`InpAuditDecisions`、`InpRunTag/InpParamSetId/InpStrategyVersion`、`InpAuditUseCommonFile`。
  - 三个 CSV：`eva_trade_events.csv`(43列)、`eva_decision_audit.csv`、`eva_run_config.csv`，落 `Common\Files\eva_audit\<run_id>\`。
  - 进场在下单点抓拍上下文(档位/状态/RV/点差/ATR/均量/基线/风险级/加仓序号/倍数/网格距/止盈距)，下单成功后按 `position_id` 绑定；出场在 `OnTradeTransaction` 落盘一行（盈亏/净盈亏/持仓时长/出场原因）。
  - 出场原因优先 `DEAL_REASON`(tp/sl/stopout)，EA 主动平仓在 10 个平仓点各打细分标签。
- **优化保护（针对“调用 MT5 优化器可能出问题”）**：`EvaInit` 检测 `MQL_OPTIMIZATION`，**优化时强制关闭**，即便忘了关也不会多 pass 抢同一文件/拖慢优化器。
- **位数**：全程 `_Digits`，3 位自动适配，无需为本次位数变化改动。

### eva003_data_pipeline.py — v1.0（已被 eva006 取代）
- 子命令 slice/enrich/request/cache；MFE/MAE/path_type/problem_tag + 聚合表。
- **问题**：`--point` 默认写死 0.01；“大顺向”阈值按点写死 300。位数变 3 位后需手改。

### eva004_data_request_template.json — v1（已被 eva007 取代）
- 请求格式 v1；`point` 必填、示例为 0.01。

---

### eva005_TickDataExporter.mq5 — v2.00（本轮新建，导出器第2代）
**改了什么**
- 加入**“强制下载 + 等待重试”**：预检阶段触发后台下载并循环等待（`Bars()/CopyRates` 触发同步，`SERIES_FIRSTDATE` 判断回溯到位），各月/天 `CopyRates/CopyTicksRange` 带重试+Sleep。新增参数 `InpSyncWaitSec/InpMaxRetries/InpRetrySleepMs`。
- **tick 与 K 线区间分开**：K 线 `InpFromYear..InpToYear`(可全程)，tick `InpTickFromYear..InpTickToYear`(默认近几年)；自动跳过早于券商可用 tick 起点的月份。
- **预检打印**每个周期**实际可用最早日期**，并把真实 tick 缺老年份的情况显式提示。
- **价格位数**：输出 = `max(品种Digits, InpForceMinDigits=3)`，防 3 位被截断；开头打印检测到的 Digits/Point。
- **写 `meta.json`**：digits/point/各周期可用起点，供 eva006 自动识别点值。

**为什么**
- 直接解决“只导到部分历史”的根因（异步下载未等待），并把 tick 历史深度的现实约束（券商只有近几年）工程化处理（分区间 + 跳过 + 明确报告），避免空等。
- 位数自动对齐 + 写 meta，杜绝 2/3 位混淆与精度截断。

### eva006_data_pipeline.py — v2.0（本轮新建，Python 第2代）
**改了什么**
- **点值自动识别**：优先读 `<root>/<symbol>/meta.json` 的 point，缺省 0.001(3位)；`--point>0` 仍可强制覆盖。`slice/enrich/request` 三个命令都接入。
- **“大顺向”阈值改按价格(美元)表达**：`--mfe-big-price`(默认 3.0)随 point 换算为点数，2/3 位通用；保留 `--mfe-big-pts`(>0 覆盖)。
- 其余（MFE/MAE、path_type、problem_tag、signal/regime 聚合、tick 缺失回退 M1、request 三型、cache）与 eva003 一致。

**为什么**
- 让位数变化“无感”：换 3 位品种、重导数据后，Python 端不必手改点值与阈值；问题单分类不会因位数缩放被误判（实测 pos102 在 3 位下用 $3 阈值正确归为 clean_loss/stopped_out，而按点写死 300 会误判 gave_back）。

### eva007_data_request_template.json — v2（本轮新建，请求格式第2代）
**改了什么**
- `point` 改为**可省略**（eva006 自动识别）；示例更新为 3 位场景；新增按 `entry_reason×vol_regime` 选“开仓即反向”候选单等示例。

**为什么**
- 与 eva006 的自动点值对齐，减少手填；示例更贴近实际诊断需求。

---

## 3. 端到端运行手册（XAUUSD）

**第 1 步 导出行情（eva005）**
1. 终端**保持连线**；`Tools→Options→Charts` 的 *Max bars in chart* 设 *Unlimited*。
2. `eva005_TickDataExporter.mq5` 放进 `MQL5/Scripts` 编译。
3. 打开**3 位的那个** XAUUSD 图表，拖入脚本：
   - K 线区间设全程（如 2014-01 ~ 2026-12）；tick 区间设近几年（如 2022-01 ~ 2026-12）。
   - 看“专家/日志”里打印的 `SYMBOL_DIGITS=…`、各周期“可用最早日期”。
4. 产物在 `…/Common/Files/eva_data/XAUUSD/`（含 `meta.json`）。整个 `eva_data` 可拷给分析机。
5. 真实 tick 想要更久：先在测试器用 *Every tick based on real ticks* 跑一遍该区间，再运行本脚本。

**第 2 步 可审计回测（eva002，不变）**
- 用 eva002 编译，加载 `true01_2.set`，`InpEnableTradeAudit=true`（仅单次回测；优化自动失效）。产物在 `Common\Files\eva_audit\<run_id>\`。

**第 3 步 交易增强诊断（eva006 enrich）**
```bash
pip install pandas pyarrow
python eva006_data_pipeline.py enrich \
  --root eva_data --symbol XAUUSD \
  --trades eva_audit/<run_id>/eva_trade_events.csv \
  --outdir enriched --path-tf tick
# 点值自动取自 meta.json；如需覆盖加 --point 0.001 或 0.01
```

**第 4 步 二次取数（eva007 + eva006 request）**
```bash
python eva006_data_pipeline.py request \
  --file my_request.json --root eva_data --symbol XAUUSD \
  --trades eva_audit/<run_id>/eva_trade_events.csv --outdir req_out
```

**可选 切片 / 缓存**
```bash
python eva006_data_pipeline.py slice --root eva_data --symbol XAUUSD \
  --timeframe m1 --start "2024-03-05 13:00" --end "2024-03-05 15:00" --out seg.csv
python eva006_data_pipeline.py cache --root eva_data --symbol XAUUSD
```

---

## 4. 本轮自测
- eva005：MQL5 语法逻辑审阅（下载等待/重试/区间分离/位数/meta），未在本机编译（无 MT5），请在 MetaEditor 编译确认。
- eva006：`py_compile` 通过；用 **3 位**合成数据 + `meta.json` 实测：自动识别 `point=0.001`；`slice/enrich/request` 全通过；阈值改按价格后，亏损单正确归类 clean_loss/stopped_out（按点写死会误判 gave_back，已修）。

---

## 5. 字段字典（eva_trade_events.csv，43 列）
`run_id, strategy_version, param_set_id, symbol, timeframe, position_id, deal_in, deal_out, order_kind(grid/trend), direction(±1), entry_reason, exit_reason, deal_reason_raw, order_number, entry_time, entry_time_msc, entry_price, exit_time, exit_time_msc, exit_price, volume, sl_price, tp_price, profit, commission, swap, net_pnl, holding_seconds, vol_regime(0低1中2高), real_vol_regime, regime_open_allowed, market_state(0震荡1涨2跌), rv_short_pts, rv_long_pts, rv_ratio, multiplier_a, grid_dist_pts, tp_dist_pts, baseline_at_entry, risk_level_at_entry, avg_vol_per_min, spread_pts_at_entry, atr_at_entry`

`exit_reason`：`tp / sl / stopout / grid_tp_baseline_revert / risk2_take_profit / risk3_take_profit / risk3_cut_loss / risk4_force_exit / last_order_stop / cutoff_line_stop / overshoot_stop / pacing_panic_stop / trend_state_exit / trend_close_opposite_grid / expert_close`

`meta.json`（eva005 写，eva006 读）：`symbol, symbol_digits, output_digits, point, m1_first_date, tick_first_date, generated`

---

## 6. 待确认 / 后续
1. 请用 eva005 在**确认为 3 位**的黄金图表上重导，并核对开头打印的 `SYMBOL_DIGITS`。若仍是 2，说明该品种确为 2 位，请换 3 位变体。
2. 真实 tick 老年份大概率不存在（券商限制）；老年份的 MFE/MAE 由 eva006 自动用 M1 近似（path_source=m1）。
3. 下一阶段（分析）：用 `signal_performance/regime_performance` 按“档位×状态×年份”切片，落实参数问题 vs 方法问题判别框架与多年数据分段（旧年压力测试 / 近年开发 / 最近前向）。

---

*本日志随版本更新；新增/修改代码请在 §2 追加条目，写明改了什么、为什么。*
