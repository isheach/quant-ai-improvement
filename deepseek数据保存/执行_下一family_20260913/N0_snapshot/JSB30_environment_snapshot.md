# `JSB30` 环境快照（Environment Snapshot · N0）

- 生成者：DeepSeek-执行者
- 生成时间：2026-09-14（Asia/Shanghai）
- 依据：`公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md` §3（N0）
- **用途：冻结运行环境事实；任何变更必须在 N1 重新登记**

---

## 1. MT5 终端与工具链

| 项 | 值 |
|---|---|
| 终端版本 | **5.0.0.6184** |
| 终端可执行 | `C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe`（126.4 MB） |
| MetaEditor | `C:\Program Files\MetaTrader 5 EXNESS\MetaEditor64.exe`（存在） |
| 数据目录 | `C:\Users\UIC\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06` |
| Tester agent 数据 | `C:\Users\UIC\AppData\Roaming\MetaQuotes\Tester\53785E099C927DB68A545C249CDBCE06` |
| 公共文件空间 | `<终端>\Common\Files\dshtrend\<run_tag>\` |

---

## 2. 账户与品种规格（实测）

### 2.1 账户

| 项 | 值 |
|---|---|
| 券商 / 服务器 | Exness / `Exness-MT5Trial5` |
| 登录 | `277335900` |
| 币种 / 杠杆 | USD / 1:200 |
| 保证金模式 | **HEDGING**（`margin_mode=2`，实测） |
| 主口径入金 | **500 USD** |

### 2.2 `USDJPYm` 实测规格

```
digits        = 3
point         = 0.001
contract      = 100,000
volume_min    = 0.01
volume_step   = 0.01
stops_level   = 0        （无最小止损距离限制）
spread_points = 11       （快照值）
leverage      = 200
margin_mode   = 2 (HEDGING)
```

**风险换算（实测 risk math）**：
```
money_per_price_per_lot  = 776.81
usd_per_point_per_0.01lot = 0.00776808 USD/点
→ 0.01 手 / 1.0×ATR 止损：JPY M30 的 ATR 量级将在 N1.5 smoke 中实测
```

### 2.3 历史数据

| 项 | 值 |
|---|---|
| **`USDJPYm` 真实可用首 bar** | **2014.01.14** |
| 依据 | `run_trend/runexp.py` 的 `FIRST_BAR["USDJPYm"]`；且历史 `run_JPYCHK1.ini`/`run_JPYCHK2.ini` 实际以 `2014.01.14` 起跑 |
| 本地历史缓存 | `<终端>\bases\Exness-MT5Trial5\history\USDJPYm\` — **18 个文件 / 458.8 MB** |

**★与 GPT 裁定 §1-Q3 的一致性**：裁定要求 TRAIN「2014-01-14 ~ 2024-05-31；若 MT5 实际首个有效 bar 稍晚，以实际首 bar 为准并记录」。
**当前证据显示首 bar 即 2014.01.14，与裁定一致。N2 运行时将再次核对 HTML 报告的 `Bars` 与首笔时间。**

---

## 3. 时段与 DST 事实（GPT §4 的核心）

```
· MT5 时间戳 = 【券商服务器时间】，不是 UTC，也不是本地时间
· Exness 服务器随 DST 在 GMT+2（夏令）/ GMT+3（冬令）之间切换
· 实测证据：R4 run（窗口 2023.01.02~2023.12.29）成交覆盖 0~23 全时段，
  说明服务器日为连续 24 小时制
· ★因此 JSB30 必须【按交易周动态推导 offset】，禁止整段固定（GPT Q1 否决整段固定）
```

**N1 必须完成的 round-trip 自测（三类周）**：
```
① 冬令周
② 夏令周
③ DST 切换附近周
每类均需：utc -> inferred offset -> server -> recovered utc  全一致
```

---

## 4. ★环境清理记录（本轮实际动作）

### 4.1 发现

在 N0 环境检查中发现 `bases\Custom\history\JPYUSD_HIST\2026.hcc` 再次出现：

| 项 | 值 |
|---|---|
| 路径 | `<终端>\bases\Custom\history\JPYUSD_HIST\2026.hcc` |
| 大小 | **15,144 B（15 KB，空缓存，无实际价格数据）** |
| 创建/修改时间 | 2026-09-13 01:40:49（MT5 在 symbols.custom.dat 被移除后自动重建的空壳） |

### 4.2 判定

```
· 自建品种的【定义】已不在：bases\symbols.custom.dat 不存在（False），Tester bases 侧同样不存在
· 因此 MT5 不会再把 JPYUSD_HIST 当作活动品种去同步
· 残留 2026.hcc 只是派生缓存（15 KB），不是自建品种数据
· ★但它属于"自建品种"相关残留，且用户原始硬约束要求清除自建品种
```

### 4.3 处置（先备份，再清理）

```
1. 备份 -> deepseek数据保存\执行_下一family_20260913\N0_snapshot\_env_backup\JPYUSD_HIST_history\
2. 停止 MT5 进程（terminal64 / metatester64）
3. 删除 bases\Custom\history\JPYUSD_HIST\ 与 bases\Custom\ticks\JPYUSD_HIST\
```

### 4.4 清理后自检

```
symbols.custom.dat          : 不存在 ✅
Custom 下自定义品种目录       : 0 个 ✅
Custom 下内容                : 仅 history / ticks 两个空容器 ✅
MT5 进程                     : 0 个 ✅
```

**★不删除的任何内容**：`XAUUSD_HIST_M1.csv`（76.8 MB，属 eva028 线，按裁定"不删证据"保留）。

---

## 5. 已有的自定义品种/回灌风险（历史登记，本轮不改）

| 项 | 数量 | 状态 |
|---|---:|---|
| 越界触碰 `user_holdout` 的 run（eva028 线） | 10 | `blocked_constraint_violation`（已登记，不删除） |
| 使用自建品种的 run（eva028 线） | 60 | 同上 |
| 与 `exposed_oos` 重叠的 INI | 113 | `exposed_oos`（不作为独立样本外） |
| 与 `user_holdout` 重叠的 INI | 10 | `user_holdout`（硬禁止） |

**明细**：`执行_20260912\stage0_provenance_v2\provenance_inventory_v2.csv`、`orphan_runs.csv`、`data_exposure.csv`

---

## 6. run tag 唯一性状态

| 项 | 值 |
|---|---|
| 既有 `run_*.ini` 总数 | **674** |
| `DS260914_JSB30*` 已存在数量 | **0** ✅（tag 可用） |
| R4 登记表条目 | 12 条（`执行_第三批\stage0_snapshot\run_registry_r4.jsonl`） |

---

## 7. 旧 EA 清单（★本轮不得修改任何一项）

```
dsh_BtcSwing.mq5          44,242 B
dsh_JPYRev.mq5            44,435 B      ← R4 审计链修复版（含重复 entry_time bug，历史文件不改）
dsh_JPYRev_R4.mq5         （第三批，51,378 B）
dsh_JPYGrid.mq5           49,542 B
dsh_TrendCore.mq5         61,529 B
dsh_MeanRev.mq5           28,244 B
dsh_TickClock.mq5          8,823 B
…（共 22 个 .mq5）
```
**★JSB30 将新建独立源码 `dsh_JSB30.mq5`，允许复制既有工程框架，但不得修改旧源码（GPT §4）。**

---

## 8. 已知的历史审计缺陷（GPT Q4 裁定）

```
★历史 R4 审计（R4_JPY_*_A/trades.csv）有 26 列，其中 entry_time 出现【两次】（重复列名）。
裁定：
  · 不修改、不重导历史 R4 文件
  · 只在 JSB30 新代码中修复
  · 增加 header unique selfcheck
  · 下游解析器发现重复 header → 立即失败（fail-close）
  · 报告注明历史 R4 存在此 bug，JSB30 已修复
```

---

## 9. 本快照的效力

```
生效范围：JSB30 的 N0 → N1 → N1.5 → N2 → N3
失效条件：MT5 版本变更、终端数据目录变更、账户/杠杆变更、品种规格变更、
          或任何影响策略行为/经济审计字段的代码修复
          → 任一发生即"重新 N1、重新 hash、重新登记"（GPT §4）
```
