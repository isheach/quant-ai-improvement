//+------------------------------------------------------------------+
//|  dsh_XAMR30Align3.mq5 — 缺失时间戳分布诊断                        |
//|                                                                  |
//|  逐根比较两个品种的 M30 open timestamp，输出：                      |
//|    · 首个 MISS 的时间戳（从最新往回）                              |
//|    · 连续 MISS 段的数量与最长段                                    |
//|    · MISS 是否全部位于 XAU 数据末端之后（= 缓存/同步问题）           |
//|    · 若 MISS 出现在中间 → 真缺口                                    |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property strict

input string InpRunTag  = "AL3";
input string InpInfoSym = "XAUUSDm";
input int    InpMaxScan = 60000;

int Fh = INVALID_HANDLE;
void W(const string s) { Print("al3: ", s); if(Fh != INVALID_HANDLE) FileWrite(Fh, s); }

void OnInit()
{
   string dir = "dshtrend\\XAMR30ALIGN";
   FolderCreate("dshtrend", FILE_COMMON); FolderCreate(dir, FILE_COMMON);
   Fh = FileOpen(dir + "\\align3_" + InpRunTag + ".txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(Fh == INVALID_HANDLE) Fh = FileOpen(dir + "\\align3_" + InpRunTag + ".txt", FILE_WRITE|FILE_TXT|FILE_ANSI);
}

void OnTick()
{
   static bool done = false; if(done) return; done = true;

   W("=== dsh_XAMR30Align3 ===");
   W("run_tag=" + InpRunTag + "  jpy=" + _Symbol + "  xau=" + InpInfoSym);
   W("tester_time=" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));

   int nJ = iBars(_Symbol, PERIOD_M30), nX = iBars(InpInfoSym, PERIOD_M30);
   W(StringFormat("M30 bars jpy=%d xau=%d", nJ, nX));
   if(nJ <= 0 || nX <= 0) { if(Fh!=INVALID_HANDLE) FileClose(Fh); return; }

   datetime jf = iTime(_Symbol, PERIOD_M30, nJ-1), jl = iTime(_Symbol, PERIOD_M30, 0);
   datetime xf = iTime(InpInfoSym, PERIOD_M30, nX-1), xl = iTime(InpInfoSym, PERIOD_M30, 0);
   W("jpy " + TimeToString(jf, TIME_DATE|TIME_MINUTES) + " ~ " + TimeToString(jl, TIME_DATE|TIME_MINUTES));
   W("xau " + TimeToString(xf, TIME_DATE|TIME_MINUTES) + " ~ " + TimeToString(xl, TIME_DATE|TIME_MINUTES));
   W("XAU 结束时间早于 JPY: " + IntegerToString((int)((long)jl - (long)xl) / 60) + " 分钟");
   W("");

   datetime a = (jf > xf) ? jf : xf;
   datetime b = (jl < xl) ? jl : xl;

   int scan=0, jpyIn=0, match=0, miss=0;
   int runs=0, maxRun=0, curRun=0;
   datetime firstMiss = 0, lastMiss = 0;
   int missBeforeXauEnd = 0;   // MISS 且 jt <= xl  → 位于 XAU 覆盖范围内 = 真缺口
   int missAfterXauEnd  = 0;   // MISS 且 jt >  xl  → 超出 XAU 覆盖 = 缓存/同步

   for(int i = 0; i < nJ && scan < InpMaxScan; i++)
   {
      datetime jt = iTime(_Symbol, PERIOD_M30, i);
      if(jt < a || jt > b) continue;
      scan++; jpyIn++;
      int sx = iBarShift(InpInfoSym, PERIOD_M30, jt, false);
      bool ok = false;
      if(sx >= 0 && sx < nX) { if(iTime(InpInfoSym, PERIOD_M30, sx) == jt) ok = true; }
      if(ok) { match++; curRun = 0; }
      else
      {
         miss++; curRun++;
         if(curRun > maxRun) maxRun = curRun;
         if(curRun == 1) runs++;
         if(firstMiss == 0) firstMiss = jt;
         lastMiss = jt;
         if(jt <= xl) missBeforeXauEnd++; else missAfterXauEnd++;
      }
   }
   double ar = (jpyIn>0) ? 100.0*match/jpyIn : 0.0;
   W(StringFormat("SUMMARY scanned=%d match=%d miss=%d alignment=%.4f%%", jpyIn, match, miss, ar));
   W(StringFormat("miss_runs=%d max_consecutive_miss=%d", runs, maxRun));
   W("first_miss(newest)=" + (firstMiss>0?TimeToString(firstMiss,TIME_DATE|TIME_MINUTES):"none"));
   W("last_miss(oldest) =" + (lastMiss>0?TimeToString(lastMiss,TIME_DATE|TIME_MINUTES):"none"));
   W(StringFormat("miss_within_xau_coverage=%d  miss_beyond_xau_end=%d", missBeforeXauEnd, missAfterXauEnd));
   W("");
   if(missBeforeXauEnd == 0)
      W("VERDICT: 所有 MISS 都在 XAU 数据末端之后 → 属【缓存/同步滞后】，非真缺口");
   else
      W("VERDICT: XAU 覆盖范围内存在 MISS → 【真缺口】，跨品种对齐不可靠");
   W("done");
   if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
}

void OnDeinit(const int reason) { if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; } }
//+------------------------------------------------------------------+
