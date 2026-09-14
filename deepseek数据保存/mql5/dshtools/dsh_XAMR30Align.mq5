//+------------------------------------------------------------------+
//|  dsh_XAMR30Align.mq5 — 双品种 M30 时间戳对齐探针（Tester-only）    |
//|                                                                  |
//|  在 Strategy Tester 内对真实 USDJPYm 运行，逐月统计：              |
//|    · USDJPY M30 bar 数                                            |
//|    · XAUUSDm M30 bar 数                                           |
//|    · 两者 exact timestamp 交集数                                   |
//|    · alignment_ratio = intersection / USDJPY_M30_bars             |
//|                                                                  |
//|  ★只读：不下单、不交易、不建自建品种。                              |
//|  输出：Common\Files\dshtrend\XAMR30ALIGN\align_<tag>.txt           |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property strict

input string InpRunTag    = "ALIGN";
input string InpInfoSym   = "XAUUSDm";
input int    InpMaxMonths = 90;

int Fh = INVALID_HANDLE;

void W(const string s)
{
   Print("align: ", s);
   if(Fh != INVALID_HANDLE) FileWrite(Fh, s);
}

void OnInit()
{
   string dir = "dshtrend\\XAMR30ALIGN";
   FolderCreate("dshtrend", FILE_COMMON);
   FolderCreate(dir, FILE_COMMON);
   Fh = FileOpen(dir + "\\align_" + InpRunTag + ".txt",
                 FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(Fh == INVALID_HANDLE)
      Fh = FileOpen(dir + "\\align_" + InpRunTag + ".txt",
                    FILE_WRITE|FILE_TXT|FILE_ANSI);
}

void OnTick()
{
   static bool done = false;
   if(done) return;
   done = true;

   W("=== dsh_XAMR30Align ===");
   W("run_tag=" + InpRunTag);
   W("trade_symbol=" + _Symbol);
   W("info_symbol=" + InpInfoSym);
   W("server=" + AccountInfoString(ACCOUNT_SERVER));
   W("build=" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)));
   W("server_minus_GMT_sec=" + IntegerToString((int)((long)TimeCurrent() - (long)TimeGMT())));
   W("");

   int nJ = iBars(_Symbol, PERIOD_M30);
   int nX = iBars(InpInfoSym, PERIOD_M30);
   W(StringFormat("M30 bars: %s=%d  %s=%d", _Symbol, nJ, InpInfoSym, nX));
   if(nJ > 0)
      W("JPY M30 first=" + TimeToString(iTime(_Symbol, PERIOD_M30, nJ-1), TIME_DATE|TIME_MINUTES)
        + " last=" + TimeToString(iTime(_Symbol, PERIOD_M30, 0), TIME_DATE|TIME_MINUTES));
   if(nX > 0)
      W("XAU M30 first=" + TimeToString(iTime(InpInfoSym, PERIOD_M30, nX-1), TIME_DATE|TIME_MINUTES)
        + " last=" + TimeToString(iTime(InpInfoSym, PERIOD_M30, 0), TIME_DATE|TIME_MINUTES));
   W("");

   if(nJ <= 0 || nX <= 0) { W("!! 某品种无 M30 bar"); if(Fh!=INVALID_HANDLE) FileClose(Fh); return; }

   // 收集 XAU 的 M30 时间戳到集合（用简单数组 + 排序后二分；此处量级 <300k，用线性+哈希图不便，
   //  改为：对每个 JPY bar 用 iBarShift 精确匹配）
   W("month | jpy_m30 | xau_match | align_ratio");
   datetime jpyFirst = iTime(_Symbol, PERIOD_M30, nJ - 1);
   datetime jpyLast  = iTime(_Symbol, PERIOD_M30, 0);

   // 逐月
   MqlDateTime s; TimeToStruct(jpyFirst, s);
   int y = s.year, mo = s.mon;
   int guard = 0;
   while(guard++ < InpMaxMonths)
   {
      datetime mFrom = StringToTime(StringFormat("%04d.%02d.01 00:00", y, mo));
      int ny = y, nmo = mo + 1; if(nmo > 12) { nmo = 1; ny++; }
      datetime mTo = StringToTime(StringFormat("%04d.%02d.01 00:00", ny, nmo));
      if(mFrom > jpyLast) break;

      int jpyCnt = 0, matchCnt = 0;
      // 遍历该月的 JPY M30 bar
      int sh0 = iBarShift(_Symbol, PERIOD_M30, mFrom, false);
      if(sh0 >= nJ) sh0 = nJ - 1;
      for(int i = sh0; i >= 0; i--)
      {
         datetime bt = iTime(_Symbol, PERIOD_M30, i);
         if(bt < mFrom) break;
         if(bt >= mTo) continue;
         if(bt < jpyFirst) break;
         jpyCnt++;
         // ★exact timestamp 匹配：必须找到 open time 完全相同的 XAU M30 bar
         int sx = iBarShift(InpInfoSym, PERIOD_M30, bt, false);
         if(sx >= 0 && sx < nX)
         {
            datetime xt = iTime(InpInfoSym, PERIOD_M30, sx);
            if(xt == bt) matchCnt++;
         }
      }
      double ar = (jpyCnt > 0) ? (100.0 * matchCnt / jpyCnt) : 0.0;
      W(StringFormat("%04d-%02d | %d | %d | %.4f%%", y, mo, jpyCnt, matchCnt, ar));

      y = ny; mo = nmo;
   }

   W("");
   W("done");
   if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
}

void OnDeinit(const int reason) { if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; } }
//+------------------------------------------------------------------+
