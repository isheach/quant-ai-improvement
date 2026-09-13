//+------------------------------------------------------------------+
//|  dsh_ExportInTester.mq5                                          |
//|  DeepSeek / 新量化策略                                            |
//|                                                                  |
//|  ★这是「从 Exness 服务器取任意久历史」的正确方法。                    |
//|                                                                  |
//|  为什么不能用终端图表脚本：                                          |
//|    终端脚本里的 CopyRates 走的是「本地缓存 + 当前点请求」，           |
//|    实测只能拿到约 500,000 根 M1（黄金回到 2025-04），更早的拿不到。   |
//|    把终端 "Max bars in chart" 从 100000 抬到 50000000 也无效。       |
//|                                                                  |
//|  为什么测试器可以：                                                  |
//|    策略测试器有独立的、按 [Tester] FromDate/ToDate 驱动的历史请求通道。|
//|    实测：FromDate=2023.01.05 的真实 XAUUSDm → Bars=30071、           |
//|          Ticks=120280、History Quality=100%。**2023 年的数据在。**   |
//|                                                                  |
//|  本 EA 的做法（与旧项目 eva008_TickDataExporterEA 同一思路）：        |
//|    在 OnTick() 里【随回测推进逐根记录】M1 bar 与 tick。              |
//|    因为测试器会把 FromDate~ToDate 逐 tick 走一遍，所以只要你把       |
//|    区间设得够长，就能把该区间的全部历史"录"下来。                     |
//|                                                                  |
//|  用法：                                                             |
//|    1) 编译本 EA 到 MQL5\Experts\dshtools\                           |
//|    2) 用 [Tester] 配置：Model=1(有tick用tick) 或 2(只要bar)          |
//|       FromDate / ToDate 设成你要导出的区间                          |
//|    3) 跑完到 Common\Files\dshtools\export_tester\ 取 CSV           |
//|                                                                  |
//|  产出（写到 Common\Files，跨终端可取）：                              |
//|    <SYM>_M1_bars.csv      time,open,high,low,close,tick_volume,spread
//|    <SYM>_ticks_partNN.csv  time_msc,time_iso,bid,ask,last,volume,flags
//|    <SYM>_export_meta.json 覆盖范围/根数/统计                          |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property script_show_inputs

input bool   InpExportBars     = true;    // 导出 M1 bar
input bool   InpExportTicks    = true;    // 导出 tick
input int    InpTicksPerFile   = 3000000; // 每个 tick 文件最多多少行（防单文件过大）
input string InpOutPrefix      = "";      // 留空=用 _Symbol

int      g_bar_fh    = INVALID_HANDLE;
int      g_tick_fh   = INVALID_HANDLE;
int      g_tick_file = 0;
long     g_bars      = 0;
long     g_ticks     = 0;
long     g_ticks_in_file = 0;
datetime g_first_bar = 0, g_last_bar = 0;
datetime g_first_tick = 0, g_last_tick = 0;
datetime g_last_bar_time = 0;
string   g_prefix    = "";
string   g_dir       = "";

//+------------------------------------------------------------------+
string MM(int m) { return (m < 10 ? "0" : "") + IntegerToString(m); }
string PN(int n) { string s = IntegerToString(n); while(StringLen(s) < 2) s = "0" + s; return s; }

//+------------------------------------------------------------------+
int OnInit()
{
   g_prefix = (InpOutPrefix == "" ? _Symbol : InpOutPrefix);
   g_dir    = "dshtools\\export_tester\\";

   if(InpExportBars)
   {
      g_bar_fh = FileOpen(g_dir + g_prefix + "_M1_bars.csv",
                          FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
      if(g_bar_fh == INVALID_HANDLE)
      {
         Print("dshX: 无法创建 bar 文件 err=", GetLastError());
         return INIT_FAILED;
      }
      FileWrite(g_bar_fh, "time", "time_iso", "open", "high", "low", "close",
                "tick_volume", "spread");
   }

   if(InpExportTicks)
   {
      g_tick_fh = FileOpen(g_dir + g_prefix + "_ticks_part" + PN(g_tick_file) + ".csv",
                           FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
      if(g_tick_fh == INVALID_HANDLE)
      {
         Print("dshX: 无法创建 tick 文件 err=", GetLastError());
         return INIT_FAILED;
      }
      FileWrite(g_tick_fh, "time_msc", "time_iso", "bid", "ask", "last",
                "volume", "flags");
   }

   Print("dshX: === ExportInTester init === symbol=", _Symbol,
         " period=", EnumToString((ENUM_TIMEFRAMES)Period()),
         " digits=", _Digits, " point=", DoubleToString(_Point, 8));
   Print("dshX: Common=", TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   Print("dshX: tester start=", TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
void OnTick()
{
   MqlTick tk;
   if(!SymbolInfoTick(_Symbol, tk)) return;

   // ---- tick ----
   if(InpExportTicks && g_tick_fh != INVALID_HANDLE)
   {
      FileWrite(g_tick_fh,
                (string)tk.time_msc,
                TimeToString(tk.time, TIME_DATE|TIME_SECONDS),
                DoubleToString(tk.bid, _Digits),
                DoubleToString(tk.ask, _Digits),
                DoubleToString(tk.last, _Digits),
                (string)tk.volume,
                (string)tk.flags);
      g_ticks++;
      g_ticks_in_file++;
      if(g_first_tick == 0) g_first_tick = tk.time;
      g_last_tick = tk.time;

      if(g_ticks_in_file >= InpTicksPerFile)
      {
         FileClose(g_tick_fh);
         g_tick_file++;
         g_ticks_in_file = 0;
         g_tick_fh = FileOpen(g_dir + g_prefix + "_ticks_part" + PN(g_tick_file) + ".csv",
                              FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
         if(g_tick_fh != INVALID_HANDLE)
            FileWrite(g_tick_fh, "time_msc", "time_iso", "bid", "ask", "last",
                      "volume", "flags");
      }
   }

   // ---- M1 bar（每根只记一次）----
   if(InpExportBars && g_bar_fh != INVALID_HANDLE)
   {
      MqlRates r[];
      if(CopyRates(_Symbol, PERIOD_M1, 0, 1, r) == 1)
      {
         if(r[0].time != g_last_bar_time)
         {
            g_last_bar_time = r[0].time;
            FileWrite(g_bar_fh,
                      (string)r[0].time,
                      TimeToString(r[0].time, TIME_DATE|TIME_SECONDS),
                      DoubleToString(r[0].open,  _Digits),
                      DoubleToString(r[0].high,  _Digits),
                      DoubleToString(r[0].low,   _Digits),
                      DoubleToString(r[0].close, _Digits),
                      (string)r[0].tick_volume,
                      (string)r[0].spread);
            g_bars++;
            if(g_first_bar == 0) g_first_bar = r[0].time;
            g_last_bar = r[0].time;
         }
      }
   }
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_bar_fh  != INVALID_HANDLE) FileClose(g_bar_fh);
   if(g_tick_fh != INVALID_HANDLE) FileClose(g_tick_fh);

   string j = "{\n";
   j += "  \"symbol\": \"" + _Symbol + "\",\n";
   j += "  \"digits\": " + (string)_Digits + ",\n";
   j += "  \"point\": " + DoubleToString(_Point, 8) + ",\n";
   j += "  \"contract_size\": " + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE), 2) + ",\n";
   j += "  \"bars\": " + (string)g_bars + ",\n";
   j += "  \"first_bar\": \"" + (g_first_bar > 0 ? TimeToString(g_first_bar, TIME_DATE|TIME_MINUTES) : "") + "\",\n";
   j += "  \"last_bar\": \""  + (g_last_bar  > 0 ? TimeToString(g_last_bar,  TIME_DATE|TIME_MINUTES) : "") + "\",\n";
   j += "  \"ticks\": " + (string)g_ticks + ",\n";
   j += "  \"first_tick\": \"" + (g_first_tick > 0 ? TimeToString(g_first_tick, TIME_DATE|TIME_SECONDS) : "") + "\",\n";
   j += "  \"last_tick\": \""  + (g_last_tick  > 0 ? TimeToString(g_last_tick,  TIME_DATE|TIME_SECONDS) : "") + "\",\n";
   j += "  \"tick_files\": " + (string)(g_tick_file + 1) + ",\n";
   j += "  \"deinit_reason\": " + (string)reason + "\n";
   j += "}\n";

   int fh = FileOpen(g_dir + g_prefix + "_export_meta.json",
                     FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, j); FileClose(fh); }

   Print("dshX: === ExportInTester done === bars=", g_bars,
         " [", TimeToString(g_first_bar, TIME_DATE|TIME_MINUTES), " ~ ",
         TimeToString(g_last_bar, TIME_DATE|TIME_MINUTES), "]",
         "  ticks=", g_ticks,
         " [", TimeToString(g_first_tick, TIME_DATE|TIME_SECONDS), " ~ ",
         TimeToString(g_last_tick, TIME_DATE|TIME_SECONDS), "]");
}
//+------------------------------------------------------------------+
