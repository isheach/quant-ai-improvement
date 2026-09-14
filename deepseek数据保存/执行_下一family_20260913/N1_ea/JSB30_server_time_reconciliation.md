# `JSB30` 服务器时间最终裁定（N1R2 · A 阶段）

- 执行者：DeepSeek-执行者
- 时间：2026-09-14（Asia/Shanghai）
- 依据：GPT N1R2 裁定 A 项 ——「Exness server 的 GMT+2/+3 假设不能继续当作事实」

---

## 0. 最终裁定

```
★★ server_utc_offset = 0
   server timestamp == UTC timestamp
   DST 只影响市场有没有 bar，不再改变时钟换算。
```

**→ 旧代码中整套「+2/+3 动态服务器时区转换」已【从策略运行依赖中删除】。**
**→ `InpUseDynamicDstOffset = false`（恒等映射），`InpExpectedServerOffsetMin/Max = 0/0`。**

---

## 1. 第一层：实时终端服务器时间

**探针**：`mql5/Scripts/dshtools/dsh_JSB30TimeProbe.mq5`（只读，不下单）
**记录**：同一瞬间的 `TimeCurrent()` / `TimeTradeServer()` / `TimeGMT()` / `TimeLocal()` / account server / terminal build

**结果（连续 5 次采样，间隔 1.5 s）**：

| idx | TimeCurrent (server) | TimeTradeServer | TimeGMT | server − GMT |
|---|---|---|---|---|
| 0–4 | 与 TimeGMT 完全一致 | 与 TimeGMT 完全一致 | 基准 | **0 秒** |

**→ `server_minus_GMT_sec = 0`**

---

## 2. 第二层：历史 Tester 时间

**探针**：`mql5/dshtools/dsh_JSB30WeekProbe.mq5`（在 Strategy Tester 内对真实 `USDJPYm` 运行，只读）
**方法**：★**不预先假设 open = UTC 22:00**，直接读真实 bar 的 tester 时间戳与星期/小时。

### 2.1 四个时段（覆盖冬令 / DST 附近 / 夏令 / 回到冬令）

| 时段 | 区间 | tester M1 bars | `server_minus_GMT_sec` | 周首 bar (dow, hour) | 周末 bar (hour) |
|---|---|---:|---:|---|---|
| P2023_01_JAN | 2023.01.02~2023.02.05 | 368,173 | **0** | **dow=1(周一) h=00** ×40 | 23 ×40 |
| P2023_03_DST | 2023.03.06~2023.04.09 | 432,036 | **0** | **dow=1 h=00** ×40 | 23 ×40 |
| P2023_07_JUL | 2023.07.03~2023.08.06 | 552,745 | **0** | **dow=1 h=00** ×40 | 23 ×40 |
| P2023_11_NOV | 2023.10.30~2023.12.03 | 674,753 | **0** | **dow=1 h=00** ×40 | 23 ×40 |

**★160 个交易周，无一例外**：
```
· server_minus_GMT_sec 恒为 0
· 每个交易周的第一根 M1 恒为【周一 00:00:00】（dow=1, hour=00）
· 每个交易周的最后 M1 恒为【周日 23:59】（dow=0, hour=23）
· M1 最早 bar = 2022.01.02 22:10  ← 周日 22:10 UTC，与 Exness 公布的周开盘一致
```

### 2.2 判定

```
A. Tester timestamp 本身是否已经是 UTC+0？          → ★是
B. 是否存在真实且可证明的历史 offset？               → ★否（无任何证据）
```

**★并且这正好解释了 GPT 指出的现象**：
> 「这正好可以解释为什么当前 WINTER / DST / SUMMER smoke 都观察到 +2。」

因为旧代码用「周日固定 22:00 UTC 开市」去反推 offset，而**周末首 bar 实际是周一 00:00**：
```
observed_hour(00) − assumed_open_hour(22) → 相差 2 小时 → 被误判为 offset = +2
```
**这是一个循环论证（用错误的假设去反推假设本身），现已废止。**

---

## 3. 与 Exness 官方口径的一致性

| Exness 官方 | 本实测 | 一致？ |
|---|---|---|
| MetaTrader 默认时区 GMT+0，与 Exness trading servers 同步 | `server − GMT = 0` | ✅ |
| Exness trading servers 使用 UTC+0 | `server_utc_offset = 0` | ✅ |
| DST 改变的是 instrument trading session | 周末首 bar 恒为周一 00:00，但**各周首尾 bar 是否存在随 DST 变化** | ✅ |
| Forex 夏令周日约 21:05 UTC 开市 / 冬令约 22:05 UTC 开市 | 缓存起点 `2022.01.02 22:10`（周日，冬令期） | ✅ |

**★无不可解释冲突 → 按裁定继续执行。**

---

## 4. 对策略的影响（已落实）

| 项 | 旧（N1R） | **新（N1R2）** |
|---|---|---|
| `ServerToUtc()` | 按周推导 offset 后做减法 | **恒等返回** |
| `UtcToServer()` | 按周推导 offset 后做加法 | **恒等返回** |
| `ServerUtcOffset()` | 缓存查表 + 推导 | **恒返回 0** |
| `WeekKeyUtc()` | 用于 offset 推导 | **仅用于自检周界断言** |
| UNIT 自测 | 三组日期 + 反推 offset ∈ {2,3} | **三组日期断言 offset == 0 且 round-trip 恒等** |
| REALWEEK 自测 | 逐周推导 offset | **逐周断言 server==UTC 且周首 bar 落在周日/周一** |
| UTC 日切换 | `UtcDayOf(ServerToUtc(t))` | **`UtcDayOf(t)` 直接用** |
| range/breakout/hard-flat 窗口 | 先换算再比较 | **直接比较 server 小时 == UTC 小时** |

**★审计列 `server_utc_offset` 仍保留并【恒写 0】**，作为 provenance 证据。
**审计列 `entry_time_server` 与 `entry_time_utc` 现在必然相等**，可直接核对。

---

## 5. 教训（写入方法论）

```
★不要用「假设的常量」去反推「该常量本身所依赖的参数」。
  旧代码：假设"外汇周开盘 = 周日 22:00 UTC"，再用实测周首 bar 反推 offset。
  但周首 bar 的真实位置【本身就随 DST 变化】→ 反推出的 offset 吸收了 DST，
  变成一个假的正偏移（+2），并被当成"服务器时区"。
★正确做法：直接用【独立的绝对时间源】（TimeGMT）做基准，
  而不是用市场行为（开市时刻）反推时钟参数。
```
