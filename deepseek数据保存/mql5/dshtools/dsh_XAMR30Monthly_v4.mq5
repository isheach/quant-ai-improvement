//+------------------------------------------------------------------+
//| dsh_XAMR30Monthly_v4.mq5 — 单月双品种 M30 数据资格探针 (v4)       |
//|                                                                  |
//| v4 只修复 Monthly Probe 的工程可信度，不改变 XAMR30 策略。       |
//|                                                                  |
//| Method A: 真正使用 iBars + iTime 遍历完整 series，按 [a,b) 过滤。 |
//| Method B: CopyTime(a, b-1s)，再显式按 [a,b) 过滤。                |
//| 两个方法比较完整 timestamp 集合，而不是只比较 count。             |
//|                                                                  |
//| 正式结果只允许由 OnTester finalization 证明；                       |
//| OnDeinit fallback 会保留真实 provenance，并将 probe 标为 INVALID。 |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "4.00"
#property strict

input string InpRunTag    = "XMON4";
input string InpInfoSym   = "XAUUSDm";
input string InpMonthFrom = "2018.01.01";
input string InpMonthTo   = "2018.02.01";

int Fh = INVALID_HANDLE;
bool g_finalised = false;
string g_finalizationEvent = "";

void W(const string s)
{
   Print("xmon4: ", s);
   if(Fh != INVALID_HANDLE) FileWrite(Fh, s);
}

string Ts(const datetime t, const int flags = TIME_DATE|TIME_MINUTES)
{
   return (t > 0) ? TimeToString(t, flags) : "";
}

void SeriesBounds(const string sym, string &first, string &last)
{
   datetime f = 0, l = 0;
   SeriesInfoInteger(sym, PERIOD_M30, SERIES_FIRSTDATE, f);
   SeriesInfoInteger(sym, PERIOD_M30, SERIES_LASTBAR_DATE, l);
   first = Ts(f);
   last = Ts(l);
}

void PrintShiftDiagnostics(const string sym, const int n, const datetime a, const datetime b)
{
   string first, last;
   SeriesBounds(sym, first, last);
   W(StringFormat("METHOD_A_DIAG sym=%s iBars=%d requested_from=%s requested_to=%s series_first=%s series_last=%s",
                  sym, n, Ts(a), Ts(b), first, last));

   int shifts[7];
   shifts[0] = 0;
   shifts[1] = 1;
   shifts[2] = 2;
   shifts[3] = n / 2;
   shifts[4] = n - 3;
   shifts[5] = n - 2;
   shifts[6] = n - 1;
   for(int i = 0; i < 7; i++)
   {
      int sh = shifts[i];
      if(sh < 0 || sh >= n) continue;
      W(StringFormat("METHOD_A_DIAG sym=%s shift=%d iTime=%s",
                     sym, sh, Ts(iTime(sym, PERIOD_M30, sh))));
   }
}

// Method A: 真正遍历 iBars + iTime；不得用 CopyTime，不得 break。
int CollectA(const string sym, const datetime a, const datetime b, datetime &out[])
{
   ArrayResize(out, 0);
   int n = iBars(sym, PERIOD_M30);
   if(n <= 0)
   {
      PrintFormat("xmon4: CollectA(%s) iBars=%d err=%d", sym, n, GetLastError());
      return 0;
   }

   for(int shift = 0; shift < n; shift++)
   {
      datetime t = iTime(sym, PERIOD_M30, shift);
      if(t <= 0) continue;
      if(t >= a && t < b)
      {
         int k = ArraySize(out);
         ArrayResize(out, k + 1);
         out[k] = t;
      }
   }

   // 不假设 shift 顺序；最终统一升序，供完整集合比较。
   ArraySort(out);
   int got = ArraySize(out);
   if(got == 0 && n > 0)
      PrintShiftDiagnostics(sym, n, a, b);
   return got;
}

// Method B: 窄范围 CopyTime，再显式按 [a,b) 过滤。
int CollectB(const string sym, const datetime a, const datetime b, datetime &out[])
{
   ArrayResize(out, 0);
   datetime ts[];
   int got = CopyTime(sym, PERIOD_M30, a, (datetime)((long)b - 1), ts);
   if(got <= 0) return 0;

   for(int i = 0; i < got; i++)
   {
      datetime t = ts[i];
      if(t <= 0) continue;
      if(t < a || t >= b) continue;
      int k = ArraySize(out);
      ArrayResize(out, k + 1);
      out[k] = t;
   }
   ArraySort(out);
   return ArraySize(out);
}

void Analyse(const datetime &arr[], const int n, int &dup, int &nonMono, long &checksum)
{
   dup = 0;
   nonMono = 0;
   checksum = 0;
   for(int i = 0; i < n; i++)
   {
      if(i > 0 && arr[i] == arr[i-1]) dup++;
      if(i > 0 && arr[i] < arr[i-1]) nonMono++;
      checksum = (checksum * 1000003 + (long)arr[i]) % 2147483647;
   }
}

bool SetsEqual(const datetime &x[], const int nx, const datetime &y[], const int ny,
               int &dupX, int &dupY)
{
   dupX = 0;
   dupY = 0;
   datetime sx[], sy[];
   ArrayResize(sx, nx);
   ArrayResize(sy, ny);
   ArrayCopy(sx, x, 0, 0, nx);
   ArrayCopy(sy, y, 0, 0, ny);
   ArraySort(sx);
   ArraySort(sy);

   datetime ux[], uy[];
   ArrayResize(ux, 0);
   ArrayResize(uy, 0);
   for(int i = 0; i < nx; i++)
   {
      if(i > 0 && sx[i] == sx[i-1]) { dupX++; continue; }
      int k = ArraySize(ux);
      ArrayResize(ux, k + 1);
      ux[k] = sx[i];
   }
   for(int i = 0; i < ny; i++)
   {
      if(i > 0 && sy[i] == sy[i-1]) { dupY++; continue; }
      int k = ArraySize(uy);
      ArrayResize(uy, k + 1);
      uy[k] = sy[i];
   }
   if(nx != ny) return false;
   if(ArraySize(ux) != ArraySize(uy)) return false;
   for(int i = 0; i < ArraySize(ux); i++)
      if(ux[i] != uy[i]) return false;
   return true;
}

int Intersect(const datetime &x[], const int nx, const datetime &y[], const int ny)
{
   int c = 0, i = 0, j = 0;
   while(i < nx && j < ny)
   {
      if(x[i] == y[j]) { c++; i++; j++; }
      else if(x[i] < y[j]) i++;
      else j++;
   }
   return c;
}

void Finalise(const string event)
{
   if(g_finalised) return;
   g_finalised = true;
   g_finalizationEvent = event;
   W("finalization_event=" + event);

   datetime a = StringToTime(InpMonthFrom);
   datetime b = StringToTime(InpMonthTo);
   datetime ftt = TimeCurrent();
   int ibJ = iBars(_Symbol, PERIOD_M30);
   int ibX = iBars(InpInfoSym, PERIOD_M30);
   string firstJ, lastJ, firstX, lastX;
   SeriesBounds(_Symbol, firstJ, lastJ);
   SeriesBounds(InpInfoSym, firstX, lastX);
   datetime lastBarJ = (ibJ > 0) ? iTime(_Symbol, PERIOD_M30, 0) : 0;

   datetime aJ[], bJ[], aX[], bX[];
   int caJ = 0, cbJ = 0, caX = 0, cbX = 0;
   int dA_J = 0, nA_J = 0, dA_X = 0, nA_X = 0;
   int dB_J = 0, nB_J = 0, dB_X = 0, nB_X = 0;
   long csA_J = 0, csA_X = 0, csB_J = 0, csB_X = 0;
   bool eqJ = false, eqX = false;
   int outside = 0;
   int inter = 0;
   double info = 0.0, common = 0.0;

   if(a > 0 && b > a)
   {
      caJ = CollectA(_Symbol,    a, b, aJ);
      cbJ = CollectB(_Symbol,    a, b, bJ);
      caX = CollectA(InpInfoSym, a, b, aX);
      cbX = CollectB(InpInfoSym, a, b, bX);

      Analyse(aJ, caJ, dA_J, nA_J, csA_J);
      Analyse(aX, caX, dA_X, nA_X, csA_X);
      Analyse(bJ, cbJ, dB_J, nB_J, csB_J);
      Analyse(bX, cbX, dB_X, nB_X, csB_X);

      int ignored1 = 0, ignored2 = 0;
      eqJ = SetsEqual(aJ, caJ, bJ, cbJ, ignored1, ignored2);
      eqX = SetsEqual(aX, caX, bX, cbX, ignored1, ignored2);

      for(int i = 0; i < caJ; i++) if(aJ[i] < a || aJ[i] >= b) outside++;
      for(int i = 0; i < caX; i++) if(aX[i] < a || aX[i] >= b) outside++;
      inter = Intersect(aJ, caJ, aX, caX);
      info = (caJ > 0) ? (100.0 * inter / caJ) : 0.0;
      common = (caX > 0) ? (100.0 * inter / caX) : 0.0;
   }

   string reason = "";
   if(event != "OnTester") reason = "normal_ontester_finalization_missing";
   else if(a <= 0 || b <= 0 || b <= a) reason = "bad_month_range";
   else if(caJ == 0 && ibJ > 0) reason = "methodA_zero_despite_positive_ibars";
   else if(caX == 0 && ibX > 0) reason = "methodA_zero_despite_positive_ibars";
   else if(dA_J != 0 || dA_X != 0 || dB_J != 0 || dB_X != 0) reason = "duplicate_timestamps";
   else if(nA_J != 0 || nA_X != 0 || nB_J != 0 || nB_X != 0) reason = "non_monotonic_timestamps";
   else if(!eqJ) reason = "methodA_methodB_jpy_mismatch";
   else if(!eqX) reason = "methodA_methodB_xau_mismatch";
   else if(outside != 0) reason = "timestamps_outside_month";
   else if(caJ <= 0 || caX <= 0) reason = "empty_month";

   int probeValid = (reason == "") ? 1 : 0;
   string gateA = (probeValid == 1) ? ((common >= 99.0) ? "PASS" : "FAIL") : "INVALID";
   string gateB = (probeValid == 1) ? ((info   >= 90.0) ? "PASS" : "FAIL") : "INVALID";
   W("probe_valid=" + IntegerToString(probeValid));
   W("invalid_reason=" + reason);

   W("month,requested_from,requested_to,probe_valid,invalid_reason,finalization_event,final_tester_time,"
     "JPY_M30_bars,XAU_M30_bars,exact_intersection,info_availability_ratio,common_session_alignment_ratio,"
     "GateA_status,GateB_status,jpy_dup,xau_dup,jpy_non_monotonic,xau_non_monotonic,"
     "first_jpy,last_jpy,first_xau,last_xau,outside_requested_month,"
     "methodA_jpy_count,methodB_jpy_count,methodA_xau_count,methodB_xau_count,"
     "methodA_methodB_jpy_equal,methodA_methodB_xau_equal,csA_jpy,csB_jpy,csA_xau,csB_xau,"
     "server_utc_offset,diagnostic_iBars_jpy,diagnostic_iBars_xau,"
     "series_first_jpy,series_last_jpy,series_first_xau,series_last_xau,diagnostic_last_bar_jpy");
   W(InpRunTag + "," + InpMonthFrom + "," + InpMonthTo + ","
     + IntegerToString(probeValid) + "," + reason + "," + event + ","
     + Ts(ftt, TIME_DATE|TIME_SECONDS) + ","
     + IntegerToString(caJ) + "," + IntegerToString(caX) + "," + IntegerToString(inter) + ","
     + DoubleToString(info, 4) + "," + DoubleToString(common, 4) + ","
     + gateA + "," + gateB + ","
     + IntegerToString(dA_J + dB_J) + "," + IntegerToString(dA_X + dB_X) + ","
     + IntegerToString(nA_J + nB_J) + "," + IntegerToString(nA_X + nB_X) + ","
     + ((caJ > 0) ? Ts(aJ[0]) : "") + ","
     + ((caJ > 0) ? Ts(aJ[caJ-1]) : "") + ","
     + ((caX > 0) ? Ts(aX[0]) : "") + ","
     + ((caX > 0) ? Ts(aX[caX-1]) : "") + ","
     + IntegerToString(outside) + ","
     + IntegerToString(caJ) + "," + IntegerToString(cbJ) + ","
     + IntegerToString(caX) + "," + IntegerToString(cbX) + ","
     + (eqJ ? "1" : "0") + "," + (eqX ? "1" : "0") + ","
     + IntegerToString(csA_J) + "," + IntegerToString(csB_J) + ","
     + IntegerToString(csA_X) + "," + IntegerToString(csB_X) + ","
     + IntegerToString((int)((long)ftt - (long)TimeGMT())) + ","
     + IntegerToString(ibJ) + "," + IntegerToString(ibX) + ","
     + firstJ + "," + lastJ + "," + firstX + "," + lastX + "," + Ts(lastBarJ));
}

void OnInit()
{
   string dir = "dshtrend\\XAMR30MON4";
   FolderCreate("dshtrend", FILE_COMMON);
   FolderCreate(dir, FILE_COMMON);
   Fh = FileOpen(dir + "\\m4_" + InpRunTag + ".txt",
                 FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(Fh == INVALID_HANDLE)
      Fh = FileOpen(dir + "\\m4_" + InpRunTag + ".txt", FILE_WRITE|FILE_TXT|FILE_ANSI);
}

void OnTick() { /* v4 只在 OnTester 结束时统计。 */ }

double OnTester()
{
   Finalise("OnTester");
   if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
   return 0.0;
}

void OnDeinit(const int reason)
{
   if(!g_finalised)
      Finalise("OnDeinitFallback");
   if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
}
//+------------------------------------------------------------------+
