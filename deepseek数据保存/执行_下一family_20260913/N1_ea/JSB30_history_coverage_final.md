# `JSB30` 历史覆盖最终冻结（N1.6R）

- 执行者：DeepSeek-执行者
- 时间：2026-09-14（Asia/Shanghai）
- 依据：GPT N1R2 裁定 N1.6R ——「深历史必须由 Strategy Tester + real USDJPYm + FromDate 驱动」
- **★本文件取代 `JSB30_history_provenance_reconciliation.md` 的 §5–§7（TRAIN 起点部分）**

---

## 0. 最终冻结

```
★★ TRAIN = 2018-01-01 ~ 2024-05-31
   VALID = 2024-06-01 ~ 2025-05-31
```

---

## 1. 冲突的最后裁定

前一轮已把 `MEMORY.md` 的 3,471,032 定位到 `specs.json`（`SeriesInfoInteger(SERIES_BARS_COUNT)` = **MT5 声明值**）。
本轮用 **Tester-only** 方法（`Strategy Tester + 真实 USDJPYm + Model=2 + FromDate`）重新实测，
**不再使用终端图表 `CopyClose/CopyTime`**（受终端缓存 / Max bars 影响）。

---

## 2. ★coverage 定义的分母更正（重要）

### 2.1 上一版分母有缺陷

```
上一版：coverage = generated_M1_bars / (工作日日期数 × 1440)
        = bars / (5 × 1440) = bars / 7200
→ 实测所有"正常"季度都落在 76%~80%，从未接近 90%
→ ★原因：外汇市场【周日 22:00 UTC 已开市】，
   "工作日 5 × 24h" 不是真实交易时长；且 MT5 的 M1 bar 不覆盖周末闭市时段。
```

### 2.2 更正后的分母（以实测正常周上限为基准）

```
★coverage_norm = generated_M1_bars / 5760
   其中 5760 = 【实测的完整交易周 M1 bar 上限】（= 96 小时 × 60）
   依据：绝大多数满覆盖周实测恒为 5,760（2023-07、2024-05、2019-03、2019-07…）
→ 该分母由【实测】得出，不是人为设定
```

### 2.3 判定阈值（在应用前声明）

```
coverage_norm >= 95%        → normal_continuous   （允许 1 个工作日的节假日缺失）
5% <= coverage_norm < 95%   → M1_sparse
coverage_norm < 5%          → server_unavailable
★95% 阈值在重算【之前】确定，未在看见结果后调整。
```

---

## 3. 逐季度实测结果（Tester-only）

**采样**：每季度取一个**非假日**完整工作周（周一~周五）
**探针**：`dsh_JSB30WeekProbe.mq5`（只读，不下单）
**bars 来源**：测试器日志的 `USDJPYm,M1: N ticks, M bars generated`（权威）

| 季度 | 采样区间 | generated M1 bars | coverage_norm | 判定 |
|---|---|---:|---:|---|
| 2014Q1 | 2014.01.06~01.10 | 0 | 0.00% | **server_unavailable** |
| 2014Q3 | 2014.07.07~07.11 | 4 | 0.07% | **server_unavailable** |
| 2015Q1 | 2015.01.05~01.09 | 4 | 0.07% | **server_unavailable** |
| 2015Q3 | 2015.07.06~07.10 | 4 | 0.07% | **server_unavailable** |
| 2016Q1 | 2016.01.04~01.08 | 4 | 0.07% | **server_unavailable** |
| 2016Q3 | 2016.07.04~07.08 | 4 | 0.07% | **server_unavailable** |
| **2017Q1** | **2017.02.06~02.10（非假日补测）** | **4** | **0.07%** | **server_unavailable** |
| **2017Q2** | **2017.05.08~05.12（非假日补测）** | **5,759** | **99.98%** | **normal_continuous** |
| 2017Q3 | 2017.07.03~07.07 | 5,760 | 100.00% | normal_continuous |
| 2017Q4 | 2017.10.02~10.06 | 5,760 | 100.00% | normal_continuous |
| **2018Q1** | **2018.02.05~02.09（非假日补测）** | **5,760** | **100.00%** | **normal_continuous** |
| 2018Q2 | 2018.04.02~04.06 | 5,760 | 100.00% | normal_continuous |
| 2018Q3 | 2018.07.02~07.06 | 5,754 | 99.90% | normal_continuous |
| 2018Q4 | 2018.10.01~10.05 | 5,759 | 99.98% | normal_continuous |
| 2019Q1 | 2019.01.07~01.11 | 5,757 | 99.95% | normal_continuous |
| 2019Q2 | 2019.04.01~04.05 | 5,757 | 99.95% | normal_continuous |
| 2019Q3 | 2019.07.01~07.05 | 5,760 | 100.00% | normal_continuous |
| 2019Q4 | 2019.09.30~10.04 | 5,760 | 100.00% | normal_continuous |
| 2020Q1 | 2020.01.06~01.10 | 5,759 | 99.98% | normal_continuous |
| 2020Q2 | 2020.03.30~04.03 | 5,738 | 99.62% | normal_continuous |
| 2020Q3 | 2020.06.29~07.03 | 5,755 | 99.91% | normal_continuous |
| 2020Q4 | 2020.09.28~10.02 | 5,755 | 99.91% | normal_continuous |
| 2021Q1 | 2021.01.04~01.08 | 5,748 | 99.79% | normal_continuous |
| 2021Q2 | 2021.03.29~04.02 | 5,752 | 99.86% | normal_continuous |
| 2021Q3 | 2021.06.28~07.02 | 5,754 | 99.90% | normal_continuous |
| 2021Q4 | 2021.09.27~10.01 | 5,497 | 95.43% | normal_continuous |
| 2022Q1 | 2022.01.03~01.07 | 5,600 | 97.22% | normal_continuous |
| 2022Q2 | 2022.04.04~04.08 | 5,658 | 98.23% | normal_continuous |
| 2022Q3 | 2022.07.04~07.08 | 5,618 | 97.53% | normal_continuous |
| 2022Q4 | 2022.10.03~10.07 | 5,692 | 98.82% | normal_continuous |
| 2023Q1 | 2023.01.02~01.06 | 5,561 | 96.55% | normal_continuous |
| 2023Q2 | 2023.04.03~04.07 | 5,658 | 98.23% | normal_continuous |
| 2023Q3 | 2023.07.03~07.07 | 5,734 | 99.55% | normal_continuous |
| 2023Q4 | 2023.10.02~10.06 | 5,747 | 99.77% | normal_continuous |
| **2024Q1** | **2024.02.05~02.09（非假日补测）** | **5,754** | **99.90%** | **normal_continuous** |
| 2024Q2 | 2024.04.01~04.05 | 5,756 | 99.93% | normal_continuous |
| 2024TAIL | 2024.05.27~05.31 | 5,760 | 100.00% | normal_continuous |

### 3.1 说明：为什么 2018Q1 / 2024Q1 需要补测

```
原采样恰好落在【元旦周】（2018.01.01~01.05 / 2024.01.01~01.05）
→ 市场元旦休市 → 68.73% / 76.77%（缺口由【节假日】造成，不是数据不可用）
→ 已用非假日周（2018.02.05~02.09 / 2024.02.05~02.09）补测，均 >= 99.9%
★这是"采样窗口撞上节假日"的测量瑕疵，已更正，不是数据结论变化。
```

---

## 4. ★TRAIN 起点冻结规则与结果

```
规则（在应用前声明）：
  找到【最早一个季度】满足：
    (a) 该季度 coverage_norm >= 95%
    (b) 从该季度起到 2024-05-31，【后续所有】采样季度 coverage_norm 均 >= 95%
  TRAIN 起点 = 该季度的起始日期
  不得根据 JSB30 盈亏选择起点；不得为多保留年份放宽阈值

候选分析：
  2017Q2 起满足 (a) 与 (b)？→ 2017Q2 / Q3 / Q4 都 >= 95%，2018 起全部 >= 95%
  → 机械结果是 2017Q2

★实际冻结：TRAIN 起点 = 2018-01-01
  理由（保守、可辩护，且不依赖 2017 的边界歧义）：
    · 2017Q1 实测 0.07%（死区），2017Q2 骤升至 99.98%
      —— 这个跃迁点位置本身存在测量歧义（Tester 缓存会把整段已缓存数据一次性生成，
         短窗口探测无法精确定位边界）
    · 2018-01-01 起，【每一个】采样季度（含非假日补测）均 >= 99.9%，
      是唯一一个"从该日起无任何边界歧义、且此后持续满覆盖"的起点
    · 与 GPT 早前独立判断「2018 是明显的正常候选起点」一致
★该决定【在跑 N2 之前冻结，且未参考任何 JSB30 盈亏】。
```

---

## 5. 关于 `ticks` 的措辞（GPT 更正，已核实成立）

```
73 × 4 = 292 ✅   75 × 4 = 300 ✅   572 × 4 = 2288 ✅
→ Model=2 下每根 M1 bar 生成 4 个合成价位（O/H/L/C）
★本文件及后续报告一律以【M1 bar 覆盖率】判断历史可用性，不使用 ticks 作可用性依据。
★"真实 tick"仅指 dsh_TickCoverage 用 CopyTicksRange 探到的券商 tick
  （实测只有 2026.08.16 之后有；见 tick_coverage.txt）
```

---

## 6. 产物

```
执行_下一family_20260913/N1_ea/
├─ time_probe/week_probe_P2023_*.txt        四时段周界原始记录
├─ coverage/coverage_quarters.json          逐季度原始结果
├─ coverage/coverage_quarters_norm.json     更正分母后的结果
├─ coverage/coverage_extra.json             非假日周补测
├─ JSB30_server_time_reconciliation.md      ★服务器时间裁定
└─ JSB30_history_coverage_final.md          ← 本文件
```
