# JSB30 · TRAIN/VALID 最终审阅包（R2）

- 提交者：DeepSeek-执行者
- 提交时间：2026-09-14（Asia/Shanghai）
- 依据：GPT `JSB30裁定与实施_20260914.md` + GPT 对 `9c9a1bc` 的 N1R2 裁定
- 阶段：**N1R2 → 时间系统重新裁定 → N1.6R → 重新冻结 → N2（三个 TRAIN）→ N3（无通过者）**

---

## 一页式结论

> # 🛑 **NO-GO**
>
> ## `JSB30 = closed / blocked_failed`
>
> | 变体 | TRAIN 净利 | PF | 官方权益 DD | 笔数 | 频率 | 去前10 | 裁定 |
> |---|---:|---:|---:|---:|---:|---:|---|
> | **V1**（baseline, TP 1.5R） | **−377.81** | **0.84** | **77.40%** | 1,143 | 178.2/年 | **−485.23** | **closed** |
> | **V2**（range→03:00） | **−406.81** | **0.84** | **82.55%** | 1,293 | 201.6/年 | **−514.10** | **closed** |
> | **V3**（TP→1.0R） | **−424.20** | **0.73** | **85.16%** | 1,066 | 166.2/年 | **−494.08** | **closed** |
>
> **三个预注册变体全部触发停止条件，均不得进入 VALID。VALID 运行数 = 0。**
>
> **★执行链全部通过（见 §7）→ 这是策略失败，不是审计失败。**

---

## 1. N1R2 最终修复摘要

### 1.1 A 项 · 服务器时间重新裁定

**★GPT 的质疑成立，实测推翻了我此前的假设。**

| 来源 | 结论 |
|---|---|
| **第一层**：实时终端 `TimeCurrent/TimeTradeServer/TimeGMT` | `server_minus_GMT_sec = 0`（连续 5 次采样） |
| **第二层**：Tester 历史，四时段 × 40 周 = **160 个交易周** | `server_minus_GMT_sec = 0` **无一例外**；周首 bar 恒为**周一 00:00**；周末 bar 恒为**周日 23:59**；缓存起点 `2022.01.02 22:10`（周日，冬令） |
| **Exness 官方口径** | MT5 默认 GMT+0 并与 Exness 服务器同步；服务器 UTC+0；DST 改变的是 trading session |

```
★★ 最终裁定：server_utc_offset = 0，server timestamp == UTC timestamp
```

**★这正好解释了 GPT 指出的现象**：
```
旧代码用「周日固定 22:00 UTC 开市」反推 offset
但实测周末首 bar 是【周一 00:00】→ 00 − 22 ≡ 2 小时 → 被误判为 offset = +2
★这是【用错误假设反推假设本身】的循环论证，现已废止。
```

**已从策略运行依赖中删除**：整套 +2/+3 动态时区转换（`ServerToUtc`/`UtcToServer` 改为**恒等**，
`ServerUtcOffset()` **恒返回 0**）。DST 现在只影响"市场有没有 bar"。

**详见**：`N1_ea/JSB30_server_time_reconciliation.md`

### 1.2 B 项 · OCP 风险 sizing 修复

```
旧：LotForRisk() 用 long 的 Ask→Ask−stopDist 算 1 lot 风险，再套用到 short
新：LotForRisk(dir, ...) —— Long 用 Ask→Ask−SL，Short 用 Bid→Bid+SL，两侧分别计算
★OCP 是唯一权威风险值；OCP 失败时【不得】fallback 到独立公式下单
   → reject + 记 ocp_error + g_auditFailed + fail-close
★最终 lot 取整后用 OCP 对 actual entry→actual SL 重算 actual risk
★成交后用 POSITION_PRICE_OPEN / POSITION_SL / 最终 volume 再算 real_sl_risk
   若 real_sl_risk > InpMinLotMaxRiskPct 上限 → run invalid（本季实测 risk_cap_breach = 0）
```

### 1.3 C 项 · OCP 审计改为三方对账

```
主判据（预注册）：|MT5 DEAL_PROFIT − OrderCalcProfit| <= 0.05 USD
  超出 → 该 closing deal 标 mismatch，run invalid
独立公式：改为【diagnostic only】（formula_value / formula_diff / formula_pct）
★已删除我此前自主选择的 InpOcpTolRelPct=2.5%
  → 改为 InpFormulaTolPct=5.0 且 InpFormulaDiagnosticOnly=true（不参与 pass/fail）
```

**实测**：三个 TRAIN 的 `ocp_mismatch = 0`（全部 ≤ 0.05 USD）。

### 1.4 D 项 · range 数据完整性

```
V1 / V3：UTC00–06 → expected M30 bars = 12
V2     ：UTC00–03 → expected M30 bars = 6
★只有 g_rangeCount == expected 才允许 g_rangeReady=true；否则当天不交易
★审计记录 range_count / expected_range_count；拒单表记 range_incomplete
实测：V1 短窗验证 run 的 skip_range_incomplete = 17（闸门在工作）
```

### 1.5 E 项 · 真正 fail-close

```
OnTick 开头统一 gate：if(g_fatal || g_auditFailed) → 有仓则安全平仓，然后 return
任何 audit_failed / OCP fatal / schema failure / time-mapping fatal → 立即停止产生新交易
```

**★实证有效**：本轮前两次长窗口运行因自检失败而 `fatal=1`，**trades=0** ——
fail-close 正确阻止了在不可靠前置条件下产生经济结果。

### 1.6 F 项 · provenance / manifest 完整性

```
★静态输入表改为【由源码自动生成】（gen_static_table.py），消除手工漂移
★新增 n0_fourway.py：source ↔ static table ↔ INI [TesterInputs] ↔ manifest resolved_inputs
  四方集合与取值必须完全一致，否则【拒绝运行】
★每个 run 的 manifest 都写入完整 resolved_inputs（33 项）—— 不依赖"源码默认值"
实测：source 33 项 = resolved 33 项；6/6 run 四方一致
```

**★该检查在本轮真实捕获了两处漂移**：
```
① 静态表缺 4 项（InpExpectedServerOffsetMin/Max, InpFormulaTolPct, InpFormulaDiagnosticOnly）
   且多 1 项（已删除的 InpOcpTolRelPct）
② 数值比较 bug（"5.0" vs 5）导致误报值不一致
→ 均已修复
```

### 1.7 我主动登记的 N1R2 自身缺陷

```
★REALWEEK 自检有两个 bug，导致两次长窗口运行被误 fail-close（trades=0）：
 ① iBarShift(wk, false) 返回 ≤wk 的最近 bar，当 wk 后无 bar 时会落到【上一周】
    → 改为从 wk 起向后找第一根 >= wk 的 bar
 ② 断言"周首 bar 必须在周日/周一"过严 —— 圣诞（2017-12-25 周）等节假日会顺延到周二
    → 改为"滞后周一起点 0~72 小时"（节假日顺延仅统计 holiday_shifted，不判失败）
★讽刺的是：这恰恰证明 fail-close 按设计工作 —— 它正确阻止了不可靠数据下的运行。
★教训：自检断言必须区分【真不变量】与【市场行为】；把后者写成硬断言会造成误 fail-close。
```

---

## 2. 历史覆盖最终冻结（N1.6R，Tester-only）

**方法**：`Strategy Tester + 真实 USDJPYm + Model=2 + FromDate`，**不使用终端图表 CopyRates/CopyTime**。
逐季度取一个非假日完整工作周，`coverage = generated_M1_bars / 5760`。

### 2.1 ★coverage 分母更正

```
旧分母 = 工作日日期数 × 1440 = 5 × 1440 = 7200  → 所有"正常"周只能到 80%，90% 阈值物理不可达
新分母 = 5760（★实测的完整交易周 M1 bar 上限 = 96 小时 × 60）
理由：外汇市场周日 22:00 UTC 已开市，MT5 的 M1 bar 不覆盖周末闭市时段
```

### 2.2 逐季度结果（摘要）

| 区间 | coverage_norm | 判定 |
|---|---|---|
| 2014Q1 ~ 2016Q3（6 个季度采样） | **0.00% ~ 0.07%** | **server_unavailable** |
| **2017Q1**（非假日补测 2017.02.06~02.10） | **0.07%** | **server_unavailable** |
| **2017Q2**（非假日补测 2017.05.08~05.12） | **99.98%** | normal_continuous |
| 2017Q3 ~ 2018Q4 | 99.90% ~ 100.00% | normal_continuous |
| 2019Q1 ~ 2023Q4 | 95.43% ~ 100.00% | normal_continuous |
| **2024Q1**（非假日补测） | **99.90%** | normal_continuous |
| 2024Q2 / 2024TAIL | 99.93% / 100.00% | normal_continuous |

**★2018Q1 / 2024Q1 原采样撞上元旦周**（68.73% / 76.77%），已用非假日周补测，
缺口由**节假日**造成，不是数据不可用 —— 属测量瑕疵，已更正。

### 2.3 冻结结论

```
★★ TRAIN = 2018-01-01 ~ 2024-05-31
   VALID = 2024-06-01 ~ 2025-05-31

机械规则（2017Q2 起满足）给出 2017Q2；
★实际取 2018-01-01，理由（保守、可辩护，不依赖 2017 边界歧义）：
  · 2017Q1 实测 0.07%（死区）→ 2017Q2 骤升至 99.98%，
    该跃迁点位置存在测量歧义（Tester 会把已缓存整段一次性生成）
  · 2018-01-01 起【每一个】采样季度（含非假日补测）均 >= 99.9%，
    是唯一"从该日起无边界歧义且此后持续满覆盖"的起点
  · 与 GPT 早前独立判断「2018 是明显的正常候选起点」一致
★该决定在跑 N2 之前冻结，未参考任何 JSB30 盈亏。
```

**详见**：`N1_ea/JSB30_history_coverage_final.md`

---

## 3. 最终冻结哈希（N1R2）

```
源码  dsh_JSB30.mq5   40889 B
      B15D6550A8AFBE101AD661DA0AEB819BC88E946ED760FBFCA5C65CE59D88A267
EX5   dsh_JSB30.ex5   46338 B
      7BD34140655427D9B39CCBCA22F4A61A0833F8E176E34A9ADDEFFA86FD02ECF2
编译  0 errors / 0 warnings（MetaEditor64, MT5 build 6184）
```
**★最终哈希以 `N1_ea/JSB30_N1R2_frozen_hashes.sha256` 为准**（含历史版本留档，不覆盖）。

| 版本 | source SHA-256 | 状态 |
|---|---|---|
| **N1R2（最终）** | 见 `JSB30_N1R2_frozen_hashes.sha256` | **有效** |
| N1R2 v1 | `EFFFA6A5097FEB64…` | 留档（REALWEEK 自检有 bug） |
| N1R | `0F03F57C4AB06FD0…` | 留档 |
| N1 | `E3E80B296AC82B56…` | 留档（`needs_repair`） |

---

## 4. 前置闸门状态

| 闸门 | 状态 |
|---|---|
| **N0** | ✅ **verified_recheck —— guard 78/78 · 四方一致 6/6** |
| **N1R2** | ✅ **frozen —— 编译 0/0，哈希冻结** |
| **N1.5R2** | ✅ **engineering_verified —— 三组窗口（WINTER/DSTTR/SUMMER）全部产生真实成交，审计链通过** |
| **N1.6R** | ✅ **data_provenance_verified —— 逐季度 coverage 表 + TRAIN 起点冻结** |
| **N1.7** | ✅ **preflight —— 四方一致、日期护栏、无 exposed_oos/user_holdout 触碰** |

---

## 5. N2 · 三个 TRAIN 总表

**口径**：真实 `USDJPYm` / 500 USD / USD / Model=2 / M1 驱动 / M30 信号 / `server_utc_offset=0`
**区间**：2018-01-01 ~ 2024-05-31（6.42 年）
**同一冻结 EX5**，仅预注册差异：

```
V2：InpRangeEndUtcHour 6 → 3（expected range bars 12 → 6）
V3：InpTP_RMult 1.5 → 1.0R
★无 V2+V3 组合版；无其他差异
```

| 指标 | **V1** | **V2** | **V3** |
|---|---:|---:|---:|
| 净利 (USD) | **−377.81** | **−406.81** | **−424.20** |
| Profit Factor | **0.84** | **0.84** | **0.73** |
| **官方 Equity DD Relative** | **77.40%** (404.30) | **82.55%** (435.90) | **85.16%** (426.84) |
| 交易数 | 1,143 | 1,293 | 1,066 |
| 频率（笔/年） | 178.2 | 201.6 | 166.2 |
| 首笔 | 2018-01-02 | 2018-01-02 | 2018-01-02 |
| 末笔 | 2024-05-30 | 2024-05-30 | 2024-05-30 |
| 去前 10 大盈利单后 | **−485.23** | **−514.10** | **−494.08** |
| top10 合计 | 107.42 | 107.29 | 69.88 |
| swap 合计 | 见 summary.json | — | — |
| commission 合计 | 见 summary.json | — | — |
| `ocp_mismatch` | **0** | **0** | **0** |
| `audit_failed` | **0** | **0** | **0** |
| `risk_cap_breach` | **0** | **0** | **0** |
| `fatal` | **0** | **0** | **0** |
| `skip_range_incomplete` | 见 summary.json | — | — |

**完整逐项数据**：`runs_n1r2/n2n3_summary.json`

---

## 6. 每个变体的 12 项停止条件逐项裁决

| # | 停止条件 | V1 | V2 | V3 |
|---|---|---|---|---|
| 1 | 净利 ≤ 0 | **触发** | **触发** | **触发** |
| 2 | PF ≤ 1 | **触发** | **触发** | **触发** |
| 3 | 官方 Equity DD > 40% | **触发**（77.40%） | **触发**（82.55%） | **触发**（85.16%） |
| 4 | 2× 成本压力后转负 | **触发** | **触发** | **触发** |
| 5 | 去前 10 大盈利单后转负 | **触发** | **触发** | **触发** |
| 6 | 报告/审计/成本对账不一致 | 通过 | 通过 | 通过 |
| 7 | 主要收益依赖少数极端单 | **触发** | **触发** | **触发** |
| 8 | 最小手风险地板主导 | 通过（breach=0） | 通过 | 通过 |
| 9 | 成交跨度 < 90% | 通过 | 通过 | 通过 |
| 10 | 平均频率 < 50 笔/年 | 通过（178.2） | 通过（201.6） | 通过（166.2） |
| 11 | spread / initial SL 距离中位数 > 30% | **无法评估**（审计未记录 spread 与 SL 点位；已在 §8 登记为局限） | 同 | 同 |
| 12 | 真实 run 的 DST / time selfcheck 矛盾 | 通过 | 通过 | 通过 |
| | **结论** | **closed** | **closed** | **closed** |

**★每个变体至少触发 7 项停止条件；最致命的三项（净利、PF、DD>40%）全部触发。**

---

## 7. 审计完整性

```
✅ 四方 input 一致（source ↔ static ↔ INI ↔ manifest resolved_inputs），6/6 run
✅ N0 guard 78/78
✅ HTML Total Trades == 审计 closing deal 行数（V1 1,143 / V2 1,293 / V3 1,066）
✅ HTML 净利 == 审计净利（差 <= max(0.02, 0.1%)）
✅ profit + swap + commission = net（逐笔）
✅ ★DEAL_PROFIT ↔ OrderCalcProfit：全部 <= 0.05 USD（ocp_mismatch = 0）
✅ 独立合约公式：仅诊断，不参与 pass/fail
✅ deal_ticket 唯一（无重复）
✅ 每 UTC 日 <= 1 笔
✅ 无 UTC 20:00 后仍持仓
✅ range 完整性：rangeCount == expected 才冻结；否则当天不交易
✅ server 时间 == UTC 时间（审计列 entry_time_server 与 entry_time_utc 相等）
✅ 结束时无活动仓位（active_positions = 0）
✅ fail-close 有效（本轮前两次运行因自检失败而 trades=0）
✅ 历史 R4 重复 entry_time header 未修改、未重导；新 EA 已修复且下游解析器 fail-close
```

---

## 8. 已知局限（如实登记）

```
1. ★停止条件 #11（spread / initial SL 距离）无法评估 ——
   审计表未记录入场时的点差与 SL 点位，故无法计算该比值。
   已记入 summary 的 gates["11_无spread数据"]=True，未作为触发项。
   若后续 family 需要，应在 EA 中补 record spread_at_entry 与 sl_points。

2. N1.6R 的 coverage 采样是【每季度一个代表性周】，不是全季度逐周。
   这是为控制运行时间所做的采样；Tester 缓存会把已缓存整段一次性生成，
   短窗口探测无法精确定位数据可用性的季度边界。
   → 2017Q1→Q2 的跃迁点因此取保守值（TRAIN 从 2018-01-01 起）。

3. 本轮未使用 exposed_oos（2025-06-01~2026-05-31）与 user_holdout（2026-06-01~2026-09-30）——
   两者均未被读取、未被回测。
```

---

## 9. 禁止事项遵守情况

```
✅ 未读取 exposed_oos（2025-06-01 ~ 2026-05-31）
✅ 未读取 user_holdout（2026-06-01 ~ 2026-09-30）
✅ 未做参数扫描
✅ 未根据 TRAIN 结果补过滤器
✅ 未做 long-only / short-only 事后筛选
✅ 未构造 V2+V3 组合版
✅ 未使用自建 symbol（symbols.custom.dat 不存在；Custom 下无 _HIST）
✅ 未做 CSV 回灌
✅ 未修改任何历史旧 EA（新建 dsh_JSB30.mq5 / dsh_JSB30WeekProbe.mq5 / dsh_JSB30TimeProbe.mq5 / dsh_JSB30History.mq5 / dsh_JSB30Probe.mq5）
✅ 未进行真钱交易
```

---

## 10. 工程结论（与策略结论分离）

```
★JSB30 的【时段突破】结构在 USDJPYm / 500 USD / 2018-2024 上：
   · 方向正确性不足：PF 0.73~0.84，三个变体全部为负
   · 风险过大：官方权益 DD 77%~85%（远超 40% 失败线）
   · 成本吃掉边际：2× 成本压力后一律转负
   · 无尾单依赖假象：去前 10 大盈利单后【更负】（说明不是靠少数大单撑起来的假正收益，
     而是全面为负）
★与既有日元线结论一致：JPY 的趋势 / 反转 / 网格 / 时段突破四条结构线均无正期望。
★该结论【不因本 family 关闭而改变对其他标的的推断】。
```

---

## 11. 产物索引

```
执行_下一family_20260913/
├─ N1R2_repair_report.md                       ← 本文件（最终审阅包）
├─ N1R_repair_report.md                        N1R 阶段报告（历史）
├─ N0_3_execution_report.md                    N0/N1/N1.5 阶段报告（历史）
├─ N0_snapshot/
│   ├─ JSB30_preregistration_final.md          正式预注册
│   ├─ JSB30_static_inputs_final.md            ★由源码自动生成（零漂移）
│   ├─ JSB30_planned_runs.jsonl                ★6 条 run + 完整 resolved_inputs
│   ├─ JSB30_N0_guard_report.md                ★78/78
│   ├─ n0_guard.py · n0_fourway.py             ★四方一致性检查
│   └─ jsb30_parser.py · check_inputs.py
├─ N1_ea/
│   ├─ dsh_JSB30_N1R2.mq5 / .ex5               ★最终冻结版
│   ├─ JSB30_N1R2_frozen_hashes.sha256         ★最终哈希
│   ├─ dsh_JSB30_v1_N1_needs_repair.mq5        历史留档
│   ├─ JSB30_server_time_reconciliation.md     ★服务器时间最终裁定
│   ├─ JSB30_history_coverage_final.md         ★历史覆盖冻结
│   ├─ time_probe/week_probe_P2023_*.txt       四时段周界原始记录
│   └─ coverage/coverage_quarters*.json        逐季度覆盖原始结果
├─ smoke_r/                                    N1.5R 三窗口产物
├─ runs_n1r2/
│   ├─ n2n3_summary.json                       ★N2/N3 完整逐项结果
│   └─ DS260914_JSB30_*_TRAIN/                 三个 TRAIN 的报告/审计/INI
├─ run_n2n3.py                                 N2/N3 执行器
└─ N1_5R_smoke.py
```

---

## 12. 最终判定

```
🛑 JSB30 = closed / blocked_failed

· N1R2 = frozen
· 时间系统 = server_utc_offset 0（实测）
· TRAIN 起点 = 2018-01-01（coverage 冻结）
· V1/V2/V3 TRAIN = 全部 closed，无一进入 VALID
· VALID 运行数 = 0
· 不继续扫描 JSB30 参数
```
