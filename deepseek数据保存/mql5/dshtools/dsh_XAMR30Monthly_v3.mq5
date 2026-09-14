//+------------------------------------------------------------------+
//|  dsh_XAMR30Monthly_v3.mq5 — 单月双品种 M30 数据资格探针 (v3)       |
//|                                                                  |
//|  ★v3 修复 v2 的 probe-timing bug：                                |
//|    v2 在【首个 tick】就 finalise 整个月统计，而那时 Tester 才处于   |
//|    测试起点（tester_time = month_start），未来一个月的 bars 尚未    |
//|    进入 tester timeline → JPY=1。                                 |
//|    v3 改为【OnTester() 结束时 finalise】——测试已完整跑完 requested  |
//|    month 后才统计。                                               |
//|                                                                  |
//|  ★v3 使用双方法独立取数并比对完整 timestamp 集合：                  |
//|    Method A: iBars + iTime（遍历整个 series，按 [a,b) 过滤）        |
//|    Method B: CopyTime(a, b-1s)（再显式过滤）                       |
//|    两者 timestamp 集合必须完全一致，否则 probe_invalid。            |
//|                                                                  |
//|  ★probe failure ≠ market data failure：                            |
//|    probe_valid=0 时 Gate 状态写 INVALID，绝不自动写 FAIL。          |
//|                                                                  |
//|  ★旧 v2 保留为 invalid_probe_timing / retained_for_provenance      |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "3.00"
#property strict

input string InpRunTag    = "XMON3";
input string InpInfoSym   = "XAUUSDm";
input string InpMonthFrom = "2018.01.01";
input string InpMonthTo   = "2018.02.01";

int Fh = INVALID_HANDLE;
void W(const string s) { Print("xmon3: ", s); if(Fh != INVALID_HANDLE) FileWrite(Fh, s); }

// ---- 双方法取数 ----
// Method A: 遍历 iBars + iTime，按 [a,b) 硬过滤
int CollectA(const string sym, datetime a, datetime b, datetime &out[])
{
   ArrayResize(out, 0);
   // ★v3b：原实现用 iBars+iTime 遍历，实测恒返回 0
   //   （同时 iBars=13536、CopyTime 全范围=13536 均正常 → 是遍历逻辑 bug，非 Tester 限制）
   //   改为「全范围 CopyTime + 显式索引过滤」，
   //   与 Method B（窄范围 CopyTime + 时间过滤）在实现路径上仍独立。
   datetime all[];
   int got = CopyTime(sym, PERIOD_M30, (datetime)0, (datetime)2147483647, all);
   if(got <= 0)
   {
      PrintFormat("xmon3: CollectA CopyTime(%s) full = %d err=%d", sym, got, GetLastError());
      return 0;
   }
   int k = 0;
   for(int i = got - 1; i >= 0; i--)          // CopyTime 升序；由新到旧
   {
      datetime t = all[i];
      if(t <= 0) continue;
      if(t >= b) continue;                    // 超上界：跳过
      if(t < a)  break;                       // 更早的一律排除
      ArrayResize(out, k + 1);
      out[k] = t; k++;
   }
   // 反转为升序，便于集合比对
   for(int i = 0, j = k - 1; i < j; i++, j--)
   { datetime tmp = out[i]; out[i] = out[j]; out[j] = tmp; }
   return k;
}

// Method B: CopyTime，再显式过滤
int CollectB(const string sym, datetime a, datetime b, datetime &out[])
{
   ArrayResize(out, 0);
   datetime ts[];
   int got = CopyTime(sym, PERIOD_M30, a, (datetime)((long)b - 1), ts);
   if(got <= 0) return 0;
   int k = 0;
   for(int i = 0; i < got; i++)
   {
      datetime t = ts[i];
      if(t <= 0) continue;
      if(t < a || t >= b) continue;         // ★不依赖 CopyTime 边界语义
      ArrayResize(out, k + 1);
      out[k] = t; k++;
   }
   return k;
}

// 统计辅助：dup / non-monotonic / checksum
void Analyse(const datetime &arr[], int n, int &dup, int &nonMono, long &checksum)
{
   dup = 0; nonMono = 0; checksum = 0;
   for(int i = 0; i < n; i++)
   {
      if(i > 0 && arr[i] == arr[i-1]) dup++;
      if(i > 0 && arr[i] <  arr[i-1]) nonMono++;
      checksum = (checksum * 1000003 + (long)arr[i]) % 2147483647;
   }
}

bool SetsEqual(const datetime &x[], int nx, const datetime &y[], int ny, int &dupX, int &dupY)
{
   dupX = 0; dupY = 0;
   // 去重后比较（用简单 O(n^2) 在 n~3000 时可接受；实际先排序去重）
   datetime sx[], sy[];
   ArrayResize(sx, nx); ArrayCopy(sx, x, 0, 0, nx);
   ArrayResize(sy, ny); ArrayCopy(sy, y, 0, 0, ny);
   ArraySort(sx); ArraySort(sy);
   int ix = 0, iy = 0;
   // 去重
   datetime ux[], uy[];
   ArrayResize(ux, 0); ArrayResize(uy, 0);
   for(int i = 0; i < nx; i++)
   { if(i > 0 && sx[i] == sx[i-1]) { dupX++; continue; } int k=ArraySize(ux); ArrayResize(ux,k+1); ux[k]=sx[i]; }
   for(int i = 0; i < ny; i++)
   { if(i > 0 && sy[i] == sy[i-1]) { dupY++; continue; } int k=ArraySize(uy); ArrayResize(uy,k+1); uy[k]=sy[i]; }
   if(ArraySize(ux) != ArraySize(uy)) return false;
   for(int i = 0; i < ArraySize(ux); i++) if(ux[i] != uy[i]) return false;
   return true;
}

// 交集（两边均已升序去重）
int Intersect(const datetime &x[], int nx, const datetime &y[], int ny)
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

// ================= 仅在测试完整结束后统计 =================
void Finalise()
{
   datetime a = StringToTime(InpMonthFrom);
   datetime b = StringToTime(InpMonthTo);
   if(a <= 0 || b <= 0 || b <= a)
   { W("probe_valid=0"); W("invalid_reason=bad_month_range"); return; }

   datetime ftt = TimeCurrent();
   // ★自证：iBars / SeriesInfo 在 OnTester 上下文中的可用性
   int ibJ0 = iBars(_Symbol, PERIOD_M30);
   int ibX0 = iBars(InpInfoSym, PERIOD_M30);
   W(StringFormat("SELFTEST iBars jpy=%d xau=%d", ibJ0, ibX0));
   {
      datetime t1 = 0, t2 = 0;
      SeriesInfoInteger(_Symbol, PERIOD_M30, SERIES_FIRSTDATE, t1);
      SeriesInfoInteger(_Symbol, PERIOD_M30, SERIES_LASTBAR_DATE, t2);
      W(StringFormat("SELFTEST series jpy=[%s .. %s]",
                     (t1>0?TimeToString(t1,TIME_DATE|TIME_MINUTES):"none"),
                     (t2>0?TimeToString(t2,TIME_DATE|TIME_MINUTES):"none")));
      datetime x1 = 0, x2 = 0;
      SeriesInfoInteger(InpInfoSym, PERIOD_M30, SERIES_FIRSTDATE, x1);
      SeriesInfoInteger(InpInfoSym, PERIOD_M30, SERIES_LASTBAR_DATE, x2);
      W(StringFormat("SELFTEST series xau=[%s .. %s]",
                     (x1>0?TimeToString(x1,TIME_DATE|TIME_MINUTES):"none"),
                     (x2>0?TimeToString(x2,TIME_DATE|TIME_MINUTES):"none")));
      datetime probe[]; int gA = CopyTime(_Symbol, PERIOD_M30, (datetime)0, ftt, probe);
      W(StringFormat("SELFTEST CopyTime(full range) jpy=%d", gA));
   }

   // ---- Method A / B ----
   datetime aJ[], bJ[], aX[], bX[];
   int caJ = CollectA(_Symbol,    a, b, aJ);
   int cbJ = CollectB(_Symbol,    a, b, bJ);
   int caX = CollectA(InpInfoSym, a, b, aX);
   int cbX = CollectB(InpInfoSym, a, b, bX);

   int dA_J, nA_J, dA_X, nA_X, dB_J, nB_J, dB_X, nB_X;
   long csA_J, csA_X, csB_J, csB_X;
   Analyse(aJ, caJ, dA_J, nA_J, csA_J);
   Analyse(aX, caX, dA_X, nA_X, csA_X);
   Analyse(bJ, cbJ, dB_J, nB_J, csB_J);
   Analyse(bX, cbX, dB_X, nB_X, csB_X);

   int ddJ, ddX;
   bool eqJ = SetsEqual(aJ, caJ, bJ, cbJ, ddJ, ddX);
   int d2J, d2X;
   bool eqX = SetsEqual(aX, caX, bX, cbX, d2J, d2X);

   // 以 Method A 为准（两法一致时等价）
   int nj = caJ, nx = caX;
   int dupJ = dA_J, dupX = dA_X;
   int nmJ  = nA_J, nmX  = nA_X;

   // outside 检查
   int outside = 0;
   for(int i = 0; i < nj; i++) if(aJ[i] < a || aJ[i] >= b) outside++;
   for(int i = 0; i < nx; i++) if(aX[i] < a || aX[i] >= b) outside++;

   int inter = Intersect(aJ, nj, aX, nx);

   double info   = (nj > 0) ? (100.0 * inter / nj) : 0.0;
   double common = (nx > 0) ? (100.0 * inter / nx) : 0.0;

   // ---- probe_valid 判定 ----
   // 测试确实走到 requested month 末尾
   datetime lastBarJ = (iBars(_Symbol, PERIOD_M30) > 0) ? iTime(_Symbol, PERIOD_M30, 0) : 0;
   bool reachedEnd = (ftt >= (datetime)((long)b - 86400));   // 测试结束时间已进入该月末日
   string reason = "";
   if(!reachedEnd)                                  reason = "test_did_not_reach_month_end";
   else if(!eqJ)                                    reason = "methodA_methodB_jpy_mismatch";
   else if(!eqX)                                    reason = "methodA_methodB_xau_mismatch";
   else if(outside != 0)                            reason = "timestamps_outside_month";
   else if(dupJ != 0 || dupX != 0)                  reason = "duplicate_timestamps";
   else if(nmJ != 0 || nmX != 0)                    reason = "non_monotonic_timestamps";
   else if(nj <= 0 || nx <= 0)                      reason = "empty_month";
   int probeValid = (reason == "") ? 1 : 0;

   // ---- 输出 ----
   W("month,requested_from,requested_to,probe_valid,invalid_reason,finalization_event,final_tester_time,"
     "JPY_M30_bars,XAU_M30_bars,exact_intersection,info_availability_ratio,common_session_alignment_ratio,"
     "GateA_status,GateB_status,"
     "jpy_dup,xau_dup,jpy_non_monotonic,xau_non_monotonic,"
     "first_jpy,last_jpy,first_xau,last_xau,outside_requested_month,"
     "methodA_jpy_count,methodB_jpy_count,methodA_xau_count,methodB_xau_count,"
     "methodA_methodB_jpy_equal,methodA_methodB_xau_equal,"
     "csA_jpy,csB_jpy,csA_xau,csB_xau,server_utc_offset");
   string gA = (probeValid == 1) ? ((common >= 99.0) ? "PASS" : "FAIL") : "INVALID";
   string gB = (probeValid == 1) ? ((info   >= 90.0) ? "PASS" : "FAIL") : "INVALID";
   W(InpRunTag + "," + InpMonthFrom + "," + InpMonthTo + ","
     + IntegerToString(probeValid) + "," + reason + ",OnTester,"
     + TimeToString(ftt, TIME_DATE|TIME_SECONDS) + ","
     + IntegerToString(nj) + "," + IntegerToString(nx) + "," + IntegerToString(inter) + ","
     + DoubleToString(info, 4) + "," + DoubleToString(common, 4) + ","
     + gA + "," + gB + ","
     + IntegerToString(dupJ) + "," + IntegerToString(dupX) + ","
     + IntegerToString(nmJ) + "," + IntegerToString(nmX) + ","
     + ((nj > 0) ? TimeToString(aJ[0], TIME_DATE|TIME_MINUTES) : "") + ","
     + ((nj > 0) ? TimeToString(aJ[nj-1], TIME_DATE|TIME_MINUTES) : "") + ","
     + ((nx > 0) ? TimeToString(aX[0], TIME_DATE|TIME_MINUTES) : "") + ","
     + ((nx > 0) ? TimeToString(aX[nx-1], TIME_DATE|TIME_MINUTES) : "") + ","
     + IntegerToString(outside) + ","
     + IntegerToString(caJ) + "," + IntegerToString(cbJ) + ","
     + IntegerToString(caX) + "," + IntegerToString(cbX) + ","
     + (eqJ ? "1" : "0") + "," + (eqX ? "1" : "0") + ","
     + IntegerToString((long)csA_J) + "," + IntegerToString((long)csB_J) + ","
     + IntegerToString((long)csA_X) + "," + IntegerToString((long)csB_X) + ","
     + IntegerToString((int)((long)ftt - (long)TimeGMT())));
}

void OnInit()
{
   string dir = "dshtrend\\XAMR30MON3";
   FolderCreate("dshtrend", FILE_COMMON);
   FolderCreate(dir, FILE_COMMON);
   Fh = FileOpen(dir + "\\m3_" + InpRunTag + ".txt",
                 FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(Fh == INVALID_HANDLE)
      Fh = FileOpen(dir + "\\m3_" + InpRunTag + ".txt", FILE_WRITE|FILE_TXT|FILE_ANSI);
}

void OnTick() { /* ★v3：不在 tick 阶段统计，只等 OnTester */ }

double OnTester()
{
   Finalise();
   if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
   return 0.0;
}

void OnDeinit(const int reason)
{
   // 若 OnTester 未被调用（异常路径），补一次
   if(Fh != INVALID_HANDLE)
   {
      Finalise();
      if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
   }
}
//+------------------------------------------------------------------+


