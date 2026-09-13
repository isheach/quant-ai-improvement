//+------------------------------------------------------------------+
//|  dsh_TesterProbe.mq5                                             |
//|  DeepSeek — 判定「策略测试器实际能读到多少 M1 历史」。                |
//|                                                                  |
//|  背景：脚本用 CopyRates 只能拿到 500000 根（终端 "Max bars in chart" |
//|  缓存口径）。但测试器是独立进程、按 [Tester] 的 FromDate 直接读磁盘     |
//|  历史文件。本 EA 在测试器里把实际的起止时间与根数打出来，一锤定音。     |
//|                                                                  |
//|  用法：挂到 XAUUSD_HIST M1，FromDate=2023.01.05，Model=2 跑一次。    |
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"

input int InpLogFirstN = 12;    // 打印最前面 N 根 M1 的时间/价格
input int InpProgressEveryDays = 90;  // 每 N 天打一行进度

datetime g_nextProgress = 0;
int      g_barsSeen     = 0;
int      g_logged       = 0;

int OnInit()
{
   Print("dshT: === TesterProbe init ===");
   Print("dshT: symbol=", _Symbol, " digits=", _Digits, " point=", DoubleToString(_Point, 8));
   Print("dshT: contract=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE), 2),
         " tick_value=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), 6),
         " tick_size=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE), 8),
         " vol_min=", DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 4),
         " spread=", SymbolInfoInteger(_Symbol, SYMBOL_SPREAD));
   Print("dshT: tester deposit=", DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
         " currency=", AccountInfoString(ACCOUNT_CURRENCY),
         " leverage=", AccountInfoInteger(ACCOUNT_LEVERAGE));
   Print("dshT: TimeCurrent at init = ", TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES));
   return INIT_SUCCEEDED;
}

void OnTick()
{
   static datetime lastBar = 0;
   datetime bt = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(bt == lastBar) return;
   lastBar = bt;
   g_barsSeen++;

   if(g_logged < InpLogFirstN)
   {
      double c = iClose(_Symbol, PERIOD_CURRENT, 0);
      Print("dshT: bar#", g_barsSeen, " time=", TimeToString(bt, TIME_DATE|TIME_MINUTES),
            " close=", DoubleToString(c, _Digits));
      g_logged++;
   }
   if(g_nextProgress == 0)
      g_nextProgress = bt + (datetime)InpProgressEveryDays * 86400;
   else if(bt >= g_nextProgress)
   {
      Print("dshT: progress time=", TimeToString(bt, TIME_DATE|TIME_MINUTES),
            " barsSeen=", g_barsSeen,
            " equity=", DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
      g_nextProgress = bt + (datetime)InpProgressEveryDays * 86400;
   }
}

void OnDeinit(const int reason)
{
   Print("dshT: === TesterProbe deinit, reason=", reason, " barsSeen=", g_barsSeen, " ===");
}
//+------------------------------------------------------------------+
