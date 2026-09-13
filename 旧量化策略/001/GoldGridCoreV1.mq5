//+------------------------------------------------------------------+
//| GoldGridCoreV1.mq5                                               |
//| Minimal adaptive gold grid EA for MT5                            |
//|                                                                  |
//| Architecture:                                                    |
//| 1. MarketBaseline only describes the market center.              |
//| 2. Grid levels are frozen when the first position opens.         |
//| 3. ExitAnchor is separate and can only become easier to reach.   |
//| 4. Risk exit enters LOCKED state; no immediate re-entry.         |
//| 5. Re-entry requires cooldown + neutral reset + a fresh crossing.|
//| 6. Embedded CAGR/risk OnTester score for Custom max optimization.|
//|                                                                  |
//| IMPORTANT:                                                       |
//| - Research/backtest version, not a profit guarantee.             |
//| - Attach only when no positions with this Magic Number exist.    |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Adaptive grid core with neutral-reset re-entry and embedded risk score."

#include <Trade/Trade.mqh>

CTrade G_trade;

//====================================================================
// Trading inputs
//====================================================================
input group "=== Trading ==="
input long            InpMagicNumber                  = 26071001;
input double          InpLotSize                      = 0.01;
input int             InpDeviationPoints              = 30;
input ENUM_TIMEFRAMES InpBaselineTF                   = PERIOD_M5;
input int             InpMinSecondsBetweenLayers      = 60;

input group "=== Market Baseline ==="
input int             InpBaselineInitBars             = 120;
input double          InpBaselineAlpha                = 0.12;
input double          InpBaselineClipATR              = 1.50;
input int             InpATRPeriod                    = 20;

input group "=== Grid Geometry ==="
input double          InpEntryATR                     = 1.50;
input double          InpAddATR                       = 1.20;
input double          InpLayerExpansion               = 1.30;
input int             InpMaxLayers                    = 4;

input group "=== Exit Anchor ==="
input double          InpExitBufferATR                = 0.25;
input double          InpMinProfitATR                 = 0.08;
input double          InpLayerConcessionATR           = 0.10;
input double          InpTimeConcessionATRPerHour     = 0.01;

input group "=== Risk Exit ==="
input double          InpMaxCycleLossPct              = 0.10;
input double          InpStopBeyondLastATR            = 1.00;
input double          InpMaxHoldingHours              = 24.0;

input group "=== Lock and Re-arm ==="
input int             InpBaseCooldownMinutes          = 60;
input double          InpCooldownMultiplier           = 4.0;
input int             InpMaxCooldownMinutes           = 1440;
input int             InpStopCountResetHours          = 24;
input double          InpNeutralZoneATR               = 0.50;
input int             InpNeutralLookbackBars          = 5;
input int             InpNeutralRequiredBars          = 3;
input int             InpSlopeLookbackBars            = 5;
input double          InpMaxBaselineSlopeATR           = 0.60;

input group "=== Diagnostics ==="
input bool            InpPrintEvents                  = true;
input bool            InpDrawLevels                   = true;

//====================================================================
// Embedded optimization score inputs
// Score = CAGR return score - DD events - underwater duration - floating risk
//====================================================================
input group "=== Optimization Score: Return ==="
input double InpScoreReturnWeight       = 100.0;
input double InpScoreTargetCAGR         = 0.30;

input group "=== Optimization Score: Drawdown Events ==="
input double InpScoreDDEventStart       = 0.05;
input double InpScoreDDEventEnd         = 0.01;
input double InpScoreDDEventFree        = 0.03;
input double InpScoreDDEventRef         = 0.20;
input double InpScoreDDEventPower       = 2.0;
input double InpScoreDDEventWeight      = 25.0;

input group "=== Optimization Score: Underwater ==="
input double InpScoreUnderwaterFree     = 0.03;
input double InpScoreUnderwaterRef      = 0.10;
input double InpScoreUnderwaterPower    = 2.0;
input double InpScoreUnderwaterWeight   = 20.0;

input group "=== Optimization Score: Floating Risk ==="
input double InpScoreFloatingFree       = 0.03;
input double InpScoreFloatingRef        = 0.15;
input double InpScoreFloatingPower      = 2.0;
input double InpScoreFloatingWeight     = 20.0;

input group "=== Optimization Score: Diagnostics ==="
input bool   InpScorePrintDetail        = false;

//====================================================================
// Constants and enums
//====================================================================
#define SCORE_SECONDS_PER_YEAR 31536000.0
#define SCORE_INVALID_VALUE   -1000000.0
#define MAX_LEVELS             20
#define MAX_NEUTRAL_FLAGS      50
#define MAX_BASELINE_HISTORY   100

enum ENUM_GRID_STATE
{
   GRID_ARMED = 0,
   GRID_ACTIVE_LONG,
   GRID_ACTIVE_SHORT,
   GRID_LOCKED
};

//====================================================================
// Trading state
//====================================================================
ENUM_GRID_STATE G_state = GRID_ARMED;

int      G_atr_handle             = INVALID_HANDLE;
datetime G_last_bar_time          = 0;
datetime G_cycle_start_time       = 0;
datetime G_last_layer_time        = 0;
datetime G_lock_start_time        = 0;
datetime G_last_risk_exit_time    = 0;

double   G_market_baseline        = 0.0;
double   G_current_atr            = 0.0;
double   G_cycle_baseline         = 0.0;
double   G_cycle_atr              = 0.0;
double   G_cycle_start_equity     = 0.0;
double   G_exit_anchor            = 0.0;
double   G_levels[MAX_LEVELS];

int      G_consecutive_risk_stops = 0;
int      G_neutral_flags[MAX_NEUTRAL_FLAGS];
int      G_neutral_flag_count     = 0;
double   G_baseline_history[MAX_BASELINE_HISTORY];
int      G_baseline_history_count = 0;

double   G_prev_bid               = 0.0;
double   G_prev_ask               = 0.0;

//====================================================================
// Score state
//====================================================================
double   G_score_initial_capital       = 0.0;
double   G_score_equity_peak           = 0.0;

datetime G_score_start_time            = 0;
datetime G_score_last_observe_time     = 0;

double   G_score_last_underwater_sev   = 0.0;
double   G_score_last_floating_sev     = 0.0;

double   G_score_underwater_integral   = 0.0;
double   G_score_floating_integral     = 0.0;

bool     G_score_in_dd_event           = false;
double   G_score_current_event_max_dd  = 0.0;
double   G_score_finished_event_sum    = 0.0;
int      G_score_finished_event_count  = 0;

double   G_score_max_drawdown_ratio    = 0.0;
double   G_score_max_floating_ratio    = 0.0;
long     G_score_observation_count     = 0;

//====================================================================
// Utility functions
//====================================================================
double ClampValue(const double value,const double low,const double high)
{
   return MathMax(low,MathMin(high,value));
}

double NormalizePriceValue(const double price)
{
   return NormalizeDouble(price,(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS));
}

double NormalizeVolumeValue(const double requested_volume)
{
   const double min_volume = SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   const double max_volume = SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX);
   const double step       = SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);

   if(step <= 0.0)
      return requested_volume;

   double volume = MathMax(min_volume,MathMin(max_volume,requested_volume));
   volume = MathFloor((volume + 1e-12) / step) * step;
   return NormalizeDouble(volume,8);
}

string StateToString()
{
   if(G_state == GRID_ARMED)        return "ARMED";
   if(G_state == GRID_ACTIVE_LONG)  return "ACTIVE_LONG";
   if(G_state == GRID_ACTIVE_SHORT) return "ACTIVE_SHORT";
   return "LOCKED";
}

void PrintEvent(const string text)
{
   if(InpPrintEvents)
      Print("[GoldGridCoreV1] ",text);
}

bool ValidateTradingInputs()
{
   if(InpLotSize <= 0.0 ||
      InpBaselineInitBars < 20 ||
      InpBaselineAlpha <= 0.0 || InpBaselineAlpha > 1.0 ||
      InpBaselineClipATR <= 0.0 ||
      InpATRPeriod < 2 ||
      InpEntryATR <= 0.0 ||
      InpAddATR <= 0.0 ||
      InpLayerExpansion < 1.0 ||
      InpMaxLayers < 1 || InpMaxLayers > MAX_LEVELS ||
      InpExitBufferATR < 0.0 ||
      InpMinProfitATR < 0.0 ||
      InpLayerConcessionATR < 0.0 ||
      InpTimeConcessionATRPerHour < 0.0 ||
      InpMaxCycleLossPct <= 0.0 ||
      InpStopBeyondLastATR < 0.0 ||
      InpMaxHoldingHours <= 0.0 ||
      InpBaseCooldownMinutes < 0 ||
      InpCooldownMultiplier < 1.0 ||
      InpMaxCooldownMinutes < InpBaseCooldownMinutes ||
      InpNeutralZoneATR <= 0.0 ||
      InpNeutralLookbackBars < 1 || InpNeutralLookbackBars > MAX_NEUTRAL_FLAGS ||
      InpNeutralRequiredBars < 1 || InpNeutralRequiredBars > InpNeutralLookbackBars ||
      InpSlopeLookbackBars < 1 || InpSlopeLookbackBars >= MAX_BASELINE_HISTORY ||
      InpMaxBaselineSlopeATR < 0.0)
   {
      Print("Invalid trading parameters.");
      return false;
   }
   return true;
}

bool ReadClosedATR(double &atr_value)
{
   atr_value = 0.0;
   if(G_atr_handle == INVALID_HANDLE)
      return false;

   double values[];
   ArraySetAsSeries(values,true);
   if(CopyBuffer(G_atr_handle,0,1,1,values) != 1)
      return false;

   atr_value = values[0];
   return (atr_value > 0.0);
}

bool ReadClosedBar(MqlRates &bar)
{
   MqlRates rates[];
   ArraySetAsSeries(rates,true);
   if(CopyRates(_Symbol,InpBaselineTF,1,1,rates) != 1)
      return false;

   bar = rates[0];
   return true;
}

bool InitializeBaseline()
{
   double closes[];
   ArraySetAsSeries(closes,true);

   const int copied =
      CopyClose(_Symbol,InpBaselineTF,1,InpBaselineInitBars,closes);

   if(copied < MathMin(20,InpBaselineInitBars))
   {
      Print("Not enough history to initialize baseline. Copied=",copied);
      return false;
   }

   double sum = 0.0;
   for(int i=0;i<copied;i++)
      sum += closes[i];

   G_market_baseline = sum / copied;

   if(!ReadClosedATR(G_current_atr))
   {
      Print("Unable to initialize ATR.");
      return false;
   }

   G_baseline_history_count = 0;
   for(int i=0;i<MAX_BASELINE_HISTORY;i++)
      G_baseline_history[i] = G_market_baseline;

   G_baseline_history_count = MAX_BASELINE_HISTORY;
   return true;
}

void PushBaselineHistory(const double value)
{
   const int last = MathMin(G_baseline_history_count,MAX_BASELINE_HISTORY-1);
   for(int i=last;i>0;i--)
      G_baseline_history[i] = G_baseline_history[i-1];

   G_baseline_history[0] = value;
   if(G_baseline_history_count < MAX_BASELINE_HISTORY)
      G_baseline_history_count++;
}

void PushNeutralFlag(const bool is_neutral)
{
   const int last = MathMin(G_neutral_flag_count,MAX_NEUTRAL_FLAGS-1);
   for(int i=last;i>0;i--)
      G_neutral_flags[i] = G_neutral_flags[i-1];

   G_neutral_flags[0] = (is_neutral ? 1 : 0);
   if(G_neutral_flag_count < MAX_NEUTRAL_FLAGS)
      G_neutral_flag_count++;
}

int CountRecentNeutralBars()
{
   const int count = MathMin(G_neutral_flag_count,InpNeutralLookbackBars);
   int total = 0;
   for(int i=0;i<count;i++)
      total += G_neutral_flags[i];
   return total;
}

bool BaselineSlopeIsAcceptable()
{
   if(G_current_atr <= 0.0 ||
      G_baseline_history_count <= InpSlopeLookbackBars)
      return false;

   const double slope_atr =
      MathAbs(G_baseline_history[0]
              - G_baseline_history[InpSlopeLookbackBars])
      / G_current_atr;

   return (slope_atr <= InpMaxBaselineSlopeATR);
}

void UpdateMarketBaselineOnNewBar()
{
   MqlRates bar;
   double atr = 0.0;

   if(!ReadClosedBar(bar) || !ReadClosedATR(atr))
      return;

   G_current_atr = atr;

   const double max_step = InpBaselineClipATR * atr;
   const double raw_gap  = bar.close - G_market_baseline;
   const double clipped  = ClampValue(raw_gap,-max_step,max_step);

   G_market_baseline += InpBaselineAlpha * clipped;
   G_market_baseline  = NormalizePriceValue(G_market_baseline);

   PushBaselineHistory(G_market_baseline);

   const bool is_neutral =
      (MathAbs(bar.close - G_market_baseline)
       <= InpNeutralZoneATR * G_current_atr);

   PushNeutralFlag(is_neutral);
}

bool IsNewBaselineBar()
{
   const datetime current_bar = iTime(_Symbol,InpBaselineTF,0);
   if(current_bar <= 0)
      return false;

   if(G_last_bar_time == 0)
   {
      G_last_bar_time = current_bar;
      return false;
   }

   if(current_bar != G_last_bar_time)
   {
      G_last_bar_time = current_bar;
      return true;
   }

   return false;
}

int CountStrategyPositions(int &long_count,int &short_count)
{
   long_count = 0;
   short_count = 0;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      const ENUM_POSITION_TYPE type =
         (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

      if(type == POSITION_TYPE_BUY)
         long_count++;
      else if(type == POSITION_TYPE_SELL)
         short_count++;
   }

   return long_count + short_count;
}

bool GetBasketStats(const ENUM_POSITION_TYPE wanted_type,
                    int &count,
                    double &total_volume,
                    double &weighted_price,
                    double &floating_profit)
{
   count = 0;
   total_volume = 0.0;
   weighted_price = 0.0;
   floating_profit = 0.0;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      const ENUM_POSITION_TYPE type =
         (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

      if(type != wanted_type)
         continue;

      const double volume = PositionGetDouble(POSITION_VOLUME);
      const double price  = PositionGetDouble(POSITION_PRICE_OPEN);

      count++;
      total_volume    += volume;
      weighted_price += volume * price;
      floating_profit += PositionGetDouble(POSITION_PROFIT);
      floating_profit += PositionGetDouble(POSITION_SWAP);
   }

   if(total_volume > 0.0)
      weighted_price /= total_volume;

   return (count > 0);
}

bool CloseAllStrategyPositions()
{
   bool all_ok = true;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      if(!G_trade.PositionClose(ticket,InpDeviationPoints))
      {
         all_ok = false;
         Print("PositionClose failed. Ticket=",ticket,
               " retcode=",G_trade.ResultRetcode(),
               " ",G_trade.ResultRetcodeDescription());
      }
   }

   return all_ok;
}

void DeleteLevelObjects()
{
   ObjectDelete(0,"GG_Baseline");
   ObjectDelete(0,"GG_Exit");
   for(int i=0;i<MAX_LEVELS;i++)
      ObjectDelete(0,"GG_Level_"+IntegerToString(i+1));
}

void DrawHorizontalLine(const string name,const double price)
{
   if(!InpDrawLevels || price <= 0.0)
      return;

   if(ObjectFind(0,name) < 0)
      ObjectCreate(0,name,OBJ_HLINE,0,0,price);

   ObjectSetDouble(0,name,OBJPROP_PRICE,price);
   ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
}

void UpdateDrawings()
{
   if(!InpDrawLevels)
      return;

   DrawHorizontalLine("GG_Baseline",G_market_baseline);

   if(G_state == GRID_ACTIVE_LONG || G_state == GRID_ACTIVE_SHORT)
   {
      DrawHorizontalLine("GG_Exit",G_exit_anchor);
      for(int i=0;i<InpMaxLayers;i++)
         DrawHorizontalLine("GG_Level_"+IntegerToString(i+1),G_levels[i]);
   }
   else
   {
      ObjectDelete(0,"GG_Exit");
      for(int i=0;i<MAX_LEVELS;i++)
         ObjectDelete(0,"GG_Level_"+IntegerToString(i+1));
   }
}

void ResetCycleState()
{
   G_cycle_start_time   = 0;
   G_last_layer_time    = 0;
   G_cycle_baseline     = 0.0;
   G_cycle_atr          = 0.0;
   G_cycle_start_equity = 0.0;
   G_exit_anchor        = 0.0;

   for(int i=0;i<MAX_LEVELS;i++)
      G_levels[i] = 0.0;
}

void BuildFrozenLevels(const bool is_long)
{
   G_levels[0] =
      G_cycle_baseline
      + (is_long ? -1.0 : 1.0) * InpEntryATR * G_cycle_atr;

   double previous = G_levels[0];

   for(int i=1;i<InpMaxLayers;i++)
   {
      const double expansion = MathPow(InpLayerExpansion,i-1);
      const double gap = InpAddATR * G_cycle_atr * expansion;

      previous += (is_long ? -gap : gap);
      G_levels[i] = NormalizePriceValue(previous);
   }

   G_levels[0] = NormalizePriceValue(G_levels[0]);
}

bool OpenLayer(const bool is_long,const int layer_number)
{
   if(layer_number < 1 || layer_number > InpMaxLayers)
      return false;

   const double volume = NormalizeVolumeValue(InpLotSize);
   if(volume <= 0.0)
      return false;

   const string comment =
      StringFormat("GGV1 %s L%d",
                   (is_long ? "BUY" : "SELL"),
                   layer_number);

   bool ok = false;
   if(is_long)
      ok = G_trade.Buy(volume,_Symbol,0.0,0.0,0.0,comment);
   else
      ok = G_trade.Sell(volume,_Symbol,0.0,0.0,0.0,comment);

   if(!ok)
   {
      Print("Open layer failed. Layer=",layer_number,
            " retcode=",G_trade.ResultRetcode(),
            " ",G_trade.ResultRetcodeDescription());
      return false;
   }

   G_last_layer_time = TimeCurrent();
   PrintEvent(StringFormat("%s layer %d opened. Frozen target=%.*f",
                           (is_long ? "Long" : "Short"),
                           layer_number,
                           (int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS),
                           G_levels[layer_number-1]));
   return true;
}

void StartCycle(const bool is_long)
{
   G_cycle_baseline     = G_market_baseline;
   G_cycle_atr          = G_current_atr;
   G_cycle_start_time   = TimeCurrent();
   G_cycle_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   G_exit_anchor        = 0.0;

   BuildFrozenLevels(is_long);

   if(OpenLayer(is_long,1))
   {
      G_state = (is_long ? GRID_ACTIVE_LONG : GRID_ACTIVE_SHORT);
      PrintEvent(StringFormat("Cycle started. State=%s baseline=%.*f ATR=%.*f",
                              StateToString(),
                              (int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS),
                              G_cycle_baseline,
                              (int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS),
                              G_cycle_atr));
   }
   else
   {
      ResetCycleState();
      G_state = GRID_ARMED;
   }
}

double CalculateExitCandidate(const bool is_long,
                              const int layers,
                              const double weighted_price)
{
   if(G_current_atr <= 0.0 || weighted_price <= 0.0)
      return 0.0;

   const double held_hours =
      (G_cycle_start_time > 0)
      ? double(TimeCurrent() - G_cycle_start_time) / 3600.0
      : 0.0;

   const double concession =
      G_current_atr *
      (InpLayerConcessionATR * MathMax(0,layers-1)
       + InpTimeConcessionATRPerHour * MathMax(0.0,held_hours));

   const double min_profit_distance =
      InpMinProfitATR * G_current_atr;

   if(is_long)
   {
      const double profit_floor =
         weighted_price + min_profit_distance;

      const double market_target =
         G_market_baseline
         - InpExitBufferATR * G_current_atr
         - concession;

      return NormalizePriceValue(MathMax(profit_floor,market_target));
   }

   const double profit_floor =
      weighted_price - min_profit_distance;

   const double market_target =
      G_market_baseline
      + InpExitBufferATR * G_current_atr
      + concession;

   return NormalizePriceValue(MathMin(profit_floor,market_target));
}

void UpdateOneWayExitAnchor(const bool is_long,
                            const int layers,
                            const double weighted_price)
{
   const double candidate =
      CalculateExitCandidate(is_long,layers,weighted_price);

   if(candidate <= 0.0)
      return;

   if(G_exit_anchor <= 0.0)
   {
      G_exit_anchor = candidate;
      return;
   }

   // Exit target may only become easier:
   // long -> lower/equal; short -> higher/equal.
   if(is_long)
      G_exit_anchor = MathMin(G_exit_anchor,candidate);
   else
      G_exit_anchor = MathMax(G_exit_anchor,candidate);

   G_exit_anchor = NormalizePriceValue(G_exit_anchor);
}

double StrategyFloatingProfit()
{
   double result = 0.0;

   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;

      if(PositionGetString(POSITION_SYMBOL) != _Symbol)
         continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      result += PositionGetDouble(POSITION_PROFIT);
      result += PositionGetDouble(POSITION_SWAP);
   }

   return result;
}

int CurrentCooldownMinutes()
{
   if(G_consecutive_risk_stops <= 0)
      return InpBaseCooldownMinutes;

   double minutes =
      InpBaseCooldownMinutes
      * MathPow(InpCooldownMultiplier,G_consecutive_risk_stops-1);

   minutes = MathMin(minutes,(double)InpMaxCooldownMinutes);
   return (int)MathRound(minutes);
}

void EnterRiskLock(const string reason)
{
   CloseAllStrategyPositions();

   const datetime now_time = TimeCurrent();

   if(G_last_risk_exit_time <= 0 ||
      now_time - G_last_risk_exit_time
      > InpStopCountResetHours * 3600)
   {
      G_consecutive_risk_stops = 1;
   }
   else
   {
      G_consecutive_risk_stops++;
   }

   G_last_risk_exit_time = now_time;
   G_lock_start_time     = now_time;
   G_state               = GRID_LOCKED;

   ResetCycleState();

   PrintEvent(StringFormat("RISK EXIT: %s. Locked. Consecutive=%d cooldown=%d min",
                           reason,
                           G_consecutive_risk_stops,
                           CurrentCooldownMinutes()));
}

void FinishProfitableCycle()
{
   if(!CloseAllStrategyPositions())
      return;

   G_state = GRID_ARMED;
   G_consecutive_risk_stops = 0;
   ResetCycleState();

   PrintEvent("Cycle closed by ExitAnchor. State returned to ARMED.");
}

bool ReArmConditionsMet()
{
   if(G_state != GRID_LOCKED || G_lock_start_time <= 0)
      return false;

   const int cooldown_seconds = CurrentCooldownMinutes() * 60;
   if(TimeCurrent() - G_lock_start_time < cooldown_seconds)
      return false;

   if(CountRecentNeutralBars() < InpNeutralRequiredBars)
      return false;

   if(!BaselineSlopeIsAcceptable())
      return false;

   return true;
}

void CheckLockedState()
{
   if(!ReArmConditionsMet())
      return;

   G_state = GRID_ARMED;
   G_lock_start_time = 0;

   // Fresh crossing is still required after re-arm.
   MqlTick tick;
   if(SymbolInfoTick(_Symbol,tick))
   {
      G_prev_bid = tick.bid;
      G_prev_ask = tick.ask;
   }

   PrintEvent("Neutral reset confirmed. State changed from LOCKED to ARMED.");
}

void ManageActiveCycle(const MqlTick &tick)
{
   const bool is_long = (G_state == GRID_ACTIVE_LONG);
   const ENUM_POSITION_TYPE wanted_type =
      (is_long ? POSITION_TYPE_BUY : POSITION_TYPE_SELL);

   int layers = 0;
   double total_volume = 0.0;
   double weighted_price = 0.0;
   double floating_profit = 0.0;

   if(!GetBasketStats(wanted_type,
                      layers,
                      total_volume,
                      weighted_price,
                      floating_profit))
   {
      // Positions disappeared externally.
      G_state = GRID_ARMED;
      ResetCycleState();
      PrintEvent("No basket position found. State recovered to ARMED.");
      return;
   }

   UpdateOneWayExitAnchor(is_long,layers,weighted_price);

   // 1. Normal profitable exit.
   if(G_exit_anchor > 0.0)
   {
      if(is_long && tick.bid >= G_exit_anchor)
      {
         FinishProfitableCycle();
         return;
      }

      if(!is_long && tick.ask <= G_exit_anchor)
      {
         FinishProfitableCycle();
         return;
      }
   }

   // 2. Risk by floating loss as a percentage of fixed initial capital.
   const double loss_limit =
      G_score_initial_capital * InpMaxCycleLossPct;

   if(StrategyFloatingProfit() <= -loss_limit)
   {
      EnterRiskLock("maximum cycle floating loss");
      return;
   }

   // 3. Risk by maximum holding time.
   if(G_cycle_start_time > 0)
   {
      const double held_hours =
         double(TimeCurrent() - G_cycle_start_time) / 3600.0;

      if(held_hours >= InpMaxHoldingHours)
      {
         EnterRiskLock("maximum holding time");
         return;
      }
   }

   // 4. Open the next frozen layer.
   if(layers < InpMaxLayers &&
      (G_last_layer_time <= 0 ||
       TimeCurrent() - G_last_layer_time >= InpMinSecondsBetweenLayers))
   {
      const double next_level = G_levels[layers];

      if(is_long && tick.bid <= next_level)
      {
         OpenLayer(true,layers+1);
         return;
      }

      if(!is_long && tick.ask >= next_level)
      {
         OpenLayer(false,layers+1);
         return;
      }
   }

   // 5. Price boundary after all layers have been used.
   if(layers >= InpMaxLayers)
   {
      if(is_long)
      {
         const double stop_price =
            G_levels[InpMaxLayers-1]
            - InpStopBeyondLastATR * G_cycle_atr;

         if(tick.bid <= stop_price)
         {
            EnterRiskLock("price beyond final long layer");
            return;
         }
      }
      else
      {
         const double stop_price =
            G_levels[InpMaxLayers-1]
            + InpStopBeyondLastATR * G_cycle_atr;

         if(tick.ask >= stop_price)
         {
            EnterRiskLock("price beyond final short layer");
            return;
         }
      }
   }
}

void CheckFreshEntryCrossing(const MqlTick &tick)
{
   if(G_state != GRID_ARMED || G_current_atr <= 0.0)
      return;

   const double long_line =
      G_market_baseline - InpEntryATR * G_current_atr;

   const double short_line =
      G_market_baseline + InpEntryATR * G_current_atr;

   // Fresh crossing only. Merely being far outside does not create a new signal.
   const bool fresh_long_cross =
      (G_prev_bid > 0.0
       && G_prev_bid >= long_line
       && tick.bid < long_line);

   const bool fresh_short_cross =
      (G_prev_ask > 0.0
       && G_prev_ask <= short_line
       && tick.ask > short_line);

   if(fresh_long_cross)
   {
      StartCycle(true);
      return;
   }

   if(fresh_short_cross)
   {
      StartCycle(false);
      return;
   }
}

//====================================================================
// Optimization score functions
//====================================================================
double Score_TanhSafe(const double x)
{
   if(x >= 20.0) return 1.0;
   if(x <= -20.0) return -1.0;

   const double e2x = MathExp(2.0*x);
   return (e2x-1.0)/(e2x+1.0);
}

double Score_Severity(const double value,
                      const double free_zone,
                      const double reference_value,
                      const double power)
{
   if(reference_value <= 0.0 || power <= 0.0)
      return 0.0;

   const double effective = value-free_zone;
   if(effective <= 0.0)
      return 0.0;

   return MathPow(effective/reference_value,power);
}

bool Score_ValidateParameters()
{
   if(InpScoreReturnWeight <= 0.0 ||
      InpScoreTargetCAGR <= 0.0)
      return false;

   if(InpScoreDDEventStart <= InpScoreDDEventEnd ||
      InpScoreDDEventEnd < 0.0 ||
      InpScoreDDEventFree < 0.0 ||
      InpScoreDDEventRef <= 0.0 ||
      InpScoreDDEventPower <= 0.0 ||
      InpScoreDDEventWeight < 0.0)
      return false;

   if(InpScoreUnderwaterFree < 0.0 ||
      InpScoreUnderwaterRef <= 0.0 ||
      InpScoreUnderwaterPower <= 0.0 ||
      InpScoreUnderwaterWeight < 0.0)
      return false;

   if(InpScoreFloatingFree < 0.0 ||
      InpScoreFloatingRef <= 0.0 ||
      InpScoreFloatingPower <= 0.0 ||
      InpScoreFloatingWeight < 0.0)
      return false;

   return true;
}

bool Score_Init()
{
   if(!Score_ValidateParameters())
   {
      Print("Invalid score parameters.");
      return false;
   }

   G_score_initial_capital = AccountInfoDouble(ACCOUNT_BALANCE);
   if(G_score_initial_capital <= 0.0)
      G_score_initial_capital = AccountInfoDouble(ACCOUNT_EQUITY);

   if(G_score_initial_capital <= 0.0)
      return false;

   double current_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(current_equity <= 0.0)
      current_equity = G_score_initial_capital;

   G_score_equity_peak          = MathMax(G_score_initial_capital,current_equity);
   G_score_start_time           = 0;
   G_score_last_observe_time    = 0;
   G_score_last_underwater_sev  = 0.0;
   G_score_last_floating_sev    = 0.0;
   G_score_underwater_integral  = 0.0;
   G_score_floating_integral    = 0.0;
   G_score_in_dd_event          = false;
   G_score_current_event_max_dd = 0.0;
   G_score_finished_event_sum   = 0.0;
   G_score_finished_event_count = 0;
   G_score_max_drawdown_ratio   = 0.0;
   G_score_max_floating_ratio   = 0.0;
   G_score_observation_count    = 0;

   return true;
}

void Score_CloseCurrentDrawdownEvent()
{
   if(!G_score_in_dd_event)
      return;

   G_score_finished_event_sum +=
      Score_Severity(G_score_current_event_max_dd,
                     InpScoreDDEventFree,
                     InpScoreDDEventRef,
                     InpScoreDDEventPower);

   G_score_finished_event_count++;
   G_score_in_dd_event = false;
   G_score_current_event_max_dd = 0.0;
}

void Score_Update()
{
   if(G_score_initial_capital <= 0.0)
   {
      if(!Score_Init())
         return;
   }

   const datetime now_time = TimeCurrent();
   if(now_time <= 0)
      return;

   double current_equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double current_balance = AccountInfoDouble(ACCOUNT_BALANCE);

   if(current_equity <= 0.0)  current_equity = current_balance;
   if(current_balance <= 0.0) current_balance = current_equity;
   if(current_equity < 0.0)   current_equity = 0.0;

   if(G_score_start_time == 0)
   {
      G_score_start_time        = now_time;
      G_score_last_observe_time = now_time;
      if(current_equity > G_score_equity_peak)
         G_score_equity_peak = current_equity;
   }

   if(G_score_last_observe_time > 0 &&
      now_time > G_score_last_observe_time)
   {
      const double delta_years =
         double(now_time-G_score_last_observe_time)
         / SCORE_SECONDS_PER_YEAR;

      G_score_underwater_integral +=
         G_score_last_underwater_sev * delta_years;

      G_score_floating_integral +=
         G_score_last_floating_sev * delta_years;
   }

   if(current_equity > G_score_equity_peak)
      G_score_equity_peak = current_equity;

   double current_drawdown_ratio = 0.0;
   if(G_score_equity_peak > current_equity)
      current_drawdown_ratio =
         (G_score_equity_peak-current_equity)
         / G_score_initial_capital;

   double current_floating_ratio = 0.0;
   if(current_balance > current_equity)
      current_floating_ratio =
         (current_balance-current_equity)
         / G_score_initial_capital;

   current_drawdown_ratio = MathMax(0.0,current_drawdown_ratio);
   current_floating_ratio = MathMax(0.0,current_floating_ratio);

   G_score_max_drawdown_ratio =
      MathMax(G_score_max_drawdown_ratio,current_drawdown_ratio);

   G_score_max_floating_ratio =
      MathMax(G_score_max_floating_ratio,current_floating_ratio);

   if(!G_score_in_dd_event &&
      current_drawdown_ratio >= InpScoreDDEventStart)
   {
      G_score_in_dd_event = true;
      G_score_current_event_max_dd = current_drawdown_ratio;
   }

   if(G_score_in_dd_event)
   {
      G_score_current_event_max_dd =
         MathMax(G_score_current_event_max_dd,current_drawdown_ratio);

      if(current_drawdown_ratio <= InpScoreDDEventEnd)
         Score_CloseCurrentDrawdownEvent();
   }

   G_score_last_underwater_sev =
      Score_Severity(current_drawdown_ratio,
                     InpScoreUnderwaterFree,
                     InpScoreUnderwaterRef,
                     InpScoreUnderwaterPower);

   G_score_last_floating_sev =
      Score_Severity(current_floating_ratio,
                     InpScoreFloatingFree,
                     InpScoreFloatingRef,
                     InpScoreFloatingPower);

   G_score_last_observe_time = now_time;
   G_score_observation_count++;
}

double Score_CalculateCAGR(const double final_equity,
                           const double initial_capital,
                           const double test_years)
{
   if(initial_capital <= 0.0 || test_years <= 0.0)
      return -1.0;

   const double equity_ratio = final_equity/initial_capital;
   if(equity_ratio <= 0.0)
      return -1.0;

   double annual_log_growth = MathLog(equity_ratio)/test_years;
   annual_log_growth = ClampValue(annual_log_growth,-20.0,20.0);

   return MathExp(annual_log_growth)-1.0;
}

double Score_Calculate()
{
   Score_Update();

   if(G_score_initial_capital <= 0.0 ||
      G_score_start_time <= 0 ||
      G_score_last_observe_time <= G_score_start_time)
      return SCORE_INVALID_VALUE;

   double final_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(final_equity <= 0.0)
      final_equity = AccountInfoDouble(ACCOUNT_BALANCE);
   if(final_equity < 0.0)
      final_equity = 0.0;

   const double test_years =
      double(G_score_last_observe_time-G_score_start_time)
      / SCORE_SECONDS_PER_YEAR;

   if(test_years <= 0.0)
      return SCORE_INVALID_VALUE;

   const double cagr =
      Score_CalculateCAGR(final_equity,
                          G_score_initial_capital,
                          test_years);

   const double return_score =
      InpScoreReturnWeight
      * Score_TanhSafe(cagr/InpScoreTargetCAGR);

   double total_event_severity = G_score_finished_event_sum;
   int total_event_count = G_score_finished_event_count;

   if(G_score_in_dd_event)
   {
      total_event_severity +=
         Score_Severity(G_score_current_event_max_dd,
                        InpScoreDDEventFree,
                        InpScoreDDEventRef,
                        InpScoreDDEventPower);
      total_event_count++;
   }

   const double drawdown_event_penalty =
      InpScoreDDEventWeight
      * total_event_severity
      / test_years;

   const double underwater_penalty =
      InpScoreUnderwaterWeight
      * G_score_underwater_integral
      / test_years;

   const double floating_penalty =
      InpScoreFloatingWeight
      * G_score_floating_integral
      / test_years;

   const double final_score =
      return_score
      - drawdown_event_penalty
      - underwater_penalty
      - floating_penalty;

   if(InpScorePrintDetail)
   {
      Print("SCORE",
            " initial=",DoubleToString(G_score_initial_capital,2),
            " final=",DoubleToString(final_equity,2),
            " years=",DoubleToString(test_years,4),
            " CAGR=",DoubleToString(cagr*100.0,2),"%",
            " return=",DoubleToString(return_score,2),
            " events=",IntegerToString(total_event_count),
            " maxDD=",DoubleToString(G_score_max_drawdown_ratio*100.0,2),"%",
            " maxFloating=",DoubleToString(G_score_max_floating_ratio*100.0,2),"%",
            " eventPenalty=",DoubleToString(drawdown_event_penalty,2),
            " underwaterPenalty=",DoubleToString(underwater_penalty,2),
            " floatingPenalty=",DoubleToString(floating_penalty,2),
            " finalScore=",DoubleToString(final_score,2));
   }

   return final_score;
}

//====================================================================
// MT5 event handlers
//====================================================================
int OnInit()
{
   if(!ValidateTradingInputs())
      return INIT_PARAMETERS_INCORRECT;

   if(!Score_Init())
      return INIT_PARAMETERS_INCORRECT;

   G_trade.SetExpertMagicNumber(InpMagicNumber);
   G_trade.SetDeviationInPoints(InpDeviationPoints);
   G_trade.SetTypeFillingBySymbol(_Symbol);

   G_atr_handle = iATR(_Symbol,InpBaselineTF,InpATRPeriod);
   if(G_atr_handle == INVALID_HANDLE)
   {
      Print("Failed to create ATR handle.");
      return INIT_FAILED;
   }

   if(!InitializeBaseline())
      return INIT_FAILED;

   int long_count=0,short_count=0;
   if(CountStrategyPositions(long_count,short_count) > 0)
   {
      Print("Existing strategy positions detected. Close them before attaching this research EA.");
      return INIT_FAILED;
   }

   G_last_bar_time = iTime(_Symbol,InpBaselineTF,0);

   MqlTick tick;
   if(SymbolInfoTick(_Symbol,tick))
   {
      G_prev_bid = tick.bid;
      G_prev_ask = tick.ask;
   }

   G_state = GRID_ARMED;
   ResetCycleState();
   UpdateDrawings();

   PrintEvent("Initialized. State=ARMED. Fresh crossing is required.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(G_atr_handle != INVALID_HANDLE)
      IndicatorRelease(G_atr_handle);

   DeleteLevelObjects();
}

void OnTick()
{
   // Capture account risk before any new trading action.
   Score_Update();

   if(IsNewBaselineBar())
      UpdateMarketBaselineOnNewBar();

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick))
      return;

   if(G_state == GRID_LOCKED)
      CheckLockedState();
   else if(G_state == GRID_ACTIVE_LONG ||
           G_state == GRID_ACTIVE_SHORT)
      ManageActiveCycle(tick);
   else
      CheckFreshEntryCrossing(tick);

   UpdateDrawings();

   G_prev_bid = tick.bid;
   G_prev_ask = tick.ask;
}

double OnTester()
{
   return Score_Calculate();
}
