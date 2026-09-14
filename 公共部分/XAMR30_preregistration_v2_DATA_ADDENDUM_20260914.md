# `XAMR30` 预注册 v2 · DATA ADDENDUM（数据资格附录）

- 提交者：DeepSeek-执行者
- 时间：2026-09-14（Asia/Shanghai）
- 性质：**pre-economic data qualification addendum**（经济测试之前的数据资格附录）
  —— **不是策略参数修改**
- 状态：**在任何 77 个月探针结果出现【之前】写入并冻结**

---

## 0. 为什么需要这个附录

prereg-v2 §2.1 只定义了 `common_session_alignment_ratio >= 99%`，存在一个**数学漏洞**：

```
若某个月 XAU 只剩极少 bar，例如：
    XAU bars = 20 ; exact match = 20
则 common_session_alignment_ratio = 100%  ← 通过
但显然不能证明该月历史完整（分母太小）。
```

**因此需要第二个独立 gate 从"USDJPY 侧"限制稀疏性。**

---

## 1. 两个独立 gate（均须每月满足）

### Gate A —— exact 数据质量

```
common_session_alignment_ratio = exact_intersection / XAU_existing_M30_bars
要求：>= 99%
含义：每一个真实存在的 XAU bar，几乎都有同 timestamp 的 USDJPY bar
```

### Gate B —— 防"分母过小"的数据完整性 sanity gate

```
info_availability_ratio = exact_intersection / USDJPY_M30_bars
要求：>= 90%
含义：XAU 在多少 USDJPY bar 时间点处于可用 session
说明：正常真实市场值预期约 95%（USDJPY session 比 XAU 宽，
      XAU 每交易日固定缺 22:00/22:30 UTC 两根 ≈ 4.17%）
★90% 不是策略过滤条件，只用于排除某个月黄金历史【严重稀疏/缺失】。
```

---

## 2. 结构完整性要求（每月）

```
duplicate JPY timestamps          = 0
duplicate XAU timestamps          = 0
non-monotonic JPY                 = 0
non-monotonic XAU                 = 0
counted_outside_requested_month   = 0
```

`counted_outside_requested_month` 定义：本探针统计的 bar 中，
open timestamp 落在 `[month_start, next_month_start)` 之外的根数。
**必须为 0**（探针内部按此区间硬过滤后计数）。

---

## 3. 冻结声明

```
★本附录在跑完整 77 个月结果【之前】写入并冻结。
★Gate A 与 Gate B 均在任何 TRAIN 之前冻结，
  不得以后根据任何盈亏结果改变。
★若早期月份 XAU history 明显稀疏 → 按机械规则向后移动 TRAIN start（见 §4）。
```

---

## 4. TRAIN start 的机械冻结规则

```
从 2018-01 起，寻找最早月份 M，使：
  · 从 M 到 2024-05 的【每一个月】都满足：Gate A PASS 且 Gate B PASS
    且 duplicate=0 · non-monotonic=0 · outside_requested_month=0
  · 且 USDJPY M1 execution coverage 已证明正常
TRAIN start = M 的第一个 actual eligible M30 signal bar

★不得为了更多年份放宽 gate
★不得看到盈利以后移动起点
★若 2018-01 即满足 → 冻结 2018 起点
★若更晚月份才连续满足 → 机械向后移动

VALID 仍固定 = 2024-06-01 ~ 2025-05-31
★禁止：2025-06-01~2026-05-31（exposed_oos）· 2026-06-01~09-30（user_holdout）
```

---

## 5. 探针方法（Tester-only，逐月独立）

```
· 每个月一个【独立 date-scoped Tester probe】
  run tag / 输出目录 / 日期范围 完全隔离，不共享结果文件
· ★不使用"一次长窗口 + SeriesBarsCount/iBars 倒推月份"（已证明受缓存污染）
· 统计只接受 month_start <= open_timestamp < next_month_start
· 输出：见 §1/§2 的全部字段 + server_utc_offset
```
