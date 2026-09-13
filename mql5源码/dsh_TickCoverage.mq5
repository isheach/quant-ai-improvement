//+------------------------------------------------------------------+
//|  dsh_TickCoverage.mq5                                            |
//|  DeepSeek / 新量化策略                                            |
//|                                                                  |
//|  探测「真实 tick 数据」能回溯多远。                                 |
//|  意义：自定义品种只有 M1 OHLC（Model=2）；                        |
//|        如果能拿到真实 tick，就能用 Model=0/1（每 tick）做更可信的回测。|
//|                                                                  |
//|  ⚠️ 不要逐月探测（CopyTicksRange 每月要几十秒，两个品种就超时）。    |
//|     改成：按「天」采样若干候选日期，快速定位边界。                    |
//|                                                                  |
//|  输出：Common\Files\dshtools\tick_coverage.txt                     |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.10"
#property script_show_inputs

input string InpSymbols   = "XAUUSDm,BTCUSDm,USDJPYm";
input int    InpDaysBack  = 1000;   // 从今天往前探测多少天
input int    InpStepDays  = 25;     // 采样步长（天）

string g_log = "";
void Rpt(const string s) { Print("dsh: ", s); g_log += s + "\n"; }

//+------------------------------------------------------------------+
//| 探测某一天的 tick 数量（0 = 没有）                                  |
//+------------------------------------------------------------------+
long TicksOnDay(const string sym, datetime day0)
{
   MqlTick t[];
   long got = CopyTicksRange(sym, t, COPY_TICKS_ALL,
                             (long)day0 * 1000, (long)(day0 + 86399) * 1000);
   return (got > 0) ? got : 0;
}

//+------------------------------------------------------------------+
void DoSymbol(const string sym)
{
   Rpt("");
   Rpt("==================== " + sym + " ====================");
   if(!SymbolSelect(sym, true)) { Rpt("  !! 不可用"); return; }

   datetime now = TimeCurrent();
   datetime today0 = now - (now % 86400);

   Rpt("  今天 tick = " + (string)TicksOnDay(sym, today0)
       + "   昨天 tick = " + (string)TicksOnDay(sym, today0 - 86400));

   datetime oldest_nonzero = 0;
   datetime newest_zero    = 0;
   string line = "";
   int checked = 0;
   for(int back = 0; back <= InpDaysBack; back += InpStepDays)
   {
      datetime d = today0 - (datetime)back * 86400;
      long n = TicksOnDay(sym, d);
      checked++;
      if(n > 0 && (oldest_nonzero == 0 || d < oldest_nonzero))
         oldest_nonzero = d;
      if(n == 0 && (newest_zero == 0 || d > newest_zero))
         newest_zero = d;
      if(back <= InpStepDays * 4 || back % (InpStepDays * 4) == 0)
         line += TimeToString(d, TIME_DATE) + ":" + (string)n + "  ";
   }
   Rpt("  采样 " + (string)checked + " 个日期（步长 " + (string)InpStepDays + " 天）");
   Rpt("  最早有 tick 的采样日 = "
       + (oldest_nonzero > 0 ? TimeToString(oldest_nonzero, TIME_DATE) : "none"));
   Rpt("  最晚无 tick 的采样日 = "
       + (newest_zero > 0 ? TimeToString(newest_zero, TIME_DATE) : "none"));
   Rpt("  明细: " + line);
}

//+------------------------------------------------------------------+
void OnStart()
{
   Rpt("=== dsh_TickCoverage " + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + " ===");
   string syms[];
   int n = StringSplit(InpSymbols, ',', syms);
   for(int i = 0; i < n; i++)
   {
      string s = syms[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(StringLen(s) > 0) DoSymbol(s);
   }
   int h = FileOpen("dshtools\\tick_coverage.txt",
                    FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h != INVALID_HANDLE) { FileWriteString(h, g_log); FileClose(h); }
   Rpt("=== done ===");
}
//+------------------------------------------------------------------+
