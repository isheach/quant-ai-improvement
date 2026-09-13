//+------------------------------------------------------------------+
//|  dsh_DownloadHistory.mq5                                         |
//|  DeepSeek / 新量化策略                                            |
//|                                                                  |
//|  目的：让 MT5 自己去券商服务器下载历史，而不是用旧项目导出的 CSV。   |
//|                                                                  |
//|  原理：对 M1 逐月调用 CopyRates(sym, PERIOD_M1, from, to, rates)   |
//|        会「请求」该区间的历史。若本地没有，终端会向 History Server  |
//|        发起下载，并把结果持久化到 bases\<server>\history\。        |
//|        下载是异步的，所以请求后要 Sleep + 重试，直到拿到数据        |
//|        或连续多次拿不到（判定为券商没有这一段）。                    |
//|                                                                  |
//|  ⚠️ 必须跑在「实时终端」的图表脚本上（不是测试器）——             |
//|     测试器有独立的历史缓存，下载不会回写主终端的数据目录。            |
//|                                                                  |
//|  输出：<数据目录>\MQL5\Files\dshtools\download_report.txt (追加)   |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property script_show_inputs

input string  InpSymbols    = "XAUUSDm,BTCUSDm,USDJPYm";  // 逗号分隔
input int     InpFromYear   = 2023;                       // 探测起始年
input int     InpToYear     = 2026;                       // 探测结束年
input int     InpMaxRounds  = 6;                          // 每月最多重试轮数
input int     InpSleepMs    = 1200;                       // 每次请求后等待（异步下载）
input bool    InpMonthlyProbe = true;                     // 逐月探测（true=能精确定位边界）
input bool    InpExportCsv    = false;                    // 同时导出 M1 CSV（数据量大，默认关）

int    g_report = INVALID_HANDLE;
string g_log    = "";

//+------------------------------------------------------------------+
void Rpt(const string s)
{
   Print("dsh: ", s);
   g_log += s + "\n";
}

//+------------------------------------------------------------------+
//| 请求某一小段 M1（触发下载），把结果写进调用者的数组                 |
//|  ⚠️ r 必须按引用传入。第一版忘了 &，导致 ProbeMonth 里读到空数组 →   |
//|     "array out of range in 'dsh_DownloadHistory.mq5' (68,17)"。   |
//+------------------------------------------------------------------+
int RequestChunk(const string sym, datetime from, datetime to,
                 MqlRates &r[], int max_rounds, int sleep_ms)
{
   int got = 0;
   for(int round = 0; round < max_rounds; round++)
   {
      got = CopyRates(sym, PERIOD_M1, from, to, r);
      if(got > 0)
         return got;
      Sleep(sleep_ms);
   }
   return 0;
}

//+------------------------------------------------------------------+
//| 探测一个月份区间的可用性                                            |
//+------------------------------------------------------------------+
void ProbeMonth(const string sym, datetime m_from, datetime m_to, int &bars, datetime &first, datetime &last)
{
   MqlRates r[];
   bars = 0; first = 0; last = 0;
   int got = RequestChunk(sym, m_from, m_to, r, InpMaxRounds, InpSleepMs);
   if(got > 0)
   {
      bars  = got;
      first = r[0].time;
      last  = r[got - 1].time;
   }
}

//+------------------------------------------------------------------+
void ProbeSymbol(const string sym)
{
   Rpt("");
   Rpt("==================== " + sym + " ====================");

   if(!SymbolSelect(sym, true))
   {
      Rpt("  !! SymbolSelect failed (symbol 不存在？) err=" + (string)GetLastError());
      return;
   }
   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   if(point <= 0.0)
   {
      Rpt("  !! symbol 不可用");
      return;
   }
   Rpt("  digits=" + (string)SymbolInfoInteger(sym, SYMBOL_DIGITS)
       + " point=" + DoubleToString(point, 8)
       + " contract=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE), 2)
       + " vol_min=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 4)
       + " spread=" + (string)SymbolInfoInteger(sym, SYMBOL_SPREAD));

   // ---- 先把终端「当前」有多少报出来 ----
   long cur_bars = SeriesInfoInteger(sym, PERIOD_M1, SERIES_BARS_COUNT);
   datetime cur_first = (datetime)SeriesInfoInteger(sym, PERIOD_M1, SERIES_FIRSTDATE);
   datetime cur_last  = (datetime)SeriesInfoInteger(sym, PERIOD_M1, SERIES_LASTBAR_DATE);
   Rpt("  [下载前] 终端已有 M1: bars=" + (string)cur_bars
       + " first=" + (cur_first > 0 ? TimeToString(cur_first, TIME_DATE|TIME_MINUTES) : "none")
       + " last="  + (cur_last  > 0 ? TimeToString(cur_last,  TIME_DATE|TIME_MINUTES) : "none"));

   // ---- 逐月探测 / 下载 ----
   int total = 0;
   int months_ok = 0, months_empty = 0;
   datetime g_first = 0, g_last = 0;
   string monthline = "";

   for(int y = InpFromYear; y <= InpToYear; y++)
   {
      for(int m = 1; m <= 12; m++)
      {
         MqlDateTime a, b;
         a.year = y; a.mon = m; a.day = 1; a.hour = 0; a.min = 0; a.sec = 0;
         datetime m_from = StructToTime(a);
         b.year = (m == 12) ? y + 1 : y; b.mon = (m == 12) ? 1 : m + 1;
         b.day = 1; b.hour = 0; b.min = 0; b.sec = 0;
         datetime m_to = StructToTime(b) - 1;

         if(m_from > TimeCurrent()) continue;   // 不探测未来

         int bars; datetime f, l;
         ProbeMonth(sym, m_from, m_to, bars, f, l);

         if(bars > 0)
         {
            total += bars;
            months_ok++;
            if(g_first == 0 || f < g_first) g_first = f;
            if(l > g_last) g_last = l;
            monthline += StringFormat("%04d-%02d:%d ", y, m, bars);
         }
         else
         {
            months_empty++;
            monthline += StringFormat("%04d-%02d:0 ", y, m);
         }
      }
   }

   Rpt("  [下载后] 有数据月份=" + (string)months_ok + "  空月份=" + (string)months_empty
       + "  合计M1根数=" + (string)total);
   Rpt("  真实可用范围: " + (g_first > 0 ? TimeToString(g_first, TIME_DATE|TIME_MINUTES) : "none")
       + "  ~  " + (g_last > 0 ? TimeToString(g_last, TIME_DATE|TIME_MINUTES) : "none"));
   Rpt("  逐月根数: " + monthline);

   // ---- 各周期都摸一遍，触发下载 ----
   ENUM_TIMEFRAMES tfs[] = {PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_D1};
   string tfn[] = {"M5", "M15", "H1", "D1"};
   string tfline = "  [各周期] ";
   for(int i = 0; i < 4; i++)
   {
      SeriesInfoInteger(sym, tfs[i], SERIES_BARS_COUNT);
      datetime f0 = (datetime)SeriesInfoInteger(sym, tfs[i], SERIES_FIRSTDATE);
      long n0 = SeriesInfoInteger(sym, tfs[i], SERIES_BARS_COUNT);
      tfline += tfn[i] + "=" + (string)n0
                + "(" + (f0 > 0 ? TimeToString(f0, TIME_DATE) : "none") + ")  ";
   }
   Rpt(tfline);
}

//+------------------------------------------------------------------+
void OnStart()
{
   string header = "=== dsh_DownloadHistory " + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + " ===";
   Print("dsh: ", header);

   string syms[];
   int n = StringSplit(InpSymbols, ',', syms);
   for(int i = 0; i < n; i++)
   {
      string s = syms[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(StringLen(s) == 0) continue;
      ProbeSymbol(s);
   }

   // 写报告（用 shared 便于多进程，但这里普通写即可）
   g_report = FileOpen("dshtools\\download_report.txt",
                       FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(g_report != INVALID_HANDLE)
   {
      FileWriteString(g_report, header + "\n" + g_log);
      FileClose(g_report);
      Print("dsh: report -> MQL5\\Files\\dshtools\\download_report.txt");
   }
   else
      Print("dsh: cannot write report err=", GetLastError());
}
//+------------------------------------------------------------------+
