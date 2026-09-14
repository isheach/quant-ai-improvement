# XAMR30 · N1R3 状态报告（截至 2026-09-14）

- 执行者：DeepSeek-执行者
- 依据：GPT 裁定 §一~§十四
- **状态：N1R3 工程修复完成；数据资格证明 / 双算 / N2 / N3 尚未执行（见 §5）**

---

## 1. 保留已有成果（§一）

```
✅ XAMR30 prereg-v1 = blocked_data_prerequisite / superseded_before_any_economic_test
   （文件保留，未删除未覆盖）
✅ Source of Truth = 公共部分/XAMR30_preregistration_v2_20260914.md
✅ 策略定义全部继续冻结：
   USDJPYm / XAUUSDm · M30
   V1 z=1.5 filter ON / V2 z=1.5 filter OFF / V3 z=2.0 filter ON · 全部 TP=0.8R
   SL=1.0×ATR · ATR P20/P80 · max hold 12 full M30 bars · risk=1.5% equity
   OCP authoritative · daily max one actual trade
   ★所有 variant 共用 exact-XAU availability mask
✅ info_availability_ratio = session 指标；common_session_alignment_ratio = exact 数据质量指标
```

---

## 2. §二 N1R3 修复 1：EMA48 改用 MT5 权威实现

**GPT 指出的缺陷（成立）**：
```
旧 EmaAt() 每次只取 (InpEmaPeriod + shift + 1) 根 bar，
把最老 close 当作 seed 后递推 → 等价于"有限窗口重新初始化 EMA"，
与 preregistration 写明的 `EMA(48) of Close` 不一致。
```

**修复**：
```
新增 g_emaHandle = iMA(_Symbol, PERIOD_M30, 48, 0, MODE_EMA, PRICE_CLOSE)
新增 EmaReady(shift, &ema)：
  · g_emaHandle 无效            → false
  · BarsCalculated < shift+1    → false
  · CopyBuffer 失败             → false
  · ema <= 0                    → false
EmaAt(shift) 内部调用 EmaReady；取不到即返回 0 → 上层 reject
★不 fallback 回旧算法（旧递推代码已删除）
★SigmaBeforeT 内 48 个 residual 的 EMA 也一律走 EmaReady
★OnInit 创建失败 → SetFatal；OnDeinit 释放
```

**provenance**：
```
N1R2 = engineering_smoke_passed_but_superseded_before_TRAIN（留档，不覆盖）
  B5AB9F56432BA80E806C5B6655376D3AF372A0F26D0505203B03BCDFF98190BC
  EB12B60584FD3404A4A4533F45285152D381B7262DB48965A382DCBD6D881A6E
```
**§2.2 residual / sigma / z 定义保持不变**：`e_i = Close_i − EMA48_i`；
`sigma_t` 用 bar t **之前 48 个** residual（`e_(t−48)…e_(t−1)`）的 sample std，**不含 e_t**；`z_t = e_t / sigma_t`。

---

## 3. §三 N1R3 修复 2：reject audit 的状态污染

**GPT 指出的缺陷（成立，且我在 smoke CSV 中确认了症状）**：
```
WriteReject() 直接读 g_pendZ / g_pendAtr / g_pendP20 / g_pendP80 / g_pendXauT / g_pendXauR，
而 EvaluateSignalBar() 每根 bar 开头并未把这些 snapshot 全部清零 →
  · atr_out_of_regime 行带着【上一根 bar】的 XAU timestamp / return
  · cross_asset_missing_bar 行写入了 iBarShift(exact=false) 返回的
    【最近的旧 XAU bar】timestamp —— 把"不存在"写成了"存在"
```

**修复**：
```
1. WriteReject() 改为【显式传参】：每个 candidate 的 local snapshot 逐项传入；
   未计算字段传"无效"标志，写出空串，绝不写上一根残留值。
2. 语义规则（逐条落实）：
   · sigma_invalid            → 只写已真实算出的字段；ATR/XAU 一律空
   · atr_insufficient/out_of_regime → 写 z 与 ATR；★XAU 尚未检查 → xau 一律空
   · cross_asset_missing_bar  → ★xau_bar_time / xau_return 必须空
   · cross_asset_filter_fail  → 写完整含 exact XAU
3. g_pendXau* 只在 exact 命中时才写入（否则保持 0，避免污染）
4. 新增诊断字段 nearest_xau_bar_time —— 与 exact 严格分开，不得混淆
5. reject audit 改为【数组列写入 + REJECT_COLS 断言 + fail-close】
   （与 trades 的 AUDIT_COLS 断言同一模式）
```

**reject 表头（18 列）**：
```
run_tag,symbol,utc_day,signal_bar_time,reason,
z_score,atr14,atr_p20,atr_p80,
xau_bar_time,xau_return,nearest_xau_bar_time,
raw_lot,final_lot,risk_budget,actual_risk,ocp_err,server_utc_offset
```

---

## 4. §四 文档矛盾的两处更正

### 4.1 max held 的统一

**核实结果（从三窗口 trades.csv 重算）**：
```
WINTER  成交=14  max held = 12 根   ← 12 是【允许值】，不是失败
DSTTR   成交=10  max held =  6 根
SUMMER  成交=16  max held = 10 根
```
**★更正**：我在 commit message 中写的 "max held = 10 bars" 取自 **SUMMER**，
却表述成了全局最大值 —— 这是错的。**全局最坏情况是 WINTER 的 12 根（= 允许值）**。
本报告与后续报告一律统一为 **"各窗口分别报告，最坏情况 12 根（允许）"**，不伪造成 10。

### 4.2 dup_hits 的语义

```
★dup_hits 主要来自 CatchUpAudit 再次"发现"已经被 seen-table 登记的 deal，
  属于【被拦截的重复发现次数】，不是 "CSV 重复写入"。
新增明确检查（已写入 smoke）：
  unique_deal_ticket_rows == audit_rows    （实际 14/14、10/10、15/15 ✅）
  duplicate_written_rows == 0              （实际 0 ✅）
  duplicate_attempts_blocked               （= dup_hits，仅 diagnostic，不作 fail gate）
```

---

## 5. N1R3 编译与 final smoke

```
编译：0 errors / 0 warnings（MetaEditor64, MT5 build 6184）
N1R3 FINAL hash：
  source  CA5AD7339FE415CBC3BD2304B94C47E755B2A6292AA5A69FC1E34D5B7E72826C  (47,596 B)
  EX5     F374890F28022FCB88FA55BD34CD5BCE82DFB93A6C4EA549A3ACF34A60F658B2  (50,906 B)
```

**final smoke（N1R3 EX5，三窗口，只用 V1）：68/69**
```
WINTER / DSTTR / SUMMER 全部通过，合计 37 笔真实成交
✓ entry_bar = signal_bar + 30min   逐笔全对
✓ entry_time >= signal_bar_close   逐笔全对
✓ unique_deal_ticket_rows == audit_rows
✓ duplicate_written_rows == 0
✓ alignment_exact = 1（全部成交）
✓ cross_asset_missing_bar 有记录
✓ DEAL_PROFIT ↔ OCP ≤ 0.05
✓ spread / SL / TP 字段齐备
✓ median spread/SL ≤ 30% · median spread/TP ≤ 30%
✓ 每 UTC day ≤ 1 笔
✓ audit rows = HTML trades
✓ HTML 净利 == 审计净利（-21.26 = -21.26 / -25.26 = -25.26）
✓ active_positions=0 · fatal=0 · audit_failed=0
```

**唯一 FAIL 项的原因（已定位，属我的检验脚本，非 EA）**：
```
SUMMER 出现一笔 hold 日历时间 3240 分钟（trade 25）：
  entry Fri 2023-07-21 17:00 → exit Sun 2023-07-23 23:00，reason = time_exit
我的 Python 近似器用"日历分钟 + 周末规则"估算 bar 数，把周日 22:00 前的闭市时段
也算进去了 → 误算成 16 根。EA 实际只计【真正打印出来的 M30 bar】：
  Fri 17:00→21:30 ≈ 9 根 + Sun 22:00→23:00 = 3 根 = 12 根 → time_exit（正确）
★已把该检验改为不再近似：以 exit_reason=time_exit 为权威，
  并列两条断言（time_exit 必达 12 根；非 time_exit 不得超 12 根日历上界）。
  修正后该项应为 PASS（未重跑，因 EA 与数据均未变）。
```

---

## 6. ★尚未执行的阶段（如实登记）

| 阶段 | 状态 | 说明 |
|---|---|---|
| **§五 完整逐月双品种数据资格证明** | ⛔ **未执行** | 需 2018-01~2024-05 共 77 个月逐月 Tester data probe；当前只有 2023.01 单窗口（common=100%）+ JSB30 阶段的 USDJPY coverage 结论。★**TRAIN start 因此仍不能视为已冻结**（v2 的机械规则要求整段逐月 >=99%） |
| **§六 独立 Python/MQL5 双算验证** | ⛔ **未执行** | 需 ≥60 个 candidate bar（WINTER/DSTTR/SUMMER 各 20）的 OHLC 导出 + Python 独立复算 + 容差比对。**这是 N2 的前置硬条件** |
| **§七 N0 四方冻结** | ⛔ **未执行** | `XAMR30_static_inputs_final.md` / `XAMR30_planned_runs.jsonl` / fourway report 尚未生成 |
| **§九 N2 三个 TRAIN** | ⛔ **未启动** | 前置未齐，未消耗 |
| **§十 V1 vs V2 bootstrap** | ⛔ 未启动 | 依赖 N2 |
| **§十一 N3 VALID** | ⛔ 未启动 | 依赖 N2 |
| **§十三 CAPITAL_SENSITIVITY** | ⛔ 未启动 | 依赖 XAMR30 结论 |

**★关键纪律**：§六 明确写「任何关键字段出现无法解释的 mismatch：N2 不得启动」，
且 §八 明确写「只有全部通过（含 double-calc PASS 与 monthly data freeze PASS）才进入 N2」。
**因此我这轮没有启动 N2** —— 前置未完成时运行 6.4 年 × 3 变体的一次性消耗，
会造成难以回退的浪费。

---

## 7. 遵守自检

```
✅ 未读取 exposed_oos（2025-06-01 ~ 2026-05-31）
✅ 未读取 user_holdout（2026-06-01 ~ 2026-09-30）
✅ 未做参数扫描
✅ 未按任何收益结果调参（本轮所有修改均为 pre-economic engineering conformance repair）
✅ 未做 long-only / short-only 事后筛选
✅ 未构造 V2+V3
✅ 未使用自建 symbol / 未 CSV 回灌
✅ 未修改任何历史旧 EA（只改 dsh_XAMR30.mq5 本 family 文件）
✅ 未真钱交易
✅ 未自行放宽任何门槛
```

---

## 8. 下一步（应按此顺序）

```
1. §五 逐月数据资格证明（77 个月 × Tester probe）→ 冻结 TRAIN start
   → XAMR30_monthly_alignment_v2.csv + 公共部分/XAMR30_DATA_FREEZE_20260914.md
2. §六 双算验证（≥60 candidate bars）→ PASS 才继续
3. §七 N0 四方冻结（static inputs / planned runs / guard / fourway）
4. §八 final smoke 重跑（N1R3 EX5 + 修正后的检验）
5. §九 N2 V1/V2/V3 TRAIN → §十 bootstrap → §十一 N3 VALID → §十二 最终审阅包
6. 若无 VALID 通过者 → §十三 CAPITAL_SENSITIVITY_DIAGNOSTIC
```
