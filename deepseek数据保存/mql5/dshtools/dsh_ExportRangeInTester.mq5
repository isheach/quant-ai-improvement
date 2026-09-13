//+------------------------------------------------------------------+
//|  dsh_ExportRangeInTester.mq5                                     |
//|  DeepSeek / 新量化策略                                            |
//|                                                                  |
//|  ★一次 CopyRates 直接取「整段历史」——比逐 tick 录制快几个数量级。      |
//|                                                                  |
//|  判据：终端图表脚本里 CopyRates 只能拿到约 500,000 根 M1；           |
//|        但在【测试器】里（独立历史通道）能否突破？本 EA 就是来测这个的。 |
//|                                                                  |
//|  成功 → 用这个（秒级）；失败 → 退回 dsh_ExportInTester.mq5（逐 bar 录制）。|
//|                                                                  |
//|  用法：挂到 [Tester]，Symbol=真实品种，Period=M1，任意 FromDate/ToDate |
//|        （本 EA 自己按 InpFrom/InpTo 取数，不依赖回测区间）。          |
//|                                                                  |
//|  输出：Common\Files\dshtools\range_test\                             |
//|          <PREFIX>_<TF>_range.csv   逐月切片导出                      |
//|          <PREFIX>_range_meta.json  各周期实际拿到的范围与根数          |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property script_show_inputs

input string   InpPrefix   = "RANGE";
input datetime InpFrom     = D'2023.01.01';
input datetime InpTo       = D'2026.09.11';
input bool     InpDoM1     = true;
input bool     InpDoM5     = true;
input bool     InpDoM15    = false;
input bool     InpDoH1     = false;
input bool     InpDoD1     = false;
input int      InpSleepMs  = 300;     // 每月之间的等待（下载是异步的）

string g_dir  = "dshtools\\range_test\\";
string g_meta = "";

//+------------------------------------------------------------------+
bool ExportTF(const string sym, ENUM_TIMEFRAMES tf, const string tag,
              datetime from, datetime to)
{
   string fname = g_dir + InpPrefix + "_" + tag + "_range.csv";
   int h = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(h == INVALID_HANDLE)
   {
      g_meta += "    \"" + tag + "\": {\"error\": \"cannot open file\"},\n";
      return false;
   }
   FileWrite(h, "time", "time_iso", "open", "high", "low", "close",
             "tick_volume", "spread", "real_volume");

   long total = 0;
   datetime first = 0, last = 0;
   int months_ok = 0;

   MqlDateTime s; TimeToStruct(from, s);
   MqlDateTime e; TimeToStruct(to, e);
   int cy = s.year, cm = s.mon;

   while(cy < e.year || (cy == e.year && cm <= e.mon))
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
      int got = 0;
      for(int round = 0; round < 4; round++)
      {
         got = CopyRates(sym, tf, cs, ce, r);
         if(got > 0) break;
         Sleep(InpSleepMs);
      }
      if(got > 0)
      {
         for(int i = 0; i < got; i++)
            FileWrite(h,
                      (string)r[i].time,
                      TimeToString(r[i].time, TIME_DATE|TIME_SECONDS),
                      DoubleToString(r[i].open,  _Digits),
                      DoubleToString(r[i].high,  _Digits),
                      DoubleToString(r[i].low,   _Digits),
                      DoubleToString(r[i].close, _Digits),
                      (string)r[i].tick_volume,
                      (string)r[i].spread,
                      (string)r[i].real_volume);
         total += got;
         months_ok++;
         if(first == 0) first = r[0].time;
         last = r[got - 1].time;
      }
      cm++;
      if(cm > 12) { cm = 1; cy++; }
      Sleep(20);
   }

   FileClose(h);

   g_meta += "    \"" + tag + "\": {\"bars\": " + (string)total
             + ", \"months_ok\": " + (string)months_ok
             + ", \"first\": \"" + (first > 0 ? TimeToString(first, TIME_DATE|TIME_MINUTES) : "") + "\""
             + ", \"last\": \""  + (last  > 0 ? TimeToString(last,  TIME_DATE|TIME_MINUTES) : "") + "\""
             + ", \"file\": \"" + fname + "\"},\n";
   Print("dshR: ", tag, " bars=", total, " months_ok=", months_ok,
         " [", TimeToString(first, TIME_DATE|TIME_MINUTES), " ~ ",
         TimeToString(last, TIME_DATE|TIME_MINUTES), "]");
   return total > 0;
}

//+------------------------------------------------------------------+
void OnTick() { }   // 本 EA 只做导出，不交易

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   int fh = FileOpen(g_dir + InpPrefix + "_range_meta.json",
                     FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(fh != INVALID_HANDLE)
   {
      FileWriteString(fh, "{\n  \"symbol\": \"" + _Symbol + "\",\n"
                          + "  \"requested_from\": \"" + TimeToString(InpFrom, TIME_DATE) + "\",\n"
                          + "  \"requested_to\": \"" + TimeToString(InpTo, TIME_DATE) + "\",\n"
                          + "  \"timeframes\": {\n" + g_meta + "    \"_\": {}\n  }\n}\n");
      FileClose(fh);
   }
   Print("dshR: === range export done ===");
}

//+------------------------------------------------------------------+
int OnInit()
{
   Print("dshR: === ExportRangeInTester === symbol=", _Symbol,
         " from=", TimeToString(InpFrom, TIME_DATE),
         " to=", TimeToString(InpTo, TIME_DATE));
   Print("dshR: tester TimeCurrent at init = ", TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES));

   if(InpDoM1)  ExportTF(_Symbol, PERIOD_M1,  "M1",  InpFrom, InpTo);
   if(InpDoM5)  ExportTF(_Symbol, PERIOD_M5,  "M5",  InpFrom, InpTo);
   if(InpDoM15) ExportTF(_Symbol, PERIOD_M15, "M15", InpFrom, InpTo);
   if(InpDoH1)  ExportTF(_Symbol, PERIOD_H1,  "H1",  InpFrom, InpTo);
   if(InpDoD1)  ExportTF(_Symbol, PERIOD_D1,  "D1",  InpFrom, InpTo);

   // 导出完就结束（回测区间设得很短，避免浪费时间走 tick）
   ExpertRemove();
   return INIT_SUCCEEDED;
}
//+------------------------------------------------------------------+
