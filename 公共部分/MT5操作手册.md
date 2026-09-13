# MT5 操作手册 · 公共部分

> **给任何要在这台机器上驱动 MT5 的 AI（或人）：先读这份。**
> 建立：2026-09-10 · 建立者：DeepSeek · **更新：2026-09-11（数据源规范）**
> **本文只讲「怎么操作 MT5」。研究结论不在这里** —— 见 `接力说明.md` 与 `deepseek数据保存\outline\改进大纲_v2.md`。

---

## ★★★ 0. 数据源规范（2026-09-11 用户指令，最高优先级）

> **"以后请不要使用自建数据来跑，都使用 MT5 自带的接口来跑数据。"**

**规则：**

1. **只用 MT5 终端里的真实券商品种**（`XAUUSDm` / `BTCUSDm` / `USDJPYm`），
   在**策略测试器**里通过 `/config:` 无头运行。
2. **禁止 `CustomSymbolCreate` 自建品种**，**禁止把本地 CSV 合并后导入成 MT5 品种**。
   （本项目早期的 `dsh_MakeHist*.mq5` / `build_m1_all.py` 路线**已停用**，仅作历史记录。
   自建的 `XAUUSD_HIST` / `BTCUSD_HIST` / `JPYUSD_HIST` 已**物理删除**。）
3. **禁止用终端图表脚本的 `CopyRates` 去"凑"历史** —— 实测那条路只返回最近一段
   （受终端 "Max bars in chart" 限制），**会严重低估可用历史**。
4. 需要历史 → 用测试器的 `FromDate` 驱动服务器下载，再用**测试器内的 EA** 读数据。

**为什么（实测对比，这个坑很值钱）：**

| 品种 | 用"脚本导出 + 自建品种"得到的 | **真实可用（直接用券商品种）** |
|---|---|---|
| XAUUSDm | 2017.04 起 | **2014.01.14 起 · 3,305,609 根 M1** |
| BTCUSDm | 2025.09 起（12 个月） | **2018.02.09 起 · 4,502,107 根 M1** |
| USDJPYm | 2025.05 起（16 个月） | **2014.01.14 起 · 3,471,032 根 M1** |

→ **自建数据把历史砍掉了 7-8 年**，而且还要自己复刻合约规格（`tick_value` 只能存常量，
   盈亏口径容易错）。**直接用真实品种既更准也更全。**

**查当前可用历史的办法**（终端启动后自动刷新）：
```powershell
# 用 [StartUp] Script=dshtools\dsh_ProbeSpecs 启动一次终端，然后读：
#   <数据目录>\MQL5\Files\dshtools\specs.json
# 其中每个品种的 history.M1.bars / .first 就是真实可用范围
```

---

## 0. 三十秒版本

**可以不用人碰 MT5 界面，全自动完成：编译 EA → 跑回测 → 读报告 → 收成交流水。**

```powershell
# 一个 2 年回测（70 万根 M1）≈ 6 秒
cd "D:\desktop\新量化策略\deepseek数据保存\run"
python mt5exp.py --list                       # 看全部实验（旧 eva028 编排器）
# 或用新的趋势策略编排器：
cd "D:\desktop\新量化策略\deepseek数据保存\run_trend"
python runexp.py --list                       # 暂未实现 --list，直接看源码 EXPERIMENTS/BASE_PARAMS
python runexp.py --symbol gold --phase valid --set mytest --params "InpTrendTF=30"
```

⚠️ **最容易踩的隐藏坑**：**回测"成功"不等于"有交易"**。
我实测遇到过三次"终端退出码 0、报告写着 successfully finished、Bars/Ticks 都正常，但 Total Trades = 0"，
原因分别是 ①按金口径错（CFD vs FOREX）②`volume_min` 没写进去 ③手数算成 0 被全部拒绝。
**每轮验收必须看：成交笔数 > 0、报告回显的 input 正确、`exit_reason` 分布合理。**

---

## 1. 环境事实（本机实测值）

| 项 | 值 |
|---|---|
| 终端 | `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe` |
| 编译器 | `C:\Program Files\MetaTrader 5 EXNESS\MetaEditor64.exe` |
| 独立测试器 | `C:\Program Files\MetaTrader 5 EXNESS\metatester64.exe` |
| **终端数据目录** | `C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\` |
| **公共文件目录** | `C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\Common\Files\` |
| 构建版本 | build 6184（服务端 build 6140） |
| 券商 / 服务器 | Exness Technologies Ltd · `Exness-MT5Trial5` |
| 账户 | `277335900` · **USD** · 杠杆 1:200 · demo · hedging |
| 终端自带 MCP | 启动时日志有 `MCP started on 127.0.0.1:22346`（build 6184 自带） |

### 1.1 ★日志到底在哪（最容易找错的地方）

有 **四个**不同的日志位置，内容互不重叠：

| 谁写的 | 位置 | 内容 |
|---|---|---|
| **终端框架** | `<数据目录>\logs\YYYYMMDD.log` | 启动、网络、Tester 框架、`last test passed with result` |
| **EA 的 `Print()`** | `%APPDATA%\MetaQuotes\Tester\<终端ID>\Agent-127.0.0.1-3000\logs\YYYYMMDD.log` | **回测里 EA 的全部输出、成交、错误** |
| **脚本（Script）的 `Print()`** | `<数据目录>\MQL5\logs\YYYYMMDD.log` | ⚠️ **脚本不在上面那个 agent 日志里** |
| 编译日志 | 由你指定的 `/log:` 路径 | `Result: 0 errors, 0 warnings, ...` |

⚠️ **这些日志按"天"累积、只追加**。一个会话里跑 10 个实验，全部混在同一个文件里。
分析时**必须用时间戳分块**，否则会读到上一个实验的数据（我踩过，差点得出错误结论）。

⚠️ **所有 MT5 日志都是 UTF-16LE**：PowerShell 里必须 `Get-Content <file> -Encoding Unicode`。

---

## 2. 编译 EA / 脚本

```powershell
# 1) 把 .mq5 复制到 MQL5\Experts\<子目录>\ 或 MQL5\Scripts\<子目录>\
# 2) 编译（★必须用 Start-Process -Wait）
$p = Start-Process -FilePath "C:\Program Files\MetaTrader 5 EXNESS\MetaEditor64.exe" `
     -ArgumentList "/compile:`"<绝对路径>.mq5`"","/log:`"<日志路径>.log`"" -PassThru -Wait
# 3) 读日志（UTF-16LE）
Get-Content "<日志路径>.log" -Encoding Unicode | Select-String "Result:"
```

**必须记住的 4 件事**：

1. **必须 `Start-Process -Wait`**。直接 `& MetaEditor64.exe /compile:...` 在 PowerShell 里会**立刻返回**，日志还没落盘 → 你会读到 `Cannot find path`。
2. **退出码没有意义**（实测成功也返回 `1`）。**只认日志里的 `Result: 0 errors, 0 warnings`**。
3. 编译日志是 **UTF-16LE**。
4. **源文件必须是 UTF-8 with BOM**，否则中文注释乱码（旧项目 eva028 正好是 BOM，可直接用；自己新写的文件要注意）。

---

## 3. 无头启动终端

**必须用配置文件**（`/portable` 单独用不起作用）：

```powershell
terminal64.exe /config:"<绝对路径>\xxx.ini"
```

### 3.1 跑脚本（探针类）

```ini
[Common]
Login=277335900
Server=Exness-MT5Trial5
KeepPrivate=1
NewsEnable=0
CertInstall=0
[Charts]
ProfileLast=Default
MaxBars=500000
[Experts]
AllowLiveTrading=0        ; ★回测/研究一律 0
AllowDllImport=0
Enabled=1
Account=0
Profile=0
[StartUp]
Symbol=XAUUSDm
Period=M1
Expert=                   ; 留空
Script=dshtools\dsh_ProbeSpecs
ShutdownTerminal=1        ; ★跑完自动退出
```

### 3.2 跑回测（★含 `[TesterInputs]` 参数注入 —— 这是全自动化的关键）

```ini
[Common]
Login=277335900
Server=Exness-MT5Trial5
KeepPrivate=1
[Experts]
AllowLiveTrading=0
AllowDllImport=0
Enabled=1
[Tester]
Expert=eva028\eva028_VolumetricPulseGrid_CoreRiskV1   ; ★相对 MQL5\Experts，不带扩展名
Symbol=XAUUSD_HIST
Period=M1
Model=2                ; 0=每tick(真实tick) 1=每tick(基于真实tick) 2=1分钟OHLC
Optimization=0
FromDate=2023.01.03
ToDate=2024.12.31
ForwardMode=0
Deposit=500
Currency=USD
Leverage=1:200
ExecutionMode=0
Visual=0
Report=<报告名>
ReplaceReport=1
ShutdownTerminal=1
[TesterInputs]         ; ★★逐项覆盖 EA 的 input —— 不需要人去点 "Load .set"
InpLotSize=0.01
InpTrendBreakoutBars=30
InpRunTag=my_experiment
```

**关键坑**：

1. `Expert=` 写 **相对路径、不带 `.ex5`**。写成 `Experts\Examples\MACD\ExpertMACD.ex5` 会报 `EX5 not found`。
2. **终端不会自己退出**，除非 `ShutdownTerminal=1`；否则要手动 `Stop-Process`。
3. 终端退出码：`0` = 正常；`-1000012355` = 测试器没启动（通常是 `Expert=` 路径写错）。
4. **启动前先检查有没有 `terminal64` 在跑** —— 可能是用户自己开着看盘，先问一句再动。
5. `.set` 文件（UTF-16LE，格式 `name=value||start||step||stop||Y/N`）**不能直接喂给 ini**；
   `mt5exp.py` 的 `load_legacy_set()` 负责解析成 `[TesterInputs]`。

### 3.3 HTML 报告在哪、怎么解析

- 报告落在 **终端数据目录根下**：`<数据目录>\<Report名>.htm`
- ⚠️ **报告是 UTF-16LE（带 BOM）**。按 UTF-8 读会得到 **0 个 `<td>`**。
  参考实现：`deepseek数据保存\run\parse_report.py` 的 `read_html()`。
- ⚠️ 报告的键值结构是 `<td colspan="3">Key:</td><td><b>Value</b></td>` —— **键和值不一定相邻**（colspan 会插空 cell）。
  必须用「键之后第一个非键 cell」来取值，不能简单两两配对。
- ⚠️ **报告里会回显全部 EA input**。这是个很好用的"参数真的注入进去了吗"的自检手段。

---

## 4. ★自定义品种：用本地 CSV 造出几十年的历史

**为什么需要**：终端自带历史很短（实测 XAUUSDm 只有 5 周、BTCUSDm 1 周、USDJPYm 2 周），
因为终端会按访问时间清理老历史文件（启动日志里能看到 `HistoryCenter delete old files ... last access time ...`）。
**没有长历史就无法做任何有统计意义的回测。**

**三步走**（完整可运行实现见 `deepseek数据保存\mql5\dshtools\`）：

```text
步骤 1（Python）: build_import_csv.py
    把每月一个的 M1 CSV 合成单个导入文件
    → <数据目录>\MQL5\Files\dshtools\<SYMBOL>_M1.csv
    列: datetime \t open \t high \t low \t close \t tick_volume \t spread(价格单位)

步骤 2（MQL5 脚本）: dsh_MakeCustomSymbol.mq5
    CustomSymbolCreate() + 分批 CustomRatesUpdate()（批 20000 行）
    ⚠️ 所有品种属性都要显式设置，特别是 §4.1 / §4.2 两个坑

步骤 3（验证）: dsh_TesterProbe.mq5
    挂到测试器里打印实际读到的第一根 bar 的时间/价格
    → 一锤定音确认"测试器真的读到了这段历史"，不要靠 SeriesInfoInteger 猜
```

### 4.1 ★坑一：`SYMBOL_VOLUME_MIN` 写不进去

实测矩阵（`dsh_VolMinProbe.mq5`，`SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN)` 读回值）：

| 做法 | 结果 |
|---|---|
| `CustomSymbolCreate` 后直接 `set(VOLUME_MIN)` | **0.0000** ❌ |
| 再补一个 `VOLUME_LIMIT=1e6` | **0.0000** ❌ |
| **先 `SymbolSelect(sym, true)`，再 `set(VOLUME_MIN)`** | **0.0100** ✅ |
| 设完全部属性后 `set`（仍未 select） | **0.0000** ❌ |

**结论**：**先 `SymbolSelect(sym, true)`，再写手数**；并且**不要同时设 `SYMBOL_VOLUME_LIMIT`**。
我的最终实现是"开头 select 一次写一遍、结尾再 select 一次补写一遍"。

### 4.2 ★★坑二：保证金口径 —— 会让回测静默变成 0 成交

用 `SYMBOL_CALC_MODE_CFD` 时，测试器把 **0.01 手**的按金算成 **$1912**
（= `contract_size × volume × price`，完全没有除以杠杆）。
日志里的形态是：

```
calculated account state: Equity 500.00, Margin: 1912.88, FreeMargin: -1412.88
not enough money [instant sell 0.01 XAUUSD_HIST at 1912.884 sl: 1919.747]
```

**后果极其隐蔽**：终端退出码 `0`、报告说 `last test passed with result "successfully finished"`、
`Bars` 和 `Ticks` 都正常 —— **但 `Total Trades = 0`，一个月一笔都没成交。**

**正确做法**：用 **`SYMBOL_CALC_MODE_FOREX`**（按金 = 合约量/杠杆）。
真实 XAUUSDm 在 1:200 下 0.01 手按金只有 **$2.19**，改完立刻正常成交。

> 一般的教训：**自定义品种的"回测成功"必须用「成交笔数 > 0」和「按金数值合理」来验收**，
> 不能只看终端退出码和报告的 "successfully finished"。

### 4.3 自定义品种的规格清单（以黄金为例，务必与目标真实品种逐项对齐）

| 属性 | 值 | 说明 |
|---|---|---|
| `SYMBOL_DIGITS` / `SYMBOL_POINT` | 3 / 0.001 | 同真实品种 |
| `SYMBOL_TRADE_CONTRACT_SIZE` | 100 | 同真实品种（0.01 手 = 1 oz → **$1 波动 = $1**） |
| `SYMBOL_VOLUME_MIN/STEP/MAX` | 0.01 / 0.01 / 200 | ★见 §4.1 |
| **`SYMBOL_TRADE_CALC_MODE`** | **`SYMBOL_CALC_MODE_FOREX`** | ★★见 §4.2 |
| `SYMBOL_TRADE_TICK_SIZE` | 0.001 | |
| **`SYMBOL_TRADE_TICK_VALUE`** | **400.0** | ⚠️ 见 §4.4 |
| `SYMBOL_CURRENCY_BASE/PROFIT` | USD / USD | |
| `SYMBOL_SPREAD` / `SYMBOL_SPREAD_FLOAT` | 200 / false | 固定点差（历史中位） |
| `SYMBOL_SWAP_MODE` | DISABLED | 先不引入第二个变量 |
| `SYMBOL_TRADE_MODE` | FULL | |
| `SYMBOL_TRADE_STOPS_LEVEL` / `FREEZE_LEVEL` | 0 / 0 | |
| 模型 | 只能 `Model=2`（1 分钟 OHLC） | 自定义品种**没有真实 tick** |

### 4.4 ⚠️ `TICK_VALUE` 只能存常量 —— 必须说明你选了哪个口径

- 真实品种的 `SYMBOL_TRADE_TICK_VALUE` **随现价变化**（XAUUSDm 在 4385 时 ≈ 0.4385）。
- 但自定义品种只能存**一个固定值**。若历史跨越 42 个月、金价从 1804 涨到 5595（3.1 倍），
  **不存在"正确答案"** —— 只能选一个口径并**在结论里注明**。
- 它会影响哪些东西：**任何用「货币金额 ÷ tick_value」换算成价格距离的逻辑**
  （例：eva028 的末单止损 `loss_dist = InpLastOrderLossPerLot × tick_size / tick_value`）。
- **本项目选择**：按**参考价 4000** 校准 → `tick_value = 4000 × 100 × 0.001 = 400.0`。
  理由：让"每手 $800 亏损"折算成约 4.8% 价格（= 原设计意图），且与按 `price/InpRefPrice` 缩放的网格距自洽。

### 4.5 自定义品种存在哪、数据有多大

```
<数据目录>\bases\Custom\history\<SYMBOL>\
    ├── 2023.hcc  2024.hcc  2025.hcc  2026.hcc     ← 按年的原始 M1
    └── cache\M1.hc  M5.hc  M15.hc  H1.hc          ← MT5 自动生成的派生周期缓存
```
实测：42 个月黄金 M1（122.95 万根）共 **121.7 MB / 8 个文件**。

⚠️ **`SeriesInfoInteger(SERIES_BARS_COUNT)` 受终端 "Max bars in chart" 限制**（本机 500000）。
它返回的是**缓存口径**，不是磁盘上的真实根数。本机 `copyrates_from_2023_bars` 脚本里也只拿到 500000 根，
**但测试器能读到全部 122.95 万根**（用 `dsh_TesterProbe.mq5` 在测试器里验证过 `bar#1 time=2023.01.05`）。
→ **判断"测试器有没有数据"必须用测试器内的 EA，不能用终端脚本。**

---

## 4B. ★★ 让 MT5 自己去券商下载历史（比自建 CSV 更优先）

**先试这条，再考虑 §4 的自建方案。** 券商的 History Server 能直接给历史，而且**是权威数据**。

### 4B.1 下载 M1

```text
脚本: mql5\dshtools\dsh_DownloadHistory.mq5
做法: 对 M1 逐月调用 CopyRates(sym, PERIOD_M1, 月首, 月末, rates)
      → 本地没有就触发服务器下载（异步），所以请求后要 Sleep 并重试
      → 报告每个月实际拿到多少根，精确定位「券商到底有到哪一年」
配置: mql5\config\download_history.ini   （[StartUp] Script=dshtools\dsh_DownloadHistory）
```

**实测结果（2026-09-10，Exness demo 账户）**：

| 品种 | 券商 M1 可回溯到 | 拿到根数 |
|---|---|---|
| XAUUSDm | **2025-04-11** | 500,017 |
| USDJPYm | **2025-05-08** | 500,009 |
| BTCUSDm | **2025-09-28** | 500,012 |

⚠️ **不是无限回溯** —— 更早的服务器不给。想要 2023-2024 就必须自建（§4）。
⚠️ **注意 `Max bars in chart` 上限**：一次 CopyRates 拿到的根数会被这个设置截断（本机 500000）。
按**月**切片请求可以绕开"一次拿多少"，但**总可用量仍受券商供给限制**。

### 4B.2 用真实 tick 回测（★这是自建自定义品种做不到的）

自建自定义品种**只有 M1 OHLC**，只能 `Model=2`。
**但真实符号可以 `Model=1`（每 tick 基于真实 tick）**，测试器会自己去下载 tick：

```ini
[Tester]
Symbol=XAUUSDm          ; ★用真实符号，不是自定义品种
Period=M1
Model=1                 ; ← 真实 tick
FromDate=2025.04.11
ToDate=2026.09.10
```

实测：黄金 2025-04-11 ~ 2026-09-10 全段 **Bars=499693、Ticks=1,998,735、History Quality=98%**。
tick 数据会落盘到 `<数据目录>\bases\<server>\ticks\<SYMBOL>\YYYYMM.tkc`。

⚠️ **tick 的历史比 M1 短得多**。本机实测：黄金只有 **2026-08 起**有真 tick 文件；更早段 MT5 会**自行合成**
（报告仍显示 98% 质量）。**引用时要说明"哪一段是真 tick、哪一段是合成"**，不要一概而论。

### 4B.3 导出成 CSV 给 Python 用

```text
脚本: mql5\dshtools\dsh_ExportRates.mq5
做法: 逐月 CopyRates → 写成 CSV 到 Common\Files\dshtools\<SYM>_{M1,M5}_real.csv
      列: datetime,open,high,low,close,tick_volume,spread
      ★ spread 是「点」，是等值点差（不是 tick 数）
配置: mql5\config\export_rates.ini
```

### 4B.4 已验证的数据质量结论（可直接引用）

把「旧项目导出的黄金 CSV」与「本次从券商下载的黄金 M1」对比：

| 项 | 结果 |
|---|---|
| 重叠期 | 2025-04-11 ~ 2026-06-30，**429,224 根共同 bar** |
| 收盘价绝对差 | **中位 0.0000 · p95 0.0000 · 最大 0.0000** |
| 点差中位 | 两边都是 **160 点** |

→ **两者是同一份数据。** 旧 CSV 可信，而且它补上了券商**已经不再提供**的 2023-01 ~ 2025-04。
→ **一般结论：判断"外部 CSV 是否可信"，最便宜的办法就是拿一段与券商下载的重叠期做逐 bar 对比。**

---

## 5. 从回测里把结果取出来

### 5.1 三类产出

| 产出 | 位置 | 说明 |
|---|---|---|
| HTML 报告 | `<数据目录>\<Report名>.htm` | UTF-16LE，见 §3.3 |
| **审计 CSV** | `Common\Files\eva_audit\<run_id>\` 或 `<数据目录>\MQL5\Files\eva_audit\<run_id>\` | EA 自己写的成交流水（含 `exit_reason` / `mae` / `mfe`） |
| EA 日志 | Tester agent 目录，见 §1.1 | |

### 5.2 审计 CSV 是"机制有没有真的触发"的唯一证据

**这是全项目最重要的验证手段。** 旧项目至少 3 次、我这一轮 1 次（网格 0 成交），
都是"以为机制在工作、实际从未触发"。
**规矩：每加/改一个机制，先用 `exit_reason`（或决策审计的 `note` 字段）计数确认它真的触发过，再谈效果。**

EA 侧相关开关（eva028 为例）：
```
InpEnableTradeAudit=true         ; 总开关
InpAuditDecisions=true           ; 逐次开仓决策（含"被什么条件过滤"）—— 很占空间，平时关
InpAuditUseCommonFile=true       ; 写到 Common\Files（跨终端可取）
InpRunTag=<名称>                 ; 指定输出目录名，便于回收
```
⚠️ **优化模式（`MQL_OPTIMIZATION`）下 EA 会自动关闭审计**（多 pass 抢文件），这是设计行为。

### 5.3 参考实现

| 脚本 | 作用 |
|---|---|
| `deepseek数据保存\run\mt5exp.py` | 实验编排器：`.set` 解析 → `LOCKED_BASE` 锁精度参数 → 单变量覆盖 → 生成 ini → 无头回测 → 回收报告/审计/日志 |
| `deepseek数据保存\run\parse_report.py` | HTML 报告解析（自动处理 UTF-16LE + colspan） |
| `deepseek数据保存\run\analyze_runs.py` | 多实验对比表 + `exit_reason` 归因 |

---

## 6. 操作边界（请遵守）

- ✅ **可以做**：编译、无头回测、优化、读日志/报告、建自定义品种、写自己的 EA/脚本、导出数据到自己的工作区。
- ✅ 回测/研究配置里**始终** `AllowLiveTrading=0`。
- ⛔ **不要做（除非用户明确授权）**：**真实账户**下单、改用户真实账户的交易设置、在实盘终端上启动带自动交易的 EA。
- ⚠️ 只改 `MQL5\Experts`、`MQL5\Scripts`、`MQL5\Files`、`bases\Custom` 下**自己创建的文件**；
  **不要碰用户原有的 EA / 指标 / 模板**。自定义品种只影响历史库，与真实品种隔离。
- ⚠️ **启动终端前先确认没有别的 `terminal64` 在跑**（可能是用户在看盘）。
- ⚠️ 每次启动都用带 `ShutdownTerminal=1` 的 ini；**偶发不退出时手动 `Stop-Process`**，别长期占着终端。

---

## 7. 速查：最短的成功路径

```powershell
# 0) 清干净
Get-Process terminal64 -ErrorAction SilentlyContinue | Stop-Process -Force

# 1) 编译（必须 -Wait）
$p = Start-Process "C:\Program Files\MetaTrader 5 EXNESS\MetaEditor64.exe" `
     -ArgumentList "/compile:`"$mq5`"","/log:`"$log`"" -PassThru -Wait
Get-Content $log -Encoding Unicode | Select-String "Result:"      # 要看到 0 errors

# 2) 跑回测（用编排器最省事）
cd "D:\desktop\新量化策略\deepseek数据保存\run"
python mt5exp.py --run <exp_id>

# 3) 验收（★别只看退出码）
#    - 报告的 Total Trades > 0 ？
#    - 报告回显的 input 是不是你想要的那一组？
#    - 审计 CSV 里 exit_reason 的分布合理吗？机制真的触发了吗？

# 4) 对比
python analyze_runs.py <exp_id1> <exp_id2> ...
```

---

## 8. 已知坑总表（按"会不会让你静默出错"排序）

| # | 坑 | 症状 | 解法 |
|---|---|---|---|
| 1 | 自定义品种用 `CALC_MODE_CFD` | **0 成交，但报告说 success** | 用 `SYMBOL_CALC_MODE_FOREX` |
| 2 | `VOLUME_MIN` 在 `SymbolSelect` 前写 | 读回 0.0000 | 先 `SymbolSelect(sym,true)` 再写；别设 `VOLUME_LIMIT` |
| 3 | 报告按 UTF-8 读 | 解析出 0 个 cell | 按 **UTF-16LE** 读 |
| 4 | 报告键值按两两配对解析 | 取到错误的字段值 | colspan 会插空 cell，要用"键后第一个非键 cell" |
| 5 | 日志按天累积、只追加 | 读到上一个实验的数据 | 用时间戳分块 |
| 6 | 直接 `& MetaEditor64.exe` | 编译日志不存在 | 用 `Start-Process -Wait` |
| 7 | 编译退出码当成功判据 | 成功也返回 1 | 只认日志的 `0 errors` |
| 8 | 在终端脚本里查 `SERIES_BARS_COUNT` | 以为只有 50 万根 | 那是缓存口径；**要用测试器内 EA 验证** |
| 9 | 找 EA 的 `Print()` 找错地方 | 只有框架日志 | EA → Tester agent 目录；**脚本 → `MQL5\logs\`** |
| 10 | `Expert=` 带 `.ex5` 或带 `Experts\` | `EX5 not found` / 退出码 `-1000012355` | 相对路径、不带扩展名 |
| 11 | `tick_value` 当成"正确值" | 止损距离算错 | 它只能存常量；**换口径必须写明**（§4.4） |
| 12 | 只管跑不管验收 | 静默 0 成交 / 机制没触发 | 每轮必查：成交笔数、input 回显、`exit_reason` 分布 |
| 13 | 以为 `CopyRates` 能拉到任意久的历史 | 拉不到就以为"数据坏了" | 券商只给近几年（本次实测金 2025-04 起）；更早必须自建 |
| 14 | 以为自定义品种能做真实 tick 回测 | 只能 `Model=2` | 真实 tick 要用**真实符号** + `Model=1`（§4B.2） |
| 15 | 把"98% History Quality"当成"全是真 tick" | 高估回测可信度 | tick 只覆盖近月，更早是合成的；**要分段说明** |
| 16 | 用外部 CSV 但没验证 | 数据错了全盘错 | **与券商下载的重叠期做逐 bar 对比**（§4B.4，本次实测差异 = 0） |

---

*本手册由 DeepSeek 维护。技术细节（脚本实现）在 `deepseek数据保存\mql5\dshtools\` 与 `deepseek数据保存\run\`，不在此重复。*
*配套：`接力说明.md`（项目入口）· `进展日志.md`（时间线）。*
