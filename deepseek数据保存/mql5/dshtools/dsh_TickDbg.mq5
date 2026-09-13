#property strict
input string InpNote = "x";
int OnInit() { return INIT_SUCCEEDED; }
void OnTick()
{
   static int n = 0;
   if(n % 20000 != 0) { n++; return; }
   n++;
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double pt = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double cs = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double vmin= SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double perLot1 = 1.0 / ts * tv;
   PrintFormat("TICKDBG t=%s bid=%.3f tv=%.6f ts=%.8f pt=%.8f cs=%.1f vmin=%.2f perLot(1.0price)=%.4f",
               TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES), bid, tv, ts, pt, cs, vmin, perLot1);
}
