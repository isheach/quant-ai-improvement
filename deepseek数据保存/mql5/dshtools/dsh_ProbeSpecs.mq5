//+------------------------------------------------------------------+
//|  dsh_ProbeSpecs.mq5                                              |
//|  DeepSeek toolchain probe.                                        |
//|  Purpose: run inside MT5 to dump exact contract specs and the     |
//|  available history range for the symbols this project needs.      |
//|  Writes JSON to the terminal's MQL5\Files\dshtools\ folder.       |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property script_show_inputs

input string InpOutFile = "dshtools\\specs.json";

void OnStart()
{
   string syms[] = {"XAUUSDm","XAUUSD","BTCUSDm","BTCUSD","USDJPYm","USDJPY","USDJPYc","EURUSDm"};
   int n = ArraySize(syms);

   string j = "{\n";
   j += "  \"terminal_build\": \"" + (string)TerminalInfoInteger(TERMINAL_BUILD) + "\",\n";
   j += "  \"company\": \"" + TerminalInfoString(TERMINAL_COMPANY) + "\",\n";
   j += "  \"server\": \"" + AccountInfoString(ACCOUNT_SERVER) + "\",\n";
   j += "  \"account_currency\": \"" + AccountInfoString(ACCOUNT_CURRENCY) + "\",\n";
   j += "  \"account_leverage\": " + (string)AccountInfoInteger(ACCOUNT_LEVERAGE) + ",\n";
   j += "  \"account_trade_mode\": " + (string)AccountInfoInteger(ACCOUNT_TRADE_MODE) + ",\n";
   j += "  \"account_balance\": " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",\n";
   j += "  \"symbols\": [\n";

   int written = 0;
   for(int i = 0; i < n; i++)
   {
      string s = syms[i];
      bool sel = SymbolSelect(s, true);
      bool ok  = SymbolInfoDouble(s, SYMBOL_POINT) > 0.0;
      if(!sel || !ok)
      {
         continue;
      }

      double point   = SymbolInfoDouble(s, SYMBOL_POINT);
      int    digits  = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
      double tickval = SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE);
      double ticksize= SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE);
      double vmin    = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN);
      double vstep   = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
      double vmax    = SymbolInfoDouble(s, SYMBOL_VOLUME_MAX);
      double csize   = SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE);
      double margin_init = SymbolInfoDouble(s, SYMBOL_MARGIN_INITIAL);
      long   spread  = SymbolInfoInteger(s, SYMBOL_SPREAD);
      long   stopslvl= SymbolInfoInteger(s, SYMBOL_TRADE_STOPS_LEVEL);
      long   freeze  = SymbolInfoInteger(s, SYMBOL_TRADE_FREEZE_LEVEL);
      double swap_long  = SymbolInfoDouble(s, SYMBOL_SWAP_LONG);
      double swap_short = SymbolInfoDouble(s, SYMBOL_SWAP_SHORT);
      double bid = SymbolInfoDouble(s, SYMBOL_BID);
      double ask = SymbolInfoDouble(s, SYMBOL_ASK);

      // ---- history availability, per timeframe ----
      ENUM_TIMEFRAMES tfs[] = {PERIOD_M1, PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_D1};
      string tfname[]        = {"M1","M5","M15","H1","D1"};
      string hist = "";
      for(int k = 0; k < 5; k++)
      {
         datetime t0 = (datetime)SeriesInfoInteger(s, tfs[k], SERIES_FIRSTDATE);
         datetime t1 = (datetime)SeriesInfoInteger(s, tfs[k], SERIES_LASTBAR_DATE);
         int bars    = (int)SeriesInfoInteger(s, tfs[k], SERIES_BARS_COUNT);
         if(k > 0) hist += ",";
         hist += "\"" + tfname[k] + "\":{\"bars\":" + (string)bars
               + ",\"first\":\"" + (t0 > 0 ? TimeToString(t0, TIME_DATE|TIME_MINUTES) : "none") + "\""
               + ",\"last\":\""  + (t1 > 0 ? TimeToString(t1, TIME_DATE|TIME_MINUTES) : "none") + "\"}";
      }

      if(written > 0) j += ",\n";
      j += "    {\n";
      j += "      \"name\": \"" + s + "\",\n";
      j += "      \"digits\": " + (string)digits + ",\n";
      j += "      \"point\": " + DoubleToString(point, 10) + ",\n";
      j += "      \"contract_size\": " + DoubleToString(csize, 4) + ",\n";
      j += "      \"tick_value\": " + DoubleToString(tickval, 8) + ",\n";
      j += "      \"tick_size\": " + DoubleToString(ticksize, 10) + ",\n";
      j += "      \"volume_min\": " + DoubleToString(vmin, 4) + ",\n";
      j += "      \"volume_step\": " + DoubleToString(vstep, 4) + ",\n";
      j += "      \"volume_max\": " + DoubleToString(vmax, 2) + ",\n";
      j += "      \"margin_initial\": " + DoubleToString(margin_init, 4) + ",\n";
      j += "      \"spread_points\": " + (string)spread + ",\n";
      j += "      \"stops_level_points\": " + (string)stopslvl + ",\n";
      j += "      \"freeze_level_points\": " + (string)freeze + ",\n";
      j += "      \"swap_long\": " + DoubleToString(swap_long, 4) + ",\n";
      j += "      \"swap_short\": " + DoubleToString(swap_short, 4) + ",\n";
      j += "      \"bid\": " + DoubleToString(bid, digits) + ",\n";
      j += "      \"ask\": " + DoubleToString(ask, digits) + ",\n";
      j += "      \"usd_per_point_per_1lot\": " + DoubleToString(tickval / (ticksize / point), 6) + ",\n";
      j += "      \"usd_per_point_per_0.01lot\": " + DoubleToString(0.01 * tickval / (ticksize / point), 6) + ",\n";
      j += "      \"history\": {" + hist + "}\n";
      j += "    }";
      written++;
   }

   j += "\n  ]\n}\n";

   int h = FileOpen(InpOutFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("dsh probe: cannot open output file, err=", GetLastError());
      return;
   }
   FileWriteString(h, j);
   FileClose(h);
   Print("dsh probe: wrote ", written, " symbols to ", InpOutFile);
}
//+------------------------------------------------------------------+
