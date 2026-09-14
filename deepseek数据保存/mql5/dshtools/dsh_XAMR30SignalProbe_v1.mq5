//+------------------------------------------------------------------+
//| dsh_XAMR30SignalProbe_v1.mq5                                    |
//| Read-only N1R3 signal reference probe                           |
//|                                                                  |
//| This EA does not trade and has no strategy-return path.  It reads |
//| only timestamps/sample labels prepared by the independent Python  |
//| selector, then computes the signal fields independently through   |
//| MT5 iMA/iATR and exact XAUUSDm M30 history.  On the bootstrap run |
//| it also exports raw M30 OHLC from the real Tester history.        |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"

input string   InpRunTag         = "XAMR30_DBL_BOOTSTRAP";
input string   InpWindow         = "ALL";
input string   InpInfoSymbol     = "XAUUSDm";
input string   InpSampleFile     = "dshtrend\\XAMR30DoubleCalc\\selected_samples.csv";
input string   InpOutputFile     = "dshtrend\\XAMR30DoubleCalc\\probe_ALL_mql.csv";
input bool     InpExportRaw      = false;
input string   InpRawUsdFile     = "dshtrend\\XAMR30DoubleCalc\\raw_USDJPYm_M30.csv";
input string   InpRawXauFile     = "dshtrend\\XAMR30DoubleCalc\\raw_XAUUSDm_M30.csv";
input datetime InpRawFrom        = D'2022.01.01 00:00:00';
input datetime InpRawTo          = D'2023.08.02 00:00:00';

const int EMA_PERIOD = 48;
const int SIGMA_WINDOW = 48;
const int ATR_PERIOD = 14;
const int ATR_PERCENTILE_WINDOW = 500;

int g_emaHandle = INVALID_HANDLE;
int g_atrHandle = INVALID_HANDLE;

struct SampleRow
{
   string   row_id;
   string   window;
   string   sample_type;
   datetime t;
   string   source_file;
   string   source_ticket;
};

void Log(const string s)
{
   PrintFormat("[%s] %s", InpRunTag, s);
}

string F(const double v)
{
   return DoubleToString(v, 10);
}

string TS(const datetime t)
{
   if(t <= 0) return "";
   return TimeToString(t, TIME_DATE|TIME_SECONDS);
}

bool ReadSamples(SampleRow &rows[])
{
   ArrayResize(rows, 0);
   int fh = FileOpen(InpSampleFile, FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(fh == INVALID_HANDLE)
   {
      Log("sample file open failed: " + InpSampleFile);
      return false;
   }

   // Header: row_id,window,sample_type,timestamp,source_audit_file,source_ticket
   if(!FileIsEnding(fh))
   {
      FileReadString(fh); FileReadString(fh); FileReadString(fh);
      FileReadString(fh); FileReadString(fh); FileReadString(fh);
   }

   while(!FileIsEnding(fh))
   {
      string id = FileReadString(fh);
      string win = FileReadString(fh);
      string typ = FileReadString(fh);
      string stamp = FileReadString(fh);
      string src = FileReadString(fh);
      string ticket = FileReadString(fh);
      if(StringLen(id) == 0 && StringLen(stamp) == 0)
         continue;
      if(StringLen(id) == 0 || StringLen(win) == 0 || StringLen(typ) == 0 || StringLen(stamp) == 0)
      {
         Log("malformed sample row; probe will mark it invalid");
         continue;
      }

      SampleRow r;
      r.row_id = id;
      r.window = win;
      r.sample_type = typ;
      r.t = StringToTime(stamp);
      r.source_file = src;
      r.source_ticket = ticket;
      int n = ArraySize(rows);
      ArrayResize(rows, n + 1);
      rows[n] = r;
   }
   FileClose(fh);
   return true;
}

bool GetBufferValue(const int handle, const int shift, double &value)
{
   value = 0.0;
   if(handle == INVALID_HANDLE || shift < 0) return false;
   double b[];
   if(CopyBuffer(handle, 0, shift, 1, b) != 1) return false;
   if(ArraySize(b) != 1 || !MathIsValidNumber(b[0])) return false;
   value = b[0];
   return true;
}

bool EmaAt(const int shift, double &value)
{
   return GetBufferValue(g_emaHandle, shift, value) && value > 0.0;
}

bool AtrAt(const int shift, double &value)
{
   return GetBufferValue(g_atrHandle, shift, value) && value > 0.0;
}

bool SigmaBeforeT(const int tShift, double &outSigma)
{
   outSigma = 0.0;
   double residuals[];
   ArrayResize(residuals, SIGMA_WINDOW);
   for(int k = 0; k < SIGMA_WINDOW; k++)
   {
      int sh = tShift + 1 + k;
      double em = 0.0;
      if(!EmaAt(sh, em)) return false;
      double c = iClose(_Symbol, PERIOD_M30, sh);
      if(c <= 0.0) return false;
      residuals[k] = c - em;
   }

   double mean = 0.0;
   for(int k = 0; k < SIGMA_WINDOW; k++) mean += residuals[k];
   mean /= SIGMA_WINDOW;
   double variance = 0.0;
   for(int k = 0; k < SIGMA_WINDOW; k++)
      variance += (residuals[k] - mean) * (residuals[k] - mean);
   variance /= (SIGMA_WINDOW - 1);
   if(variance <= 0.0) return false;
   outSigma = MathSqrt(variance);
   return MathIsValidNumber(outSigma) && outSigma > 0.0;
}

bool AtrPercentile(const int tShift, double &p20, double &p80)
{
   p20 = 0.0; p80 = 0.0;
   double a[];
   ArrayResize(a, ATR_PERCENTILE_WINDOW);
   int got = CopyBuffer(g_atrHandle, 0, tShift + 1, ATR_PERCENTILE_WINDOW, a);
   if(got != ATR_PERCENTILE_WINDOW) return false;
   for(int k = 0; k < ATR_PERCENTILE_WINDOW; k++)
      if(!MathIsValidNumber(a[k]) || a[k] <= 0.0) return false;
   ArraySort(a);
   int r20 = (int)MathCeil(20.0 / 100.0 * ATR_PERCENTILE_WINDOW);
   int r80 = (int)MathCeil(80.0 / 100.0 * ATR_PERCENTILE_WINDOW);
   if(r20 < 1) r20 = 1;
   if(r80 > ATR_PERCENTILE_WINDOW) r80 = ATR_PERCENTILE_WINDOW;
   p20 = a[r20 - 1];
   p80 = a[r80 - 1];
   return p80 > 0.0;
}

bool ExactXau(const datetime t, datetime &xt, double &xo, double &xc, double &xr)
{
   xt = 0; xo = 0.0; xc = 0.0; xr = 0.0;
   int sh = iBarShift(InpInfoSymbol, PERIOD_M30, t, true);
   if(sh < 0) return false;
   xt = iTime(InpInfoSymbol, PERIOD_M30, sh);
   if(xt != t) { xt = 0; return false; }
   xo = iOpen(InpInfoSymbol, PERIOD_M30, sh);
   xc = iClose(InpInfoSymbol, PERIOD_M30, sh);
   if(xo <= 0.0) return false;
   xr = xc / xo - 1.0;
   return true;
}

void WriteInvalid(int fh, const SampleRow &r, const string reason, const int shift)
{
   string e = "";
   FileWrite(fh, r.row_id, r.window, r.sample_type, TS(r.t), r.source_file, r.source_ticket,
             "INVALID_" + reason, IntegerToString(shift),
             e,e,e,e,e,
             e,e,e,e,e,
             e,e,e,e,e,
             e,e,e,e,e);
}

int WriteProbe()
{
   SampleRow rows[];
   bool sampleOk = ReadSamples(rows);
   int out = FileOpen(InpOutputFile, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(out == INVALID_HANDLE)
   {
      Log("probe output open failed: " + InpOutputFile);
      return 0;
   }
   FileWrite(out, "row_id", "window", "sample_type", "timestamp", "source_audit_file", "source_ticket",
             "row_status", "bar_shift", "usd_open", "usd_high", "usd_low", "usd_close", "usd_tr",
             "ema48", "residual", "sigma48", "z_score", "atr14",
             "atr_p20", "atr_p80", "xau_bar_time", "xau_open", "xau_close", "xau_return",
             "v1_candidate", "v3_candidate", "direction", "atr_regime_pass", "xau_filter_pass");
   if(!sampleOk)
   {
      FileClose(out);
      return 0;
   }

   int written = 0;
   for(int i = 0; i < ArraySize(rows); i++)
   {
      SampleRow r = rows[i];
      if(InpWindow != "ALL" && r.window != InpWindow) continue;

      int shift = iBarShift(_Symbol, PERIOD_M30, r.t, true);
      if(shift < 0) { WriteInvalid(out, r, "NO_EXACT_USDJPY_BAR", shift); continue; }
      double usdOpen = iOpen(_Symbol, PERIOD_M30, shift);
      double usdHigh = iHigh(_Symbol, PERIOD_M30, shift);
      double usdLow = iLow(_Symbol, PERIOD_M30, shift);
      double usdClose = iClose(_Symbol, PERIOD_M30, shift);
      double previousClose = iClose(_Symbol, PERIOD_M30, shift + 1);
      double usdTr = MathMax(usdHigh - usdLow,
                      MathMax(MathAbs(usdHigh - previousClose), MathAbs(usdLow - previousClose)));
      double ema = 0.0;
      if(!EmaAt(shift, ema)) { WriteInvalid(out, r, "EMA_INVALID", shift); continue; }
      double close = iClose(_Symbol, PERIOD_M30, shift);
      if(close <= 0.0) { WriteInvalid(out, r, "CLOSE_INVALID", shift); continue; }
      double residual = close - ema;
      double sigma = 0.0;
      if(!SigmaBeforeT(shift, sigma)) { WriteInvalid(out, r, "SIGMA_INVALID", shift); continue; }
      double z = residual / sigma;
      double atr = 0.0;
      if(!AtrAt(shift, atr)) { WriteInvalid(out, r, "ATR_INVALID", shift); continue; }
      double p20 = 0.0, p80 = 0.0;
      if(!AtrPercentile(shift, p20, p80)) { WriteInvalid(out, r, "ATR_PERCENTILE_INVALID", shift); continue; }

      datetime xt = 0; double xo = 0.0, xc = 0.0, xr = 0.0;
      if(!ExactXau(r.t, xt, xo, xc, xr))
      {
         FileWrite(out, r.row_id, r.window, r.sample_type, TS(r.t), r.source_file, r.source_ticket,
                   "INVALID_XAU_NOT_EXACT", IntegerToString(shift), F(usdOpen), F(usdHigh), F(usdLow), F(usdClose), F(usdTr),
                   F(ema), F(residual), F(sigma), F(z), F(atr),
                   F(p20), F(p80), TS(xt), "", "", "", "", "", "", "", "");
         continue;
      }

      int v1 = (MathAbs(z) >= 1.5) ? 1 : 0;
      int v3 = (MathAbs(z) >= 2.0) ? 1 : 0;
      string direction = z < 0.0 ? "long" : (z > 0.0 ? "short" : "none");
      int atrPass = (atr >= p20 && atr <= p80) ? 1 : 0;
      int xauPass = (xr != 0.0 && ((xr > 0.0 && z > 0.0) || (xr < 0.0 && z < 0.0))) ? 1 : 0;
      FileWrite(out, r.row_id, r.window, r.sample_type, TS(r.t), r.source_file, r.source_ticket,
                "PASS", IntegerToString(shift), F(usdOpen), F(usdHigh), F(usdLow), F(usdClose), F(usdTr),
                F(ema), F(residual), F(sigma), F(z), F(atr), F(p20), F(p80),
                TS(xt), F(xo), F(xc), F(xr), IntegerToString(v1), IntegerToString(v3), direction,
                IntegerToString(atrPass), IntegerToString(xauPass));
      written++;
   }
   FileClose(out);
   return written;
}

bool ExportRaw(const string symbol, const string fileName)
{
   MqlRates rates[];
   int got = CopyRates(symbol, PERIOD_M30, InpRawFrom, InpRawTo, rates);
   if(got <= 0)
   {
      Log("raw CopyRates failed symbol=" + symbol + " err=" + IntegerToString(GetLastError()));
      return false;
   }
   int fh = FileOpen(fileName, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(fh == INVALID_HANDLE)
   {
      Log("raw output open failed: " + fileName);
      return false;
   }
   FileWrite(fh, "timestamp", "timestamp_iso", "open", "high", "low", "close");
   for(int i = 0; i < got; i++)
      FileWrite(fh, (string)rates[i].time, TS(rates[i].time),
                DoubleToString(rates[i].open, 8), DoubleToString(rates[i].high, 8),
                DoubleToString(rates[i].low, 8), DoubleToString(rates[i].close, 8));
   FileClose(fh);
   Log("raw exported symbol=" + symbol + " bars=" + IntegerToString(got) + " -> " + fileName);
   return true;
}

int OnInit()
{
   if(!SymbolSelect(_Symbol, true) || !SymbolSelect(InpInfoSymbol, true))
   {
      Log("SymbolSelect failed");
      return INIT_FAILED;
   }
   g_emaHandle = iMA(_Symbol, PERIOD_M30, EMA_PERIOD, 0, MODE_EMA, PRICE_CLOSE);
   g_atrHandle = iATR(_Symbol, PERIOD_M30, ATR_PERIOD);
   if(g_emaHandle == INVALID_HANDLE || g_atrHandle == INVALID_HANDLE)
   {
      Log("indicator handle creation failed");
      return INIT_FAILED;
   }
   Log("init ok; read-only probe; window=" + InpWindow);
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Intentionally empty: this EA never trades or emits strategy returns.
}

double OnTester()
{
   if(InpExportRaw)
   {
      ExportRaw(_Symbol, InpRawUsdFile);
      ExportRaw(InpInfoSymbol, InpRawXauFile);
   }
   int n = WriteProbe();
   Log("OnTester completed rows=" + IntegerToString(n));
   return (double)n;
}

void OnDeinit(const int reason)
{
   if(g_emaHandle != INVALID_HANDLE) { IndicatorRelease(g_emaHandle); g_emaHandle = INVALID_HANDLE; }
   if(g_atrHandle != INVALID_HANDLE) { IndicatorRelease(g_atrHandle); g_atrHandle = INVALID_HANDLE; }
   Log("deinit reason=" + IntegerToString(reason));
}
//+------------------------------------------------------------------+
