//+------------------------------------------------------------------+
//|  dsh_TickProbe2.mq5                                              |
//|  DeepSeek / 新量化策略                                            |
//|                                                                  |
//|  判定「券商到底有没有真实 tick，能回溯到什么时候」。                  |
//|                                                                  |
//|  与前几次失败版本的差别（重要）：                                    |
//|   1) ★带上 eva005 的「历史未就绪」重试逻辑：                         |
//|      CopyTicksRange 返回 <=0 且 GetLastError ∈ {4401,4073,4074,4066}  |
//|      → 说明历史仍在异步加载，必须 Sleep 后重试，不能直接判定"无数据"。  |
//|   2) ★从「现在」往回搜（而不是从老往新），这样一旦确认某天没 tick，    |
//|      就可以停止，不会在不存在的老 tick 上白等几小时。                 |
//|   3) 先在候选日期上做二分定位边界，再在边界附近细查。                 |
//|                                                                  |
//|  输出：Common\Files\dshtools\tick_probe2.txt                       |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "2.00"
#property script_show_inputs

input string InpSymbol      = "XAUUSDm";
input int    InpDaysBack    = 500;    // 从今天往回搜多少天
input int    InpStepDays    = 7;      // 粗搜步长（天）
input int    InpRetries     = 40;     // 单次请求的重试次数
input int    InpRetrySleep  = 500;    // 重试间隔（毫秒）
input int    InpWaitConnectSec = 60;  // ★等终端连上服务器最多多少秒

string g_log = "";
void Rpt(const string s) { Print("dshP: ", s); g_log += s + "\n"; }

//+------------------------------------------------------------------+
//| 带「历史未就绪」重试的 CopyTicksRange                              |
//| 返回：>0 = tick 条数；0 = 该区间确实没有 tick                        |
//+------------------------------------------------------------------+
int TicksRetry(const string sym, MqlTick &t[], ulong from_msc, ulong to_msc)
{
   for(int a = 0; a <= InpRetries; a++)
   {
      ResetLastError();
      int got = CopyTicksRange(sym, t, COPY_TICKS_ALL, from_msc, to_msc);
      if(got > 0) return got;

      int err = GetLastError();
      // 4401=历史未就绪 4073/4074/4066=历史相关错误 → 等待重试
      if(got < 0 || err == 4401 || err == 4073 || err == 4074 || err == 4066)
      {
         if(IsStopped()) return got;
         Sleep(InpRetrySleep);
         continue;
      }
      return 0;   // 明确的"无数据"
   }
   return 0;
}

//+------------------------------------------------------------------+
long TicksOnDay(const string sym, datetime day0)
{
   MqlTick t[];
   MqlDateTime d; TimeToStruct(day0, d);
   d.hour = 0; d.min = 0; d.sec = 0;
   datetime d0 = StructToTime(d);
   return TicksRetry(sym, t, (ulong)d0 * 1000, ((ulong)d0 + 86399) * 1000);
}

//+------------------------------------------------------------------+
void OnStart()
{
   string sym = InpSymbol;
   Rpt("=== dsh_TickProbe2 " + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + " ===");
   Rpt("symbol=" + sym + "  搜 " + (string)InpDaysBack + " 天，步长 " + (string)InpStepDays
       + " 天，重试 " + (string)InpRetries + "x" + (string)InpRetrySleep + "ms");

   if(!SymbolSelect(sym, true)) { Rpt("!! SymbolSelect 失败"); }

   // ★★ 关键：等终端真正连上服务器。
   // 实测教训：脚本在终端刚启动时就跑了，此时 TERMINAL_CONNECTED=false，
   // 所有历史请求都无法触发服务器下载（重试也没用，因为根本没在下载）。
   Rpt("等待终端连接服务器...");
   int waited = 0;
   while(!(bool)TerminalInfoInteger(TERMINAL_CONNECTED) && waited < InpWaitConnectSec)
   {
      Sleep(500);
      waited += 1;
      if(waited % 10 == 0) Rpt("  ...已等 " + (string)(waited / 2) + " 秒");
      if(IsStopped()) break;
   }
   bool conn = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   Rpt("连接状态 = " + (conn ? "OK" : "★仍未连接（历史下载会失败）")
       + "   等了 " + (string)(waited / 2) + " 秒");
   if(!conn)
   {
      Rpt("!! 未连接，本次结果不可信。请确认终端能登录 277335900@Exness-MT5Trial5 后重跑。");
   }

   Rpt("digits=" + (string)SymbolInfoInteger(sym, SYMBOL_DIGITS)
       + " point=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_POINT), 8));

   datetime now = TimeCurrent();
   MqlDateTime td; TimeToStruct(now, td); td.hour=0; td.min=0; td.sec=0;
   datetime today0 = StructToTime(td);

   // 基准：今天与昨天
   Rpt("今天(" + TimeToString(today0, TIME_DATE) + ") tick = " + (string)TicksOnDay(sym, today0));
   Rpt("昨天 tick = " + (string)TicksOnDay(sym, today0 - 86400));

   // 从今天往回粗搜，记录最后一个"有 tick"的日期
   datetime oldest_ok = 0;
   datetime first_fail = 0;
   string detail = "";
   int checked = 0;

   for(int back = 0; back <= InpDaysBack; back += InpStepDays)
   {
      datetime d = today0 - (datetime)back * 86400;
      long n = TicksOnDay(sym, d);
      checked++;

      if(n > 0)
      {
         oldest_ok = d;
         detail += TimeToString(d, TIME_DATE) + ":" + (string)n + "  ";
      }
      else if(first_fail == 0)
      {
         first_fail = d;
         detail += TimeToString(d, TIME_DATE) + ":0*  ";   // * = 第一个失败点
      }
      if(back % (InpStepDays * 20) == 0 || (n > 0 && back < InpStepDays * 8))
         Rpt("  [" + TimeToString(d, TIME_DATE) + "] ticks=" + (string)n);

      if(IsStopped()) break;
   }

   Rpt("");
   Rpt("检查了 " + (string)checked + " 个日期");
   Rpt("★ 最早有 tick 的采样日 = "
       + (oldest_ok > 0 ? TimeToString(oldest_ok, TIME_DATE) : "none"));
   Rpt("★ 第一个无 tick 的采样日 = "
       + (first_fail > 0 ? TimeToString(first_fail, TIME_DATE) : "none（全区间都有）"));
   Rpt("明细: " + detail);

   // 写报告
   int h = FileOpen("dshtools\\tick_probe2.txt",
                    FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h != INVALID_HANDLE) { FileWriteString(h, g_log); FileClose(h); }
   Rpt("=== done ===");
}
//+------------------------------------------------------------------+
