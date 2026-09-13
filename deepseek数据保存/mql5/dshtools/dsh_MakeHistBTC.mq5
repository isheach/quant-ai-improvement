//+------------------------------------------------------------------+
//|  dsh_MakeHistBTC.mq5                                             |
//|  建 USDJPY 自定义品种（参数化版本，与 dsh_MakeHist 同思路）           |
//|                                                                  |
//|  USDJPYm 实测规格：digits=3 point=0.001 contract=100000           |
//|                    volume_min=0.01 volume_step=0.01              |
//|                    tick_value≈0.01 (1手/1point)                 |
//|  → 0.01 手每 point = $0.00649                                     |
//|                                                                  |
//|  保留全部踩坑修正：                                                |
//|   1) VOLUME_MIN 必须在 SymbolSelect(true) 之后写                  |
//|   2) 必须用 SYMBOL_CALC_MODE_FOREX（CFD 会把按金算成 合约量×价格）  |
//|   3) TICK_VALUE 按合约×point 设定                                 |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property script_show_inputs

input string InpSymbolName = "BTCUSD_HIST";
input string InpCsvFile    = "dshtrend\\\\BTC_M1_all.csv";
input string InpOutFile    = "dshtrend/makehist_btc_report.txt";
input bool   InpDropFirst  = true;
input int    InpBatchSize  = 20000;

#define SPEC_CONTRACT  1.0
#define SPEC_DIGITS    2
#define SPEC_POINT     0.01
#define SPEC_VOLMIN    0.01
#define SPEC_VOLSTEP   0.01
#define SPEC_VOLMAX    300.0

int      g_total=0, g_loaded=0, g_bad=0;
datetime g_first=0, g_last=0;
string   g_log="";
void Rpt(const string s) { Print("dshJ: ", s); g_log += s + "\n"; }

bool Setup(const string sym)
{
   if(SymbolSelect(sym, false))
   {
      if(InpDropFirst)
      {
         if(!CustomSymbolDelete(sym)) { Rpt("delete 失败 " + (string)GetLastError()); return false; }
         Rpt("已删除旧的 " + sym);
      }
      else return true;
   }
   if(!CustomSymbolCreate(sym)) { Rpt("create 失败 " + (string)GetLastError()); return false; }
   Rpt("已创建 " + sym);

   CustomSymbolSetString(sym, SYMBOL_PATH, "dshtrend\\" + sym);
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_BASE,   "USD");
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_PROFIT, "USD");
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_MARGIN, "USD");
   CustomSymbolSetString(sym, SYMBOL_DESCRIPTION, "BTCUSDm history (DeepSeek)");

   CustomSymbolSetInteger(sym, SYMBOL_DIGITS, SPEC_DIGITS);
   CustomSymbolSetDouble (sym, SYMBOL_POINT,  SPEC_POINT);
   CustomSymbolSetDouble (sym, SYMBOL_TRADE_TICK_SIZE, SPEC_POINT);
   CustomSymbolSetDouble (sym, SYMBOL_TRADE_CONTRACT_SIZE, SPEC_CONTRACT);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_CALC_MODE, SYMBOL_CALC_MODE_FOREX);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_MODE, SYMBOL_TRADE_MODE_FULL);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_EXEMODE, SYMBOL_TRADE_EXECUTION_INSTANT);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_STOPS_LEVEL, 0);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_FREEZE_LEVEL, 0);
   CustomSymbolSetInteger(sym, SYMBOL_FILLING_MODE, SYMBOL_FILLING_FOK | SYMBOL_FILLING_IOC);
   CustomSymbolSetInteger(sym, SYMBOL_EXPIRATION_MODE, 0);
   CustomSymbolSetDouble (sym, SYMBOL_MARGIN_INITIAL, 0.0);
   CustomSymbolSetDouble (sym, SYMBOL_MARGIN_MAINTENANCE, 0.0);
   CustomSymbolSetInteger(sym, SYMBOL_MARGIN_HEDGED_USE_LEG, 0);
   CustomSymbolSetInteger(sym, SYMBOL_SWAP_MODE, SYMBOL_SWAP_MODE_DISABLED);
   CustomSymbolSetDouble (sym, SYMBOL_SWAP_LONG, 0.0);
   CustomSymbolSetDouble (sym, SYMBOL_SWAP_SHORT, 0.0);
   CustomSymbolSetInteger(sym, SYMBOL_CHART_MODE, SYMBOL_CHART_MODE_BID);

   if(!SymbolSelect(sym, true)) Rpt("select 失败 " + (string)GetLastError());
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_STEP, SPEC_VOLSTEP);
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_MIN,  SPEC_VOLMIN);
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_MAX,  SPEC_VOLMAX);

   // ★TICK_VALUE 必须让 "每手每单位价格变动的 USD 价值" 与真实 USDJPYm 一致。
   //   真实 USDJPYm 实测：tick_value≈0.01, tick_size=0.001
   //     → 每手每 1.0 价格单位 = 0.01 / 0.001 = 648.9 USD
   //     → 0.01 手每 1.0 价格单位 = $6.489
   //   （对照黄金：0.01 手每 $1 价格 = $1.00 → JPY 的风险粒度细得多）
   double tv = 0.01;
   CustomSymbolSetDouble(sym, SYMBOL_TRADE_TICK_VALUE, tv);
   Rpt("tick_value 设定 = " + DoubleToString(tv, 6)
       + "  → 每手每1.0价格单位 = " + DoubleToString(tv / SPEC_POINT, 2) + " USD"
       + "  → 0.01手每1.0价格单位 = " + DoubleToString(0.01 * tv / SPEC_POINT, 4) + " USD");

   CustomSymbolSetInteger(sym, SYMBOL_SPREAD_FLOAT, false);
   CustomSymbolSetInteger(sym, SYMBOL_SPREAD, 1540);

   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_STEP, SPEC_VOLSTEP);
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_MIN,  SPEC_VOLMIN);
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_MAX,  SPEC_VOLMAX);
   SymbolSelect(sym, true);

   Sleep(200);
   Rpt("回读 volume_min=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 4)
       + " contract=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE), 2)
       + " tickval=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), 8)
       + " ticksize=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE), 8)
       + " calc=" + (string)SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE));
   return true;
}

bool Load(const string sym)
{
   int h = FileOpen(InpCsvFile, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE) { Rpt("打不开 CSV err=" + (string)GetLastError()); return false; }

   MqlRates buf[];
   ArrayResize(buf, InpBatchSize);
   int n = 0, lines = 0;
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      lines++;
      if(StringLen(line) < 8) continue;
      string p[];
      if(StringSplit(line, '\t', p) < 7) { if(lines==1) continue; g_bad++; continue; }
      datetime t = StringToTime(p[0]);
      if(t <= 0) { if(lines==1) continue; g_bad++; continue; }
      buf[n].time = t;
      buf[n].open  = (double)StringToDouble(p[1]);
      buf[n].high  = (double)StringToDouble(p[2]);
      buf[n].low   = (double)StringToDouble(p[3]);
      buf[n].close = (double)StringToDouble(p[4]);
      buf[n].tick_volume = (long)StringToInteger(p[5]);
      buf[n].real_volume = 0;
      buf[n].spread = (int)MathRound((double)StringToDouble(p[6]) / SPEC_POINT);
      n++;
      if(n >= InpBatchSize)
      {
         if(CustomRatesUpdate(sym, buf) < 0) { Rpt("update 失败 line=" + (string)lines); FileClose(h); return false; }
         if(g_first == 0) g_first = buf[0].time;
         g_last = buf[n-1].time;
         g_loaded += n; n = 0;
      }
   }
   if(n > 0)
   {
      MqlRates tail[]; ArrayResize(tail, n);
      for(int i=0;i<n;i++) tail[i]=buf[i];
      if(CustomRatesUpdate(sym, tail) < 0) { Rpt("update(tail) 失败"); FileClose(h); return false; }
      if(g_first == 0) g_first = tail[0].time;
      g_last = tail[n-1].time;
      g_loaded += n;
   }
   FileClose(h);
   g_total = lines;
   return true;
}

void OnStart()
{
   string sym = InpSymbolName;
   Rpt("=== dsh_MakeHistBTC " + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + " ===");
   if(!Setup(sym)) { Rpt("setup 失败"); return; }
   if(!Load(sym))  { Rpt("load 失败");  return; }
   ENUM_TIMEFRAMES tfs[] = {PERIOD_M5, PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H4, PERIOD_D1};
   for(int i=0;i<6;i++) SeriesInfoInteger(sym, tfs[i], SERIES_BARS_COUNT);
   for(int w=0; w<120; w++) { if(SeriesInfoInteger(sym, PERIOD_M1, SERIES_SYNCHRONIZED)) break; Sleep(250); }
   Rpt("csv_lines=" + (string)g_total + " loaded=" + (string)g_loaded + " bad=" + (string)g_bad);
   Rpt("范围 " + TimeToString(g_first, TIME_DATE|TIME_MINUTES) + " ~ " + TimeToString(g_last, TIME_DATE|TIME_MINUTES));
   int fh = FileOpen(InpOutFile, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, g_log); FileClose(fh); }
   Rpt("=== done ===");
}
//+------------------------------------------------------------------+

