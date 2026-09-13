//+------------------------------------------------------------------+
//|  dsh_VerifyCustom.mq5                                            |
//|  DeepSeek / 新量化策略                                            |
//|                                                                  |
//|  目的：验证 XAUUSD_HIST 自定义品种在「新进程」里到底能看到多少历史。   |
//|        关键点：SeriesInfoInteger(SERIES_BARS_COUNT) 受终端               |
//|        "Max bars in chart" 限制（缓存口径），不等于磁盘上的真实根数。   |
//|        这里用 CopyRates 从目标起点直接取证，才是测试器真正读到的口径。  |
//|                                                                  |
//|  同时复核合约规格（volume_min 等）是否真的写进去了。                   |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property script_show_inputs

input string InpSymbolName = "XAUUSD_HIST";
input string InpOutFile    = "dshtools\\verify_custom.json";
input datetime InpProbeFrom = D'2023.01.01 00:00';

//+------------------------------------------------------------------+
string J(double v, int d) { return DoubleToString(v, d); }
string JI(long v)         { return (string)v; }

void ProbeTF(const string sym, ENUM_TIMEFRAMES tf, const string tfname, string &out)
{
   int cached = (int)SeriesInfoInteger(sym, tf, SERIES_BARS_COUNT);
   datetime c0 = (datetime)SeriesInfoInteger(sym, tf, SERIES_FIRSTDATE);
   datetime c1 = (datetime)SeriesInfoInteger(sym, tf, SERIES_LASTBAR_DATE);

   // 用 CopyRates 从固定起点取证（绕开缓存条数口径）
   MqlRates r[];
   int got = CopyRates(sym, tf, InpProbeFrom, TimeCurrent() + 86400, r);
   int real_n = 0;
   datetime r0 = 0, r1 = 0;
   if(got > 0)
   {
      real_n = got;
      r0 = r[0].time;
      r1 = r[got - 1].time;
   }

   out += "    \"" + tfname + "\": {";
   out += "\"cached_bars\": " + JI(cached) + ", ";
   out += "\"cached_first\": \"" + (c0 > 0 ? TimeToString(c0, TIME_DATE|TIME_MINUTES) : "none") + "\", ";
   out += "\"cached_last\": \""  + (c1 > 0 ? TimeToString(c1, TIME_DATE|TIME_MINUTES) : "none") + "\", ";
   out += "\"copyrates_from_2023_bars\": " + JI(real_n) + ", ";
   out += "\"copyrates_first\": \"" + (r0 > 0 ? TimeToString(r0, TIME_DATE|TIME_MINUTES) : "none") + "\", ";
   out += "\"copyrates_last\": \""  + (r1 > 0 ? TimeToString(r1, TIME_DATE|TIME_MINUTES) : "none") + "\"";
   out += "}";

   Print("dsh: ", tfname, " cached=", cached, " [", TimeToString(c0, TIME_DATE|TIME_MINUTES),
         " .. ", TimeToString(c1, TIME_DATE|TIME_MINUTES), "]",
         "  copyrates=", real_n, " [", TimeToString(r0, TIME_DATE|TIME_MINUTES),
         " .. ", TimeToString(r1, TIME_DATE|TIME_MINUTES), "]");
}

void OnStart()
{
   string sym = InpSymbolName;
   SymbolSelect(sym, true);

   Print("dsh: === VerifyCustom start, symbol=", sym, " ===");

   if(!SymbolInfoDouble(sym, SYMBOL_POINT))
   {
      Print("dsh: symbol not found: ", sym);
      return;
   }

   double csize = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   double tsize = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double tval  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double vmin  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vstep = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmax  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double vlim  = SymbolInfoDouble(sym, SYMBOL_VOLUME_LIMIT);
   int    digs  = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   int    sprd  = (int)SymbolInfoInteger(sym, SYMBOL_SPREAD);
   long   calc  = SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE);
   string curp  = SymbolInfoString(sym, SYMBOL_CURRENCY_PROFIT);
   string curb  = SymbolInfoString(sym, SYMBOL_CURRENCY_BASE);

   string tfs = "";
   ProbeTF(sym, PERIOD_M1,  "M1",  tfs); tfs += ",\n";
   ProbeTF(sym, PERIOD_M5,  "M5",  tfs); tfs += ",\n";
   ProbeTF(sym, PERIOD_M15, "M15", tfs); tfs += ",\n";
   ProbeTF(sym, PERIOD_H1,  "H1",  tfs); tfs += ",\n";
   ProbeTF(sym, PERIOD_D1,  "D1",  tfs); tfs += "\n";

   string j = "{\n";
   j += "  \"symbol\": \"" + sym + "\",\n";
   j += "  \"terminal_build\": " + JI(TerminalInfoInteger(TERMINAL_BUILD)) + ",\n";
   j += "  \"maxbars_setting\": " + JI(TerminalInfoInteger(TERMINAL_MAXBARS)) + ",\n";
   j += "  \"digits\": " + JI(digs) + ",\n";
   j += "  \"point\": " + J(point, 10) + ",\n";
   j += "  \"contract_size\": " + J(csize, 4) + ",\n";
   j += "  \"tick_size\": " + J(tsize, 8) + ",\n";
   j += "  \"tick_value\": " + J(tval, 8) + ",\n";
   j += "  \"volume_min\": " + J(vmin, 4) + ",\n";
   j += "  \"volume_step\": " + J(vstep, 4) + ",\n";
   j += "  \"volume_max\": " + J(vmax, 2) + ",\n";
   j += "  \"volume_limit\": " + J(vlim, 2) + ",\n";
   j += "  \"spread_points\": " + JI(sprd) + ",\n";
   j += "  \"calc_mode\": " + JI(calc) + ",\n";
   j += "  \"currency_base\": \"" + curb + "\",\n";
   j += "  \"currency_profit\": \"" + curp + "\",\n";
   j += "  \"usd_per_1price_unit_0.01lot\": " + J(0.01 * csize, 6) + ",\n";
   j += "  \"timeframes\": {\n" + tfs + "  }\n";
   j += "}\n";

   int fh = FileOpen(InpOutFile, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, j); FileClose(fh); }

   Print("dsh: contract=", DoubleToString(csize, 4), " vmin=", DoubleToString(vmin, 4),
         " vstep=", DoubleToString(vstep, 4), " vmax=", DoubleToString(vmax, 2),
         " tickval=", DoubleToString(tval, 6), " calc=", calc);
   Print("dsh: === VerifyCustom done ===");
}
//+------------------------------------------------------------------+
