# eva026 · 代码审计与重构交付文档

基于 eva025a（3814 行）审计，产出 eva026_VolumetricPulseGrid_VolGate.mq5（3935 行）。
行号均指 eva025a 原文件。

---

## 第一部分：残余代码审计清单

### A. 确认死亡、已删除

| # | 符号 | 原位置 | 原本想做什么 | 现在是否参与交易 | 处置 | 删除影响 |
|---|---|---|---|---|---|---|
| 1 | `ENUM_VOL_REGIME` | L273-277 | 三档波动枚举（v0.95 多档参数体系） | 否。eva019 删掉判档分类器后无人产生非 LOW 值 | **删除** | 无。仅被下列死变量引用 |
| 2 | `G_VolRegime` | L327 | "当前参数档位"。v0.95 时代驱动三套参数切换 | **否**。初始化=LOW 后永不更新。只进日志/面板/CSV | **删除** | 日志与面板少一行谎言；CSV 见 #11 |
| 3 | `G_RealVolRegime` | L332 | v0.97 "真实波动档位"（与强制档位模式配对） | **否**。同上，永远 LOW。这正是新跑 enrich 里 42 个月 `real_vol_regime` 全为 0 的原因——**连 2026-03 最高波月也标 0**，实证其冻死 | **删除** | 同上 |
| 4 | `G_RegimeOpenAllowed` | L333 | v0.97 强制档位模式的开仓门闸 | **半死**：L829 确实有 `if(!G_RegimeOpenAllowed) return;` 拦截网格开仓，但没有任何代码把它置 false → 恒放行，从不拦截 | **删除**（含 L829 死判断） | 无行为变化（条件恒假）。这是最危险的一类残留：看起来像在风控，实际是空气 |
| 5 | `G_RVLongPoints` | L336 | 长周期 RV（旧双 RV 比值体系） | **否**。从不写入，恒 0.0；进日志、面板、CSV `rv_long_pts` 列（恒 0） | **删除** | CSV 少一列常量 0，见 #11 |
| 6 | `RegimeToStr()` | L999-1004 | 档位转文本 | 否。只服务上述死变量的日志/面板 | **删除** | 无 |
| 7 | `IsWeekendForcedHighParamTime()` | L452 声明、L1111-1118 定义 | 周末时段强制切高波参数（多档时代） | **否**。全文无调用者 | **删除**；周末保护输入注释中"强制使用高波动参数"的过期表述一并修正（注释级，行为不变） | 无 |
| 8 | `ComputeMultiplierA()` | L519 声明、L2707-2723 定义 | v0.99 注释称"供越界止损复用" | **否**。无调用者；且与网格开仓处内联倍数逻辑完全重复，留着必然日后失同步 | **删除** | 无 |
| 9 | `G_TrendPrevHigh` / `G_TrendPrevLow` | L352-353，写入 L1658-1659 | 缓存突破窗前高/前低（疑为调试遗留） | **否**。只写不读 | **删除** | 无 |
| 10 | v0.98 空壳注释块 | L1121-1133 | 已删函数（档位组合）的注释残骸 | — | **删除**，留一行墓碑注释 | 无 |
| 11 | CSV 列 `vol_regime` / `real_vol_regime` / `regime_open_allowed` / `rv_long_pts` | 表头 L3199/L3209，行写出 L3088-3093 / L3132-3134 | 记录下单瞬间档位环境 | 否——四列全程常量（0/0/1/0），零信息量 | **删除**，新增真实生效的 `vol_gate_low` 列（1=闸下低波，0=活跃） | 见下"CSV 兼容性" |
| 12 | run_config 占位列 `vol_pct_*` ×5 | L3339/L3353 | eva019 删判档阈值后填 "0" 占位 | 否 | **改造**为 Vol-Gate 参数快照（volgate_on / enter / exit / confirm / downshift_on），列数不变 | run_config 无下游消费者，仅人读 |

**CSV 兼容性说明**：eva013 管线按列名取列且用 `if c in tr.columns` 过滤，删列不报错；`regime_performance.csv` 自动退化为按 `market_state × year` 聚合。随附的 `eva014_data_pipeline.py` 已把 `vol_gate_low` 加进聚合候选列，且**新旧 CSV 双向兼容**（旧 CSV 有旧列就用旧列，新 CSV 用新列）。跨代对比脚本若曾引用这四列，本来对比的也是常量，无信息损失。

### B. 名不副实、已重命名（行为零改动）

| 旧名 | 新名 | 理由 |
|---|---|---|
| `UpdateVolatilityRegime()` | `UpdateRealizedVol()` | eva019 起它不更新任何 regime，只算百分比波动 G_RVRatio 并刷新参数。旧名正是"以后再被旧变量误导"的头号来源 |
| `LoadLowVolParams()` | `LoadBaseParams()` | eva018 统一模型后它是唯一参数集，"LowVol"暗示还存在 Mid/High 参数集，误导 |

### C. 功能存活但已被数据否定、保留作消融（默认改关）

| 符号 | 处置 | 理由 |
|---|---|---|
| `InpUseMTFConfirm` / `InpUseADXFilter` / `InpUseEMASepFilter` 及其参数、指标句柄 | **保留，源码默认值 true→false**，输入组标题加注【负结果】 | ① a9 强开证明更差、a1~a8 寻参主动架空——机制被否定但代码是活的；② **a8 参数集里 ADX(17,10)/EMASep(0.2) 处于弱开启**，删掉这些开关将导致 a8 无法逐笔复现，违反回测可比性约束。改默认值不影响 .set 驱动的回测 |
| `InpEnableGrid` | 保留 | 纯趋势诊断（对照组⑤）必需 |
| `InpTradeBelowBaseVol`、周末保护、动态手数等 | 保留 | 均有真实调用路径，非残留 |

---

## 第二部分：新架构改动清单

### 模块划分（代码内已用 ①~⑤ 标注）

- **① 网格模块**：基线双向布网 + 回归基线整篮止盈。**不接受 Vol-Gate 任何输入**，低波/高波照常运行；唯一外部影响是⑤降档（且只影响新开仓）。
- **② 趋势单模块**：`ManageTrendOrders()`。
- **③ 砍单模块**：`CutOppositeGrid()`（ticket 级全砍，无部分平仓——0.01 最小手数约束下唯一正确形态，未改）。
- **④ Vol-Gate 模块**（新增）：`UpdateVolGate()` + `IsVolGateLow()`。
- **⑤ 高波网格降档模块**（新增，默认关）：`UpdateHighVolDownshift()` + `UpdateActiveParams()` 内的档位收缩。

### Vol-Gate 状态切换逻辑

```
状态量：G_VolGateLow（初始 = true，保守起步：开机即视为低波，
        需 RV% 持续走高才放行趋势侧——避免"开机瞬间撞上假活跃"）

每根新 M1（节流，与 RV 计算同频）：
  活跃态：RV% < InpVolGateEnterLowPct 连续计数，≥ InpVolGateConfirmBars → 切低波
          （任一根不满足即清零计数）
  低波态：RV% > InpVolGateExitLowPct  连续计数，≥ InpVolGateConfirmBars → 切活跃

  Enter(0.020) < Exit(0.026) 构成滞后带：RV% 落在带内时维持现状，
  加上连续 N=30 根确认，双重防抖。
```

**闸门只锁行为，不锁计算**——状态机每根照常评估、`G_MarketState` 照常切换（面板/日志/CSV 里的 market_state 语义与历史完全一致），被拦的只有三个行为出口：

| 出口 | 接入点 | 低波时（对应开关开启） |
|---|---|---|
| 开新趋势单 | `ManageTrendOrders()`，置于"状态退出平仓/移动止损"**之后** | 禁止。已有趋势单（活跃期开的）照常移动止损、照常按状态退出——闸门落下不产生孤儿仓 |
| 砍逆势网格 | `UpdateMarketState()` 状态切换处 | 禁止触发 `trend_close_opposite_grid` |
| 禁逆势网格过滤 | 网格开仓方向判定处 | 旁路过滤 → 网格恢复双向围绕基线布网 |

活跃态下三个出口全部恢复 eva025a 原行为。`InpUseVolGateForTrendSide=false` 时 `IsVolGateLow()` 恒返回 false，全 EA 与 eva025a 行为逐笔一致（新机制默认值差异除外，见上表 C）。

### 高波网格降档（⑤，默认关，与 Vol-Gate 完全独立）

独立的滞后状态（Enter 0.048 / Exit 0.038 / N=15）。激活时只做两件事，且**只影响新开仓**：
1. `max_total_positions_open = min(硬上限, InpDownshiftMaxPos)`——新增字段，硬上限 `max_total_positions` 原样保留给超额处理逻辑，**保证降档激活瞬间不会强平存量仓位**（避免把风险控制变成即时实现亏损）；
2. 网格基距 × `InpDownshiftGridWidenCoef`。

### 新增输入参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `InpUseVolGateForTrendSide` | true | Vol-Gate 总开关 |
| `InpVolGateEnterLowPct` | 0.020 | 进低波阈值（RV% 口径 = G_RVRatio） |
| `InpVolGateExitLowPct` | 0.026 | 退低波阈值，须 > 进入阈值 |
| `InpVolGateConfirmBars` | 30 | 连续确认 M1 根数（=半小时） |
| `InpVolGateBlockTrendOrders` | true | 低波禁开新趋势单 |
| `InpVolGateBlockTrendCuts` | true | 低波禁砍单 |
| `InpVolGateBlockAgainstTrendGridFilter` | true | 低波旁路"禁逆势网格" |
| `InpVolGateDebugLog` | false | 闸门切换日志 |
| `InpUseHighVolDownshift` | false | 降档总开关 |
| `InpDownshiftEnterPct` / `ExitPct` | 0.048 / 0.038 | 降档滞后阈值 |
| `InpDownshiftConfirmBars` | 15 | 降档确认根数 |
| `InpDownshiftMaxPos` | 2 | 降档时新开仓上限 |
| `InpDownshiftGridWidenCoef` | 1.30 | 降档时网格基距放大 |
| `InpDownshiftDebugLog` | false | 降档切换日志 |

默认阈值标定依据（42 个月 M1，2023-01~2026-06，复刻 EA 的 RV% 公式仿真闸门）：
enter=0.020 / exit=0.026 / N=30 下，2023~2024 有 23/24 个月的多数时间处于闸下
（2024-04 金价大涨月正确地开闸 52%），2025-04/05、2025-10/11、2026 全部高波月
多数时间开闸，**2026 三个极端月 0 误闸**；且 0.018~0.028 邻域内四组候选阈值结果
几乎一致——闸门对阈值不敏感，是机制属性而非拟合值。

### 删除 / 重命名 / 重新实现总表

- **删除**：`ENUM_VOL_REGIME`、`G_VolRegime`、`G_RealVolRegime`、`G_RegimeOpenAllowed`（含 L829 死判断）、`G_RVLongPoints`、`RegimeToStr()`、`IsWeekendForcedHighParamTime()`、`ComputeMultiplierA()`、`G_TrendPrevHigh/Low`、v0.98 空壳注释、CSV 四个常量列。
- **重命名**：`UpdateVolatilityRegime()`→`UpdateRealizedVol()`；`LoadLowVolParams()`→`LoadBaseParams()`。
- **重新实现**（旧 regime 概念的正统继承者）：波动分档判断以 `G_RVRatio` 为唯一事实来源，由 Vol-Gate（趋势侧资格）与降档模块（网格档位）分别持有各自独立的滞后状态——不再存在一个"全局档位"变量被多处隐式依赖。
- **CSV 变化**：trade_events 表头删 4 列增 1 列（`vol_gate_low`）；decision_audit 同步；run_config 占位列改 Vol-Gate 快照。随附 `eva014_data_pipeline.py` 已兼容。

### 推荐回测对照组（同一窗口 2023-01-01 ~ 2026-06-30，a8 参数为基）

| 组 | 配置 | 回答什么 |
|---|---|---|
| C0 原版 a8 | eva025a + a8.set | 基准（已知：全程 +2175，2023-24 段 −691，MaxDD −936，水下 902 天） |
| C1 Vol-Gate 版 | eva026 + a8.set + Gate 默认开 | 核心验证：2023-24 段应从 −691 → 约 +1400±；比照我的反事实上界 +4275（预期实际略低——被砍的单实际会占坑、走完整回归路径） |
| C2 Gate + 降档 | C1 + `InpUseHighVolDownshift=true` | 降档在 2025-26 高波段损失多少网格利润、换回多少 MAE 收缩（重点看逐月最深 MAE 54/77/86/120 压到多少） |
| C3 纯网格 | eva026 + `InpEnableStateMachine=false` | 网格裸奔全程基线；与 C1 之差 = 趋势侧在活跃期的真实净贡献 |
| C4 纯趋势 | eva026 + `InpEnableGrid=false` + Gate 开 | §8-2 一直欠的诊断：趋势侧自身资金曲线、开机时点风险 |

对账锚点：C1 在 2026-02/03（闸门几乎全开的月份）的逐笔成交应与 C0 基本一致；差异集中在低波时段。若 C1 的高波月成交与 C0 明显不同，说明闸门误闸，先查 `InpVolGateDebugLog`。

### 已知限制

- 本环境无 MetaEditor，代码经过结构化校验（括号平衡、符号引用图谱、四个接入点逐一复核）但**未经真实编译**，请先在 MetaEditor 编译一遍再进测试器。
- 旧 .set（a1~a9）导入 eva026 后，新增参数取源码默认值（Gate 开、降档关）；跑 C0 对照请显式置 `InpUseVolGateForTrendSide=false`。
