//+------------------------------------------------------------------+
//|  dsh_JSB30History.mq5  —  历史覆盖权威探针（脚本，非 EA）          |
//|                                                                  |
//|  在【终端图表】上运行，会触发券商服务器全量历史同步，              |
//|  从而得到与 specs.json 同口径的"券商实际可用历史"。                |
//|                                                                  |
//|  只读：不交易、不下单、不建自建品种、不写行情数据。                 |
//|  输出：Common\Files\dshtrend\JSB30HIST\history_probe.txt           |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property script_show_inputs

input string InpSymbol     = "USDJPYm";
input bool   InpForceSync  = true;    // 请求全量历史同步

void Rpt(int fh, const string s)
{
   Print("dshhist: ", s);
   if(fh != INVALID_HANDLE) FileWrite(fh, s);
}

void OnStart()
{
   string dir = "dshtrend\\JSB30HIST";
   FolderCreate("dshtrend", FILE_COMMON);
   FolderCreate(dir, FILE_COMMON);
   string fn = dir + "\\history_probe.txt";
   int fh = FileOpen(fn, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh == INVALID_HANDLE) fh = FileOpen(fn, FILE_WRITE|FILE_TXT|FILE_ANSI);

   Rpt(fh, "=== dsh_JSB30History ===");
   Rpt(fh, "terminal_build=" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)));
   Rpt(fh, "server=" + AccountInfoString(ACCOUNT_SERVER));
   Rpt(fh, "symbol=" + InpSymbol);
   Rpt(fh, "probe_time=" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   Rpt(fh, "is_custom=" + (SymbolInfoInteger(InpSymbol, SYMBOL_CUSTOM) ? "YES" : "no"));
   Rpt(fh, "is_select=" + (SymbolInfoInteger(InpSymbol, SYMBOL_SELECT) ? "YES" : "no"));

   ENUM_TIMEFRAMES tfs[] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_D1};
   string names[]        = {"M1", "M5", "M15", "M30", "H1", "D1"};

   for(int i = 0; i < ArraySize(tfs); i++)
   {
      // ★关键：用 CopyClose/CopyTime 请求全量同步（会向服务器要历史）
      if(InpForceSync)
      {
         datetime probeFrom = D'2000.01.01';
         double dummy[];
         int n = CopyClose(InpSymbol, tfs[i], probeFrom, TimeCurrent(), dummy);
         int err = GetLastError();
         datetime f0 = 0, l0 = 0;
         int total = (int)SeriesInfoInteger(InpSymbol, tfs[i], SERIES_BARS_COUNT);
         SeriesInfoInteger(InpSymbol, tfs[i], SERIES_FIRSTDATE, f0);
         SeriesInfoInteger(InpSymbol, tfs[i], SERIES_LASTBAR_DATE, l0);
         Rpt(fh, StringFormat("tf=%-4s bars=%d first=%s last=%s copied=%d err=%d",
              names[i], total,
              (f0 > 0) ? TimeToString(f0, TIME_DATE|TIME_MINUTES) : "none",
              (l0 > 0) ? TimeToString(l0, TIME_DATE|TIME_MINUTES) : "none",
              (n > 0 ? n : 0), err));
      }
      else
      {
         datetime f0 = 0, l0 = 0;
         int total = (int)SeriesInfoInteger(InpSymbol, tfs[i], SERIES_BARS_COUNT);
         SeriesInfoInteger(InpSymbol, tfs[i], SERIES_FIRSTDATE, f0);
         SeriesInfoInteger(InpSymbol, tfs[i], SERIES_LASTBAR_DATE, l0);
         Rpt(fh, StringFormat("tf=%-4s bars=%d first=%s last=%s",
              names[i], total,
              (f0 > 0) ? TimeToString(f0, TIME_DATE|TIME_MINUTES) : "none",
              (l0 > 0) ? TimeToString(l0, TIME_DATE|TIME_MINUTES) : "none"));
      }
   }

   // 逐年 M1 计数（用 CopyTime 分年统计真实存在的 bar 数）
   Rpt(fh, "--- M1 yearly bar count ---");
   for(int y = 2014; y <= 2026; y++)
   {
      datetime a = StringToTime(StringFormat("%04d.01.01 00:00", y));
      datetime b = StringToTime(StringFormat("%04d.01.01 00:00", y + 1));
      if(b > TimeCurrent()) b = TimeCurrent();
      datetime ta[];
      int n = CopyTime(InpSymbol, PERIOD_M1, a, b, ta);
      string note = "";
      if(n <= 0)
      {
         int err = GetLastError();
         note = StringFormat(" [err=%d]", err);
      }
      Rpt(fh, StringFormat("year=%d M1_bars=%d%s", y, (n > 0 ? n : 0), note));
   }

   // 真实 tick 覆盖（只探最近，避免超时）
   Rpt(fh, "--- real tick coverage (sampled) ---");
   for(int d = 0; d <= 400; d += 40)
   {
      datetime day0 = (datetime)(((long)TimeCurrent() / 86400) * 86400 - (long)d * 86400);
      MqlTick tk[];
      int cnt = CopyTicksRange(InpSymbol, tk, COPY_TICKS_ALL,
                               (ulong)day0 * 1000, (ulong)(day0 + 86400) * 1000);
      Rpt(fh, StringFormat("days_back=%d date=%s ticks=%d",
           d, TimeToString(day0, TIME_DATE), (cnt > 0 ? cnt : 0)));
   }

   if(fh != INVALID_HANDLE) { FileClose(fh); }
   Print("dshhist: 完成 -> ", fn);
}
//+------------------------------------------------------------------+
