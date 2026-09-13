# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG，本轮代际 = eva013）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 本轮：①彻底移除旧的"长短比值/固定RV/价格缩放"判档与其参数（你点 1）；②新增 `volscan` 工具直接量出训练集内"百分比波动"的真实范围（你点 2/3）；③澄清窗口输入；④回应你对"等比例缩放在过去失效"的质疑（点 4 的疑问）；⑤细化评分思路（点 5）。
> **本轮产物 = eva013**：`eva013_VolumetricPulseGrid_StateMachine.mq5` + `eva013.set` + `eva013_data_pipeline.py`（含 volscan）。

---

## ★ 约定 / 长期事实
- 代际命名 = 每轮所有产物整体进位。训练窗口 = **2025-01-01 → 2026-04-24**。
- 参数一律写**完整英文变量名 + 中文释义**；回测固定手数、不开复利。

---

## 1. 此前摘要（压缩）
- 风控（eva010/011）：趋势门控离场 + 浮亏熔断；浮亏峰值 $339→$200，但样本外接近打平 → 根问题=参数过多 + 波动率归一化方式不对。
- 选方案 B（稳健参数/walk-forward），前提先降维：R1（换波动率度量）已在 eva012 引入（带开关）。

---

## 2. 本轮代码改动（changelog）

### eva013_VolumetricPulseGrid_StateMachine.mq5
- **R1 收尾：百分比波动判档成为唯一方法，旧方法整套删除（你点 1）**
  - `UpdateVolatilityRegime` 改为只用 `rv_pct = 100 × RV(点) × point / 价位`（尺度无关）+ 绝对%阈值 `InpVolPct_*` 判档；四阈值方向滞后逻辑不变。
  - **删除的参数/函数**：`InpUsePctVolRegime`（开关，已无需要）、`InpRVRatio_MidToLow/LowToMid/HighToMid/MidToHigh`、`InpUseFixedLongRV`、`InpFixedLongRVPoints`、`InpFixedLongRVRefPrice`、`InpRVHighAbsPoints`、`InpRVLongMinutes`，以及 `GetEffectiveFixedLongRV()` 函数。同步改了 OnInit 顺序校验、数据窗口计算、run_config 写盘的表头与值（旧vol列→新%列）。
  - **窗口输入重命名（你点 3a）**：`InpRVShortMinutes` → **`InpVolWindowMinutes`**（含义：算百分比波动用多少根 M1，即多少分钟）。这就是你"没找到"的窗口输入——之前叫 RVShort，现在名字明确。太小噪声大、太大滞后，可纳入寻参。
  - 自测：去注释/字符串后括号平衡相对原文件**零净变化**；旧符号残留 0；**无法在此编译 MQL5，请在 MetaEditor 编译，有报错贴给我**。

### eva013_data_pipeline.py
- **新增 `MODE="volscan"`（你点 2/3 的核心）**：用与 EA 完全一致的公式，扫训练集内每分钟的"百分比波动"，输出各分位(min/p5/p50/p95/max)、对多个窗口 W 做敏感性、并给出 `InpVolPct_*` 阈值建议与寻参范围。**这能直接告诉你数据的真实上下界**，避免阈值定到数据范围之外（那会导致判档恒定一档、你"怎么调都没变化"）。
  - 新 CONFIG：`VOLSCAN_START/END`（默认训练窗口）、`VOLSCAN_WINDOWS=[10,15,30,60]`（对应 `InpVolWindowMinutes`，看窗口敏感性）。输出 `volscan_summary.csv`。
- **顺手修了一个时间戳 bug**：m1 读取里 `to_datetime(...).astype(int64)//10**6` 在 pandas 2.x 下分辨率不定、换算错（会得到 1970 年）；统一改为 `.astype("datetime64[ms]")`。影响 m1 路径相关计算（含 enrich 的 m1 回退、volscan）。

### eva013.set
- 删掉 EA 已移除的旧 vol 参数；加入 `InpVolWindowMinutes` 与 4 个 `InpVolPct_*`（带寻参范围）+ 打开 `InpEnableVolRegimeLog`。
- ⚠ **里面的%阈值是占位估计，务必先跑 volscan，用其输出替换这些范围**（见 §5 操作）。

---

## 3. 关于"判档用%、间距用绝对波动"——回应你的质疑（点 4 的疑问）
- **你质疑得对**：等比例（按价位线性）缩放**不能排除"过去狠狠失效"的可能**。我之前"乘价位就自动搞定"的说法**只对"价位维度"成立**（$4000 同%波动给 4 倍绝对波动，这部分没错），但**不解决"跨年代/跨体制"的稳健性**——因为不同年代的微观结构、点差、跳空、均值回归强度都不同，任何波动率归一化都救不了这层。
- 两个有用的区分：
  1. 你旧方法用的是**手工固定的长周期RV值**再按价缩放；R1/R2 用的是**实时波动**(live RV)，本身就比固定值更能适配当下体制——这是改进，但**不是终点**。
  2. "跨年代是否还有边缘"这件事，**不该靠更聪明的乘数去赌**，而应靠 **walk-forward 显式检验** + 必要时**只在有边缘的体制交易（方案A）**。
- **现在先这么处理**（live 绝对波动定间距），把"更高明的方法"列为后续课题（候选：用 ATR 分位/波动的分位归一、或把策略边缘做得不那么依赖绝对间距）。我同意你的判断，不把它当已解决。

---

## 4. 评分指标：你的"滚动求标准差最小"思路（点 5）
- **你的直觉对**：把训练集按"每几天"滚动算一个数值，让它的**标准差尽量小** = 追求一致性、压制"靠某一段赚"。
- **小修正（避免一个坑）**：只最小化标准差，可能选出"一直不赚/小亏但很稳"的解。更稳的是做成**类夏普**：
  \[
  \text{score}=\frac{\text{mean}(\text{每段收益})}{\text{std}(\text{每段收益})}
  \]
  —— 同时奖励"高"与"稳"。进一步可用**下行波动**(Sortino，只罚亏损段)或**盈利段占比**。
- 这块我会在 R2 之后改进 `OnTester`：用"每段收益的类夏普 + 最大权益回撤(含浮亏)惩罚 + 盈利段占比"，直接对准你点 5 的过拟合。

---

## 5. 下一步操作（务必按序）
1. **编译** eva013 EA（有报错贴给我）。
2. **先跑 volscan**：`eva013_data_pipeline.py` 设 `MODE="volscan"`、确认 `ROOT/SYMBOL` 指向你的行情仓库、`VOLSCAN_START/END` = 训练窗口 → Run。读控制台输出的**百分比波动真实范围**与**阈值建议**。
3. **把 volscan 的建议值/范围填进 `eva013.set`** 的 `InpVolPct_*`（替换我给的占位范围），同时可把 `InpVolWindowMinutes` 设成 volscan 里看起来最稳的窗口。
4. **在训练窗口寻优** `InpVolPct_*`（4 个），看新判档下样本内/外表现；把结果发我，对比 eva011。
5. 我接着做 **R2（绝对波动定间距，降维核心）** 与 **新 `OnTester` 评分**，并可搭 Python walk-forward 编排器。

---

## 6. 代码 / 参数 changelog（历代）
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva010 | EA + .set | 趋势门控 + pacing 开关 + 浮亏熔断 + 趋势止损放宽 |
| eva011 | .set | 关独立趋势单，隔离网格本体 |
| eva012 | EA + .set | 引入百分比波动判档（带开关，过渡版）|
| **eva013** | **EA + .set + pipeline** | **删净旧判档法与其全部参数**（`InpVolPct_*` 成唯一）；窗口改名 `InpVolWindowMinutes`；新增 **volscan** 量化真实%范围；修 m1 时间戳 bug |

---

*本日志随版本更新；代际默认进位。代码/参数改动在 §6 追加。*
*（以上为基于回测数据的工程与分析，不构成投资建议；改动后务必在测试器充分验证。）*
