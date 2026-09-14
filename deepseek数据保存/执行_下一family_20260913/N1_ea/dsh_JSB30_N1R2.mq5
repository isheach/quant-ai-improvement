//+------------------------------------------------------------------+
//|                                                    dsh_JSB30.mq5  |
//|  JSB30 = JPY Session Breakout on M30                             |
//|  ★N1R2 版本（服务器时间重新裁定 + OCP 硬化 + fail-close）           |
//|                                                                  |
//|  依据：                                                          |
//|   · 公共部分/GPT下一步执行流程_JSB30裁定与实施_20260914.md          |
//|   · GPT N1R2 裁定（服务器时间 / OCP sizing / 三方对账 / range       |
//|     完整性 / fail-close / provenance 完整性）                      |
//|                                                                  |
//|  ★★ 时间系统最终裁定（实测，见 JSB30_server_time_reconciliation.md）|
//|     server_utc_offset = 0                                        |
//|     server timestamp == UTC timestamp                            |
//|     DST 只影响市场有没有 bar，不改变时钟换算。                      |
//|     —— 实测证据：四个时段（2023-01/03/07/11）共 160 个交易周，      |
//|        server_minus_GMT_sec 恒为 0；周首 bar 恒为周一 00:00，      |
//|        周末 bar 恒为周日 23:59；M1 first=2022.01.02 22:10（周日）。 |
//|                                                                  |
//|  结构：M30 时段突破，单仓，每日最多一笔，无网格/马丁/加仓          |
//|    · range   : UTC 00:00 -> 06:00  (V2: -> 03:00)                |
//|    · breakout: UTC 07:00 -> 12:00                                |
//|    · hard-flat: UTC 20:00                                        |
//|    · SL = 1.0 x ATR14(M30)；TP = 1.5R (V3: 1.0R)；最长 16 根 M30   |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "3.00"
#property strict

//==================== 输入 ====================
//--- 标识
input string InpRunTag                  = "JSB30";
input long   InpMagic                   = 20260914;

//--- 时段（UTC；★server==UTC，故直接用 server 时间）
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

//--- ★时间系统：N1R2 裁定为 UTC+0（保留为 provenance / 自检开关）
input bool   InpUseDynamicDstOffset     = false;  // ★恒 false：不做任何 offset 转换
input int    InpExpectedServerOffsetMin = 0;      // ★实测 0
input int    InpExpectedServerOffsetMax = 0;      // ★实测 0

//--- ★OCP / 审计（N1R2：主判据改为 DEAL_PROFIT ↔ OCP）
input double InpOcpTolUsd               = 0.05;   // ★预注册：|DEAL_PROFIT - OCP| <= 0.05
input double InpFormulaTolPct           = 5.0;    // 独立公式仅作【诊断】，不参与 pass/fail
input bool   InpFormulaDiagnosticOnly   = true;   // ★恒为诊断用

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

//==================== 时间系统（N1R2：恒等映射）====================
// ★server_utc_offset = 0 —— server 时间戳就是 UTC。
//   不做任何猜测、不做 DST 推导、不做缓存。
//   DST 对策略的唯一影响是"某些周首/周尾的 bar 是否存在"，而不是时钟换算。
datetime ServerToUtc(datetime tServer) { return tServer; }
datetime UtcToServer(datetime tUtc)    { return tUtc; }
int      ServerUtcOffset()             { return 0; }

// 周键：UTC 下的"周一 00:00"（周日 22:00 后归下一周）
datetime WeekKeyUtc(datetime tUtc)
{
   MqlDateTime s; TimeToStruct(tUtc, s);
   int dow = s.day_of_week;
   datetime dayStart = (datetime)((long)tUtc - (long)s.hour*3600 - (long)s.min*60 - s.sec);
   int back = (dow == 0) ? 6 : dow - 1;
   datetime wk = (datetime)((long)dayStart - (long)back * 86400);
   if(dow == 0 && s.hour >= 22) wk = (datetime)((long)wk + 7 * 86400);
   return wk;
}

//==================== 全局状态 ====================
ENUM_TIMEFRAMES g_sigTF  = PERIOD_M30;
ENUM_TIMEFRAMES TF() { return g_sigTF; }
int      g_atrHandle    = INVALID_HANDLE;

//--- ★N1R2 统一 fail-close
bool     g_fatal        = false;
string   g_fatalReason  = "";

void SetFatal(string why)
{
   if(!g_fatal)
   {
      g_fatal = true;
      g_fatalReason = why;
      PrintFormat("[%s] ★★ FATAL: %s → fail-close（不再产生新交易）", InpRunTag, why);
   }
}

//--- range 状态（★N1R2：要求 rangeCount == expected）
datetime g_rangeDay       = 0;
double   g_rangeHi        = 0.0;
double   g_rangeLo        = 1e18;
int      g_rangeCount     = 0;
int      g_rangeExpected  = 0;
bool     g_rangeReady     = false;
double   g_rangeFrozenHi  = 0.0;
double   g_rangeFrozenLo  = 0.0;

//--- 日与持仓
datetime g_curUtcDay      = 0;
bool     g_dayTraded      = false;
datetime g_lastClosedBar  = 0;
datetime g_evalBar        = 0;

ulong    g_ticket         = 0;
int      g_dir            = 0;
double   g_entryPrice     = 0.0;
double   g_initSL         = 0.0;
double   g_initTP         = 0.0;
double   g_riskBudget     = 0.0;
double   g_actualSLRisk   = 0.0;   // 下单时按最终手数用 OCP 重算
double   g_realSLRisk     = 0.0;   // ★成交后按 POSITION_PRICE_OPEN / POSITION_SL 重算
double   g_entryATR       = 0.0;
int      g_barsHeld       = 0;
datetime g_entryTimeUtc   = 0;

//--- 统计
long     g_nTrades = 0, g_nWin = 0;
long     g_skipRangeNotReady = 0, g_skipRangeIncomplete = 0, g_skipRangeTooNarrow = 0;
long     g_skipNoBreak = 0, g_skipDayTraded = 0;
long     g_rejRisk = 0, g_rejOcp = 0;
long     g_riskCapBreach = 0;

//--- 审计
int      g_auditFh  = INVALID_HANDLE;
int      g_rejectFh = INVALID_HANDLE;
long     g_writtenDeals = 0;
long     g_dupHits = 0;
long     g_ocpMismatch = 0;          // ★DEAL_PROFIT ↔ OCP 超容差次数
long     g_formulaDiagOut = 0;       // 独立公式偏离次数（仅诊断）
uint     g_lastWriteBytes = 0;
bool     g_auditFailed = false;

#define MAX_DEALTICKET 8192
ulong    g_seen[MAX_DEALTICKET];
int      g_seenCount = 0;

//==================== 审计 ====================
string AuditDir() { return "dshtrend\\" + InpRunTag; }

// ★N1R2 审计列（deal_profit = MT5 DEAL_PROFIT，主判据）
const string AUDIT_HEADER =
   "run_tag,symbol,deal_ticket,position_id,"
   "entry_time_server,entry_time_utc,exit_time_server,exit_time_utc,"
   "entry,exit,volume,profit,swap,commission,net,"
   "close_type,exit_reason,risk_budget,actual_sl_risk,real_sl_risk,reject_reason,"
   "server_utc_offset,deal_profit,ocp_value,ocp_diff,ocp_err,"
   "formula_value,formula_diff,formula_pct";

const string REJECT_HEADER =
   "run_tag,symbol,utc_day,server_time,utc_time,server_utc_offset,reason,"
   "range_hi,range_lo,range_count,expected_range_count,atr,range_atr_mult,"
   "raw_lot,final_lot,risk_budget,actual_risk,ocp_err";

bool HeaderUnique(const string csvHeader, const string which)
{
   string parts[];
   int n = StringSplit(csvHeader, ',', parts);
   for(int i = 0; i < n; i++)
      for(int j = i + 1; j < n; j++)
         if(parts[i] == parts[j])
         {
            PrintFormat("[%s] ★HEADER FAIL: %s 重复列 '%s'", InpRunTag, which, parts[i]);
            return false;
         }
   return true;
}

bool IsDealSeen(ulong ticket)
{
   for(int i = 0; i < g_seenCount; i++) if(g_seen[i] == ticket) return true;
   return false;
}

void MarkDealSeen(ulong ticket)
{
   if(g_seenCount < MAX_DEALTICKET) g_seen[g_seenCount++] = ticket;
   else SetFatal("seen 表溢出，去重不再可靠");
}

void WriteReject(datetime tServer, string reason, double rawLot, double finalLot,
                 double riskBudget, double actualRisk, int ocpErr)
{
   if(!InpWriteRejectAudit || g_rejectFh == INVALID_HANDLE) return;
   double atr = 0.0;
   double b[]; if(CopyBuffer(g_atrHandle, 0, 0, 1, b) == 1) atr = b[0];
   double rm = (atr > 0.0) ? (g_rangeHi - g_rangeLo) / atr : 0.0;
   g_lastWriteBytes = FileWrite(g_rejectFh, InpRunTag, _Symbol,
             TimeToString(g_curUtcDay, TIME_DATE),
             TimeToString(tServer, TIME_DATE|TIME_SECONDS),
             TimeToString(tServer, TIME_DATE|TIME_SECONDS),   // ★server==UTC
             IntegerToString(ServerUtcOffset()),
             reason,
             DoubleToString(g_rangeHi, _Digits), DoubleToString(g_rangeLo, _Digits),
             IntegerToString(g_rangeCount), IntegerToString(g_rangeExpected),
             DoubleToString(atr, _Digits), DoubleToString(rm, 4),
             DoubleToString(rawLot, 4), DoubleToString(finalLot, 2),
             DoubleToString(riskBudget, 2), DoubleToString(actualRisk, 2),
             IntegerToString(ocpErr));
   if(g_lastWriteBytes <= 0)
   {
      g_auditFailed = true;
      PrintFormat("[%s] ★AUDIT FAIL: reject FileWrite 返回 %u", InpRunTag, g_lastWriteBytes);
      SetFatal("reject audit 写入失败");
   }
   FileFlush(g_rejectFh);
}

void OpenAudit()
{
   if(!InpWriteAudit) return;
   if(!HeaderUnique(AUDIT_HEADER, "trades"))   { g_auditFailed = true; SetFatal("trades header 有重复列"); return; }
   if(!HeaderUnique(REJECT_HEADER, "reject"))  { g_auditFailed = true; SetFatal("reject header 有重复列"); return; }

   string fn = AuditDir() + "\\trades.csv";
   bool exists = FileIsExist(fn, FILE_COMMON);
   g_auditFh = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(g_auditFh == INVALID_HANDLE)
   {
      g_auditFh = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(g_auditFh == INVALID_HANDLE)
      { PrintFormat("[%s] AUDIT FAIL: 无法打开 trades.csv", InpRunTag); g_auditFailed = true;
        SetFatal("trades.csv 无法打开"); return; }
   }
   FileSeek(g_auditFh, 0, SEEK_END);
   if(!exists)
   {
      g_lastWriteBytes = FileWrite(g_auditFh, AUDIT_HEADER);
      if(g_lastWriteBytes <= 0)
      { g_auditFailed = true; SetFatal("trades header 写入失败"); return; }
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
         { g_auditFailed = true; SetFatal("reject header 写入失败"); }
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

double AlignLot(double raw)
{
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(vstep <= 0.0) vstep = 0.01;
   double lot = MathFloor(raw / vstep + 1e-9) * vstep;
   if(lot > vmax) lot = MathFloor(vmax / vstep + 1e-9) * vstep;
   return lot;
}

//==================== ★OCP 风险（N1R2 硬化）====================
// ★OrderCalcProfit 是【唯一权威】风险值。
//   失败时【不得】fallback 到独立公式下单 —— 必须 reject + fail-close。
// ★Long 与 Short 分别计算（GPT 指出旧实现用 long 的 Ask→Ask-stop 结果套用到 short）。
bool OcpRiskProfit(bool isLong, double entry, double exitPx, double lot,
                   double &ocpProfit, int &ocpErr)
{
   ocpProfit = 0.0; ocpErr = 0;
   ResetLastError();
   double v = 0.0;
   bool ok = isLong ? OrderCalcProfit(ORDER_TYPE_BUY,  _Symbol, lot, entry, exitPx, v)
                    : OrderCalcProfit(ORDER_TYPE_SELL, _Symbol, lot, entry, exitPx, v);
   if(!ok) ocpErr = GetLastError();
   ocpProfit = v;
   return ok;
}

// 独立合约公式（★仅作诊断，不参与 pass/fail）
double FormulaProfit(bool isLong, double entry, double exitPx, double lot)
{
   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contract <= 0.0) contract = 100000.0;
   double rate = exitPx;
   if(rate <= 0.0) rate = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(rate <= 0.0) rate = 1.0;
   double diff = isLong ? (exitPx - entry) : (entry - exitPx);
   return diff * contract * lot / rate;
}

// ★N1R2：LotForRisk(dir, ...) —— long/short 分别用各自入场价
double LotForRisk(int dir, double stopDist, double &riskBudget,
                  double &actualRisk, int &ocpErrOut)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   riskBudget = 0.0; actualRisk = 0.0; ocpErrOut = 0;
   if(eq <= 0.0 || stopDist <= 0.0) return 0.0;

   riskBudget = eq * InpRiskPct / 100.0;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask <= 0.0 || bid <= 0.0) { SetFatal("无有效报价值"); return 0.0; }

   // ★方向分别取价
   bool   isLong  = (dir > 0);
   double entry   = isLong ? ask : bid;
   double slPx    = isLong ? (entry - stopDist) : (entry + stopDist);

   // 1 手风险（OCP 权威）
   double ocp1 = 0.0; int e1 = 0;
   if(!OcpRiskProfit(isLong, entry, slPx, 1.0, ocp1, e1))
   {
      // ★★ 不得 fallback 到公式
      g_rejOcp++;
      ocpErrOut = e1;
      PrintFormat("[%s] ★OCP FATAL: 1-lot 风险计算失败 err=%d dir=%d → reject + fail-close",
                  InpRunTag, e1, dir);
      SetFatal(StringFormat("OrderCalcProfit 1-lot 失败 err=%d", e1));
      return 0.0;
   }
   double riskPerLot = MathAbs(ocp1);
   if(riskPerLot <= 0.0)
   {
      g_rejOcp++; ocpErrOut = -1;
      SetFatal("OCP 1-lot 风险为 0");
      return 0.0;
   }

   double ideal = riskBudget / riskPerLot;
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lot   = AlignLot(ideal);
   if(lot < vmin)
   {
      if(!InpAllowMinLotOvershoot) return 0.0;
      lot = vmin;
   }

   // 最终手数再算一次 actual risk（OCP 权威）
   double ocpF = 0.0; int eF = 0;
   if(!OcpRiskProfit(isLong, entry, slPx, lot, ocpF, eF))
   {
      g_rejOcp++; ocpErrOut = eF;
      SetFatal(StringFormat("OrderCalcProfit final-lot 失败 err=%d", eF));
      return 0.0;
   }
   actualRisk = MathAbs(ocpF);

   double cap = eq * InpMinLotMaxRiskPct / 100.0;
   if(actualRisk > cap)
   {
      g_riskCapBreach++;
      PrintFormat("[%s] 风险超上限 actual=%.2f cap=%.2f → reject", InpRunTag, actualRisk, cap);
      return 0.0;
   }
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
   if(g_fatal) return false;
   double stopDist = InpSL_ATR * atr;
   if(stopDist <= 0.0) return false;

   double riskBudget = 0.0, actualRisk = 0.0; int ocpErr = 0;
   double lot = LotForRisk(dir, stopDist, riskBudget, actualRisk, ocpErr);
   datetime tNow = TimeCurrent();
   if(lot <= 0.0)
   {
      g_rejRisk++;
      WriteReject(tNow, (ocpErr != 0 ? "ocp_failure" : "risk_reject"), 0.0, 0.0,
                  riskBudget, actualRisk, ocpErr);
      return false;
   }

   bool   isLong = (dir > 0);
   double price  = isLong ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                          : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0) return false;
   double sl = isLong ? (price - stopDist) : (price + stopDist);
   double tp = isLong ? (price + InpTP_RMult * stopDist)
                      : (price - InpTP_RMult * stopDist);

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = _Symbol;
   req.volume    = lot;
   req.type      = isLong ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price     = NormalizeDouble(price, _Digits);
   req.sl        = NormalizeDouble(sl, _Digits);
   req.tp        = NormalizeDouble(tp, _Digits);
   req.deviation = 50;
   req.magic     = InpMagic;
   req.comment   = "open_jsb30";
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

   g_ticket = FindTicket();
   if(g_ticket == 0 || !PositionSelectByTicket(g_ticket))
   {
      PrintFormat("[%s] ★开仓后找不到 position → fail-close", InpRunTag);
      SetFatal("开仓后 position 不可回溯");
      return false;
   }

   g_dir          = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   g_entryPrice   = PositionGetDouble(POSITION_PRICE_OPEN);
   g_initSL       = PositionGetDouble(POSITION_SL);
   g_initTP       = PositionGetDouble(POSITION_TP);
   double realVol = PositionGetDouble(POSITION_VOLUME);
   g_riskBudget   = riskBudget;
   g_actualSLRisk = actualRisk;
   g_entryATR     = atr;
   g_barsHeld     = 0;
   g_entryTimeUtc = (datetime)PositionGetInteger(POSITION_TIME);
   g_dayTraded    = true;

   // ★★N1R2：成交后用真实 POSITION_PRICE_OPEN / POSITION_SL / VOLUME 重算真实初始 SL 风险
   if(g_initSL > 0.0)
   {
      double ocpR = 0.0; int eR = 0;
      if(OcpRiskProfit(g_dir > 0, g_entryPrice, g_initSL, realVol, ocpR, eR))
      {
         g_realSLRisk = MathAbs(ocpR);
         double cap = AccountInfoDouble(ACCOUNT_EQUITY) * InpMinLotMaxRiskPct / 100.0;
         if(g_realSLRisk > cap)
         {
            g_riskCapBreach++;
            PrintFormat("[%s] ★实际成交风险超上限 real=%.2f cap=%.2f (entry=%.5f sl=%.5f vol=%.2f) → run invalid",
                        InpRunTag, g_realSLRisk, cap, g_entryPrice, g_initSL, realVol);
            SetFatal(StringFormat("实际成交 SL 风险 %.2f 超上限 %.2f", g_realSLRisk, cap));
            // 安全平仓（研究回测 fail-close）
            return true;
         }
      }
      else
      {
         SetFatal(StringFormat("成交后 OCP 重算失败 err=%d", eR));
      }
   }

   if(InpVerboseLog)
      PrintFormat("[%s] OPEN dir=%d lot=%.2f entry=%.5f sl=%.5f tp=%.5f planRisk=%.2f realRisk=%.2f",
                  InpRunTag, g_dir, lot, g_entryPrice, g_initSL, g_initTP, actualRisk, g_realSLRisk);
   return true;
}

bool CloseTrade(string reason)
{
   if(!HasPosition()) return false;
   if(g_ticket == 0 || !PositionSelectByTicket(g_ticket)) g_ticket = FindTicket();
   if(g_ticket == 0 || !PositionSelectByTicket(g_ticket)) return false;

   int    dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   double vol = PositionGetDouble(POSITION_VOLUME);

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = _Symbol;
   req.position  = g_ticket;
   req.volume    = vol;
   req.deviation = 50;
   req.magic     = InpMagic;
   req.comment   = "close_" + reason;
   req.type      = (dir > 0) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   ENUM_POSITION_TYPE pt = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   ENUM_ORDER_TYPE_FILLING f;
   PickFilling(f);
   req.type_filling = f;
   req.price = (pt == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
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

//==================== 出场审计（三方对账）====================
void RecordClosingDeal(ulong dealTicket)
{
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;
   long en = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY) return;
   if(g_auditFh == INVALID_HANDLE) { g_auditFailed = true; return; }
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
   int    dir     = (dtype == DEAL_TYPE_SELL) ? 1 : -1;   // 平仓方向 = 持仓方向的对手

   double entryPx = g_entryPrice, entryVol = 0.0;
   datetime entrySrv = g_entryTimeUtc;
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
      SetFatal(StringFormat("deal 字段缺失 ticket=%I64u", dealTicket));
   }

   string closeType = "full";
   if(PositionSelectByTicket(pid) && PositionGetDouble(POSITION_VOLUME) > 0.0)
      closeType = "partial";

   string reason = "expert";
   string cmt = HistoryDealGetString(dealTicket, DEAL_COMMENT);
   long rsn = HistoryDealGetInteger(dealTicket, DEAL_REASON);
   if(StringFind(cmt, "window_end") >= 0)     reason = "window_end";
   else if(StringFind(cmt, "time_exit") >= 0) reason = "time_exit";
   else if(StringFind(cmt, "tp") >= 0)        reason = "tp";
   else if(StringFind(cmt, "sl") >= 0)        reason = "sl";
   else if(rsn == DEAL_REASON_SL)             reason = "sl";
   else if(rsn == DEAL_REASON_TP)             reason = "tp";
   else if(rsn == DEAL_REASON_SO)             reason = "stopout";

   // ★N1R2 三方对账：MT5 DEAL_PROFIT 为基准，OCP 为主判据，公式仅诊断
   bool   isLong = (dir > 0);
   double ocpVal = 0.0; int ocpErr = 0;
   bool   ocpOk  = OcpRiskProfit(isLong, entryPx, price, vol, ocpVal, ocpErr);
   double fmlVal = FormulaProfit(isLong, entryPx, price, vol);
   double ocpDiff = MathAbs(dProfit - ocpVal);
   double fmlDiff = MathAbs(dProfit - fmlVal);
   double fmlPct  = (MathAbs(dProfit) > 0.01) ? (fmlDiff / MathAbs(dProfit) * 100.0) : 0.0;

   if(!ocpOk)
   {
      g_ocpMismatch++;
      g_auditFailed = true;
      SetFatal(StringFormat("closing OCP 失败 ticket=%I64u err=%d", dealTicket, ocpErr));
   }
   else if(ocpDiff > InpOcpTolUsd)
   {
      g_ocpMismatch++;
      g_auditFailed = true;
      PrintFormat("[%s] ★★OCP MISMATCH ticket=%I64u deal_profit=%.4f ocp=%.4f diff=%.4f > %.4f",
                  InpRunTag, dealTicket, dProfit, ocpVal, ocpDiff, InpOcpTolUsd);
      SetFatal(StringFormat("DEAL_PROFIT 与 OCP 差 %.4f 超容差", ocpDiff));
   }
   // 独立公式：仅诊断
   if(fmlPct > InpFormulaTolPct) g_formulaDiagOut++;

   g_lastWriteBytes = FileWrite(g_auditFh, InpRunTag, _Symbol,
             IntegerToString((long)dealTicket),
             IntegerToString((long)pid),
             TimeToString(entrySrv, TIME_DATE|TIME_SECONDS),
             TimeToString(entrySrv, TIME_DATE|TIME_SECONDS),   // ★server==UTC
             TimeToString(tSrv, TIME_DATE|TIME_SECONDS),
             TimeToString(tSrv, TIME_DATE|TIME_SECONDS),
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
             DoubleToString(g_realSLRisk, 2),
             "",
             IntegerToString(ServerUtcOffset()),
             DoubleToString(dProfit, 4),
             DoubleToString(ocpVal, 4),
             DoubleToString(ocpDiff, 4),
             IntegerToString(ocpErr),
             DoubleToString(fmlVal, 4),
             DoubleToString(fmlDiff, 4),
             DoubleToString(fmlPct, 3));
   FileFlush(g_auditFh);

   if(g_lastWriteBytes <= 0)
   {
      g_auditFailed = true;
      PrintFormat("[%s] ★AUDIT FAIL: FileWrite 返回 %u（ticket=%I64u）", InpRunTag, g_lastWriteBytes, dealTicket);
      SetFatal("closing deal 写入失败");
      return;
   }
   MarkDealSeen(dealTicket);
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

//==================== UTC 日与 range 状态机 ====================
datetime UtcDayOf(datetime tUtc)
{
   MqlDateTime s; TimeToStruct(tUtc, s);
   return (datetime)((long)tUtc - (long)s.hour*3600 - (long)s.min*60 - s.sec);
}

int ExpectedRangeBars()
{
   // range 窗口小时数 × 2（每 30 分钟一根）
   return (InpRangeEndUtcHour - InpRangeStartUtcHour) * 2;
}

// ★N1R2：range 必须【完整】才允许冻结
void RangeStateOnNewClosedBar(datetime barServerOpen, double barHigh, double barLow)
{
   datetime btUtc      = ServerToUtc(barServerOpen);
   datetime btUtcClose = (datetime)((long)btUtc + 1800);
   datetime dayUtc     = UtcDayOf(btUtc);
   int expBars         = ExpectedRangeBars();

   if(dayUtc != g_rangeDay)
   {
      g_rangeDay      = dayUtc;
      g_rangeHi       = 0.0;
      g_rangeLo       = 1e18;
      g_rangeCount    = 0;
      g_rangeExpected = expBars;
      g_rangeReady    = false;
      g_rangeFrozenHi = 0.0;
      g_rangeFrozenLo = 0.0;
   }

   datetime wS = (datetime)((long)dayUtc + (long)InpRangeStartUtcHour * 3600);
   datetime wE = (datetime)((long)dayUtc + (long)InpRangeEndUtcHour   * 3600);

   if(!g_rangeReady && btUtc >= wS && btUtcClose <= wE)
   {
      if(barHigh > g_rangeHi) g_rangeHi = barHigh;
      if(barLow  < g_rangeLo) g_rangeLo = barLow;
      g_rangeCount++;
   }

   // ★N1R2：只有 count == expected 才冻结；否则当天不交易
   if(!g_rangeReady && btUtcClose >= wE)
   {
      if(g_rangeCount == expBars && g_rangeHi > g_rangeLo)
      {
         g_rangeFrozenHi = g_rangeHi;
         g_rangeFrozenLo = g_rangeLo;
         g_rangeReady    = true;
      }
      else if(g_rangeCount < expBars)
      {
         g_skipRangeIncomplete++;
      }
   }
}

bool RangeForBreakout(double &hi, double &lo)
{
   if(!g_rangeReady) return false;
   hi = g_rangeFrozenHi; lo = g_rangeFrozenLo;
   return (hi > lo);
}

double ATR(int shift)
{
   double b[]; if(CopyBuffer(g_atrHandle, 0, shift, 1, b) == 1) return b[0];
   return 0.0;
}

//==================== 自检 ====================
bool InferOffsetFromWeekOpen(datetime firstBarServer, int &outOffset, string &why)
{
   // ★N1R2：server==UTC，故"周首 bar 的 server 时间"应落在 UTC 周日 21:00~周一 02:00
   MqlDateTime s; TimeToStruct(firstBarServer, s);
   if(s.day_of_week == 0 || s.day_of_week == 1) { outOffset = 0; why = ""; return true; }
   outOffset = 0; why = StringFormat("周首 bar dow=%d 既非周日也非周一", s.day_of_week);
   return false;
}

void RealWeekRoundTripTest()
{
   if(!InpRunTimeSelfcheck) return;
   int n = iBars(_Symbol, TF());
   if(n <= 0) { PrintFormat("[%s] REALWEEK 无 bar", InpRunTag); return; }
   datetime lastBar = iTime(_Symbol, TF(), 0);
   if(lastBar <= 0) return;

   int checked = 0, ok = 0, fail = 0, skipped = 0, shifted = 0;
   datetime cur = lastBar;
   for(int k = 0; k < 80 && checked < 30; k++)
   {
      datetime wk = WeekKeyUtc(cur);
      // ★N1R2 修正：iBarShift(wk,false) 会返回 <= wk 的最近 bar，
      //   若 wk 之后尚无 bar 就会落到【上一周】→ 误判。
      //   改为从 wk 起向后找第一根 >= wk 的 bar。
      datetime bt = 0;
      for(int j = 0; j < 96; j++)   // 96 × 30min = 48 小时
      {
         datetime t = (datetime)((long)wk + (long)j * 1800);
         int sh = iBarShift(_Symbol, TF(), t, false);
         if(sh < 0 || sh >= n) continue;
         datetime cand = iTime(_Symbol, TF(), sh);
         if(cand < wk) continue;                 // 必须在 wk 之后
         if(cand > (datetime)((long)wk + 48 * 3600)) break;
         bt = cand;
         break;
      }
      if(bt == 0) { skipped++; cur = (datetime)((long)cur - 7 * 86400); continue; }

      MqlDateTime s; TimeToStruct(bt, s);
      // ★N1R2 断言设计（v3，修正过严问题）：
      //   核心不变量 = 「server timestamp 就是 UTC」→ round-trip 必须恒等。
      //   ★该不变量在 offset=0 下【不可能失败】，因此它无法 catching 真问题；
      //     真正的可用性断言是「周首 bar 必须落在该周起始的合理范围内」。
      //   节假日（圣诞/元旦）会让市场延后开市，周首 bar 可能落在周二/周三，
      //   这是【真实市场行为】，不得判为失败。
      bool rt   = (ServerToUtc(bt) == bt) && (UtcToServer(bt) == bt);
      long lagH = (long)bt - (long)wk;                    // 周首 bar 相对周一起点的滞后（秒）
      bool okLag = (lagH >= 0) && (lagH <= 72 * 3600);    // 允许 0~72 小时（含节假日顺延）
      if(okLag && rt) ok++; else fail++;
      if(lagH > 48 * 3600) shifted++;                     // 节假日顺延（仅统计，不判失败）
      if((ok + fail) <= 5)
         PrintFormat("[%s] REALWEEK wk=%s firstBar=%s dow=%d hour=%02d lagH=%.1f rt=%s %s",
                     InpRunTag, TimeToString(wk, TIME_DATE),
                     TimeToString(bt, TIME_DATE|TIME_MINUTES), s.day_of_week, s.hour,
                     (double)lagH / 3600.0, rt ? "OK" : "FAIL",
                     (okLag && rt) ? "OK" : "FAIL");
      checked++;
      cur = (datetime)((long)cur - 7 * 86400);
   }
   PrintFormat("[%s] REALWEEK 汇总：checked=%d OK=%d FAIL=%d skipped=%d holiday_shifted=%d "
               "(server_utc_offset=0)",
               InpRunTag, checked, ok, fail, skipped, shifted);
   if(fail > 0) SetFatal(StringFormat("REALWEEK %d/%d 失败", fail, checked));
   if(checked == 0) SetFatal("REALWEEK 无样本");
}

void RunOffsetSelfTest()
{
   // ★N1R2：UNIT 自测断言"恒等映射 + 周键在周日/周一"
   string labels[3] = {"winter 2023-01-08", "summer 2023-07-09", "dst-trans 2023-03-26"};
   string dstr[3]   = {"2023.01.08 22:00", "2023.07.09 22:00", "2023.03.26 22:00"};
   int okN = 0;
   for(int c = 0; c < 3; c++)
   {
      datetime utcOpen = StringToTime(dstr[c]);
      datetime srv = UtcToServer(utcOpen);
      datetime back = ServerToUtc(srv);
      bool rt = (back == utcOpen) && (srv == utcOpen);
      int off = -1; string why = "";
      bool r = InferOffsetFromWeekOpen(srv, off, why);
      bool okc = rt && r && off == 0;
      if(okc) okN++;
      PrintFormat("[%s] UNIT %-20s utc=%s server=%s back=%s offset=%d %s (%s)",
                  InpRunTag, labels[c], TimeToString(utcOpen, TIME_DATE|TIME_MINUTES),
                  TimeToString(srv, TIME_DATE|TIME_MINUTES),
                  TimeToString(back, TIME_DATE|TIME_MINUTES), off,
                  okc ? "OK" : "FAIL", why);
   }
   PrintFormat("[%s] UNIT 汇总：%d/3 通过（offset 恒为 0）", InpRunTag, okN);
   if(okN < 3) SetFatal("UNIT 自测未全通过");
   RealWeekRoundTripTest();
}

//==================== 生命周期 ====================
void OnInit()
{
   g_sigTF = PERIOD_M30;
   g_atrHandle = iATR(_Symbol, TF(), InpATRPeriod);
   if(g_atrHandle == INVALID_HANDLE) { PrintFormat("[%s] iATR 失败", InpRunTag); SetFatal("iATR 失败"); return; }

   OpenAudit();
   if(g_auditFailed) { PrintFormat("[%s] ★审计初始化失败 → fail-close", InpRunTag); }

   if(InpRunTimeSelfcheck) RunOffsetSelfTest();

   PrintFormat("[%s] init ok range=UTC%02d-%02d(exp %d bars) breakout=UTC%02d-%02d flat=UTC%02d "
               "SL=%.2fxATR TP=%.2fR maxBars=%d risk=%.2f%% cap=%.2f%% "
               "server_utc_offset=%d ocp_tol=%.2f formula_diag_only=%s",
               InpRunTag, InpRangeStartUtcHour, InpRangeEndUtcHour, ExpectedRangeBars(),
               InpBreakoutStartUtcHour, InpBreakoutEndUtcHour, InpHardFlatUtcHour,
               InpSL_ATR, InpTP_RMult, InpMaxBarsInTrade, InpRiskPct, InpMinLotMaxRiskPct,
               ServerUtcOffset(), InpOcpTolUsd, InpFormulaDiagnosticOnly ? "true" : "false");
}

void OnDeinit(const int reason)
{
   CatchUpAudit();

   {
      string sf = AuditDir() + "\\audit_selfcheck.csv";
      int fh = FileOpen(sf, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(fh == INVALID_HANDLE) fh = FileOpen(sf, FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(fh != INVALID_HANDLE)
      {
         FileWrite(fh, "run_tag,written_deals,dup_hits,audit_failed,fatal,fatal_reason,"
                       "ocp_mismatch,formula_diag_out,risk_cap_breach,"
                       "trades,wins,active_positions,"
                       "skip_range_notready,skip_range_incomplete,skip_range_toonarrow,"
                       "skip_nobreak,skip_daytraded,rej_risk,rej_ocp,"
                       "server_utc_offset,reason");
         FileWrite(fh, InpRunTag, IntegerToString(g_writtenDeals), IntegerToString(g_dupHits),
                   g_auditFailed ? "1" : "0",
                   g_fatal ? "1" : "0", g_fatalReason,
                   IntegerToString(g_ocpMismatch), IntegerToString(g_formulaDiagOut),
                   IntegerToString(g_riskCapBreach),
                   IntegerToString(g_nTrades), IntegerToString(g_nWin),
                   IntegerToString(CountMyPositions()),
                   IntegerToString(g_skipRangeNotReady), IntegerToString(g_skipRangeIncomplete),
                   IntegerToString(g_skipRangeTooNarrow),
                   IntegerToString(g_skipNoBreak), IntegerToString(g_skipDayTraded),
                   IntegerToString(g_rejRisk), IntegerToString(g_rejOcp),
                   IntegerToString(ServerUtcOffset()), IntegerToString(reason));
         FileClose(fh);
      }
   }

   if(g_auditFh  != INVALID_HANDLE) { FileClose(g_auditFh);  g_auditFh  = INVALID_HANDLE; }
   if(g_rejectFh != INVALID_HANDLE) { FileClose(g_rejectFh); g_rejectFh = INVALID_HANDLE; }
   if(g_atrHandle!= INVALID_HANDLE) { IndicatorRelease(g_atrHandle); g_atrHandle = INVALID_HANDLE; }

   PrintFormat("[%s] === END reason=%d trades=%d win=%d written=%d dup=%d fatal=%d/%s "
               "ocpMismatch=%d formulaDiag=%d capBreach=%d "
               "rangeNotReady=%d rangeIncomplete=%d narrow=%d noBreak=%d dayTraded=%d "
               "rejRisk=%d rejOcp=%d ===",
               InpRunTag, reason, (int)g_nTrades, (int)g_nWin, (int)g_writtenDeals,
               (int)g_dupHits, g_fatal ? 1 : 0, g_fatalReason,
               (int)g_ocpMismatch, (int)g_formulaDiagOut, (int)g_riskCapBreach,
               (int)g_skipRangeNotReady, (int)g_skipRangeIncomplete,
               (int)g_skipRangeTooNarrow, (int)g_skipNoBreak, (int)g_skipDayTraded,
               (int)g_rejRisk, (int)g_rejOcp);
}

void OnTick()
{
   // ★★N1R2 统一 fail-close gate：fatal 后不再产生新交易
   if(g_fatal)
   {
      if(HasPosition()) CloseTrade("fatal_close");
      return;
   }
   if(g_auditFailed)
   {
      SetFatal("audit_failed 已置位");
      if(HasPosition()) CloseTrade("fatal_close");
      return;
   }

   datetime tUtc = ServerToUtc(TimeCurrent());
   datetime todayUtc = UtcDayOf(tUtc);

   if(todayUtc != g_curUtcDay)
   {
      g_curUtcDay = todayUtc;
      g_dayTraded = false;
   }

   // 每根【已收盘】M30 bar
   datetime closedBarT = iTime(_Symbol, TF(), 1);
   if(closedBarT > 0 && closedBarT != g_lastClosedBar)
   {
      g_lastClosedBar = closedBarT;
      double bh = iHigh(_Symbol, TF(), 1);
      double bl = iLow (_Symbol, TF(), 1);
      RangeStateOnNewClosedBar(closedBarT, bh, bl);
      if(HasPosition())
      {
         g_barsHeld++;
         if(g_barsHeld >= InpMaxBarsInTrade) { CloseTrade("time_exit"); return; }
      }
   }

   MqlDateTime su; TimeToStruct(tUtc, su);
   int utcMin = su.hour * 60 + su.min;

   if(HasPosition())
   {
      if(utcMin >= InpHardFlatUtcHour * 60) { CloseTrade("window_end"); return; }
      return;
   }

   if(utcMin < InpBreakoutStartUtcHour * 60 || utcMin >= InpBreakoutEndUtcHour * 60) return;
   if(g_dayTraded) { g_skipDayTraded++; return; }

   double rHi = 0.0, rLo = 0.0;
   if(!RangeForBreakout(rHi, rLo)) { g_skipRangeNotReady++; return; }

   if(closedBarT <= 0 || closedBarT == g_evalBar) return;
   g_evalBar = closedBarT;

   double atr = ATR(1);
   if(atr <= 0.0) return;
   double rangeW = rHi - rLo;
   if(rangeW < InpMinRangeATRMult * atr) { g_skipRangeTooNarrow++; return; }

   double close1 = iClose(_Symbol, TF(), 1);
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

