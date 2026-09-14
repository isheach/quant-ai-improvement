//+------------------------------------------------------------------+
//|                                                    dsh_JSB30.mq5  |
//|  JSB30 = JPY Session Breakout on M30                             |
//|                                                                  |
//|  依据：公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md      |
//|  预注册：执行_下一family_20260913/N0_snapshot/                    |
//|          JSB30_preregistration_final.md                          |
//|                                                                  |
//|  ★独立新 EA。不修改任何旧源码。                                    |
//|                                                                  |
//|  结构：M30 时段突破（UTC 定义 / server 时间执行）                   |
//|    · range   : UTC 00:00 -> 06:00   (V2: -> 03:00)               |
//|    · breakout: UTC 07:00 -> 12:00                                |
//|    · hard-flat: UTC 20:00                                        |
//|    · 单仓；每个 UTC 日最多一笔；无网格/马丁/加仓/移动盈利止损        |
//|    · SL = 1.0 x ATR14(M30)；TP = 1.5R (V3: 1.0R)；最长 16 根 M30   |
//|                                                                  |
//|  时间系统（GPT §4）：                                              |
//|    · 按【交易周】动态推导 server_utc_offset 并缓存                 |
//|    · 只允许 +2 / +3；否则 offset_undetermined -> 整段 environment_error |
//|    · 禁止整段固定 offset                                          |
//|                                                                  |
//|  审计（GPT §4）：19 个唯一字段 + header 唯一性自检                  |
//|    · 修复历史 R4 的重复 entry_time header bug                     |
//|    · FileWrite 成功后才登记为已写                                  |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property strict

//==================== 输入 ====================
//--- 标识
input string InpRunTag                  = "JSB30";
input long   InpMagic                   = 20260914;

//--- 时段（UTC 定义）
input int    InpRangeStartUtcHour       = 0;
input int    InpRangeEndUtcHour         = 6;    // V2 -> 3
input int    InpBreakoutStartUtcHour    = 7;
input int    InpBreakoutEndUtcHour      = 12;
input int    InpHardFlatUtcHour         = 20;

//--- 信号
input int    InpSignalTFMinutes         = 30;
input int    InpATRPeriod               = 14;
input double InpMinRangeATRMult         = 0.5;

//--- 出场
input double InpSL_ATR                  = 1.0;
input double InpTP_RMult                = 1.5;  // V3 -> 1.0
input int    InpMaxBarsInTrade          = 16;

//--- 风险
input double InpRiskPct                 = 1.5;
input double InpMinLotMaxRiskPct        = 3.0;
input bool   InpAllowMinLotOvershoot    = false;

//--- 方向
input bool   InpAllowLong               = true;
input bool   InpAllowShort              = true;

//--- 时间系统
input bool   InpUseDynamicDstOffset     = true;
input int    InpExpectedServerOffsetMin = 2;
input int    InpExpectedServerOffsetMax = 3;

//--- ★N1R 修复 4：OCP 与独立公式的容差
input double InpOcpTolUsd               = 0.05;   // 绝对容差（USD）
input double InpOcpTolRelPct            = 2.5;    // 相对容差（%）；用于吸收 OCP 内部换算约定差异

//--- 审计与控制
input bool   InpWriteAudit              = true;
input bool   InpWriteRejectAudit        = true;
input bool   InpRunTimeSelfcheck        = true;
input int    InpLatencyMs               = 0;
input int    InpLatencyTicks            = 0;
input bool   InpVerboseLog              = false;

//--- 禁止项（写死）
input bool   InpUseGrid                 = false;
input bool   InpUseMartingale           = false;
input bool   InpUseTrailingWin          = false;

//==================== 时间系统 ====================
#define MAX_WEEKS 2048

struct WeekOffset
{
   int      year;      // ISO-ish：该周所属年份（用周一所属年）
   int      weekIdx;   // 年内周序号（1..53）
   int      offset;    // server_utc_offset（+2 / +3）
   bool     valid;
};

WeekOffset g_wo[MAX_WEEKS];
int        g_woCount = 0;

bool     g_offsetUndetermined = false;
int      g_offsetFailCount    = 0;
string   g_offsetFailReason   = "";

// 把 server time 转成 UTC（用给定 offset）
datetime ServerToUtc(datetime tServer, int offset) { return (datetime)((long)tServer - (long)offset * 3600); }
datetime UtcToServer(datetime tUtc, int offset)    { return (datetime)((long)tUtc + (long)offset * 3600); }

// 周一 00:00 UTC 基准（周键）
// ★★★ N1R 修复 2：周键 = 该交易周的【周一 00:00 UTC】
//   旧实现返回【周日 00:00 UTC】，与实际外汇周首 bar（周日 22:00 UTC）相差 22 小时，
//   导致 WeekFirstBarServer 的扫描窗口根本盖不到周首 bar（GPT 源码复核指出）。
//   新规则：周日 22:00 UTC 之后属于【下一周】。
datetime WeekKeyUtc(datetime tUtc)
{
   MqlDateTime s; TimeToStruct(tUtc, s);
   int dow = s.day_of_week;                                  // 0=Sun..6=Sat
   datetime dayStart = (datetime)((long)tUtc - (long)s.hour * 3600 - (long)s.min * 60 - s.sec);
   int back;
   if(dow == 0) back = 6;              // 周日 00:00 → 回退到【上周一】
   else         back = dow - 1;        // 周一→0, 周二→1 … 周六→5
   datetime wk = (datetime)((long)dayStart - (long)back * 86400);
   // ★周日 22:00 UTC 之后属于下一周 → 前进 7 天到本周一
   if(dow == 0 && s.hour >= 22) wk = (datetime)((long)wk + 7 * 86400);
   return wk;
}

// 缓存查找
int FindWeekOffset(datetime weekKey)
{
   for(int i = 0; i < g_woCount; i++)
      if(g_wo[i].valid && (datetime)g_wo[i].year == weekKey) return g_wo[i].offset;
   return -1;
}

void StoreWeekOffset(datetime weekKey, int offset, bool ok)
{
   if(g_woCount >= MAX_WEEKS) return;
   g_wo[g_woCount].year    = (int)weekKey;   // 直接复用字段存 weekKey
   g_wo[g_woCount].weekIdx = 0;
   g_wo[g_woCount].offset  = offset;
   g_wo[g_woCount].valid   = ok;
   g_woCount++;
}

// ★按交易周推导 offset：给定该周第一根 bar 的 server 时间
//   外汇周界 = 周日 22:00 UTC。server 时间 = UTC + offset
//   -> serverHourOfWeekOpen = 22 + offset
//   允许 +2 -> 00:00(周一)  ; +3 -> 01:00(周一)
//   这里用更稳的判据：offset ∈ {2,3} 且 (observedHour - 22 - offset) % 24 == 0
bool InferOffsetFromWeekOpen(datetime firstBarServer, int &outOffset, string &why)
{
   MqlDateTime s; TimeToStruct(firstBarServer, s);
   int obsH = s.hour;
   // 该 bar 必须是【周首 bar】：offset=2 → server 周一 00:00 ；offset=3 → server 周一 01:00
   // ★N1R：旧实现允许 22/23/2，与"周首 bar"的定义不符，已收紧为 0..1
   if(obsH != 0 && obsH != 1)
   { why = StringFormat("week-open server hour=%d 不是周首（期望 0 或 1）", obsH); return false; }

   int found = -1;
   for(int off = InpExpectedServerOffsetMin; off <= InpExpectedServerOffsetMax; off++)
   {
      int want = (22 + off) % 24;
      if(obsH == want) { if(found >= 0) { why = "多个候选 offset"; return false; } found = off; }
   }
   if(found < 0) { why = StringFormat("hour=%d 无候选 offset ∈[%d,%d]", obsH,
                                      InpExpectedServerOffsetMin, InpExpectedServerOffsetMax); return false; }
   outOffset = found;
   why = "";
   return true;
}

// 取用于推导的"周第一根 bar"：用 D1 找到该周起始，再取 M30 首根
// ★N1R 修复 2：周首 bar 的 server 时间应在 [周一 00:00, 周一 04:00) server 区间内
//   （对应 UTC 周日 22:00 开盘 + offset ∈ {+2,+3} → server 周一 00:00 或 01:00）
//   旧实现从 offset 猜测值换算后只扫 8 小时，与"周日 22:00 UTC"的假定冲突；
//   新实现直接从周一 00:00 server 起向后扫 4 小时，覆盖两种 offset。
bool WeekFirstBarServer_At(datetime weekKeyUtcMon, datetime &outServer)
{
   int n = iBars(_Symbol, TF());
   if(n <= 0) return false;
   for(int k = 0; k < 16; k++)                       // 16 × 15min = 4 小时
   {
      datetime t = (datetime)((long)weekKeyUtcMon + (long)k * 900);
      if(t > iTime(_Symbol, TF(), 0)) break;         // 不越过最后一根
      int sh = iBarShift(_Symbol, TF(), t, false);
      if(sh < 0 || sh >= n) continue;
      datetime bt = iTime(_Symbol, TF(), sh);
      if(bt < weekKeyUtcMon) continue;               // 必须在周一 00:00 之后
      if(bt >= (datetime)((long)weekKeyUtcMon + 4 * 3600)) break;   // 超出 4 小时窗口
      outServer = bt;
      return true;
   }
   return false;
}

// 兼容旧签名（offsetGuess 保留以兼容既有调用点，新实现不再依赖它）
bool WeekFirstBarServer(datetime weekKeyUtc, int offsetGuess, datetime &outServer)
{
   if(offsetGuess <= 0) offsetGuess = InpExpectedServerOffsetMin;   // 仅消参
   return WeekFirstBarServer_At(weekKeyUtc, outServer);
}

// ★获取给定 server 时间所属周的 offset（带缓存；失败即 fail-close）
int OffsetForServerTime(datetime tServer)
{
   // 先用 +2 试算周键（误差最多 1 小时，跨周键的影响在 ±1h 内可控）
   datetime wk = WeekKeyUtc(ServerToUtc(tServer, InpExpectedServerOffsetMin));
   int cached = FindWeekOffset(wk);
   if(cached > 0) return cached;

   datetime firstBar;
   if(!WeekFirstBarServer(wk, InpExpectedServerOffsetMin, firstBar))
   {
      g_offsetUndetermined = true; g_offsetFailCount++;
      g_offsetFailReason = StringFormat("week %s 找不到周首 bar", TimeToString(wk));
      StoreWeekOffset(wk, 0, false);
      return -1;
   }
   int off = -1; string why = "";
   if(!InferOffsetFromWeekOpen(firstBar, off, why))
   {
      g_offsetUndetermined = true; g_offsetFailCount++;
      g_offsetFailReason = StringFormat("week %s: %s (firstBar=%s)", TimeToString(wk), why,
                                        TimeToString(firstBar));
      StoreWeekOffset(wk, 0, false);
      return -1;
   }
   StoreWeekOffset(wk, off, true);
   return off;
}

//==================== 全局状态 ====================
ENUM_TIMEFRAMES g_sigTF  = PERIOD_M30;
int      g_atrHandle    = INVALID_HANDLE;

ENUM_TIMEFRAMES TF() { return g_sigTF; }   // ★显式类型访问器（避免 enum 隐式转换错误）

datetime g_lastClosedBar = 0;     // ★N1R：最近一次"新收盘 M30"的 bar 时间
datetime g_evalBar       = 0;      // ★N1R：最近一次"已评估突破"的 bar 时间
datetime g_curUtcDay    = 0;      // 当前 UTC 日（00:00 UTC）
bool     g_dayTraded    = false;  // 该 UTC 日是否已成交
double   g_rangeHi       = 0.0;    // 当日累计 high
double   g_rangeLo       = 1e18;   // 当日累计 low
bool     g_rangeReady    = false;  // 窗口完整结束后置 true
int      g_rangeCount    = 0;      // 参与 range 的已收盘 M30 bar 数
datetime g_rangeDay      = 0;      // 该 range 所属 UTC 日（00:00 UTC）
double   g_rangeFrozenHi = 0.0;    // ★冻结值（breakout 只用它）
double   g_rangeFrozenLo = 0.0;

//--- 持仓跟踪
ulong    g_ticket       = 0;
int      g_dir          = 0;
double   g_entryPrice   = 0.0;
double   g_initSL       = 0.0;
double   g_initTP       = 0.0;
double   g_riskBudget   = 0.0;    // 计划风险（USD）
double   g_actualSLRisk = 0.0;    // 按最终手数重算的实际风险（USD）
double   g_entryATR     = 0.0;
int      g_barsHeld     = 0;
datetime g_entryTimeServer = 0;
datetime g_entryTimeUtc    = 0;
int      g_entryOffset     = 0;

//--- 统计
long     g_nTrades = 0, g_nWin = 0;
long     g_skipRangeNotReady = 0, g_skipRangeTooNarrow = 0;
long     g_skipNoBreak = 0, g_skipDayTraded = 0, g_skipBadWindow = 0;
long     g_rejRisk = 0, g_rejOffset = 0;

//--- 审计
int      g_auditFh  = INVALID_HANDLE;
int      g_rejectFh = INVALID_HANDLE;
long     g_writtenDeals = 0;
long     g_dupHits = 0;
long     g_ocpMismatch = 0;      // ★N1R：OCP 与独立公式差异超容差的次数
uint     g_lastWriteBytes = 0;   // ★N1R：最近一次 FileWrite 的返回值（0 = 失败）
bool     g_auditFailed = false;

#define MAX_DEALTICKET 8192
ulong    g_seen[MAX_DEALTICKET];
int      g_seenCount = 0;

//==================== 审计 ====================
string AuditDir() { return "dshtrend\\" + InpRunTag; }

const string AUDIT_HEADER =
   "run_tag,symbol,deal_ticket,position_id,entry_time_server,entry_time_utc,"
   "exit_time_server,exit_time_utc,entry,exit,volume,profit,swap,commission,net,"
   "close_type,exit_reason,risk_budget,actual_sl_risk,reject_reason,server_utc_offset,"
   "ocp_value,formula_value,ocp_err,ocp_diff,ocp_lim";

const string REJECT_HEADER =
   "run_tag,symbol,utc_day,server_time,utc_time,server_utc_offset,reason,"
   "range_hi,range_lo,atr,range_atr_mult,raw_lot,final_lot,risk_budget,actual_risk";

// ★header 唯一性自检（修复历史 R4 重复 entry_time bug）
bool HeaderUnique(const string csvHeader)
{
   string parts[];
   int n = StringSplit(csvHeader, ',', parts);
   for(int i = 0; i < n; i++)
      for(int j = i + 1; j < n; j++)
         if(parts[i] == parts[j])
         {
            PrintFormat("[%s] ★AUDIT FAIL: duplicated header column '%s'", InpRunTag, parts[i]);
            return false;
         }
   return true;
}

// ★★★ N1R 修复 3：拆成 IsDealSeen / MarkDealSeen
//   旧实现 DealSeen() 在【检查时】就把 ticket 写入 g_seen，而 FileWrite 返回值没被检查
//   → 重新引入了此前已明确禁止的"先标记、后写入"问题
//   （FileWrite 失败时该 ticket 已被标记 → 永久漏记且不会重试）。
bool IsDealSeen(ulong ticket)
{
   for(int i = 0; i < g_seenCount; i++) if(g_seen[i] == ticket) return true;
   return false;
}

void MarkDealSeen(ulong ticket)
{
   if(g_seenCount < MAX_DEALTICKET) g_seen[g_seenCount++] = ticket;
   else { g_dupHits++; g_auditFailed = true;
          PrintFormat("[%s] ★AUDIT FAIL: seen 表溢出，去重不再可靠", InpRunTag); }
}

void WriteReject(datetime tServer, string reason, double rawLot, double finalLot,
                 double riskBudget, double actualRisk)
{
   if(!InpWriteRejectAudit || g_rejectFh == INVALID_HANDLE) return;
   int off = OffsetForServerTime(tServer);
   datetime tUtc = (off > 0) ? ServerToUtc(tServer, off) : tServer;
   double atr = 0.0;
   double b[]; if(CopyBuffer(g_atrHandle, 0, 0, 1, b) == 1) atr = b[0];
   double rm = (atr > 0.0) ? (g_rangeHi - g_rangeLo) / atr : 0.0;
   // ★N1R 修复 3：reject audit 的写入结果也要检查
   g_lastWriteBytes = FileWrite(g_rejectFh, InpRunTag, _Symbol,
             TimeToString(g_curUtcDay, TIME_DATE),
             TimeToString(tServer, TIME_DATE|TIME_SECONDS),
             (off > 0) ? TimeToString(tUtc, TIME_DATE|TIME_SECONDS) : "undetermined",
             (off > 0) ? IntegerToString(off) : "undetermined",
             reason,
             DoubleToString(g_rangeHi, _Digits), DoubleToString(g_rangeLo, _Digits),
             DoubleToString(atr, _Digits), DoubleToString(rm, 4),
             DoubleToString(rawLot, 4), DoubleToString(finalLot, 2),
             DoubleToString(riskBudget, 2), DoubleToString(actualRisk, 2));
   if(g_lastWriteBytes <= 0)
   {
      g_auditFailed = true;
      PrintFormat("[%s] ★AUDIT FAIL: reject FileWrite 返回 %u 字节 → run 作废",
                  InpRunTag, g_lastWriteBytes);
   }
   FileFlush(g_rejectFh);
}

void OpenAudit()
{
   if(!InpWriteAudit) return;
   if(!HeaderUnique(AUDIT_HEADER)) { g_auditFailed = true; return; }
   if(!HeaderUnique(REJECT_HEADER)) { g_auditFailed = true; return; }

   string fn = AuditDir() + "\\trades.csv";
   bool exists = FileIsExist(fn, FILE_COMMON);
   g_auditFh = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(g_auditFh == INVALID_HANDLE)
   {
      // 回退到 worker 沙盒（portable tester 拒绝 FILE_COMMON 的情形）
      g_auditFh = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(g_auditFh == INVALID_HANDLE)
      { PrintFormat("[%s] AUDIT FAIL: 无法打开 trades.csv", InpRunTag); g_auditFailed = true; return; }
   }
   FileSeek(g_auditFh, 0, SEEK_END);
   if(!exists)
   {
      // ★N1R 修复 3：header 写入结果也要检查
      g_lastWriteBytes = FileWrite(g_auditFh, AUDIT_HEADER);
      if(g_lastWriteBytes <= 0)
      {
         g_auditFailed = true;
         PrintFormat("[%s] ★AUDIT FAIL: trades header 写入失败（返回 %u）",
                     InpRunTag, g_lastWriteBytes);
         return;
      }
   }

   string rf = AuditDir() + "\\reject_audit.csv";
   bool rexists = FileIsExist(rf, FILE_COMMON);
   g_rejectFh = FileOpen(rf, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(g_rejectFh == INVALID_HANDLE)
      g_rejectFh = FileOpen(rf, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(g_rejectFh != INVALID_HANDLE)
   {
      FileSeek(g_rejectFh, 0, SEEK_END);
      if(!rexists)
      {
         g_lastWriteBytes = FileWrite(g_rejectFh, REJECT_HEADER);
         if(g_lastWriteBytes <= 0)
         {
            g_auditFailed = true;
            PrintFormat("[%s] ★AUDIT FAIL: reject header 写入失败（返回 %u）",
                        InpRunTag, g_lastWriteBytes);
         }
      }
   }
}

//==================== 持仓工具 ====================
bool HasPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      return true;
   }
   return false;
}

ulong FindTicket()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      return tk;
   }
   return 0;
}

int CountMyPositions()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      n++;
   }
   return n;
}

double MoneyPerPriceUnit(double lot)
{
   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contract <= 0.0) contract = 100000.0;
   // USDJPYm：盈亏以 JPY 计，1 手 1.0 价格变动 = contract JPY
   // 换成 USD：除以当前汇率（用 Ask 近似）
   double rate = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(rate <= 0.0) rate = 1.0;
   return lot * contract / rate;
}

// ★OCP 与第二套公式的一致性判据
//   实测：两者在 USDJPYm 上存在 1~2% 的固定相对差（OCP 内部换算约定与
//   "÷出场价" 的近似公式不同），在 ~7 USD 风险上表现为 0.05~0.13 USD 绝对差。
//   因此判据 = max(绝对容差, 相对容差% × |OCP|)，并把实际差异记录下来备审。
bool OcpAgrees(double ocpVal, double formulaVal)
{
   double diff = MathAbs(ocpVal - formulaVal);
   double lim  = MathMax(InpOcpTolUsd, InpOcpTolRelPct / 100.0 * MathAbs(ocpVal));
   if(diff <= lim) return true;
   PrintFormat("[%s] ★OCP MISMATCH ocp=%.4f formula=%.4f diff=%.4f > lim=%.4f (abs=%.4f rel=%.2f%%)",
               InpRunTag, ocpVal, formulaVal, diff, lim, InpOcpTolUsd, InpOcpTolRelPct);
   return false;
}

// ★★★ N1R 修复 4：恢复 OrderCalcProfit 作为权威风险值
//   旧实现（N1）只用 contract/rate 公式估算 USDJPY 风险，被 GPT 判定 needs_repair。
//   新实现：
//     · OrderCalcProfit  → 权威值（用于 sizing 与 actual SL risk）
//     · 独立合约公式      → 第二套审计值
//     · 两者差异 > InpOcpTolUsd → g_ocpMismatch++ 且 run 作废
//   注意：OrderCalcProfit 的 profit 参数是【按 lot 的名义盈亏】，
//         对空头传 ORDER_TYPE_SELL，开平价与平价按方向给。
bool CalcRiskBoth(double entryPx, double exitPx, double lot, bool isLong,
                  double &ocpVal, double &formulaVal, int &ocpErr)
{
   ocpVal = 0.0; formulaVal = 0.0; ocpErr = 0;

   // --- 权威值：OrderCalcProfit ---
   ResetLastError();
   double ocp = 0.0;
   bool ok = false;
   if(isLong)
      ok = OrderCalcProfit(ORDER_TYPE_BUY,  _Symbol, lot, entryPx, exitPx, ocp);
   else
      ok = OrderCalcProfit(ORDER_TYPE_SELL, _Symbol, lot, entryPx, exitPx, ocp);
   if(!ok) ocpErr = GetLastError();
   ocpVal = ocp;

   // --- 第二套：独立合约公式（JPY 计价 → 除以汇率换成 USD）---
   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contract <= 0.0) contract = 100000.0;
   double rate = exitPx;
   if(rate <= 0.0) rate = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(rate <= 0.0) rate = 1.0;
   double diff = isLong ? (exitPx - entryPx) : (entryPx - exitPx);
   formulaVal = diff * contract * lot / rate;   // ← 与审计/报告同口径（÷出场价）

   return ok;
}

double AlignLot(double raw)
{
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(vstep <= 0.0) vstep = 0.01;
   double lot = MathFloor(raw / vstep + 1e-9) * vstep;   // ★向下取整
   if(lot > vmax) lot = MathFloor(vmax / vstep + 1e-9) * vstep;
   return lot;
}

double LotForRisk(double stopDist, double &riskBudget, double &actualRisk)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   riskBudget = 0.0; actualRisk = 0.0;
   if(eq <= 0.0 || stopDist <= 0.0) return 0.0;

   riskBudget = eq * InpRiskPct / 100.0;

   // ★N1R 修复 4：用 OrderCalcProfit 作为权威 sizing 依据
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask <= 0.0 || bid <= 0.0) return 0.0;

   // 试算用的"1 手到止损"损失（取多头方向，USDJPY 多空量级对称）
   double trialEntry = ask;
   double trialSL    = ask - stopDist;
   double ocp1 = 0.0, fml1 = 0.0; int e1 = 0;
   bool ok1 = CalcRiskBoth(trialEntry, trialSL, 1.0, true, ocp1, fml1, e1);
   double riskPerLot = ok1 ? MathAbs(ocp1) : MathAbs(fml1);
   if(riskPerLot <= 0.0) return 0.0;

   double ideal = riskBudget / riskPerLot;
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lot  = AlignLot(ideal);
   if(lot < vmin) { if(!InpAllowMinLotOvershoot) return 0.0; lot = vmin; }

   // ★最终 actual SL risk 用 OCP 重算（权威值），独立公式作第二套
   double ocpF = 0.0, fmlF = 0.0; int eF = 0;
   bool isLong = (ask > 0.0);
   CalcRiskBoth(trialEntry, trialSL, lot, isLong, ocpF, fmlF, eF);
   actualRisk = MathAbs(ocpF);
   // ★N1R：统一走 OcpAgrees（max(绝对容差, 相对容差%×|OCP|)）
   if(!OcpAgrees(ocpF, fmlF))
   {
      g_ocpMismatch++;
      g_auditFailed = true;
   }

   double cap = eq * InpMinLotMaxRiskPct / 100.0;
   if(actualRisk > cap) return 0.0;
   return lot;
}

//==================== 交易 ====================
bool PickFilling(ENUM_ORDER_TYPE_FILLING &f)
{
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) != 0) { f = ORDER_FILLING_FOK; return true; }
   if((mode & SYMBOL_FILLING_IOC) != 0) { f = ORDER_FILLING_IOC; return true; }
   f = ORDER_FILLING_RETURN; return true;
}

bool OpenTrade(int dir, double atr)
{
   double stopDist = InpSL_ATR * atr;
   if(stopDist <= 0.0) return false;
   double riskBudget = 0.0, actualRisk = 0.0;
   double lot = LotForRisk(stopDist, riskBudget, actualRisk);
   datetime tNow = TimeCurrent();
   if(lot <= 0.0)
   {
      g_rejRisk++;
      WriteReject(tNow, "min_lot_over_budget_or_cap", riskBudget / MathMax(stopDist, 1e-9),
                  0.0, riskBudget, actualRisk);
      return false;
   }

   double price = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0) return false;
   double sl = (dir > 0) ? price - stopDist : price + stopDist;
   double tp = 0.0;
   double tpDist = InpTP_RMult * stopDist;
   tp = (dir > 0) ? price + tpDist : price - tpDist;

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = _Symbol;
   req.volume       = lot;
   req.type         = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price        = NormalizeDouble(price, _Digits);
   req.sl           = NormalizeDouble(sl, _Digits);
   req.tp           = NormalizeDouble(tp, _Digits);
   req.deviation    = 50;
   req.magic        = InpMagic;
   req.comment      = "open_jsb30";
   ENUM_ORDER_TYPE_FILLING f;
   PickFilling(f);
   req.type_filling = f;

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      if(InpVerboseLog)
         PrintFormat("[%s] open fail retcode=%d err=%d", InpRunTag, res.retcode, GetLastError());
      return false;
   }

   g_ticket = res.order;
   if(!PositionSelectByTicket(g_ticket) && res.deal > 0)
   {
      // 用 deal 反查 position
      if(HistorySelectByPosition(res.deal)) { }
   }
   g_ticket = FindTicket();
   if(g_ticket == 0) return false;
   if(!PositionSelectByTicket(g_ticket)) return false;

   g_dir            = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   g_entryPrice     = PositionGetDouble(POSITION_PRICE_OPEN);
   g_initSL         = PositionGetDouble(POSITION_SL);
   g_initTP         = PositionGetDouble(POSITION_TP);
   g_riskBudget     = riskBudget;
   g_actualSLRisk   = actualRisk;
   g_entryATR       = atr;
   g_barsHeld       = 0;
   g_entryTimeServer= (datetime)PositionGetInteger(POSITION_TIME);
   g_entryOffset    = OffsetForServerTime(g_entryTimeServer);
   if(g_entryOffset > 0) g_entryTimeUtc = ServerToUtc(g_entryTimeServer, g_entryOffset);
   else                  g_entryTimeUtc = 0;
   g_dayTraded      = true;

   if(InpVerboseLog)
      PrintFormat("[%s] OPEN dir=%d lot=%.2f price=%.5f sl=%.5f tp=%.5f risk=%.2f off=%d",
                  InpRunTag, g_dir, lot, g_entryPrice, g_initSL, g_initTP, actualRisk, g_entryOffset);
   return true;
}

bool CloseTrade(string reason)
{
   if(!HasPosition()) return false;
   if(!PositionSelectByTicket(g_ticket)) g_ticket = FindTicket();
   if(g_ticket == 0) return false;
   if(!PositionSelectByTicket(g_ticket)) return false;

   int    dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   double vol = PositionGetDouble(POSITION_VOLUME);

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = _Symbol;
   req.position     = g_ticket;
   req.volume       = vol;
   req.deviation    = 50;
   req.magic        = InpMagic;
   req.comment      = "close_" + reason;
   req.type         = (dir > 0) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   ENUM_ORDER_TYPE_FILLING f;
   PickFilling(f);
   req.type_filling = f;
   req.price        = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      if(InpVerboseLog)
         PrintFormat("[%s] close(%s) fail retcode=%d err=%d", InpRunTag, reason, res.retcode, GetLastError());
      return false;
   }
   g_ticket = 0;
   return true;
}

//==================== 出场审计（逐 closing deal）====================
void RecordClosingDeal(ulong dealTicket)
{
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;
   long en = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY) return;
   if(g_auditFh == INVALID_HANDLE) { g_auditFailed = true; return; }

   // ★N1R 修复 3：只【检查】是否已写，不在此标记
   if(IsDealSeen(dealTicket)) { g_dupHits++; return; }

   double dProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
   double dSwap   = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
   double dComm   = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
   double net     = dProfit + dSwap + dComm;
   double price   = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double vol     = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   ulong  pid     = (ulong)HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
   datetime tSrv  = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
   long   dtype   = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
   int    dir     = (dtype == DEAL_TYPE_SELL) ? 1 : -1;

   // 反查开仓腿均价
   double entryPx = g_entryPrice, entryVol = 0.0;
   datetime entrySrv = g_entryTimeServer;
   if(HistorySelectByPosition(pid))
   {
      int nd = HistoryDealsTotal(); double spv = 0.0, sv = 0.0; datetime et = 0;
      for(int i = 0; i < nd; i++)
      {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0) continue;
         if(HistoryDealGetInteger(tk, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
         double p = HistoryDealGetDouble(tk, DEAL_PRICE);
         double v = HistoryDealGetDouble(tk, DEAL_VOLUME);
         spv += p * v; sv += v;
         datetime tt = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
         if(et == 0 || tt < et) et = tt;
      }
      if(sv > 0.0) entryPx = spv / sv;
      entryVol = sv;
      if(et > 0) entrySrv = et;
   }
   if(entryPx <= 0.0 || price <= 0.0 || vol <= 0.0 || pid == 0)
   {
      g_auditFailed = true;
      PrintFormat("[%s] ★AUDIT FAIL 字段缺失 ticket=%I64u pid=%I64u", InpRunTag, dealTicket, pid);
   }

   string closeType = "full";
   if(PositionSelectByTicket(pid) && PositionGetDouble(POSITION_VOLUME) > 0.0)
      closeType = "partial";

   // 出场原因
   string reason = "expert";
   string cmt = HistoryDealGetString(dealTicket, DEAL_COMMENT);
   long rsn = HistoryDealGetInteger(dealTicket, DEAL_REASON);
   if(StringFind(cmt, "window_end") >= 0)      reason = "window_end";
   else if(StringFind(cmt, "time_exit") >= 0)  reason = "time_exit";
   else if(StringFind(cmt, "tp") >= 0)         reason = "tp";
   else if(StringFind(cmt, "sl") >= 0)         reason = "sl";
   else if(rsn == DEAL_REASON_SL)              reason = "sl";
   else if(rsn == DEAL_REASON_TP)              reason = "tp";
   else if(rsn == DEAL_REASON_SO)              reason = "stopout";

   int offE = OffsetForServerTime(entrySrv);
   int offX = OffsetForServerTime(tSrv);
   datetime utcE = (offE > 0) ? ServerToUtc(entrySrv, offE) : 0;
   datetime utcX = (offX > 0) ? ServerToUtc(tSrv,    offX) : 0;

   // ★N1R 修复 3 + 4：OCP 与独立公式对照（容差外 → invalid）
   double ocpVal = 0.0, ocpCmp = 0.0;
   int    ocpErr = 0;
   bool   ocpOk  = CalcRiskBoth(entryPx, price, vol, (dir > 0), ocpVal, ocpCmp, ocpErr);
   if(!ocpOk || !OcpAgrees(ocpVal, ocpCmp))
   {
      g_ocpMismatch++;
      g_auditFailed = true;
      PrintFormat("[%s] ★OCP problem ticket=%I64u ocp=%.4f formula=%.4f ocp_err=%d",
                  InpRunTag, dealTicket, ocpVal, ocpCmp, ocpErr);
   }

   g_lastWriteBytes = FileWrite(g_auditFh, InpRunTag, _Symbol,
             IntegerToString((long)dealTicket),
             IntegerToString((long)pid),
             TimeToString(entrySrv, TIME_DATE|TIME_SECONDS),
             (utcE > 0) ? TimeToString(utcE, TIME_DATE|TIME_SECONDS) : "undetermined",
             TimeToString(tSrv, TIME_DATE|TIME_SECONDS),
             (utcX > 0) ? TimeToString(utcX, TIME_DATE|TIME_SECONDS) : "undetermined",
             DoubleToString(entryPx, _Digits),
             DoubleToString(price, _Digits),
             DoubleToString(vol, 2),
             DoubleToString(dProfit, 2),
             DoubleToString(dSwap, 2),
             DoubleToString(dComm, 2),
             DoubleToString(net, 2),
             closeType, reason,
             DoubleToString(g_riskBudget, 2),
             DoubleToString(g_actualSLRisk, 2),
             "",
             (offX > 0) ? IntegerToString(offX) : "undetermined",
             DoubleToString(ocpVal, 2),
             DoubleToString(ocpCmp, 2),
             IntegerToString(ocpErr),
             DoubleToString(MathAbs(ocpVal - ocpCmp), 4),
             DoubleToString(MathMax(InpOcpTolUsd, InpOcpTolRelPct / 100.0 * MathAbs(ocpVal)), 4));
   FileFlush(g_auditFh);

   // ★N1R 修复 3：检查 FileWrite 结果；失败即 fail-close，且【不标记 ticket】
   if(g_lastWriteBytes <= 0)
   {
      g_auditFailed = true;
      PrintFormat("[%s] ★AUDIT FAIL: FileWrite 返回 %u 字节（ticket=%I64u）→ run 作废",
                  InpRunTag, g_lastWriteBytes, dealTicket);
      return;                                   // ★不 Mark、不 ++g_writtenDeals
   }
   MarkDealSeen(dealTicket);                     // ★确认写入成功后才标记
   g_writtenDeals++;

   g_nTrades++;
   if(net > 0.0) g_nWin++;
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      RecordClosingDeal(trans.deal);
}

// 补扫（窗口结束时 MT5 会强平，但本 EA 在 UTC 20:00 已主动平仓）
void CatchUpAudit()
{
   if(!InpWriteAudit) return;
   if(!HistorySelect(0, TimeCurrent() + 7 * 86400)) return;
   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
   {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0) continue;
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != InpMagic) continue;
      long en = HistoryDealGetInteger(tk, DEAL_ENTRY);
      if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY) continue;
      RecordClosingDeal(tk);
   }
}

//==================== UTC 日切换 ====================
datetime UtcDayOf(datetime tUtc)
{
   MqlDateTime s; TimeToStruct(tUtc, s);
   datetime d = (datetime)((long)tUtc - (long)s.hour*3600 - (long)s.min*60 - s.sec);
   return d;
}

// 把 server 时间换算到 UTC（失败即返回 0）
datetime ToUtc(datetime tServer)
{
   int off = OffsetForServerTime(tServer);
   if(off <= 0) { g_rejOffset++; return 0; }
   return ServerToUtc(tServer, off);
}

// ★★★ N1R 修复 1：每日 range 状态机（增量构建）
//   旧实现缺陷（GPT 源码复核指出）：
//     ComputeDailyRange() 只在【UTC 日切换】时调用一次，而 UTC 日切换发生在 UTC 00:00，
//     此时预注册的 UTC00-06 range 窗口【尚未形成】→ range 为空/不完整，
//     且 UTC06 之后【没有任何机制再形成 range】→ g_rangeReady 永远为 false。
//   新实现：在每根【已收盘】M30 bar 到达时增量累积当日 range；
//     只有 range 窗口【完整结束】后才置 g_rangeReady=true 并冻结。
//     未收盘 bar 一律不参与（用 barServerOpen + 1800 判定）。
void RangeStateOnNewClosedBar(datetime barServerOpen, double barHigh, double barLow)
{
   // 该已收盘 bar 的 server 区间 = [barServerOpen, barServerOpen+1800)
   int off = OffsetForServerTime(barServerOpen);
   if(off <= 0) return;                       // offset 未定 → 由 ToUtc 侧统一 fail-close

   datetime btUtc      = ServerToUtc(barServerOpen, off);
   datetime btUtcClose = (datetime)((long)btUtc + 1800);
   datetime dayUtc     = UtcDayOf(btUtc);

   // --- UTC 日切换：清空上一天状态 ---
   if(dayUtc != g_rangeDay)
   {
      g_rangeDay      = dayUtc;
      g_rangeHi       = -1e18;
      g_rangeLo       = 1e18;
      g_rangeCount    = 0;
      g_rangeReady    = false;
      g_rangeFrozenHi = 0.0;
      g_rangeFrozenLo = 0.0;
   }

   datetime wS = (datetime)((long)dayUtc + (long)InpRangeStartUtcHour * 3600);
   datetime wE = (datetime)((long)dayUtc + (long)InpRangeEndUtcHour   * 3600);

   // --- 只接收【完整落在 range 窗口内】的已收盘 bar ---
   if(!g_rangeReady && btUtc >= wS && btUtcClose <= wE)
   {
      if(barHigh > g_rangeHi) g_rangeHi = barHigh;
      if(barLow  < g_rangeLo) g_rangeLo = barLow;
      g_rangeCount++;
   }

   // --- range 窗口完整结束后才冻结 ---
   if(!g_rangeReady && btUtcClose >= wE && g_rangeCount > 0 && g_rangeHi > g_rangeLo)
   {
      g_rangeFrozenHi = g_rangeHi;
      g_rangeFrozenLo = g_rangeLo;
      g_rangeReady    = true;
   }
}

// 突破窗内读 range（只用冻结值）
bool RangeForBreakout(double &hi, double &lo)
{
   if(!g_rangeReady) return false;
   hi = g_rangeFrozenHi; lo = g_rangeFrozenLo;
   return (hi > lo);
}

//==================== 信号 ====================
double ATR(int shift)
{
   double b[]; if(CopyBuffer(g_atrHandle, 0, shift, 1, b) == 1) return b[0];
   return 0.0;
}

//==================== 主循环 ====================
void OnInit()
{
   g_sigTF = PERIOD_M30;   // 固定 M30
   if(InpSignalTFMinutes != 30)
      PrintFormat("[%s] ★警告：InpSignalTFMinutes=%d 但本 EA 固定使用 M30", InpRunTag, InpSignalTFMinutes);

   g_atrHandle = iATR(_Symbol, TF(), InpATRPeriod);
   if(g_atrHandle == INVALID_HANDLE)
   { PrintFormat("[%s] iATR 失败", InpRunTag); return; }

   OpenAudit();
   if(g_auditFailed) { PrintFormat("[%s] ★审计初始化失败 -> 终止", InpRunTag); ExpertRemove(); return; }

   // ★round-trip 自测（冬令周 / 夏令周 / DST 切换周）
   if(InpRunTimeSelfcheck) RunOffsetSelfTest();

   PrintFormat("[%s] init ok range=UTC%02d-%02d breakout=UTC%02d-%02d flat=UTC%02d "
               "SL=%.2fxATR TP=%.2fR maxBars=%d risk=%.2f%% overshoot=%s dynDST=%s",
               InpRunTag, InpRangeStartUtcHour, InpRangeEndUtcHour,
               InpBreakoutStartUtcHour, InpBreakoutEndUtcHour, InpHardFlatUtcHour,
               InpSL_ATR, InpTP_RMult, InpMaxBarsInTrade, InpRiskPct,
               InpAllowMinLotOvershoot ? "on" : "off", InpUseDynamicDstOffset ? "on" : "off");
}

// round-trip 自测：用合成周界时间验证 offset 推导 + 反推
// ★★★ N1R 修复 2b：两层测试
//   第一层（本函数）：纯函数 unit self-test，用【三组不同的历史日期】
//     分别对应冬令周 / 夏令周 / DST 切换周，逐一验证 utc -> offset -> server -> utc
//     旧实现三组都构造了同一个 `2023.01.01 22:00`，等于没测三个时期（GPT 指出）。
//   第二层：RealWeekRoundTripTest() —— 读真实 TRAIN bar 逐周验证
void RunOffsetSelfTest()
{
   // 三组真实周日 22:00 UTC 开盘时刻（欧洲 DST：3 月末切换、10 月末切换）
   string labels[3] = {"winter  (Jan, GMT+2)", "summer  (Jul, GMT+3)", "dst-trans(Mar 26)"};
   string dstr[3]   = {"2023.01.08 22:00",      "2023.07.09 22:00",      "2023.03.26 22:00"};

   int okN = 0, totN = 0;
   for(int c = 0; c < 3; c++)
   {
      datetime utcOpen = StringToTime(dstr[c]);
      for(int off = InpExpectedServerOffsetMin; off <= InpExpectedServerOffsetMax; off++)
      {
         datetime srv = UtcToServer(utcOpen, off);
         int got = -1; string why = "";
         bool r = InferOffsetFromWeekOpen(srv, got, why);
         datetime back = (r && got > 0) ? ServerToUtc(srv, got) : 0;
         bool rt = (r && back == utcOpen);
         totN++; if(rt) okN++;
         PrintFormat("[%s] UNIT %-22s utc=%s in_off=%d out_off=%d server=%s back=%s %s (%s)",
                     InpRunTag, labels[c],
                     TimeToString(utcOpen, TIME_DATE|TIME_MINUTES), off, got,
                     TimeToString(srv,  TIME_DATE|TIME_MINUTES),
                     (back > 0) ? TimeToString(back, TIME_DATE|TIME_MINUTES) : "none",
                     rt ? "OK" : "FAIL", why);
      }
   }
   PrintFormat("[%s] UNIT 汇总：%d/%d 通过", InpRunTag, okN, totN);
   if(okN < totN) { g_offsetUndetermined = true; g_offsetFailReason = "unit self-test 未全通过"; }

   // ---- 第二层：真实历史周 round-trip ----
   RealWeekRoundTripTest();
}

// ★N1R 第二层：读真实历史 bar，对实际交易周跑完整
//   server historical bar -> week identification -> inferred offset
//   -> server→UTC -> UTC→server round-trip
void RealWeekRoundTripTest()
{
   int n = iBars(_Symbol, TF());
   if(n <= 0) { PrintFormat("[%s] REALWEEK 无 bar，跳过", InpRunTag); return; }

   datetime lastBar = iTime(_Symbol, TF(), 0);
   if(lastBar <= 0) return;

   int checked = 0, okW = 0, failW = 0, printed = 0;
   datetime cur = lastBar;
   for(int k = 0; k < 80 && checked < 30; k++)     // 最多回溯 80 周，采 30 个样本
   {
      datetime wk = WeekKeyUtc(cur);
      if(wk <= 0) break;
      datetime firstBar;
      if(WeekFirstBarServer_At(wk, firstBar))
      {
         int off = -1; string why = "";
         if(InferOffsetFromWeekOpen(firstBar, off, why) && off > 0)
         {
            datetime utc  = ServerToUtc(firstBar, off);
            datetime back = UtcToServer(utc, off);
            bool rt = (back == firstBar);
            if(rt) okW++; else failW++;
            if(printed < 6)
            {
               PrintFormat("[%s] REALWEEK wk=%s firstBar=%s off=+%d utc=%s roundtrip=%s",
                           InpRunTag, TimeToString(wk, TIME_DATE),
                           TimeToString(firstBar, TIME_DATE|TIME_MINUTES), off,
                           TimeToString(utc, TIME_DATE|TIME_MINUTES), rt ? "OK" : "FAIL");
               printed++;
            }
         }
         else
         {
            failW++;
            if(printed < 6)
            {
               PrintFormat("[%s] REALWEEK wk=%s firstBar=%s 推导失败: %s",
                           InpRunTag, TimeToString(wk, TIME_DATE),
                           TimeToString(firstBar, TIME_DATE|TIME_MINUTES), why);
               printed++;
            }
         }
         checked++;
      }
      cur = (datetime)((long)cur - 7 * 86400);
   }
   PrintFormat("[%s] REALWEEK 汇总：checked=%d OK=%d FAIL=%d", InpRunTag, checked, okW, failW);
   if(failW > 0)
   {
      g_offsetUndetermined = true;
      g_offsetFailReason = StringFormat("REALWEEK 有 %d/%d 个周 round-trip 失败", failW, checked);
   }
   if(checked == 0)
   {
      g_offsetUndetermined = true;
      g_offsetFailReason = "REALWEEK 未能取到任何交易周的周首 bar";
   }
}

void OnDeinit(const int reason)
{
   // ★先补扫再关文件
   CatchUpAudit();

   // 自检文件
   {
      string sf = AuditDir() + "\\audit_selfcheck.csv";
      int fh = FileOpen(sf, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(fh == INVALID_HANDLE) fh = FileOpen(sf, FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(fh != INVALID_HANDLE)
      {
         FileWrite(fh, "run_tag,written_deals,dup_hits,audit_failed,offset_undetermined,"
                       "offset_fail_count,offset_fail_reason,trades,wins,active_positions,"
                       "skip_range_notready,skip_range_toonarrow,skip_nobreak,skip_daytraded,"
                       "skip_badwindow,rej_risk,rej_offset,ocp_mismatch,reason");
         FileWrite(fh, InpRunTag, IntegerToString(g_writtenDeals), IntegerToString(g_dupHits),
                   g_auditFailed ? "1" : "0",
                   g_offsetUndetermined ? "1" : "0",
                   IntegerToString(g_offsetFailCount),
                   g_offsetFailReason,
                   IntegerToString(g_nTrades), IntegerToString(g_nWin),
                   IntegerToString(CountMyPositions()),
                   IntegerToString(g_skipRangeNotReady), IntegerToString(g_skipRangeTooNarrow),
                   IntegerToString(g_skipNoBreak), IntegerToString(g_skipDayTraded),
                   IntegerToString(g_skipBadWindow), IntegerToString(g_rejRisk),
                   IntegerToString(g_rejOffset), IntegerToString(g_ocpMismatch), IntegerToString(reason));
         FileClose(fh);
      }
   }

   if(g_auditFh  != INVALID_HANDLE) { FileClose(g_auditFh);  g_auditFh  = INVALID_HANDLE; }
   if(g_rejectFh != INVALID_HANDLE) { FileClose(g_rejectFh); g_rejectFh = INVALID_HANDLE; }
   if(g_atrHandle!= INVALID_HANDLE) { IndicatorRelease(g_atrHandle); g_atrHandle = INVALID_HANDLE; }

   PrintFormat("[%s] === END reason=%d trades=%d win=%d written=%d dup=%d "
               "offsetFail=%d rangeReadySkip=%d narrow=%d noBreak=%d dayTraded=%d badWin=%d "
               "rejRisk=%d rejOffset=%d ===",
               InpRunTag, reason, (int)g_nTrades, (int)g_nWin, (int)g_writtenDeals,
               (int)g_dupHits, g_offsetFailCount, (int)g_skipRangeNotReady,
               (int)g_skipRangeTooNarrow, (int)g_skipNoBreak, (int)g_skipDayTraded,
               (int)g_skipBadWindow, (int)g_rejRisk, (int)g_rejOffset);
}

void OnTick()
{
   // 0) offset 失败 -> fail-close
   if(g_offsetUndetermined && InpUseDynamicDstOffset)
   {
      // 不静默继续
      return;
   }

   datetime tSrv = TimeCurrent();
   datetime tUtc = ToUtc(tSrv);
   if(tUtc == 0) return;                        // offset 无法确定
   datetime todayUtc = UtcDayOf(tUtc);

   // 1) UTC 日切换：只重置"当日是否已成交"，range 由增量状态机构建
   if(todayUtc != g_curUtcDay)
   {
      g_curUtcDay = todayUtc;
      g_dayTraded = false;
   }

   // 1b) ★N1R 修复 1：每根【已收盘】M30 bar 到达时增量构建当日 range
   //     判据：iTime(shift=0) 是本根未收盘 bar；shift=1 是最近已收盘 bar。
   //     用 shift=1 的 bar 时间作为"新收盘"的事件键。
   datetime closedBarT = iTime(_Symbol, TF(), 1);
   if(closedBarT > 0 && closedBarT != g_lastClosedBar)
   {
      g_lastClosedBar = closedBarT;
      double bh = iHigh(_Symbol, TF(), 1);
      double bl = iLow (_Symbol, TF(), 1);
      RangeStateOnNewClosedBar(closedBarT, bh, bl);
      // 该已收盘 bar 也用于持仓时间计数
      if(HasPosition())
      {
         g_barsHeld++;
         if(g_barsHeld >= InpMaxBarsInTrade) { CloseTrade("time_exit"); return; }
      }
   }

   MqlDateTime su; TimeToStruct(tUtc, su);
   int utcMin = su.hour * 60 + su.min;

   // 2) 持仓管理（优先级最高）
   if(HasPosition())
   {
      // hard-flat：UTC 20:00 前必须平仓
      if(utcMin >= InpHardFlatUtcHour * 60)
      {
         CloseTrade("window_end");
         return;
      }
      // SL/TP 由券商侧执行（req.sl / req.tp 已设）
      return;
   }

   // 3) 无仓：只在 breakout 窗内评估
   if(utcMin < InpBreakoutStartUtcHour * 60 || utcMin >= InpBreakoutEndUtcHour * 60) return;
   if(g_dayTraded) { g_skipDayTraded++; return; }

   double rHi = 0.0, rLo = 0.0;
   if(!RangeForBreakout(rHi, rLo)) { g_skipRangeNotReady++; return; }

   // 4) 只在【刚收盘】的 M30 边界上评估一次（已在 1b 记录 g_lastClosedBar）
   if(closedBarT <= 0 || closedBarT != g_evalBar) { }
   if(closedBarT == g_evalBar) return;
   g_evalBar = closedBarT;

   double atr = ATR(1);                       // ★用已收盘 bar 的 ATR
   if(atr <= 0.0) return;
   double rangeW = rHi - rLo;
   if(rangeW < InpMinRangeATRMult * atr) { g_skipRangeTooNarrow++; return; }

   double close1 = iClose(_Symbol, TF(), 1);   // 已收盘 bar 收盘价
   if(close1 <= 0.0) return;

   int dir = 0;
   if(close1 > rHi)      dir =  1;
   else if(close1 < rLo) dir = -1;
   if(dir == 0) { g_skipNoBreak++; return; }
   if(dir > 0 && !InpAllowLong)  { g_skipNoBreak++; return; }
   if(dir < 0 && !InpAllowShort) { g_skipNoBreak++; return; }

   OpenTrade(dir, atr);
}
//+------------------------------------------------------------------+




