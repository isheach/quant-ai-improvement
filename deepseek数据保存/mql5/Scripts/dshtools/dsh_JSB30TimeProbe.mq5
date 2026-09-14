//+------------------------------------------------------------------+
//|  dsh_JSB30TimeProbe.mq5 — 服务器时间只读探针（第一层：实时终端）    |
//|                                                                  |
//|  GPT 裁定：不能再用"周日固定 22:00 UTC 开市"反推 server offset，   |
//|  因为外汇市场周界本身随 DST 改变。必须先实测 server_time - UTC。    |
//|                                                                  |
//|  只读：不下单、不改配置、不写行情数据。                            |
//|  输出：Common\Files\dshtrend\JSB30TIME\instant_probe.txt          |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property script_show_inputs

input int InpSamples = 5;      // 连续采样次数
input int InpSleepMs = 1500;   // 每次间隔

void OnStart()
{
   string dir = "dshtrend\\JSB30TIME";
   FolderCreate("dshtrend", FILE_COMMON);
   FolderCreate(dir, FILE_COMMON);
   string fn = dir + "\\instant_probe.txt";
   int fh = FileOpen(fn, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh == INVALID_HANDLE) fh = FileOpen(fn, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(fh == INVALID_HANDLE) { Print("timeprobe: 无法写文件"); return; }

   FileWrite(fh, "=== dsh_JSB30TimeProbe (instant, live terminal) ===");
   FileWrite(fh, "terminal_build=" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)));
   FileWrite(fh, "terminal_company=" + TerminalInfoString(TERMINAL_COMPANY));
   FileWrite(fh, "account_server=" + AccountInfoString(ACCOUNT_SERVER));
   FileWrite(fh, "account_login=" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)));
   FileWrite(fh, "symbol=" + _Symbol);
   FileWrite(fh, "local_time_pc=" + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS));
   FileWrite(fh, "columns: idx | TimeCurrent(server) | TimeTradeServer | TimeGMT | pc_local | "
                 "server-minus-GMT_sec | tradeServer-minus-GMT_sec | pcUtc-minus-GMT_sec");
   FileWrite(fh, "");

   for(int i = 0; i < InpSamples; i++)
   {
      datetime tCur = TimeCurrent();
      datetime tTrd = TimeTradeServer();
      datetime tGmt = TimeGMT();
      datetime tLoc = TimeLocal();
      long dSrv = (long)tCur - (long)tGmt;
      long dTrd = (long)tTrd - (long)tGmt;
      // 本机 UTC：用 TimeGMT 与 TimeLocal 的差推本机时区
      long dLoc = (long)tLoc - (long)tGmt;
      FileWrite(fh, StringFormat("%d | %s | %s | %s | %s | %+d | %+d | %+d",
                i,
                TimeToString(tCur, TIME_DATE|TIME_SECONDS),
                TimeToString(tTrd, TIME_DATE|TIME_SECONDS),
                TimeToString(tGmt, TIME_DATE|TIME_SECONDS),
                TimeToString(tLoc, TIME_DATE|TIME_SECONDS),
                (int)dSrv, (int)dTrd, (int)dLoc));
      PrintFormat("TIMEPROBE[%d] server=%s tradeServer=%s GMT=%s local=%s | server-GMT=%+ds tradeServer-GMT=%+ds local-GMT=%+ds",
                  i, TimeToString(tCur, TIME_DATE|TIME_SECONDS),
                  TimeToString(tTrd, TIME_DATE|TIME_SECONDS),
                  TimeToString(tGmt, TIME_DATE|TIME_SECONDS),
                  TimeToString(tLoc, TIME_DATE|TIME_SECONDS),
                  (int)dSrv, (int)dTrd, (int)dLoc);
      if(i < InpSamples - 1) Sleep(InpSleepMs);
   }

   FileWrite(fh, "");
   FileWrite(fh, "note: server_minus_GMT = TimeCurrent() - TimeGMT()  <- 这就是 server_utc_offset");
   FileClose(fh);
   Print("timeprobe: 完成 -> ", fn);
}
//+------------------------------------------------------------------+
