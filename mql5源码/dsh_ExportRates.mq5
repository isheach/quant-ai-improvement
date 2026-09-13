//+------------------------------------------------------------------+
//|  dsh_ExportRates.mq5                                             |
//|  DeepSeek / 新量化策略                                            |
//|                                                                  |
//|  把终端里（从券商服务器下载到的）真实历史导出成 CSV。                |
//|  与自定义品种那条线互补：这条是「券商原始数据」，点差是真实等值点差。  |
//|                                                                  |
//|  输出（写到 Common\Files\dshtools\，路径固定好取）：                |
//|      <SYM>_M1_real.csv   datetime,open,high,low,close,tick_volume,spread
//|      <SYM>_M5_real.csv   同上（M5）                                |
//|      export_report.txt   覆盖范围/根数/点差分位数/tick 覆盖          |
//|                                                                  |
//|  ⚠️ 逐月切片 CopyRates，避免一次申请百万根数组。                     |
//|  ⚠️ 跑在实时终端图表脚本上（不是测试器）。                            |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property script_show_inputs

input string InpSymbols = "XAUUSDm,BTCUSDm,USDJPYm";
input int    InpFromYear = 2019;      // 探测起点（脚本会自己找到真实首日）
input int    InpToYear   = 2026;
input bool   InpExportM5 = true;

string g_log = "";

//+------------------------------------------------------------------+
void Rpt(const string s) { Print("dsh: ", s); g_log += s + "\n"; }

//+------------------------------------------------------------------+
//| 从某起点往后探测，返回第一个真实存在的 M1 bar 时间                    |
//+------------------------------------------------------------------+
datetime FindFirstBar(const string sym, int y0, int y1)
{
   for(int y = y0; y <= y1; y++)
   {
      for(int m = 1; m <= 12; m++)
      {
         MqlDateTime a, b;
         a.year = y; a.mon = m; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
         datetime from = StructToTime(a);
         b.year = (m == 12) ? y + 1 : y; b.mon = (m == 12) ? 1 : m + 1;
         b.day = 1; b.hour = 0; b.min = 0; b.sec = 0;
         datetime to = StructToTime(b) - 1;
         if(from > TimeCurrent()) return 0;

         MqlRates r[];
         int got = CopyRates(sym, PERIOD_M1, from, to, r);
         if(got > 0)
         {
            Rpt("    首个有数据月: " + StringFormat("%04d-%02d", y, m) + " bars=" + (string)got
                + " first=" + TimeToString(r[0].time, TIME_DATE|TIME_MINUTES));
            return r[0].time;
         }
         Sleep(120);
      }
   }
   return 0;
}

//+------------------------------------------------------------------+
//| 导出单品种单周期                                                    |
//+------------------------------------------------------------------+
int ExportTF(const string sym, ENUM_TIMEFRAMES tf, const string tag,
             datetime from, datetime to, string &outfile, double &spread_med,
             datetime &real_first, datetime &real_last)
{
   outfile = "dshtools\\" + sym + "_" + tag + "_real.csv";
   int h = FileOpen(outfile, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE)
   {
      Rpt("    !! 打不开 " + outfile + " err=" + (string)GetLastError());
      return 0;
   }

   int total = 0;
   spread_med = 0; real_first = 0; real_last = 0;
   int spreads[]; ArrayResize(spreads, 0);

   // 逐月切片
   int y0 = 0, m0 = 0, d0 = 0, hh0 = 0, mm0 = 0;
   MqlDateTime st;
   TimeToStruct(from, st);
   int cy = st.year, cm = st.mon;
   MqlDateTime et;
   TimeToStruct(to, et);

   while(cy < et.year || (cy == et.year && cm <= et.mon))
   {
      MqlDateTime a, b;
      a.year = cy; a.mon = cm; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
      datetime cs = StructToTime(a);
      b.year = (cm == 12) ? cy + 1 : cy; b.mon = (cm == 12) ? 1 : cm + 1;
      b.day = 1; b.hour = 0; b.min = 0; b.sec = 0;
      datetime ce = StructToTime(b) - 1;
      if(cs < from) cs = from;
      if(ce > to)   ce = to;

      MqlRates r[];
      int got = CopyRates(sym, tf, cs, ce, r);
      if(got > 0)
      {
         for(int i = 0; i < got; i++)
         {
            FileWriteString(h, TimeToString(r[i].time, TIME_DATE|TIME_MINUTES|TIME_SECONDS) + ","
                            + DoubleToString(r[i].open,  5) + ","
                            + DoubleToString(r[i].high,  5) + ","
                            + DoubleToString(r[i].low,   5) + ","
                            + DoubleToString(r[i].close, 5) + ","
                            + (string)r[i].tick_volume + ","
                            + (string)r[i].spread + "\n");
            if(i % 7 == 0 && ArraySize(spreads) < 20000)
            {
               int n = ArraySize(spreads);
               ArrayResize(spreads, n + 1);
               spreads[n] = (int)r[i].spread;
            }
         }
         total += got;
         if(real_first == 0) real_first = r[0].time;
         real_last = r[got - 1].time;
      }
      cm++;
      if(cm > 12) { cm = 1; cy++; }
      Sleep(60);
   }

   FileClose(h);

   if(ArraySize(spreads) > 0)
   {
      ArraySort(spreads);
      spread_med = (double)spreads[ArraySize(spreads) / 2];
   }
   return total;
}

//+------------------------------------------------------------------+
void DoSymbol(const string sym)
{
   Rpt("");
   Rpt("==================== " + sym + " ====================");
   if(!SymbolSelect(sym, true)) { Rpt("  !! symbol 不可用"); return; }

   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   int    digs  = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   double csize = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
   double vmin  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double tval  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double tsize = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   long   cur_spread = SymbolInfoInteger(sym, SYMBOL_SPREAD);

   Rpt("  规格: digits=" + (string)digs + " point=" + DoubleToString(point, 8)
       + " contract=" + DoubleToString(csize, 2) + " vol_min=" + DoubleToString(vmin, 4));
   Rpt("        tick_value=" + DoubleToString(tval, 8) + " tick_size=" + DoubleToString(tsize, 8)
       + " -> 0.01手每$1价格波动=" + DoubleToString(0.01 * csize, 4) + " USD(按合约反推)");
   Rpt("        当前点差=" + (string)cur_spread + " 点");

   datetime first = FindFirstBar(sym, InpFromYear, InpToYear);
   if(first == 0) { Rpt("  !! 完全没有 M1 历史"); return; }
   datetime last = (datetime)SeriesInfoInteger(sym, PERIOD_M1, SERIES_LASTBAR_DATE);
   if(last == 0) last = TimeCurrent();

   string f1; double sp1; datetime a1, b1;
   int n1 = ExportTF(sym, PERIOD_M1, "M1", first, last, f1, sp1, a1, b1);
   Rpt("  M1 导出: " + (string)n1 + " 根  " + TimeToString(a1, TIME_DATE|TIME_MINUTES)
       + " ~ " + TimeToString(b1, TIME_DATE|TIME_MINUTES)
       + "  点差中位=" + DoubleToString(sp1, 0) + " 点");
   Rpt("         -> Common\\Files\\" + f1);

   if(InpExportM5)
   {
      string f5; double sp5; datetime a5, b5;
      int n5 = ExportTF(sym, PERIOD_M5, "M5", first, last, f5, sp5, a5, b5);
      Rpt("  M5 导出: " + (string)n5 + " 根  -> Common\\Files\\" + f5);
   }

   // tick 覆盖情况（能否做「每 tick」回测的关键）
   long tcount = SeriesInfoInteger(sym, PERIOD_M1, SERIES_BARS_COUNT);
   MqlTick t[];
   long tgot = CopyTicksRange(sym, t, COPY_TICKS_ALL, (long)(last - 86400) * 1000, (long)last * 1000);
   Rpt("  tick 探测(最后1天): " + (string)tgot + " 个 tick  (>=0 说明有 tick 数据可用)");
}

//+------------------------------------------------------------------+
void OnStart()
{
   Rpt("=== dsh_ExportRates " + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + " ===");
   Rpt("Common 目录: " + TerminalInfoString(TERMINAL_COMMONDATA_PATH));

   string syms[];
   int n = StringSplit(InpSymbols, ',', syms);
   for(int i = 0; i < n; i++)
   {
      string s = syms[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(StringLen(s) > 0) DoSymbol(s);
   }

   int h = FileOpen("dshtools\\export_report.txt",
                    FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h != INVALID_HANDLE) { FileWriteString(h, g_log); FileClose(h); }
   Rpt("=== done ===");
}
//+------------------------------------------------------------------+
