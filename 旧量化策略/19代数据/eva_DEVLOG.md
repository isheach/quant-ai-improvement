# eva 量化策略可审计化 / 数据流水线 —— 开发日志（eva_DEVLOG，本轮代际 = eva020）

> 标的：XAUUSDm（Exness 黄金，point=0.001），平台 Exness / MT5。
> 本轮：基于你跑的 eva019.1.set 结果，删 `pacing_panic` 熔断、给网格加最小距下限、把验证过的好默认值固化进 EA、清理注释与并组。
> **本轮产物 = eva020**：`eva020_VolumetricPulseGrid_StateMachine.mq5` + `eva020.set`（仅寻优用，跑一遍不需要）。

---

## 1. eva019 回测分析回顾（结论指向本轮改动）
- 1382 笔、净 −$276、PF 0.76；月度亏损平稳、无爆雷 → **框架稳定，问题在机制/参数**（与你判断一致）。
- **出场拆解（关键）**：
  | 出场 | 笔数 | 净利 |
  |---|---|---|
  | pacing_panic_stop | 714 | **−$867.8** |
  | grid_tp_baseline_revert（核心盈利） | 576 | **+$835.4** |
  | cutoff_line_stop | 78 | −$207.6 |
  | 其余 | 14 | −$36 |
- 核心回归机制本是盈利的（+$835）；亏损几乎全由 `pacing_panic_stop` 造成（−$868）。去掉它，其余净 = **+$591.6**。

---

## 2. 本轮针对你 5 点的处理（eva020）

### 点 1 / 点 2 —— 删 `pacing_panic`（你记忆正确，已被趋势替代）
读源码确认 `pacing_panic` 的真实逻辑（函数 `CheckAddPacingAndMaybePanic`）：当某侧已有持仓、且在"加仓延迟时间窗"内，若价格**已经冲过"下一单 + 下下单"的位置**，就判定为单边、**全平 + 进冷静期**。这正是你说的"用很短时间冲到开下一单位置来确立单边、然后止损"的老机制——它**没有开关**（源码里无 `InpEnablePacingPanic`，是硬编码），所以你找不到关闭窗口、也一直在生效。
- **改动**：删除该熔断分支；函数更名 `CheckAddPacingDelay`，**只保留"加仓延迟门闸"**（未到延迟时间→暂不加仓，不再全平）；删 `ADD_PACING_PANIC` 枚举值与 OnTick 两处 PANIC 处理。单边行情改由**趋势状态机**识别并平掉逆势网格（你的设计）。
- 预期：原 714 笔 pacing 平仓将主要转为"回归基线获利"或"因网格变宽而不开"，策略由 −$276 量级翻正（保守估计 +$400~+$600，需实跑确认）。

### 点 2 / 点 3 —— 网格最小距下限（**仅随价、不随波动**，正是你要的）
- 你点 3 的判断**部分对、但本例不成立**：`final_grid_distance = base_grid_z × point × multiplier_a × 扩展^n`，`multiplier_a` 确实在乘式里——但源码把它**地板在 1.0**（"倍数不应小于1，避免缩小网格"），数据里 `multiplier_a` 中位 1.17、最大 1.38、≈1 的占 39%。**它只会放大网格、永远不会缩小**。小网格（<100pt 共 235 笔、88.5% 的 multiplier_a=1）的真凶是 **`base_grid_z` 被 `^2.7` 指数在低波动下压塌到 1pt**，`multiplier_a=1` 救不回来。
- **改动**：在 `UpdateActiveParams` 加最小距下限——
  `base_grid_z = max( InpGridZ×(价/参考价)×(波动%/参考%)^指数 , InpMinGridZ×(价/参考价) )`
  下限 `InpMinGridZ` **只随价格缩放、不随波动**（低波动时正好兜住，不让网格塌陷）；高波动时被正常缩放值盖过、不干预。新增输入 `InpMinGridZ`（默认 100，**建议寻优**）。
- 这样即便 `GridVolExp=2.7` 在低波动端，网格也不会低于 `InpMinGridZ × 价格比`，churn 源头被堵住，pacing 删除后也不会乱开。

### 点 3 —— 趋势挣钱效果：**当前数据无法评估**（重要提示）
- eva019 跑的是 `InpEnableTrendOrders=false`，**无任何趋势单**；出场原因里也**没有任何趋势相关平仓**（无 trend_close / trend_state）；所有网格入场时 `market_state=0(震荡)`。
- 原因：趋势确立时逆势网格被门闸挡、顺势网格因"价在基线另一侧"也基本不开 → 网格天然只在震荡里开，所以入场态恒为 0；这**不代表趋势没确立**，但也**看不到趋势机制产生过收益或平过逆势仓**。
- **风险提示**：你删 `pacing_panic` 的前提是"趋势会替代它"，但本回测里趋势机制**零活动迹象**。删除后，真正单边行情中的保护，目前实际落在 **`cutoff_line_stop`（截止线）+ `last_order_stop`（末单）+ 最大持仓=3 的硬上限**上（这些仍保留、够用）。**建议补一次 `InpEnableTrendOrders=true` 的专门验证跑**，看趋势单是否真的盈利、状态机是否真的在切——这样"用趋势替代 pacing"才算被证实。

### 点 4 —— 好默认值固化进 EA（不再依赖 .set）
- 把你 eva019.1.set 验证过的值**写成 EA 默认**，编译后直接跑：
  `UniMaxPos=3`、`GridVolExp=2.7`、`MoveVolExp=0.8`、`CoefCVolExp=0`、`GridZ=350`、`MoveB=130`、`CoefC=63`、`CoefDecay=0.85`、`UniGridExpCoef=1.4`、`UniBaseProfit=200000`、`X_Minutes=40`、`AvgVolumeMinutes=50`、`BaseAvgVolumePerMin=160`、`MaxAvgVolumePerMin=220`、`RiskL3LossPerLot=700`、`LastOrderLossPerLot=800`、`Cooldown=120`、`BigCooldown=840`、延迟 19/13/16/12/8；新增 `InpMinGridZ=100`。
- 这也解释了你这次为什么亏：pacing 是硬编码无开关，.set 关不掉它——现在直接从代码删除，根治。
- `eva020.set` 只在你要**寻优** `InpMinGridZ` 时才载入；**只想跑一遍看结果 → 直接编译 EA 即可**。

### 点 3（上轮）—— 注释/布局
- 删除 `统一-` / `=旧中波动` 这类标注，直接给值。
- **基线移动系数不再单独成组**：`InpCoefC / InpCoefCVolExp / InpCoefDecay` 与网格/订单参数并入同一组，恢复你原来的布局。

---

## 3. 参数瘦身（点 2）
- 真正需要你关注/寻优的核心旋钮已压到 ~10 个（`GridZ / MinGridZ / MoveB / CoefC` + `GridVolExp / MoveVolExp / CoefCVolExp` + `UniGridExpCoef / UniMaxPos / X_Minutes`）。
- 本轮 `eva020.set` 的寻优**只开 3 个**：`InpMinGridZ / InpGridZ / InpMoveB`（其余全部单值=你的验证值），直接回应"参数太多"。
- 日志/仪表盘/`InpScore*`/动态手数/周末守护等属基础设施，不进调参清单。

---

## 4. 自测
- 去注释/字符串后括号平衡相对原文件**零净变化**；删 44 行。
- 残留检查：`pacing_panic_stop` 代码引用 0（仅注释 4 处）、`ADD_PACING_PANIC` 0、旧函数名 0。
- **MQL5 无法在此编译，请在 MetaEditor 编译，有报错贴我**（`CheckAddPacingDelay` 的 `multiplier_a/current_price/point` 现为未用参数，MQL5 不报错；如个别版本提示，告诉我即可去签名）。

---

## 5. 下一步
1. **编译** eva020（有报错贴我）。
2. **直接跑**（默认值即验证版，无需 .set，2025-01→2026-06）：先看 `pacing_panic_stop` 是否消失、净利是否翻正、网格距是否不再有 <100pt 的塌陷单；发我 enrich。
3. 健康后**寻优** `eva020.set`（仅 3 旋钮：MinGridZ / GridZ / MoveB）。
4. **单独验证趋势**：`InpEnableTrendOrders=true` 跑一次，确认趋势机制真的在工作（这是"删 pacing 靠趋势兜底"成立的前提）。

---

## 6. 代码 / 参数 changelog（历代）
| 代际 | 产物 | 改了什么 / 为什么 |
|---|---|---|
| eva016 | EA+.set |（失败）局部网格波动化→churn |
| eva017 | EA+.set |（失败）统一模型未删三档=四不像 |
| eva018 | EA+.set | 真删三档；距离=占价%×价×波动^指数 |
| eva019 | EA+.set | 删换挡分类器；基准改中波动；距离整数化+显式价格缩放；去"低波动"命名 |
| **eva020** | **EA+.set** | 删 `pacing_panic` 熔断（−$868 元凶，单边改由趋势状态机处理）；网格加最小距下限 `InpMinGridZ`（仅随价、不随波动，防低波动 churn）；好默认值固化进 EA（含 MaxPos=3、指数 2.7/0.8）；基线系数并入主组、清理 `统一-/=旧中波动` 注释；寻优收敛到 3 旋钮 |

---

*本日志随版本更新；代际默认进位。代码/参数改动在 §6 追加。*
*（以上为工程与分析记录，不构成投资建议；改动后务必在测试器充分验证。）*
