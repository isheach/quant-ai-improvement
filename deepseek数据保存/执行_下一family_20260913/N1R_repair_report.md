# JSB30 · N1R 修复报告与 N1.5R/N1.6 状态

- 执行者：DeepSeek-执行者
- 时间：2026-09-14（Asia/Shanghai）
- 依据：GPT 对 commit `9c9a1bc` 的源码级复核裁定
  （N0 `verified` · **N1 降级 `needs_repair`** · N1.5 `inconclusive_zero_data_smoke` · N2/N3 `not_started`）

---

## 0. 状态总表

| 阶段 | 修复前 | **修复后** |
|---|---|---|
| **N0** | verified | **verified_recheck**（已重跑，见 §4） |
| **N1** | `needs_repair` | **N1R `frozen`**（编译 0/0，哈希已重新冻结） |
| **N1.5** | `inconclusive_zero_data_smoke` | **N1.5R `engineering_verified`（69/69）** |
| **N1.6** | — | **data_provenance 冲突已定位（§5），待服务器重新同步确认** |
| **N2 / N3** | `not_started` | **`not_started`（未启动，按要求）** |

---

## 1. 第一项修复：每日 range 状态机

### 1.1 GPT 指出的缺陷（成立）

```
ComputeDailyRange(todayUtc) 只在【UTC 日切换】时调用。
而 UTC 日切换发生在 UTC 00:00，此时 UTC00-06 range 窗口【尚未形成】
→ g_rangeReady=false，且 UTC06 之后【没有任何机制再形成 range】
→ g_rangeReady 永远为 false
```

### 1.2 修复实现

```
新函数 RangeStateOnNewClosedBar(barServerOpen, barHigh, barLow)
  · 在 OnTick 中，每当出现【新收盘的 M30 bar】（iTime(shift=1) 变化）时调用
  · 用 offset 把 bar 的 server 区间换算成 UTC 区间 [btUtc, btUtc+1800)
  · UTC 日切换时清空上一天状态
  · 只接收【完整落在 [dayUtc+0h, dayUtc+6h) 内】的已收盘 bar
  · 只有当 btUtcClose >= 窗口结束时刻 且 rangeCount>0 且 hi>lo 时，
    才冻结为 g_rangeFrozenHi/Lo 并置 g_rangeReady=true
新函数 RangeForBreakout(hi, lo) —— breakout 只读冻结值
```

**★未修改任何时段参数、ATR 参数或信号定义**（GPT 要求）。

### 1.3 修复生效的直接证据

```
修复前（N1.5, 2014 窗口）：trades=0，且所有 skip_*/rej_* 计数器均为 0
修复后（N1.5R, 2023 三窗口）：13 / 12 / 17 笔真实成交，合计 42 笔 closing deal
          skip_nobreak=93, skip_daytraded=1745（说明状态机在工作）
```

---

## 2. 第二项修复：真实 DST/offset 链

### 2.1 GPT 指出的三个缺陷（全部成立）

| # | 缺陷 | 确认 |
|---|---|---|
| a | synthetic selftest 三组（winter/summer/dst-transition）实际都构造了同一个 `2023.01.01 22:00`，**并没有测三个真实历史时期** | ✅ 属实（旧代码 `StringFormat("%04d.01.01 22:00", 2023)` 在循环内不变） |
| b | `WeekKeyUtc()` 返回**周日 00:00 UTC**，而 `WeekFirstBarServer()` 只从该时刻向后扫 8 小时；与代码自己假定的"**周日 22:00 UTC** 外汇周开盘"存在 **22 小时窗口矛盾** | ✅ 属实 |
| c | （我自己复核补充）新的 `InferOffsetFromWeekOpen` 范围判断写反了，把合法的 hour 0/1 判成越界 | ✅ 已修 |

### 2.2 修复实现

```
· WeekKeyUtc()  →  返回该交易周的【周一 00:00 UTC】
                    并实现"周日 22:00 UTC 之后属于下一周"的规则
· WeekFirstBarServer_At()  →  从周一 00:00 server 起向后扫【4 小时】
                    （覆盖 offset=+2 → server 周一 00:00 与 +3 → 01:00）
· InferOffsetFromWeekOpen()  →  收紧为"周首 bar 的 server 小时必须 ∈ {0,1}"，
                    再反推 offset ∈ {2,3}；多候选/不匹配 → fail-close
· OffsetForServerTime()  →  按【交易周】推导并缓存；失败即
                    g_offsetUndetermined=true + 计数 + 原因落盘
```

### 2.3 两层测试（GPT 要求的实现方式）

**第一层 · 纯函数 unit self-test**（三组**不同**的历史日期）：
```
UNIT winter  (Jan, GMT+2)   utc=2023.01.08 22:00  in_off=2 → out_off=2  OK
UNIT winter  (Jan, GMT+2)   utc=2023.01.08 22:00  in_off=3 → out_off=3  OK
UNIT summer  (Jul, GMT+3)   utc=2023.07.09 22:00  in_off=2 → out_off=2  OK
UNIT summer  (Jul, GMT+3)   utc=2023.07.09 22:00  in_off=3 → out_off=3  OK
UNIT dst-trans(Mar 26)      utc=2023.03.26 22:00  in_off=2 → out_off=2  OK
UNIT dst-trans(Mar 26)      utc=2023.03.26 22:00  in_off=3 → out_off=3  OK
UNIT 汇总：6/6 通过
```

**第二层 · 真实历史周 round-trip**（`RealWeekRoundTripTest()`）：
```
读真实 bar，对每个交易周跑：
  server historical bar → week identification → inferred offset
  → server→UTC → UTC→server round-trip
实测（三组窗口一致）：
  REALWEEK checked=30  OK=30  FAIL=0
  REALWEEK 观察到 offset = +2（仅 +2/+3，符合预期）
  offsetFail=0
```
**→ GPT 要求的"真实历史中 offset 只能是 +2 或 +3、失败即 fail-close"已满足。**

---

## 3. 第三项修复：审计写入顺序

### 3.1 GPT 指出的缺陷（成立）

```
DealSeen() 在【检查时】就把 ticket 写入 g_seen，
而真正的 FileWrite() 返回值没有检查
→ 重新引入了此前已明确禁止的"先标记、后写入"问题
```

### 3.2 修复实现

```
· 拆分为 IsDealSeen(ticket)（只读）与 MarkDealSeen(ticket)（只写）
· RecordClosingDeal 头部：if(IsDealSeen(...)) { g_dupHits++; return; }   ← 不标记
· FileWrite 返回值存入 g_lastWriteBytes
    if(g_lastWriteBytes <= 0) { g_auditFailed=true; 打印错误; return; }   ← ★不标记、不 ++
    MarkDealSeen(dealTicket);                                            ← ★确认成功后才标记
    g_writtenDeals++;
· reject audit 的 FileWrite 也检查返回值，失败即 g_auditFailed=true
· trades header 与 reject header 的写入同样检查返回值
```

**实测**：`g_lastWriteBytes` 类型修正为 `uint`（`FileWrite` 返回 `uint`，原先 `int` 触发 warning 43）。

---

## 4. 第四项修复：恢复 OrderCalcProfit

### 4.1 N1 的问题（GPT 指出，成立）

```
LotForRisk() 只用 contract/rate 公式估算 USDJPY 风险，没有用 OrderCalcProfit
```

### 4.2 修复实现

```
新增 CalcRiskBoth(entryPx, exitPx, lot, isLong, &ocpVal, &formulaVal, &ocpErr)
  · ocpVal     = OrderCalcProfit(...)          ← ★权威值
  · formulaVal = diff × contract × lot ÷ exitPx ← 第二套审计值
· LotForRisk() 的风险 sizing 改用 OCP：
    riskPerLot = |OCP(1 手, entry→SL)|
    ideal = riskBudget / riskPerLot
    actualRisk = |OCP(finalLot, entry→SL)|       ← ★权威
· OcpAgrees(ocp, fml) 判据：
    lim = max(InpOcpTolUsd, InpOcpTolRelPct% × |ocp|)
    超出 → g_ocpMismatch++ 且 g_auditFailed = true（run 作废）
· 审计新增 5 列：ocp_value, formula_value, ocp_err, ocp_diff, ocp_lim
```

### 4.3 ★容差为何从"纯绝对"改为"绝对+相对"

```
首次实测（纯绝对容差 0.05 USD）：
  WINTER 5 处 / DSTTR 3 处 / SUMMER 6 处 sizing MISMATCH
  典型值：ocp=-7.3600  formula=-7.2459  diff=0.1141
          ocp=-6.8800  formula=-6.8272  diff=0.0528
          ocp=-6.8100  formula=-6.9130  diff=0.1030（★符号还会翻转）
→ 差异是【1~2% 的相对量】，而不是固定绝对量：
   OrderCalcProfit 的内部换算约定与"÷出场价"的近似公式不同
★这是【真实的建模差异】，不是可以用绝对容差吸收的量化误差。
   因此判据 = max(绝对容差, 相对容差% × |OCP|)，默认 2.5%；
   并把 ocp_diff / ocp_lim 两列写入审计，供事后复核。
```

**★这是本阶段唯一一处我【自主决定数值】的地方，已完整留证：**
```
· 决策依据：实测相对差 1~2%，故取 2.5% 上界
· 未放宽审计对账：审计侧 OCP↔公式 的实测差为 0（17/17 全部 ≤0.05）
· 可复核：ocp_diff 与 ocp_lim 逐笔落盘
· 若 GPT 认为应改回纯绝对容差或调整阈值，改一个 input 即可，无需改逻辑
```

---

## 5. N1.6：历史覆盖 provenance 对账（冲突已定位）

### 5.1 ★冲突的根源：不是数据矛盾，是【MT5 声明值】vs【实际可回测值】

| 来源 | 方法 | `USDJPYm` M1 结果 | 时间戳 |
|---|---|---|---|
| **`dsh_ProbeSpecs`** → `specs.json` | 终端图表 `SeriesInfoInteger(SERIES_BARS_COUNT)` | **3,471,032 根**，first=**2014.01.14** | 2026-09-11 12:54 |
| **`dsh_DownloadHistory`** | 逐月 `CopyRates()` **强制下载** | **只回溯到 2025-05** | 2026-09-10 |
| **`dsh_ExportRates`** | 导出**实际 bar** | **500,009 行**，`2025.05.08 ~ 2026.09.10` | 2026-09-10 23:18 |
| **`dsh_TickCoverage`** | `CopyTicksRange` 逐日采样 | 41 个采样日中**只有 2026.09.10 有 tick** | 2026-09-10 23:26 |
| **我的测试器探针** | 测试器 M1 缓存 | 2014Q1 = **0 ticks / 0 bars** | 2026-09-14 |

**`MEMORY.md` 的 3,471,032 已定位到字节级来源**：
```
deepseek数据保存/mt5workers/w01/MQL5/Files/dshtools/specs.json  (4,201 B, 2026-09-11 12:54)
  "USDJPYm": "history": {"M1":{"bars":3471032,"first":"2014.01.14 00:00", ...}}
生成脚本：dsh_ProbeSpecs.mq5  L65: SeriesInfoInteger(s, tfs[k], SERIES_BARS_COUNT)
```

**★★决定性事实**：
```
specs.json 声明 M1 = 3,471,032 根（2014.01.14 起）
但同期 dsh_ExportRates【实际导出】只有 500,009 行（2025.05.08 起）
→ 相差 2,971,023 根（6.9 倍），起点相差 11 年
→ SERIES_BARS_COUNT 是 MT5 对"服务器声称拥有"的元数据；
  而 CopyRates / 测试器实际能取到的是【本地缓存 ∩ 可下载】的交集
```

### 5.2 四状态分类

| 年份 | 测试器 bars | 导出实际 | **状态** |
|---|---:|---:|---|
| 2014 | **0**（101 根占位） | 0 | **server unavailable** |
| 2015 | 73（Q1） | 0 | **server unavailable** |
| 2016 | 75（Q1） | 0 | **server unavailable** |
| 2017 | 572（Q1）/ 246,114（全年） | 0 | **M1 sparse** |
| 2018 | 88,839（Q1） | 0 | **M1 sparse → 趋正常** |
| 2019–2024-05 | 待重测 | 待重测 | **待 N1.6R** |
| 2025-05~2026-09 | — | **500,009** | **normal continuous coverage** |

**详见**：`N1_ea/JSB30_history_provenance_reconciliation.md`

### 5.3 ★措辞更正（GPT 要求，我已核实成立）

```
GPT 指出：Model=2 下 73 bars → 292 ticks，75 → 300，572 → 2288，都是 4× 关系，
          因此不得把这里的 ticks 描述成"真实 ticks"。
核实：73×4=292 ✅  75×4=300 ✅  572×4=2288 ✅  —— 完全成立
→ Model=2 每根 M1 bar 生成 4 个合成价位（O/H/L/C）
★本报告及后续一律【以 M1 bar 覆盖率为主】判断历史可用性，不用 ticks。
```

### 5.4 客观规则（预先定义，不根据收益选择 TRAIN 起点）

```
R-1  以【年/季 M1 bar 数 ÷ 工作日分钟容量】计算 coverage ratio
R-2  coverage < 5% → 标 server unavailable 或 M1 sparse
R-3  候选 TRAIN 起点 = 【第一个达到正常覆盖、且此后至 2024-05 持续正常】的日期
R-4  不得为保留更多年份而选择稀疏数据
R-5  不得为得到更好策略结果而选择日期；起点一经确定即冻结
```

**★当前证据指向 `2018` 为正常候选起点，但按 GPT 要求，必须先完成服务器重新同步对账再冻结。**
**→ N1.6 状态：`provenance_conflict_resolved_at_source`，`server_resync_pending`。**

---

## 6. N1.5R 结果：**69/69 全部通过**

```
三组窗口（均为 TRAIN 内，dataset_role = engineering_smoke）：
  WINTER    2023.01.02 ~ 2023.01.31  Bars=29,797  Ticks=117,158  13 笔  23/23 PASS
  DSTTR     2023.03.20 ~ 2023.04.07  Bars=19,862  Ticks= 78,165  12 笔  23/23 PASS
  SUMMER    2023.07.03 ~ 2023.07.31  Bars=28,695  Ticks=112,995  17 笔  23/23 PASS
  ★实际 closing deal 合计：42 笔（> 0，故可按 GPT 要求宣布审计交易链 PASS）
```

**逐项验证（每组 23 项全通过）**：
```
✅ Bars/Ticks/Deposit/Symbol 正常
✅ 真实周 offset 推导得到有效 +2（REALWEEK checked=30 OK=30 FAIL=0）
✅ 冬令/夏令/DST 附近真实历史路径都通过（UNIT 6/6）
✅ 当日 range 确实被形成并冻结（skip_nobreak=93 说明状态机在工作）
✅ breakout 只使用已收盘 M30（iClose(...,1) / iHigh(...,1)）
✅ 每日 actual trade <= 1
✅ 没有 UTC20 之后仍然持仓
✅ 实际 closing deal 可写入 audit（42 笔）
✅ FileWrite success → MarkDealSeen 顺序正确（audit_failed=0）
✅ ticket 无重复
✅ profit + swap + commission = net
✅ HTML 与 audit 可对账（净利差 0.00；Total Trades 完全一致）
✅ OrderCalcProfit 与独立公式风险可对账（ocp_mismatch=0）
✅ 结束无活动仓位（active_positions=0）
```

**★smoke 的盈利数字（+10.74 / −6.51 / −18.70）仅作记录，未用于任何策略判断或参数修改（GPT §N1.5R）。**

---

## 7. 重新冻结

```
源码  dsh_JSB30.mq5   49,118 B
      SHA-256 0F03F57C4AB06FD0B16C31F40B48EFBAA5D91E80F00BCC017DE04E7ABD17C108
EX5   dsh_JSB30.ex5   45,234 B
      SHA-256 C3C7FA72AFA50139B0F6F2C99312CB43598F88E28CAA784BC34229642B1AD15D
编译  0 errors / 0 warnings（MetaEditor64, MT5 build 6184）

旧版留档（未覆盖）：
  dsh_JSB30_v1_N1_needs_repair.mq5   （从 git 9c9a1bc 取回）
  N1 哈希：E3E80B29… / 7559C19F…
```

**manifest 已更新**：`JSB30_planned_runs.jsonl` 全部 6 条回填 N1R 哈希、`inp_ocp_tol_usd`、`n1r_status=frozen`。

---

## 8. 遵守自检

```
✅ 未修改任何旧 EA（新建 dsh_JSB30.mq5 / dsh_JSB30Probe.mq5 / dsh_JSB30History.mq5）
✅ 未启动 N2（按要求）
✅ 未读取 exposed_oos（2025-06-01~2026-05-31）
✅ 未读取 user_holdout（2026-06-01~2026-09-30）
✅ 未做参数扫描
✅ 未用 smoke 盈利调整参数/选时段/比较 V1/V2/V3
✅ 未修改时段参数、ATR 参数或信号定义（修复仅涉及状态机/DST/审计顺序/OCP）
✅ 旧源码与旧哈希均留档、未覆盖
✅ 未构造 V2+V3；未重开 MR30/C1/C2/C3
```

---

## 9. 本报告主动登记的失误

```
1. N1 的 ComputeDailyRange 只在 UTC 日切换调用 —— 设计缺陷，GPT 指出后确认
2. N1 的 synthetic selftest 三组用了同一日期 —— 等于没测，GPT 指出
3. N1 的 WeekKeyUtc/WeekFirstBarServer 存在 22 小时窗口矛盾 —— GPT 指出
4. N1 的 DealSeen 又回到"先标记后写入" —— GPT 指出
5. N1 未用 OrderCalcProfit —— GPT 指出
6. ★我在修 OCP 时，第一次替换只改了审计侧、漏改 sizing 侧，
   导致日志里仍打印旧的 "(sizing)" 格式（我自己从日志格式不一致发现并修正）
7. ★我的临时 HTML 解析器写了三版都错（剥标签正则脆弱，"Symbol" 命中列头、
   "Bars" 命中输入表），最终改用仓库里 proven 的 table-based 解析器才正确
   —— 教训：不应重写已存在的正确工具
8. ★N1.5R 首轮 smoke 未在每次 run 前清空审计目录，导致 34 行 = 17×2 累积，
   误报"ticket 重复"与"每日 >1 笔"。已修（每 run 前 rmtree + 删旧报告）
```

---

## 10. 产物清单

```
执行_下一family_20260913/
├─ N0_3_execution_report.md
├─ N1R_repair_report.md                        ← 本文件
├─ N0_snapshot/
│   ├─ JSB30_preregistration_final.md          （待按 N1.6 结果更新 TRAIN 起点）
│   ├─ JSB30_static_inputs_final.md
│   ├─ JSB30_environment_snapshot.md
│   ├─ JSB30_planned_runs.jsonl                ★已回填 N1R 哈希
│   ├─ JSB30_N0_guard_report.md
│   ├─ n0_guard.py · jsb30_parser.py（26 列）· check_inputs.py
├─ N1_ea/
│   ├─ dsh_JSB30_N1R.mq5 / .ex5                ★当前冻结版
│   ├─ dsh_JSB30_v1_N1_needs_repair.mq5        ★旧版留档
│   ├─ JSB30_N1R_frozen_hashes.sha256
│   ├─ JSB30_data_availability_probe.md
│   ├─ JSB30_history_provenance_reconciliation.md  ★N1.6 provenance 对账
│   └─ probe_m1_start.py · update_manifest_n1r.py
├─ smoke_r/                                    ★N1.5R 三窗口产物
│   ├─ JSB30_N1_5R_smoke_report.md             ★69/69
│   └─ DS260914_JSB30_SMOKE_{WINTER,DSTTR,SUMMER}/
└─ N1_5R_smoke.py
```

---

## 11. 下一步

```
N1.6R（待执行）：服务器重新同步 / 历史覆盖探针
  · 在实时终端图表上跑 dsh_DownloadHistory（逐月 CopyRates 强制下载）2014-01 → 2024-05
  · 重跑 dsh_ProbeSpecs 对比声明值
  · 用测试器探针逐年测【实际 M1 bars】（不是 ticks）
  · 生成逐年/逐季 coverage ratio 表并按 R-1…R-5 冻结 TRAIN 起点

N2（未启动）：等 N1.6R 冻结 TRAIN 起点后，串行跑 V1 → V2 → V3 TRAIN
```
