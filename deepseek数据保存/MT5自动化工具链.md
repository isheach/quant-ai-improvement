# MT5 自动化工具链 · 已验证可用（DeepSeek）

> 验证时间：2026-09-10（第二轮）· **2026-09-11 重大更新：用户指令 + 数据源规范**
> 状态：**全链路打通，且已批量跑了 190+ 次回测**
> 本文档记录"我（AI）如何直接驱动 MT5"，含精确路径、配置模板、实测结果与已知坑。
> 配套：`MEMORY.md`（工作记忆）· `outline\改进大纲_v2.md`（研究主线）

---

## 0. ★★ 用户指令（2026-09-11，长期有效，最高优先级）

> **"以后请不要使用自建数据来跑，都使用 MT5 自带的接口来跑数据。"**

**执行细则（我据此把自建品种全部删除并固化为纪律）：**

1. **一律使用 MT5 终端里的真实券商品种**（`XAUUSDm` / `BTCUSDm` / `USDJPYm`），
   在**策略测试器**里通过 `/config:` 无头运行。**不再调用 `CustomSymbolCreate` 建品种。**
2. **不再把本地 CSV 合并、再导入成 MT5 品种。**
   （即 `dsh_MakeHist*.mq5`、`build_m1_all.py` 这条路线**停用**，仅作历史记录保留。）
3. **不依赖终端图表脚本的 `CopyRates` 导出去"凑"历史** ——
   实测那条路只给最近一段（受 Max bars in chart 限制），会**严重低估**可用历史。
4. 需要历史时，**让测试器的 `FromDate` 去驱动下载**（`AutoTesting: preliminary downloading`
   会自动从服务器拉），然后用测试器内的 EA 读数据。

### 0.1 为什么这条指令是对的（我的实测证据）

我此前用"终端脚本导出 + 自建品种"绕了一大圈，结果**把数据砍掉了 7-8 年**：

| 品种 | 我**以为**的可用历史（脚本导出） | **真实可用历史**（删掉自建品种后实测） |
|---|---|---|
| XAUUSDm | 2017.04 起 | **2014.01.14 起，3,305,609 根 M1** |
| BTCUSDm | 2025.09 起（12 个月） | **2018.02.09 起，4,502,107 根 M1** |
| USDJPYm | 2025.05 起（16 个月） | **2014.01.14 起，3,471,032 根 M1** |

**教训：自建数据不仅多一道手工环节（合约规格要复刻、tick_value 只能存常量、
盈亏口径可能错），还会因为导出路径的限制而丢掉大部分历史。直接用真实品种既更准也更全。**

（本节数据由 `mql5\config\verify_clean.ini` + `dsh_ProbeSpecs.mq5` 实测得到，
  每次终端启动后 `MQL5\Files\dshtools\specs.json` 会自动刷新。）

---

## 1. 一句话

**我可以自己编译 EA、自己跑回测、自己读结果 —— 不需要人操作 MT5。**
一次 2 年（70 万根 M1）回测 **约 6 秒**；整个 40+ 实验矩阵约 4 分钟。
第一轮的"数据瓶颈（终端只有 5 周历史）"**已解决** —— 见 §1.5。

---

## 1. 环境事实

| 项 | 值 |
|---|---|
| 终端 | `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe` |
| 编译器 | `C:\Program Files\MetaTrader 5 EXNESS\MetaEditor64.exe` |
| 独立测试器 | `C:\Program Files\MetaTrader 5 EXNESS\metatester64.exe` |
| 数据目录 | `C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\` |
| 版本 | build 6184（服务端 build 6140） |
| 券商 | Exness Technologies Ltd · 服务器 `Exness-MT5Trial5` |
| 账户 | `277335900` · **USD** · 杠杆 1:200 · 类型=0（demo，hedging） |
| 账户余额 | **0.00**（demo 空账户；回测入金由配置单独指定，不影响） |
| 终端 MCP | 启动时有 `MCP started on 127.0.0.1:22346`（build 6184 自带） |
| 测试器代理日志 | `C:\Users\UIC\AppData\Roaming\MetaQuotes\Tester\53785E099C927DB68A545C249CDBCE06\Agent-127.0.0.1-3000\logs\YYYYMMDD.log`（**EA 的 `Print()` 在这里**） |
| 脚本日志 | `<数据目录>\MQL5\logs\YYYYMMDD.log`（**脚本的 `Print()` 在这里**，不在终端 logs 里） |
| 优化项 / 审核输出 | `<数据目录>\MQL5\Files\` 或 `...\MetaQuotes\Terminal\Common\Files\`（EA 的 `InpAuditUseCommonFile=true` 时） |

### 1.5 ★自定义品种：解决历史不足（第二轮新增，已验证）

**问题**：终端自带历史只有 XAUUSDm 5 周 / BTCUSDm 1 周 / USDJPYm 2 周。旧项目有 42 个月黄金 M1。

**解法**：把旧项目的 M1 CSV 导入成 MT5 **自定义品种**。

```
步骤 1（Python）: mql5\dshtools\build_import_csv.py
    旧量化策略\31代数据\eva_data\eva_data\XAUUSDm\m1\*.csv  (42 个月)
    → 合成一个制表符分隔文件 → <数据目录>\MQL5\Files\dshtools\XAUUSD_HIST_M1.csv
      列: datetime \t open \t high \t low \t close \t tick_volume \t spread(价格单位)
      ★ 必须用 time_iso 列，不要用 time（Unix 秒）——否则得到 1970 年
    实测: 1229522 行, 76.8 MB, 2023.01.02 23:01 ~ 2026.06.30 23:59, 价格 1804~5595

步骤 2（MQL5）: mql5\dshtools\dsh_MakeCustomSymbol.mq5
    CustomSymbolCreate + CustomRatesUpdate 分批灌入（批大小 20000）
    → 自定义品种 XAUUSD_HIST

步骤 3（验证）: mql5\dshtools\dsh_TesterProbe.mq5
    在测试器里打印实际读到的第一根 bar → 一锤定音确认数据真的可用
    实测: FromDate=2023.01.05 → bar#1 time=2023.01.05 00:00 close=1854.794 ✅
    实测: M5/M15/H1/D1 从 2023.01.02 起完整（246461 / 82216 / 20576 / 1084 根）
```

#### ★★这一步踩了两个大坑（都会导致"0 成交"，务必记住）

| # | 坑 | 现象 | 正确做法 |
|---|---|---|---|
| 1 | **`SYMBOL_VOLUME_MIN` 写不进去** | 读回恒 `0.0000` | **必须在 `SymbolSelect(sym, true)` 之后写**。实测矩阵：create+set(未select)→0；加 VOLUME_LIMIT→0；**select(true) 之后再 set→0.01 ✅**；完整属性后 set(未select)→0。另外 **不要同时设 `SYMBOL_VOLUME_LIMIT`** |
| 2 | **保证金口径错 → 每单都被拒** | `calculated account state: Margin: 1912.88, FreeMargin: -1412.88` → `not enough money`，**一个月 0 笔成交** | 第一版用 `SYMBOL_CALC_MODE_CFD`，测试器算 0.01 手按金 = 合约量×价格 = **$1912**；真实 XAUUSDm 只要 **$2.19**（= 100×0.01×4385/200）。**必须用 `SYMBOL_CALC_MODE_FOREX`**（按金 = 合约量/杠杆） |

#### 自定义品种的最终规格（已核对）

| 属性 | 值 | 说明 |
|---|---|---|
| digits / point | 3 / 0.001 | 同 XAUUSDm |
| contract_size | 100 | 同 XAUUSDm（0.01 手 = 1 oz → **$1 波动 = $1**） |
| volume_min / step / max | 0.01 / 0.01 / 200 | 同 XAUUSDm |
| **calc_mode** | **`SYMBOL_CALC_MODE_FOREX`(1)** | ★见上面坑 2 |
| tick_size | 0.001 | |
| **tick_value** | **400.0**（= 参考价 4000 × 100 × 0.001） | ⚠️ 见下方说明 |
| currency_base / profit | USD / USD | |
| spread | 200 点固定（`SPREAD_FLOAT=false`） | 历史中位；**当前实盘是 260 点** |
| swap | 关闭 | 先不引入第二个变量 |
| Model | **只能用 `Model=2`（1 分钟 OHLC）** | 自定义品种没有真实 tick |

> ⚠️ **tick_value 的取舍必须知道**：真实品种的 tick_value 随现价变化（XAUUSDm 在 4385 时 ≈ 0.4385），但自定义品种只能存**一个常量**。42 个月金价 1804→5595（3.1 倍），只能选一个口径。
> EA 里唯一用到它的是末单止损换算 `loss_dist = InpLastOrderLossPerLot × tick_size / tick_value`。
> **本项目选按参考价 4000 校准 → tick_value = 400.0**，让"每手 $800 亏损"折算约 4.8% 价格（= 旧项目设计意图），且与网格距本身的 `price/InpRefPrice` 缩放自洽。

---

## 2. 编译 EA（已验证）

```powershell
# 把 .mq5 放进 MQL5\Experts\<子目录>\ 然后：
MetaEditor64.exe /compile:"<绝对路径>.mq5" /log:"<日志路径>.log"
```
- **必须用 `Start-Process -Wait`**：直接 `& MetaEditor64.exe /compile:...` 在 PowerShell 里会立刻返回、日志还没写出来。
- 退出码无意义（实测成功也返回 1），**必须读 log**。
- log 是 **UTF-16LE**：`Get-Content $log -Encoding Unicode`。
- 成功标志：`Result: 0 errors, 0 warnings, N ms elapsed, cpu='X64 Regular'`
- **源文件必须是 UTF-8 with BOM**（否则中文注释会乱码）。旧项目的 eva028 正好是 BOM，直接可用。

**实测**：eva028（4640 行）→ `0 errors, 0 warnings`，生成 `176950` 字节 `.ex5`。
→ **这解决了旧项目 37 代从未验证过编译的悬案，代码是干净的。**

---

## 3. 无头启动 + 配置文件（已验证）

**必须用配置文件**（`/portable` 单独用不起作用）。

```powershell
terminal64.exe /config:"<绝对路径>\xxx.ini"
```

### 3.1 跑脚本（探针用）

```ini
[Common]
Login=277335900
Server=Exness-MT5Trial5
KeepPrivate=1
NewsEnable=0
[StartUp]
Symbol=XAUUSDm
Period=M1
Script=dshtools\dsh_ProbeSpecs
```
→ 日志确认：`script dsh_ProbeSpecs (XAUUSDm,M1) loaded successfully` ✅

### 3.2 跑回测（★含 TesterInputs 注入 —— 这是自动化的关键）

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
Expert=<相对 MQL5\Experts 的路径，不带 .ex5>
Symbol=XAUUSD_HIST
Period=M1
Model=2              ; 0/1=真实tick；2=1分钟OHLC（自定义品种只能用 2）
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
ShutdownTerminal=1   ; 跑完自动退出，适合自动化
[TesterInputs]       ; ★★逐项覆盖 EA 的 input，不需要人去点 "Load .set"
InpLotSize=0.01
InpTrendBreakoutBars=30
InpRunTag=my_experiment
...
```

**关键坑**：
1. `Expert=` 写 **相对路径且不带扩展名**。写 `Experts\Examples\MACD\ExpertMACD.ex5` 会报 `EX5 not found`。
2. 终端进程**不会自己退出**，除非 `ShutdownTerminal=1`；否则要手动 kill。
3. 跑完终端退出码 `0` = 正常；`-1000012355` = 测试器未启动（通常是 Expert 路径错）。
4. 回测日志有三处（**别找错地方**）：
   - 终端日志 `<数据目录>\logs\YYYYMMDD.log`（只有启动/网络/Tester 框架信息）
   - **EA 的 `Print()`** → `%APPDATA%\MetaQuotes\Tester\...\Agent-127.0.0.1-3000\logs\YYYYMMDD.log`
   - **脚本的 `Print()`** → `<数据目录>\MQL5\logs\YYYYMMDD.log`（**注意：脚本不在上面那个 agent 日志里**）
   - ⚠️ 这些日志是**累积的**，一次会话里跑多个实验全部追加到同一文件 —— 分析时要用时间戳分块。
5. **HTML 报告是 UTF-16LE 编码**（带 BOM），直接按 UTF-8 读会得到 0 个 `<td>`。解析时必须先试 `utf-16`。
6. **报告里 `Expected Payoff` 等字段名容易和自定义列名撞车** —— 我第一次写解析器时把实验名 `exp` 覆盖成了 `Expected Payoff=0.56`。字段短名要避免撞车。
7. 报告的键值结构是 `<td colspan="3">Key:</td><td><b>Value</b></td>` —— 键和值**不一定相邻**，要用"键之后第一个非键 cell"来取值。

---

## 3.3 ★实验编排器（`run\mt5exp.py`，第二轮新增）

```powershell
cd "D:\desktop\新量化策略\deepseek数据保存\run"
python mt5exp.py --list                            # 看全部实验定义
python mt5exp.py --run base_locked base_locked_valid
python mt5exp.py --group sens                      # 按组跑
python analyze_runs.py base_locked base_locked_valid   # 出对比表 + exit_reason 归因
```

它做的事：
1. 解析旧项目 `.set`（UTF-16LE，`name=value||start||step||stop||Y/N`）→ 取 `value` 段
2. 套上 **`LOCKED_BASE` 锁定基座**（铁律二：8 个精度参数永不进优化空间）
3. 叠加**单个**覆盖项 → 强制单变量
4. 生成含 `[TesterInputs]` 的 ini，无头启动，等它退出（约 6 秒/2 年）
5. 自动回收 `Common\Files\eva_audit\<run_id>\` 的审计 CSV + HTML 报告 + 终端日志尾 → `run\<exp_id>\`

**性能实测**：2 年（699566 根 M1）单次约 **5.5~6.6 秒**。

---

## 4. ~~★真正的瓶颈：行情历史严重不足~~ → ✅ 已解决（见 §1.5）

**第一轮的实测（保留作对照）**：

| 品种 | M1 根数 | 历史起点 | 说明 |
|---|---:|---|---|
| **XAUUSDm** | 38,965 | **2026-08-03** | 只有约 5 周 |
| **BTCUSDm** | 10,914 | **2026-09-03** | 只有约 1 周 |
| **USDJPYm** | 16,610 | **2026-08-26** | 只有约 2 周 |
| EURUSDm | 18,070 | 2026-08-25 | 参考 |

**对比旧项目**：它有 **42 个月**（2023-01 ~ 2026-06，122 万根）黄金 M1。

**第二轮已解决（黄金）**：用 §1.5 的自定义品种方案，把 42 个月真实 M1 导入，**测试器实测能读到 2023.01.05 的行情**。
（终端启动时日志里还有一行 `HistoryCenter delete old files ... last access time 2023.06.08` —— 说明老历史文件被按访问时间清掉了，所以必须自己导入。）

**⚠️ 仍然未解决：BTCUSD / USDJPY**。这两个品种旧项目**没有任何历史文件**，终端自带只有 1~2 周。
→ 这是接下来做第二品种的硬门槛（见 `outline\改进大纲_v2.md` 阶段 C）。


### 解决路径（第一轮的评估，第二轮已按方案 1 落地）

1. **★ 把旧项目的 M1 CSV 导入为 MT5 自定义品种** ← **第二轮已实现并验证，见 §1.5。**
   注意：自定义品种只有 M1 bar、无 tick → 只能用 `Model=2`（1 分钟 OHLC），点差需显式设定。
   **这是"用几何/机制验证"，不是"用真实 tick 验证"，必须在结论里注明。**
2. **让终端重新下载更长历史**：Exness 对 XAUUSDm 的真实 tick 历史通常只有近几年，**实测无效**（终端只保留你访问过的区间）。
3. **换数据源**（Dukascopy 等）：旧项目明确否决过 —— 不同源的 tick_volume 语义不同、点差与实盘脱节。
4. **接受"只有近 5 周"**：能验证链路，不能验证策略。

---

## 5. 实测回测结果

### 5.1 第一轮：eva028 在真实 XAUUSDm 上跑 1 个月（2026-08-05 ~ 2026-09-05，入金 $500，0.01 手）

| 指标 | 值 |
|---|---|
| 最终余额 | **436.16 USD** |
| 净利 | **−63.84 USD**（−12.8%） |
| 最大回撤（官方 tick 口径） | **15.93%** |
| **月均交易数** | **122.2**（评分区间是 8~45） |
| **阶段1 统计** | `basket_stop=4  daily_stop=6  equity_kill=1` |
| 收到 tick 数 | 126,264 |

**诚实边界**：只有 1 个月、31566 根 M1 —— 样本量不足以下任何结论；且在 2026-09-04 被永久锁提前终止。

### 5.2 ★第二轮：eva028 在 `XAUUSD_HIST`（42 个月真实历史）上跑 60+ 次

| 配置 | 区间 | 净利 | PF | 笔数 | 权益回撤 | 净利/回撤 |
|---|---|---:|---:|---:|---:|---:|
| `stage1_full` 原样 | 训练 2023-2024 | +272.60 | 1.32 | 484（网格 0） | 11.28% | 3.94 |
| `stage1_full` 原样 | **验证 2025-2026** | **−44.12** | **0.58** | 45 | 15.15% | −0.54 |
| **锁定精度参数** | 训练 2023-2024 | +76.56 | 1.34 | 102 | 10.94% | 1.26 |
| **锁定精度参数** | **验证 2025-2026** | **+242.89** | **1.67** | 103 | 11.04% | **2.73** |

**核心发现**（详细见 `outline\改进大纲_v2.md`）：
1. **网格在 `stage1_full` 下 2 年 0 成交** —— 优化器把 `InpGridZ` 从 7000 抬到 20000（上边界），网格距 $20~25，在 60 分钟基线上几乎永不触发。
2. **网格就算调回来也不赚钱** —— 纯网格 6 个间距档全部 −72 ~ +43，**单均毛利润 $0.15 < 往返点差 $0.40**。
3. **锁定 8 个被优化器架空的精度参数后，样本外从 −44 变成 +243。** 训练集数字越高，样本外越差。
4. **风控层是哑的** —— 永久锁 15/25/40%/关、日损开/关，结果完全相同（回撤只 10.9%，从未触发）。
5. **牛市 beta 已排除** —— 验证期全关策略 = 0 笔、0 盈亏。

---

## 6. 输出文件位置

| 内容 | 路径 |
|---|---|
| EA（已编译） | `%APPDATA%\...\MQL5\Experts\eva028\eva028_*.mq5/.ex5` |
| **自定义品种历史库** | `%APPDATA%\...\bases\Custom\history\XAUUSD_HIST\`（2023~2026 的 .hcc + 各周期 cache） |
| 导入源 CSV（76.8 MB） | `%APPDATA%\...\MQL5\Files\dshtools\XAUUSD_HIST_M1.csv` |
| 探针/构建脚本（已编译） | `%APPDATA%\...\MQL5\Scripts\dshtools\dsh_*.mq5/.ex5` |
| 探针输出 / 规格 JSON | `%APPDATA%\...\MQL5\Files\dshtools\specs.json`、`custom_symbol_report.json`、`verify_custom.json` |
| 编译日志 | `deepseek数据保存\analysis\out\compile_*.log` |
| 启动/回测配置 | `deepseek数据保存\mql5\config\*.ini`（`run_*.ini` 由 mt5exp.py 自动生成） |
| MQL5 源码（我的副本） | `deepseek数据保存\mql5\dshtools\` |
| 实验编排与结果 | `deepseek数据保存\run\`（`mt5exp.py`、`parse_report.py`、`analyze_runs.py`、`<exp_id>\`） |
| 审计 CSV（trade_events） | `...\MetaQuotes\Terminal\Common\Files\eva_audit\<run_id>\` |
| 测试器代理日志（含 EA Print） | `C:\Users\UIC\AppData\Roaming\MetaQuotes\Tester\53785E099C927DB68A545C249CDBCE06\Agent-127.0.0.1-3000\logs\` |
| 脚本 Print 日志 | `%APPDATA%\...\MQL5\logs\YYYYMMDD.log` |


---

## 7. 我的操作边界（重要，务必遵守）

- ✅ **我可以做**：编译、无头回测、优化、读日志/报告、写 EA 源码、建自定义品种、导出数据到我的工作区。
- ✅ 回测配置里我始终设 `AllowLiveTrading=0`。所有回测都在策略测试器里跑，与真实账户隔离。
- ⛔ **我不做（除非你明确授权）**：**真实账户**下单、改动你真实账户的交易设置、在实盘终端上启动带自动交易的 EA。
- ⚠️ 我会修改 MT5 的 `MQL5\Experts`、`MQL5\Scripts`、`MQL5\Files`、`bases\Custom` 下的**我自己的文件**；不会碰你原有的 EA / 指标 / 模板。
- ⚠️ 我建的**自定义品种 `XAUUSD_HIST`** 只存在于历史库（`bases\Custom\`），**不影响你的真实品种，也不会出现在下单列表之外的地方**。
- ⚠️ 每次启动终端我都会记录，**跑完会关闭进程**（我用的 ini 都带 `ShutdownTerminal=1`；偶发不退出时我会 `Stop-Process`）。
  启动前若发现已有 `terminal64` 在跑，我会先判断那是不是**你自己开着看盘**的 —— 必要时我会问一句再动。

### 7.1 你希望我"自己操作 MT5"时的现状

| 环节 | 状态 |
|---|---|
| 读行情 / 历史 | ✅ 全自动（含 42 个月自定义历史） |
| 编译 EA | ✅ 全自动 |
| 策略测试器回测 / 优化 | ✅ 全自动，2 年约 6 秒 |
| 读报告 / 审计 CSV / 日志 | ✅ 全自动 |
| **demo 账户真实下单验证**（滑点/成交/点差） | ⏳ **需要你明确授权**（阶段 D） |

---

*本文档随工具链演进更新。配套：`MEMORY.md`（工作记忆）、`outline\改进大纲_v2.md`（★研究主线，最新）。*
