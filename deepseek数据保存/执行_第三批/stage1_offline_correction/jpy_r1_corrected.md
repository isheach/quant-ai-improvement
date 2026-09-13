# Step 1 · R1 更正报告（USDJPY 六次控制回测）

**解析器**：`执行_第三批\mt5_html_parser.py` v1（按 `<tr>/<td>` 单元格成对解析，非模糊正则）

**性质**：本文件是对 `执行_20260912\stage2_usdjpy_pnl_r3\jpy_r3_reconciliation.md` 的**更正**；
原报告与原 CSV **不改写**，原哈希见 §3。

## 1. ★更正的核心结论

我原报告写「逐笔 6/6 达 100%、报告 closing deal 与审计一一对应」——**这四行是错的**。

逐层复核后发现：**4 个 run 各缺一行 `end of test` 强制平仓 deal**。

| run_id | HTML Trades | HTML Deals | HTML out 行 | 审计行 | 缺 | end-of-test 行 | 差额 USD | 审计净 | 报告净 | 判定 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `DS260913_JPYR3_LONG_A` | 403.0 | 806.0 | 403 | 403 | **0** | 0 | — | -48.49 | -48.49 | 一致 |
| `DS260913_JPYR3_LONG_B` | 403.0 | 806.0 | 403 | 403 | **0** | 0 | — | -48.49 | -48.49 | 一致 |
| `DS260913_JPYR3_SHORT_A` | 399.0 | 798.0 | 399 | 398 | **1** | 2 | -0.70 | -78.54 | -79.24 | ★审计缺 1.0 行 |
| `DS260913_JPYR3_SHORT_B` | 399.0 | 798.0 | 399 | 398 | **1** | 2 | -0.70 | -78.54 | -79.24 | ★审计缺 1.0 行 |
| `DS260913_JPYR3_PARTIAL_A` | 791.0 | 1581.0 | 791 | 790 | **1** | 2 | -0.70 | -105.38 | -106.08 | ★审计缺 1.0 行 |
| `DS260913_JPYR3_PARTIAL_B` | 791.0 | 1581.0 | 791 | 790 | **1** | 2 | -0.70 | -105.38 | -106.08 | ★审计缺 1.0 行 |

## 2. 更正后的判定

```
完整一致（HTML Trades == 审计行）: 2 / 6
  ★ DS260913_JPYR3_SHORT_A 缺 1 行 end-of-test 平仓，净利差 -0.70 USD
  ★ DS260913_JPYR3_SHORT_B 缺 1 行 end-of-test 平仓，净利差 -0.70 USD
  ★ DS260913_JPYR3_PARTIAL_A 缺 1 行 end-of-test 平仓，净利差 -0.70 USD
  ★ DS260913_JPYR3_PARTIAL_B 缺 1 行 end-of-test 平仓，净利差 -0.70 USD
→ 原报告「逐笔 6/6 一一对应」更正为【2/6 完整一致、4/6 缺结束平仓】
→ JPY 维持 blocked_mapping（严格汇总容差 max(0.02, 0.1%%×|net|) 不变）
→ 状态统一改标 audit_reconcile_required / blocked_mapping
```

**★我的原判定为什么错**：
```
我的 r1_exec.py 条件②实际只检查了「审计内部公式逐笔通过」，
没有解析 HTML 的 closing-deal 集合 → 无法发现审计【少了整行】。
逐笔残差小（中位 0.0026 USD）并不能抵销【汇总漏记 0.70】。
→ 这正说明四方对账必须真的做四方，缺一方就会漏掉「整行缺失」这类错误。
```

## 3. 原文件哈希（保留以便追溯，未改写）

| 文件 | SHA-256 |
|---|---|
| `DS260913_JPYR3_LONG_A/report.htm` | `42F630F426B30562A61D344395AF3274EC917AC32195B0F3F8635F7E10C5995F` |
| `DS260913_JPYR3_LONG_A/trades.csv` | `10FFE5C5693BAE641175F47B1CD704E1171C5329E46E49AF70CE1A9C4E95B9F9` |
| `DS260913_JPYR3_LONG_B/report.htm` | `70607ED0B5E1A3390571C016D1360FF74FE57EADBF719EFC06BCFCE380DBF6AD` |
| `DS260913_JPYR3_LONG_B/trades.csv` | `3E3B24C85106A84E55B469B408FEAF3A3C89F13C0BB6AC54742B2DE3B7EB5A81` |
| `DS260913_JPYR3_SHORT_A/report.htm` | `A6819D3E4ABD77B76F1D8C49D22AB91D8B283F4FCD31EB99B1E627C865105E19` |
| `DS260913_JPYR3_SHORT_A/trades.csv` | `E83C9A993ECBCBB622EFE17F39B9D27B91E372AF284F40662DA55CF8603E2C27` |
| `DS260913_JPYR3_SHORT_B/report.htm` | `34BC8C149C4B73E84BF34A01ACF0013089D624C7CC01428B7873539E24609196` |
| `DS260913_JPYR3_SHORT_B/trades.csv` | `AA549D656C86CA2D2566C49323B65E67D9F4211F8F67FDD71A20A943413B7ACA` |
| `DS260913_JPYR3_PARTIAL_A/report.htm` | `4421F8E439854620ABAA62406A5E473B1A35F88B5201E9C0EA1C9E8B0042AF40` |
| `DS260913_JPYR3_PARTIAL_A/trades.csv` | `C04060007C157341E63B1748792EAE2C31A4CCB77E968BE258D1517951EE075D` |
| `DS260913_JPYR3_PARTIAL_B/report.htm` | `4B878DC4E154608BC0FE8646E5AE115EC27B63D4DAC64A0C56F0C73501F186C5` |
| `DS260913_JPYR3_PARTIAL_B/trades.csv` | `F78C42E34370555824A1F0B4502F83B12767DDF9295A8C3E6CD37E279D5D654D` |

