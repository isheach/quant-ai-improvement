//+------------------------------------------------------------------+
//|  dsh_VolMinProbe.mq5                                             |
//|  DeepSeek — 诊断：自定义品种的 volume_min 为什么写不进去            |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property script_show_inputs

input string InpOutFile = "dshtools\\volmin_probe.json";

string g_log = "";

void Say(const string s)
{
   Print("dsh: ", s);
   g_log += s + " | ";
}

double VM(const string s) { return SymbolInfoDouble(s, SYMBOL_VOLUME_MIN); }
double VS(const string s) { return SymbolInfoDouble(s, SYMBOL_VOLUME_STEP); }

void OnStart()
{
   string t = "DSH_VM_TEST";
   if(SymbolSelect(t, false)) CustomSymbolDelete(t);

   Say("--- A: plain create + vol set ---");
   CustomSymbolCreate(t);
   CustomSymbolSetDouble(t, SYMBOL_VOLUME_STEP, 0.01);
   CustomSymbolSetDouble(t, SYMBOL_VOLUME_MIN,  0.01);
   CustomSymbolSetDouble(t, SYMBOL_VOLUME_MAX,  200.0);
   Say("A vmin=" + DoubleToString(VM(t), 4) + " vstep=" + DoubleToString(VS(t), 4));

   Say("--- B: with volume_limit large ---");
   CustomSymbolSetDouble(t, SYMBOL_VOLUME_LIMIT, 1000000.0);
   Say("B vmin=" + DoubleToString(VM(t), 4) + " vlim=" + DoubleToString(SymbolInfoDouble(t, SYMBOL_VOLUME_LIMIT), 2));

   Say("--- C: select(true) then set ---");
   SymbolSelect(t, true);
   CustomSymbolSetDouble(t, SYMBOL_VOLUME_MIN, 0.01);
   Say("C vmin=" + DoubleToString(VM(t), 4));

   Say("--- D: set other props then retry ---");
   CustomSymbolSetInteger(t, SYMBOL_DIGITS, 3);
   CustomSymbolSetDouble (t, SYMBOL_POINT, 0.001);
   CustomSymbolSetDouble (t, SYMBOL_TRADE_TICK_SIZE, 0.001);
   CustomSymbolSetDouble (t, SYMBOL_TRADE_TICK_VALUE, 400.0);
   CustomSymbolSetDouble (t, SYMBOL_TRADE_CONTRACT_SIZE, 100.0);
   CustomSymbolSetInteger(t, SYMBOL_TRADE_CALC_MODE, SYMBOL_CALC_MODE_CFD);
   CustomSymbolSetString (t, SYMBOL_CURRENCY_PROFIT, "USD");
   CustomSymbolSetString (t, SYMBOL_CURRENCY_BASE, "USD");
   CustomSymbolSetInteger(t, SYMBOL_TRADE_MODE, SYMBOL_TRADE_MODE_FULL);
   CustomSymbolSetDouble (t, SYMBOL_VOLUME_MIN, 0.01);
   Say("D vmin=" + DoubleToString(VM(t), 4) + " vstep=" + DoubleToString(VS(t), 4));

   Say("--- E: feed one rate then re-set ---");
   MqlRates r[1];
   r[0].time = D'2024.01.02 00:00'; r[0].open = 2000; r[0].high = 2001;
   r[0].low = 1999; r[0].close = 2000.5; r[0].tick_volume = 100; r[0].spread = 200;
   CustomRatesUpdate(t, r);
   CustomSymbolSetDouble(t, SYMBOL_VOLUME_MIN, 0.01);
   Say("E vmin=" + DoubleToString(VM(t), 4));

   Say("--- F: delete and recreate in this exact order (final recipe test) ---");
   SymbolSelect(t, false);
   CustomSymbolDelete(t);
   CustomSymbolCreate(t);
   CustomSymbolSetInteger(t, SYMBOL_DIGITS, 3);
   CustomSymbolSetDouble (t, SYMBOL_POINT, 0.001);
   CustomSymbolSetDouble (t, SYMBOL_TRADE_TICK_SIZE, 0.001);
   CustomSymbolSetDouble (t, SYMBOL_TRADE_TICK_VALUE, 400.0);
   CustomSymbolSetDouble (t, SYMBOL_TRADE_CONTRACT_SIZE, 100.0);
   CustomSymbolSetDouble (t, SYMBOL_VOLUME_MIN, 0.01);
   CustomSymbolSetDouble (t, SYMBOL_VOLUME_STEP, 0.01);
   CustomSymbolSetDouble (t, SYMBOL_VOLUME_MAX, 200.0);
   CustomSymbolSetInteger(t, SYMBOL_TRADE_MODE, SYMBOL_TRADE_MODE_FULL);
   CustomSymbolSetInteger(t, SYMBOL_TRADE_CALC_MODE, SYMBOL_CALC_MODE_CFD);
   Say("F vmin=" + DoubleToString(VM(t), 4) + " vstep=" + DoubleToString(VS(t), 4));

   Say("--- G: as F but WITHOUT volume_step ---");
   SymbolSelect(t, false); CustomSymbolDelete(t); CustomSymbolCreate(t);
   CustomSymbolSetInteger(t, SYMBOL_DIGITS, 3);
   CustomSymbolSetDouble (t, SYMBOL_POINT, 0.001);
   CustomSymbolSetDouble (t, SYMBOL_TRADE_CONTRACT_SIZE, 100.0);
   CustomSymbolSetDouble (t, SYMBOL_VOLUME_MIN, 0.01);
   Say("G vmin=" + DoubleToString(VM(t), 4) + " vstep=" + DoubleToString(VS(t), 4));

   SymbolSelect(t, false); CustomSymbolDelete(t);
   SymbolSelect("XAUUSD_HIST", true);

   int fh = FileOpen(InpOutFile, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(fh != INVALID_HANDLE) { FileWriteString(fh, g_log); FileClose(fh); }
}
//+------------------------------------------------------------------+
