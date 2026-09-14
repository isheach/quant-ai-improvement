//+------------------------------------------------------------------+
//|  dsh_JSB30Probe.mq5  —  数据可用性探针（只读，不交易）             |
//|                                                                  |
//|  目的（GPT JSB30 裁定 §1-Q3）：                                    |
//|    TRAIN 必须从真实可用历史起点开始；若 MT5 实际首个有效 bar 晚于  |
//|    2014-01-14，须【以实际首 bar 为准并登记原因】。                  |
//|                                                                  |
//|  本探针只做一件事：报告 USDJPYm 各周期的真实首/末 bar 与 bar 数。   |
//|  不交易、不下单、不写行情数据。                                     |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property strict

input string InpRunTag = "JSB30PROBE";

void OnInit() { }

void OnTick()
{
   // 只在第一个 tick 记录一次
   static bool done = false;
   if(done) return;
   done = true;

   string fn = "dshtrend\\" + InpRunTag + "\\probe_" + InpRunTag + ".txt";
   int fh = FileOpen(fn, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh == INVALID_HANDLE)
      fh = FileOpen(fn, FILE_WRITE|FILE_TXT|FILE_ANSI);   // worker 沙盒回退
   if(fh == INVALID_HANDLE) { Print("probe: 无法写文件"); return; }

   FileWrite(fh, "=== dsh_JSB30Probe " + _Symbol + " ===");
   FileWrite(fh, "run_tag=" + InpRunTag);
   FileWrite(fh, "server_time_at_probe=" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   FileWrite(fh, "tester_from_to=" + TimeToString((datetime)0) + " / " + TimeToString(TimeCurrent()));

   ENUM_TIMEFRAMES tfs[] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_D1};
   string names[]        = {"M1", "M5", "M15", "M30", "H1", "D1"};

   for(int i = 0; i < ArraySize(tfs); i++)
   {
      int bars = iBars(_Symbol, tfs[i]);
      datetime first = (bars > 0) ? iTime(_Symbol, tfs[i], bars - 1) : 0;
      datetime last  = (bars > 0) ? iTime(_Symbol, tfs[i], 0) : 0;
      FileWrite(fh, StringFormat("tf=%-4s bars=%d first=%s last=%s",
                names[i], bars,
                (first > 0) ? TimeToString(first, TIME_DATE|TIME_MINUTES) : "none",
                (last  > 0) ? TimeToString(last,  TIME_DATE|TIME_MINUTES) : "none"));
      PrintFormat("PROBE %-4s bars=%d first=%s last=%s", names[i], bars,
                  (first > 0) ? TimeToString(first, TIME_DATE|TIME_MINUTES) : "none",
                  (last  > 0) ? TimeToString(last,  TIME_DATE|TIME_MINUTES) : "none");
   }
   FileClose(fh);
}

void OnDeinit(const int reason) { }
//+------------------------------------------------------------------+
