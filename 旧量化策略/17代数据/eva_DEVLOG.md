# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG，本轮代际 = eva018）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 本轮：按确认的设计交付**真·统一模型**——删三档、唯一一套参数、距离按"占价% × 价 × 波动^指数"缩放（你的指数主意）。
> **本轮产物 = eva018**：`eva018_VolumetricPulseGrid_StateMachine.mq5` + `eva018.set`。

---

## ★ 已确认的设计（你上轮拍板 + 本轮补充）
1. `base_profit` 保留**单一大值**（=200000，中档；反正主要靠回基线出场）。
2. **删判档"切参数"**：三档不再驱动参数（分类器仅保留算 rv_pct，`RegimeMode=AUTO` 下对开仓零影响）。
3. **彻底删三档参数集**（中/高输入 + Load 函数）。
4. **指数缩放（你的好主意）**：每个距离参数 = `占价%/100 × 当前价 × (当前波动%/参照波动%)^指数`。指数 0=不随波动（纯价格缩放）、1=线性、2=平方，可填小数。

---

## 1. 交易逻辑（已与你对齐的精确版，供查阅）
- **基线**：近 `x_minutes` 均价；每分钟 `AdjustBaseline`——空仓时以 `move_points_b`/分钟追价（慢漂移追上→不开单避险）；持仓时朝净仓方向移动 `Σ coef_c×coef_decay^i`。**三基线参数齐全**：`move_points_b`(空仓追价)、`coef_c`(持仓移动基数)、`coef_decay`(每新增一仓的衰减影响系数)。
- **网格**：价偏离基线一个"网格距"开回归单，继续偏离按马丁加仓（距×`grid_exp_coef^仓数`、手数×mult）；主出场=**回到基线**。
- **趋势反制**：状态机确认单边→平逆势网格 + 顺势开趋势单（独立 magic、ATR 移动止损）。

---

## 2. 本轮代码 changelog（eva018，基于 eva017）
**(A) 真·统一模型（删三档，唯一一套参数）**
- 重写 `UpdateActiveParams`：只用一套参数（`LoadLowVolParams` 填基础 24 字段），再把**三个距离类字段**按指数公式缩放：
  \[
  \text{距离(价)}=\frac{\text{Pct}}{100}\times\text{当前价}\times\Big(\frac{\text{当前波动\%}}{\text{InpRefVolPct}}\Big)^{\text{exp}},\quad \text{点数}=\text{距离}/point
  \]
  作用于 `base_grid_z(InpGridPct,InpGridVolExp)`、`move_points_b(InpMovePct,InpMoveVolExp)`、`coef_c(InpCoefCPct,InpCoefCVolExp)`。`base_profit/grid_exp_coef/max_total_positions` 用单一 `InpUni*`；其余字段沿用单一基础值。
- **删除**：`LoadMidVolParams`、`LoadHighVolParams`（定义+前向声明）；**中/高波动全部输入（54 行）**；同步修了数据窗口计算、run_config 写盘（low/mid/high 列→统一列）。
- **价格 vs 波动分离（回应你点 1）**：公式里**价格显式在内**（`×当前价`），所以 $1000/$4000 自动按比例放大（不再"开一样的网格"）；波动影响由**指数**控制、**默认 0=不启用**（先纯价格缩放跑通，符合你"先不引入波动"的偏好）。
- **指数捕捉旧三档规律**：你观察的 `base_grid_z`(100/350/700)≈随波动^2.7、`move_points_b`(93/130/175)≈^0.8（两者差≈2，正是你看到比值像平方的原因）。要引入波动时把 `InpGridVolExp≈2.7`、`InpMoveVolExp≈0.8` 即可，且可优化。
- **分类器**：仅保留计算 rv_pct（喂给缩放公式）；`InpRegimeMode=AUTO` 下对开仓零影响。其残留判档逻辑可在下一轮纯无害清理时删（不影响本轮行为）。
- **自测**：去注释/字符串后括号平衡相对原文件**零净变化**；`InpMid/InpHigh` 残留 **0**；删 114 行。**MQL5 无法在此编译，请在 MetaEditor 编译，有报错贴我**。

**(B) eva018.set（先单跑验证，不寻优）**
- `InpRegimeMode=0(AUTO)`；指数全 0（纯价格缩放）；距离%默认 `Grid 0.00875 / Move 0.00325 / CoefC 0.00158`（在 ~$4000 时约等于旧"中档"的 base_grid_z=350、move=130、coef_c=63）；`InpUniBaseProfit=200000`、`ExpCoef=1.4`、`MaxPos=5`；带 eva011 保护（关趋势单、浮亏熔断200、关 pacing）。全部 N。

---

## 3. 下一步（先验健康再调）
1. **编译** eva018（有报错贴我）。
2. **单跑** `eva018.set`（2025-01-01→2026-04-24），**先只看**：成交数是否正常量级（~1000~3000，不是 2 单也不是 28000）、是否爆仓、网格是否在开。把 enrich 发我。
3. 健康后：
   - 先调 `InpGridPct / InpMovePct / InpCoefCPct`（纯价格缩放下的基准距离）；
   - 再决定是否引入波动：把 `InpGridVolExp/InpMoveVolExp` 设非 0（经验≈2.7 / 0.8）寻优，看是否更好；
   - 之后用新评分 + walk-forward + eva015 稳健选参。
4. 下一轮纯清理：删判档分类器残留逻辑（无害）。

> 提醒：`InpGridPct` 与 `InpMovePct` 的**比值**决定开单频率（网格距 vs 追价速度）。默认比值≈2.7（0.00875/0.00325），近似旧"中档"。若单跑几乎不开单→调小 `InpGridPct` 或调大 `InpMovePct`；若开太多→反之。

---

## 4. 代码 / 参数 changelog（历代）
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva010~015 | … | 风控/判档/工具（见旧日志）|
| eva016 | EA+.set |（失败）局部网格波动化→churn |
| eva017 | EA+.set |（失败）统一模型未删三档=四不像；只开2单 |
| **eva018** | **EA+.set** | **真·统一模型**：删三档(中/高输入+Load函数)，唯一一套参数；距离=占价%×价×波动^指数(指数0=纯价格缩放)；分类器仅留算rv_pct |

---

*本日志随版本更新；代际默认进位。代码/参数改动在 §4 追加。*
*（以上为工程与分析记录，不构成投资建议；改动后务必在测试器充分验证。）*
