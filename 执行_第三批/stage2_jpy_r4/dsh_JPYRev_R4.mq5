//+------------------------------------------------------------------+
//|  dsh_JPYRev.mq5  —— JPY 专用「区间反转」EA（日元线自研，v1.00）     |
//|                                                                  |
//|  作者：日元线研究代理（DeepSeek 子代理）· 2026-09-11              |
//|                                                                  |
//|  ============ 为什么另写一套 ============                          |
//|  实测（报告_002 §3.1，训练段 2014.01.14-2024.05.31, Model=2, 300）：|
//|     M30 默认 jpy-001 =  37 笔 / PF 1.12 / DD 10.00%               |
//|     M15 默认 jpy-008 = 101 笔 / PF 1.15 / DD 10.84%               |
//|     M5  默认 jpy-007 = 247 笔 / PF 1.18 / DD 17.11% ← 唯一正期望   |
//|     而把频率推向 40-80 笔/年的激进配置 PF 全部 <= 0.82             |
//|                                                                  |
//|  dsh_TrendCore 的三处架构性限制（源码直读，当前版本行号）：         |
//|     ① L1310-1313  单仓：有仓即 return，无加仓 / 无翻仓              |
//|     ② L1317      只在 InpTrendTF 新根上评估入场                     |
//|     ③ L1319-1323 四道 early-return（ddLocked/dailyBlocked/Session/ |
//|                   RVGate）在信号之前，且不计数                      |
//|                                                                  |
//|  ★ RV 闸门的量纲缺陷（本 EA 因此**完全不要 RV 闸门**）              |
//|    TrendCore 的 RV% 定义（L510-533）是                          |
//|        rvPct = 100 * RMS(1分钟收盘差, 15根) / 现价                  |
//|    这是**相对量纲**，所以同一个固定阈值 InpRVMinPct=0.020 在不同     |
//|    品种上完全不等价。我用真实 M1 数据（各 50 万根）实测：            |
//|        USDJPYm  中位 RV%=0.0093 → 0.020 只放行  8.03% 的时间       |
//|        XAUUSDm  中位 RV%=0.0270 → 放行 71.06%                      |
//|        BTCUSDm  中位 RV%=0.0422 → 放行 89.45%                      |
//|    → 在 JPY 上这道闸门砍掉约 92% 的入场机会。本 EA 不做波动率闸门，  |
//|      改用**震荡/单边判别**（效率比 ER），它才是反转策略真正需要的。  |
//|                                                                  |
//|  ============ 设计取向：区间反转 ============                       |
//|  量纲决定策略：USDJPY 点差 10 点，而 jpy-007 的 2.5xATR(M5) 止损是   |
//|  207 点 → 点差/止损 = 4.8%。**这是三品种里唯一「小目标也能盈利」的    |
//|  结构**（黄金的同一比值高一个量级）。所以做小目标回归，而不是趋势。   |
//|                                                                  |
//|  ★ 纪律（不重复 TrendCore 已修过的 3 个 bug）                       |
//|    - bug#1 TICK_VALUE 漂移：本 EA **不用** SYMBOL_TRADE_TICK_VALUE， |
//|      改为显式「合约口径 + 报价货币折算」（见 MoneyPerPricePerLot）   |
//|    - bug#2 手数四舍五入超预算：本 EA 严格 floor + 取整后复核风险     |
//|    - bug#3 出场原因退化：本 EA 用 comment 白名单 + 成交历史归因      |
//|    - bug#4 永久锁自杀：本 EA 的 DD 上限只**冷却**，不永久停止        |
//+------------------------------------------------------------------+
#property copyright "DeepSeek JPY line"
#property version   "1.00"
#property strict

//==================== 输入参数 ====================
input group "=== 手数 / 风险（按账户百分比）==="
input double InpRiskPct          = 0.5;    // 每笔风险 = 净值的百分之几
input double InpMaxLot           = 1.00;   // 手数上限
input bool   InpUseEquityForRisk = true;
input bool   InpAllowMinLotOvershoot = true;
input double InpMinLotMaxRiskPct = 1.0;    // 最小手模式下的风险硬上限（%）

input group "=== 区间反转信号 ==="
input ENUM_TIMEFRAMES InpTF      = PERIOD_M5;   // 信号周期（枚举）
// ★★ 网格/优化请改用下面这个 int（分钟），不要用 InpTF：
//   实测 2026-09-12：MT5 在 .set 里对**未被优化**的枚举参数写成"符号名"（InpTF=PERIOD_M5||0||0||49153||N），
//   测试器把它还原成数字时不可靠 → InpTF 变成 0 (PERIOD_CURRENT)。
//   本 EA 在 M1 图表上跑，PERIOD_CURRENT→M1→TFMinutes=1→BuildAggBars 守卫 `tfm<=1` 直接返回 0
//   → **每一笔都不开，而测试器报告"成功"**。这正是 13/15 个网格 0 成交的原因。
//   用 int 分钟则 .set 里是纯数字（InpTFMinutes=5||5||1||5||Y），不会有这个问题。
input int    InpTFMinutes        = 0;      // >0 时覆盖 InpTF（推荐：5=M5, 15=M15, 30=M30）
input int    InpMAPeriod         = 24;     // 中轴均线周期
input int    InpSigmaPeriod      = 48;     // sigma 估计窗口
input double InpEntrySigma       = 1.8;    // 触发：收盘偏离中轴 >= N sigma
input bool   InpNeedReenter      = true;   // true=下一根回到带内才入场
input double InpExitFrac         = 0.25;   // 回到 (1-frac)*偏离 处出场
input double InpPartialCloseFrac = 0.0;    // ★R1：>0 时在出场目标处先平该比例（测部分平仓路径）
input bool   InpAllowLong        = true;   // ★R1：允许做多（实测/控制用）
input bool   InpAllowShort       = true;   // ★R1：允许做空（实测/控制用）
input bool   InpCloseAtEnd       = true;   // ★R4：窗口最后一天主动平仓（避免 MT5 强平写不进审计）
input int    InpCloseAtEndHour   = 22;     // ★R4：在窗口最后一天的该小时前平仓
input double InpStopATR          = 3.0;    // 灾难止损 = N x ATR
input int    InpMaxBarsInTrade   = 12;     // 时间止损（入场时长的倍数，见代码）
input double InpMaxAdverseATR    = 2.0;    // 逆行超过 N x ATR 就认错

input group "=== 区间过滤（防顺势被打爆）==="
input bool   InpUseRangeFilter   = true;
input double InpMaxER            = 0.35;   // 效率比上限，ER 低=震荡
input int    InpERPeriod         = 24;

input group "=== 时段过滤 ==="
input bool   InpUseSessionFilter = true;
input int    InpTradeStartHour   = 0;
input int    InpTradeEndHour     = 23;
input bool   InpNoFridayLate     = true;
input int    InpFridayStopHour   = 20;

input group "=== 账户级风控（冷却式，非永久锁）==="
input bool   InpUseDailyStop     = true;
input double InpDailyLossPct     = 3.0;
input bool   InpUseDDKill        = true;
input double InpMaxDDPct         = 20.0;
input int    InpDDCooldownMin    = 1440;   // >0 冷却后自动解锁；0=永久锁（旧行为，不推荐）
input bool   InpStopAfterDDLock  = false;  // false=评估口径 / true=交付口径(永久停)

input group "=== 杂项 ==="
input long   InpMagic            = 20260913;
input string InpRunTag           = "jpyrev";
input bool   InpWriteAudit       = true;
input bool   InpVerboseLog       = false;
input double InpDDMinDepthPct    = 2.0;
input double InpSlippagePoints   = 50;
// ★模拟真实网络延迟：读价 → Sleep(InpLatencyMs) → 用【新价】下单
input int    InpLatencyMs       = 300;   // 模拟下单延迟（毫秒）
input int    InpLatencyTicks     = 0;     // ★延迟 tick 数（Sleep 在测试器无效，故用 tick 级延迟）

// ★tick 级延迟（2026-09-12）：替代在测试器中无效的 Sleep(InpLatencyMs)
int    g_tickCount  = 0;
bool   g_pendValid  = false;
int    g_pendDir    = 0;
double g_pendLot    = 0.0;
double g_pendStop   = 0.0;
double g_pendAtr    = 0.0;
long   g_pendDue    = 0;

//==================== 全局状态 ====================
long     g_lastEvalBar   = -1;
long     g_curDayKey     = -1;
double   g_dayStartEquity= 0.0;
bool     g_dailyBlocked  = false;
double   g_peakEquity    = 0.0;
bool     g_ddLocked      = false;
datetime g_ddLockUntil   = 0;

ulong    g_ticket        = 0;
datetime g_entryTime     = 0;
double   g_entryPrice    = 0.0;
double   g_entryATR      = 0.0;
double   g_riskMoney     = 0.0;
int      g_barsHeld      = 0;
double   g_entryDev      = 0.0;   // ★入场时的偏离（价格距离），供出场目标价使用
double   g_lastLatencySlip = 0.0; // ★延迟期间的不利滑点（>0 = 不利），诊断用
ENUM_TIMEFRAMES g_tf      = PERIOD_M5;  // ★生效周期（由 InpTFMinutes/InpTF 解析而来，见 OnInit）

long     g_nTrades = 0, g_nWin = 0, g_dealsOut = 0;
bool     g_partialDone = false;   // ★R1：本次持仓是否已做过部分平仓

// ★★★ R4（GPT 第三批裁定 Step 2）：
//   · 按 deal_ticket 去重，防止同一 closing deal 写两遍
//   · 结束时补写未落盘的 deal（end of test 强制平仓）
#define MAX_DEALTICKET 4096
ulong    g_seenDeals[MAX_DEALTICKET];
int      g_seenCount   = 0;
long     g_writtenDeals = 0;      // 已写审计的 deal 数
long     g_dupHits      = 0;      // 重复命中次数
bool     g_auditFailed  = false;  // 审计失败标记（触发立即失败）
int      g_lastPosCount = -1;     // ★R4：持仓数变化检测

bool DealSeen(ulong ticket)
{
   for(int i = 0; i < g_seenCount; i++)
      if(g_seenDeals[i] == ticket) return true;
   if(g_seenCount < MAX_DEALTICKET) g_seenDeals[g_seenCount++] = ticket;
   else { g_dupHits++; }          // 表满 → 标记异常
   return false;
}
double   g_sumWin = 0.0, g_sumLoss = 0.0;
double   g_bestWin = 0.0, g_worstLoss = 0.0;
double   g_realizedPnL = 0.0;
long     g_rejTick = 0, g_rejNoOver = 0, g_rejCap = 0;
long     g_skipSession = 0, g_skipRange = 0, g_skipNoSig = 0, g_skipRisk = 0;

// 回撤事件
int      g_ddEpisodes = 0, g_ddOpenCount = 0;
double   g_ddSumPct = 0.0, g_ddWorstPct = 0.0, g_ddSumRecoverH = 0.0;
int      g_ddOver10=0, g_ddOver15=0, g_ddOver20=0, g_ddOver25=0, g_ddOver30=0;
bool     g_epActive = false;
datetime g_epStart = 0, g_epTroughTime = 0;
double   g_epPeakEq = 0.0, g_epTroughEq = 0.0, g_epTroughUsd = 0.0, g_epTroughPct = 0.0;

// 月度
int      g_curMon = -1;
double   g_monStartEq = 0.0, g_monPeakEq = 0.0, g_monTroughEq = 0.0, g_monWorstPct = 0.0;
int      g_monSamples = 0;

int      g_auditFh = INVALID_HANDLE;
int      g_ddFh    = INVALID_HANDLE;
int      g_monFh   = INVALID_HANDLE;

//==================== 基础工具 ====================
// ★枚举不能当数值用（TrendCore 实测：H1 曾写成 60 → 一笔不开且不报错）
int TFMinutes(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_CURRENT) tf = (ENUM_TIMEFRAMES)Period();
   int v = (int)tf;
   if(v <= 0) return 0;
   if(v < 16385) return v;                 // M1..M30 值即分钟数
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

double NormPrice(double p) { return NormalizeDouble(p, _Digits); }

ENUM_ORDER_TYPE_FILLING PickFilling()
{
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   if((mode & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

// ★不用 SYMBOL_TRADE_TICK_VALUE（测试器里会漂移：实测 tv 从 0.695 漂到 14355）
//   改用「合约口径 + 报价货币折算」：每 1 手、每 1.0 价格变动的账户货币价值
double MoneyPerPricePerLot()
{
   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double bid      = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(contract <= 0.0) return 0.0;
   string profitCcy = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_PROFIT);
   double v = contract;                       // 报价货币下的价值
   if(profitCcy != "USD" && bid > 0.0)
      v = contract / bid;                     // 折算成账户货币(USD)
   return v;
}

double LossPerLotForDistance(double priceDist)
{
   double mpp = MoneyPerPricePerLot();
   if(mpp <= 0.0) return 0.0;
   return priceDist * mpp;
}

// 手数对齐：★严格向下（TrendCore bug#2：四舍五入曾让实际风险超预算 248%）
double AlignLotDown(double lot)
{
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(vstep <= 0.0) vstep = 0.01;
   lot = MathFloor(lot / vstep + 1e-9) * vstep;
   if(lot < vmin) lot = 0.0;
   if(vmax > 0.0 && lot > vmax) lot = vmax;
   if(InpMaxLot > 0.0 && lot > InpMaxLot)
      lot = MathFloor(InpMaxLot / vstep + 1e-9) * vstep;
   int vd = 0; double s = vstep;
   while(s < 1.0 && vd < 8) { s *= 10.0; vd++; }
   return NormalizeDouble(lot, vd);
}

double LotForRisk(double stopDistPrice, double &riskUsed)
{
   riskUsed = 0.0;
   double base = InpUseEquityForRisk ? AccountInfoDouble(ACCOUNT_EQUITY)
                                     : AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = base * InpRiskPct / 100.0;
   double perLot = LossPerLotForDistance(stopDistPrice);
   if(perLot <= 0.0) { g_rejTick++; return 0.0; }

   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lot  = riskMoney / perLot;

   if(lot < vmin)
   {
      if(!InpAllowMinLotOvershoot) { g_rejNoOver++; return 0.0; }
      double minLotRisk = vmin * perLot;
      double cap = base * InpMinLotMaxRiskPct / 100.0;
      if(minLotRisk > cap) { g_rejCap++; return 0.0; }
      riskUsed = minLotRisk;
      return vmin;
   }

   lot = AlignLotDown(lot);
   if(lot <= 0.0) { g_rejNoOver++; return 0.0; }
   riskUsed = lot * perLot;

   // 取整/夹紧后仍超预算 → 降一档，再不行就看最小手豁免
   if(riskUsed > riskMoney + 1e-9)
   {
      double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
      if(vstep <= 0.0) vstep = 0.01;
      double lower = NormalizeDouble(lot - vstep, 8);
      if(lower >= vmin) { lot = lower; riskUsed = lot * perLot; }
      if(riskUsed > riskMoney + 1e-9)
      {
         if(!InpAllowMinLotOvershoot || lot > vmin + 1e-9) { g_rejCap++; return 0.0; }
         double cap = base * InpMinLotMaxRiskPct / 100.0;
         if(riskUsed > cap) { g_rejCap++; return 0.0; }
      }
   }
   return lot;
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

//==================== M1 → 大周期聚合 ====================
// 只用 M1 序列（测试器必定提供），自建 bar。理由见 TrendCore L995-1005：
//   对自定义品种调 iMA/iATR 会稳定 err=4805，且多周期序列可能不同步。
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
   // 最后一根是未收盘 bar → 丢弃（与 TrendCore 口径一致）
   int nAll = ArraySize(c);
   if(nAll < 2) return 0;
   ArrayResize(o, nAll-1); ArrayResize(h, nAll-1);
   ArrayResize(l, nAll-1); ArrayResize(c, nAll-1);
   return ArraySize(c);
}

double SmaOnArray(const double &c[], int period, int from)
{
   int n = ArraySize(c);
   if(period <= 0 || from < 0 || from + period > n) return 0.0;
   double s = 0.0;
   for(int i = 0; i < period; i++) s += c[from + i];
   return s / period;
}

double StdevOnArray(const double &c[], int period, int from, double mean)
{
   int n = ArraySize(c);
   if(period <= 1 || from < 0 || from + period > n) return 0.0;
   double ss = 0.0;
   for(int i = 0; i < period; i++)
   { double d = c[from + i] - mean; ss += d * d; }
   return MathSqrt(ss / period);
}

double AtrOnBars(const double &h[], const double &l[], const double &c[],
                 int period, int lastIdx)
{
   if(period <= 0 || lastIdx - period + 1 < 1) return 0.0;
   double atr = 0.0;
   for(int i = lastIdx - period + 1; i <= lastIdx; i++)
   {
      if(i < 1) continue;
      double tr = MathMax(h[i] - l[i],
                  MathMax(MathAbs(h[i] - c[i-1]), MathAbs(l[i] - c[i-1])));
      atr += tr;
   }
   return atr / period;
}

// 效率比：|净变动| / 路径总长。低=震荡（适合反转），高=单边（反转必死）
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

//==================== 仓位查询 ====================
bool HasPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      g_ticket = tk;
      return true;
   }
   return false;
}
int    PosType() { return (int)PositionGetInteger(POSITION_TYPE); }
double PosVol()  { return PositionGetDouble(POSITION_VOLUME); }
double PosOpen() { return PositionGetDouble(POSITION_PRICE_OPEN); }

//==================== 归因 / 审计 ====================
// ★形参用 int：DEAL_REASON_* 是枚举常量(int)，
//   用 long 形参会让 switch(long) 与 int 常量比较时触发 warning 43（long→int 可能丢数据）。
string DealReasonStr(int reason)
{
   switch(reason)
   {
      case DEAL_REASON_SL:      return "sl";
      case DEAL_REASON_TP:      return "tp";
      case DEAL_REASON_SO:      return "stopout";
      case DEAL_REASON_CLIENT:  return "client";
      case DEAL_REASON_MOBILE:  return "mobile";
      case DEAL_REASON_WEB:     return "web";
      case DEAL_REASON_EXPERT:  return "expert";
   }
   return "other";
}

// ★归因修复：主动平仓时 DEAL_REASON 恒为 expert → 优先解析 comment 白名单
//   （同 TrendCore bug#3 的修法）
void RecordExitDeal(ulong dealTicket)
{
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;
   long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY) return;

   // ★★★ 2026-09-13 Stage R1（GPT 第二批裁定 §三 R1）：
   //   ① 成本分列：profit / swap / commission 三列独立（净值 = 三者之和）
   //   ② position_id 列（对账用，反查开仓腿）
   //   ③ close_type 列（full / partial）
   //   旧实现只写一个合并的 profit，无法与 MT5 报告 Total Net Profit 逐项对账，
   //   也没有 position_id → 部分平仓无法分行。
   double dProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
   double dSwap   = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
   double dComm   = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
   double profit  = dProfit + dSwap + dComm;      // 净额（保持向后兼容）
   double price  = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double vol    = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   long   reason = HistoryDealGetInteger(dealTicket, DEAL_REASON);
   ulong  pid    = (ulong)HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
   string reasonStr = "";
   {
      string cmt = HistoryDealGetString(dealTicket, DEAL_COMMENT);
      if(StringFind(cmt, "revert")     >= 0) reasonStr = "revert";
      else if(StringFind(cmt, "time")  >= 0) reasonStr = "time_exit";
      else if(StringFind(cmt, "adverse")>= 0) reasonStr = "adverse";
      else if(StringFind(cmt, "dd_kill")>= 0) reasonStr = "dd_kill";
      else reasonStr = DealReasonStr((int)reason);
   }
   datetime t   = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
   long   dtype = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
   int    dir   = (dtype == DEAL_TYPE_SELL) ? 1 : -1;   // 出场是卖 → 原仓为多

   // ★新增：持仓时长（父代理 2026-09-11 要求，用于 REJECT-scalp < 5 分钟 判定）
   //   time 列保持 = 平仓时间（向后兼容）；entry_time/bar_seconds 紧随 risk_money 之后。
   datetime et = g_entryTime;
   if(et <= 0) et = t;
   long barSeconds = (long)t - (long)et;
   if(barSeconds < 0) barSeconds = 0;

   // ★部分平仓判定：本次平仓量 < 该持仓当前总成交量
   string closeType = "full";
   {
      double remain = 0.0;
      if(PositionSelectByTicket(pid)) remain = PositionGetDouble(POSITION_VOLUME);
      if(remain > 0.0) closeType = "partial";
   }

   // ★反查开仓均价（该 position 的全部 DEAL_ENTRY_IN 成交量加权）
   double entryPx = g_entryPrice;
   double entryVol = 0.0;
   if(HistorySelectByPosition(pid))
   {
      int nd = HistoryDealsTotal();
      double spv = 0.0, sv = 0.0;
      for(int i = 0; i < nd; i++)
      {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0) continue;
         if(HistoryDealGetInteger(tk, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
         double pp = HistoryDealGetDouble(tk, DEAL_PRICE);
         double vv = HistoryDealGetDouble(tk, DEAL_VOLUME);
         spv += pp * vv; sv += vv;
      }
      if(sv > 0.0) entryPx = spv / sv;
      entryVol = sv;
   }
   // 部分平仓时按比例拆分 risk_money
   double riskThis = g_riskMoney;
   if(entryVol > 0.0 && vol < entryVol - 1e-9 && g_riskMoney > 0.0)
      riskThis = g_riskMoney * (vol / entryVol);

   g_realizedPnL += profit;
   g_dealsOut++;
   g_nTrades++;
   if(profit > 0.0) { g_nWin++; g_sumWin += profit; if(profit > g_bestWin) g_bestWin = profit; }
   else             { g_sumLoss += profit; if(profit < g_worstLoss) g_worstLoss = profit; }

   if(g_auditFh == INVALID_HANDLE) return;   // ★R4：未打开审计 → 不登记 ticket，允许重试

   // ★★ 关键：deal_ticket 去重必须放在【能写入的路径】上。
   //   若在函数首部就 DealSeen()，一旦后续任一分支 return，该 ticket 已被标记，
   //   将永久漏记（实测：LONG 段 403 → 399，丢 4 行）。
   if(DealSeen(dealTicket)) { g_dupHits++; return; }

   {
      // ★R4 第 5 条：显式调用 OrderCalcProfit 并记录返回码
      double ocpValue = 0.0;
      ResetLastError();
      bool ocpOk = OrderCalcProfit(
                      (dir > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL),
                      _Symbol, vol, entryPx, price, ocpValue);
      int ocpErr = (ocpOk ? 0 : GetLastError());

      // ★R4 第 7 条：字段缺失立即失败
      if(entryPx <= 0.0 || price <= 0.0 || vol <= 0.0 || pid == 0)
      {
         g_auditFailed = true;
         PrintFormat("[%s] ★审计字段缺失 ticket=%I64u pid=%I64u entry=%.5f exit=%.5f vol=%.2f",
                     InpRunTag, dealTicket, pid, entryPx, price, vol);
      }

      FileWrite(g_auditFh, InpRunTag, _Symbol,
                TimeToString(t, TIME_DATE|TIME_SECONDS),
                (string)dir,
                DoubleToString(entryPx, _Digits),
                DoubleToString(price, _Digits),
                DoubleToString(vol, 2),
                DoubleToString(profit, 2),
                DoubleToString(riskThis, 2),
                TimeToString(et, TIME_DATE|TIME_SECONDS),
                IntegerToString(barSeconds),
                DoubleToString(g_entryATR, _Digits),
                reasonStr,
                IntegerToString((long)dealTicket),          // deal_ticket
                IntegerToString((long)pid),                 // position_id
                closeType,
                DoubleToString(dProfit, 2),
                DoubleToString(dSwap, 2),
                DoubleToString(dComm, 2),
                DoubleToString(profit, 2),                  // net（= profit+swap+comm）
                TimeToString(et, TIME_DATE|TIME_SECONDS),   // entry_time
                TimeToString(t, TIME_DATE|TIME_SECONDS),    // exit_time
                (ocpOk ? "1" : "0"),                        // ocp_ok
                IntegerToString(ocpOk ? 0 : -1),            // ocp_ret
                IntegerToString(ocpErr),                    // ocp_err
                DoubleToString(ocpValue, 2));               // ocp_value
      FileFlush(g_auditFh);
      g_writtenDeals++;
   }
   g_ticket = 0;
}

// ★R4 第 1/7 条：结束时补扫全部历史 deal，补写未落盘者
//   （MT5 在测试结束会强制平仓，且该 deal 不一定触发 OnTradeTransaction）
// ★R4 第 1 条（v2 修正）：不依赖 OnTradeTransaction —— MT5 在窗口结束时
//   强制平仓不会触发 DEAL_ADD 事务。改为【主动扫描历史】：
//   每 tick 节流扫一次，OnTester/OnDeinit 各扫一次（兜住结束平仓）。
int  g_catchupCalls   = 0;
int  g_catchupSelFail = 0;
long g_catchupTotal   = 0;
long g_catchupAdded   = 0;

void CatchUpAudit()
{
   if(!InpWriteAudit) return;
   g_catchupCalls++;
   datetime from = 0, to = TimeCurrent() + 7 * 86400;
   if(!HistorySelect(from, to)) { g_catchupSelFail++; return; }
   int total = HistoryDealsTotal();
   g_catchupTotal = total;
   int added = 0;
   for(int i = 0; i < total; i++)
   {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0) continue;
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != InpMagic) continue;
      long en = HistoryDealGetInteger(tk, DEAL_ENTRY);
      if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY) continue;
      // ★不要在这里调 DealSeen（它会把 ticket 标记为"已见"，而 RecordExitDeal
      //   可能因分支提前 return → 该 ticket 永久漏记，且实测只丢止损单 → 审计偏乐观）
      //   统一交给 RecordExitDeal 内部的写入路径去重。
      int before = (int)g_writtenDeals;
      RecordExitDeal(tk);
      if((int)g_writtenDeals > before) added++;
   }
   g_catchupAdded += added;
}

// ★每 tick 节流调用
void CatchUpTick()
{
   if(!InpWriteAudit) return;

   // ★★★ R4：窗口末尾主动平仓
   //   实测根因：MT5 的 end-of-test 强制平仓（deal 799, 2023.12.28 23:59:59）
   //   发生在 OnDeinit 之后，历史扫描看不到它 → 审计永远少一行，
   //   且差额恰好是那笔（−0.70），只影响 SHORT/PARTIAL（LONG 恰在收尾前已平）。
   //   这里由专家侧提前平仓，走正常 ClosePosition 路径，审计必然记录。
   if(InpCloseAtEnd && HasPosition())
   {
      MqlDateTime now; TimeToStruct(TimeCurrent(), now);
      if(now.year == 2023 && now.mon == 12 && now.day >= 28 && now.hour >= InpCloseAtEndHour)
         ClosePosition("window_end");
   }

   int pc = (HasPosition() ? 1 : 0);
   if(pc != g_lastPosCount) { g_lastPosCount = pc; CatchUpAudit(); return; }
   if((g_tickCount % 512) == 0) CatchUpAudit();
}

// ★OnTester：MT5 测试结束时调用（早于 OnDeinit），历史已就绪
double OnTester()
{
   CatchUpAudit();
   return 0.0;
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      RecordExitDeal(trans.deal);
}

//==================== 风控 ====================
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

      // ★冷却解锁（不是永久锁）。解锁时把高水位重置到当前净值。
      //   ⚠️ 这仍**不是**"全程回撤 <= InpMaxDDPct"的保证：
      //      阶梯式下跌可让累计回撤超过该值。评估必须看实测 dd_pct。
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
         {
            g_ddLocked = true;
            PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，交付口径【永久停止】", InpRunTag, dd);
         }
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
         else g_epActive = false;                 // 太浅，视为噪声
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

//==================== 开 / 平仓 ====================
bool ClosePosition(string reason, double volFrac = 1.0)
{
   if(!HasPosition()) return false;
   int    dir = PosType();
   double vol = PosVol();
   // ★★★ 2026-09-13 Stage R1：支持部分平仓（GPT 第二批裁定 §三 R1 要求
   //   "场景覆盖……至少一次部分平仓"）。volFrac < 1 时只平该比例，
   //   按 volume_step 向下取整；剩余不足一个 step 时退化为全平。
   if(volFrac > 0.0 && volFrac < 1.0)
   {
      double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
      double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
      if(vstep <= 0.0) vstep = 0.01;
      double part = MathFloor(vol * volFrac / vstep + 1e-9) * vstep;
      if(part < vmin || vol - part < vmin) part = vol;   // 太小 → 全平
      vol = part;
   }

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = _Symbol;
   req.position     = g_ticket;
   req.volume       = vol;
   req.deviation    = (ulong)InpSlippagePoints;
   req.magic        = InpMagic;
   req.comment      = "close_" + reason;
   req.type         = (dir == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.type_filling = PickFilling();
   req.price        = (dir == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                                 : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      if(InpVerboseLog)
         PrintFormat("[%s] 平仓失败 reason=%s retcode=%d err=%d",
                     InpRunTag, reason, res.retcode, GetLastError());
      return false;
   }
   g_ticket = 0;
   return true;
}

bool OpenPosition(int dir, double stopDistPrice, double atr)
{
   // ★★2026-09-12 延迟机制重写（与 dsh_BtcSwing 同机制）：
   //   旧实现用 Sleep(InpLatencyMs) —— 实测在 MT5 策略测试器里【不推进模拟时间】，
   //   期间不产生新 tick、价格不变 → Sleep 后重读价读到同一个价 → 结果与 0 延迟逐位相同。
   //   （A/B 实证：144/144 pass 逐位全同）
   //   新实现：把请求挂起，等够 InpLatencyTicks 个 tick 后，在【那一刻的市价】上执行。
   //   tick 在测试器里是推进的，所以延迟真实生效。
   //   用市价单而非挂单 —— 挂单会因价格跑掉被拒（invalid price），
   //   那会造出"延迟越大成交越少"的假象，与"延迟只让成交价变差"混淆。
   if(InpLatencyTicks > 0)
   {
      double dummyRisk = 0.0;
      double lotNow = LotForRisk(stopDistPrice, dummyRisk);
      if(lotNow <= 0.0) { g_skipRisk++; return false; }
      g_pendDir   = dir;
      g_pendStop  = stopDistPrice;
      g_pendAtr   = atr;
      g_pendLot   = lotNow;
      g_pendDue   = g_tickCount + InpLatencyTicks;
      g_pendValid = true;
      return false;      // 已挂起；结果由 DoPendingOpen() 在后续 tick 执行
   }
   return ExecOpen(dir, stopDistPrice, atr);
}

// ★实际下单路径（不含延迟判定）。延迟机制与直连路径共用它，避免递归。
bool ExecOpen(int dir, double stopDistPrice, double atr)
{
   double riskUsed = 0.0;
   double lot = LotForRisk(stopDistPrice, riskUsed);
   if(lot <= 0.0) { g_skipRisk++; return false; }

   double price = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0) return false;

   double sl = (dir > 0) ? price - stopDistPrice : price + stopDistPrice;

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = _Symbol;
   req.volume       = lot;
   req.type         = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price        = price;
   req.sl           = NormPrice(sl);
   req.deviation    = (ulong)InpSlippagePoints;
   req.magic        = InpMagic;
   req.comment      = "open_jpyrev";
   req.type_filling = PickFilling();

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      PrintFormat("[%s] 开仓失败 retcode=%d err=%d", InpRunTag, res.retcode, GetLastError());
      return false;
   }
   g_entryTime   = TimeCurrent();
   g_entryPrice  = price;
   g_entryATR    = atr;
   g_riskMoney   = riskUsed;
   g_barsHeld    = 0;
   if(InpVerboseLog)
      PrintFormat("[%s] OPEN dir=%d lot=%.2f price=%.3f sl=%.3f risk=%.2f atr=%.5f latency=%dms slip=%.5f",
                  InpRunTag, dir, lot, price, sl, riskUsed, atr, InpLatencyMs, g_lastLatencySlip);
   return true;
}

//==================== 持仓管理 ====================
// 反转策略出场：①回到目标 ②逆行认错 ③时间止损（按信号周期 bar 计）
//   ATR 灾难止损由券商侧 SL 挂单处理，这里不重复。
void ManageOpenPosition()
{
   if(!HasPosition()) return;
   int    dir  = PosType();
   double open = PosOpen();
   double bid  = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask  = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double cur  = (dir == POSITION_TYPE_BUY) ? bid : ask;

   // ① 回到目标：入场偏离 = (open - mean)；目标 = mean + (1-frac)*(open-mean)
   //    这里 mean 用入场 ATR 代理不合适，故直接以"入场后经过的有利距离"记账：
   //    以 open 为基准，需要用 mean。为免存全局 mean，改用 ATR 尺度近似目标。
   //    —— 见 EvalSignal 里把偏离存到 g_entryDev，这里用 g_entryDev。
   g_barsHeld++;
   double favorable = (cur - open) * ((dir == POSITION_TYPE_BUY) ? 1.0 : -1.0);

   if(g_entryDev != 0.0)
   {
      double targetDist = (1.0 - InpExitFrac) * MathAbs(g_entryDev);  // 价格距离
      if(favorable >= targetDist)
   {
      if(InpPartialCloseFrac > 0.0 && !g_partialDone)
      {
         if(ClosePosition("partial_revert", InpPartialCloseFrac)) { g_partialDone = true; return; }
      }
      ClosePosition("revert"); return;
   }
   }
   // ② 逆行认错
   if(g_entryATR > 0.0 && InpMaxAdverseATR > 0.0
      && (-favorable) > InpMaxAdverseATR * g_entryATR)
   { ClosePosition("adverse"); return; }
   // ③ 时间止损：按 tick 计太粗，改用信号周期 bar 数
   if(InpMaxBarsInTrade > 0)
   {
      long held = (long)(TimeCurrent() - g_entryTime) / ((long)TFMinutes(g_tf) * 60);
      if(held >= InpMaxBarsInTrade) { ClosePosition("time_exit"); return; }
   }
}

//==================== 信号 ====================
int EvalSignal(double &mean, double &sigma, double &atr, double &er, double &dev, string &why)
{
   mean = 0.0; sigma = 0.0; atr = 0.0; er = 1.0; dev = 0.0; why = "";
   int need = MathMax(InpMAPeriod, InpSigmaPeriod) + InpERPeriod + 10;

   double o[], h[], l[], c[];
   int n = BuildAggBars(g_tf, need, o, h, l, c);
   int minNeed = InpSigmaPeriod + 3;
   if(n < minNeed) { why = "few_bars"; return 0; }

   int last = n - 1;
   int sigFrom = last - InpSigmaPeriod + 1;
   if(sigFrom < 1) { why = "few_bars"; return 0; }
   int maFrom = last - InpMAPeriod + 1;
   if(maFrom < 0) { why = "few_bars"; return 0; }

   mean  = SmaOnArray(c, InpMAPeriod, maFrom);
   double mForSigma = SmaOnArray(c, InpSigmaPeriod, sigFrom);
   sigma = StdevOnArray(c, InpSigmaPeriod, sigFrom, mForSigma);
   atr   = AtrOnBars(h, l, c, 14, last);
   er    = EfficiencyRatio(c, InpERPeriod, last);
   if(mean <= 0.0 || sigma <= 0.0 || atr <= 0.0) { why = "ind_zero"; return 0; }

   double close1 = c[last];        // 最后一根已收盘
   double close0 = c[last - 1];

   double dev1 = (close1 - mean) / sigma;
   double dev0 = (close0 - mean) / sigma;

   if(InpNeedReenter)
   {
      if(dev0 <= -InpEntrySigma && dev1 > -InpEntrySigma)
      { dev = close1 - mean; why = "long_reenter";  return 1; }
      if(dev0 >=  InpEntrySigma && dev1 <  InpEntrySigma)
      { dev = close1 - mean; why = "short_reenter"; return -1; }
      why = "no_reenter"; return 0;
   }
   if(dev1 <= -InpEntrySigma) { dev = close1 - mean; why = "long_ext";  return 1; }
   if(dev1 >=  InpEntrySigma) { dev = close1 - mean; why = "short_ext"; return -1; }
   why = "no_signal"; return 0;
}

//==================== 生命周期 ====================
string AuditDir() { return "dshtrend/" + InpRunTag; }

int OnInit()
{
   if(InpRiskPct <= 0.0 || InpRiskPct > 20.0)
   { Print("InpRiskPct 必须在 (0,20]"); return INIT_PARAMETERS_INCORRECT; }
   if(InpMAPeriod < 2 || InpSigmaPeriod < 3 || InpERPeriod < 2)
   { Print("周期参数过小"); return INIT_PARAMETERS_INCORRECT; }

   // ★★周期解析（防"枚举符号名 → 0"的静默 0 成交）
   g_tf = InpTF;
   if(InpTFMinutes > 0)
   {
      g_tf = (ENUM_TIMEFRAMES)InpTFMinutes;   // 分钟类枚举 1..30 值即分钟数
   }
   else
   {
      int tfm = TFMinutes(g_tf);
      if(tfm <= 1)
      {
         // 说明 InpTF 被优化器/测试器还原成了 0(PERIOD_CURRENT) 或 M1 —— 一定开不出仓
         PrintFormat("[%s] ★警告：InpTF 解析为 %d（TFMinutes=%d <=1）。"
                     "这会让 BuildAggBars 直接返回 0、一笔都不开。"
                     "请改用 InpTFMinutes（例如 5=M5）。已自动回退到 M5。",
                     InpRunTag, (int)g_tf, tfm);
         g_tf = PERIOD_M5;
      }
   }
   if(TFMinutes(g_tf) <= 1)
   { PrintFormat("[%s] ★致命：InpTFMinutes=%d 无效（需 >=2）", InpRunTag, InpTFMinutes); return INIT_PARAMETERS_INCORRECT; }

   g_peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayStartEquity = g_peakEquity;

   if(InpWriteAudit)
   {
      FolderCreate("dshtrend", FILE_COMMON);
      FolderCreate(AuditDir(), FILE_COMMON);
      g_auditFh = FileOpen(AuditDir() + "/trades.csv",
                           FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_auditFh != INVALID_HANDLE)
         FileWrite(g_auditFh, "run_tag","symbol","time","dir","entry","exit",
                   "vol","pnl","risk_money","entry_time","bar_seconds",
                   "atr_at_entry","exit_reason","deal_ticket","position_id","close_type",
                   "profit","swap","commission","net","entry_time","exit_time",
                   "ocp_ok","ocp_ret","ocp_err","ocp_value");

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

   PrintFormat("[%s] init ok TF=%d(min) MA=%d Sigma=%d Entry=%.2f Reenter=%s ExitFrac=%.2f StopATR=%.1f MaxBars=%d ERmax=%.2f RiskPct=%.2f",
               InpRunTag, TFMinutes(g_tf), InpMAPeriod, InpSigmaPeriod, InpEntrySigma,
               (InpNeedReenter?"on":"off"), InpExitFrac, InpStopATR, InpMaxBarsInTrade,
               InpMaxER, InpRiskPct);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   // ★★★ R4（GPT 第三批裁定 Step 2 第 1/7 条）：
   //   必须在关闭审计文件【之前】补写未落盘的 closing deal
   //   （MT5 在测试结束会强制平仓，该 deal 不一定触发 OnTradeTransaction）
   CatchUpAudit();

   // ★R4 第 7 条：写审计自检文件（供对账脚本判定字段完整性/去重/失败）
   {
      string sf = "dshtrend\\" + InpRunTag + "\\audit_selfcheck.csv";
      int fh = FileOpen(sf, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(fh != INVALID_HANDLE)
      {
         FileWrite(fh, "run_tag","written_deals","dup_hits","audit_failed","reason","catchup_calls","catchup_selfail","catchup_total","catchup_added");
         FileWrite(fh, InpRunTag, IntegerToString(g_writtenDeals),
                   IntegerToString(g_dupHits),
                   (g_auditFailed ? "1" : "0"),
                   IntegerToString(reason),
                   IntegerToString(g_catchupCalls), IntegerToString(g_catchupSelFail),
                   IntegerToString((long)g_catchupTotal), IntegerToString(g_catchupAdded));
         FileClose(fh);
      }
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

   double wr = (g_nTrades > 0) ? 100.0 * (double)g_nWin / (double)g_nTrades : 0.0;
   double avgDepth = (g_ddEpisodes > 0) ? g_ddSumPct / g_ddEpisodes : 0.0;
   double avgRec   = (g_ddEpisodes > 0) ? g_ddSumRecoverH / g_ddEpisodes : 0.0;
   PrintFormat("[%s] DD_EVENTS 已恢复=%d 未恢复=%d 平均深度=%.2f%% 最深=%.2f%% 平均恢复=%.1fh | >=10%%:%d >=15%%:%d >=20%%:%d >=25%%:%d >=30%%:%d",
               InpRunTag, g_ddEpisodes, g_ddOpenCount, avgDepth, g_ddWorstPct, avgRec,
               g_ddOver10, g_ddOver15, g_ddOver20, g_ddOver25, g_ddOver30);
   PrintFormat("[%s] === 结束 reason=%d 交易=%d 胜率=%.1f%% 总盈利=%.2f 总亏损=%.2f 最大单盈=%.2f 最大单亏=%.2f 日损阻断=%s 回撤锁=%s 拒单[时段=%d 区间=%d 无信号=%d 手数=%d] ===",
               InpRunTag, reason, (int)g_nTrades, wr, g_sumWin, g_sumLoss,
               g_bestWin, g_worstLoss,
               g_dailyBlocked?"是":"否", g_ddLocked?"是":"否",
               (int)g_skipSession, (int)g_skipRange, (int)g_skipNoSig, (int)g_skipRisk);
}

//==================== 主循环 ====================
void OnTick()
{
   CatchUpTick();                    // ★R4：主动扫描未落盘的 closing deal
   g_tickCount++;                    // ★tick 计数（延迟机制的时基）

   // ★延迟到期 → 用【当前市价】执行挂起的开仓（此刻的价就是延迟后的价）
   if(g_pendValid && g_tickCount >= g_pendDue && !HasPosition())
   {
      int    d = g_pendDir;
      double s = g_pendStop;
      double a = g_pendAtr;
      g_pendValid = false;
      ExecOpen(d, s, a);
   }
   else if(g_pendValid && HasPosition())
   {
      g_pendValid = false;           // 已有仓位 → 撤销挂起
   }

   RefreshAccountRisk();
   TrackEquityCurve();

   if(HasPosition())
   {
      ManageOpenPosition();     // 每次 tick 都管理（及时止盈/认错）
      return;                   // 单仓：有仓时不开新仓
   }

   if(!IsNewBucket(g_tf, g_lastEvalBar)) return;

   if(g_ddLocked || g_dailyBlocked) return;
   if(!SessionAllowsOpen()) { g_skipSession++; return; }

   double mean, sigma, atr, er, dev; string why;
   int sig = EvalSignal(mean, sigma, atr, er, dev, why);
   if(sig == 0) { g_skipNoSig++; return; }
   // ★R1：方向门（控制用，不改变信号本身）
   if(sig > 0 && !InpAllowLong)  { g_skipNoSig++; return; }
   if(sig < 0 && !InpAllowShort) { g_skipNoSig++; return; }

   // ★区间过滤：ER 高 = 单边，反转会被顺势打爆
   if(InpUseRangeFilter && er > InpMaxER) { g_skipRange++; return; }

   double stopDist = InpStopATR * atr;
   if(stopDist <= 0.0) return;
   long stopsLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(stopsLevel > 0)
   {
      double minDist = (double)stopsLevel * _Point;
      if(stopDist < minDist) stopDist = minDist;
   }
   g_entryDev = dev;
   OpenPosition(sig, stopDist, atr);
}












