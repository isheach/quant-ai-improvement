//+------------------------------------------------------------------+
//|  dsh_JPYGrid.mq5 —— USDJPYm「网格交易」EA（日元滚动线自研，v1.00）  |
//|                                                                  |
//|  作者：日元滚动优化 · 网格策略线研究代理（DeepSeek 子代理）         |
//|  日期：2026-09-12                                                |
//|                                                                  |
//|  ============ 为什么写这个 EA ============                        |
//|  前一条日元线（601 次回测 / 5 份报告）已正式否证两个**方向性**策略族：|
//|      dsh_TrendCore（趋势突破）  在 JPY 上无正期望                  |
//|      dsh_JPYRev  （区间反转）   在 JPY 上无正期望                  |
//|  ≥50 笔/年的 298/691 个 pass 里 PF>1.0 的数量 = 0，最高 PF 0.859。 |
//|  用户 2026-09-12 明确授权：「不止使用趋势算法，也可以使用网格」。    |
//|                                                                  |
//|  ★ 网格与方向性策略在**盈亏结构上是对偶的**：                       |
//|      - 趋势/反转：低胜率 + 大 R（靠少数大单）                       |
//|      - 网格     ：高胜率 + 小 R（靠大量小赢），左尾厚（单边行情）      |
//|  前一条线已量化：JPY 的**盈亏比 R 在所有配置里几乎恒定**            |
//|  （平均赢 +1.17~+1.35R、平均亏 −0.66~−0.99R），PF 的全部差异来自     |
//|  **胜率**。→ "换一个天生高胜率的结构"是唯一未被测过的方向。          |
//|                                                                  |
//|  ============ 量纲（本 EA 的可行性前提，broker_specs 直读）========= |
//|    USDJPYm: point=0.001  contract=100000  spread_points=10         |
//|             volume_min=0.01  stops_level=0  杠杆=200               |
//|             swap_long=0.0000   swap_short=-13.30                   |
//|    → 1 点 / 0.01 手 = $0.006489                                    |
//|    → 往返点差 10 点 = $0.0649 / 0.01 手                            |
//|    若 层间距=止盈=200 点(20 pip)：毛利 $1.298 − 点差 $0.065 =       |
//|       净 $1.233/层/周期 → **点差只占 5.0%**（REJECT-spread 门槛 30%）|
//|    ★ 这是三品种里唯一「小目标网格在成本上可行」的结构。             |
//|    ★ swap_long = 0：做多网格无持仓成本（做空付 −13.3 点/夜）        |
//|      → 默认方向取只做多，方向由 g_useLong / g_useShort 控制。       |
//|                                                                  |
//|  ============ 与 dsh_JPYRev/dsh_TrendCore 的三处纪律差异 =========== |
//|   ① 本 EA **不设券商侧 TP/SL**，只用**篮子均价**统一管理            |
//|      → 记账状态只有 (anchor, layers)，不依赖 ticket 映射，          |
//|        净额(Netting)与对冲(Hedging)账户都能跑。                    |
//|      → OnInit 探测 ACCOUNT_MARGIN_MODE 并写入 specs.txt。          |
//|   ② **全部 FileOpen/FolderCreate 带 FILE_COMMON**（父代理硬要求）    |
//|   ③ **实现 OnTradeTransaction 逐笔归因**：券商侧强平(SO)不会漏记；   |
//|      入场价/入场时间用 HistorySelectByPosition 反查，不依赖全局变量。|
//|                                                                  |
//|  ★★ 网格策略的特有风险（父代理要求必须在报告里量化）★★             |
//|    网格 = 逆势加仓 = 左尾极厚。没有硬上限的网格必然爆仓。           |
//|    本 EA 因此内置三层硬上限（默认全开）：                            |
//|      ① g_maxLayers     —— 单向最大层数（几何上限）                 |
//|      ② InpMaxTotalLot  —— 篮子总手数硬上限（保证金上限）            |
//|      ③ InpBasketStopPct—— 篮子浮亏 ≥ 净值 N% → 立即全平（左尾上限） |
//|    baskets.csv 逐周期记录 **max_float_pct（最坏浮亏）** ——           |
//|    这正是"最坏情况下的浮亏"的直接观测量。                           |
//|                                                                  |
//|  ★ 延迟：InpLatencyMs（口径标记，Sleep 在测试器里不推进模拟时间）    |
//|          + InpLatencyTicks（★真机制：等 N 个 tick 后用【当前价】下单，|
//|            在 Model=2 测试器里真实生效，见滚动优化线 报告_004 §11.1） |
//+------------------------------------------------------------------+
#property copyright "DeepSeek JPY rolling line"
#property version   "1.00"
#property strict

//==================== 输入参数 ====================
input group "=== GRID GEOMETRY ==="
input ENUM_TIMEFRAMES InpTF          = PERIOD_M5;   // 评估周期（枚举）★勿放进 opt
input int    InpTFMinutes            = 5;           // ★评估周期（分钟），>0 时覆盖 InpTF
input double InpGridStepPoints       = 200.0;       // 层间距（点，1点=0.001）
input double InpTPPoints             = 200.0;       // 篮子止盈距离（自均价，点）
input int    InpMaxLayers            = 8;           // 单向最大层数
input double InpLotPerLayer          = 0.01;        // 首层手数
input double InpLotMultiplier        = 1.0;         // 马丁倍数（1.0=固定手，>1 危险）
input double InpMaxLotPerLayer       = 0.10;        // 单层手数上限
input double InpMaxTotalLot          = 0.40;        // 篮子总手数硬上限

input group "=== DIRECTION ==="
input bool   InpGridLong             = true;        // 做多网格
input bool   InpGridShort            = false;       // 做空网格

input group "=== RISK (grid lifeline) ==="
input double InpBasketStopPct        = 15.0;        // 篮子浮亏 >= 净值 N% → 全平（0=关，不建议）
input bool   InpUseBasketTP          = true;        // 用篮子均价止盈
input int    InpCooldownMinAfterStop = 0;           // 篮子止损后冷却分钟数
input bool   InpCloseAllFriday       = false;       // 周五收盘前全平（防周末跳空）
input int    InpFridayStopHour       = 21;
input bool   InpUseDailyStop         = true;
input double InpDailyLossPct         = 5.0;
input bool   InpUseDDKill            = true;
input double InpMaxDDPct             = 30.0;
input int    InpDDCooldownMin        = 1440;        // >0 冷却解锁；0=永久锁（不推荐）
input bool   InpStopAfterDDLock      = false;       // false=评估口径 / true=交付口径

input group "=== RANGE GATE ==="
input bool   InpUseERGate            = true;
input double InpMaxER                = 0.35;        // 效率比上限，ER 低=震荡
input int    InpERPeriod             = 24;

input group "=== SESSION ==="
input bool   InpUseSessionFilter     = false;
input int    InpTradeStartHour       = 0;
input int    InpTradeEndHour         = 23;

input group "=== MISC ==="
input long   InpMagic                = 20260914;
input string InpRunTag               = "jpygrid";
input bool   InpWriteAudit           = true;
input bool   InpVerboseLog           = false;
input double InpDDMinDepthPct        = 2.0;
input double InpSlippagePoints       = 50;
input int    InpLatencyMs            = 300;         // 口径标记（Sleep 在测试器里不推进时间）
input int    InpLatencyTicks         = 0;           // ★>0 = 额外等 N 个 tick 再下单（真实生效）

//==================== 类型 ====================
struct DirStat
{
   int      n;
   double   vol;
   double   avg;
   double   pl;
   datetime oldest;
};

//==================== 全局状态 ====================
// ★input 变量在 MQL5 里是常量，不可赋值 → 方向开关用可写副本
bool     g_useLong = true;
bool     g_useShort = false;

int      g_idxL = 0;
int      g_idxS = 1;
double   g_anchor[2];
int      g_layers[2];
datetime g_basketOpen[2];
double   g_basketMaxFloatPct[2];
double   g_basketMaxFloatUsd[2];
int      g_basketMaxLayers[2];
double   g_basketMaxVol[2];
double   g_basketPeakProfit[2];
double   g_basketRealized[2];
bool     g_basketClosing[2];
string   g_basketReason[2];
double   g_basketCloseFloat[2];
double   g_cooldownUntil[2];
int      g_cycleSeq = 0;

long     g_lastEvalBar = -1;
long     g_curDayKey   = -1;
double   g_dayStartEquity = 0.0;
bool     g_dailyBlocked = false;
double   g_peakEquity  = 0.0;
bool     g_ddLocked    = false;
datetime g_ddLockUntil = 0;

double   g_er       = 1.0;
bool     g_erValid  = false;

int      g_pendDir   = 0;
int      g_pendTicks = 0;

ENUM_TIMEFRAMES g_tf = PERIOD_M5;

long     g_nTrades = 0, g_nWin = 0, g_dealsOut = 0, g_nOpens = 0;
double   g_sumWin = 0.0, g_sumLoss = 0.0;
double   g_bestWin = 0.0, g_worstLoss = 0.0;
double   g_realizedPnL = 0.0;
long     g_skipSession = 0, g_skipER = 0, g_skipGate = 0, g_skipLot = 0;
long     g_skipCap = 0, g_skipMargin = 0, g_openFail = 0;
long     g_noBars = 0;
long     g_basketStops = 0, g_basketTPs = 0, g_basketFriClose = 0;
double   g_worstFloatPctEver = 0.0;

int      g_ddEpisodes = 0, g_ddOpenCount = 0;
double   g_ddSumPct = 0.0, g_ddWorstPct = 0.0, g_ddSumRecoverH = 0.0;
int      g_ddOver10=0, g_ddOver15=0, g_ddOver20=0, g_ddOver25=0, g_ddOver30=0;
bool     g_epActive = false;
datetime g_epStart = 0, g_epTroughTime = 0;
double   g_epPeakEq = 0.0, g_epTroughEq = 0.0, g_epTroughUsd = 0.0, g_epTroughPct = 0.0;

int      g_curMon = -1;
double   g_monStartEq = 0.0, g_monPeakEq = 0.0, g_monTroughEq = 0.0, g_monWorstPct = 0.0;
int      g_monSamples = 0;

int      g_auditFh = INVALID_HANDLE;
int      g_ddFh    = INVALID_HANDLE;
int      g_monFh   = INVALID_HANDLE;
int      g_baskFh  = INVALID_HANDLE;

//==================== 基础工具（全部先定义后使用）====================
int TFMinutes(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_CURRENT) tf = (ENUM_TIMEFRAMES)Period();
   int v = (int)tf;
   if(v <= 0) return 0;
   if(v < 16385) return v;
   switch(v)
   {
      case 16385: return 60;
      case 16386: return 120;
      case 16387: return 180;
      case 16388: return 240;
      case 16390: return 360;
      case 16392: return 480;
      case 16396: return 720;
   }
   if(v >= 16398 && v < 32769) return 1440;
   if(v >= 32769 && v < 49153) return 10080;
   return 43200;
}

ENUM_ORDER_TYPE_FILLING PickFilling()
{
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   if((mode & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

// 每 1 手、每 1.0 价格变动的账户货币价值（不用会漂移的 SYMBOL_TRADE_TICK_VALUE）
double MoneyPerPricePerLotAt(double rate)
{
   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contract <= 0.0) return 0.0;
   if(rate <= 0.0) rate = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   string profitCcy = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_PROFIT);
   double v = contract;
   if(profitCcy != "USD" && rate > 0.0) v = contract / rate;
   return v;
}
double MoneyPerPricePerLot() { return MoneyPerPricePerLotAt(SymbolInfoDouble(_Symbol, SYMBOL_BID)); }

double AlignLotDown(double lot)
{
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(vstep <= 0.0) vstep = 0.01;
   lot = MathFloor(lot / vstep + 1e-9) * vstep;
   if(lot < vmin) lot = 0.0;
   if(vmax > 0.0 && lot > vmax) lot = vmax;
   int vd = 0; double s = vstep;
   while(s < 1.0 && vd < 8) { s *= 10.0; vd++; }
   return NormalizeDouble(lot, vd);
}

double LayerLot(int layerIdx)
{
   double lot = InpLotPerLayer * MathPow(InpLotMultiplier, (double)layerIdx);
   if(InpMaxLotPerLayer > 0.0 && lot > InpMaxLotPerLayer) lot = InpMaxLotPerLayer;
   return AlignLotDown(lot);
}

bool IsNewBucket(ENUM_TIMEFRAMES tf, long &store)
{
   int tfm = TFMinutes(tf);
   if(tfm <= 0) return false;
   long bucket = (long)TimeCurrent() / ((long)tfm * 60);
   if(bucket == store) return false;
   store = bucket;
   return true;
}

//==================== M1 → 大周期聚合（与 JPYRev 同源）====================
int BuildAggBars(ENUM_TIMEFRAMES tf, int wantBars,
                 double &o[], double &h[], double &l[], double &c[])
{
   int tfm = TFMinutes(tf);
   if(tfm <= 1 || wantBars < 2) return 0;
   int needM1 = tfm * (wantBars + 2);

   MqlRates m1[];
   ArraySetAsSeries(m1, false);
   ResetLastError();
   int got = CopyRates(_Symbol, PERIOD_M1, 0, needM1, m1);
   if(got < tfm * 2) return 0;

   ArrayResize(o, 0); ArrayResize(h, 0); ArrayResize(l, 0); ArrayResize(c, 0);
   long curBucket = -1; double bo=0,bh=0,bl=0,bc=0; bool isOpen=false;

   for(int i = 0; i < got; i++)
   {
      long bucket = (long)m1[i].time / ((long)tfm * 60);
      if(!isOpen || bucket != curBucket)
      {
         if(isOpen)
         {
            int n = ArraySize(c);
            ArrayResize(o, n+1); ArrayResize(h, n+1);
            ArrayResize(l, n+1); ArrayResize(c, n+1);
            o[n]=bo; h[n]=bh; l[n]=bl; c[n]=bc;
         }
         curBucket = bucket; bo = m1[i].open; bh = m1[i].high;
         bl = m1[i].low;     bc = m1[i].close; isOpen = true;
      }
      else
      {
         if(m1[i].high > bh) bh = m1[i].high;
         if(m1[i].low  < bl) bl = m1[i].low;
         bc = m1[i].close;
      }
   }
   int nAll = ArraySize(c);
   if(nAll < 2) return 0;
   ArrayResize(o, nAll-1); ArrayResize(h, nAll-1);
   ArrayResize(l, nAll-1); ArrayResize(c, nAll-1);
   return ArraySize(c);
}

double EfficiencyRatio(const double &c[], int period, int lastIdx)
{
   if(period <= 1 || lastIdx - period < 0) return 1.0;
   double net  = MathAbs(c[lastIdx] - c[lastIdx - period]);
   double path = 0.0;
   for(int i = lastIdx - period + 1; i <= lastIdx; i++)
      path += MathAbs(c[i] - c[i-1]);
   if(path <= 0.0) return 1.0;
   return net / path;
}

void RefreshER()
{
   if(!InpUseERGate) return;
   double o[], h[], l[], c[];
   int want = InpERPeriod + 5;
   int n = BuildAggBars(g_tf, want, o, h, l, c);
   if(n < InpERPeriod + 2) { g_erValid = false; g_noBars++; return; }
   g_er = EfficiencyRatio(c, InpERPeriod, n-1);
   g_erValid = true;
}

//==================== 仓位 / 篮子 ====================
bool GetDirStat(int dir, DirStat &s)
{
   s.n = 0; s.vol = 0.0; s.avg = 0.0; s.pl = 0.0; s.oldest = 0;
   double sumPV = 0.0; datetime oldest = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      int ptype = (int)PositionGetInteger(POSITION_TYPE);
      int pdir  = (ptype == POSITION_TYPE_BUY) ? 1 : -1;
      if(pdir != dir) continue;
      double v  = PositionGetDouble(POSITION_VOLUME);
      double op = PositionGetDouble(POSITION_PRICE_OPEN);
      s.n++;
      s.vol  += v;
      sumPV  += v * op;
      s.pl   += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      datetime t = (datetime)PositionGetInteger(POSITION_TIME);
      if(oldest == 0 || t < oldest) oldest = t;
   }
   if(s.vol > 0.0) s.avg = sumPV / s.vol;
   s.oldest = oldest;
   return (s.n > 0);
}

//==================== 审计：篮子周期重置 ====================
void ResetBasketState(int idx)
{
   g_basketMaxFloatPct[idx] = 0.0;
   g_basketMaxFloatUsd[idx] = 0.0;
   g_basketMaxVol[idx]      = 0.0;
   g_basketPeakProfit[idx]  = 0.0;
   g_basketMaxLayers[idx]   = 0;
   g_basketOpen[idx]        = 0;
   g_basketRealized[idx]    = 0.0;
   g_basketClosing[idx]     = false;
   g_basketReason[idx]      = "";
   g_basketCloseFloat[idx]  = 0.0;
}

string ReasonOrUnknown(string r)
{
   if(StringLen(r) > 0) return r;
   return "unknown";
}

void WriteBasketRow(int idx, string reason)
{
   if(g_baskFh == INVALID_HANDLE) return;
   if(g_basketMaxLayers[idx] <= 0) { ResetBasketState(idx); return; }
   g_cycleSeq++;
   datetime tEnd = TimeCurrent();
   double durH = (g_basketOpen[idx] > 0)
               ? (double)(tEnd - g_basketOpen[idx]) / 3600.0 : 0.0;
   FileWrite(g_baskFh, InpRunTag, IntegerToString(g_cycleSeq),
             (idx == g_idxL ? "long" : "short"),
             DoubleToString(g_anchor[idx], _Digits),
             IntegerToString(g_basketMaxLayers[idx]),
             DoubleToString(g_basketMaxVol[idx], 2),
             DoubleToString(g_basketPeakProfit[idx], 2),
             DoubleToString(g_basketMaxFloatUsd[idx], 2),   // ★最坏浮亏($)
             DoubleToString(g_basketMaxFloatPct[idx], 3),   // ★最坏浮亏(净值%)
             TimeToString((g_basketOpen[idx] > 0 ? g_basketOpen[idx] : tEnd), TIME_DATE|TIME_SECONDS),
             TimeToString(tEnd, TIME_DATE|TIME_SECONDS),
             DoubleToString(durH, 2),
             ReasonOrUnknown(reason),
             DoubleToString(g_basketRealized[idx], 2),
             DoubleToString(g_basketCloseFloat[idx], 2));
   FileFlush(g_baskFh);
   ResetBasketState(idx);
}

//==================== 归因 ====================
string DealReasonStr(int reason)
{
   switch(reason)
   {
      case DEAL_REASON_SL:     return "sl";
      case DEAL_REASON_TP:     return "tp";
      case DEAL_REASON_SO:     return "stopout";
      case DEAL_REASON_CLIENT: return "client";
      case DEAL_REASON_MOBILE: return "mobile";
      case DEAL_REASON_WEB:    return "web";
      case DEAL_REASON_EXPERT: return "expert";
   }
   return "other";
}

// ★入场价/入场时间用 HistorySelectByPosition 反查（券商侧平仓也正确）
void RecordDeal(ulong dealTicket)
{
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;
   long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY) return;

   long     posId  = HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
   double   exitP  = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double   vol    = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   double   profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                   + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                   + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
   datetime tExit  = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
   long     reason = HistoryDealGetInteger(dealTicket, DEAL_REASON);
   long     dtype  = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
   int      dir    = (dtype == DEAL_TYPE_SELL) ? 1 : -1;   // 出场是卖 → 原仓为多

   string reasonStr = "";
   {
      string cmt = HistoryDealGetString(dealTicket, DEAL_COMMENT);
      if(StringFind(cmt, "basket_stop")   >= 0) reasonStr = "basket_stop";
      else if(StringFind(cmt, "basket_tp")>= 0) reasonStr = "basket_tp";
      else if(StringFind(cmt, "friday")   >= 0) reasonStr = "friday";
      else if(StringFind(cmt, "dd_kill")  >= 0) reasonStr = "dd_kill";
      else if(StringFind(cmt, "daily")    >= 0) reasonStr = "daily_stop";
      else reasonStr = DealReasonStr((int)reason);
   }

   double   entryP = 0.0; datetime tEntry = 0; double entryVol = 0.0;
   if(HistorySelectByPosition(posId))
   {
      int tot = HistoryDealsTotal();
      for(int i = 0; i < tot; i++)
      {
         ulong dt = HistoryDealGetTicket(i);
         if(dt == 0) continue;
         if(HistoryDealGetInteger(dt, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
         entryP   = HistoryDealGetDouble(dt, DEAL_PRICE);
         tEntry   = (datetime)HistoryDealGetInteger(dt, DEAL_TIME);
         entryVol = HistoryDealGetDouble(dt, DEAL_VOLUME);
         break;
      }
   }
   if(entryP   <= 0.0) entryP   = exitP;
   if(tEntry   <= 0)   tEntry   = tExit;
   if(entryVol <= 0.0) entryVol = vol;

   long barSeconds = (long)tExit - (long)tEntry;
   if(barSeconds < 0) barSeconds = 0;

   // ★risk_money 口径：该层的「1 个网格步」风险
   //   = InpGridStepPoints × point × 手数 × 每价格单位每手价值
   double mpp   = MoneyPerPricePerLotAt(entryP);
   double riskM = InpGridStepPoints * _Point * entryVol * mpp;

   g_realizedPnL += profit;
   g_dealsOut++;
   g_nTrades++;
   if(profit > 0.0) { g_nWin++; g_sumWin += profit; if(profit > g_bestWin) g_bestWin = profit; }
   else             { g_sumLoss += profit; if(profit < g_worstLoss) g_worstLoss = profit; }

   int idx = (dir > 0) ? g_idxL : g_idxS;
   g_basketRealized[idx] += profit;

   if(g_auditFh != INVALID_HANDLE)
   {
      FileWrite(g_auditFh, InpRunTag, _Symbol,
                TimeToString(tExit, TIME_DATE|TIME_SECONDS),
                IntegerToString(dir),
                DoubleToString(entryP, _Digits),
                DoubleToString(exitP,  _Digits),
                DoubleToString(vol, 2),
                DoubleToString(profit, 2),
                DoubleToString(riskM, 2),
                TimeToString(tEntry, TIME_DATE|TIME_SECONDS),
                IntegerToString(barSeconds),
                DoubleToString(0.0, _Digits),
                reasonStr,
                IntegerToString(g_layers[idx]),
                IntegerToString(g_basketMaxLayers[idx]),
                DoubleToString(g_basketMaxVol[idx], 2),
                DoubleToString(g_basketMaxFloatPct[idx], 3),
                DoubleToString(g_basketMaxFloatUsd[idx], 2),
                "step" + DoubleToString(InpGridStepPoints, 0));
      FileFlush(g_auditFh);
   }
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      RecordDeal(trans.deal);
}

//==================== 风控 ====================
bool SessionAllowsOpen()
{
   if(!InpUseSessionFilter) return true;
   MqlDateTime t; TimeToStruct(TimeCurrent(), t);
   if(t.day_of_week == 0 || t.day_of_week == 6) return false;
   if(InpTradeStartHour <= InpTradeEndHour)
      return (t.hour >= InpTradeStartHour && t.hour <= InpTradeEndHour);
   return (t.hour >= InpTradeStartHour || t.hour <= InpTradeEndHour);
}

void RefreshAccountRisk()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   MqlDateTime t; TimeToStruct(TimeCurrent(), t);
   long dayKey = (long)t.year * 10000 + (long)t.mon * 100 + (long)t.day;

   if(dayKey != g_curDayKey)
   { g_curDayKey = dayKey; g_dayStartEquity = eq; g_dailyBlocked = false; }

   if(InpUseDailyStop && !g_dailyBlocked && g_dayStartEquity > 0.0)
   {
      double lossPct = (g_dayStartEquity - eq) / g_dayStartEquity * 100.0;
      if(lossPct >= InpDailyLossPct) g_dailyBlocked = true;
   }
   if(eq > g_peakEquity) g_peakEquity = eq;

   if(InpUseDDKill && g_peakEquity > 0.0)
   {
      double dd = (g_peakEquity - eq) / g_peakEquity * 100.0;
      if(g_ddLocked && InpDDCooldownMin > 0 && g_ddLockUntil > 0
         && TimeCurrent() >= g_ddLockUntil)
      {
         g_ddLocked = false; g_ddLockUntil = 0; g_peakEquity = eq;
         if(InpVerboseLog)
            PrintFormat("[%s] DD冷却结束，建立新阶段高点 %.2f，恢复交易", InpRunTag, eq);
      }
      if(InpStopAfterDDLock && dd >= InpMaxDDPct)
      {
         if(!g_ddLocked)
         { g_ddLocked = true;
           PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，交付口径【永久停止】", InpRunTag, dd); }
      }
      else if(dd >= InpMaxDDPct && !g_ddLocked)
      {
         g_ddLocked = true;
         if(InpDDCooldownMin > 0)
         {
            g_ddLockUntil = TimeCurrent() + (datetime)(InpDDCooldownMin * 60);
            PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，冷却 %d 分钟后解锁（峰值 %.2f 现 %.2f）",
                        InpRunTag, dd, InpDDCooldownMin, g_peakEquity, eq);
         }
         else
            PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，永久锁（InpDDCooldownMin=0）", InpRunTag, dd);
      }
   }
}

//==================== 回撤事件 / 月度 ====================
void DDEpisodeLog(const string kind, double recoverH)
{
   if(g_ddFh == INVALID_HANDLE) return;
   FileWrite(g_ddFh, InpRunTag, kind,
             TimeToString(g_epStart, TIME_DATE|TIME_SECONDS),
             TimeToString(g_epTroughTime, TIME_DATE|TIME_SECONDS),
             TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
             DoubleToString(g_epPeakEq, 2), DoubleToString(g_epTroughEq, 2),
             DoubleToString(g_epTroughUsd, 2), DoubleToString(g_epTroughPct, 2),
             DoubleToString(recoverH, 1));
   FileFlush(g_ddFh);
}

void DDCloseEpisode()
{
   if(!g_epActive) return;
   double recoverH = (double)(TimeCurrent() - g_epStart) / 3600.0;
   g_ddEpisodes++;
   g_ddSumPct += g_epTroughPct;
   g_ddSumRecoverH += recoverH;
   if(g_epTroughPct > g_ddWorstPct) g_ddWorstPct = g_epTroughPct;
   if(g_epTroughPct >= 10.0) g_ddOver10++;
   if(g_epTroughPct >= 15.0) g_ddOver15++;
   if(g_epTroughPct >= 20.0) g_ddOver20++;
   if(g_epTroughPct >= 25.0) g_ddOver25++;
   if(g_epTroughPct >= 30.0) g_ddOver30++;
   DDEpisodeLog("recovered", recoverH);
   g_epActive = false;
}

void TrackEquityCurve()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   MqlDateTime t; TimeToStruct(TimeCurrent(), t);

   if(g_epActive)
   {
      if(eq < g_epTroughEq)
      {
         g_epTroughEq = eq; g_epTroughTime = TimeCurrent();
         g_epTroughUsd = g_epPeakEq - eq;
         g_epTroughPct = (g_epPeakEq > 0.0) ? (g_epPeakEq - eq) / g_epPeakEq * 100.0 : 0.0;
      }
      if(eq >= g_epPeakEq)
      {
         if(g_epTroughPct >= InpDDMinDepthPct) DDCloseEpisode();
         else g_epActive = false;
      }
   }
   else if(g_peakEquity > 0.0)
   {
      double dd = (g_peakEquity - eq) / g_peakEquity * 100.0;
      if(dd >= InpDDMinDepthPct)
      { g_epActive = true; g_epStart = TimeCurrent(); g_epPeakEq = g_peakEquity;
        g_epTroughEq = eq; g_epTroughTime = TimeCurrent();
        g_epTroughUsd = g_epPeakEq - eq; g_epTroughPct = dd; }
   }

   int monKey = t.year * 100 + t.mon;
   if(monKey != g_curMon)
   {
      if(g_curMon > 0 && g_monFh != INVALID_HANDLE)
         FileWrite(g_monFh, InpRunTag, IntegerToString(g_curMon),
                   DoubleToString(g_monStartEq, 2), DoubleToString(g_monPeakEq, 2),
                   DoubleToString(g_monTroughEq, 2), DoubleToString(g_monWorstPct, 2),
                   IntegerToString(g_monSamples));
      g_curMon = monKey; g_monStartEq = eq; g_monPeakEq = eq;
      g_monTroughEq = eq; g_monWorstPct = 0.0; g_monSamples = 0;
   }
   g_monSamples++;
   if(eq > g_monPeakEq) g_monPeakEq = eq;
   if(eq < g_monTroughEq) g_monTroughEq = eq;
   if(g_monPeakEq > 0.0)
   {
      double mp = (g_monPeakEq - g_monTroughEq) / g_monPeakEq * 100.0;
      if(mp > g_monWorstPct) g_monWorstPct = mp;
   }
}

//==================== 平仓 ====================
int CloseDir(int dir, string reason, bool markBasket)
{
   ulong tks[];
   int cnt = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      int ptype = (int)PositionGetInteger(POSITION_TYPE);
      int pdir  = (ptype == POSITION_TYPE_BUY) ? 1 : -1;
      if(pdir != dir) continue;
      ArrayResize(tks, cnt+1);
      tks[cnt] = tk; cnt++;
   }

   int idx = (dir > 0) ? g_idxL : g_idxS;
   DirStat s; GetDirStat(dir, s);
   if(markBasket)
   {
      g_basketCloseFloat[idx] = s.pl;
      g_basketReason[idx]     = ReasonOrUnknown(reason);
      g_basketClosing[idx]    = true;
   }

   int done = 0;
   for(int i = 0; i < cnt; i++)
   {
      if(!PositionSelectByTicket(tks[i])) continue;
      double vol  = PositionGetDouble(POSITION_VOLUME);
      int    ptyp = (int)PositionGetInteger(POSITION_TYPE);
      MqlTradeRequest req; MqlTradeResult res;
      ZeroMemory(req); ZeroMemory(res);
      req.action       = TRADE_ACTION_DEAL;
      req.symbol       = _Symbol;
      req.position     = tks[i];
      req.volume       = vol;
      req.deviation    = (ulong)InpSlippagePoints;
      req.magic        = InpMagic;
      req.comment      = "grid_" + reason;
      req.type         = (ptyp == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      req.type_filling = PickFilling();
      req.price        = (ptyp == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                     : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      if(OrderSend(req, res) && (res.retcode == TRADE_RETCODE_DONE ||
                                 res.retcode == TRADE_RETCODE_PLACED)) done++;
      else if(InpVerboseLog)
         PrintFormat("[%s] 平仓失败 reason=%s retcode=%d err=%d",
                     InpRunTag, reason, res.retcode, GetLastError());
   }
   if(done > 0 && StringFind(reason, "basket_stop") >= 0 && InpCooldownMinAfterStop > 0)
      g_cooldownUntil[idx] = (double)TimeCurrent() + (double)(InpCooldownMinAfterStop * 60);

   g_anchor[idx] = 0.0;
   g_layers[idx] = 0;

   // ★在这里（而不是等 n==0）落盘 baskets.csv：
   //   平仓后 OnTick 会在同一 tick 立刻重新锚定并开第 0 层，
   //   若等到 n==0 才写，g_basketMaxLayers 会被下一轮继承 → 周期统计错乱。
   if(done > 0 && markBasket) WriteBasketRow(idx, ReasonOrUnknown(reason));
   return done;
}

//==================== 开层 ====================
bool MarginOk(double lot)
{
   double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(price <= 0.0) return true;
   double lev = (double)AccountInfoInteger(ACCOUNT_LEVERAGE);
   if(lev <= 0.0) return true;
   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double need = lot * contract / lev;
   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   if(freeMargin <= 0.0) return true;
   return (need < freeMargin * 0.60);
}

bool DoOpenLayer(int dir)
{
   int idx = (dir > 0) ? g_idxL : g_idxS;
   if(g_layers[idx] >= InpMaxLayers) return false;

   double lot = LayerLot(g_layers[idx]);
   if(lot <= 0.0) { g_skipLot++; return false; }

   DirStat s; GetDirStat(dir, s);
   if(InpMaxTotalLot > 0.0 && s.vol + lot > InpMaxTotalLot + 1e-9)
   { g_skipCap++; return false; }
   if(!MarginOk(lot)) { g_skipMargin++; return false; }

   double price = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0) return false;

   if(InpLatencyMs > 0)
   {
      Sleep(InpLatencyMs);
      double p2 = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(p2 > 0.0) price = p2;
   }

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = _Symbol;
   req.volume       = lot;
   req.type         = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price        = price;
   req.deviation    = (ulong)InpSlippagePoints;
   req.magic        = InpMagic;
   req.comment      = "grid_layer";
   req.type_filling = PickFilling();
   // ★不设券商侧 TP/SL：网格由篮子均价统一管理

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      g_openFail++;
      if(InpVerboseLog)
         PrintFormat("[%s] 开层失败 dir=%d layer=%d lot=%.2f retcode=%d err=%d",
                     InpRunTag, dir, g_layers[idx], lot, res.retcode, GetLastError());
      return false;
   }
   g_nOpens++;
   if(g_layers[idx] == 0) g_anchor[idx] = price;
   g_layers[idx]++;

   if(g_basketOpen[idx] == 0) g_basketOpen[idx] = TimeCurrent();
   if(g_layers[idx] > g_basketMaxLayers[idx]) g_basketMaxLayers[idx] = g_layers[idx];

   if(InpVerboseLog)
      PrintFormat("[%s] OPEN dir=%d layer=%d lot=%.2f price=%.3f anchor=%.3f",
                  InpRunTag, dir, g_layers[idx], lot, price, g_anchor[idx]);
   return true;
}

//==================== 状态自愈 ====================
void Reconcile(int dir)
{
   int idx = (dir > 0) ? g_idxL : g_idxS;
   DirStat s; GetDirStat(dir, s);
   if(s.n == 0)
   {
      if(g_layers[idx] != 0)
      {
         if(InpVerboseLog)
            PrintFormat("[%s] 方向 %d 仓位被外部清空（券商强平/滑点），重置 layers %d→0",
                        InpRunTag, dir, g_layers[idx]);
         g_layers[idx] = 0;
         g_anchor[idx] = 0.0;
      }
      return;
   }
   if(g_layers[idx] != s.n)
   {
      if(InpVerboseLog)
         PrintFormat("[%s] 方向 %d 层数不一致 记账=%d 实际=%d，以实际为准",
                     InpRunTag, dir, g_layers[idx], s.n);
      g_layers[idx] = s.n;
   }
   if(g_anchor[idx] <= 0.0)
   {
      double stepP = InpGridStepPoints * _Point;
      g_anchor[idx] = s.avg + (double)dir * stepP * (double)(s.n - 1) / 2.0;
      if(InpVerboseLog)
         PrintFormat("[%s] 方向 %d 锚点丢失，由均价反推 anchor=%.3f", InpRunTag, dir, g_anchor[idx]);
   }
}

//==================== 生命周期 ====================
string AuditDir() { return "dshtrend/" + InpRunTag; }

string MarginModeStr()
{
   long m = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   if(m == ACCOUNT_MARGIN_MODE_RETAIL_HEDGING) return "HEDGING";
   if(m == ACCOUNT_MARGIN_MODE_RETAIL_NETTING) return "NETTING";
   if(m == ACCOUNT_MARGIN_MODE_EXCHANGE)       return "EXCHANGE";
   return "UNKNOWN";
}

void WriteSpecsFile()
{
   int fh = FileOpen(AuditDir() + "/specs.txt", FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(fh == INVALID_HANDLE) return;
   long mm = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   double mpp = MoneyPerPricePerLot();
   double worstLoss = 0.0, totLot = 0.0;
   for(int k = 0; k < InpMaxLayers; k++)
   {
      double lk = LayerLot(k);
      totLot += lk;
      worstLoss += lk * (double)(InpMaxLayers - 1 - k) * InpGridStepPoints * _Point * mpp;
   }
   double lev = MathMax(1.0, (double)AccountInfoInteger(ACCOUNT_LEVERAGE));
   double marginNeed = totLot * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE) / lev;

   FileWriteString(fh, "run_tag=" + InpRunTag + "\r\n");
   FileWriteString(fh, "symbol=" + _Symbol + "\r\n");
   FileWriteString(fh, "digits=" + IntegerToString(_Digits) + "\r\n");
   FileWriteString(fh, "point=" + DoubleToString(_Point, 8) + "\r\n");
   FileWriteString(fh, "contract=" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE), 2) + "\r\n");
   FileWriteString(fh, "volume_min=" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), 2) + "\r\n");
   FileWriteString(fh, "volume_step=" + DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP), 2) + "\r\n");
   FileWriteString(fh, "stops_level=" + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL)) + "\r\n");
   FileWriteString(fh, "spread_points=" + IntegerToString((int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD)) + "\r\n");
   FileWriteString(fh, "leverage=" + IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE)) + "\r\n");
   FileWriteString(fh, "margin_mode=" + IntegerToString((int)mm) + " (" + MarginModeStr() + ")\r\n");
   FileWriteString(fh, "equity_init=" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + "\r\n");
   FileWriteString(fh, "g_tf_minutes=" + IntegerToString(TFMinutes(g_tf)) + "\r\n");
   FileWriteString(fh, "grid_step_points=" + DoubleToString(InpGridStepPoints, 1) + "\r\n");
   FileWriteString(fh, "tp_points=" + DoubleToString(InpTPPoints, 1) + "\r\n");
   FileWriteString(fh, "max_layers=" + IntegerToString(InpMaxLayers) + "\r\n");
   FileWriteString(fh, "lot_per_layer=" + DoubleToString(InpLotPerLayer, 2) + "\r\n");
   FileWriteString(fh, "lot_multiplier=" + DoubleToString(InpLotMultiplier, 4) + "\r\n");
   FileWriteString(fh, "max_lot_per_layer=" + DoubleToString(InpMaxLotPerLayer, 2) + "\r\n");
   FileWriteString(fh, "max_total_lot=" + DoubleToString(InpMaxTotalLot, 2) + "\r\n");
   FileWriteString(fh, "basket_stop_pct=" + DoubleToString(InpBasketStopPct, 2) + "\r\n");
   FileWriteString(fh, "use_basket_tp=" + (InpUseBasketTP ? "1" : "0") + "\r\n");
   FileWriteString(fh, "grid_long=" + (g_useLong ? "1" : "0") + "\r\n");
   FileWriteString(fh, "grid_short=" + (g_useShort ? "1" : "0") + "\r\n");
   FileWriteString(fh, "use_er_gate=" + (InpUseERGate ? "1" : "0") + "\r\n");
   FileWriteString(fh, "max_er=" + DoubleToString(InpMaxER, 3) + "\r\n");
   FileWriteString(fh, "er_period=" + IntegerToString(InpERPeriod) + "\r\n");
   FileWriteString(fh, "latency_ms=" + IntegerToString(InpLatencyMs) + "\r\n");
   FileWriteString(fh, "latency_ticks=" + IntegerToString(InpLatencyTicks) + "\r\n");
   FileWriteString(fh, "max_dd_pct=" + DoubleToString(InpMaxDDPct, 2) + "\r\n");
   FileWriteString(fh, "daily_loss_pct=" + DoubleToString(InpDailyLossPct, 2) + "\r\n");
   FileWriteString(fh, "--- risk math (initial equity) ---\r\n");
   FileWriteString(fh, "planned_total_lot=" + DoubleToString(totLot, 3) + "\r\n");
   FileWriteString(fh, "planned_margin_usd=" + DoubleToString(marginNeed, 2) + "\r\n");
   FileWriteString(fh, "planned_worst_float_usd=" + DoubleToString(worstLoss, 2) + "\r\n");
   FileWriteString(fh, "planned_worst_float_pct=" +
                   DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY) > 0.0
                                  ? worstLoss / AccountInfoDouble(ACCOUNT_EQUITY) * 100.0 : 0.0, 2) + "\r\n");
   FileWriteString(fh, "money_per_price_per_lot=" + DoubleToString(mpp, 2) + "\r\n");
   FileWriteString(fh, "usd_per_point_per_0.01lot=" + DoubleToString(0.01 * _Point * mpp, 8) + "\r\n");
   FileClose(fh);
}

int OnInit()
{
   if(InpGridStepPoints <= 0.0 || InpTPPoints <= 0.0)
   { Print("InpGridStepPoints / InpTPPoints 必须 > 0"); return INIT_PARAMETERS_INCORRECT; }
   if(InpMaxLayers < 1 || InpMaxLayers > 64)
   { Print("InpMaxLayers 必须在 [1,64]"); return INIT_PARAMETERS_INCORRECT; }
   if(InpLotPerLayer <= 0.0)
   { Print("InpLotPerLayer 必须 > 0"); return INIT_PARAMETERS_INCORRECT; }
   if(!InpGridLong && !InpGridShort)
   { Print("至少启用一个方向"); return INIT_PARAMETERS_INCORRECT; }
   if(InpBasketStopPct <= 0.0)
      PrintFormat("[%s] ⚠ 警告：InpBasketStopPct=0，网格没有左尾硬上限（不推荐）", InpRunTag);

   g_useLong  = InpGridLong;
   g_useShort = InpGridShort;

   g_tf = InpTF;
   if(InpTFMinutes > 0)
      g_tf = (ENUM_TIMEFRAMES)InpTFMinutes;
   else
   {
      int tfm = TFMinutes(g_tf);
      if(tfm <= 1)
      {
         PrintFormat("[%s] ★警告：InpTF 解析为 %d（TFMinutes=%d <=1）。已自动回退 M5。请改用 InpTFMinutes。",
                     InpRunTag, (int)g_tf, tfm);
         g_tf = PERIOD_M5;
      }
   }
   if(TFMinutes(g_tf) <= 1)
   { PrintFormat("[%s] ★致命：InpTFMinutes=%d 无效（需 >=2）", InpRunTag, InpTFMinutes);
     return INIT_PARAMETERS_INCORRECT; }

   long mm = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   if(mm != ACCOUNT_MARGIN_MODE_RETAIL_HEDGING && g_useLong && g_useShort)
   {
      PrintFormat("[%s] ★警告：账户是 %s，无法同时持有多空 → 自动关闭做空网格",
                  InpRunTag, MarginModeStr());
      g_useShort = false;
   }

   for(int i = 0; i < 2; i++) ResetBasketState(i);
   g_cooldownUntil[0] = 0.0; g_cooldownUntil[1] = 0.0;

   g_peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayStartEquity = g_peakEquity;

   if(InpWriteAudit)
   {
      FolderCreate("dshtrend", FILE_COMMON);
      FolderCreate(AuditDir(), FILE_COMMON);

      WriteSpecsFile();

      g_auditFh = FileOpen(AuditDir() + "/trades.csv",
                           FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_auditFh != INVALID_HANDLE)
         FileWrite(g_auditFh, "run_tag","symbol","time","dir","entry","exit",
                   "vol","pnl","risk_money","entry_time","bar_seconds",
                   "atr_at_entry","exit_reason",
                   "layer_idx","basket_layers","basket_lot",
                   "basket_max_float_pct","basket_max_float_usd","step_tag");

      g_baskFh = FileOpen(AuditDir() + "/baskets.csv",
                          FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_baskFh != INVALID_HANDLE)
         FileWrite(g_baskFh, "run_tag","cycle","dir","anchor","max_layers","max_lot",
                   "peak_profit_usd","max_float_usd","max_float_pct",
                   "open_time","close_time","duration_h","exit_reason",
                   "realized_pnl","float_at_close");

      g_ddFh = FileOpen(AuditDir() + "/dd_episodes.csv",
                        FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_ddFh != INVALID_HANDLE)
         FileWrite(g_ddFh, "run_tag","kind","peak_time","trough_time","end_time",
                   "peak_equity","trough_equity","dd_usd","dd_pct","recover_hours");

      g_monFh = FileOpen(AuditDir() + "/dd_monthly.csv",
                         FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_monFh != INVALID_HANDLE)
         FileWrite(g_monFh, "run_tag","month","equity_start","equity_peak",
                   "equity_trough","dd_pct","samples");
   }

   PrintFormat("[%s] init ok TF=%dmin mode=%s step=%.0f tp=%.0f maxLayers=%d lot=%.2f x%.2f "
               "maxTotalLot=%.2f basketStop=%.1f%% ERgate=%s(%.2f) long=%s short=%s latMs=%d latTicks=%d",
               InpRunTag, TFMinutes(g_tf), MarginModeStr(), InpGridStepPoints, InpTPPoints,
               InpMaxLayers, InpLotPerLayer, InpLotMultiplier, InpMaxTotalLot, InpBasketStopPct,
               (InpUseERGate?"on":"off"), InpMaxER,
               (g_useLong?"on":"off"), (g_useShort?"on":"off"),
               InpLatencyMs, InpLatencyTicks);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   for(int i = 0; i < 2; i++)
   {
      int d = (i == g_idxL) ? 1 : -1;
      DirStat s; GetDirStat(d, s);
      if(s.n > 0 && g_basketMaxLayers[i] > 0) WriteBasketRow(i, "still_open");
   }
   if(g_epActive && g_epTroughPct >= InpDDMinDepthPct)
      DDEpisodeLog("still_open", (double)(TimeCurrent() - g_epStart) / 3600.0);
   if(g_monFh != INVALID_HANDLE && g_curMon > 0)
      FileWrite(g_monFh, InpRunTag, IntegerToString(g_curMon),
                DoubleToString(g_monStartEq, 2), DoubleToString(g_monPeakEq, 2),
                DoubleToString(g_monTroughEq, 2), DoubleToString(g_monWorstPct, 2),
                IntegerToString(g_monSamples));
   if(g_auditFh != INVALID_HANDLE) FileClose(g_auditFh);
   if(g_ddFh    != INVALID_HANDLE) FileClose(g_ddFh);
   if(g_monFh   != INVALID_HANDLE) FileClose(g_monFh);
   if(g_baskFh  != INVALID_HANDLE) FileClose(g_baskFh);

   double wr = (g_nTrades > 0) ? 100.0 * (double)g_nWin / (double)g_nTrades : 0.0;
   double avgDepth = (g_ddEpisodes > 0) ? g_ddSumPct / g_ddEpisodes : 0.0;
   double avgRec   = (g_ddEpisodes > 0) ? g_ddSumRecoverH / g_ddEpisodes : 0.0;
   PrintFormat("[%s] FLOAT_WORST 全程最坏篮子浮亏=%.2f%% | 篮子止损=%d 篮子止盈=%d 周五平=%d | 开层次数=%d 平仓笔数=%d",
               InpRunTag, g_worstFloatPctEver, (int)g_basketStops, (int)g_basketTPs,
               (int)g_basketFriClose, (int)g_nOpens, (int)g_nTrades);
   PrintFormat("[%s] DD_EVENTS 已恢复=%d 未恢复=%d 平均深度=%.2f%% 最深=%.2f%% 平均恢复=%.1fh | >=10%%:%d >=15%%:%d >=20%%:%d >=25%%:%d >=30%%:%d",
               InpRunTag, g_ddEpisodes, g_ddOpenCount, avgDepth, g_ddWorstPct, avgRec,
               g_ddOver10, g_ddOver15, g_ddOver20, g_ddOver25, g_ddOver30);
   PrintFormat("[%s] === 结束 reason=%d 平仓笔数=%d 胜率=%.1f%% 总盈利=%.2f 总亏损=%.2f 最大单盈=%.2f 最大单亏=%.2f "
               "日损阻断=%s 回撤锁=%s 拒单[时段=%d ER=%d 闸门=%d 手数=%d 总手上限=%d 保证金=%d 开仓失败=%d] 无bar=%d ===",
               InpRunTag, reason, (int)g_nTrades, wr, g_sumWin, g_sumLoss,
               g_bestWin, g_worstLoss,
               g_dailyBlocked?"是":"否", g_ddLocked?"是":"否",
               (int)g_skipSession, (int)g_skipER, (int)g_skipGate, (int)g_skipLot,
               (int)g_skipCap, (int)g_skipMargin, (int)g_openFail, (int)g_noBars);
}

//==================== 单方向管理 ====================
void ManageDir(int dir)
{
   int idx = (dir > 0) ? g_idxL : g_idxS;
   DirStat s; GetDirStat(dir, s);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= 0.0) return;

   if(s.n == 0)
   {
      // 兜底：外部平仓（券商强平 / stop-out / 手动）时 CloseDir 不会被调用，
      // 这里补一条周期记录，避免 baskets.csv 丢周期。
      if(g_basketMaxLayers[idx] > 0)
         WriteBasketRow(idx, g_basketClosing[idx] ? ReasonOrUnknown(g_basketReason[idx]) : "external_close");
      return;
   }

   // ① 篮子止损（最高优先级：左尾硬上限）
   if(InpBasketStopPct > 0.0)
   {
      double lossLimit = eq * InpBasketStopPct / 100.0;
      if(-s.pl >= lossLimit)
      {
         g_basketStops++;
         if(InpVerboseLog)
            PrintFormat("[%s] ★篮子浮亏 %.2f (%.2f%%) 达上限 → 全平 dir=%d layers=%d",
                        InpRunTag, -s.pl, -s.pl / eq * 100.0, dir, g_layers[idx]);
         CloseDir(dir, "basket_stop", true);
         return;
      }
   }

   // ② 记录最坏浮亏 / 峰值浮盈 / 峰值手数
   {
      double fPct = (s.pl < 0.0) ? (-s.pl / eq * 100.0) : 0.0;
      if(fPct > g_basketMaxFloatPct[idx])
      { g_basketMaxFloatPct[idx] = fPct; g_basketMaxFloatUsd[idx] = -s.pl; }
      if(fPct > g_worstFloatPctEver) g_worstFloatPctEver = fPct;
      if(s.pl > g_basketPeakProfit[idx]) g_basketPeakProfit[idx] = s.pl;
      if(s.vol > g_basketMaxVol[idx])    g_basketMaxVol[idx] = s.vol;
   }

   // ③ 篮子止盈（自均价）
   if(InpUseBasketTP)
   {
      double tgt = s.avg + (double)dir * InpTPPoints * _Point;
      double cur = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                             : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      bool hit = (dir > 0) ? (cur >= tgt) : (cur <= tgt);
      if(hit) { g_basketTPs++; CloseDir(dir, "basket_tp", true); return; }
   }

   // ④ 加层
   if(g_ddLocked || g_dailyBlocked) return;
   if(TimeCurrent() < (datetime)g_cooldownUntil[idx]) return;
   if(g_layers[idx] >= InpMaxLayers) return;
   if(!SessionAllowsOpen()) { g_skipSession++; return; }

   if(InpUseERGate)
   {
      if(g_erValid) { if(g_er > InpMaxER) { g_skipER++; return; } }
      else g_skipGate++;      // 无 bar 信息 → fail-open，计数以便诊断
   }

   double stepP = InpGridStepPoints * _Point;
   double nextLevel = g_anchor[idx] - (double)dir * stepP * (double)g_layers[idx];
   double px = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                         : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(px <= 0.0) return;

   bool crossed = (dir > 0) ? (px <= nextLevel) : (px >= nextLevel);
   if(!crossed) return;

   if(InpLatencyTicks > 0)
   {
      if(g_pendTicks <= 0) { g_pendDir = dir; g_pendTicks = InpLatencyTicks; }
      return;
   }
   DoOpenLayer(dir);
}

//==================== 主循环 ====================
void OnTick()
{
   RefreshAccountRisk();
   TrackEquityCurve();

   // ★tick 级延迟队列（在 Model=2 测试器里真实生效）
   if(g_pendTicks > 0)
   {
      g_pendTicks--;
      if(g_pendTicks <= 0)
      {
         int d = g_pendDir; g_pendDir = 0;
         if(d != 0) DoOpenLayer(d);
      }
   }

   if(IsNewBucket(g_tf, g_lastEvalBar)) RefreshER();

   Reconcile(1);
   Reconcile(-1);

   if(InpCloseAllFriday)
   {
      MqlDateTime t; TimeToStruct(TimeCurrent(), t);
      if(t.day_of_week == 5 && t.hour >= InpFridayStopHour)
      {
         bool any = false;
         if(g_useLong)  { DirStat s1; if(GetDirStat(1, s1))  { CloseDir(1, "friday", true);  any = true; } }
         if(g_useShort) { DirStat s2; if(GetDirStat(-1, s2)) { CloseDir(-1, "friday", true); any = true; } }
         if(any) g_basketFriClose++;
         return;
      }
   }

   if(g_useLong)  ManageDir(1);
   if(g_useShort) ManageDir(-1);

   if(g_ddLocked || g_dailyBlocked) return;
   if(!SessionAllowsOpen()) return;

   // 空仓 → 开第 0 层（建立锚点）
   if(g_useLong)
   {
      DirStat s; if(!GetDirStat(1, s))
      {
         if(TimeCurrent() >= (datetime)g_cooldownUntil[g_idxL])
         {
            bool okGate = true;
            if(InpUseERGate && g_erValid && g_er > InpMaxER) { okGate = false; g_skipER++; }
            if(okGate)
            {
               if(InpLatencyTicks > 0) { if(g_pendTicks <= 0) { g_pendDir = 1; g_pendTicks = InpLatencyTicks; } }
               else DoOpenLayer(1);
            }
         }
      }
   }
   if(g_useShort)
   {
      DirStat s; if(!GetDirStat(-1, s))
      {
         if(TimeCurrent() >= (datetime)g_cooldownUntil[g_idxS])
         {
            bool okGate = true;
            if(InpUseERGate && g_erValid && g_er > InpMaxER) { okGate = false; g_skipER++; }
            if(okGate)
            {
               if(InpLatencyTicks > 0) { if(g_pendTicks <= 0) { g_pendDir = -1; g_pendTicks = InpLatencyTicks; } }
               else DoOpenLayer(-1);
            }
         }
      }
   }
}
//+------------------------------------------------------------------+
