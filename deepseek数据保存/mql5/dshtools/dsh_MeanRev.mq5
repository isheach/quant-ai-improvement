//+------------------------------------------------------------------+
//|  dsh_MeanRev.mq5                                                 |
//|  DeepSeek / 新量化策略 — 第二套：均值回归（供 BTCUSDm 开发）          |
//|                                                                  |
//|  ============ 为什么换设计（有数据依据，不是拍脑袋）================
//|  第一套（dsh_TrendCore，突破式趋势跟随）在 BTC 上三段验证失败：
//|    • 基准 SL2.0/TF30/突破60：训练 +175.89 / 验证 +30.33 / 测试 −11.95
//|    • 36 组参数扫描训练段全部为正（"平台"），但最优的候选
//|      A(SL3.0/TF15) 测试 −125.25(DD 55%)、B(SL1.5/TF60) 验证 −81.75
//|    • 逐年拆解：训练段 +175.89 几乎全来自 2018 年(+218.3)，其余 5 年 −42
//|    • 收紧止损到 0.5×ATR 后三段全负（训练 DD 73%）
//|                                                                  |
//|  对 BTC M1 的统计特性分析（2025-09 ~ 2026-09，50 万根 M1）：
//|    • 各周期收益自相关全部 |值|<0.05 → **方向基本不可线性预测**
//|      （5min lag1 −0.0055 / 30min lag2 −0.0151 / 1h +0.0029）
//|    • M30 峰度 = **14.23** → 极端肥尾
//|    • 波动率高度聚集（肥尾 + 聚集）
//|  → 结论：**别预测方向，去利用"极端偏离后的回摆"**。
//|     这既是数据分析的结论，也解释了为什么趋势突破在样本外必死。
//|                                                                  |
//|  ============ 本 EA 的设计 ============
//|  1) 不预测趋势：以 SMA(N) 为"公允价"，用 σ 衡量偏离程度
//|  2) 只在【极端偏离】入场：|price − SMA| ≥ k×σ （k 由参数给）
//|  3) 出场三重：
//|       tp    : 回到 SMA + 一部分（回归目标，不是回到中轴）
//|       stop  : 偏离继续扩大到 (k+sl)×σ （自适应止损，随波动放大）
//|       time  : 超过 N 根仍未回归就走（避免无限期暴露）
//|  4) 时段过滤：只在【低波动时段】交易（实测 UTC 01-05 波动最小）
//|  5) 账户风控：日损 / 净值高水位回撤（均按净值百分比）
//|  6) 回撤事件统计：一年几次、每次多深、多久恢复（用户明确要求的指标）
//|                                                                  |
//|  ============ 关键设计取舍 ============
//|  • 用 σ（标准差）而不是 ATR 定止损：均值回归的"错"是"偏离还在扩大"，
//|    用统计尺度衡量更自然，且能自适应波动率聚集。
//|  • 止损相对【宽】：均值回归最怕被噪声扫掉。第一套的教训是止损一紧
//|    胜率就崩。所以这里止损距离由 (k+sl)×σ 给出，比趋势法宽。
//|  • 单笔风险仍按净值百分比控制（手数反推），账户级风险不放大。
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property strict

//==================== 输入 ====================
input group "=== 手数 / 风险（按账户百分比）==="
input double InpRiskPct        = 0.7;    // 每笔风险 = 净值的百分之几
input double InpMaxLot         = 1.00;
input bool   InpUseEquityForRisk = true;
input bool   InpAllowMinLotOvershoot = true;  // 算出的手数小于最小手时按最小手交易
input double InpMinLotMaxRiskPct = 3.0;       // 上述模式下的风险硬上限（占净值%）

input group "=== 均值回归信号 ==="
input ENUM_TIMEFRAMES InpTF    = PERIOD_M30;
input int    InpMAPeriod       = 48;     // 公允价均线周期（M30×48 ≈ 1 天）
input int    InpSigmaPeriod    = 96;     // σ 估计窗口
input double InpEntrySigma     = 2.0;    // 入场：偏离 ≥ 这么多 σ
input double InpExitSigmaFrac  = 0.5;    // 出场：回到 (1−frac)×偏离 处（0=回到中轴）
input double InpStopSigma      = 2.0;    // 止损：偏离再扩大这么多 σ 就认错
input int    InpMaxBarsInTrade = 48;     // 时间止损：超过 N 根 TF 仍未止盈就走（0=关闭）
input bool   InpAllowLong      = true;
input bool   InpAllowShort     = true;

input group "=== 时段过滤（实测 UTC 01-05 波动最小）==="
input bool   InpUseSessionFilter = true;
input int    InpTradeStartHour   = 1;
input int    InpTradeEndHour     = 5;
input bool   InpNoFridayLate     = false;
input int    InpFridayStopHour   = 20;

input group "=== 账户级风控（净值百分比）==="
input bool   InpUseDailyStop   = true;
input double InpDailyLossPct   = 6.0;
input bool   InpUseDDKill      = false;
input double InpMaxDDPct       = 25.0;

input group "=== 审计 / 统计 ==="
input long   InpMagic          = 20260912;
input string InpRunTag         = "meanrev";
input bool   InpWriteAudit     = true;
input double InpSlippagePoints = 50;
// ★模拟真实网络延迟：读价 → Sleep(InpLatencyMs) → 用【新价】下单
input int    InpLatencyMs       = 300;   // 模拟下单延迟（毫秒）
input bool   InpVerboseLog     = false;
input double InpDDMinDepthPct  = 2.0;    // 回撤事件最小深度%

//==================== 全局 ====================
double   g_point, g_tickValue, g_tickSize;
int      g_digits;

ulong    g_ticket = 0;
double   g_entryPrice = 0.0, g_curSL = 0.0, g_atrAtEntry = 0.0, g_riskMoney = 0.0;
double   g_sigmaAtEntry = 0.0, g_maAtEntry = 0.0;
datetime g_entryTime = 0;
int      g_barsInTrade = 0;

long     g_lastBar = -1;
datetime g_curDay = 0;
double   g_dayStartEquity = 0.0, g_peakEquity = 0.0;
bool     g_dailyBlocked = false, g_ddLocked = false;

long     g_nTrades = 0, g_nWin = 0;
double   g_sumWin = 0.0, g_sumLoss = 0.0, g_bestWin = 0.0, g_worstLoss = 0.0;
long     g_rejNoMargin = 0, g_rejCap = 0;

int      g_auditFh = INVALID_HANDLE, g_ddFh = INVALID_HANDLE, g_monFh = INVALID_HANDLE;

// 回撤事件
bool     g_epActive=false; datetime g_epStart=0, g_epTroughTime=0;
double   g_epPeakEq=0, g_epTroughEq=0, g_epTroughPct=0, g_epTroughUsd=0;
int      g_ddEpisodes=0, g_ddOpen=0;
double   g_ddSumPct=0, g_ddWorstPct=0, g_ddSumRecH=0;
int      g_ddOver10=0,g_ddOver15=0,g_ddOver20=0,g_ddOver25=0,g_ddOver30=0;
int      g_curMon=-1, g_monSamples=0;
double   g_monStartEq=0, g_monPeakEq=0, g_monTroughEq=0, g_monWorstPct=0;

// 诊断
double   g_lastSigma=0, g_lastMA=0, g_lastPrice=0;
long     g_sigNone=0, g_sigBlockedSession=0;

//+------------------------------------------------------------------+
int TFMinutes(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_CURRENT) tf = (ENUM_TIMEFRAMES)Period();
   int v = (int)tf;
   if(v <= 0) return 0;
   if(v < 16385) return v;
   switch(v)
   {
      case 16385: return 60;   case 16386: return 120;
      case 16387: return 180;  case 16388: return 240;
      case 16390: return 360;  case 16392: return 480;
      case 16396: return 720;
   }
   if(v >= 16398 && v < 32769) return 1440;
   if(v >= 32769 && v < 49153) return 10080;
   return 43200;
}

bool IsNewBucket(ENUM_TIMEFRAMES tf, long &store)
{
   int tfm = TFMinutes(tf);
   if(tfm <= 0) return false;
   long b = (long)TimeCurrent() / ((long)tfm * 60);
   if(b == store) return false;
   store = b;
   return true;
}

// ★每手每单位价格变动的账户货币价值
//   （与 dsh_TrendCore 相同的稳健口径：优先用合约规模，避免 TICK_VALUE 漂移）
double MoneyPerPricePerLot()
{
   double cs = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double bid= SymbolInfoDouble(_Symbol, SYMBOL_BID);
   string prof = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_PROFIT);
   string acc  = AccountInfoString(ACCOUNT_CURRENCY);
   if(cs > 0.0)
   {
      if(prof == acc) return cs;
      double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tv > 0.0 && ts > 0.0 && bid > 0.0)
      {
         double ratio = tv / ts, exp = cs / bid;
         if(ratio > exp/50.0 && ratio < exp*50.0) return ratio;
         return exp;
      }
      return (bid > 0.0) ? cs / bid : 0.0;
   }
   return 0.0;
}

double AlignLot(double lot)
{
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vstep= SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(vstep <= 0.0) vstep = 0.01;
   lot = MathFloor(lot / vstep + 0.5) * vstep;
   if(lot < vmin) lot = vmin;
   if(vmax > 0.0 && lot > vmax) lot = vmax;
   if(InpMaxLot > 0.0 && lot > InpMaxLot) lot = InpMaxLot;
   int vd = 0; double s = vstep;
   while(s < 1.0 && vd < 8) { s *= 10.0; vd++; }
   return NormalizeDouble(lot, vd);
}

ENUM_ORDER_TYPE_FILLING PickFilling()
{
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   if((mode & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

double LotForRisk(double stopDistPrice, double &riskUsed)
{
   riskUsed = 0.0;
   double base = InpUseEquityForRisk ? AccountInfoDouble(ACCOUNT_EQUITY)
                                     : AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = base * InpRiskPct / 100.0;
   double mpp = MoneyPerPricePerLot();
   if(mpp <= 0.0) return 0.0;
   double perLot = stopDistPrice * mpp;
   if(perLot <= 0.0) return 0.0;

   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lot = riskMoney / perLot;
   if(lot < vmin)
   {
      if(!InpAllowMinLotOvershoot) { g_rejNoMargin++; return 0.0; }
      double minRisk = vmin * perLot;
      if(minRisk > base * InpMinLotMaxRiskPct / 100.0) { g_rejCap++; return 0.0; }
      riskUsed = minRisk;
      return vmin;
   }
   lot = AlignLot(lot);
   riskUsed = lot * perLot;
   return lot;
}

//==================== 统计窗口 ====================
// 返回已完成 bar 的 SMA 与 σ（用已收盘 bar，避免用未完成的当前 bar）
bool GetStats(double &ma, double &sigma, double &lastClose, int &bars)
{
   ma = 0; sigma = 0; lastClose = 0; bars = 0;
   int need = MathMax(InpMAPeriod, InpSigmaPeriod) + 5;
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int got = CopyRates(_Symbol, InpTF, 0, need, r);
   if(got < need) return false;
   bars = got;

   int lastClosed = got - 1;          // 最后一根是未完成 bar
   int end = lastClosed - 1;          // 用「上一根已收盘」作为信号 bar
   if(end < InpSigmaPeriod) return false;

   double sum = 0.0;
   for(int i = end - InpMAPeriod + 1; i <= end; i++) sum += r[i].close;
   ma = sum / InpMAPeriod;

   double s2 = 0.0;
   for(int i = end - InpSigmaPeriod + 1; i <= end; i++)
   {
      double d = r[i].close - ma;
      s2 += d * d;
   }
   sigma = MathSqrt(s2 / InpSigmaPeriod);
   lastClose = r[end].close;
   return (sigma > 0.0);
}

//==================== 时段 ====================
bool SessionAllowsOpen()
{
   if(!InpUseSessionFilter) return true;
   MqlDateTime t; TimeToStruct(TimeCurrent(), t);
   if(t.day_of_week == 0 || t.day_of_week == 6) return false;
   if(InpNoFridayLate && t.day_of_week == 5 && t.hour >= InpFridayStopHour) return false;
   if(InpTradeStartHour <= InpTradeEndHour)
      return (t.hour >= InpTradeStartHour && t.hour <= InpTradeEndHour);
   return (t.hour >= InpTradeStartHour || t.hour <= InpTradeEndHour);
}

//==================== 持仓 ====================
int CountMyPositions()
{
   int n = 0;
   for(int i = PositionsTotal()-1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      n++;
   }
   return n;
}
ulong FindMyTicket()
{
   for(int i = PositionsTotal()-1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      return tk;
   }
   return 0;
}
bool HasPosition()
{
   if(CountMyPositions() == 0) { g_ticket = 0; return false; }
   if(g_ticket == 0 || !PositionSelectByTicket(g_ticket))
   {
      ulong tk = FindMyTicket();
      if(tk == 0) { g_ticket = 0; return false; }
      g_ticket = tk;
   }
   return true;
}
long   PosType(){ return PositionGetInteger(POSITION_TYPE); }
double PosOpen(){ return PositionGetDouble(POSITION_PRICE_OPEN); }
double PosSL()  { return PositionGetDouble(POSITION_SL); }
double PosVol() { return PositionGetDouble(POSITION_VOLUME); }

string DealReasonStr(long r)
{
   switch((int)r)
   {
      case DEAL_REASON_SL: return "sl";
      case DEAL_REASON_TP: return "tp";
      case DEAL_REASON_SO: return "stopout";
      case DEAL_REASON_EXPERT: return "expert";
      case DEAL_REASON_CLIENT: return "client";
   }
   return "other";
}

void RecordExitDeal(ulong dealTicket)
{
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;
   long et = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(et != DEAL_ENTRY_OUT && et != DEAL_ENTRY_OUT_BY) return;

   double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                 + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                 + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
   double price = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double vol   = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   long   rs    = HistoryDealGetInteger(dealTicket, DEAL_REASON);
   datetime t   = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
   long   dt    = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
   int    dir   = (dt == DEAL_TYPE_SELL) ? 1 : -1;

   g_nTrades++;
   if(profit > 0) { g_nWin++; g_sumWin += profit; if(profit > g_bestWin) g_bestWin = profit; }
   else           { g_sumLoss += profit; if(profit < g_worstLoss) g_worstLoss = profit; }

   if(g_auditFh != INVALID_HANDLE)
   {
      FileWrite(g_auditFh, InpRunTag, _Symbol,
                TimeToString(t, TIME_DATE|TIME_SECONDS), (string)dir,
                "sig=" + DoubleToString(g_sigmaAtEntry,2), "ma=" + DoubleToString(g_maAtEntry,2),
                DoubleToString(price, _Digits), DoubleToString(vol,2),
                DoubleToString(profit,2), DoubleToString(g_riskMoney,2),
                (string)g_barsInTrade, DealReasonStr(rs));
      FileFlush(g_auditFh);
   }
   if(InpVerboseLog)
      PrintFormat("[%s] EXIT %s dir=%d vol=%.2f price=%.2f pnl=%.2f bars=%d",
                  InpRunTag, DealReasonStr(rs), dir, vol, price, profit, g_barsInTrade);
   g_ticket = 0; g_curSL = 0.0; g_barsInTrade = 0;
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD) RecordExitDeal(trans.deal);
}

bool ClosePosition(string reason)
{
   if(!HasPosition()) return false;
   int dir = (int)PosType();
   double vol = PosVol();
   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action   = TRADE_ACTION_DEAL;
   req.symbol   = _Symbol;
   req.position = g_ticket;
   req.volume   = vol;
   req.deviation= (ulong)InpSlippagePoints;
   req.magic    = InpMagic;
   req.comment  = "close_" + reason;
   req.type     = (dir == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.type_filling = PickFilling();
   req.price    = (dir == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                             : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      PrintFormat("[%s] 平仓失败 %s ret=%d err=%d", InpRunTag, reason, res.retcode, GetLastError());
      return false;
   }
   if(InpVerboseLog) PrintFormat("[%s] CLOSE-REQ %s @%.2f", InpRunTag, reason, res.price);
   g_ticket = 0;
   return true;
}

//==================== 开仓 ====================
// dir: +1 做多, -1 做空
bool OpenBySignal(int dir, double sigma, double ma, double stopDist, string reason)
{
   double riskUsed = 0.0;
   double lot = LotForRisk(stopDist, riskUsed);
   if(lot <= 0.0) return false;

   double price = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double sl = (dir > 0) ? price - stopDist : price + stopDist;

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action = TRADE_ACTION_DEAL;
   req.symbol = _Symbol;
   req.volume = lot;
   req.type   = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price  = price;
   req.sl     = NormalizeDouble(sl, _Digits);
   req.deviation = (ulong)InpSlippagePoints;
   req.magic  = InpMagic;
   req.comment= "mr_" + reason;
   req.type_filling = PickFilling();

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      PrintFormat("[%s] 开仓失败 ret=%d err=%d", InpRunTag, res.retcode, GetLastError());
      return false;
   }
   g_ticket = FindMyTicket();
   if(g_ticket == 0) { PrintFormat("[%s] ★开仓后找不到持仓", InpRunTag); return false; }

   g_entryPrice = PosOpen();
   g_curSL      = PosSL();
   g_sigmaAtEntry = sigma;
   g_maAtEntry    = ma;
   g_atrAtEntry   = stopDist;
   g_riskMoney    = riskUsed;
   g_entryTime    = TimeCurrent();
   g_barsInTrade  = 0;

   if(InpVerboseLog)
      PrintFormat("[%s] OPEN %s dir=%d lot=%.2f price=%.2f sl=%.2f risk=%.2f (%.2f%%) sigma=%.2f ma=%.2f",
                  InpRunTag, reason, dir, lot, g_entryPrice, g_curSL, riskUsed,
                  riskUsed/AccountInfoDouble(ACCOUNT_EQUITY)*100.0, sigma, ma);
   return true;
}

//==================== 账户风控 + 回撤事件 ====================
void DDEpisodeLog(const string kind, double recoverH)
{
   if(g_ddFh == INVALID_HANDLE) return;
   FileWrite(g_ddFh, InpRunTag, kind,
             TimeToString(g_epStart, TIME_DATE|TIME_SECONDS),
             TimeToString(g_epTroughTime, TIME_DATE|TIME_SECONDS),
             TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
             DoubleToString(g_epPeakEq,2), DoubleToString(g_epTroughEq,2),
             DoubleToString(g_epTroughUsd,2), DoubleToString(g_epTroughPct,2),
             DoubleToString(recoverH,1));
   FileFlush(g_ddFh);
}
void DDClose()
{
   if(!g_epActive) return;
   double rh = (double)(TimeCurrent()-g_epStart)/3600.0;
   g_ddEpisodes++; g_ddSumPct += g_epTroughPct; g_ddSumRecH += rh;
   if(g_epTroughPct > g_ddWorstPct) g_ddWorstPct = g_epTroughPct;
   if(g_epTroughPct>=10) g_ddOver10++;
   if(g_epTroughPct>=15) g_ddOver15++;
   if(g_epTroughPct>=20) g_ddOver20++;
   if(g_epTroughPct>=25) g_ddOver25++;
   if(g_epTroughPct>=30) g_ddOver30++;
   DDEpisodeLog("recovered", rh);
   g_epActive = false;
}
void DDStart(datetime now, double eq)
{
   g_epActive=true; g_epStart=now;
   g_epPeakEq = (g_peakEquity > eq ? g_peakEquity : eq);
   if(g_epPeakEq <= 0) g_epPeakEq = eq;
   g_epTroughEq=eq; g_epTroughTime=now; g_epTroughPct=0; g_epTroughUsd=0;
}
void DDMonthRoll(datetime now)
{
   MqlDateTime t; TimeToStruct(now,t);
   int ym = t.year*12 + t.mon;
   if(ym == g_curMon) return;
   if(g_curMon > 0 && g_monSamples > 0 && g_monFh != INVALID_HANDLE)
   {
      int y=(g_curMon-1)/12, m=g_curMon-y*12;
      FileWrite(g_monFh, InpRunTag, StringFormat("%04d-%02d",y,m),
                DoubleToString(g_monStartEq,2),DoubleToString(g_monPeakEq,2),
                DoubleToString(g_monTroughEq,2),DoubleToString(g_monWorstPct,2),
                (string)g_monSamples);
      FileFlush(g_monFh);
   }
   g_curMon=ym; g_monStartEq=AccountInfoDouble(ACCOUNT_EQUITY);
   g_monPeakEq=g_monStartEq; g_monTroughEq=g_monStartEq;
   g_monWorstPct=0; g_monSamples=0;
}

void RefreshAccountRisk()
{
   datetime now = TimeCurrent();
   MqlDateTime t; TimeToStruct(now,t);
   t.hour=0; t.min=0; t.sec=0;
   datetime day = StructToTime(t);
   if(day != g_curDay)
   {
      g_curDay = day;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_dailyBlocked = false;
   }
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq > g_peakEquity) g_peakEquity = eq;

   // 回撤事件
   DDMonthRoll(now);
   g_monSamples++;
   if(eq > g_monPeakEq) g_monPeakEq = eq;
   if(eq < g_monTroughEq) g_monTroughEq = eq;
   if(g_monPeakEq > 0)
   {
      double mp = (g_monPeakEq-g_monTroughEq)/g_monPeakEq*100.0;
      if(mp > g_monWorstPct) g_monWorstPct = mp;
   }
   if(!g_epActive) DDStart(now, eq);
   else if(eq > g_epPeakEq)
   {
      if(g_epTroughPct >= InpDDMinDepthPct) DDClose();
      else g_epActive = false;
      DDStart(now, eq);
   }
   else if(eq < g_epTroughEq)
   {
      g_epTroughEq=eq; g_epTroughTime=now;
      if(g_epPeakEq>0){ g_epTroughPct=(g_epPeakEq-eq)/g_epPeakEq*100.0; g_epTroughUsd=g_epPeakEq-eq; }
   }

   if(InpUseDailyStop && g_dayStartEquity > 0)
   {
      double dd = (g_dayStartEquity-eq)/g_dayStartEquity*100.0;
      if(dd >= InpDailyLossPct)
      {
         if(!g_dailyBlocked)
            PrintFormat("[%s] 日内亏损达 %.2f%%，今日停止开新仓", InpRunTag, dd);
         g_dailyBlocked = true;
      }
   }
   if(InpUseDDKill && g_peakEquity > 0)
   {
      double dd = (g_peakEquity-eq)/g_peakEquity*100.0;
      if(dd >= InpMaxDDPct && !g_ddLocked)
      {
         g_ddLocked = true;
         PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，永久锁", InpRunTag, dd);
         ClosePosition("dd_kill");
      }
   }
}

//==================== 生命周期 ====================
int OnInit()
{
   if(InpMAPeriod < 5 || InpSigmaPeriod < 10) { Print("周期参数太小"); return INIT_PARAMETERS_INCORRECT; }
   if(InpEntrySigma <= 0.0 || InpStopSigma <= 0.0) { Print("sigma 参数非法"); return INIT_PARAMETERS_INCORRECT; }
   if(InpRiskPct <= 0.0 || InpRiskPct > 20.0) { Print("InpRiskPct 非法"); return INIT_PARAMETERS_INCORRECT; }

   g_digits = _Digits;
   g_point  = _Point;
   g_peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayStartEquity = g_peakEquity;

   if(InpWriteAudit)
   {
      FolderCreate("dshtrend", FILE_COMMON);
      FolderCreate("dshtrend/" + InpRunTag, FILE_COMMON);
      g_auditFh = FileOpen("dshtrend/"+InpRunTag+"/trades.csv",
                           FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_auditFh != INVALID_HANDLE)
         FileWrite(g_auditFh,"run_tag","symbol","time","dir","sigma_at_entry","ma_at_entry",
                   "exit_price","vol","pnl","risk_money","bars_held","exit_reason");
      g_ddFh = FileOpen("dshtrend/"+InpRunTag+"/dd_episodes.csv",
                        FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_ddFh != INVALID_HANDLE)
         FileWrite(g_ddFh,"run_tag","kind","peak_time","trough_time","end_time",
                   "peak_equity","trough_equity","dd_usd","dd_pct","recover_hours");
      g_monFh = FileOpen("dshtrend/"+InpRunTag+"/dd_monthly.csv",
                         FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_monFh != INVALID_HANDLE)
         FileWrite(g_monFh,"run_tag","month","equity_start","equity_peak",
                   "equity_trough","dd_pct","samples");
   }

   PrintFormat("[%s] 启动 %s digits=%d 每手每单位价格=%s | TF=%s MA=%d sigma=%d 入场k=%.2f 止损k=%.2f 时间止损=%d根 | 风险=%.2f%% | 时段=%s(%d-%d UTC)",
               InpRunTag, _Symbol, g_digits, DoubleToString(MoneyPerPricePerLot(),4),
               EnumToString(InpTF), InpMAPeriod, InpSigmaPeriod,
               InpEntrySigma, InpStopSigma, InpMaxBarsInTrade, InpRiskPct,
               InpUseSessionFilter?"开":"关", InpTradeStartHour, InpTradeEndHour);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_epActive && g_epTroughPct >= InpDDMinDepthPct)
   {
      g_ddOpen++;
      DDEpisodeLog("still_open", (double)(TimeCurrent()-g_epStart)/3600.0);
   }
   if(g_curMon > 0 && g_monSamples > 0 && g_monFh != INVALID_HANDLE)
   {
      int y=(g_curMon-1)/12, m=g_curMon-y*12;
      FileWrite(g_monFh, InpRunTag, StringFormat("%04d-%02d",y,m),
                DoubleToString(g_monStartEq,2),DoubleToString(g_monPeakEq,2),
                DoubleToString(g_monTroughEq,2),DoubleToString(g_monWorstPct,2),
                (string)g_monSamples);
      FileFlush(g_monFh);
   }
   if(g_auditFh!=INVALID_HANDLE){FileFlush(g_auditFh);FileClose(g_auditFh);}
   if(g_ddFh!=INVALID_HANDLE){FileFlush(g_ddFh);FileClose(g_ddFh);}
   if(g_monFh!=INVALID_HANDLE){FileFlush(g_monFh);FileClose(g_monFh);}

   double wr = (g_nTrades>0)?100.0*(double)g_nWin/(double)g_nTrades:0.0;
   PrintFormat("[%s] === 结束 reason=%d 交易=%d 胜率=%.1f%% 总盈利=%.2f 总亏损=%.2f 最大单盈=%.2f 最大单亏=%.2f 手数被拒=%d/%d ===",
               InpRunTag, reason, (int)g_nTrades, wr, g_sumWin, g_sumLoss,
               g_bestWin, g_worstLoss, (int)g_rejNoMargin, (int)g_rejCap);
   double ddAvg=(g_ddEpisodes>0)?g_ddSumPct/g_ddEpisodes:0.0;
   double recAvg=(g_ddEpisodes>0)?g_ddSumRecH/g_ddEpisodes:0.0;
   PrintFormat("[%s] DD_EVENTS 已恢复=%d 未恢复=%d 平均深度=%.2f%% 最深=%.2f%% 平均恢复=%.1fh | >=10%%:%d >=15%%:%d >=20%%:%d >=25%%:%d >=30%%:%d",
               InpRunTag, g_ddEpisodes, g_ddOpen, ddAvg, g_ddWorstPct, recAvg,
               g_ddOver10,g_ddOver15,g_ddOver20,g_ddOver25,g_ddOver30);
}

//==================== 主循环 ====================
void OnTick()
{
   RefreshAccountRisk();

   // 1) 管理已有持仓：止盈（回归）/ 时间止损
   if(HasPosition())
   {
      int dir = (int)PosType();
      double open = PosOpen();
      double cur = (dir == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                              : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      // 时间止损：按 TF 根数计
      if(IsNewBucket(InpTF, g_lastBar)) g_barsInTrade++;
      if(InpMaxBarsInTrade > 0 && g_barsInTrade >= InpMaxBarsInTrade)
      { ClosePosition("time"); return; }

      // 回归止盈：回到 均值 + 剩余比例×入场偏离
      double dev = open - g_maAtEntry;
      double target = g_maAtEntry + dev * InpExitSigmaFrac;
      if(dir == POSITION_TYPE_BUY  && cur >= target) { ClosePosition("revert"); return; }
      if(dir == POSITION_TYPE_SELL && cur <= target) { ClosePosition("revert"); return; }
      return;
   }

   if(g_ddLocked || g_dailyBlocked) return;
   if(!IsNewBucket(InpTF, g_lastBar)) return;

   double ma, sigma, px; int bars;
   if(!GetStats(ma, sigma, px, bars)) return;
   g_lastSigma = sigma; g_lastMA = ma; g_lastPrice = px;

   double dev = px - ma;
   double devSig = dev / sigma;

   if(!SessionAllowsOpen()) { g_sigBlockedSession++; return; }

   int dir = 0;
   if(devSig <= -InpEntrySigma && InpAllowLong)  dir = +1;   // 低于均值太多 → 做多
   if(devSig >=  InpEntrySigma && InpAllowShort) dir = -1;   // 高于均值太多 → 做空
   if(dir == 0) { g_sigNone++; return; }

   double stopDist = InpStopSigma * sigma;
   if(stopDist <= 0.0) return;
   long sl_lvl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(sl_lvl > 0) { double mn=(double)sl_lvl*_Point; if(stopDist<mn) stopDist=mn; }

   OpenBySignal(dir, sigma, ma, stopDist, devSig>0?"over":"under");
}
//+------------------------------------------------------------------+
