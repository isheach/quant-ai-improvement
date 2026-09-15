//+------------------------------------------------------------------+
//| dsh_XAMR30_TradingCalendar_R2.mq5                                |
//| Standalone USDJPYm M30 data-only calendar probe.                  |
//| It does not load the XAMR30 strategy and contains no trade API.    |
//+------------------------------------------------------------------+
#property strict
#property version   "2.00"

input string   InpRunTag = "DS260915_XAMR30_TRAIN_CALENDAR_R2";
input datetime InpFrom  = D'2018.01.01 00:00';
input datetime InpTo    = D'2024.05.31 23:59:59';

string CsvPath()
{
   return "dshtrend\\XAMR30_TRAIN_CALENDAR_R2\\calendar.csv";
}

string MetaPath()
{
   return "dshtrend\\XAMR30_TRAIN_CALENDAR_R2\\calendar_meta.txt";
}

string Stamp(const datetime value)
{
   if(value <= 0)
      return "";
   return TimeToString(value, TIME_DATE | TIME_MINUTES | TIME_SECONDS);
}

string DayStamp(const datetime value)
{
   string day = TimeToString(value, TIME_DATE);
   StringReplace(day, ".", "-");
   return day;
}

void WriteMeta(const string status,
               const int m30_bars,
               const int trading_days,
               const datetime first_bar,
               const datetime last_bar,
               const string first_day,
               const string last_day,
               const int duplicate_timestamps,
               const int non_monotonic_timestamps,
               const int outside_train,
               const int csv_write_ok,
               const int meta_write_ok,
               const int csv_error,
               const int meta_error,
               const int folder_error)
{
   ResetLastError();
   int h = FileOpen(MetaPath(), FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE)
   {
      PrintFormat("CALENDAR_R2_META_OPEN_FAIL error=%d", GetLastError());
      return;
   }

   FileWriteString(h, "run_tag=" + InpRunTag + "\n");
   FileWriteString(h, "status=" + status + "\n");
   FileWriteString(h, "symbol=" + _Symbol + "\n");
   FileWriteString(h, "period=M30\n");
   FileWriteString(h, "requested_from=" + Stamp(InpFrom) + "\n");
   FileWriteString(h, "requested_to=" + Stamp(InpTo) + "\n");
   FileWriteString(h, "timestamp_time_basis=server_utc_as_frozen_audit\n");
   FileWriteString(h, "m30_bar_count=" + (string)m30_bars + "\n");
   FileWriteString(h, "trading_day_count=" + (string)trading_days + "\n");
   FileWriteString(h, "first_m30_timestamp=" + Stamp(first_bar) + "\n");
   FileWriteString(h, "last_m30_timestamp=" + Stamp(last_bar) + "\n");
   FileWriteString(h, "first_trading_date=" + first_day + "\n");
   FileWriteString(h, "last_trading_date=" + last_day + "\n");
   FileWriteString(h, "duplicate_timestamp_count=" + (string)duplicate_timestamps + "\n");
   FileWriteString(h, "non_monotonic_timestamp_count=" + (string)non_monotonic_timestamps + "\n");
   FileWriteString(h, "outside_train_timestamp_count=" + (string)outside_train + "\n");
   FileWriteString(h, "calendar_csv_write_ok=" + (string)csv_write_ok + "\n");
   FileWriteString(h, "calendar_meta_write_ok=" + (string)meta_write_ok + "\n");
   FileWriteString(h, "calendar_csv_error=" + (string)csv_error + "\n");
   FileWriteString(h, "calendar_meta_error=" + (string)meta_error + "\n");
   FileWriteString(h, "folder_create_error=" + (string)folder_error + "\n");
   FileWriteString(h, "strategy_loaded=false\n");
   FileWriteString(h, "trade_api_calls=false\n");
   FileFlush(h);
   FileClose(h);
}

//+------------------------------------------------------------------+
int OnInit()
{
   ResetLastError();
   bool folder_created = FolderCreate("dshtrend\\XAMR30_TRAIN_CALENDAR_R2", FILE_COMMON);
   int folder_error = folder_created ? 0 : GetLastError();

   if(!SymbolSelect(_Symbol, true))
   {
      PrintFormat("CALENDAR_R2_SYMBOL_FAIL error=%d", GetLastError());
      WriteMeta("FAIL", 0, 0, 0, 0, "", "", 0, 0, 0, 0, 0, 0, 0, folder_error);
      ExpertRemove();
      return INIT_SUCCEEDED;
   }

   MqlRates rates[];
   ResetLastError();
   int got = CopyRates(_Symbol, PERIOD_M30, InpFrom, InpTo, rates);
   int copy_error = (got < 0) ? GetLastError() : 0;
   if(got < 0)
      got = 0;

   string days[];
   int day_counts[];
   ArrayResize(days, 0);
   ArrayResize(day_counts, 0);

   datetime first_bar = 0;
   datetime last_bar = 0;
   datetime previous = 0;
   int duplicate_timestamps = 0;
   int non_monotonic_timestamps = 0;
   int outside_train = 0;
   int m30_bars = 0;

   for(int i = 0; i < got; i++)
   {
      datetime stamp = rates[i].time;
      if(stamp < InpFrom || stamp > InpTo)
      {
         outside_train++;
         continue;
      }
      if(previous > 0)
      {
         if(stamp == previous)
            duplicate_timestamps++;
         if(stamp <= previous)
            non_monotonic_timestamps++;
      }
      previous = stamp;
      if(first_bar == 0)
         first_bar = stamp;
      last_bar = stamp;
      m30_bars++;

      string day = DayStamp(stamp);
      int day_index = ArraySize(days) - 1;
      if(day_index < 0 || days[day_index] != day)
      {
         int next = ArraySize(days);
         ArrayResize(days, next + 1);
         ArrayResize(day_counts, next + 1);
         days[next] = day;
         day_counts[next] = 1;
      }
      else
      {
         day_counts[day_index]++;
      }
   }

   int csv_error = 0;
   int csv_write_ok = 0;
   ResetLastError();
   int csv = FileOpen(CsvPath(), FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(csv == INVALID_HANDLE)
   {
      csv_error = GetLastError();
      PrintFormat("CALENDAR_R2_FILEOPEN_FAIL error=%d", csv_error);
   }
   else
   {
      FileWrite(csv, "utc_date", "jpy_m30_bar_count");
      for(int d = 0; d < ArraySize(days); d++)
         FileWrite(csv, days[d], day_counts[d]);
      FileFlush(csv);
      FileClose(csv);
      ResetLastError();
      int verify = FileOpen(CsvPath(), FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
      if(verify == INVALID_HANDLE)
      {
         csv_error = GetLastError();
         PrintFormat("CALENDAR_R2_FILEVERIFY_FAIL error=%d", csv_error);
      }
      else
      {
         FileClose(verify);
         csv_write_ok = FileIsExist(CsvPath(), FILE_COMMON) ? 1 : 0;
      }
   }

   int meta_error = 0;
   int meta_write_ok = 0;
   string status = (m30_bars > 0
                    && ArraySize(days) > 0
                    && duplicate_timestamps == 0
                    && non_monotonic_timestamps == 0
                    && outside_train == 0
                    && csv_write_ok == 1) ? "PASS" : "FAIL";
   WriteMeta(status, m30_bars, ArraySize(days), first_bar, last_bar,
             ArraySize(days) > 0 ? days[0] : "",
             ArraySize(days) > 0 ? days[ArraySize(days) - 1] : "",
             duplicate_timestamps, non_monotonic_timestamps, outside_train,
             csv_write_ok, 1, csv_error, meta_error,
             copy_error != 0 ? copy_error : folder_error);
   meta_write_ok = FileIsExist(MetaPath(), FILE_COMMON) ? 1 : 0;

   if(status != "PASS" || meta_write_ok != 1)
      PrintFormat("CALENDAR_R2_STATUS_FAIL status=%s csv=%d meta=%d copy_error=%d folder_error=%d",
                  status, csv_write_ok, meta_write_ok, copy_error, folder_error);
   else
      PrintFormat("CALENDAR_R2_STATUS_PASS m30_bars=%d trading_days=%d first=%s last=%s",
                  m30_bars, ArraySize(days), Stamp(first_bar), Stamp(last_bar));

   ExpertRemove();
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Data-only helper: no strategy logic and no trade operations.
}

void OnDeinit(const int reason)
{
   PrintFormat("CALENDAR_R2_DEINIT reason=%d", reason);
}
//+------------------------------------------------------------------+
