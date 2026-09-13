# dsh_TrendCore 最小安全修复审查（只读）

时间：2026-09-11（Asia/Shanghai）  
审查身份：GPT-子审（trendcore_patch_review）  
目标：不改动原始 `deepseek数据保存/mql5/dshtools/dsh_TrendCore.mq5`，给出手数、最小手风险、出场原因映射的最小安全修复方案。

## 结论摘要

1. `AlignLot()` 在 334–348 行使用 `MathFloor(lot / vstep + 0.5)`，是四舍五入，可能把实际止损风险抬高到预算之上。应改为严格向下取整，并在取整后重新计算 `riskUsed`。
2. `LotForRisk()` 在 430–447 行已经对“原始计算手数低于最小手”的情况做了最小手风险上限检查；但当前普通分支在 449 行四舍五入后没有再次检查，且无法处理“取整后跌破最小手”的步长边界。建议把向下取整结果重新送回同一最小手风险检查路径。
3. `RecordExitDeal()` 在 691–737 行只把 `DEAL_REASON_EXPERT` 映射为 `expert`，丢失 `ClosePosition("tp"/"trend_exit"/"dd_kill")` 的内部原因。应优先使用券商原因 `sl/tp/stopout`；对 `DEAL_REASON_EXPERT` 读取 `DEAL_COMMENT` 的 `close_` 前缀，失败时使用按 position ticket 关联的 pending reason，最后才回退为 `expert`。

## 具体位置与方案

### A. 向下取整（334–348 行）

当前：

```text
lot = MathFloor(lot / vstep + 0.5) * vstep;
if(lot < vmin) lot = vmin;
```

最小改法：先把有效上限（品种最大手和 `InpMaxLot`）限制到候选手数，再用 `MathFloor(lot / vstep + eps) * vstep`；如果结果低于 `vmin`，返回 0，由 `LotForRisk()` 统一处理最小手分支。不要在这个 helper 内无条件把低于 `vmin` 的数抬到 `vmin`，否则会绕过风险预算判断。最终返回值仍需规范化到 step 的小数位。

### B. 最小手风险（409–452 行）

保留现有语义：`InpAllowMinLotOvershoot=true` 时允许 0.01 手，但必须满足 `vmin * perLot <= base * InpMinLotMaxRiskPct / 100`；否则跳过信号。修复后的流程应是：

```text
rawLot = riskMoney / perLot
lot = AlignLot(rawLot)       // 严格向下取整
if(lot < vmin) {
    if(!InpAllowMinLotOvershoot) reject
    minLotRisk = vmin * perLot
    if(minLotRisk > cap) reject
    lot = vmin; riskUsed = minLotRisk
} else {
    riskUsed = lot * perLot  // 向下取整后不会超过目标风险
}
```

`riskUsed` 必须始终按最终发送的 `lot` 重算，不能记录未取整的理论风险。

### C. 出场原因映射（691–745、755–793 行）

`ClosePosition()` 目前将 `req.comment = "close_" + reason`（772 行），但 `RecordExitDeal()`（705–728 行）完全不读 `DEAL_COMMENT`，所以当前审计中 `tp`、`trend_exit`、`dd_kill` 都会显示为 `expert`。建议：

- `DEAL_REASON_SL/TP/SO` 保留服务器权威原因；
- `DEAL_REASON_EXPERT` 时读取 `HistoryDealGetString(dealTicket, DEAL_COMMENT)`，若以 `close_` 开头则去掉前缀并限制到白名单 `tp/trend_exit/dd_kill`；
- 若经纪商重写 comment，`ClosePosition()` 在发单前暂存 `{position_ticket, reason}`，`RecordExitDeal()` 以 `DEAL_POSITION_ID` 关联作为回退；关联失败才记录 `expert`；
- 记录完成后清理 pending 映射。外部手动/网页/移动端原因不得伪装成内部原因。

此外，`g_entryPrice/g_riskMoney/g_atrAtEntry` 也依赖全局状态；更稳妥的后续修复是开仓时用 position/deal ID 保存元数据并按 ID 取回，但这不是本轮最小补丁的必要条件。

## 对 TC-03 的影响判断

- 信号条件（EMA、突破、RV、时段等）不会改变；因此理论信号时间/方向不变。
- 交易经济结果会改变：TC-03 的 BTCUSDm 审计中存在大量高于 0.01 手的成交，验证段 0.02/0.03 手共 7 笔，测试段共 13 笔，训练段更多。当前四舍五入可能向上取整；严格向下取整会减少这些成交的手数和单笔盈亏/风险，故净利、回撤、PF 及可能的 DD 锁路径都必须重跑，不能沿用旧报告。
- 最小手风险检查本身只会在“原始/向下取整后低于最小手”且超过 `InpMinLotMaxRiskPct` 时拒绝信号；若当前 BTCUSDm `vmin=vstep=0.01` 且 cap 未触发，信号数量通常不变，但需以修复后日志确认。
- 出场原因映射只改审计标签和统计归类，不改变成交价格/手数；但必须在重跑后验证 `tp/trend_exit/dd_kill/sl` 的构成。

## 证据

- 源码：`deepseek数据保存/mql5/dshtools/dsh_TrendCore.mq5`，上述行号按 2026-09-11 工作树。
- TC-03 交易审计：`gpt数据保存/mt5_runs/outputs/audits/btc_tc03_train/trades.csv`、`.../btc_tc03_valid/trades.csv`、`.../btc_tc03_test/trades.csv`。
- 只读复核，未修改源码、EX5 或旧策略目录。

