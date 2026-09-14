//+------------------------------------------------------------------+
//|  dsh_XAMR30Monthly.mq5 — 单月双品种 M30 数据资格探针 (v2)          |
//|                                                                  |
//|  ★v2 修复：改用 CopyTime(sym, PERIOD_M30, a, b, arr) 按区间取数，  |
//|    而不是"遍历 iBars + iTime"。                                   |
//|    v1 缺陷：每月的 JPY_M30_bars 恒为 1，与测试器日志的             |
//|    "1098 bars generated" 直接冲突（一个月不可能只有 1 根 M30）。    |
//|  ★自带自证日志：打印 iBars / CopyTime 结果 / 首末 bar。            |
//|                                                                  |
//|  ★回归基准：2023.01 窗口的正确值应为 JPY=12477 / XAU=11817         |
//|    （由 dsh_XAMR30Align2 独立测得）                                |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "2.00"
#property strict

input string InpRunTag    = "XMON";
input string InpInfoSym   = "XAUUSDm";
input string InpMonthFrom = "2018.01.01";
input string InpMonthTo   = "2018.02.01";

int Fh = INVALID_HANDLE;
void W(const string s) { Print("xmon: ", s); if(Fh != INVALID_HANDLE) FileWrite(Fh, s); }

void OnInit()
{
   string dir = "dshtrend\\XAMR30MON";
   FolderCreate("dshtrend", FILE_COMMON);
   FolderCreate(dir, FILE_COMMON);
   Fh = FileOpen(dir + "\\m_" + InpRunTag + ".txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(Fh == INVALID_HANDLE)
      Fh = FileOpen(dir + "\\m_" + InpRunTag + ".txt", FILE_WRITE|FILE_TXT|FILE_ANSI);
}

// ★按 [a,b) 直接取该品种的 M30 open timestamps（升序）
//   返回取得的根数；dup / non-monotonic 在此判定
int CollectRange(const string sym, datetime a, datetime b, datetime &out[],
                 int &dupCount, int &nonMonoCount)
{
   dupCount = 0; nonMonoCount = 0;
   ArrayResize(out, 0);

   datetime ts[];
   // CopyTime(符号, 周期, 起始, 结束, 数组) → 返回 [a,b) 内的 bar 时间
   int got = CopyTime(sym, PERIOD_M30, a, b, ts);
   if(got <= 0)
   {
      int err = GetLastError();
      PrintFormat("xmon: CopyTime(%s, M30, %s, %s) = %d err=%d",
                  sym, TimeToString(a, TIME_DATE), TimeToString(b, TIME_DATE), got, err);
      return 0;
   }
   ArrayResize(out, got);
   int k = 0;
   datetime prev = 0;
   for(int i = 0; i < got; i++)
   {
      datetime t = ts[i];
      if(t <= 0) continue;
      // 硬过滤：只接受 [a,b)
      if(t < a || t >= b) continue;
      if(k > 0 && out[k-1] == t) { dupCount++; continue; }
      if(k > 0 && t < out[k-1]) nonMonoCount++;
      out[k] = t; k++;
      prev = t;
   }
   ArrayResize(out, k);
   return k;
}

void OnTick()
{
   // ★v2.1：首次 OnTick 时 M30 序列尚未加载完（只有 1 根），
   //   必须等到序列就绪再取数。用 tick 计数重试，最多 InpMaxWaitTicks 次。
   static int tries = 0;
   static bool done = false;
   if(done) return;
   tries++;
   int ibNowJ = iBars(_Symbol, PERIOD_M30);
   int ibNowX = iBars(InpInfoSym, PERIOD_M30);
   // 就绪判据：两品种都拿到足够多 bar，且首根 bar 时间不晚于窗口起点
   datetime firstJ = (ibNowJ > 0) ? iTime(_Symbol, PERIOD_M30, ibNowJ - 1) : 0;
   datetime firstX = (ibNowX > 0) ? iTime(InpInfoSym, PERIOD_M30, ibNowX - 1) : 0;
   datetime wA = StringToTime(InpMonthFrom);
   bool ready = (ibNowJ > 100 && ibNowX > 100 && firstJ > 0 && firstJ <= wA);
   if(!ready && tries < 4000) return;       // 继续等
   done = true;

   datetime a = StringToTime(InpMonthFrom);
   datetime b = StringToTime(InpMonthTo);
   if(a <= 0 || b <= 0 || b <= a) { W("bad month range"); if(Fh!=INVALID_HANDLE) FileClose(Fh); return; }

   // ---- 自证日志 ----
   int ibJ = iBars(_Symbol, PERIOD_M30);
   int ibX = iBars(InpInfoSym, PERIOD_M30);
   W(StringFormat("SELFTEST run=%s window=[%s, %s)", InpRunTag,
                  TimeToString(a, TIME_DATE), TimeToString(b, TIME_DATE)));
   W(StringFormat("SELFTEST tries=%d iBars: jpy=%d xau=%d", tries, ibJ, ibX));
   datetime sj = 0, lj = 0, sx = 0, lx = 0;
   SeriesInfoInteger(_Symbol,   PERIOD_M30, SERIES_FIRSTDATE,    sj);
   SeriesInfoInteger(_Symbol,   PERIOD_M30, SERIES_LASTBAR_DATE, lj);
   SeriesInfoInteger(InpInfoSym, PERIOD_M30, SERIES_FIRSTDATE,    sx);
   SeriesInfoInteger(InpInfoSym, PERIOD_M30, SERIES_LASTBAR_DATE, lx);
   W(StringFormat("SELFTEST series: jpy=[%s .. %s]  xau=[%s .. %s]",
                  TimeToString(sj, TIME_DATE|TIME_MINUTES), TimeToString(lj, TIME_DATE|TIME_MINUTES),
                  TimeToString(sx, TIME_DATE|TIME_MINUTES), TimeToString(lx, TIME_DATE|TIME_MINUTES)));
   W(StringFormat("SELFTEST tester_time=%s  server_minus_GMT=%d",
                  TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
                  (int)((long)TimeCurrent() - (long)TimeGMT())));

   // ---- 取数 ----
   datetime jpyTs[], xauTs[];
   int jd = 0, jn = 0, xd = 0, xn = 0;
   int nj = CollectRange(_Symbol,   a, b, jpyTs, jd, jn);
   int nx = CollectRange(InpInfoSym, a, b, xauTs, xd, xn);
   W(StringFormat("SELFTEST collected: jpy=%d xau=%d", nj, nx));

   // exact intersection（双指针；两边均升序）
   int inter = 0, i = 0, j = 0;
   while(i < nj && j < nx)
   {
      if(jpyTs[i] == xauTs[j]) { inter++; i++; j++; }
      else if(jpyTs[i] < xauTs[j]) i++;
      else j++;
   }

   int outside = 0;
   for(int k = 0; k < nj; k++) if(jpyTs[k] < a || jpyTs[k] >= b) outside++;
   for(int k = 0; k < nx; k++) if(xauTs[k] < a || xauTs[k] >= b) outside++;

   double info   = (nj > 0) ? (100.0 * inter / nj) : 0.0;
   double common = (nx > 0) ? (100.0 * inter / nx) : 0.0;

   W("month,requested_from,requested_to,JPY_M30_bars,XAU_M30_bars,exact_intersection,"
     "info_availability_ratio,common_session_alignment_ratio,"
     "jpy_dup_ts,xau_dup_ts,jpy_non_monotonic,xau_non_monotonic,"
     "first_jpy,last_jpy,first_xau,last_xau,"
     "counted_outside_requested_month,server_utc_offset");
   W(InpRunTag + "," + InpMonthFrom + "," + InpMonthTo + ","
     + IntegerToString(nj) + "," + IntegerToString(nx) + "," + IntegerToString(inter) + ","
     + DoubleToString(info, 4) + "," + DoubleToString(common, 4) + ","
     + IntegerToString(jd) + "," + IntegerToString(xd) + ","
     + IntegerToString(jn) + "," + IntegerToString(xn) + ","
     + ((nj > 0) ? TimeToString(jpyTs[0], TIME_DATE|TIME_MINUTES) : "") + ","
     + ((nj > 0) ? TimeToString(jpyTs[nj-1], TIME_DATE|TIME_MINUTES) : "") + ","
     + ((nx > 0) ? TimeToString(xauTs[0], TIME_DATE|TIME_MINUTES) : "") + ","
     + ((nx > 0) ? TimeToString(xauTs[nx-1], TIME_DATE|TIME_MINUTES) : "") + ","
     + IntegerToString(outside) + ","
     + IntegerToString((int)((long)TimeCurrent() - (long)TimeGMT())));

   if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
}

void OnDeinit(const int reason) { if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; } }
//+------------------------------------------------------------------+

