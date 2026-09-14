//+------------------------------------------------------------------+
//|  dsh_XAMR30Align2.mq5 — 单月双品种 M30 exact 对齐（逐根判定）      |
//|                                                                  |
//|  在一个短窗口内（例如 1 个月），逐根比较 USDJPYm 与 XAUUSDm 的     |
//|  M30 open timestamp，输出：                                       |
//|    · 双方各有多少根                                               |
//|    · exact timestamp 交集数                                       |
//|    · 缺失的时间戳样例（前若干）                                    |
//|  这能区分「真缺 bar」与「探针统计口径问题」。                       |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property strict

input string InpRunTag  = "AL2";
input string InpInfoSym = "XAUUSDm";

int Fh = INVALID_HANDLE;
void W(const string s) { Print("al2: ", s); if(Fh != INVALID_HANDLE) FileWrite(Fh, s); }

void OnInit()
{
   string dir = "dshtrend\\XAMR30ALIGN";
   FolderCreate("dshtrend", FILE_COMMON);
   FolderCreate(dir, FILE_COMMON);
   Fh = FileOpen(dir + "\\align2_" + InpRunTag + ".txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(Fh == INVALID_HANDLE)
      Fh = FileOpen(dir + "\\align2_" + InpRunTag + ".txt", FILE_WRITE|FILE_TXT|FILE_ANSI);
}

void OnTick()
{
   static bool done = false;
   if(done) return;
   done = true;

   W("=== dsh_XAMR30Align2 ===");
   W("run_tag=" + InpRunTag);
   W("jpy=" + _Symbol + "  xau=" + InpInfoSym);
   W("server_minus_GMT_sec=" + IntegerToString((int)((long)TimeCurrent() - (long)TimeGMT())));
   W("tester_time=" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));

   int nJ = iBars(_Symbol, PERIOD_M30);
   int nX = iBars(InpInfoSym, PERIOD_M30);
   W(StringFormat("M30 bars: jpy=%d xau=%d", nJ, nX));
   if(nJ <= 0 || nX <= 0) { W("!! 缺 bar"); if(Fh!=INVALID_HANDLE) FileClose(Fh); return; }

   datetime jf = iTime(_Symbol, PERIOD_M30, nJ-1), jl = iTime(_Symbol, PERIOD_M30, 0);
   datetime xf = iTime(InpInfoSym, PERIOD_M30, nX-1), xl = iTime(InpInfoSym, PERIOD_M30, 0);
   W("jpy range: " + TimeToString(jf, TIME_DATE|TIME_MINUTES) + " ~ " + TimeToString(jl, TIME_DATE|TIME_MINUTES));
   W("xau range: " + TimeToString(xf, TIME_DATE|TIME_MINUTES) + " ~ " + TimeToString(xl, TIME_DATE|TIME_MINUTES));

   // 交集窗口
   datetime a = (jf > xf) ? jf : xf;
   datetime b = (jl < xl) ? jl : xl;
   W("overlap  : " + TimeToString(a, TIME_DATE|TIME_MINUTES) + " ~ " + TimeToString(b, TIME_DATE|TIME_MINUTES));

   // ★限制扫描量：只扫交集窗口内最近 InpMaxScan 根
   int scan = 0;
   int jpyIn = 0, match = 0, miss = 0;
   int shown = 0;
   W("");
   W("--- per-bar check (jpy bars inside overlap, newest first, capped) ---");
   for(int i = 0; i < nJ && scan < 20000; i++)
   {
      datetime jt = iTime(_Symbol, PERIOD_M30, i);
      if(jt < a || jt > b) continue;
      scan++; jpyIn++;
      int sx = iBarShift(InpInfoSym, PERIOD_M30, jt, false);
      bool ok = false;
      if(sx >= 0 && sx < nX) { datetime xt = iTime(InpInfoSym, PERIOD_M30, sx); if(xt == jt) ok = true; }
      if(ok) match++;
      else
      {
         miss++;
         if(shown < 12)
         {
            W("  MISS jpy_ts=" + TimeToString(jt, TIME_DATE|TIME_MINUTES));
            shown++;
         }
      }
   }
   W("");
   double ar = (jpyIn > 0) ? (100.0 * match / jpyIn) : 0.0;
   W(StringFormat("SUMMARY jpy_bars_in_overlap=%d match=%d miss=%d alignment_ratio=%.4f%%",
                  jpyIn, match, miss, ar));
   W("done");
   if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
}

void OnDeinit(const int reason) { if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; } }
//+------------------------------------------------------------------+
