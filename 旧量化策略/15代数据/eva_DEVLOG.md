# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG，本轮代际 = eva017）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 本轮：**正面回应"局部乱改、逻辑混乱"的批评** —— 把策略架构讲清楚，承认 eva016 的错误，按"统一模型"重搭（取消三档切换）。
> **本轮产物 = eva017**：`eva017_VolumetricPulseGrid_StateMachine.mq5` + `eva017.set`。

---

## ★ 先承认问题（你点 3）
- eva016 跑出 **28626 笔、净 −$3963（$4000 几乎亏光到 $37）**，且所有寻优结果几乎一致。**你的判断对：这是局部乱改，不是连贯设计。**
- 根因：我只把"网格间距"波动化了，**止盈、基线、三档切换都没动** → 自相矛盾：低波动时 RV 小 → 网格距变小 → 在微小波动上疯狂开平 → 28000 笔 churn 被点差吃死（regime 0 低波动就 20190 笔、亏 −$2941）。

---

## 1. 这个策略到底是什么（先把内在含义讲清楚——你点 2）
**它是"基线均值回归 + 马丁格网"策略**：
- 有一条**基线** `G_Baseline`（近 N 分钟均价）。价格跌破基线一个"网格间距"→ 开多（赌回归）；继续跌 → 按马丁加多（间距×`grid_exp_coef^count`、手数×`multiplier`）。空头对称。
- **出场主要靠"价格回到基线"（`grid_tp_baseline_revert`）**；`base_profit`（旧 $86~588）是个几乎不触发的止盈上限，不是真正出场点。
- **赚钱条件**：价格围绕一条稳定基线来回震荡（区间） → 网格反复收割小回归。
- **亏钱条件**：价格单边趋势走开 → 马丁不断加亏损单 → 浮亏堆积/爆仓。
- **波动档位的作用**：高波动=震荡幅度大 → 网格收割得动；低波动=价格几乎不动 → 小网格只在赚点差的反面 churn；趋势=马丁death。

**关于你问的三件事**：
1. **"还是三个模型吗？现在生效吗？"** 是——旧代码里 `LoadLow/Mid/HighVolParams` 三个函数各硬编码 24 个字段，`UpdateActiveParams` 按档位选一个填进唯一的 `G_ActiveParams`。**eva016 及以前它们都在生效**（我只覆盖了其中"网格间距"的用法，所以才矛盾）。
2. **"恐慌保护上轮去了这轮又加回来？"** 是我没说清，对不起：`InpEnablePacingPanic` 是个开关，eva011 关掉(=false)、后来某些 .set 又被设回 true。它**应当保持关闭**（已被趋势门控取代）。
3. **"基线移动你完全没碰"** 对——基线由 `move_points_b/coef_c/coef_decay` 调整，我之前确实没涉及。**你完全说对了：要做就该做一套统一模型，而不是在三档之上贴一个缩放。**

---

## 2. 重新设计：统一波动率模型（你点 2 的正解）
**思路**：所有交易逻辑只读 `G_ActiveParams` 这一个结构体。所以不需要到处改——**只要让 `UpdateActiveParams` 用"一套参数 + 波动缩放"来填它，而不是从三套里选**。三档切换就此作废。

**eva017 统一模型如何填 `G_ActiveParams`**（开关 `InpUnifiedVolModel`，默认 true；false=回旧三档，等于你的"option 2"退路）：
| 字段 | 统一模型怎么定 | 含义 |
|---|---|---|
| `base_grid_z`（网格间距）| `InpUniGridPerVol × 实时绝对波动(RV点)`，并设**下限 `InpUniMinGridZ`** | ∝波动且随价位天然放大；**下限防低波动churn**（修 eva016 的病）|
| `base_profit`（止盈上限）| **单一 `InpUniBaseProfit`（大值，不随网格缩放）** | **保住"回归基线"出场机制**（这是我 eva016 差点又改错的地方）|
| `grid_exp_coef` | 单一 `InpUniGridExpCoef` | 取代三套 |
| `max_total_positions` | 单一 `InpUniMaxPos` | 取代三套 |
| 其余 20 个字段 | 复用"基础"那套单一输入 | 取代三套 |

→ **~6 个统一参数取代了 3×24=72 个硬编码数**；无三档切换；网格随波动连续伸缩、且有下限不再 churn；止盈/基线机制保持原样。

### 关于"价位相关定位"（你点 1，再次澄清）
- `base_grid_z = k × RV点`，而 **RV点 = 百分比波动 × 价位 / point**，所以 **$4000 时的 RV点≈$1000 时的 4 倍 → 网格也≈4 倍**。**它确实随价位放大，不是 1000 和 4000 开一样的网格**（那个担心针对的是"乘百分比"，而我用的是"乘绝对波动点数"）。
- 但你更深的质疑（等比例缩放跨年代仍可能失效）**我同意且未当解决**：绝对波动定位只解决"价位维度"，不保证"跨体制稳健"。这一层留待 walk-forward 检验 + 必要时只做高波动（边缘一直只在 regime 2）。

---

## 3. 本轮代码 changelog
### eva017_VolumetricPulseGrid_StateMachine.mq5（基于 eva016）
- **改了什么**：
  1. 还原 eva016 在下单处的网格缩放 hack（避免双重缩放），删除 `InpUseVolGrid/InpGridZperVol`；
  2. **重写 `UpdateActiveParams`**：新增统一模型分支（`InpUnifiedVolModel`）——`LoadLowVolParams` 填满全部字段后，把 `base_grid_z` 按 `InpUniGridPerVol×RV` 缩放(带下限 `InpUniMinGridZ`)、`base_profit/grid_exp_coef/max_total_positions` 用单一统一值；
  3. 新增统一输入组：`InpUnifiedVolModel / InpUniGridPerVol / InpUniMinGridZ / InpUniBaseProfit / InpUniGridExpCoef / InpUniMaxPos`；
  4. 沿用 eva016 的跨度无关评分。
- **为什么**：eva016 局部缩放导致 churn 爆仓；统一模型把"三套硬编码+切换"降为"一套+波动缩放"，并加网格下限根治 churn，同时保住基线回归出场。
- **自测**：去注释/字符串后括号平衡相对原文件**零净变化**；旧符号残留 0；**MQL5 无法在此编译，请在 MetaEditor 编译，有报错贴我**。

### eva017.set（先单跑验证，不寻优）
- `InpUnifiedVolModel=true`；统一参数给保守默认（`InpUniGridPerVol=1.0`、`InpUniMinGridZ=1500` 防churn、`InpUniBaseProfit=200000`、`InpUniGridExpCoef=1.4`、`InpUniMaxPos=5`）；带 eva011 保护（关趋势单、浮亏熔断200、关pacing）。**全部 N（单跑）**。

---

## 4. 路线建议（你点 3 给的两个选项）
- 我选你的 **option 1 的精神：先把连贯的整套搭好，再调参**——这正是 eva017 做的（一次给出统一模型）。同时保留 `InpUnifiedVolModel=false` 作为 option 2 的退路（一键回旧三档）。
- **诚实预期**：每一版数据都指向同一事实——**边缘只在高波动(regime 2 一直 PF~1.3)，低/中波动一直漏血**。所以统一模型即使把 churn 治好、回撤压住，**天花板很可能仍是"高波动专用、收益温和"**。统一模型的价值是：把它变成一个**可调、可解释、不自相矛盾**的整体，让"到底有没有边缘"能被 walk-forward 干净地检验；若仍只有高波动有效，就坦然走 A（只做高波动）。

---

## 5. 下一步（务必按序，先确认健康再寻优）
1. **编译** eva017（有报错贴我）。
2. **单跑** `eva017.set`（2025-01-01→2026-04-24），**先只看成交数是否回到正常量级**（目标 ~1000~3000，而不是 28000）和是否还爆仓；把全程/训练段 enrich 发我。
3. 若量级正常、不爆仓 → 再寻优 `InpUniGridPerVol / InpUniMinGridZ / InpUniGridExpCoef / InpUniMaxPos`（这次是**有物理含义的少数参数**）。
4. 之后：在新评分下用 **walk-forward + eva015 稳健选参**；并做一次**删码精简 pass**（旧三档 Load 函数、pacing 暴跌检测等可清理）。

---

## 6. 代码 / 参数 changelog（历代）
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva010 | EA+.set | 趋势门控+pacing开关+浮亏熔断+趋势止损放宽 |
| eva011 | .set | 关独立趋势单，隔离网格本体 |
| eva012 | EA+.set | 引入百分比波动判档（过渡）|
| eva013 | EA+.set+pipeline | 删旧判档法与参数；窗口改名；volscan；修m1时间戳 |
| eva014 | pipeline | 澄清 volscan/MODE 开关 |
| eva015 | py | 稳健选参工具（防测试集泄漏）|
| eva016 | EA+.set | （失败）局部把网格间距波动化 → churn爆仓；评分改跨度无关 |
| **eva017** | **EA+.set** | **统一波动率模型**：一套参数+波动缩放填 `G_ActiveParams`，取消三档切换；网格∝绝对波动带下限防churn；止盈/基线机制保持。开关 `InpUnifiedVolModel`(false回旧三档) |

---

*本日志随版本更新；代际默认进位。代码/参数改动在 §6 追加。*
*（以上为基于回测数据的工程与分析，不构成投资建议；改动后务必在测试器充分验证。）*
