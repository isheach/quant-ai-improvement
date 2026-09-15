//+------------------------------------------------------------------+
//| dsh_XAMR30_TradingCalendar.mq5                                   |
//| Data-only USDJPYm M30 timestamp probe for V1 evidence repair.     |
//| This helper never loads the strategy and never sends trade calls.  |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"

input string   InpOutputTag = "DS260914_XAMR30_TRADING_CALENDAR";
input datetime InpFrom      = D'2018.01.01 00:00';
input datetime InpTo        = D'2024.06.01 00:00';

string OutputDir()
{
   return "dshtrend\\" + InpOutputTag + "\\";
}

string Stamp(const datetime value)
{
   return TimeToString(value, TIME_DATE | TIME_MINUTES | TIME_SECONDS);
}

//+------------------------------------------------------------------+
int OnInit()
{
   if(!SymbolSelect(_Symbol, true))
   {
      Print("CALENDAR_PROBE symbol selection failed: ", _Symbol);
      return INIT_FAILED;
   }

   MqlRates rates[];
   int got = 0;
   for(int attempt = 0; attempt < 5; attempt++)
   {
      got = CopyRates(_Symbol, PERIOD_M30, InpFrom, InpTo - 1, rates);
      if(got > 0)
         break;
      Sleep(250);
   }

   int meta = FileOpen(OutputDir() + "calendar_meta.txt",
                       FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(meta != INVALID_HANDLE)
   {
      FileWriteString(meta, "probe_kind=data_only_usdjpy_m30\n");
      FileWriteString(meta, "symbol=" + _Symbol + "\n");
      FileWriteString(meta, "timeframe=M30\n");
      FileWriteString(meta, "requested_from=" + Stamp(InpFrom) + "\n");
      FileWriteString(meta, "requested_to_exclusive=" + Stamp(InpTo) + "\n");
      FileWriteString(meta, "bars_returned=" + (string)got + "\n");
      FileWriteString(meta, "strategy_loaded=false\n");
      FileWriteString(meta, "trade_calls=false\n");
      FileClose(meta);
   }

   if(got <= 0)
   {
      Print("CALENDAR_PROBE CopyRates returned no bars");
      ExpertRemove();
      return INIT_SUCCEEDED;
   }

   int out = FileOpen(OutputDir() + "calendar.csv",
                      FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(out == INVALID_HANDLE)
   {
      Print("CALENDAR_PROBE output open failed: ", GetLastError());
      ExpertRemove();
      return INIT_SUCCEEDED;
   }

   FileWrite(out, "bar_open_time", "utc_date");
   int written = 0;
   datetime first = 0;
   datetime last = 0;
   for(int i = 0; i < got; i++)
   {
      if(rates[i].time < InpFrom || rates[i].time >= InpTo)
         continue;
      string stamp = Stamp(rates[i].time);
      string day = StringSubstr(stamp, 0, 10);
      StringReplace(day, ".", "-");
      FileWrite(out, stamp, day);
      if(first == 0)
         first = rates[i].time;
      last = rates[i].time;
      written++;
   }
   FileClose(out);

   meta = FileOpen(OutputDir() + "calendar_meta.txt",
                   FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(meta != INVALID_HANDLE)
   {
      FileWriteString(meta, "probe_kind=data_only_usdjpy_m30\n");
      FileWriteString(meta, "symbol=" + _Symbol + "\n");
      FileWriteString(meta, "timeframe=M30\n");
      FileWriteString(meta, "requested_from=" + Stamp(InpFrom) + "\n");
      FileWriteString(meta, "requested_to_exclusive=" + Stamp(InpTo) + "\n");
      FileWriteString(meta, "bars_returned=" + (string)got + "\n");
      FileWriteString(meta, "bars_written=" + (string)written + "\n");
      FileWriteString(meta, "first_bar=" + (first > 0 ? Stamp(first) : "") + "\n");
      FileWriteString(meta, "last_bar=" + (last > 0 ? Stamp(last) : "") + "\n");
      FileWriteString(meta, "strategy_loaded=false\n");
      FileWriteString(meta, "trade_calls=false\n");
      FileClose(meta);
   }

   Print("CALENDAR_PROBE completed bars_returned=", got,
         " bars_written=", written,
         " first=", Stamp(first), " last=", Stamp(last));
   ExpertRemove();
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Deliberately empty: this is a data-only probe.
}

void OnDeinit(const int reason)
{
   Print("CALENDAR_PROBE deinit reason=", reason);
}
//+------------------------------------------------------------------+
