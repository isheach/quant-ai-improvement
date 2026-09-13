//+------------------------------------------------------------------+
//|  dsh_MakeHist.mq5                                                |
//|  DeepSeek / 新量化策略 — 从本地 CSV 建自定义品种（带正确执行/保证金口径） |
//|                                                                  |
//|  吸取的教训（全部实测过，别再犯）：                                    |
//|   1) SYMBOL_VOLUME_MIN 必须在 SymbolSelect(sym,true) 之后写，否则读回 0 |
//|   2) 用 SYMBOL_CALC_MODE_CFD 时测试器把 0.01 手按金算成 $1912          |
//|      （=合约量×价格，没除杠杆）→ 每单被拒、整月 0 成交。               |
//|      → 必须用 SYMBOL_CALC_MODE_FOREX                                |
//|   3) TICK_VALUE 只能存常量。本脚本按"参考价"校准，使                    |
//|      tick_value = refPrice × contract × point                       |
//|      这样任何"美元金额 ÷ tick_value → 价格距离"的逻辑在参考价处正确。   |
//|      但本 EA（dsh_TrendCore）只用 TICK_VALUE 做"每手每单位价格"换算，   |
//|      该换算与价格无关，所以这里 TICK_VALUE 的取值对 EA 行为影响很小；   |
//|      仍然按参考价设，保持与真实品种量级一致。                          |
//|   4) 点差用 CSV 里记录的历史等值点差（逐 bar），不再统一成一个常数。      |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "2.00"
#property script_show_inputs

input string InpSymbolName  = "XAUUSD_HIST";
input string InpCsvDir      = "dshtrend";        // Common\Files 下的目录
input string InpCsvFile     = "XAU_M1_all.csv";  // datetime\tO\tH\tL\tC\tvol\tspread(price)
input string InpOutFile     = "dshtrend/makehist_report.txt";
input bool   InpDropFirst   = true;
input int    InpBatchSize   = 20000;

// XAUUSDm 真实规格
#define SPEC_CONTRACT  100.0
#define SPEC_DIGITS    3
#define SPEC_POINT     0.001
#define SPEC_VOLMIN    0.01
#define SPEC_VOLSTEP   0.01
#define SPEC_VOLMAX    200.0

int      g_total=0, g_loaded=0, g_bad=0;
datetime g_first=0, g_last=0;
string   g_log="";
void Rpt(const string s) { Print("dshH: ", s); g_log += s + "\n"; }

//+------------------------------------------------------------------+
bool Setup(const string sym)
{
   if(SymbolSelect(sym, false))
   {
      if(InpDropFirst)
      {
         if(!CustomSymbolDelete(sym)) { Rpt("CustomSymbolDelete 失败 " + (string)GetLastError()); return false; }
         Rpt("已删除旧的自定义品种 " + sym);
      }
      else { Rpt("品种已存在，保留"); return true; }
   }
   if(!CustomSymbolCreate(sym)) { Rpt("CustomSymbolCreate 失败 " + (string)GetLastError()); return false; }
   Rpt("已创建 " + sym);

   CustomSymbolSetString(sym, SYMBOL_PATH, "dshtrend\\" + sym);
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_BASE,   "USD");
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_PROFIT, "USD");
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_MARGIN, "USD");
   CustomSymbolSetString(sym, SYMBOL_DESCRIPTION, "XAUUSDm history (DeepSeek trend research)");

   CustomSymbolSetInteger(sym, SYMBOL_DIGITS, SPEC_DIGITS);
   CustomSymbolSetDouble (sym, SYMBOL_POINT,  SPEC_POINT);
   CustomSymbolSetDouble (sym, SYMBOL_TRADE_TICK_SIZE, SPEC_POINT);
   CustomSymbolSetDouble (sym, SYMBOL_TRADE_CONTRACT_SIZE, SPEC_CONTRACT);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_CALC_MODE, SYMBOL_CALC_MODE_FOREX);  // ★见教训 2
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

   // ★见教训 1：先 select 再写手数
   if(!SymbolSelect(sym, true)) Rpt("SymbolSelect(true) 失败 " + (string)GetLastError());
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_STEP, SPEC_VOLSTEP);
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_MIN,  SPEC_VOLMIN);
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_MAX,  SPEC_VOLMAX);

   // TICK_VALUE：每手每 tick 的账户货币价值 = 合约 × point（USD 计价）
   double tv = SPEC_CONTRACT * SPEC_POINT;   // 100 × 0.001 = 0.1
   CustomSymbolSetDouble(sym, SYMBOL_TRADE_TICK_VALUE, tv);
   Rpt("tick_value = " + DoubleToString(tv, 6));

   CustomSymbolSetInteger(sym, SYMBOL_SPREAD_FLOAT, false);
   CustomSymbolSetInteger(sym, SYMBOL_SPREAD, 200);

   // 再补写一次手数 + select（实测最稳）
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_STEP, SPEC_VOLSTEP);
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_MIN,  SPEC_VOLMIN);
   CustomSymbolSetDouble(sym, SYMBOL_VOLUME_MAX,  SPEC_VOLMAX);
   SymbolSelect(sym, true);

   Sleep(200);
   Rpt("回读 volume_min=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 4)
       + " step=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP), 4)
       + " contract=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE), 2)
       + " tickval=" + DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), 6)
       + " calc=" + (string)SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE));
   return true;
}

//+------------------------------------------------------------------+
bool Load(const string sym)
{
   int h = FileOpen(InpCsvDir + "\\" + InpCsvFile, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
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

      buf[n].time        = t;
      buf[n].open        = (double)StringToDouble(p[1]);
      buf[n].high        = (double)StringToDouble(p[2]);
      buf[n].low         = (double)StringToDouble(p[3]);
      buf[n].close       = (double)StringToDouble(p[4]);
      buf[n].tick_volume = (long)StringToInteger(p[5]);
      buf[n].real_volume = 0;
      buf[n].spread      = (int)MathRound((double)StringToDouble(p[6]) / SPEC_POINT);
      n++;

      if(n >= InpBatchSize)
      {
         if(CustomRatesUpdate(sym, buf) < 0) { Rpt("CustomRatesUpdate 失败 line=" + (string)lines); FileClose(h); return false; }
         if(g_first == 0) g_first = buf[0].time;
         g_last = buf[n-1].time;
         g_loaded += n; n = 0;
      }
   }
   if(n > 0)
   {
      MqlRates tail[]; ArrayResize(tail, n);
      for(int i=0;i<n;i++) tail[i]=buf[i];
      if(CustomRatesUpdate(sym, tail) < 0) { Rpt("CustomRatesUpdate(tail) 失败"); FileClose(h); return false; }
      if(g_first == 0) g_first = tail[0].time;
      g_last = tail[n-1].time;
      g_loaded += n;
   }
   FileClose(h);
   g_total = lines;
   return true;
}

//+------------------------------------------------------------------+
void OnStart()
{
   string sym = InpSymbolName;
   Rpt("=== dsh_MakeHist " + TimeToString(TimeLocal(), TIME_DATE|TIME_SECONDS) + " ===");

   if(!Setup(sym)) { Rpt("setup 失败"); return; }
   if(!Load(sym))  { Rpt("load 失败");  return; }

   ENUM_TIMEFRAMES tfs[] = {PERIOD_M5, PERIOD_M15, PERIOD_H1, PERIOD_D1};
   for(int i=0;i<4;i++) SeriesInfoInteger(sym, tfs[i], SERIES_BARS_COUNT);
   for(int w=0; w<120; w++) { if(SeriesInfoInteger(sym, PERIOD_M1, SERIES_SYNCHRONIZED)) break; Sleep(250); }

   Rpt("csv_lines=" + (string)g_total + " rows_loaded=" + (string)g_loaded + " bad=" + (string)g_bad);
   Rpt("期望范围 " + TimeToString(g_first, TIME_DATE|TIME_MINUTES) + " ~ " + TimeToString(g_last, TIME_DATE|TIME_MINUTES));
   Rpt("回读 M1 bars(缓存口径)=" + (string)SeriesInfoInteger(sym, PERIOD_M1, SERIES_BARS_COUNT));

   int fh = FileOpen(InpOutFile, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, g_log); FileClose(fh); }
   Rpt("=== done ===");
}
//+------------------------------------------------------------------+
