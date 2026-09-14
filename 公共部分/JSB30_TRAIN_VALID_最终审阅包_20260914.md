# JSB30 · TRAIN/VALID 最终审阅包（阶段：N0–N1.5 完成）

- 提交者：DeepSeek-执行者
- 提交时间：2026-09-14（Asia/Shanghai）
- Source of Truth：`公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md`
- **状态：N0 ✅ / N1 ✅ / N1.5 ⚠️阻塞（数据可用性）→ N2 未启动**

---

## 一页式结论

> ### ⚠️ **N0、N1 通过；N1.5 被【M1 数据可用性】阻塞，N2 未启动**
>
> | 阶段 | 结果 |
> |---|---|
> | **N0** 快照与护栏 | ✅ **78/78 通过** |
> | **N1** 新 EA 与静态审计 | ✅ **编译 0 errors / 0 warnings，源码与 EX5 哈希已冻结** |
> | **N1.5** 最小工程 smoke | ⚠️ **工程链 17/22 通过；5 项失败【全部】源于 2014 年 M1 数据不存在** |
> | **N2** 正式 TRAIN | ⛔ **未启动**（等 TRAIN 起点裁定） |
> | **N3** VALID | ⛔ 未启动 |
>
> **★本轮最有价值的发现**：**「2014–2016 静默」的真实原因是 USDJPYm 的 M1 历史不存在**，
> 不是策略守卫、不是 D1 过滤器、不是参数问题。这解开了前一条日元线遗留的未解之谜。

---

## 1. 三个关键事实（可直接复核）

### 1.1 工程链完全通过

```
EA 内 round-trip 自测（GPT §1-Q1 要求的三类周）：
  SELFTEST winter          in_off=2 -> out_off=2 roundtrip=OK
  SELFTEST winter          in_off=3 -> out_off=3 roundtrip=OK
  SELFTEST summer          in_off=2 -> out_off=2 roundtrip=OK
  SELFTEST summer          in_off=3 -> out_off=3 roundtrip=OK
  SELFTEST dst-transition  in_off=2 -> out_off=2 roundtrip=OK
  SELFTEST dst-transition  in_off=3 -> out_off=3 roundtrip=OK
  SELFTEST 汇总：6/6 通过
→ 动态 DST offset 的 utc -> inferred -> server -> recovered utc 往返全部一致 ✅

CSV schema：
  trades.csv        21 列，header 唯一 ✅
  reject_audit.csv  15 列，header 唯一 ✅
  audit_selfcheck.csv  offset_undetermined=0 · audit_failed=0 · active_positions=0 ✅

下游解析器对重复 header fail-close（实测历史 R4 文件）：
  FAIL(duplicate-header): ★重复 header 列：['entry_time']   退出码 1 ✅
```

### 1.2 ★阻塞：`USDJPYm` 的 M1 在 2014 年不存在

**MT5 日志原文**：
```
USDJPYm,M1: history cache allocated for 101 bars
            and contains 101 bars from 2014.01.14 00:00 to 2014.05.11 00:00
USDJPYm,M1: 0 ticks, 0 bars generated        ← ★测试器无法执行
```
**对照（正常窗口）**：
```
USDJPYm,M1: 1445658 ticks, 368216 bars generated
```

**逐窗口客观探测**：

| 窗口 | ticks | bars | 每年 M1 缓存文件 |
|---|---:|---:|---|
| 2014Q1 | **0** | **0** | **0.1 MB** ← 仅 101 根占位 bar |
| 2015Q1 | **292** | 73 | 0.1 MB |
| 2016Q1 | **300** | 75 | 0.1 MB |
| 2017Q1 | 2,288 | 572 | 14.2 MB |
| 2017 全年 | **983,079** | 246,114 | — |
| 2018Q1 | 354,598 | 88,839 | 21 MB |
| 2019Q1 | 362,146 | 90,906 | 21 MB |

**→ 这不是「首个有效 bar 稍晚」，而是【2014 完全无 M1、2015–2016 近乎无、2017 稀疏】。**

### 1.3 N1.5 的 5 项失败全部是同一原因

```
失败项：Bars>0 · Ticks>0 · Initial Deposit=500 · Symbol=USDJPYm · trades 行数>0
★ 所有 skip_* / rej_* 计数器均为 0
→ EA 未收到任何 tick —— 不是守卫拦掉的，是测试器未执行
```

---

## 2. 需要裁定的一项范围问题

```
Q5（新）TRAIN 起点应取哪一个？

  A) 保持 2014-01-14，接受 2014–2016 的 0 成交
     （按预注册"独立诊断段"如实报告）
  B) 以【实测可执行起点】2017-01-03 为 TRAIN 起点，登记"数据可用性"原因
  C) 以【数据密度正常起点】2018-01-02 为 TRAIN 起点，登记原因
  D) 先补下载 USDJPYm 的 M1 历史（MT5 联网抓取），再按 A 执行

★技术建议：D → 若不可行则 C
  理由：A/B 会把"数据缺口"混进策略评价 —— 频率、覆盖率、逐年 PF 会全部失真；
        D 能得到真正的 2014 起数据；C 是在无法补数据时最接近"可检验"的选项。
★不自行决定：这是预注册范围，按裁定应由 GPT/用户定。
```

**★在裁定前不启动 N2**（避免用掺了 3 年数据缺口的结果去评价策略）。

---

## 3. 遵守情况

```
✅ 未修改任何旧 EA（新建 2 个独立文件：dsh_JSB30.mq5 / dsh_JSB30Probe.mq5）
✅ 未读取 exposed_oos（2025-06-01~2026-05-31）
✅ 未读取 user_holdout（2026-06-01~2026-09-30）
✅ 未做参数扫描
✅ 未用 smoke 盈利调整参数 / 选时段 / 比较 V1/V2/V3
✅ 未构造 V2+V3 组合版
✅ 未真钱下单
✅ 所有 run 先登记（planned）后执行
✅ 未重开 MR30 / C1 / C2 / C3
✅ 历史 R4 重复 header 文件未修改、未重导
```

---

## 4. 产物索引

```
deepseek数据保存/执行_下一family_20260913/
├─ N0_3_execution_report.md                 ★本阶段完整报告
├─ N0_snapshot/
│   ├─ JSB30_preregistration_final.md       ★正式预注册
│   ├─ JSB30_static_inputs_final.md         ★静态输入表
│   ├─ JSB30_environment_snapshot.md        ★环境快照
│   ├─ JSB30_planned_runs.jsonl             ★6 条 run 登记（含冻结哈希）
│   ├─ JSB30_N0_guard_report.md             ★护栏 78/78
│   ├─ n0_guard.py · jsb30_parser.py
│   └─ _env_backup/
├─ N1_ea/
│   ├─ dsh_JSB30.mq5 / .ex5
│   ├─ JSB30_N1_frozen_hashes.sha256        ★冻结哈希
│   ├─ JSB30_data_availability_probe.md     ★M1 起点实测
│   └─ probe_m1_start.py
├─ smoke/
│   ├─ JSB30_N1_5_smoke_report.md           ★smoke 报告
│   └─ DS260914_JSB30_SMOKE_V1/
└─ N1_5_smoke.py

deepseek数据保存/mql5/dshtools/
├─ dsh_JSB30.mq5        ★新 EA（34,860 B / E3E80B29…）
└─ dsh_JSB30Probe.mq5   只读数据探针
```

### 4.1 冻结哈希

```
源码  E3E80B296AC82B560C56C949D3DC3E3FEEF5511E33B27B58D3E8E36C71235A69
      dsh_JSB30.mq5   34,860 B
EX5   7559C19F1FB87ED62C23EDBB30D7840A8BD11FC4E189F64E89A561C34905B45D
      dsh_JSB30.ex5   40,212 B
编译  0 errors / 0 warnings（MetaEditor64, MT5 build 6184）
```

---

## 5. 下一步（等裁定）

```
Q5 裁定后：
  · 若选 C（2018-01-02 起）或 D 补数据成功 → 我立即按 §6 串行跑 V1/V2/V3 TRAIN
  · 每个 TRAIN 后立即出：HTML 原报告 / trade audit / reject audit / manifest actual /
    reconciliation / result report / 逐年统计 / 2014–2016 静默诊断 / 成本压力 / 去尾诊断
  · 触发任一停止条件 → 标 blocked_failed/closed，不跑其 VALID
  · 只有 TRAIN 通过者才跑 VALID（2024-06-01 ~ 2025-05-31）
  · N3 后停止，提交最终审阅包
```
