//+------------------------------------------------------------------+
//|                                                  dsh_XAMR30.mq5  |
//|  XAMR30 = Cross-Asset Mean Reversion on M30                      |
//|                                                                  |
//|  Source of Truth:                                                |
//|    公共部分/XAMR30_preregistration_final_20260914.md              |
//|                                                                  |
//|  交易 USDJPYm；信息源 XAUUSDm（exact M30 timestamp 匹配）          |
//|  ★server_utc_offset = 0（沿用 JSB30 实测裁定）                     |
//|  ★所有计算只用【已收盘】M30 bar；入场在【下一根 bar 的第一个 tick】  |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property strict

//==================== 输入（★必须与预注册完全一致）====================
//--- 标识
input string InpRunTag                  = "XAMR30";
input long   InpMagic                   = 20260915;

//--- 信号
input int    InpEmaPeriod               = 48;
input int    InpSigmaWindow             = 48;     // 只用 bar t 之前的 48 个 residual
input double InpZThreshold              = 1.5;    // V3 -> 2.0
input int    InpATRPeriod               = 14;
input int    InpATRPercentileWindow     = 500;    // bar t 之前 500 个 ATR
input double InpATRP20Pct               = 20.0;   // nearest-rank
input double InpATRP80Pct               = 80.0;

//--- 跨品种
input string InpInfoSymbol              = "XAUUSDm";
input bool   InpCrossAssetFilter        = true;   // V2 -> false

//--- 出场
input double InpSL_ATR                  = 1.0;
input double InpTP_RMult                = 0.8;
input int    InpMaxBarsInTrade          = 12;

//--- 风险
input double InpRiskPct                 = 1.5;
input double InpMinLotMaxRiskPct        = 3.0;
input bool   InpAllowMinLotOvershoot    = false;
input double InpOcpTolUsd               = 0.05;   // DEAL_PROFIT ↔ OCP 主判据
input double InpFormulaTolPct           = 5.0;    // 仅诊断
input bool   InpFormulaDiagnosticOnly   = true;

//--- 方向（★预注册要求两侧都开放；此处仅作审计冗余，不做事后筛选）
input bool   InpAllowLong               = true;
input bool   InpAllowShort              = true;

//--- 控制
input bool   InpWriteAudit              = true;
input bool   InpWriteRejectAudit        = true;
input bool   InpRunTimeSelfcheck        = true;
input int    InpLatencyMs               = 0;
input int    InpLatencyTicks            = 0;
input bool   InpVerboseLog              = false;
input bool   InpUseGrid                 = false;
input bool   InpUseMartingale           = false;
input bool   InpUseTrailingWin          = false;

//==================== 全局 ====================
ENUM_TIMEFRAMES TF() { return PERIOD_M30; }
int g_atrHandle = INVALID_HANDLE;

bool   g_fatal = false;
string g_fatalReason = "";

void SetFatal(string why)
{
   if(!g_fatal)
   {
      g_fatal = true; g_fatalReason = why;
      PrintFormat("[%s] ★★ FATAL: %s → fail-close", InpRunTag, why);
   }
}

//--- 日与信号
datetime g_curUtcDay   = 0;
bool     g_dayTraded   = false;
datetime g_lastBar     = 0;      // 最近一次已处理的 signal bar（避免重复处理）
datetime g_pendingBar  = 0;      // 已完成信号计算、待下一 bar 入场的 signal bar
bool     g_pending     = false;
int      g_pendDir     = 0;
double   g_pendZ = 0, g_pendEma = 0, g_pendRes = 0, g_pendSig = 0, g_pendAtr = 0;
double   g_pendP20 = 0, g_pendP80 = 0;
datetime g_pendXauT = 0; double g_pendXauO = 0, g_pendXauC = 0, g_pendXauR = 0;
int      g_pendXauPass = 0;

//--- 持仓
ulong  g_ticket = 0;
int    g_dir = 0;
double g_entryPx = 0, g_initSL = 0, g_initTP = 0;
double g_riskBudget = 0, g_actualRisk = 0, g_realRisk = 0;
double g_spreadPtsAtEntry = 0, g_slPts = 0, g_tpPts = 0;
int    g_barsHeld = 0;
double g_sigZ = 0, g_sigEma = 0, g_sigRes = 0, g_sigSigma = 0, g_sigAtr = 0;
double g_sigP20 = 0, g_sigP80 = 0;
datetime g_sigBarTime = 0, g_sigXauT = 0;
double g_sigXauO = 0, g_sigXauC = 0, g_sigXauR = 0;
int    g_sigXauPass = 0, g_sigAlignExact = 0;

//--- 统计
long g_nTrades = 0, g_nWin = 0, g_nLong = 0, g_nShort = 0;
long g_rejSigma = 0, g_rejAtrInsuf = 0, g_rejAtrRegime = 0;
long g_rejXauMissing = 0, g_rejXauFail = 0, g_rejMinLot = 0, g_rejRiskCap = 0, g_rejOcp = 0;
long g_skipNoSignal = 0, g_skipDayTraded = 0, g_skipHasPos = 0;

//--- 审计
int  g_auditFh = INVALID_HANDLE, g_rejectFh = INVALID_HANDLE;
long g_writtenDeals = 0, g_dupHits = 0, g_ocpMismatch = 0, g_formulaDiagOut = 0;
long g_riskCapBreach = 0;
uint g_lastWriteBytes = 0;
bool g_auditFailed = false;

#define MAX_DEALTICKET 8192
ulong g_seen[MAX_DEALTICKET]; int g_seenCount = 0;

//==================== 审计表头 ====================
string AuditDir() { return "dshtrend\\" + InpRunTag; }

const string AUDIT_HEADER =
   "run_tag,symbol,deal_ticket,position_id,"
   "signal_bar_time,entry_time,exit_time,"
   "z_score,ema48,residual,sigma48,"
   "atr14,atr_p20,atr_p80,"
   "xau_bar_time,xau_open,xau_close,xau_return,"
   "cross_asset_filter_enabled,cross_asset_filter_pass,alignment_exact,"
   "trade_direction,"
   "spread_at_entry_points,initial_sl_distance_points,initial_tp_distance_points,"
   "spread_over_sl,spread_over_tp,"
   "risk_budget,actual_initial_sl_risk,"
   "ocp_expected_pl,deal_profit,formula_value,formula_diff,"
   "close_type,exit_reason,server_utc_offset";

const string REJECT_HEADER =
   "run_tag,symbol,utc_day,signal_bar_time,reason,"
   "z_score,atr14,atr_p20,atr_p80,xau_bar_time,xau_return,"
   "raw_lot,final_lot,risk_budget,actual_risk,ocp_err";

bool HeaderUnique(const string h, const string which)
{
   string p[]; int n = StringSplit(h, ',', p);
   for(int i = 0; i < n; i++)
      for(int j = i + 1; j < n; j++)
         if(p[i] == p[j])
         { PrintFormat("[%s] ★HEADER FAIL: %s 重复列 '%s'", InpRunTag, which, p[i]); return false; }
   return true;
}

bool IsDealSeen(ulong t) { for(int i = 0; i < g_seenCount; i++) if(g_seen[i] == t) return true; return false; }
void MarkDealSeen(ulong t)
{
   if(g_seenCount < MAX_DEALTICKET) g_seen[g_seenCount++] = t;
   else SetFatal("seen 表溢出");
}

double SpreadPoints()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double pt  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(ask <= 0 || bid <= 0 || pt <= 0) return 0.0;
   return (ask - bid) / pt;
}

void WriteReject(datetime tSrv, string reason,
                 double rawLot, double finalLot, double riskBudget, double actualRisk, int ocpErr)
{
   if(!InpWriteRejectAudit || g_rejectFh == INVALID_HANDLE) return;
   g_lastWriteBytes = FileWrite(g_rejectFh, InpRunTag, _Symbol,
             TimeToString(g_curUtcDay, TIME_DATE),
             TimeToString(tSrv, TIME_DATE|TIME_SECONDS), reason,
             DoubleToString(g_pendZ, 5), DoubleToString(g_pendAtr, _Digits),
             DoubleToString(g_pendP20, _Digits), DoubleToString(g_pendP80, _Digits),
             (g_pendXauT > 0) ? TimeToString(g_pendXauT, TIME_DATE|TIME_MINUTES) : "",
             DoubleToString(g_pendXauR, 6),
             DoubleToString(rawLot, 4), DoubleToString(finalLot, 2),
             DoubleToString(riskBudget, 2), DoubleToString(actualRisk, 2),
             IntegerToString(ocpErr));
   if(g_lastWriteBytes <= 0)
   { g_auditFailed = true; PrintFormat("[%s] ★AUDIT FAIL: reject FileWrite=%u", InpRunTag, g_lastWriteBytes); SetFatal("reject 写入失败"); }
   FileFlush(g_rejectFh);
}

void OpenAudit()
{
   if(!InpWriteAudit) return;
   if(!HeaderUnique(AUDIT_HEADER, "trades"))  { g_auditFailed = true; SetFatal("trades header 重复列"); return; }
   if(!HeaderUnique(REJECT_HEADER, "reject")) { g_auditFailed = true; SetFatal("reject header 重复列"); return; }

   string fn = AuditDir() + "\\trades.csv";
   bool ex = FileIsExist(fn, FILE_COMMON);
   g_auditFh = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(g_auditFh == INVALID_HANDLE)
   {
      g_auditFh = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
      if(g_auditFh == INVALID_HANDLE) { g_auditFailed = true; SetFatal("trades.csv 打不开"); return; }
   }
   FileSeek(g_auditFh, 0, SEEK_END);
   if(!ex)
   {
      g_lastWriteBytes = FileWrite(g_auditFh, AUDIT_HEADER);
      if(g_lastWriteBytes <= 0) { g_auditFailed = true; SetFatal("trades header 写入失败"); return; }
   }

   string rf = AuditDir() + "\\reject_audit.csv";
   bool rex = FileIsExist(rf, FILE_COMMON);
   g_rejectFh = FileOpen(rf, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(g_rejectFh == INVALID_HANDLE) g_rejectFh = FileOpen(rf, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI, ',');
   if(g_rejectFh != INVALID_HANDLE)
   {
      FileSeek(g_rejectFh, 0, SEEK_END);
      if(!rex)
      {
         g_lastWriteBytes = FileWrite(g_rejectFh, REJECT_HEADER);
         if(g_lastWriteBytes <= 0) { g_auditFailed = true; SetFatal("reject header 写入失败"); }
      }
   }
}

//==================== 信号计算 ====================
// ★EMA48：可用截至 bar t 收盘的历史（含 bar t）
double EmaAt(int shift)
{
   int need = InpEmaPeriod + shift + 1;
   int have = iBars(_Symbol, TF());
   if(have < need) return 0.0;
   double k = 2.0 / (InpEmaPeriod + 1.0);
   // 以最早一根收盘价为种子，向前递推到 shift
   int start = need - 1;                    // 最老的 shift
   double ema = iClose(_Symbol, TF(), start);
   for(int i = start - 1; i >= shift; i--)
      ema = iClose(_Symbol, TF(), i) * k + ema * (1.0 - k);
   return ema;
}

// ★sigma：只用 bar t 之前的 InpSigmaWindow 个已收盘 residual（不含 t）
bool SigmaBeforeT(int tShift, double &outSigma)
{
   outSigma = 0.0;
   int bars = iBars(_Symbol, TF());
   if(bars < tShift + InpSigmaWindow + InpEmaPeriod + 2) return false;
   double e[]; ArrayResize(e, InpSigmaWindow);
   for(int k = 0; k < InpSigmaWindow; k++)
   {
      int sh = tShift + 1 + k;               // t-1, t-2, ..., t-48
      double em = EmaAt(sh);
      if(em <= 0.0) return false;
      e[k] = iClose(_Symbol, TF(), sh) - em;
   }
   double m = 0.0; for(int k = 0; k < InpSigmaWindow; k++) m += e[k];
   m /= InpSigmaWindow;
   double v = 0.0; for(int k = 0; k < InpSigmaWindow; k++) v += (e[k]-m)*(e[k]-m);
   v /= (InpSigmaWindow - 1);                 // sample std
   if(v <= 0.0) return false;
   outSigma = MathSqrt(v);
   return true;
}

// ★ATR percentile：只用 bar t 之前的 InpATRPercentileWindow 个 ATR（不含 t）
//   nearest-rank percentile
bool AtrPercentile(int tShift, double &p20, double &p80)
{
   int need = tShift + 1 + InpATRPercentileWindow;
   if(iBars(_Symbol, TF()) < need) return false;
   double a[]; ArrayResize(a, InpATRPercentileWindow);
   for(int k = 0; k < InpATRPercentileWindow; k++)
   {
      double b[];
      if(CopyBuffer(g_atrHandle, 0, tShift + 1 + k, 1, b) != 1) return false;
      a[k] = b[0];
   }
   ArraySort(a);
   int n = InpATRPercentileWindow;
   int r20 = (int)MathCeil(InpATRP20Pct / 100.0 * n); if(r20 < 1) r20 = 1;
   int r80 = (int)MathCeil(InpATRP80Pct / 100.0 * n); if(r80 > n) r80 = n;
   p20 = a[r20 - 1];
   p80 = a[r80 - 1];
   return (p80 > 0.0);
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

//==================== OCP（权威）====================
bool OcpProfit(bool isLong, double entry, double exitPx, double lot, double &v, int &err)
{
   v = 0.0; err = 0; ResetLastError();
   double r = 0.0;
   bool ok = isLong ? OrderCalcProfit(ORDER_TYPE_BUY,  _Symbol, lot, entry, exitPx, r)
                    : OrderCalcProfit(ORDER_TYPE_SELL, _Symbol, lot, entry, exitPx, r);
   if(!ok) err = GetLastError();
   v = r; return ok;
}
double FormulaProfit(bool isLong, double entry, double exitPx, double lot)
{
   double c = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(c <= 0) c = 100000.0;
   double rate = (exitPx > 0) ? exitPx : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(rate <= 0) rate = 1.0;
   double d = isLong ? (exitPx - entry) : (entry - exitPx);
   return d * c * lot / rate;
}
bool OcpAgrees(double a, double b)
{
   double diff = MathAbs(a - b);
   double lim = MathMax(InpOcpTolUsd, 0.0);
   if(diff <= lim) return true;
   PrintFormat("[%s] ★OCP MISMATCH a=%.4f b=%.4f diff=%.4f > %.4f", InpRunTag, a, b, diff, lim);
   return false;
}

// ★LotForRisk(dir,...)：long/short 分别取价；OCP 失败不得 fallback
double LotForRisk(int dir, double stopDist, double &riskBudget, double &actualRisk, int &ocpErrOut)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   riskBudget = 0.0; actualRisk = 0.0; ocpErrOut = 0;
   if(eq <= 0 || stopDist <= 0) return 0.0;
   riskBudget = eq * InpRiskPct / 100.0;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(ask <= 0 || bid <= 0) { SetFatal("无有效报价"); return 0.0; }
   bool isLong = (dir > 0);
   double entry = isLong ? ask : bid;
   double sl    = isLong ? (entry - stopDist) : (entry + stopDist);

   double o1 = 0.0; int e1 = 0;
   if(!OcpProfit(isLong, entry, sl, 1.0, o1, e1))
   { g_rejOcp++; ocpErrOut = e1; SetFatal(StringFormat("OCP 1-lot 失败 err=%d", e1)); return 0.0; }
   double rpl = MathAbs(o1);
   if(rpl <= 0) { g_rejOcp++; SetFatal("OCP 1-lot 风险为 0"); return 0.0; }

   double ideal = riskBudget / rpl;
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lot = AlignLot(ideal);
   if(lot < vmin)
   {
      g_rejMinLot++;
      ocpErrOut = -2;
      return 0.0;                      // ★InpAllowMinLotOvershoot=false → min_lot_risk_reject
   }

   double oF = 0.0; int eF = 0;
   if(!OcpProfit(isLong, entry, sl, lot, oF, eF))
   { g_rejOcp++; ocpErrOut = eF; SetFatal(StringFormat("OCP final-lot 失败 err=%d", eF)); return 0.0; }
   actualRisk = MathAbs(oF);

   double cap = eq * InpMinLotMaxRiskPct / 100.0;
   if(actualRisk > cap) { g_rejRiskCap++; ocpErrOut = -3; return 0.0; }
   return lot;
}

//==================== 交易 ====================
bool PickFilling(ENUM_ORDER_TYPE_FILLING &f)
{
   long m = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((m & SYMBOL_FILLING_FOK) != 0) { f = ORDER_FILLING_FOK; return true; }
   if((m & SYMBOL_FILLING_IOC) != 0) { f = ORDER_FILLING_IOC; return true; }
   f = ORDER_FILLING_RETURN; return true;
}

bool OpenTrade(int dir, double atr)
{
   if(g_fatal) return false;
   double stopDist = InpSL_ATR * atr;
   if(stopDist <= 0) return false;

   double rb = 0, ar = 0; int oerr = 0;
   double lot = LotForRisk(dir, stopDist, rb, ar, oerr);
   datetime now = TimeCurrent();
   if(lot <= 0)
   {
      string rs = (oerr == -2) ? "min_lot_risk_reject"
                : (oerr == -3) ? "risk_cap_reject"
                : (oerr != 0)  ? "ocp_failure" : "risk_reject";
      WriteReject(now, rs, 0, 0, rb, ar, oerr);
      return false;
   }

   bool isLong = (dir > 0);
   double price = isLong ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0) return false;
   double sl = isLong ? (price - stopDist) : (price + stopDist);
   double tp = isLong ? (price + InpTP_RMult * stopDist) : (price - InpTP_RMult * stopDist);

   double pt = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double sprdPts = SpreadPoints();
   double slPts = (pt > 0) ? stopDist / pt : 0.0;
   double tpPts = (pt > 0) ? (InpTP_RMult * stopDist) / pt : 0.0;

   MqlTradeRequest rq; MqlTradeResult rs2;
   ZeroMemory(rq); ZeroMemory(rs2);
   rq.action = TRADE_ACTION_DEAL; rq.symbol = _Symbol; rq.volume = lot;
   rq.type = isLong ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   rq.price = NormalizeDouble(price, _Digits);
   rq.sl = NormalizeDouble(sl, _Digits);
   rq.tp = NormalizeDouble(tp, _Digits);
   rq.deviation = 50; rq.magic = InpMagic; rq.comment = "open_xamr30";
   ENUM_ORDER_TYPE_FILLING f; PickFilling(f); rq.type_filling = f;

   if(!OrderSend(rq, rs2) || (rs2.retcode != TRADE_RETCODE_DONE && rs2.retcode != TRADE_RETCODE_PLACED))
   {
      if(InpVerboseLog) PrintFormat("[%s] open fail ret=%d err=%d", InpRunTag, rs2.retcode, GetLastError());
      return false;
   }

   g_ticket = FindTicket();
   if(g_ticket == 0 || !PositionSelectByTicket(g_ticket))
   { SetFatal("开仓后 position 不可回溯"); return false; }

   g_dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   g_entryPx = PositionGetDouble(POSITION_PRICE_OPEN);
   g_initSL  = PositionGetDouble(POSITION_SL);
   g_initTP  = PositionGetDouble(POSITION_TP);
   double rvol = PositionGetDouble(POSITION_VOLUME);
   g_riskBudget = rb; g_actualRisk = ar;
   g_spreadPtsAtEntry = sprdPts; g_slPts = slPts; g_tpPts = tpPts;
   g_barsHeld = 0;
   g_sigBarTime = g_pendingBar;
   g_sigZ = g_pendZ; g_sigEma = g_pendEma; g_sigRes = g_pendRes; g_sigSigma = g_pendSig;
   g_sigAtr = g_pendAtr; g_sigP20 = g_pendP20; g_sigP80 = g_pendP80;
   g_sigXauT = g_pendXauT; g_sigXauO = g_pendXauO; g_sigXauC = g_pendXauC; g_sigXauR = g_pendXauR;
   g_sigXauPass = g_pendXauPass; g_sigAlignExact = 1;
   g_dayTraded = true;
   g_pending = false;

   // ★成交后用真实 POSITION 字段重算真实初始 SL 风险
   if(g_initSL > 0)
   {
      double oR = 0; int eR = 0;
      if(OcpProfit(g_dir > 0, g_entryPx, g_initSL, rvol, oR, eR))
      {
         g_realRisk = MathAbs(oR);
         double cap = AccountInfoDouble(ACCOUNT_EQUITY) * InpMinLotMaxRiskPct / 100.0;
         if(g_realRisk > cap)
         {
            g_riskCapBreach++;
            PrintFormat("[%s] ★实际成交风险超上限 real=%.2f cap=%.2f → invalid", InpRunTag, g_realRisk, cap);
            SetFatal(StringFormat("实际成交 SL 风险 %.2f 超上限 %.2f", g_realRisk, cap));
            return true;
         }
      }
      else SetFatal(StringFormat("成交后 OCP 重算失败 err=%d", eR));
   }

   if(g_dir > 0) g_nLong++; else g_nShort++;
   if(InpVerboseLog)
      PrintFormat("[%s] OPEN dir=%d lot=%.2f entry=%.5f sl=%.5f tp=%.5f spreadPts=%.1f slPts=%.1f tpPts=%.1f risk=%.2f",
                  InpRunTag, g_dir, lot, g_entryPx, g_initSL, g_initTP, sprdPts, slPts, tpPts, ar);
   return true;
}

bool CloseTrade(string reason)
{
   if(!HasPosition()) return false;
   if(g_ticket == 0 || !PositionSelectByTicket(g_ticket)) g_ticket = FindTicket();
   if(g_ticket == 0 || !PositionSelectByTicket(g_ticket)) return false;
   ENUM_POSITION_TYPE pt = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double vol = PositionGetDouble(POSITION_VOLUME);
   MqlTradeRequest rq; MqlTradeResult rs;
   ZeroMemory(rq); ZeroMemory(rs);
   rq.action = TRADE_ACTION_DEAL; rq.symbol = _Symbol; rq.position = g_ticket;
   rq.volume = vol; rq.deviation = 50; rq.magic = InpMagic;
   rq.comment = "close_" + reason;
   rq.type = (pt == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   ENUM_ORDER_TYPE_FILLING f; PickFilling(f); rq.type_filling = f;
   rq.price = (pt == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                        : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(!OrderSend(rq, rs) || (rs.retcode != TRADE_RETCODE_DONE && rs.retcode != TRADE_RETCODE_PLACED))
      return false;
   g_ticket = 0;
   return true;
}

//==================== 出场审计 ====================
void RecordClosingDeal(ulong dk)
{
   if(!HistoryDealSelect(dk)) return;
   if(HistoryDealGetString(dk, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dk, DEAL_MAGIC) != InpMagic) return;
   long en = HistoryDealGetInteger(dk, DEAL_ENTRY);
   if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY) return;
   if(g_auditFh == INVALID_HANDLE) { g_auditFailed = true; return; }
   if(IsDealSeen(dk)) { g_dupHits++; return; }

   double dp = HistoryDealGetDouble(dk, DEAL_PROFIT);
   double ds = HistoryDealGetDouble(dk, DEAL_SWAP);
   double dc = HistoryDealGetDouble(dk, DEAL_COMMISSION);
   double net = dp + ds + dc;
   double px = HistoryDealGetDouble(dk, DEAL_PRICE);
   double vol = HistoryDealGetDouble(dk, DEAL_VOLUME);
   ulong pid = (ulong)HistoryDealGetInteger(dk, DEAL_POSITION_ID);
   datetime tS = (datetime)HistoryDealGetInteger(dk, DEAL_TIME);
   long dt = HistoryDealGetInteger(dk, DEAL_TYPE);
   int dir = (dt == DEAL_TYPE_SELL) ? 1 : -1;

   double entryPx = g_entryPx; datetime entryT = g_sigBarTime;
   if(HistorySelectByPosition(pid))
   {
      int nd = HistoryDealsTotal(); double sp = 0, sv = 0; datetime et = 0;
      for(int i = 0; i < nd; i++)
      {
         ulong tk = HistoryDealGetTicket(i); if(tk == 0) continue;
         if(HistoryDealGetInteger(tk, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
         double p = HistoryDealGetDouble(tk, DEAL_PRICE), v = HistoryDealGetDouble(tk, DEAL_VOLUME);
         sp += p * v; sv += v;
         datetime tt = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
         if(et == 0 || tt < et) et = tt;
      }
      if(sv > 0) entryPx = sp / sv;
      if(et > 0) entryT = et;
   }
   if(entryPx <= 0 || px <= 0 || vol <= 0 || pid == 0)
   { g_auditFailed = true; SetFatal(StringFormat("deal 字段缺失 tk=%I64u", dk)); }

   string closeType = "full";
   if(PositionSelectByTicket(pid) && PositionGetDouble(POSITION_VOLUME) > 0) closeType = "partial";

   string reason = "expert";
   string cmt = HistoryDealGetString(dk, DEAL_COMMENT);
   long rsn = HistoryDealGetInteger(dk, DEAL_REASON);
   if(StringFind(cmt, "window_end") >= 0)     reason = "window_end";
   else if(StringFind(cmt, "time_exit") >= 0) reason = "time_exit";
   else if(StringFind(cmt, "tp") >= 0)        reason = "tp";
   else if(StringFind(cmt, "sl") >= 0)        reason = "sl";
   else if(rsn == DEAL_REASON_SL)             reason = "sl";
   else if(rsn == DEAL_REASON_TP)             reason = "tp";
   else if(rsn == DEAL_REASON_SO)             reason = "stopout";

   bool isLong = (dir > 0);
   double ocpV = 0; int ocpE = 0;
   bool ocpOk = OcpProfit(isLong, entryPx, px, vol, ocpV, ocpE);
   double fV = FormulaProfit(isLong, entryPx, px, vol);
   double ocpDiff = MathAbs(dp - ocpV);
   double fDiff = MathAbs(dp - fV);

   if(!ocpOk) { g_ocpMismatch++; g_auditFailed = true; SetFatal(StringFormat("closing OCP 失败 err=%d", ocpE)); }
   else if(ocpDiff > InpOcpTolUsd)
   {
      g_ocpMismatch++; g_auditFailed = true;
      PrintFormat("[%s] ★★OCP MISMATCH tk=%I64u deal=%.4f ocp=%.4f diff=%.4f", InpRunTag, dk, dp, ocpV, ocpDiff);
      SetFatal(StringFormat("DEAL_PROFIT 与 OCP 差 %.4f 超容差", ocpDiff));
   }

   g_lastWriteBytes = FileWrite(g_auditFh, InpRunTag, _Symbol,
             IntegerToString((long)dk), IntegerToString((long)pid),
             TimeToString(g_sigBarTime, TIME_DATE|TIME_SECONDS),
             TimeToString(entryT, TIME_DATE|TIME_SECONDS),
             TimeToString(tS, TIME_DATE|TIME_SECONDS),
             DoubleToString(g_sigZ, 5), DoubleToString(g_sigEma, _Digits),
             DoubleToString(g_sigRes, _Digits), DoubleToString(g_sigSigma, _Digits),
             DoubleToString(g_sigAtr, _Digits), DoubleToString(g_sigP20, _Digits),
             DoubleToString(g_sigP80, _Digits),
             (g_sigXauT > 0) ? TimeToString(g_sigXauT, TIME_DATE|TIME_MINUTES) : "",
             DoubleToString(g_sigXauO, _Digits), DoubleToString(g_sigXauC, _Digits),
             DoubleToString(g_sigXauR, 6),
             InpCrossAssetFilter ? "1" : "0",
             IntegerToString(g_sigXauPass), IntegerToString(g_sigAlignExact),
             (dir > 0) ? "long" : "short",
             DoubleToString(g_spreadPtsAtEntry, 1),
             DoubleToString(g_slPts, 1), DoubleToString(g_tpPts, 1),
             (g_slPts > 0) ? DoubleToString(g_spreadPtsAtEntry / g_slPts, 5) : "",
             (g_tpPts > 0) ? DoubleToString(g_spreadPtsAtEntry / g_tpPts, 5) : "",
             DoubleToString(g_riskBudget, 2), DoubleToString(g_actualRisk, 2),
             DoubleToString(ocpV, 4), DoubleToString(dp, 4),
             DoubleToString(fV, 4), DoubleToString(fDiff, 4),
             closeType, reason, "0");
   FileFlush(g_auditFh);

   if(g_lastWriteBytes <= 0)
   { g_auditFailed = true; SetFatal("closing 写入失败"); return; }
   MarkDealSeen(dk); g_writtenDeals++;
   g_nTrades++; if(net > 0) g_nWin++;

   // 重置信号快照，避免下一笔误用
   g_sigZ = 0; g_sigEma = 0; g_sigRes = 0; g_sigSigma = 0;
   g_sigXauT = 0; g_sigXauR = 0;
}

void OnTradeTransaction(const MqlTradeTransaction &t, const MqlTradeRequest &r, const MqlTradeResult &s)
{
   if(t.type == TRADE_TRANSACTION_DEAL_ADD) RecordClosingDeal(t.deal);
}

void CatchUpAudit()
{
   if(!InpWriteAudit) return;
   if(!HistorySelect(0, TimeCurrent() + 7 * 86400)) return;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong tk = HistoryDealGetTicket(i); if(tk == 0) continue;
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != InpMagic) continue;
      long en = HistoryDealGetInteger(tk, DEAL_ENTRY);
      if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY) continue;
      RecordClosingDeal(tk);
   }
}

//==================== 信号评估 ====================
// 返回 true 表示产生了待入场信号
bool EvaluateSignalBar(int tShift)
{
   // 1) z-score
   double emaT = EmaAt(tShift);
   if(emaT <= 0) { g_rejSigma++; WriteReject(iTime(_Symbol, TF(), tShift), "sigma_invalid", 0,0,0,0,0); return false; }
   double eT = iClose(_Symbol, TF(), tShift) - emaT;
   double sigT = 0;
   if(!SigmaBeforeT(tShift, sigT)) { g_rejSigma++; WriteReject(iTime(_Symbol, TF(), tShift), "sigma_invalid",0,0,0,0,0); return false; }
   double zT = eT / sigT;

   g_pendZ = zT; g_pendEma = emaT; g_pendRes = eT; g_pendSig = sigT;

   if(MathAbs(zT) < InpZThreshold) { g_skipNoSignal++; return false; }

   // 2) ATR 与 regime
   double a[];
   if(CopyBuffer(g_atrHandle, 0, tShift, 1, a) != 1)
   { g_rejAtrInsuf++; WriteReject(iTime(_Symbol, TF(), tShift), "atr_insufficient",0,0,0,0,0); return false; }
   double atrT = a[0];
   g_pendAtr = atrT;
   double p20 = 0, p80 = 0;
   if(!AtrPercentile(tShift, p20, p80) || atrT <= 0)
   { g_rejAtrInsuf++; WriteReject(iTime(_Symbol, TF(), tShift), "atr_insufficient",0,0,0,0,0); return false; }
   g_pendP20 = p20; g_pendP80 = p80;
   if(atrT < p20 || atrT > p80)
   { g_rejAtrRegime++; WriteReject(iTime(_Symbol, TF(), tShift), "atr_out_of_regime",0,0,0,0,0); return false; }

   // 3) 跨品种 exact timestamp
   datetime jt = iTime(_Symbol, TF(), tShift);
   int sx = iBarShift(InpInfoSymbol, PERIOD_M30, jt, false);
   int xbars = iBars(InpInfoSymbol, PERIOD_M30);
   bool exact = false; datetime xt = 0; double xo = 0, xc = 0;
   if(sx >= 0 && sx < xbars)
   {
      xt = iTime(InpInfoSymbol, PERIOD_M30, sx);
      if(xt == jt) { exact = true; xo = iOpen(InpInfoSymbol, PERIOD_M30, sx); xc = iClose(InpInfoSymbol, PERIOD_M30, sx); }
   }
   g_pendXauT = xt; g_pendXauO = xo; g_pendXauC = xc;
   double xr = (exact && xo > 0) ? (xc / xo - 1.0) : 0.0;
   g_pendXauR = xr;

   if(!exact)
   { g_rejXauMissing++; WriteReject(jt, "cross_asset_missing_bar",0,0,0,0,0); return false; }

   // 4) 方向
   int dir = (zT > 0) ? -1 : 1;           // trade_direction = -sign(z)
   if(dir > 0 && !InpAllowLong)  { g_skipNoSignal++; return false; }
   if(dir < 0 && !InpAllowShort) { g_skipNoSignal++; return false; }

   // 5) cross-asset filter
   int pass = 1;
   if(InpCrossAssetFilter)
   {
      bool ok = (xr != 0.0) && ((xr > 0 && zT > 0) || (xr < 0 && zT < 0));
      pass = ok ? 1 : 0;
      g_pendXauPass = pass;
      if(!ok) { g_rejXauFail++; WriteReject(jt, "cross_asset_filter_fail",0,0,0,0,0); return false; }
   }
   else g_pendXauPass = 0;

   g_pendDir = dir;
   g_pendingBar = jt;
   g_pending = true;
   return true;
}

//==================== 生命周期 ====================
void OnInit()
{
   g_atrHandle = iATR(_Symbol, TF(), InpATRPeriod);
   if(g_atrHandle == INVALID_HANDLE) { SetFatal("iATR 失败"); return; }
   OpenAudit();
   if(g_auditFailed) PrintFormat("[%s] ★审计初始化失败 → fail-close", InpRunTag);

   if(InpRunTimeSelfcheck)
   {
      // UNIT：断言 server==UTC 与关键常量
      int okN = 0;
      if(TimeCurrent() - TimeGMT() == 0) okN++;
      if(InpSL_ATR == 1.0 && InpTP_RMult == 0.8 && InpMaxBarsInTrade == 12) okN++;
      if(InpEmaPeriod == 48 && InpSigmaWindow == 48 && InpATRPercentileWindow == 500) okN++;
      PrintFormat("[%s] UNIT %d/3 通过（server==UTC / SL-TP-hold / 窗口参数）", InpRunTag, okN);
      if(okN < 3) SetFatal("UNIT 自检未全通过");
   }

   PrintFormat("[%s] init ok z=%.2f crossAsset=%s sym=%s EMA=%d sigWin=%d ATR=%d pctWin=%d "
               "SL=%.2fxATR TP=%.2fR hold=%d risk=%.2f%% cap=%.2f%% span=%s~%s",
               InpRunTag, InpZThreshold, InpCrossAssetFilter ? "ON" : "OFF", InpInfoSymbol,
               InpEmaPeriod, InpSigmaWindow, InpATRPeriod, InpATRPercentileWindow,
               InpSL_ATR, InpTP_RMult, InpMaxBarsInTrade, InpRiskPct, InpMinLotMaxRiskPct,
               TimeToString(iTime(_Symbol, TF(), iBars(_Symbol, TF())-1), TIME_DATE),
               TimeToString(iTime(_Symbol, TF(), 0), TIME_DATE));
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
                       "trades,wins,long,short,active_positions,"
                       "rej_sigma,rej_atr_insufficient,rej_atr_regime,"
                       "rej_xau_missing,rej_xau_fail,rej_minlot,rej_riskcap,rej_ocp,"
                       "skip_no_signal,skip_day_traded,server_utc_offset,reason");
         FileWrite(fh, InpRunTag, IntegerToString(g_writtenDeals), IntegerToString(g_dupHits),
                   g_auditFailed ? "1":"0", g_fatal ? "1":"0", g_fatalReason,
                   IntegerToString(g_ocpMismatch), IntegerToString(g_formulaDiagOut),
                   IntegerToString(g_riskCapBreach),
                   IntegerToString(g_nTrades), IntegerToString(g_nWin),
                   IntegerToString(g_nLong), IntegerToString(g_nShort),
                   IntegerToString(CountMyPositions()),
                   IntegerToString(g_rejSigma), IntegerToString(g_rejAtrInsuf),
                   IntegerToString(g_rejAtrRegime), IntegerToString(g_rejXauMissing),
                   IntegerToString(g_rejXauFail), IntegerToString(g_rejMinLot),
                   IntegerToString(g_rejRiskCap), IntegerToString(g_rejOcp),
                   IntegerToString(g_skipNoSignal), IntegerToString(g_skipDayTraded),
                   IntegerToString((int)((long)TimeCurrent() - (long)TimeGMT())),
                   IntegerToString(reason));
         FileClose(fh);
      }
   }
   if(g_auditFh != INVALID_HANDLE) { FileClose(g_auditFh); g_auditFh = INVALID_HANDLE; }
   if(g_rejectFh != INVALID_HANDLE) { FileClose(g_rejectFh); g_rejectFh = INVALID_HANDLE; }
   if(g_atrHandle != INVALID_HANDLE) { IndicatorRelease(g_atrHandle); g_atrHandle = INVALID_HANDLE; }

   PrintFormat("[%s] === END reason=%d trades=%d win=%d L=%d S=%d written=%d dup=%d "
               "fatal=%d/%s ocpMismatch=%d capBreach=%d "
               "rejSig=%d rejAtrIns=%d rejRegime=%d rejXauMiss=%d rejXauFail=%d "
               "rejMinLot=%d rejRiskCap=%d rejOcp=%d skipNoSig=%d skipDay=%d ===",
               InpRunTag, reason, (int)g_nTrades, (int)g_nWin, (int)g_nLong, (int)g_nShort,
               (int)g_writtenDeals, (int)g_dupHits, g_fatal?1:0, g_fatalReason,
               (int)g_ocpMismatch, (int)g_riskCapBreach,
               (int)g_rejSigma, (int)g_rejAtrInsuf, (int)g_rejAtrRegime,
               (int)g_rejXauMissing, (int)g_rejXauFail, (int)g_rejMinLot,
               (int)g_rejRiskCap, (int)g_rejOcp, (int)g_skipNoSignal, (int)g_skipDayTraded);
}

void OnTick()
{
   if(g_fatal) { if(HasPosition()) CloseTrade("fatal_close"); return; }
   if(g_auditFailed) { SetFatal("audit_failed 已置位"); if(HasPosition()) CloseTrade("fatal_close"); return; }

   datetime tNow = TimeCurrent();
   datetime todayUtc = (datetime)((long)tNow - (long)((tNow / 86400) * 86400));
   MqlDateTime s; TimeToStruct(tNow, s);
   todayUtc = (datetime)((long)tNow - (long)s.hour*3600 - (long)s.min*60 - s.sec);

   if(todayUtc != g_curUtcDay) { g_curUtcDay = todayUtc; g_dayTraded = false; }

   // ---- 持仓管理 ----
   if(HasPosition())
   {
      // 最长持仓：12 根完整 M30
      static datetime lastCnt = 0;
      datetime cb = iTime(_Symbol, TF(), 1);
      if(cb > 0 && cb != lastCnt)
      {
         lastCnt = cb; g_barsHeld++;
         if(g_barsHeld >= InpMaxBarsInTrade) { CloseTrade("time_exit"); return; }
      }
      return;
   }

   // ---- 新收盘 bar：评估信号 ----
   datetime closedBar = iTime(_Symbol, TF(), 1);
   if(closedBar <= 0 || closedBar == g_lastBar) return;

   // ★待入场：上一根 signal bar 已算好 → 在本 bar 的第一个 tick 入场
   if(g_pending && g_pendingBar == closedBar)
   {
      g_lastBar = closedBar;
      if(g_dayTraded) { g_skipDayTraded++; g_pending = false; return; }
      OpenTrade(g_pendDir, g_pendAtr);
      return;
   }

   g_lastBar = closedBar;
   g_pending = false;
   EvaluateSignalBar(1);
}
//+------------------------------------------------------------------+
