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
datetime WeekKeyUtc(datetime tUtc)
{
   MqlDateTime s; TimeToStruct(tUtc, s);
   int dow = s.day_of_week;                 // 0=Sun..6=Sat
   int back = (dow == 0) ? 0 : dow;          // 回到本周日
   datetime dayStart = (datetime)((long)tUtc - (long)s.hour * 3600 - (long)s.min * 60 - s.sec);
   datetime sunday = (datetime)((long)dayStart - (long)back * 86400);
   return sunday;                            // 该"周"的周日 00:00 UTC
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
   // 该 bar 是周日夜间/周一凌晨：允许 22,23,0,1,2
   if(!(obsH >= 22 || obsH <= 2))
   { why = StringFormat("week-open hour=%d 不在 22..2", obsH); return false; }

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
bool WeekFirstBarServer(datetime weekKeyUtc, int offsetGuess, datetime &outServer)
{
   // 从 weekKeyUtc 起，在 server 时间轴上扫描前 8 小时，找第一根 M30 bar
   datetime startServer = UtcToServer(weekKeyUtc, offsetGuess);
   for(int i = 0; i < 16; i++)
   {
      datetime t = (datetime)((long)startServer + (long)i * 1800);
      int shift = iBarShift(_Symbol, PERIOD_M30, t, false);
      if(shift >= 0 && shift < iBars(_Symbol, PERIOD_M30))
      {
         datetime bt = iTime(_Symbol, PERIOD_M30, shift);
         if(bt >= t - 1800 && bt <= t + 1800) { outServer = bt; return true; }
      }
   }
   return false;
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

datetime g_lastM30Bar   = 0;      // 最近一根【已收盘】M30 的 bar 时间
datetime g_curUtcDay    = 0;      // 当前 UTC 日（00:00 UTC）
bool     g_dayTraded    = false;  // 该 UTC 日是否已成交
double   g_rangeHi      = 0.0;
double   g_rangeLo      = 0.0;
bool     g_rangeReady   = false;
int      g_rangeCount   = 0;      // 参与 range 的 M30 bar 数

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
bool     g_auditFailed = false;

#define MAX_DEALTICKET 8192
ulong    g_seen[MAX_DEALTICKET];
int      g_seenCount = 0;

//==================== 审计 ====================
string AuditDir() { return "dshtrend\\" + InpRunTag; }

const string AUDIT_HEADER =
   "run_tag,symbol,deal_ticket,position_id,entry_time_server,entry_time_utc,"
   "exit_time_server,exit_time_utc,entry,exit,volume,profit,swap,commission,net,"
   "close_type,exit_reason,risk_budget,actual_sl_risk,reject_reason,server_utc_offset";

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

bool DealSeen(ulong ticket)
{
   for(int i = 0; i < g_seenCount; i++) if(g_seen[i] == ticket) return true;
   if(g_seenCount < MAX_DEALTICKET) g_seen[g_seenCount++] = ticket;
   return false;
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
   FileWrite(g_rejectFh, InpRunTag, _Symbol,
             TimeToString(g_curUtcDay, TIME_DATE),
             TimeToString(tServer, TIME_DATE|TIME_SECONDS),
             (off > 0) ? TimeToString(tUtc, TIME_DATE|TIME_SECONDS) : "undetermined",
             (off > 0) ? IntegerToString(off) : "undetermined",
             reason,
             DoubleToString(g_rangeHi, _Digits), DoubleToString(g_rangeLo, _Digits),
             DoubleToString(atr, _Digits), DoubleToString(rm, 4),
             DoubleToString(rawLot, 4), DoubleToString(finalLot, 2),
             DoubleToString(riskBudget, 2), DoubleToString(actualRisk, 2));
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
   if(!exists) FileWrite(g_auditFh, AUDIT_HEADER);

   string rf = AuditDir() + "\\reject_audit.csv";
   bool rexists = FileIsExist(rf, FILE_COMMON);
   g_rejectFh = FileOpen(rf, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(g_rejectFh == INVALID_HANDLE)
      g_rejectFh = FileOpen(rf, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(g_rejectFh != INVALID_HANDLE)
   {
      FileSeek(g_rejectFh, 0, SEEK_END);
      if(!rexists) FileWrite(g_rejectFh, REJECT_HEADER);
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
   double mpp = MoneyPerPriceUnit(1.0);            // 每 1 手每 1.0 价格的 USD
   if(mpp <= 0.0) return 0.0;
   double ideal = riskBudget / (stopDist * mpp);

   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lot  = AlignLot(ideal);
   bool   over = false;
   if(lot < vmin) { if(!InpAllowMinLotOvershoot) return 0.0; lot = vmin; over = true; }

   actualRisk = stopDist * mpp * lot;
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
   if(g_auditFh == INVALID_HANDLE) return;

   // ★去重放在"确认能写入"的路径上（R4 教训：入口标记会造成永久漏记）
   if(DealSeen(dealTicket)) { g_dupHits++; return; }

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

   FileWrite(g_auditFh, InpRunTag, _Symbol,
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
             (offX > 0) ? IntegerToString(offX) : "undetermined");
   FileFlush(g_auditFh);
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

//==================== 每日 range 计算 ====================
// 只用【已收盘】的 M30 bar：barClose = barOpen + 1800
void ComputeDailyRange(datetime utcDay)
{
   g_rangeReady = false; g_rangeCount = 0;
   g_rangeHi = -1e18; g_rangeLo = 1e18;

   int bars = iBars(_Symbol, TF());
   if(bars <= 0) return;
   int need = (InpRangeEndUtcHour - InpRangeStartUtcHour) * 2 + 4;   // 2 根/小时
   if(need > bars) need = bars;

   for(int i = 0; i < need; i++)
   {
      datetime bt = iTime(_Symbol, TF(), i);
      if(bt <= 0) continue;
      datetime btClose = (datetime)((long)bt + 1800);          // ★只用已收盘 bar
      int off = OffsetForServerTime(bt);
      if(off <= 0) return;
      datetime btUtc = ServerToUtc(bt, off);
      datetime btUtcClose = ServerToUtc(btClose, off);
      // 该 bar 必须完整落在 [utcDay + startHour, utcDay + endHour)
      datetime wS = (datetime)((long)utcDay + (long)InpRangeStartUtcHour * 3600);
      datetime wE = (datetime)((long)utcDay + (long)InpRangeEndUtcHour   * 3600);
      if(btUtc < wS || btUtcClose > wE) continue;
      double h = iHigh(_Symbol, TF(), i);
      double l = iLow (_Symbol, TF(), i);
      if(h > g_rangeHi) g_rangeHi = h;
      if(l < g_rangeLo) g_rangeLo = l;
      g_rangeCount++;
   }
   if(g_rangeCount > 0 && g_rangeHi > g_rangeLo) g_rangeReady = true;
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
void RunOffsetSelfTest()
{
   int cases[][2] = {{2023,1},{2023,7},{2023,3}};   // 冬令 / 夏令 / DST 切换月
   string names[3] = {"winter", "summer", "dst-transition"};
   int okN = 0;
   for(int c = 0; c < 3; c++)
   {
      // 构造一个"周首 bar"的候选 server 时间：周日 22:00 UTC + offset
      for(int off = 2; off <= 3; off++)
      {
         datetime utcOpen = StringToTime(StringFormat("%04d.01.01 22:00", 2023));
         datetime srv = UtcToServer(utcOpen, off);
         int got = -1; string why = "";
         bool r = InferOffsetFromWeekOpen(srv, got, why);
         datetime back = (r && got > 0) ? ServerToUtc(srv, got) : 0;
         bool rt = (r && back == utcOpen);
         if(rt) okN++;
         PrintFormat("[%s] SELFTEST %-14s in_off=%d -> out_off=%d roundtrip=%s (%s)",
                     InpRunTag, names[c], off, got, rt ? "OK" : "FAIL", why);
      }
   }
   PrintFormat("[%s] SELFTEST 汇总：%d/6 通过", InpRunTag, okN);
   if(okN < 6)
   {
      g_offsetUndetermined = true;
      g_offsetFailReason = "round-trip 自测未全通过";
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
                       "skip_badwindow,rej_risk,rej_offset,reason");
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
                   IntegerToString(g_rejOffset), IntegerToString(reason));
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

   // 1) UTC 日切换
   if(todayUtc != g_curUtcDay)
   {
      g_curUtcDay = todayUtc;
      g_dayTraded = false;
      ComputeDailyRange(todayUtc);
   }

   MqlDateTime su; TimeToStruct(tUtc, su);
   int utcMin = su.hour * 60 + su.min;

   // 2) 持仓管理（优先级最高）
   if(HasPosition())
   {
      // hard-flat
      if(utcMin >= InpHardFlatUtcHour * 60)
      {
         CloseTrade("window_end");
         return;
      }
      // 时间退出：按已收盘 M30 计数
      datetime cur30 = iTime(_Symbol, TF(), 0);
      if(cur30 != g_lastM30Bar)
      {
         g_lastM30Bar = cur30;
         g_barsHeld++;
         if(g_barsHeld >= InpMaxBarsInTrade) { CloseTrade("time_exit"); return; }
      }
      // SL/TP 由券商侧执行（req.sl / req.tp 已设）
      return;
   }

   // 3) 无仓：只在 breakout 窗内评估
   if(utcMin < InpBreakoutStartUtcHour * 60 || utcMin >= InpBreakoutEndUtcHour * 60) return;
   if(g_dayTraded) { g_skipDayTraded++; return; }
   if(!g_rangeReady) { g_skipRangeNotReady++; return; }

   // 4) 只在【已收盘】M30 边界上评估一次
   datetime cur30 = iTime(_Symbol, TF(), 0);
   if(cur30 == g_lastM30Bar) return;
   g_lastM30Bar = cur30;

   double atr = ATR(1);                       // ★用已收盘 bar 的 ATR
   if(atr <= 0.0) return;
   double rangeW = g_rangeHi - g_rangeLo;
   if(rangeW < InpMinRangeATRMult * atr) { g_skipRangeTooNarrow++; return; }

   double close1 = iClose(_Symbol, TF(), 1);   // 已收盘 bar 收盘价
   if(close1 <= 0.0) return;

   int dir = 0;
   if(close1 > g_rangeHi)      dir =  1;
   else if(close1 < g_rangeLo) dir = -1;
   if(dir == 0) { g_skipNoBreak++; return; }
   if(dir > 0 && !InpAllowLong)  { g_skipNoBreak++; return; }
   if(dir < 0 && !InpAllowShort) { g_skipNoBreak++; return; }

   OpenTrade(dir, atr);
}
//+------------------------------------------------------------------+

