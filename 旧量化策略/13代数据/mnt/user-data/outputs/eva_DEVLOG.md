# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG，本轮代际 = eva014）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 本轮：解决"找不到 volscan 在哪开/关"——把流水线的"总开关"做得一目了然。
> **本轮产物 = eva014**：`eva014_data_pipeline.py`（仅澄清/注释改动）。**EA 与 .set 本轮未改，仍是 eva013**。

---

## ★ 怎么开/关 volscan（你这次的问题）
- 流水线**只有一个总开关 = 最上面的 `MODE` 变量**。改它的字符串 = 切换功能；没有别的开关。
- **打开 volscan**：把 `MODE = "enrich"` 改成 **`MODE = "volscan"`** → 点 Run。
- **关闭 / 跑别的**：把 `MODE` 改回 `"enrich"`（或其它模式）即可。
- volscan 的扫描区间在 `VOLSCAN_START / VOLSCAN_END`（默认训练窗口）；窗口列表 `VOLSCAN_WINDOWS`（对应 EA 的 `InpVolWindowMinutes`）。
- 结果：控制台直接打印"百分比波动"的各分位 + 阈值建议；明细写到 `enriched/volscan_summary.csv`。

> 之所以之前难找：开关藏在一行注释里、且文件顶部说明还停留在旧版没提 volscan。本轮已在顶部加了醒目的"怎么用"说明 + 在 `MODE` 行上下加了 `↓↓↓ 总开关 ↑↑↑` 提示。

---

## 1. 此前摘要（压缩）
- 风控（eva010/011）：趋势门控离场 + 浮亏熔断；浮亏峰值 $339→$200，但样本外接近打平 → 根问题=参数过多 + 波动率归一化方式不对。
- 走方案 B（稳健参数/walk-forward），前提先降维。
- eva013：**百分比波动判档成为唯一方法**，删净旧的长短比值/固定RV/价格缩放及其全部参数；窗口输入改名 `InpVolWindowMinutes`；新增 `volscan` 量化真实%范围；修 m1 时间戳 bug。

---

## 2. 本轮代码改动（changelog）

### eva014_data_pipeline.py（仅可读性/注释，逻辑零改动）
- **改了什么**：
  1. 重写文件顶部 docstring：清楚列出全部 MODE 选项，并写明"改 `MODE` 字符串来切换；跑 volscan 就写 `MODE="volscan"`、跑完改回 `"enrich"`"。
  2. 在 `MODE` 行**上下各加一行醒目提示**（`↓↓↓ 总开关 ↓↓↓` / `↑↑↑ 例 ↑↑↑`），让人一眼看到这就是开关。
  3. 修正 volscan 配置区注释里的旧参数名（`InpRVShortMinutes` → `InpVolWindowMinutes`），并标注这些配置"仅当 `MODE="volscan"` 时生效"。
- **为什么改**：你反馈找不到 volscan 在哪开/关。功能本就在（eva013 已加），是入口不显眼。
- **没改什么**：volscan/enrich/followup 等所有计算逻辑**一字未动**；`py_compile` 通过，volscan 合成数据回归一致。

> 注：EA（`eva013_VolumetricPulseGrid_StateMachine.mq5`）与参数（`eva013.set`）**本轮未改**，继续用 eva013 的版本。

---

## 3. 完整操作清单（从这里照做即可）
1. **编译** `eva013_VolumetricPulseGrid_StateMachine.mq5`（MetaEditor，有报错贴我）。
2. **跑 volscan 量真实%范围**：
   - 打开 `eva014_data_pipeline.py`；
   - 把 `MODE` 改成 `"volscan"`；
   - 确认 `ROOT="eva_data"`、`SYMBOL="XAUUSDm"` 指向你的行情仓库，`VOLSCAN_START/END` = 训练窗口；
   - 点 Run，看控制台输出的"百分比波动各分位 + 阈值建议"。
3. **把建议值填进 `eva013.set`** 的 `InpVolPct_MidToLow/LowToMid/HighToMid/MidToHigh`（替换占位范围），`InpVolWindowMinutes` 取 volscan 里看起来最稳的窗口。
4. 把 `MODE` 改回 `"enrich"`（volscan 用完即关）。
5. **在训练窗口（2025-01-01→2026-04-24）寻优** 这 4 个 `InpVolPct_*`，结果发我，对比 eva011。
6. 我接着做 **R2（绝对波动定间距）** 与 **新 `OnTester` 评分（类夏普 + 浮亏惩罚 + 盈利段占比）**，并可搭 Python walk-forward 编排器。

---

## 4. 代码 / 参数 changelog（历代）
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva010 | EA + .set | 趋势门控 + pacing 开关 + 浮亏熔断 + 趋势止损放宽 |
| eva011 | .set | 关独立趋势单，隔离网格本体 |
| eva012 | EA + .set | 引入百分比波动判档（带开关，过渡版）|
| eva013 | EA + .set + pipeline | 删净旧判档法与全部旧参数；窗口改名 `InpVolWindowMinutes`；新增 volscan；修 m1 时间戳 bug |
| **eva014** | **pipeline** | 仅澄清 volscan/MODE 的开关入口（顶部说明 + `↓↓↓总开关↑↑↑` 提示 + 注释修正）；逻辑零改动。EA/.set 沿用 eva013 |

---

*本日志随版本更新；代际默认进位（除非你说不进位）。代码/参数改动在 §4 追加。*
*（以上为基于回测数据的工程与分析，不构成投资建议；改动后务必在测试器充分验证。）*
