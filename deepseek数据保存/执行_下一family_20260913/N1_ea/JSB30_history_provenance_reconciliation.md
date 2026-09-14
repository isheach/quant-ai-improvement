# `USDJPYm` 历史覆盖 provenance 对账

- 生成者：DeepSeek-执行者
- 生成时间：2026-09-14（Asia/Shanghai）
- 依据：GPT JSB30 裁定（N1.6 阶段要求）——「不能直接接受『2014–2016 M1 不存在』这个结论」
- **结论：冲突已解决。不是数据矛盾，而是【MT5 声明值】与【实际可回测值】的区别。**

---

## 1. 冲突的两方原始陈述

| 来源 | 陈述 | 出处 |
|---|---|---|
| **`MEMORY.md`** | `USDJPYm` 真实可用历史 = **2014.01.14 起 · 3,471,032 根 M1** | `deepseek数据保存/MEMORY.md` L37 |
| **我的测试器探针** | 2014Q1 = **0 ticks / 0 bars**；2015Q1 = 73；2016Q1 = 75；2017Q1 = 572；2018Q1 = 88,839 | `N1_ea/JSB30_data_availability_probe.md` |

---

## 2. ★找到 3,471,032 的原始证据来源（不是二手引用）

### 2.1 来源文件（已定位到字节级）

```
文件：deepseek数据保存/mt5workers/w01/MQL5/Files/dshtools/specs.json
      （同一份在 w02…w08 与 template 下各有一份）
时间：2026-09-11 12:54:15
大小：4,201 字节
```

**原文摘录（`USDJPYm`）**：
```json
"history": {"M1":{"bars":3471032,"first":"2014.01.14 00:00","last":"2026.09.11 04:39"},
            "M5":{"bars":663979,...}, "M15":{"bars":222902,...},
            "H1":{"bars":57366,...}, "D1":{"bars":3898,...}}
```
**同文件里 `XAUUSDm` M1 = 3,305,609（2014.01.14 起）、`BTCUSDm` M1 = 4,502,107（2018.02.09 起）**
→ **与 `MEMORY.md` 表中的三个数字完全一致 ⇒ MEMORY 的数字确实来自这份 `specs.json`。**

### 2.2 生成方法（`dsh_ProbeSpecs.mq5` 源码直读）

```
L57  // ---- history availability, per timeframe ----
L65  int bars = (int)SeriesInfoInteger(s, tfs[k], SERIES_BARS_COUNT);
L63  datetime t0 = (datetime)SeriesInfoInteger(s, tfs[k], SERIES_FIRSTDATE);
L64  datetime t1 = (datetime)SeriesInfoInteger(s, tfs[k], SERIES_LASTBAR_DATE);
```
**→ 它读的是 `SERIES_BARS_COUNT` / `SERIES_FIRSTDATE`，即【MT5 系列元数据声明值】。**
**→ 该脚本运行位置：终端图表（`Scripts/dshtools/`），不是测试器。**

### 2.3 ★同一时期的另外两个探针给出的是**完全不同的数字**

| 探针 | 方法 | `USDJPYm` M1 结果 | 时间戳 |
|---|---|---|---|
| **`dsh_ProbeSpecs`** | 终端图表 `SeriesInfoInteger(SERIES_BARS_COUNT)` | **3,471,032 根**，first = **2014.01.14** | 2026-09-11 12:54 |
| **`dsh_DownloadHistory`** | 逐月 `CopyRates()` **强制下载** | **只回溯到 2025-05**（MEMORY L342 自记） | 2026-09-10 |
| **`dsh_ExportRates`** | 导出**实际 bar** | **500,009 行**，`2025.05.08 10:38 ~ 2026.09.10 15:18` | 2026-09-10 23:18 |
| **`dsh_TickCoverage`** | `CopyTicksRange` 逐日采样 | 41 个采样日中**只有 2026.09.10 有 tick**，其余全 0 | 2026-09-10 23:26 |
| **我的测试器探针** | 测试器 M1 缓存 | **2014Q1 = 0 ticks / 0 bars** | 2026-09-14 |

**★★决定性事实**：
```
`specs.json` 声明 M1 = 3,471,032 根（2014.01.14 起）
但同期 `dsh_ExportRates`【实际导出】只有 500,009 行（2025.05.08 起）
→ 声明值与实际导出值相差 2,971,023 根（约 6.9 倍）
→ 且实际起点晚 11 年
```

**→ 结论：`SERIES_BARS_COUNT` 返回的是 MT5 对「该品种在服务器上声称拥有的历史」的元数据，
   而 `CopyRates()` / 测试器实际能取到的是本地缓存 + 可下载的交集。
   前者是【声明】，后者是【实测可用】。**

---

## 3. ★四状态分类（GPT 要求明确区分）

按裁定要求，把每个年份归入四类状态之一：

| 状态 | 定义 | 判定依据 |
|---|---|---|
| **server unavailable** | 券商服务器不提供该区间 | `dsh_DownloadHistory` 逐月强制下载后仍拿不到 |
| **local/tester cache incomplete** | 服务器有、本地/测试器缓存没有 | 终端图表能取到而测试器取不到 |
| **M1 sparse** | 有 bar 但相对工作日分钟容量严重不足 | coverage ratio 低 |
| **normal continuous coverage** | coverage ratio 正常且持续 | coverage ratio ≥ 阈值 |

### 3.1 `USDJPYm` M1 逐年状态

| 年份 | 测试器生成 bars | 导出实际行数 | coverage ratio（估） | **状态判定** |
|---|---:|---:|---:|---|
| 2014 | **0**（仅 101 根占位） | 0 | ≈ 0 | **server unavailable** |
| 2015 | 73（Q1 实测） | 0 | ≈ 0 | **server unavailable** |
| 2016 | 75（Q1 实测） | 0 | ≈ 0 | **server unavailable** |
| 2017 | 572（Q1）/ 246,114（全年） | 0 | ~0.6%（Q1） | **M1 sparse** |
| 2018 | 88,839（Q1） | 0 | ~20%（Q1） | **M1 sparse → 趋正常** |
| 2019–2024-05 | — | — | 待 N1.6R 重测 | **待重测** |
| 2025-05 ~ 2026-09 | — | **500,009** | 正常 | **normal continuous coverage** |

**★支持"server unavailable"的直接证据**：
- `dsh_DownloadHistory`（逐月 `CopyRates()` **强制向 History Server 下载**）结果：**`USDJPYm` 只回溯到 2025-05**（MEMORY L342 自记原文：「发现券商的 M1 只回溯到 2025-04（金）/ 2025-05（JPY）/ 2025-09（BTC）」）
- 我的测试器探针：2014 请求 → M1 cache **101 根占位 bar、0 ticks**，`0 ticks, 0 bars generated`
- `b01_data_audit.csv`：券商新下载 `USDJPYm` = **500,009 根**，`first = 2025-05-08 10:38`

**★支持 2017–2018 是"M1 sparse"而非"不可用"的证据**：
- 2018Q1 生成 **354,598 ticks / 88,839 bars**（测试器能执行）
- 2017 全年生成 **983,079 ticks / 246,114 bars**（能执行但密度低）

---

## 4. ★关于 `ticks` 的措辞更正（GPT 明确要求）

GPT 指出：
> 当前是 `Model=2`。例如：73 M1 bars → 292 generated ticks；75 → 300；572 → 2288，都是 **4× 关系**。
> 因此后续报告**不得把这里的 `ticks` 描述成"真实 ticks"**。历史可用性判断**以 M1 bar 覆盖率为主**。

**核实**：
```
73  × 4 = 292   ✅
75  × 4 = 300   ✅
572 × 4 = 2288  ✅
```
**→ 完全成立。`Model=2` 每个 M1 bar 生成 4 个合成 tick（O/H/L/C）。**
**→ 即 1 tick ≈ 15 秒（这根 bar 内），而**不是**真实逐笔 tick。**

**★与既往记录的一致性检查**：
```
· 我在 R0 阶段用 dsh_TickClock 实测过 "1 tick ≈ 60 秒"（ticks_per_M1 = 1.000）
  —— 那是【探针 EA 在 Model=2 下每 tick 调用一次 OnTick】的口径，
     与"合成 tick 内部有 4 个价位"并不冲突：
     测试器每根 M1 bar 内部按 O/H/L/C 走 4 个价位，
     但 EA 的 OnTick 在 Model=2 下是否每次都被调用，取决于实现。
  → 两个数字口径不同，**本报告一律以 `bars` 为准，不用 ticks 判断可用性。**
```

**→ 本报告及后续所有报告：**
```
· 不再把 Model=2 的 ticks 称为"真实 ticks"
· 历史可用性判断【以 M1 bar 覆盖率为主】
· "真实 tick"仅指 dsh_TickCoverage 用 CopyTicksRange 探到的券商 tick（实测只有 2026.08.16 之后）
```

---

## 5. 客观规则（GPT 要求预先定义，不根据策略收益选择 TRAIN 起点）

```
规则 R-1：以【年/季度 M1 bar 数 ÷ 该期工作日分钟容量】计算 coverage ratio
          （工作日分钟容量 = 工作日数 × 1440）
规则 R-2：若某年 coverage ratio < 5%  → 标 server unavailable 或 M1 sparse（按 §3 判据细分）
规则 R-3：候选 TRAIN 起点 = 【第一个 coverage ratio 达到正常水平的日期】，
          且【从该日起至 2024-05-31 持续正常】
规则 R-4：不得为了保留更多年份而选择稀疏数据
规则 R-5：不得为了得到更好策略结果而选择日期
规则 R-5：起点一经确定即冻结；N2 期间不得更改
```

**★当前证据的初步指向**：`2018` 是明显的正常候选起点（2018Q1 已有 88,839 bars），
**但必须先完成 §6 的服务器重新同步对账再冻结。**

---

## 6. 待执行：明确的重新同步/历史覆盖探针（N1.6R）

```
计划（只使用 MT5 真实 USDJPYm 与策略测试器服务器历史）：
  1. 在【实时终端图表】上运行 dsh_DownloadHistory（逐月 CopyRates 强制下载），
     从 2014-01 到 2024-05，记录每月能否拿到数据
  2. 重新运行 dsh_ProbeSpecs，对比 specs.json 的声明值是否变化
  3. 用测试器探针逐年测实际生成的 M1 bars（不是 ticks）
  4. 生成逐年/逐季 coverage ratio 表
  5. 按 §5 的 R-1…R-5 冻结 TRAIN 起点

禁止：CustomSymbol / CSV 回灌 / 自建品种
```

**★当前状态：本文件为 provenance 对账的【第一阶段】（冲突根源已定位到字节级）。
   §6 的服务器重新同步探针为【第二阶段】，其结果将写入本文件的 §7。**

---

## 7. 第二阶段结果（待填）

```
（N1.6R 执行后填写）
```
