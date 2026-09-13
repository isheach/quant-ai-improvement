#property strict
input string InpSym = "USDJPYm";
bool opened=false; double entry=0, entryTime=0; int ticks=0;
int OnInit(){ PrintFormat("PLEDBG init %s cs=%.1f vmin=%.2f vstep=%.2f tv=%.6f ts=%.8f base=%s prof=%s cur=%s",
   _Symbol, SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE),
   SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN), SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP),
   SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE), SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),
   SymbolInfoString(_Symbol,SYMBOL_CURRENCY_BASE), SymbolInfoString(_Symbol,SYMBOL_CURRENCY_PROFIT),
   AccountInfoString(ACCOUNT_CURRENCY)); return INIT_SUCCEEDED; }
void OnTick()
{
   ticks++;
   if(!opened && ticks>50)
   {
      MqlTradeRequest r; MqlTradeResult s; ZeroMemory(r); ZeroMemory(s);
      r.action=TRADE_ACTION_DEAL; r.symbol=_Symbol; r.volume=0.01;
      r.type=ORDER_TYPE_BUY; r.price=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
      r.deviation=50; r.magic=999; r.type_filling=ORDER_FILLING_FOK;
      if(OrderSend(r,s)) { opened=true; entry=r.price; entryTime=(double)TimeCurrent();
        PrintFormat("PLEDBG OPEN ok retcode=%d price=%.3f", s.retcode, r.price); }
      else PrintFormat("PLEDBG OPEN fail retcode=%d err=%d", s.retcode, GetLastError());
      return;
   }
   if(opened && !PositionSelect(_Symbol))
   {
      double bid=SymbolInfoDouble(_Symbol,SYMBOL_BID);
      double move=bid-entry;
      PrintFormat("PLEDBG CLOSED? entry=%.3f bid=%.3f move=%.3f balance=%.2f equity=%.2f",
                  entry, bid, move, AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_EQUITY));
      opened=false;
   }
}
void OnDeinit(const int r)
{
   PrintFormat("PLEDBG end ticks=%d balance=%.2f equity=%.2f", ticks,
               AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_EQUITY));
}
