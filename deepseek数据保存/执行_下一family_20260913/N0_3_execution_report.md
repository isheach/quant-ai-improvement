# JSB30 · N0 → N1.5 执行报告与阻塞项

- 执行者：DeepSeek-执行者
- 时间：2026-09-14（Asia/Shanghai）
- Source of Truth：`公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md`
- **结论：N0 ✅ 通过（78/78）· N1 ✅ 通过（编译 0/0，哈希已冻结）· N1.5 ⚠️ 因【数据可用性】阻塞**

---

## 1. 阶段状态总表

| 阶段 | 状态 | 依据 |
|---|---|---|
| **N0** 只读快照与护栏 | ✅ **PASS 78/78** | `N0_snapshot/JSB30_N0_guard_report.md` |
| **N1** 新 EA 与静态审计 | ✅ **编译 0 errors / 0 warnings，哈希已冻结** | `N1_ea/JSB30_N1_frozen_hashes.sha256` |
| **N1.5** 最小工程 smoke | ⚠️ **工程链 17/22 通过；5 项失败全部源于【M1 数据不存在】** | `smoke/JSB30_N1_5_smoke_report.md` |
| **N2** 正式 TRAIN | ⛔ **未启动**（等 §5 裁定） | — |
| **N3** VALID | ⛔ 未启动 | — |

---

## 2. N0 产物（GPT §3 要求的 4 份）

| 文件 | 说明 |
|---|---|
| `no_snapshot/JSB30_preregistration_final.md` | **正式预注册**（GPT §2 逐字落实 + 两处关键修正） |
| `N0_snapshot/JSB30_static_inputs_final.md` | 静态输入表（33 个 input + 16 项闸门检查） |
| `N0_snapshot/JSB30_environment_snapshot.md` | 环境快照（终端/账户/品种规格/清理记录） |
| `N0_snapshot/JSB30_planned_runs.jsonl` | 6 条 run 登记（3 TRAIN `planned` + 3 VALID `planned_if_train_pass`） |
| `N0_snapshot/JSB30_N0_guard_report.md` | **护栏报告 78/78** |
| `N0_snapshot/n0_guard.py` | 护栏脚本（`--declared` / `--source` 两种权威源） |
| `N0_snapshot/jsb30_parser.py` | 下游解析器（**重复 header fail-close**） |

### 2.1 N0 关键检查结果（78/78 全通过）

```
✅ symbol = USDJPYm（白名单）
✅ TRAIN 2014-01-14 ~ 2024-05-31；VALID 2024-06-01 ~ 2025-05-31
✅ ★user_holdout（2026-06-01~09-30）无重叠
✅ ★exposed_oos（2025-06-01~2026-05-31）无重叠
✅ run_id 唯一（6 条）且与既有 674 个 tag 不冲突
✅ 报告名 / 审计目录均不复用
✅ 变体 V2 只改 range_end；V3 只改 TP；★无 V2+V3 组合版
✅ 冻结 input 清单 33 项在真实源码中全部存在（--source 校验）
✅ 无未登记 Inp 参数（未知 input fail-close）
✅ 无自建品种残留；symbols.custom.dat 不存在
✅ 所有 run 先登记（planned）后执行
```

---

## 3. N1 产物

### 3.1 新 EA

```
路径：deepseek数据保存/mql5/dshtools/dsh_JSB30.mq5   （34,860 字节）
★独立新文件；未修改任何旧 EA（旧 EA mtime 有前置记录）
```

**实现了 GPT §4 的全部要求**：

| 要求 | 落实 |
|---|---|
| UTC 定义、server 执行 | 所有时段以 UTC 常量声明，运行期按 offset 换算 |
| **按历史日期/交易周动态 offset** | `OffsetForServerTime()` 按周推导 + 缓存（`WeekOffset` 表） |
| **禁止整段固定 offset** | 每周独立推导；无全局常量 |
| 只允许 +2 / +3 | `InferOffsetFromWeekOpen()` 只接受 `[InpExpectedServerOffsetMin, Max]` |
| **fail-close** | 推导失败 / 多候选 / 超范围 → `g_offsetUndetermined` + 计数 + 原因落盘 |
| UTC 日切换不用 server midnight | `UtcDayOf()` 基于 UTC 时间戳 |
| 只用已收盘 M30 bar | `if(btUtc < wS \|\| btUtcClose > wE) continue;` + `iClose(...,1)` |
| 检查 `FileWrite` 成功后才登记 | `g_writtenDeals++` 在 `FileWrite` 之后；`g_auditFailed` 标记 |
| 19 个审计字段 | `deal_ticket … server_utc_offset`（21 列含 run_tag/symbol） |
| **header 唯一性自检** | `HeaderUnique()` 在 `OpenAudit()` 里对 trades 与 reject 两张表都跑 |
| 结束时无活动仓位 | `audit_selfcheck.csv` 的 `active_positions` 列 |
| 每个 UTC 日 <= 1 笔 | `g_dayTraded` 门（UTC 日切换时重置） |
| window_end 可追踪 | `CloseTrade("window_end")` 在 `utcMin >= 20*60` 触发 |

### 3.2 冻结哈希（GPT §4 要求）

```
源码  E3E80B296AC82B560C56C949D3DC3E3FEEF5511E33B27B58D3E8E36C71235A69
      dsh_JSB30.mq5   34,860 字节
EX5   7559C19F1FB87ED62C23EDBB30D7840A8BD11FC4E189F64E89A561C34905B45D
      dsh_JSB30.ex5   40,212 字节
编译  0 errors / 0 warnings（MetaEditor64, MT5 build 6184）
```
**★三个 TRAIN 将使用同一 EX5，仅预注册输入不同（GPT §4）。**
哈希已回填进 `JSB30_planned_runs.jsonl` 的全部 6 条记录。

### 3.3 重复 header bug 修复（GPT §1-Q4）

```
· JSB30 的 audit header 经 HeaderUnique() 自检 → 无重复
· 下游解析器 jsb30_parser.py 对重复 header【fail-close】
· 实测验证：对历史 R4 文件运行 →
    FAIL(duplicate-header): ★重复 header 列：['entry_time']
    退出码 1 ✅
· ★历史 R4 文件未修改、未重导（GPT Q4 明确要求）
```

---

## 4. N1.5 工程 smoke 结果

```
tag    : DS260914_JSB30_SMOKE_V1
窗口   : 2014.01.14 ~ 2014.02.14（TRAIN 内）
口径   : USDJPYm / 500 USD / Model=2 / ticks=0
EA     : 同一封存 EX5
```

### 4.1 工程链检查（17/22 通过）

| # | 检查项 | 结果 | 明细 |
|---|---|---|---|
| 1 | EA 加载（报告存在） | **PASS** | report 已生成 |
| 2 | **round-trip 自测执行** | **PASS** | 7 行 SELFTEST |
| 3 | **round-trip 全通过** | **PASS** | **6/6** |
| 4 | **offset 推导无失败** | **PASS** | `offsetFail=0` |
| 5 | **trades.csv header 唯一且列匹配** | **PASS** | **21 列** |
| 6 | **reject_audit.csv header 唯一且列匹配** | **PASS** | **15 列** |
| 7 | trades.csv 已写出 | **PASS** | 231 B（仅表头） |
| 8 | audit_selfcheck.csv 已写出 | **PASS** | 300 B |
| 9 | 每个 UTC 日 <= 1 笔 | **PASS** | 无违反 |
| 10 | hard-flat（出场 UTC < 20:00） | **PASS** | 无越界 |
| 11 | profit+swap+commission = net | **PASS** | 无不一致 |
| 12 | deal_ticket 唯一 | **PASS** | — |
| 13 | position/schema 字段齐备 | **PASS** | 无缺失 |
| 14 | 审计净利 == 报告净利 | **PASS** | 0.00 vs 0.00 |
| 15 | 结束时无活动仓位 | **PASS** | `active_positions=0` |
| 16 | `offset_undetermined = 0` | **PASS** | 值=0 |
| 17 | `audit_failed = 0` | **PASS** | 值=0 |

**★EA 内 round-trip 自测原始输出（三类周全覆盖）**：
```
SELFTEST winter          in_off=2 -> out_off=2 roundtrip=OK
SELFTEST winter          in_off=3 -> out_off=3 roundtrip=OK
SELFTEST summer          in_off=2 -> out_off=2 roundtrip=OK
SELFTEST summer          in_off=3 -> out_off=3 roundtrip=OK
SELFTEST dst-transition  in_off=2 -> out_off=2 roundtrip=OK
SELFTEST dst-transition  in_off=3 -> out_off=3 roundtrip=OK
SELFTEST 汇总：6/6 通过
```
**→ GPT §1-Q1 要求的「冬令周 / 夏令周 / DST 切换附近周」三类 round-trip 全部通过 ✅**

**★EA 初始化日志**：
```
init ok range=UTC00-06 breakout=UTC07-12 flat=UTC20 SL=1.00xATR TP=1.50R
        maxBars=16 risk=1.50% overshoot=off dynDST=on
=== END trades=0 win=0 written=0 dup=0 offsetFail=0
        rangeReadySkip=0 narrow=0 noBreak=0 dayTraded=0 badWin=0 rejRisk=0 rejOffset=0 ===
```

### 4.2 ⚠️ 5 项失败 —— 全部源于【M1 数据不存在】

| # | 失败项 | 值 |
|---|---|---|
| 1 | Bars > 0 | `Bars=`（空） |
| 2 | Ticks > 0 | `Ticks=None` |
| 3 | Initial Deposit = 500 | `dep=None` |
| 4 | Symbol = USDJPYm | 空 |
| 5 | trades 行数 > 0 | **0 笔** |

**★所有 `skip_*` 与 `rej_*` 计数器均为 0** → **EA 根本没收到任何 tick**，
不是守卫拦掉的，而是**测试器未执行**。

**★MT5 日志的直接证据**：
```
USDJPYm,M1: history cache allocated for 101 bars
            and contains 101 bars from 2014.01.14 00:00 to 2014.05.11 00:00
USDJPYm,M1: history begins from 2014.01.14 00:00
USDJPYm,M1: 0 ticks, 0 bars generated        ← ★测试器无法执行
```
**对照（可正常执行的窗口）**：
```
USDJPYm,M1: history cache ... 368172 bars from 2022.01.02 22:10 to 2023.01.01 23:59
USDJPYm,M1: 1445658 ticks, 368216 bars generated
```

---

## 5. ⛔ 阻塞项：`USDJPYm` 的 M1 真实可用起点远晚于 2014-01-14

### 5.1 客观探测结果（只读探针，逐窗口读 MT5 日志）

| 窗口 | 区间 | ticks | bars | 判定 |
|---|---|---:|---:|---|
| 2014Q1 | 2014.01.14~2014.03.31 | **0** | **0** | **仅 101 根占位 bar，0 ticks ❌** |
| 2015Q1 | 2015.01.05~2015.03.31 | 292 | 73 | 极稀疏 |
| 2016Q1 | 2016.01.04~2016.03.31 | 300 | 75 | 极稀疏 |
| 2017Q1 | 2017.01.03~2017.03.31 | 2,288 | 572 | 稀疏 |
| **2017 全年** | 2017.01.03~2017.12.29 | **983,079** | **246,114** | 可用但密度低 |
| 2018Q1 | 2018.01.02~2018.03.31 | 354,598 | 88,839 | 正常 |
| 2019Q1 | 2019.01.02~2019.03.31 | 362,146 | 90,906 | 正常 |

**每年 M1 缓存文件大小（终端侧）**：
```
2014 / 2015 / 2016 : 各 0.1 MB     ← ★几乎没有数据
2017 : 14.2 MB
2018-2025 : 各 21 MB
```

### 5.2 ★这解释了 3.3 年静默的真实原因

```
前一条日元线记录的「2014–2016 静默」，
其根因【不是】策略守卫、D1 过滤器或参数问题，
而是【USDJPYm 的 M1 历史在 2014–2016 基本不存在】。

实测铁证：
· 请求 2014.01.14 窗口 → M1 cache 只有 101 根占位 bar、0 ticks → 测试器无法执行
· 2015/2016 Q1 各仅 292 / 300 ticks（对比 2018 Q1 的 354,598）
```

### 5.3 对 JSB30 预注册的直接影响

```
预注册规定：TRAIN = 2014-01-14 ~ 2024-05-31
GPT 裁定 §1-Q3 同时规定：「若 MT5 实际首个有效 bar 稍晚，
                             以实际首 bar 为准并登记原因」

→ 本报告即该「实际首 bar」的实测依据。
→ ★但这不是「稍晚」：2014 完全无 M1，2015–2016 近乎无 M1，2017 稀疏。
   若强行以 2014-01-14 起跑，得到的将是一条【先有 3 年零成交、
   再有 1 年稀疏成交】的曲线 —— 它不是对策略的检验，而是对数据缺口的记录。
```

### 5.4 需要 GPT 裁定的一项范围问题

```
Q5（新）TRAIN 起点应取哪一个？
   A) 保持 2014-01-14，接受 2014–2016 的 0 成交（按预注册"独立诊断段"如实报告）
   B) 以【实测可执行起点】2017-01-03 为 TRAIN 起点，登记"数据可用性"原因
   C) 以【数据密度正常起点】2018-01-02 为 TRAIN 起点，登记原因
   D) 先补下载 USDJPYm 的 M1 历史（需 MT5 联网抓取），再按 A 执行

★我的技术建议：**D → 若不可行则 C**。
   理由：A/B 会把"数据缺口"混进策略评价（频率、覆盖率、逐年 PF 全部失真）；
         D 能得到真正的 2014 起数据；C 是在无法补数据时最接近"可检验"的选项。
★但我【不自行决定】—— 这是预注册范围，按裁定应由 GPT/用户定。
```

**★在裁定前我不启动 N2**（避免用一条掺了 3 年数据缺口的结果去评价策略）。

---

## 6. 遵守情况自检

```
✅ 未修改任何旧 EA（旧 EA mtime 有前置记录；新建 2 个独立文件）
✅ 未读取 exposed_oos（2025-06-01~2026-05-31）
✅ 未读取 user_holdout（2026-06-01~2026-09-30）
✅ 未做参数扫描
✅ 未用 smoke 盈利调整参数 / 选时段 / 比较 V1/V2/V3
✅ 未构造 V2+V3 组合版
✅ 未真钱下单
✅ 所有 run 先登记（planned）后执行
✅ 未重开 MR30 / C1 / C2 / C3
```

---

## 7. 产物清单

```
执行_下一family_20260913\
├─ N0_snapshot\
│   ├─ JSB30_preregistration_final.md        ★正式预注册
│   ├─ JSB30_static_inputs_final.md          ★静态输入表
│   ├─ JSB30_environment_snapshot.md         ★环境快照
│   ├─ JSB30_planned_runs.jsonl              ★6 条 run 登记（含冻结哈希）
│   ├─ JSB30_N0_guard_report.md              ★78/78
│   ├─ n0_guard.py                           护栏脚本
│   ├─ jsb30_parser.py                       下游解析器（duplicate-header fail-close）
│   ├─ JSB30_static_inputs.md                草案版（保留）
│   └─ _env_backup\                          环境清理前备份
├─ N1_ea\
│   ├─ dsh_JSB30.mq5 / .ex5                  新 EA（独立）
│   ├─ JSB30_N1_frozen_hashes.sha256         ★冻结哈希
│   ├─ probe_m1_start.py                     数据可用性探针
│   └─ JSB30_data_availability_probe.md      ★M1 起点实测
├─ smoke\
│   ├─ JSB30_N1_5_smoke_report.md            ★smoke 报告
│   └─ DS260914_JSB30_SMOKE_V1\              原始产物
├─ N1_5_smoke.py                             smoke 执行器
└─ N0_3_execution_report.md                  ← 本文件

mql5\dshtools\
├─ dsh_JSB30.mq5                             ★新 EA
└─ dsh_JSB30Probe.mq5                        探针（只读）
```

---

## 8. 下一步

```
N2 正式 TRAIN（V1 → V2 → V3 串行）
  ⛔ 阻塞：等 §5.4 的 Q5 裁定（TRAIN 起点）
  ✅ 其余前置全部就绪：N0 78/78、N1 编译 0/0 哈希冻结、N1.5 工程链通过
```
