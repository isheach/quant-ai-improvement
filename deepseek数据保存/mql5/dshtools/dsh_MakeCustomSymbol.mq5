//+------------------------------------------------------------------+
//|  dsh_MakeCustomSymbol.mq5                                        |
//|  DeepSeek / 新量化策略                                            |
//|                                                                  |
//|  目的：在 MT5 里建立一个「历史完整」的自定义品种，用于策略测试器。      |
//|        旧项目有 2023-01 ~ 2026-06 共 42 个月真实 XAUUSDm M1，         |
//|        而终端自带历史只有 5 周 —— 这是当前研究的第一瓶颈。             |
//|                                                                  |
//|  ★关键设计 1：EA（eva028）完全靠 SymbolInfoDouble 推导点值/缩放，      |
//|    不硬编码品种名。自定义品种只要合约规格与 XAUUSDm 一致              |
//|    （contract=100 oz / digits=3 / volume_min=0.01），                |
//|    导入真实价位后其美元行为与 XAUUSDm 完全一致：                      |
//|        0.01 手 = 1 oz  →  $1 金价波动 = $1 盈亏                      |
//|                                                                  |
//|  ★关键设计 2（TICK_VALUE 的取舍，必须读）：                           |
//|    EA 唯一使用 TICK_VALUE 的地方是「末单止损距离换算」：               |
//|        loss_dist = InpLastOrderLossPerLot × tick_size / tick_value   |
//|    真实 XAUUSDm 的 TICK_VALUE 随现价变化（= price × 0.1）。           |
//|    但 MT5 自定义品种的 TICK_VALUE 是「存储的常量」，不能随历史价变化。  |
//|    42 个月里金价从 1804 走到 5595（3.1 倍），所以只能选一个口径。      |
//|    → 本项目选「按 InpRefTickValuePrice 校准」：                      |
//|        tick_value = ref_price × contract × point                     |
//|    这样在 ref_price 附近，所有「美元金额参数」与真实 XAUUSDm 完全对等； |
//|    而且由于网格距离本身按 price/InpRefPrice 缩放，整篮止损的触发位置   |
//|    在各价位保持自洽。这是「固定美元风控」，对 500 本金是正确口径。      |
//|                                                                  |
//|  输入文件：MQL5\Files\dshtools\XAUUSD_HIST_M1.csv                    |
//|     列: datetime \t open \t high \t low \t close \t tick_volume \t  |
//|         spread(price units, = points*0.001)                          |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.10"
#property script_show_inputs

input string InpSymbolName  = "XAUUSD_HIST";       // 自定义品种名
input string InpCsvFile     = "dshtools\\XAUUSD_HIST_M1.csv";
input string InpOutFile     = "dshtools\\custom_symbol_report.json";
input bool   InpDropFirst   = true;                // 已存在则先删除重建
input int    InpBatchSize   = 20000;               // CustomRatesUpdate 批大小
input double InpRefTickValuePrice = 4000.0;        // 校准 TICK_VALUE 用的参考价
input int    InpSpreadPoints = 200;                // 固定点差（历史中位）
input bool   InpRunProfitTest = true;              // 做一次「盈亏口径」实测校验

// XAUUSDm 实测规格（specs.json）
#define SPEC_CONTRACT_SIZE   100.0
#define SPEC_DIGITS          3
#define SPEC_POINT           0.001
#define SPEC_VOLUME_MIN      0.01
#define SPEC_VOLUME_STEP     0.01
#define SPEC_VOLUME_MAX      200.0

int      g_total   = 0;
int      g_loaded  = 0;
int      g_badline = 0;
datetime g_first   = 0;
datetime g_last    = 0;

string   g_profit_test = "{}";

//+------------------------------------------------------------------+
string J(double v, int d) { return DoubleToString(v, d); }
string JI(long v)         { return (string)v; }

//+------------------------------------------------------------------+
bool SetupSymbol(const string sym)
{
   if(SymbolSelect(sym, false))
   {
      if(InpDropFirst)
      {
         if(!CustomSymbolDelete(sym))
         {
            Print("dsh: CustomSymbolDelete failed err=", GetLastError());
            return false;
         }
         Print("dsh: deleted existing custom symbol ", sym);
      }
      else
      {
         Print("dsh: custom symbol exists, keeping (InpDropFirst=false)");
         return true;
      }
   }

   if(!CustomSymbolCreate(sym))
   {
      Print("dsh: CustomSymbolCreate failed err=", GetLastError());
      return false;
   }
   Print("dsh: created custom symbol ", sym);

   CustomSymbolSetString(sym, SYMBOL_PATH, "dshtools\\" + sym);
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_BASE,  "USD");
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_PROFIT, "USD");
   CustomSymbolSetString(sym, SYMBOL_CURRENCY_MARGIN, "USD");
   CustomSymbolSetString(sym, SYMBOL_DESCRIPTION, "XAUUSD legacy 42M history (DeepSeek)");

   CustomSymbolSetInteger(sym, SYMBOL_DIGITS,            SPEC_DIGITS);
   CustomSymbolSetDouble (sym, SYMBOL_POINT,             SPEC_POINT);
   CustomSymbolSetDouble (sym, SYMBOL_TRADE_TICK_SIZE,   SPEC_POINT);
   CustomSymbolSetDouble (sym, SYMBOL_TRADE_CONTRACT_SIZE, SPEC_CONTRACT_SIZE);

   // ★实测发现（dsh_VolMinProbe，配方 C 生效）：
   //   VOLUME_MIN 必须在 SymbolSelect(sym,true) 之后、且**不与 VOLUME_LIMIT 一起**
   //   写入才能生效。实测矩阵：
   //     A create+set（未 select）          → vmin=0.0000
   //     B 加 VOLUME_LIMIT=1e6              → vmin=0.0000
   //     C select(true) 之后再 set          → vmin=0.0100  ★
   //     F 完整属性后 set（未 select）       → vmin=0.0000
   //   所以这里有意的顺序是：select → set 手数。
   if(!SymbolSelect(sym, true))
      Print("dsh: SymbolSelect(true) failed err=", GetLastError());

   CustomSymbolSetDouble (sym, SYMBOL_VOLUME_STEP,       SPEC_VOLUME_STEP);
   CustomSymbolSetDouble (sym, SYMBOL_VOLUME_MIN,        SPEC_VOLUME_MIN);
   CustomSymbolSetDouble (sym, SYMBOL_VOLUME_MAX,        SPEC_VOLUME_MAX);

   double tv = InpRefTickValuePrice * SPEC_CONTRACT_SIZE * SPEC_POINT;
   CustomSymbolSetDouble (sym, SYMBOL_TRADE_TICK_VALUE,  tv);
   Print("dsh: tick_value set to ", DoubleToString(tv, 6), " (ref price ",
         DoubleToString(InpRefTickValuePrice, 2), ")");

   CustomSymbolSetInteger(sym, SYMBOL_TRADE_MODE,        SYMBOL_TRADE_MODE_FULL);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_EXEMODE,     SYMBOL_TRADE_EXECUTION_INSTANT);
   // ★★ 保证金口径（2026-09-10 实测修正，关键）：
   //   第一版用 SYMBOL_CALC_MODE_CFD 时，测试器算出的 0.01 手按金是 $1912
   //   （= contract_size × volume × price），而真实 XAUUSDm 只要 $2.19
   //   （= contract_size × volume × price / leverage = 100×0.01×4385/200）。
   //   结果 EA 每一单都被 "not enough money" 拒绝，1 个月 0 笔成交。
   //   → 改用 SYMBOL_CALC_MODE_FOREX + MARGIN_HEDGED_USE_LEG，
   //     保证金 = 合约量/杠杆，与 XAUUSDm 完全一致。
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_CALC_MODE,   SYMBOL_CALC_MODE_FOREX);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_STOPS_LEVEL, 0);
   CustomSymbolSetInteger(sym, SYMBOL_TRADE_FREEZE_LEVEL, 0);
   CustomSymbolSetInteger(sym, SYMBOL_FILLING_MODE,      SYMBOL_FILLING_FOK | SYMBOL_FILLING_IOC);
   CustomSymbolSetInteger(sym, SYMBOL_EXPIRATION_MODE,   0);

   CustomSymbolSetDouble (sym, SYMBOL_MARGIN_INITIAL,     0.0);
   CustomSymbolSetDouble (sym, SYMBOL_MARGIN_MAINTENANCE, 0.0);
   CustomSymbolSetInteger(sym, SYMBOL_MARGIN_HEDGED_USE_LEG, 0);

   // 隔夜利息：暂关（旧项目 swap_long=-534.4 points/lot/day，先不引入第二个变量）
   CustomSymbolSetInteger(sym, SYMBOL_SWAP_MODE,         SYMBOL_SWAP_MODE_DISABLED);
   CustomSymbolSetDouble (sym, SYMBOL_SWAP_LONG,         0.0);
   CustomSymbolSetDouble (sym, SYMBOL_SWAP_SHORT,        0.0);

   CustomSymbolSetInteger(sym, SYMBOL_CHART_MODE,        SYMBOL_CHART_MODE_BID);
   CustomSymbolSetInteger(sym, SYMBOL_SPREAD_FLOAT,      false);
   CustomSymbolSetInteger(sym, SYMBOL_SPREAD,            InpSpreadPoints);

   // 最后再补写一次手数（实测最稳），并回读确认
   CustomSymbolSetDouble (sym, SYMBOL_VOLUME_STEP,       SPEC_VOLUME_STEP);
   CustomSymbolSetDouble (sym, SYMBOL_VOLUME_MIN,        SPEC_VOLUME_MIN);
   CustomSymbolSetDouble (sym, SYMBOL_VOLUME_MAX,        SPEC_VOLUME_MAX);
   if(!SymbolSelect(sym, true))
      Print("dsh: final SymbolSelect(true) failed err=", GetLastError());

   // 立刻回读，确认写入真的生效
   Sleep(200);
   Print("dsh: readback volume_min=", DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN), 4),
         " step=", DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP), 4),
         " max=", DoubleToString(SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX), 2),
         " contract=", DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE), 2),
         " tickval=", DoubleToString(SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE), 6));
   return true;
}

//+------------------------------------------------------------------+
//| 载入 CSV → CustomRatesUpdate                                       |
//+------------------------------------------------------------------+
bool LoadRates(const string sym)
{
   int h = FileOpen(InpCsvFile, FILE_READ | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
   {
      Print("dsh: cannot open ", InpCsvFile, " err=", GetLastError());
      return false;
   }

   MqlRates buf[];
   ArrayResize(buf, InpBatchSize);
   int n = 0;
   int lines = 0;

   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      lines++;
      if(StringLen(line) < 10) continue;

      string p[];
      int np = StringSplit(line, '\t', p);
      if(np < 7)
      {
         if(lines == 1) continue;
         g_badline++;
         continue;
      }

      datetime t = StringToTime(p[0]);
      if(t <= 0)
      {
         if(lines == 1) continue;
         g_badline++;
         continue;
      }

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
         if(CustomRatesUpdate(sym, buf) < 0)
         {
            Print("dsh: CustomRatesUpdate failed at line ", lines, " err=", GetLastError());
            FileClose(h);
            return false;
         }
         if(g_first == 0) g_first = buf[0].time;
         g_last  = buf[n - 1].time;
         g_loaded += n;
         n = 0;
      }
   }

   if(n > 0)
   {
      MqlRates tail[];
      ArrayResize(tail, n);
      for(int i = 0; i < n; i++) tail[i] = buf[i];
      if(CustomRatesUpdate(sym, tail) < 0)
      {
         Print("dsh: CustomRatesUpdate (tail) failed err=", GetLastError());
         FileClose(h);
         return false;
      }
      if(g_first == 0) g_first = tail[0].time;
      g_last = tail[n - 1].time;
      g_loaded += n;
   }

   FileClose(h);
   g_total = lines;
   return true;
}

//+------------------------------------------------------------------+
//| 实测校验：symbol 的「1 美元价格波动 = 多少账户货币」                  |
//|  在测试器里下 0.01 手，价格每动 $1，账户应动 $1。这里用规格反推并交叉验证。|
//+------------------------------------------------------------------+
void ProfitConventionTest(const string sym)
{
   double csize = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   double tsize = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE);
   double tval  = SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE);
   double vmin  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vstep = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double vmax  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   long   calc  = SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE);

   // 合约反推：0.01 手、$1 价格波动 → 应该是 $1.00
   double usd_per_price_1lot  = csize;                    // CFD/简单口径
   double usd_per_price_0_01  = 0.01 * csize;
   // tick_value 口径反推
   double tv_implied_per_price_1lot = (tsize > 0.0) ? (tval / tsize) : 0.0;
   double tv_implied_per_price_0_01 = 0.01 * tv_implied_per_price_1lot;

   // 用真实 M1 首末价做一个「手算盈亏」样本
   MqlRates r[];
   double p_first = 0.0, p_last = 0.0, delta = 0.0;
   if(CopyRates(sym, PERIOD_M1, 0, 1, r) == 1) p_last = r[0].close;
   datetime t0 = (datetime)SeriesInfoInteger(sym, PERIOD_M1, SERIES_FIRSTDATE);
   if(t0 > 0)
   {
      MqlRates r0[];
      if(CopyRates(sym, PERIOD_M1, t0, 1, r0) == 1) p_first = r0[0].close;
   }
   delta = p_last - p_first;

   g_profit_test  = "{\n";
   g_profit_test += "    \"calc_mode\": " + JI(calc) + ",\n";
   g_profit_test += "    \"contract_size\": " + J(csize, 4) + ",\n";
   g_profit_test += "    \"tick_size\": " + J(tsize, 8) + ",\n";
   g_profit_test += "    \"tick_value\": " + J(tval, 8) + ",\n";
   g_profit_test += "    \"volume_min\": " + J(vmin, 4) + ",\n";
   g_profit_test += "    \"volume_step\": " + J(vstep, 4) + ",\n";
   g_profit_test += "    \"volume_max\": " + J(vmax, 2) + ",\n";
   g_profit_test += "    \"contract_implied_usd_per_1price_0.01lot\": " + J(usd_per_price_0_01, 6) + ",\n";
   g_profit_test += "    \"tickvalue_implied_usd_per_1price_0.01lot\": " + J(tv_implied_per_price_0_01, 6) + ",\n";
   g_profit_test += "    \"sample_price_first\": " + J(p_first, 3) + ",\n";
   g_profit_test += "    \"sample_price_last\": " + J(p_last, 3) + ",\n";
   g_profit_test += "    \"sample_delta\": " + J(delta, 3) + "\n";
   g_profit_test += "  }";

   Print("dsh: ---- PROFIT CONVENTION TEST ----");
   Print("dsh: contract=", DoubleToString(csize, 4), " tick_size=", DoubleToString(tsize, 8),
         " tick_value=", DoubleToString(tval, 8));
   Print("dsh: volume_min=", DoubleToString(vmin, 4), " step=", DoubleToString(vstep, 4),
         " max=", DoubleToString(vmax, 2));
   Print("dsh: contract-implied USD per $1 price @0.01lot = ", DoubleToString(usd_per_price_0_01, 6),
         "  (MUST be 1.00)");
   Print("dsh: ---- END PROFIT CONVENTION TEST ----");
}

//+------------------------------------------------------------------+
void OnStart()
{
   Print("dsh: === MakeCustomSymbol start, target=", InpSymbolName, " ===");

   if(!SetupSymbol(InpSymbolName))
   {
      Print("dsh: setup failed, abort");
      return;
   }

   if(!LoadRates(InpSymbolName))
   {
      Print("dsh: load failed, abort");
      return;
   }

   // 建立派生周期（MT5 会从 M1 生成）
   ENUM_TIMEFRAMES tfs[] = {PERIOD_M5, PERIOD_M15, PERIOD_H1};
   for(int i = 0; i < 3; i++)
      SeriesInfoInteger(InpSymbolName, tfs[i], SERIES_BARS_COUNT);

   // 等待 M1 数据同步
   for(int w = 0; w < 120; w++)
   {
      if(SeriesInfoInteger(InpSymbolName, PERIOD_M1, SERIES_SYNCHRONIZED)) break;
      Sleep(250);
   }

   if(InpRunProfitTest)
      ProfitConventionTest(InpSymbolName);

   // ---- 复核：读回来的实际规格 ----
   double csize  = SymbolInfoDouble(InpSymbolName, SYMBOL_TRADE_CONTRACT_SIZE);
   int    digits = (int)SymbolInfoInteger(InpSymbolName, SYMBOL_DIGITS);
   double point  = SymbolInfoDouble(InpSymbolName, SYMBOL_POINT);
   double tsize  = SymbolInfoDouble(InpSymbolName, SYMBOL_TRADE_TICK_SIZE);
   double tval   = SymbolInfoDouble(InpSymbolName, SYMBOL_TRADE_TICK_VALUE);
   double vmin   = SymbolInfoDouble(InpSymbolName, SYMBOL_VOLUME_MIN);
   int    spread = (int)SymbolInfoInteger(InpSymbolName, SYMBOL_SPREAD);

   int m1bars = (int)SeriesInfoInteger(InpSymbolName, PERIOD_M1, SERIES_BARS_COUNT);
   datetime m1first = (datetime)SeriesInfoInteger(InpSymbolName, PERIOD_M1, SERIES_FIRSTDATE);
   datetime m1last  = (datetime)SeriesInfoInteger(InpSymbolName, PERIOD_M1, SERIES_LASTBAR_DATE);
   int m5bars = (int)SeriesInfoInteger(InpSymbolName, PERIOD_M5, SERIES_BARS_COUNT);

   string j = "{\n";
   j += "  \"symbol\": \"" + InpSymbolName + "\",\n";
   j += "  \"csv_file\": \"" + InpCsvFile + "\",\n";
   j += "  \"csv_lines\": " + JI(g_total) + ",\n";
   j += "  \"rows_loaded\": " + JI(g_loaded) + ",\n";
   j += "  \"bad_lines\": " + JI(g_badline) + ",\n";
   j += "  \"expected_first\": \"" + TimeToString(g_first, TIME_DATE|TIME_MINUTES) + "\",\n";
   j += "  \"expected_last\": \""  + TimeToString(g_last,  TIME_DATE|TIME_MINUTES) + "\",\n";
   j += "  \"digits\": " + JI(digits) + ",\n";
   j += "  \"point\": " + J(point, 10) + ",\n";
   j += "  \"contract_size\": " + J(csize, 4) + ",\n";
   j += "  \"tick_size\": " + J(tsize, 10) + ",\n";
   j += "  \"tick_value\": " + J(tval, 8) + ",\n";
   j += "  \"volume_min\": " + J(vmin, 4) + ",\n";
   j += "  \"spread_points\": " + JI(spread) + ",\n";
   j += "  \"usd_per_1price_unit_0.01lot_contract_implied\": " + J(0.01 * csize, 6) + ",\n";
   j += "  \"m1_bars\": " + JI(m1bars) + ",\n";
   j += "  \"m1_first\": \"" + (m1first > 0 ? TimeToString(m1first, TIME_DATE|TIME_MINUTES) : "none") + "\",\n";
   j += "  \"m1_last\": \""  + (m1last  > 0 ? TimeToString(m1last,  TIME_DATE|TIME_MINUTES) : "none") + "\",\n";
   j += "  \"m5_bars\": " + JI(m5bars) + ",\n";
   j += "  \"profit_convention_test\": " + g_profit_test + "\n";
   j += "}\n";

   int fh = FileOpen(InpOutFile, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(fh != INVALID_HANDLE)
   {
      FileWriteString(fh, j);
      FileClose(fh);
   }

   Print("dsh: csv_lines=", g_total, " rows_loaded=", g_loaded, " bad=", g_badline);
   Print("dsh: m1_bars=", m1bars, " first=", TimeToString(m1first, TIME_DATE|TIME_MINUTES),
         " last=", TimeToString(m1last, TIME_DATE|TIME_MINUTES));
   Print("dsh: volume_min=", DoubleToString(vmin, 4));
   Print("dsh: === MakeCustomSymbol done ===");
}
//+------------------------------------------------------------------+
