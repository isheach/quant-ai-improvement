//+------------------------------------------------------------------+
//| dsh_MR30.mq5                                                     |
//| MR30 family: single-symbol M30 mean reversion for BTCUSDm        |
//|                                                                    |
//| This is a new research EA.  It does not modify the legacy EAs or  |
//| the earlier dsh_MeanRev.mq5.  The implementation deliberately      |
//| keeps the pre-registered axes fixed:                              |
//|   - M30 bars made from completed M1 bars                           |
//|   - 48-bar mean / standard deviation, entry at 2 sigma             |
//|   - fixed TP (1.5 or 2.5 ATR), fixed SL (2 ATR), 24-bar time exit  |
//|   - optional ATR percentile volatility filter (V3 only)            |
//|   - one position, no grid, no martingale, no trailing winner       |
//|                                                                    |
//| The tester is driven on M1.  All signal statistics use completed  |
//| M30 bars; the current, incomplete bucket is discarded.             |
//+------------------------------------------------------------------+
#property copyright "DeepSeek / GPT MR30 research"
#property version   "1.00"
#property strict

//==================== Pre-registered inputs =========================
input group "=== Risk / account (fixed research protocol) ==="
input double InpRiskPct              = 1.5;
input bool   InpUseEquityForRisk     = true;
input double InpMaxLot               = 100.0;
input bool   InpAllowMinLotOvershoot = false;
input double InpMinLotMaxRiskPct     = 3.0;

input group "=== Mean reversion signal (fixed) ==="
input int    InpMAPeriod             = 48;
input int    InpSigmaPeriod          = 48;
input double InpEntrySigma           = 2.0;
input bool   InpNeedReenter          = true;
input bool   InpAllowLong            = true;
input bool   InpAllowShort           = true;

input group "=== Exit (only TP differs between V1/V2) ==="
input double InpTP_ATR               = 1.5;
input double InpSL_ATR               = 2.0;
input int    InpMaxBarsInTrade       = 24;

input group "=== Volatility regime (V3 only) ==="
input bool   InpUseVolRegime         = false;
input int    InpVolLookback          = 500;
input double InpVolPctLow            = 20.0;
input double InpVolPctHigh           = 80.0;
input int    InpATRPeriod             = 14;

input group "=== Operational / audit ==="
input long   InpMagic                = 20260913;
input string InpRunTag               = "MR30";
input bool   InpWriteAudit           = true;
input double InpSlippagePoints       = 50.0;
input int    InpLatencyTicks         = 0;
input string InpTestEndDate          = "";    // yyyy.mm.dd; supplied by run manifest
input int    InpCloseAtEndHour       = 23;     // operational, not a strategy axis
input bool   InpVerboseLog           = false;

// M30 is intentionally a compile-time protocol constant.  There is no
// timeframe input to accidentally optimize or silently coerce in an INI.
#define MR30_TF_MINUTES 30
#define MR30_TF_SECONDS 1800

//==================== Runtime state =================================
long     g_lastBucket = -1;
int      g_pendingDir = 0;          // +1 long after lower-tail extreme; -1 short
datetime g_pendingTime = 0;
long     g_signalSeq = 0;

ulong    g_positionTicket = 0;
ulong    g_positionIdentifier = 0;
int      g_positionDir = 0;
datetime g_entryTime = 0;
datetime g_entryBarTime = 0;
double   g_entryPrice = 0.0;
double   g_entryATR = 0.0;
double   g_entryRisk = 0.0;
double   g_entrySL = 0.0;
double   g_entryTP = 0.0;
long     g_entrySignalId = -1;
string   g_lastCloseReason = "";

double   g_peakEquity = 0.0;
double   g_dayStartEquity = 0.0;
datetime g_day = 0;

long     g_nTrades = 0;
long     g_nWins = 0;
double   g_sumWin = 0.0;
double   g_sumLoss = 0.0;
double   g_bestWin = 0.0;
double   g_worstLoss = 0.0;
long     g_rejectRisk = 0;
long     g_rejectRegime = 0;
long     g_rejectStops = 0;
long     g_rejectOrder = 0;

int      g_auditFh = INVALID_HANDLE;
int      g_signalFh = INVALID_HANDLE;
int      g_selfcheckFh = INVALID_HANDLE;
bool     g_useCommonFiles = true;
bool     g_auditFailed = false;
bool     g_signalWriteFailed = false;
long     g_writtenDeals = 0;
long     g_duplicateHits = 0;
long     g_catchupCalls = 0;
long     g_catchupSelectFails = 0;
long     g_catchupTotal = 0;
long     g_catchupAdded = 0;

// Dynamic, post-write de-duplication.  A fixed 4096-slot table is not used:
// if a run is longer, the array grows and never silently permits duplicates.
ulong    g_seenDeals[];

//==================== Small utilities ===============================
double NormPrice(const double p)
{
   return NormalizeDouble(p, _Digits);
}

long BucketOf(const datetime t)
{
   return (long)t / (long)MR30_TF_SECONDS;
}

datetime BucketTime(const long b)
{
   return (datetime)(b * (long)MR30_TF_SECONDS);
}

bool IsNewBucket()
{
   long b = BucketOf(TimeCurrent());
   if(b == g_lastBucket) return false;
   g_lastBucket = b;
   return true;
}

bool TagHas(const string token)
{
   return StringFind(InpRunTag, token) >= 0;
}

bool TagEndsWith(const string suffix)
{
   int n = StringLen(InpRunTag);
   int m = StringLen(suffix);
   if(n < m) return false;
   return StringSubstr(InpRunTag, n - m, m) == suffix;
}

bool IsTrainTag()
{
   return StringFind(InpRunTag, "DS260913_MR30_") == 0 && TagEndsWith("_TRAIN");
}

bool IsValidTag()
{
   return StringFind(InpRunTag, "DS260913_MR30_") == 0 && TagEndsWith("_VALID");
}

bool IsPreregisteredTag()
{
   if(!IsTrainTag() && !IsValidTag()) return false;
   bool v1 = StringFind(InpRunTag, "DS260913_MR30_V1_") == 0;
   bool v2 = StringFind(InpRunTag, "DS260913_MR30_V2_") == 0;
   bool v3 = StringFind(InpRunTag, "DS260913_MR30_V3_") == 0;
   return ((v1 ? 1 : 0) + (v2 ? 1 : 0) + (v3 ? 1 : 0)) == 1;
}

string DealReasonName(const int reason)
{
   switch(reason)
   {
      case DEAL_REASON_SL:      return "sl";
      case DEAL_REASON_TP:      return "tp";
      case DEAL_REASON_SO:      return "stopout";
      case DEAL_REASON_CLIENT:  return "client";
      case DEAL_REASON_MOBILE:  return "mobile";
      case DEAL_REASON_WEB:     return "web";
      case DEAL_REASON_EXPERT:  return "expert";
   }
   return "other";
}

string RequestedReason(const string comment, const int serverReason)
{
   // The broker's TP/SL/stopout reason is authoritative.  Opening comments
   // are often propagated onto server-side exit deals and must not mask it.
   if(serverReason == DEAL_REASON_TP) return "tp";
   if(serverReason == DEAL_REASON_SL) return "sl";
   if(serverReason == DEAL_REASON_SO) return "stopout";
   if(StringFind(comment, "close_time") >= 0) return "time_exit";
   if(StringFind(comment, "close_window_end") >= 0) return "window_end";
   if(g_lastCloseReason != "") return g_lastCloseReason;
   if(StringFind(comment, "mr30_open") >= 0) return "server_close";
   return DealReasonName(serverReason);
}

bool SeenDeal(const ulong ticket)
{
   for(int i = 0; i < ArraySize(g_seenDeals); i++)
      if(g_seenDeals[i] == ticket) return true;
   return false;
}

bool RememberDealAfterWrite(const ulong ticket)
{
   int n = ArraySize(g_seenDeals);
   if(ArrayResize(g_seenDeals, n + 1) != n + 1)
   {
      g_auditFailed = true;
      return false;
   }
   g_seenDeals[n] = ticket;
   return true;
}

bool WriteSignalRow(const datetime barTime, const double z, const double ma,
                    const double sigma, const double atr, const int beforeDir,
                    const int afterDir, const string decision, const string reason,
                    const long signalId)
{
   if(!InpWriteAudit || g_signalFh == INVALID_HANDLE) return false;
   ResetLastError();
   uint n = FileWrite(g_signalFh, InpRunTag, _Symbol,
                      TimeToString(barTime, TIME_DATE|TIME_SECONDS),
                      IntegerToString(signalId), DoubleToString(z, 6),
                      DoubleToString(ma, _Digits), DoubleToString(sigma, _Digits),
                      DoubleToString(atr, _Digits), IntegerToString(beforeDir),
                      IntegerToString(afterDir), decision, reason,
                      (decision == "accepted" ? "1" : "0"));
   FileFlush(g_signalFh);
    // MQL5 FileWrite returns bytes written, not the number of fields.
    if(n == 0)
   {
      g_signalWriteFailed = true;
      if(InpVerboseLog)
          PrintFormat("[%s] signal FileWrite failed bytes=%u err=%d", InpRunTag, n, GetLastError());
      return false;
   }
   return true;
}

//==================== M1 -> completed M30 bars =======================
// Arrays are oldest-first.  The final aggregate bucket is discarded because
// it is the currently forming M30 bar; no signal calculation can see it.
int BuildM30Bars(const int wantBars, double &o[], double &h[], double &l[],
                 double &c[], datetime &bt[])
{
   if(wantBars < 3) return 0;
   int needM1 = MR30_TF_MINUTES * (wantBars + 3);
   MqlRates m1[];
   ArraySetAsSeries(m1, false);
   ResetLastError();
   int got = CopyRates(_Symbol, PERIOD_M1, 0, needM1, m1);
   if(got < MR30_TF_MINUTES * 2) return 0;

   ArrayResize(o, 0); ArrayResize(h, 0); ArrayResize(l, 0);
   ArrayResize(c, 0); ArrayResize(bt, 0);
   long currentBucket = -1;
   bool have = false;
   double bo = 0.0, bh = 0.0, bl = 0.0, bc = 0.0;
   datetime start = 0;

   for(int i = 0; i < got; i++)
   {
      long b = BucketOf(m1[i].time);
      if(!have || b != currentBucket)
      {
         if(have)
         {
            int n = ArraySize(c);
            ArrayResize(o, n+1); ArrayResize(h, n+1); ArrayResize(l, n+1);
            ArrayResize(c, n+1); ArrayResize(bt, n+1);
            o[n] = bo; h[n] = bh; l[n] = bl; c[n] = bc; bt[n] = start;
         }
         currentBucket = b; have = true;
         bo = m1[i].open; bh = m1[i].high; bl = m1[i].low;
         bc = m1[i].close; start = BucketTime(b);
      }
      else
      {
         if(m1[i].high > bh) bh = m1[i].high;
         if(m1[i].low < bl) bl = m1[i].low;
         bc = m1[i].close;
      }
   }
   if(have)
   {
      int n = ArraySize(c);
      ArrayResize(o, n+1); ArrayResize(h, n+1); ArrayResize(l, n+1);
      ArrayResize(c, n+1); ArrayResize(bt, n+1);
      o[n] = bo; h[n] = bh; l[n] = bl; c[n] = bc; bt[n] = start;
   }

   int nAll = ArraySize(c);
   if(nAll < 2) return 0;
   // Drop the open/current bucket, retaining only completed bars.
   ArrayResize(o, nAll - 1); ArrayResize(h, nAll - 1);
   ArrayResize(l, nAll - 1); ArrayResize(c, nAll - 1);
   ArrayResize(bt, nAll - 1);
   return nAll - 1;
}

double MeanAt(const double &x[], const int last, const int period)
{
   if(period <= 0 || last - period + 1 < 0) return 0.0;
   double s = 0.0;
   for(int i = last - period + 1; i <= last; i++) s += x[i];
   return s / period;
}

double SigmaAt(const double &x[], const int last, const int period, const double mean)
{
   if(period <= 1 || last - period + 1 < 0) return 0.0;
   double ss = 0.0;
   for(int i = last - period + 1; i <= last; i++)
   {
      double d = x[i] - mean;
      ss += d * d;
   }
   return MathSqrt(ss / period);
}

double ATRAt(const double &h[], const double &l[], const double &c[],
             const int last, const int period)
{
   if(period <= 0 || last - period + 1 < 1) return 0.0;
   double s = 0.0;
   for(int i = last - period + 1; i <= last; i++)
   {
      double tr = MathMax(h[i] - l[i],
                          MathMax(MathAbs(h[i] - c[i-1]), MathAbs(l[i] - c[i-1])));
      s += tr;
   }
   return s / period;
}

double PercentileCopy(const double &values[], const double pct)
{
   int n = ArraySize(values);
   if(n <= 0) return 0.0;
   double tmp[];
   ArrayResize(tmp, n);
   ArrayCopy(tmp, values);
   ArraySort(tmp);
   double q = pct / 100.0;
   if(q < 0.0) q = 0.0;
   if(q > 1.0) q = 1.0;
   int idx = (int)MathFloor(q * (n - 1) + 1e-9);
   if(idx < 0) idx = 0;
   if(idx >= n) idx = n - 1;
   return tmp[idx];
}

bool VolatilityPass(const double &h[], const double &l[], const double &c[],
                    const int last, const double currentAtr,
                    double &pLow, double &pHigh)
{
   pLow = 0.0; pHigh = 0.0;
   if(!InpUseVolRegime) return true;
   // The distribution deliberately ends at last-1.  The current signal bar's
   // ATR is compared with a trailing distribution that was known before it.
   int first = last - InpVolLookback;
   if(first < InpATRPeriod) return false;
   double vals[];
   ArrayResize(vals, InpVolLookback);
   int n = 0;
   for(int i = first; i < last; i++)
   {
      double a = ATRAt(h, l, c, i, InpATRPeriod);
      if(a > 0.0) vals[n++] = a;
   }
   if(n < InpVolLookback - 2) return false;
   ArrayResize(vals, n);
   pLow = PercentileCopy(vals, InpVolPctLow);
   pHigh = PercentileCopy(vals, InpVolPctHigh);
   return (currentAtr >= pLow && currentAtr <= pHigh);
}

//==================== Position / risk ================================
ulong FindPosition()
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

bool SelectMyPosition()
{
   ulong tk = FindPosition();
   if(tk == 0)
   {
      g_positionTicket = 0;
      g_positionIdentifier = 0;
      return false;
   }
   g_positionTicket = tk;
   if(!PositionSelectByTicket(tk))
   {
      g_positionIdentifier = 0;
      return false;
   }
   g_positionIdentifier = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
   return true;
}

bool SelectPositionByIdentifier(const ulong identifier)
{
   if(identifier == 0) return false;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if((ulong)PositionGetInteger(POSITION_IDENTIFIER) != identifier) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      return PositionSelectByTicket(tk);
   }
   return false;
}

ENUM_ORDER_TYPE_FILLING FillingMode()
{
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   if((mode & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

// For BTCUSDm the profit currency is USD, but using OrderCalcProfit here also
// makes the risk calculation explicit and guards against tick-value drift.
double LossPerLot(const int dir, const double price, const double stop)
{
   double result = 0.0;
   ResetLastError();
   bool ok = OrderCalcProfit(dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,
                             _Symbol, 1.0, price, stop, result);
   if(!ok) return 0.0;
   return MathAbs(result);
}

double AlignLotDown(const double raw)
{
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(step <= 0.0) step = 0.01;
   if(vmin <= 0.0) vmin = step;
   double x = MathFloor(raw / step + 1e-9) * step;
   if(x > vmax && vmax > 0.0) x = MathFloor(vmax / step + 1e-9) * step;
   if(InpMaxLot > 0.0 && x > InpMaxLot)
      x = MathFloor(InpMaxLot / step + 1e-9) * step;
   if(x < vmin) return 0.0;
   // Do not infer decimal precision from the step: valid broker steps such as
   // 0.25 would otherwise be rounded to 0.3.  MQL5 accepts up to eight volume
   // decimals; the floor above remains the source of truth for risk control.
   return NormalizeDouble(x, 8);
}

double LotForRisk(const int dir, const double price, const double stop,
                  double &riskUsed)
{
   riskUsed = 0.0;
   double base = InpUseEquityForRisk ? AccountInfoDouble(ACCOUNT_EQUITY)
                                     : AccountInfoDouble(ACCOUNT_BALANCE);
   if(base <= 0.0) return 0.0;
   double lossLot = LossPerLot(dir, price, stop);
   if(lossLot <= 0.0) { g_rejectRisk++; return 0.0; }
   double budget = base * InpRiskPct / 100.0;
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   if(vmin <= 0.0) vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double ideal = budget / lossLot;
   if(ideal < vmin)
   {
      if(!InpAllowMinLotOvershoot) { g_rejectRisk++; return 0.0; }
      double minRisk = vmin * lossLot;
      if(minRisk > base * InpMinLotMaxRiskPct / 100.0) { g_rejectRisk++; return 0.0; }
      riskUsed = minRisk;
      return vmin;
   }
   double lot = AlignLotDown(ideal);
   if(lot <= 0.0) { g_rejectRisk++; return 0.0; }
   riskUsed = lot * lossLot;
   // The floor should never exceed the budget; retain a defensive check.
   if(riskUsed > budget + 1e-8)
   {
      g_rejectRisk++;
      return 0.0;
   }
   return lot;
}

bool StopsAllowed(const int dir, const double price, const double sl, const double tp)
{
   long level = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(level <= 0) return true;
   double minDist = (double)level * _Point;
   if(MathAbs(price - sl) + 1e-9 < minDist) return false;
   if(MathAbs(tp - price) + 1e-9 < minDist) return false;
   return true;
}

//==================== Files / audit ==================================
bool OpenAuditSet(const bool common)
{
   int flags = FILE_WRITE|FILE_CSV|FILE_ANSI;
   if(common) flags |= FILE_COMMON;
   if(common)
   {
      FolderCreate("dshtrend", FILE_COMMON);
      FolderCreate("dshtrend/" + InpRunTag, FILE_COMMON);
   }
   else
   {
      FolderCreate("dshtrend");
      FolderCreate("dshtrend/" + InpRunTag);
   }
   string root = "dshtrend/" + InpRunTag + "/";

   g_auditFh = FileOpen(root + "trades.csv", flags, ',');
   g_signalFh = FileOpen(root + "signals.csv", flags, ',');
   g_selfcheckFh = FileOpen(root + "audit_selfcheck.csv", flags, ',');
   if(g_auditFh == INVALID_HANDLE || g_signalFh == INVALID_HANDLE ||
      g_selfcheckFh == INVALID_HANDLE)
   {
      PrintFormat("[%s] audit FileOpen failed common=%s err=%d", InpRunTag,
                  common ? "true" : "false", GetLastError());
      if(g_auditFh != INVALID_HANDLE) FileClose(g_auditFh);
      if(g_signalFh != INVALID_HANDLE) FileClose(g_signalFh);
      if(g_selfcheckFh != INVALID_HANDLE) FileClose(g_selfcheckFh);
      g_auditFh = INVALID_HANDLE; g_signalFh = INVALID_HANDLE;
      g_selfcheckFh = INVALID_HANDLE;
      return false;
   }
   ResetLastError();
   uint a = FileWrite(g_auditFh,
      "run_tag","symbol","signal_id","deal_ticket","position_id","dir",
      "entry_time","exit_time","entry","exit","volume","entry_atr",
      "risk_money","profit","swap","commission","net","close_type",
      "exit_reason","ocp_ok","ocp_value","ocp_error","formula_value",
      "formula_diff");
   uint s = FileWrite(g_signalFh,
      "run_tag","symbol","bar_time","signal_id","zscore","ma","sigma",
      "atr","pending_before","pending_after","decision","reason","accepted");
   uint c = FileWrite(g_selfcheckFh,
      "run_tag","written_deals","duplicate_hits","audit_failed",
      "signal_write_failed","catchup_calls","catchup_select_fails",
      "catchup_total","catchup_added","reject_risk","reject_regime",
      "reject_stops","reject_order");
   FileFlush(g_auditFh); FileFlush(g_signalFh); FileFlush(g_selfcheckFh);
   // A positive return value means the CSV row was written; the return value
   // is a byte count and therefore must not be compared with column counts.
   if(a == 0 || s == 0 || c == 0)
   {
      PrintFormat("[%s] audit header write failed common=%s bytes(a/s/c)=%u/%u/%u err=%d",
                  InpRunTag, common ? "true" : "false", a, s, c, GetLastError());
      FileClose(g_auditFh); FileClose(g_signalFh); FileClose(g_selfcheckFh);
      g_auditFh = INVALID_HANDLE; g_signalFh = INVALID_HANDLE;
      g_selfcheckFh = INVALID_HANDLE;
      return false;
   }
   return true;
}

bool OpenFiles()
{
   if(!InpWriteAudit) return true;
   // Prefer FILE_COMMON for normal terminals.  Portable tester agents can
   // deny that namespace; fall back to the worker's sandbox rather than
   // aborting a run with an un-audited result.
   if(OpenAuditSet(true)) { g_useCommonFiles = true; return true; }
   if(OpenAuditSet(false)) { g_useCommonFiles = false; return true; }
   g_auditFailed = true;
   return false;
}

bool WriteAuditDeal(const ulong dealTicket)
{
   if(!HistoryDealSelect(dealTicket)) return false;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return false;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return false;
   long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY) return false;
   if(SeenDeal(dealTicket)) { g_duplicateHits++; return true; }
   if(g_auditFh == INVALID_HANDLE) { g_auditFailed = true; return false; }

   double dProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
   double dSwap = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
   double dComm = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
   double net = dProfit + dSwap + dComm;
   double exitPx = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double vol = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   long dtype = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
   int dir = (dtype == DEAL_TYPE_SELL) ? 1 : -1;
   ulong pid = (ulong)HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
   datetime exitTime = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
   string comment = HistoryDealGetString(dealTicket, DEAL_COMMENT);
   int serverReason = (int)HistoryDealGetInteger(dealTicket, DEAL_REASON);
   string reason = RequestedReason(comment, serverReason);

   // Reconstruct the opening leg from the position's history.  This remains
   // valid during catch-up scans, even if the in-memory position was cleared.
   double entryPx = 0.0, entryVol = 0.0;
   datetime entryTime = 0;
   long historySignalId = -1;
   if(HistorySelectByPosition(pid))
   {
      int n = HistoryDealsTotal();
      double weighted = 0.0;
      for(int i = 0; i < n; i++)
      {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0) continue;
          if(HistoryDealGetInteger(tk, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
          double v = HistoryDealGetDouble(tk, DEAL_VOLUME);
          double p = HistoryDealGetDouble(tk, DEAL_PRICE);
          weighted += p * v; entryVol += v;
          datetime et = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
          if(entryTime == 0 || et < entryTime) entryTime = et;
          string openComment = HistoryDealGetString(tk, DEAL_COMMENT);
          int marker = StringFind(openComment, "mr30_open_");
          if(marker >= 0)
          {
             string sidText = StringSubstr(openComment, marker + StringLen("mr30_open_"));
             historySignalId = StringToInteger(sidText);
          }
       }
      if(entryVol > 0.0) entryPx = weighted / entryVol;
   }
   if(entryPx <= 0.0 && pid == g_positionIdentifier) entryPx = g_entryPrice;
   if(entryTime == 0 && pid == g_positionIdentifier) entryTime = g_entryTime;
   double entryAtr = (pid == g_positionIdentifier ? g_entryATR : 0.0);
   double riskMoney = (pid == g_positionIdentifier ? g_entryRisk : 0.0);
   long signalId = (pid == g_positionIdentifier ? g_entrySignalId : historySignalId);
   string closeType = "full";
   if(SelectPositionByIdentifier(pid) && PositionGetDouble(POSITION_VOLUME) > 1e-9)
      closeType = "partial";
   if(entryVol > 0.0 && vol < entryVol - 1e-9 && riskMoney > 0.0)
      riskMoney *= vol / entryVol;

   double ocp = 0.0; int ocpErr = 0; bool ocpOk = false;
   ResetLastError();
   if(entryPx > 0.0 && exitPx > 0.0 && vol > 0.0)
   {
      ocpOk = OrderCalcProfit(dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,
                               _Symbol, vol, entryPx, exitPx, ocp);
      if(!ocpOk) ocpErr = GetLastError();
   }
   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contract <= 0.0) contract = 1.0;
   double formula = (dir > 0 ? (exitPx - entryPx) : (entryPx - exitPx)) * contract * vol;
   double formulaDiff = dProfit - formula;
   double ocpTol = MathMax(0.02, 0.001 * MathMax(1.0, MathAbs(dProfit)));
   bool fieldsOk = (pid > 0 && entryPx > 0.0 && exitPx > 0.0 && vol > 0.0 && entryTime > 0);
   if(!fieldsOk || !ocpOk || MathAbs(ocp - dProfit) > ocpTol || MathAbs(formulaDiff) > 0.05)
      g_auditFailed = true;

   ResetLastError();
   uint wrote = FileWrite(g_auditFh,
      InpRunTag, _Symbol, IntegerToString(signalId),
      IntegerToString((long)dealTicket), IntegerToString((long)pid), IntegerToString(dir),
      TimeToString(entryTime, TIME_DATE|TIME_SECONDS),
      TimeToString(exitTime, TIME_DATE|TIME_SECONDS),
      DoubleToString(entryPx, _Digits), DoubleToString(exitPx, _Digits),
      DoubleToString(vol, 2), DoubleToString(entryAtr, _Digits),
      DoubleToString(riskMoney, 2), DoubleToString(dProfit, 2),
      DoubleToString(dSwap, 2), DoubleToString(dComm, 2), DoubleToString(net, 2),
      closeType, reason, (ocpOk ? "1" : "0"), DoubleToString(ocp, 2),
      IntegerToString(ocpErr), DoubleToString(formula, 2), DoubleToString(formulaDiff, 6));
   FileFlush(g_auditFh);
   // FileWrite's uint result is the number of bytes, not 24 columns.
   if(wrote == 0)
   {
      g_auditFailed = true;
      return false; // Do not remember the ticket: a later catch-up can retry.
   }
   if(!RememberDealAfterWrite(dealTicket)) return false;
   g_writtenDeals++;
   g_nTrades++;
   if(net > 0.0) { g_nWins++; g_sumWin += net; if(net > g_bestWin) g_bestWin = net; }
   else { g_sumLoss += net; if(net < g_worstLoss) g_worstLoss = net; }
   if(!SelectPositionByIdentifier(pid))
   {
      g_positionTicket = 0; g_positionIdentifier = 0;
      g_positionDir = 0; g_entrySignalId = -1;
   }
   return true;
}

void CatchUpAudit()
{
   if(!InpWriteAudit) return;
   g_catchupCalls++;
   ResetLastError();
   if(!HistorySelect(0, TimeCurrent() + 7 * 86400))
   {
      g_catchupSelectFails++;
      return;
   }
   int total = HistoryDealsTotal();
   g_catchupTotal = total;
   // HistorySelectByPosition inside WriteAuditDeal changes the active list,
   // so snapshot tickets before processing.
   ulong tickets[];
   ArrayResize(tickets, total);
   for(int i = 0; i < total; i++) tickets[i] = HistoryDealGetTicket(i);
   for(int i = 0; i < total; i++)
   {
      int before = (int)g_writtenDeals;
      WriteAuditDeal(tickets[i]);
      if((int)g_writtenDeals > before) g_catchupAdded++;
   }
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      WriteAuditDeal(trans.deal);
}

//==================== Orders =========================================
bool ClosePosition(const string reason)
{
   if(!SelectMyPosition()) return false;
   int dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   double vol = PositionGetDouble(POSITION_VOLUME);
   if(vol <= 0.0) return false;
   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = _Symbol;
   req.position = g_positionTicket;
   req.volume = vol;
   req.type = dir > 0 ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.price = NormPrice(dir > 0 ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                 : SymbolInfoDouble(_Symbol, SYMBOL_ASK));
   req.deviation = (ulong)InpSlippagePoints;
   req.magic = InpMagic;
   req.comment = "close_" + reason;
   req.type_filling = FillingMode();
   g_lastCloseReason = reason;
   ResetLastError();
   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      g_rejectOrder++;
      g_lastCloseReason = "";
      return false;
   }
   return true;
}

bool OpenPosition(const int dir, const double atr, const long signalId)
{
   double price = dir > 0 ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                          : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0 || atr <= 0.0) { g_rejectOrder++; return false; }
   double slDist = InpSL_ATR * atr;
   double tpDist = InpTP_ATR * atr;
   double sl = dir > 0 ? price - slDist : price + slDist;
   double tp = dir > 0 ? price + tpDist : price - tpDist;
   sl = NormPrice(sl); tp = NormPrice(tp); price = NormPrice(price);
   if(!StopsAllowed(dir, price, sl, tp)) { g_rejectStops++; return false; }

   double risk = 0.0;
   double lot = LotForRisk(dir, price, sl, risk);
   if(lot <= 0.0) return false;

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = _Symbol;
   req.volume = lot;
   req.type = dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price = price;
   req.sl = sl;
   req.tp = tp;
   req.deviation = (ulong)InpSlippagePoints;
   req.magic = InpMagic;
   req.comment = "mr30_open_" + IntegerToString(signalId);
   req.type_filling = FillingMode();
   ResetLastError();
   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      g_rejectOrder++;
      return false;
   }
   if(!SelectMyPosition()) { g_auditFailed = true; return false; }
   g_positionDir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   g_entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   g_entryTime = (datetime)PositionGetInteger(POSITION_TIME);
   if(g_entryTime <= 0) g_entryTime = TimeCurrent();
   g_entryBarTime = BucketTime(BucketOf(g_entryTime));
   g_entryATR = atr;
   g_entryRisk = risk;
   g_entrySL = PositionGetDouble(POSITION_SL);
   g_entryTP = PositionGetDouble(POSITION_TP);
   g_entrySignalId = signalId;
   if(InpVerboseLog)
      PrintFormat("[%s] OPEN dir=%d lot=%.4f entry=%.2f sl=%.2f tp=%.2f atr=%.2f risk=%.2f sid=%I64d",
                  InpRunTag, g_positionDir, PositionGetDouble(POSITION_VOLUME),
                  g_entryPrice, g_entrySL, g_entryTP, g_entryATR, g_entryRisk, signalId);
   return true;
}

//==================== Signal / management ===========================
bool EndWindowReached()
{
   if(StringLen(InpTestEndDate) < 10) return false;
   datetime endDay = StringToTime(InpTestEndDate + " 00:00");
   if(endDay <= 0) return false;
   MqlDateTime now; TimeToStruct(TimeCurrent(), now);
   MqlDateTime end; TimeToStruct(endDay, end);
   return (now.year == end.year && now.mon == end.mon && now.day == end.day &&
           now.hour >= InpCloseAtEndHour);
}

void ManagePosition()
{
   if(!SelectMyPosition()) return;
   if(EndWindowReached())
   {
      ClosePosition("window_end");
      return;
   }
   if(InpMaxBarsInTrade > 0 && g_entryBarTime > 0)
   {
      long held = BucketOf(TimeCurrent()) - BucketOf(g_entryBarTime);
      if(held >= InpMaxBarsInTrade)
      {
         ClosePosition("time");
         return;
      }
   }
   // TP and SL are fixed at entry.  There is intentionally no trailing or
   // break-even modification in this family.
}

bool EvaluateAndMaybeOpen()
{
   int want = MathMax(InpVolLookback + InpATRPeriod + 8,
                      MathMax(InpMAPeriod, InpSigmaPeriod) + InpATRPeriod + 8);
   double o[], h[], l[], c[]; datetime bt[];
   int n = BuildM30Bars(want, o, h, l, c, bt);
   if(n <= 0) return false;
   int last = n - 1;
   int need = MathMax(InpMAPeriod, InpSigmaPeriod) + InpATRPeriod + 2;
   if(last < need) return false;
   double ma = MeanAt(c, last, InpMAPeriod);
   double sigma = SigmaAt(c, last, InpSigmaPeriod, ma);
   double atr = ATRAt(h, l, c, last, InpATRPeriod);
   if(ma <= 0.0 || sigma <= 0.0 || atr <= 0.0) return false;
   double z = (c[last] - ma) / sigma;
   int before = g_pendingDir;
   int after = g_pendingDir;
   string decision = "none";
   string reason = "";
   int signalDir = 0;

   if(!InpNeedReenter)
   {
      if(z <= -InpEntrySigma && InpAllowLong) signalDir = 1;
      else if(z >= InpEntrySigma && InpAllowShort) signalDir = -1;
      after = 0;
   }
   else
   {
      // A tail event arms the signal.  It cannot be consumed on the same bar;
      // the next completed bar must re-enter the +/- entry band.
      if(g_pendingDir != 0 && bt[last] > g_pendingTime)
      {
         if(g_pendingDir > 0 && z > -InpEntrySigma)
         {
            signalDir = InpAllowLong ? 1 : 0;
            reason = "reenter_lower";
            g_pendingDir = 0; after = 0;
         }
         else if(g_pendingDir < 0 && z < InpEntrySigma)
         {
            signalDir = InpAllowShort ? -1 : 0;
            reason = "reenter_upper";
            g_pendingDir = 0; after = 0;
         }
         else if(z <= -InpEntrySigma || z >= InpEntrySigma)
         {
            g_pendingDir = (z <= -InpEntrySigma ? 1 : -1);
            g_pendingTime = bt[last]; after = g_pendingDir;
            reason = "replace_extreme";
         }
         else
         {
            g_pendingDir = 0; after = 0; reason = "no_reentry";
         }
      }
      else if(g_pendingDir == 0)
      {
         if(z <= -InpEntrySigma)
         {
            g_pendingDir = 1; g_pendingTime = bt[last]; after = 1;
            reason = "arm_lower";
         }
         else if(z >= InpEntrySigma)
         {
            g_pendingDir = -1; g_pendingTime = bt[last]; after = -1;
            reason = "arm_upper";
         }
         else reason = "inside_band";
      }
   }

   if(signalDir != 0)
   {
      double pLow = 0.0, pHigh = 0.0;
      if(!VolatilityPass(h, l, c, last, atr, pLow, pHigh))
      {
         g_rejectRegime++;
         decision = "blocked"; reason = "vol_regime";
         WriteSignalRow(bt[last], z, ma, sigma, atr, before, after, decision, reason, -1);
         return false;
      }
      long sid = ++g_signalSeq;
      if(OpenPosition(signalDir, atr, sid))
      {
         decision = "accepted";
         if(reason == "") reason = signalDir > 0 ? "lower_reentry" : "upper_reentry";
         WriteSignalRow(bt[last], z, ma, sigma, atr, before, after, decision, reason, sid);
         return true;
      }
      decision = "rejected";
      if(reason == "") reason = "order_or_risk";
      WriteSignalRow(bt[last], z, ma, sigma, atr, before, after, decision, reason, sid);
      return false;
   }
   if(reason == "") reason = "no_signal";
   WriteSignalRow(bt[last], z, ma, sigma, atr, before, after, decision, reason, -1);
   return false;
}

void RefreshEquity()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq > g_peakEquity) g_peakEquity = eq;
   MqlDateTime t; TimeToStruct(TimeCurrent(), t);
   t.hour = 0; t.min = 0; t.sec = 0;
   datetime day = StructToTime(t);
   if(day != g_day)
   {
      g_day = day;
      g_dayStartEquity = eq;
   }
}

//==================== Lifecycle ======================================
int OnInit()
{
   // Hard guards make accidental use on another symbol, timeframe or input
   // axis fail loudly rather than producing a plausible but wrong run.
   if(_Symbol != "BTCUSDm") { Print("MR30 requires BTCUSDm"); return INIT_PARAMETERS_INCORRECT; }
   if(Period() != PERIOD_M1) { Print("MR30 must be tested on M1"); return INIT_PARAMETERS_INCORRECT; }
   if(!IsPreregisteredTag()) { Print("MR30 requires a pre-registered V1/V2/V3 TRAIN/VALID tag"); return INIT_PARAMETERS_INCORRECT; }
   if(IsTrainTag() && InpTestEndDate != "2024.05.31") return INIT_PARAMETERS_INCORRECT;
   if(IsValidTag() && InpTestEndDate != "2025.05.31") return INIT_PARAMETERS_INCORRECT;
   if(InpMAPeriod != 48 || InpSigmaPeriod != 48 || MathAbs(InpEntrySigma - 2.0) > 1e-9)
      return INIT_PARAMETERS_INCORRECT;
   if(!InpNeedReenter || MathAbs(InpSL_ATR - 2.0) > 1e-9 || InpMaxBarsInTrade != 24)
      return INIT_PARAMETERS_INCORRECT;
   if(MathAbs(InpTP_ATR - 1.5) > 1e-9 && MathAbs(InpTP_ATR - 2.5) > 1e-9)
      return INIT_PARAMETERS_INCORRECT;
   if(InpVolLookback != 500 || MathAbs(InpVolPctLow-20.0)>1e-9 ||
      MathAbs(InpVolPctHigh-80.0)>1e-9 || InpATRPeriod != 14)
      return INIT_PARAMETERS_INCORRECT;
   if(InpRiskPct != 1.5 || !InpUseEquityForRisk || MathAbs(InpMaxLot-100.0)>1e-9 ||
      InpAllowMinLotOvershoot || InpMinLotMaxRiskPct != 3.0 ||
      !InpAllowLong || !InpAllowShort)
      return INIT_PARAMETERS_INCORRECT;
   if(InpLatencyTicks != 0 || !InpWriteAudit || InpMagic != 20260913 ||
      MathAbs(InpSlippagePoints-50.0)>1e-9 || InpCloseAtEndHour != 23 ||
      InpVerboseLog || StringLen(InpTestEndDate) < 10)
      return INIT_PARAMETERS_INCORRECT;
   if(StringFind(InpRunTag, "DS260913_MR30_V1_") == 0 &&
      (MathAbs(InpTP_ATR-1.5)>1e-9 || InpUseVolRegime))
      return INIT_PARAMETERS_INCORRECT;
   if(StringFind(InpRunTag, "DS260913_MR30_V2_") == 0 &&
      (MathAbs(InpTP_ATR-2.5)>1e-9 || InpUseVolRegime))
      return INIT_PARAMETERS_INCORRECT;
   if(StringFind(InpRunTag, "DS260913_MR30_V3_") == 0 &&
      (MathAbs(InpTP_ATR-1.5)>1e-9 || !InpUseVolRegime))
      return INIT_PARAMETERS_INCORRECT;
   if(!OpenFiles()) return INIT_FAILED;
   g_peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayStartEquity = g_peakEquity;
   g_day = 0;
   PrintFormat("[%s] MR30 init symbol=%s M30 mean=%d sigma=%d entry=%.1f TP=%.1fATR SL=%.1fATR max=%d V3=%s risk=%.2f%%",
               InpRunTag, _Symbol, InpMAPeriod, InpSigmaPeriod, InpEntrySigma,
               InpTP_ATR, InpSL_ATR, InpMaxBarsInTrade,
               InpUseVolRegime ? "on" : "off", InpRiskPct);
   return INIT_SUCCEEDED;
}

void OnTick()
{
   RefreshEquity();
   if(SelectMyPosition())
   {
      ManagePosition();
      // Catch-up on position transitions so server-side TP/SL is captured.
      if((g_catchupCalls % 8) == 0) CatchUpAudit();
      return;
   }
   if(g_auditFailed) return;
   if(!IsNewBucket()) return;
   EvaluateAndMaybeOpen();
}

double OnTester()
{
   CatchUpAudit();
   return 0.0;
}

void OnDeinit(const int reason)
{
   // Give the tester's history one last chance before handles close.
   CatchUpAudit();
   if(g_selfcheckFh != INVALID_HANDLE)
   {
      ResetLastError();
      uint n = FileWrite(g_selfcheckFh, InpRunTag,
                         IntegerToString(g_writtenDeals), IntegerToString(g_duplicateHits),
                         (g_auditFailed ? "1" : "0"),
                         (g_signalWriteFailed ? "1" : "0"),
                         IntegerToString(g_catchupCalls), IntegerToString(g_catchupSelectFails),
                         IntegerToString(g_catchupTotal), IntegerToString(g_catchupAdded),
                         IntegerToString(g_rejectRisk), IntegerToString(g_rejectRegime),
                         IntegerToString(g_rejectStops), IntegerToString(g_rejectOrder));
      FileFlush(g_selfcheckFh);
      // FileWrite returns bytes written; zero is the only failure sentinel.
      if(n == 0) g_auditFailed = true;
   }
   if(g_auditFh != INVALID_HANDLE) { FileFlush(g_auditFh); FileClose(g_auditFh); }
   if(g_signalFh != INVALID_HANDLE) { FileFlush(g_signalFh); FileClose(g_signalFh); }
   if(g_selfcheckFh != INVALID_HANDLE) { FileFlush(g_selfcheckFh); FileClose(g_selfcheckFh); }
   PrintFormat("[%s] MR30 end reason=%d trades=%I64d wins=%I64d net=%.2f audit=%I64d failed=%s",
               InpRunTag, reason, g_nTrades, g_nWins, g_sumWin + g_sumLoss,
               g_writtenDeals, g_auditFailed ? "yes" : "no");
}
//+------------------------------------------------------------------+
