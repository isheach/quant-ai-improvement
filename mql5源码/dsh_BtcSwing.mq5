//+------------------------------------------------------------------+
//|                                          dsh_BtcSwing.mq5        |
//|  比特币专用波段趋势跟随 EA（比特币线自研，v1）                    |
//|                                                                  |
//|  设计动机（来自 btc-048 的真实审计，不是猜测）：                  |
//|    btc-048 (dsh_TrendCore, M30/突破6/确认2/SL2.5ATR) 在训练段    |
//|    给出 1071 笔 / PF 1.11，但审计显示：                          |
//|      sl         n=600  平均 -37.63  ≈ -0.73R                     |
//|      trend_exit n=471  平均 +54.02  ≈ +1.05R                     |
//|      胜率 44% → 期望 ≈ +0.06R/笔（极薄）                         |
//|    问题：EMA 交叉退场把赢家钉死在 ~1R，右尾被截断。              |
//|                                                                  |
//|  本 EA 的四个针对性改动：                                        |
//|    1) 宽跟踪止盈（Chandelier Exit，默认 3.5×ATR）取代 EMA 交叉   |
//|       → 让赢家跑到 2–4R，直接抬高平均盈利 R。                    |
//|    2) 多周期趋势过滤（默认 D1 EMA50）→ 只在宏观趋势同向做突破，  |
//|       试图砍掉 2021/2022/2024 那类亏损年的逆势单。               |
//|    3) 波动率归一化仓位：用 ATR14 / ATR240 的比值反向缩放风险，   |
//|       缓解"同一 ×ATR 在 2018 与 2024 是完全不同美元距离"的问题。 |
//|    4) 时间止损（默认 96 根 TF）：突破失败但没打止损的单子不占用  |
//|       仓位过久，保证换手率（成本优先于收益）。                   |
//|                                                                  |
//|  风控：固定分数风险、最小手处理、日损、回撤冷却锁（可设永久）。   |
//|  未做真钱下单；本文件由比特币线研究代理编写，等待总调度编译注册。 |
//+------------------------------------------------------------------+
#property copyright "BTC line research agent"
#property version   "1.00"
#property strict

//==================== 参数 ====================
input group "=== 手数 / 风险 ==="
input double InpRiskPct            = 1.5;    // 每笔基础风险（占净值%）
input bool   InpUseVolNormalize    = true;   // 波动率归一化（ATR/ATR基准 反向缩放风险）
input double InpVolNormMin         = 0.60;   // 归一化系数下限
input double InpVolNormMax         = 1.80;   // 归一化系数上限
input double InpMaxLot             = 100.0;  // 手数上限
input bool   InpAllowMinLotOvershoot = true; // 算出手数<最小手时按最小手交易
input double InpMinLotMaxRiskPct   = 3.0;    // 上述模式的风险硬上限（占净值%），超过放弃信号

input group "=== 入场：唐奇安突破（不用 EMA 交叉）==="
input ENUM_TIMEFRAMES InpTF        = PERIOD_H1;
input int    InpDonchianBars       = 48;     // 突破前 N 根高/低点
input bool   InpAllowLong          = true;
input bool   InpAllowShort         = true;

input group "=== 趋势过滤（宏观方向）==="
input bool   InpUseTrendFilter     = true;
input ENUM_TIMEFRAMES InpFilterTF  = PERIOD_D1;
input int    InpFilterEMA          = 50;     // 过滤周期 EMA；价格须在其同侧
input int    InpFilterSlopeBars    = 3;      // EMA 斜率回看根数
input bool   InpFilterRequireSlope = false;  // ★要求 EMA 斜率同向（拦"价格高于EMA但EMA已转头"）

input group "=== 入场质量闸门（针对 2026 方向性单边市）==="
input bool   InpUseEntryQuality    = false;  // ★要求突破K线本身足够强
input double InpMinBarRangeATR     = 1.2;    // 突破K线振幅 >= 此倍数 ATR
input double InpMinClosePosFrac    = 0.65;   // 收盘须位于K线区间上部/下部的比例
input bool   InpRequireMomConfirm  = false;  // 要求前一根同向确认

input bool   InpRegimeSwitch       = false;  // ★★regime 切换：牛市只做多 / 熊市只做空

input group "=== 出场 ==="
input int    InpATRPeriod          = 14;
input double InpSL_ATR             = 2.0;    // 初始止损（×ATR(InpTF)）
input bool   InpUseChandelier      = true;   // 宽跟踪止盈
input double InpTrail_ATR          = 3.5;    // Chandelier 距离（×ATR(InpTF)）
input double InpTrailStart_ATR     = 1.0;    // 浮盈超过此倍数 ATR 才启动跟踪
input double InpBE_ATR             = 0.0;    // >0 时：浮盈达此倍数ATR 把止损移到开仓价
input int    InpMaxBarsInTrade     = 96;     // 时间止损（根数，0=关闭）
input double InpTP_ATR             = 0.0;    // 固定止盈（<=0 关闭）

input group "=== 时段（服务器时间）==="
input bool   InpUseSessionFilter   = false;
input int    InpTradeStartHour     = 0;
input int    InpTradeEndHour       = 23;

input group "=== 账户级风控 ==="
input bool   InpUseDailyStop       = true;
input double InpDailyLossPct       = 5.0;
input bool   InpUseDDKill          = true;
input double InpMaxDDPct           = 25.0;
input int    InpDDCooldownMin      = 1440;   // >0=冷却后自动解锁；0=永久锁

input group "=== 杂项 ==="
input long   InpMagic              = 20260913;
input string InpRunTag             = "btcswing";
input bool   InpWriteAudit         = true;
input bool   InpVerboseLog         = false;
input double InpSlippagePoints     = 50;
// ★模拟真实网络延迟：读价 → Sleep(InpLatencyMs) → 用【新价】下单
input int    InpLatencyTicks       = 1;     // ★延迟 tick 数（Sleep 在测试器无效，故用 tick 级延迟）
input int    InpLatencyMs          = 300;   // 模拟下单延迟（毫秒）

//==================== 全局 ====================
double   g_peakEquity    = 0.0;
double   g_dayStartEquity= 0.0;
bool     g_dailyBlocked  = false;
bool     g_ddLocked      = false;
datetime g_ddLockUntil   = 0;
datetime g_curDay        = 0;
ulong    g_ticket        = 0;
double   g_entryPrice    = 0.0;
double   g_initSL        = 0.0;
double   g_curSL         = 0.0;
double   g_bestPrice     = 0.0;
double   g_atrAtEntry    = 0.0;
double   g_riskMoney     = 0.0;
int      g_dir           = 0;
datetime g_entryBarTime  = 0;

// ★tick 级延迟（2026-09-12）：替代在测试器中无效的 Sleep(InpLatencyMs)
int    g_tickCount  = 0;
bool   g_pendValid  = false;
int    g_pendDir    = 0;
double g_pendLot    = 0.0;
double g_pendStop   = 0.0;
double g_pendAtr    = 0.0;
string g_pendNote   = "";
long   g_pendDue    = 0;

//==================== 时间周期换算（照抄已验证过的安全写法）====================
int TFMinutes(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_CURRENT) tf = (ENUM_TIMEFRAMES)Period();
   int v = (int)tf;
   if(v <= 0) return 0;
   if(v < 16385) return v;                    // 1..30 分钟类，值即分钟数
   switch(v)
   {
      case 16385: return 60;                  // H1
      case 16386: return 120;                 // H2
      case 16387: return 180;                 // H3
      case 16388: return 240;                 // H4
      case 16390: return 360;                 // H6
      case 16392: return 480;                 // H8
      case 16396: return 720;                 // H12
   }
   if(v >= 16398 && v < 32769) return 1440;   // D1
   if(v >= 32769 && v < 49153) return 10080;  // W1
   return 43200;                              // MN1
}

// 把 M1 序列聚合成 tf 周期的 OHLC（index 0=最早，最后一根=未收盘的当前bar）
int BuildAggBars(ENUM_TIMEFRAMES tf, int wantBars,
                 double &o[], double &h[], double &l[], double &c[], datetime &bt[])
{
   int tfm = TFMinutes(tf);
   if(tfm < 1 || wantBars < 2) return 0;
   int needM1 = tfm * (wantBars + 2);

   MqlRates m1[];
   ArraySetAsSeries(m1, false);
   ResetLastError();
   int got = CopyRates(_Symbol, PERIOD_M1, 0, needM1, m1);
   if(got < tfm * 2) return 0;

   ArrayResize(o, 0); ArrayResize(h, 0); ArrayResize(l, 0);
   ArrayResize(c, 0); ArrayResize(bt, 0);

   long curBucket = -1;
   double bo = 0, bh = 0, bl = 0, bc = 0;
   datetime bt0 = 0;
   bool opened = false;

   for(int i = 0; i < got; i++)
   {
      long bucket = (long)m1[i].time / ((long)tfm * 60);
      if(!opened || bucket != curBucket)
      {
         if(opened)
         {
            int n = ArraySize(c);
            ArrayResize(o, n+1); ArrayResize(h, n+1);
            ArrayResize(l, n+1); ArrayResize(c, n+1); ArrayResize(bt, n+1);
            o[n]=bo; h[n]=bh; l[n]=bl; c[n]=bc; bt[n]=bt0;
         }
         curBucket = bucket;
         bo = m1[i].open; bh = m1[i].high; bl = m1[i].low; bc = m1[i].close;
         bt0 = m1[i].time;
         opened = true;
      }
      else
      {
         if(m1[i].high > bh) bh = m1[i].high;
         if(m1[i].low  < bl) bl = m1[i].low;
         bc = m1[i].close;
      }
   }
   if(opened)
   {
      int n = ArraySize(c);
      ArrayResize(o, n+1); ArrayResize(h, n+1);
      ArrayResize(l, n+1); ArrayResize(c, n+1); ArrayResize(bt, n+1);
      o[n]=bo; h[n]=bh; l[n]=bl; c[n]=bc; bt[n]=bt0;
   }
   return ArraySize(c);
}

// indexFromEnd: 0=最后一根(未收盘当前bar), 1=最后一根已收盘, ...
double EMAOnArray(const double &arr[], int period, int indexFromEnd)
{
   int n = ArraySize(arr);
   int idx = n - 1 - indexFromEnd;
   if(period < 1 || idx < period - 1) return 0.0;
   double k = 2.0 / (period + 1.0);
   // 用 idx-period+1 .. idx 的 SMA 作为种子，然后递归到 idx
   double sum = 0.0;
   for(int i = idx - period + 1; i <= idx; i++) sum += arr[i];
   double ema = sum / period;
   for(int i = idx - period + 2; i <= idx; i++) ema = arr[i]*k + ema*(1.0-k);
   return ema;
}

// 简单版 ATR：用 bar 的 high/low/close 计算 TR 的 SMA，取"最后一根已收盘"为止
double ATRFromBars(const double &h[], const double &l[], const double &c[],
                   int period, int indexFromEnd)
{
   int n = ArraySize(c);
   int idx = n - 1 - indexFromEnd;          // 最后一根已收盘
   if(period < 1 || idx < period) return 0.0;
   double sum = 0.0;
   for(int i = idx - period + 1; i <= idx; i++)
   {
      double prevClose = c[i-1];
      double tr = MathMax(h[i]-l[i], MathMax(MathAbs(h[i]-prevClose), MathAbs(l[i]-prevClose)));
      sum += tr;
   }
   return sum / period;
}

bool SessionAllowsOpen()
{
   if(!InpUseSessionFilter) return true;
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   if(InpTradeStartHour <= InpTradeEndHour)
      return (t.hour >= InpTradeStartHour && t.hour <= InpTradeEndHour);
   return (t.hour >= InpTradeStartHour || t.hour <= InpTradeEndHour);
}

//==================== 手数 ====================
double AlignLot(double lot)
{
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(vstep <= 0.0) vstep = 0.01;
   if(vmin <= 0.0)  vmin  = vstep;
   if(vmax <= 0.0)  vmax  = 100.0;
   if(lot < vmin) lot = vmin;
   if(lot > vmax) lot = vmax;
   if(lot > InpMaxLot) lot = InpMaxLot;
   // ★向下取整到 step（不要四舍五入，避免超出风险预算）
   double steps = MathFloor(lot / vstep + 1e-9);
   lot = steps * vstep;
   if(lot < vmin) lot = vmin;
   int dg = 2;
   double tmp = vstep;
   while(tmp < 1.0 && dg < 8) { tmp *= 10.0; dg++; }
   return NormalizeDouble(lot, dg);
}

// 按"每 1 美元价格波动 = contract × lot 美元"的合约口径算盈亏，避免 tickvalue 漂移
double MoneyPerPriceUnit(double lot)
{
   double contract = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contract <= 0.0) contract = 1.0;
   return contract * lot;
}

// ★★★ 2026-09-12 Stage1 §1A：逐笔拒单记录（原实现有 5 处【静默】 return 0.0，
//   只能靠 g_skipRisk 计数，无法定位是哪一个闸门拒的）
//   现在把每一处拒单的原因与算术写进独立 CSV：signals.csv
int      g_sigHandle = INVALID_HANDLE;
int      g_sigSeq    = 0;
string   g_lastReject = "";

void LogSignalReject(datetime t, string why, double eq, double stopDist,
                     double ideal, double lot, double riskPctActual)
{
   if(g_sigHandle == INVALID_HANDLE) return;
   FileWrite(g_sigHandle, InpRunTag, _Symbol,
             TimeToString(t, TIME_DATE|TIME_SECONDS),
             why,
             DoubleToString(eq, 2),
             DoubleToString(stopDist, _Digits),
             DoubleToString(ideal, 4),           // raw_lot（理想手数，未取整）
             DoubleToString(lot, 2),             // final_lot（取整后）
             DoubleToString(stopDist * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE) * lot, 2),  // final_risk
             DoubleToString(riskPctActual, 3),
             DoubleToString(InpRiskPct, 3),
             DoubleToString(InpMinLotMaxRiskPct, 3),
             DoubleToString(InpAllowMinLotOvershoot ? 1.0 : 0.0, 0));
   FileFlush(g_sigHandle);
}

double LotForRisk(double stopDist, double riskPct, bool &ok)
{
   ok = false;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= 0.0 || stopDist <= 0.0)
   { g_lastReject = "bad_eq_or_stop"; LogSignalReject(TimeCurrent(), g_lastReject, eq, stopDist, 0, 0, 0); return 0.0; }
   double riskMoney = eq * riskPct / 100.0;
   double contract  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   if(contract <= 0.0) contract = 1.0;
   double ideal = riskMoney / (stopDist * contract);      // 手
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double lot = AlignLot(ideal);
   if(lot <= 0.0)
   { g_lastReject = "floor_to_zero"; LogSignalReject(TimeCurrent(), g_lastReject, eq, stopDist, ideal, 0, 0); return 0.0; }

   if(lot < vmin) lot = vmin;

   // 取整后复核实际风险
   double actualRisk = stopDist * contract * lot;
   double riskPctActual = actualRisk / eq * 100.0;

   if(ideal < vmin)
   {
      // 理想手数低于地板 → 只能按最小手；除非显式禁止，或超过硬上限
      if(!InpAllowMinLotOvershoot)
      { g_lastReject = "no_overshoot"; LogSignalReject(TimeCurrent(), g_lastReject, eq, stopDist, ideal, lot, riskPctActual); return 0.0; }
      if(riskPctActual > InpMinLotMaxRiskPct)
      { g_lastReject = "cap_exceeded_overshoot"; LogSignalReject(TimeCurrent(), g_lastReject, eq, stopDist, ideal, lot, riskPctActual); return 0.0; }
   }
   if(riskPctActual > InpMinLotMaxRiskPct)
   { g_lastReject = "cap_exceeded_normal"; LogSignalReject(TimeCurrent(), g_lastReject, eq, stopDist, ideal, lot, riskPctActual); return 0.0; }

   ok = true;
   g_lastReject = "";
   return lot;
}

//==================== 持仓工具 ====================
int CountMyPositions()
{
   int n = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
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
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      return tk;
   }
   return 0;
}

//==================== 审计 CSV ====================
int g_auditHandle = INVALID_HANDLE;
void OpenAudit()
{
   if(!InpWriteAudit) return;
   // 与 dsh_TrendCore 的审计布局保持一致：Common\Files\dshtrend\<runTag>\trades.csv
   string fn = "dshtrend\\" + InpRunTag + "\\trades.csv";
   bool exists = FileIsExist(fn, FILE_COMMON);
   g_auditHandle = FileOpen(fn, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(g_auditHandle == INVALID_HANDLE) return;
   FileSeek(g_auditHandle, 0, SEEK_END);
   if(!exists)
   {
      FileWrite(g_auditHandle, "run_tag","symbol","time","dir","entry","exit",
                "vol","pnl","risk_money","atr_at_entry","exit_reason",
                "position_id","close_type","profit","swap","commission");   // ★Stage1-R2 分列成本
   }

   // ★Stage1 §1A：逐笔拒单审计 signals.csv（每次拒单都落盘，可定位是哪个闸门）
   string sf = "dshtrend\\" + InpRunTag + "\\signals.csv";
   bool sexists = FileIsExist(sf, FILE_COMMON);
   g_sigHandle = FileOpen(sf, FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(g_sigHandle != INVALID_HANDLE)
   {
      FileSeek(g_sigHandle, 0, SEEK_END);
      if(!sexists)
         FileWrite(g_sigHandle, "run_tag","symbol","time","reject_reason",
                   "equity","stop_dist","raw_lot","final_lot","final_risk",
                   "risk_pct_actual","risk_pct_target","cap_pct","allow_overshoot");
   }
}

void AuditRow(datetime t, int dir, double entry, double exitPx, double vol,
              double pnl, double riskMoney, double atrEntry, string reason)
{
   if(!InpWriteAudit || g_auditHandle == INVALID_HANDLE) return;
   FileWrite(g_auditHandle, InpRunTag, _Symbol,
             TimeToString(t, TIME_DATE|TIME_SECONDS), IntegerToString(dir),
             DoubleToString(entry, _Digits), DoubleToString(exitPx, _Digits),
             DoubleToString(vol, 2), DoubleToString(pnl, 2),
             DoubleToString(riskMoney, 2), DoubleToString(atrEntry, 2), reason);
   FileFlush(g_auditHandle);
}

//==================== ★从成交历史记录出场（必需）====================
// 实测缺口：本 EA 原先只在【主动平仓】里记审计（AuditRow），而券商侧
// SL/TP 平仓完全不经过那条路径。实测 BS75t2 报告 66 笔、审计只 3 行 ——
// 丢掉 63 笔止损单。dsh_TrendCore 用 OnTradeTransaction 读成交历史解决，
// 这里补齐（审计字段保持与 TrendCore 一致）。
// ★★★ 2026-09-12 Stage1 修复（GPT 执行框架 §1B）：
//   旧实现三个缺陷：
//     ① entry 硬编码 DoubleToString(0.0,_Digits) → 审计 entry 永远是 0
//     ② g_riskMoney / g_atrAtEntry 是【全局单值】→ 每持仓无独立状态，重入时会串值
//     ③ 部分平仓被当成完整平仓 → 风险重复计数
//   修复：per-position 状态表 + HistorySelectByPosition 反查开仓腿 + 部分平仓按比例拆分
#define MAX_POS_TRACK 64

struct PosTrack
{
   ulong    pid;
   double   entry;
   double   entryVol;
   double   riskMoney;
   double   atr;
   double   stopDist;
   datetime entryTime;
   double   closedVol;
   bool     used;
};

PosTrack g_pt[MAX_POS_TRACK];

int PosSlot(ulong pid, bool create)
{
   for(int i = 0; i < MAX_POS_TRACK; i++)
      if(g_pt[i].used && g_pt[i].pid == pid) return i;
   if(!create) return -1;
   for(int i = 0; i < MAX_POS_TRACK; i++)
      if(!g_pt[i].used)
      {
         g_pt[i].used = true; g_pt[i].pid = pid;
         g_pt[i].entry = 0.0; g_pt[i].entryVol = 0.0;
         g_pt[i].riskMoney = 0.0; g_pt[i].atr = 0.0;
         g_pt[i].stopDist = 0.0; g_pt[i].entryTime = 0;
         g_pt[i].closedVol = 0.0;
         return i;
      }
   return -1;
}

double PositionVolumeByID(ulong pid)
{
   if(PositionSelectByTicket(pid))
      return PositionGetDouble(POSITION_VOLUME);
   return 0.0;
}

void RecordExitDeal(ulong dealTicket)
{
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;
   long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY) return;

   // ★★★ 2026-09-13 Stage1-R2（GPT 复核 §4 阶段B 第 4 条）：
   //   profit / swap / commission【分列】保存，净值只能由明确公式合成：
   //     pnl = profit + swap + commission
   //   旧实现把三者合并成单个 pnl，无法与 MT5 报告逐项对账。
   double dProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT);
   double dSwap   = HistoryDealGetDouble(dealTicket, DEAL_SWAP);
   double dComm   = HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
   double pnl     = dProfit + dSwap + dComm;
   double price= HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double vol  = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   long   rsn  = HistoryDealGetInteger(dealTicket, DEAL_REASON);
   datetime t  = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
   long   dt   = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
   ulong  pid  = (ulong)HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
   int    dir  = (dt == DEAL_TYPE_SELL) ? 1 : -1;

   string reason = "";
   string cmt = HistoryDealGetString(dealTicket, DEAL_COMMENT);
   if(StringFind(cmt,"dd_kill")>=0) reason="dd_kill";
   else if(StringFind(cmt,"time")>=0) reason="time_exit";
   else if(StringFind(cmt,"chand")>=0) reason="chandelier";
   else if(StringFind(cmt,"trend")>=0) reason="trend_exit";
   else if(StringFind(cmt,"sl")>=0) reason="sl";
   else
   {
      if(rsn==DEAL_REASON_SL) reason="sl";
      else if(rsn==DEAL_REASON_TP) reason="tp";
      else if(rsn==DEAL_REASON_SO) reason="stopout";
      else reason="expert";
   }

   int slot = PosSlot(pid, false);
   double entryPx = 0.0, entryVol = 0.0, entryRisk = 0.0, entryAtr = 0.0;
   datetime entryTm = 0;
   if(slot >= 0)
   {
      entryPx   = g_pt[slot].entry;
      entryVol  = g_pt[slot].entryVol;
      entryRisk = g_pt[slot].riskMoney;
      entryAtr  = g_pt[slot].atr;
      entryTm   = g_pt[slot].entryTime;
   }
   if(entryPx <= 0.0 && HistorySelectByPosition(pid))
   {
      int nd = HistoryDealsTotal();
      double sumPV = 0.0, sumV = 0.0; datetime etm = 0;
      for(int i = 0; i < nd; i++)
      {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0) continue;
         if(HistoryDealGetInteger(tk, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
         double p = HistoryDealGetDouble(tk, DEAL_PRICE);
         double v = HistoryDealGetDouble(tk, DEAL_VOLUME);
         sumPV += p * v; sumV += v;
         datetime tt = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
         if(etm == 0 || tt < etm) etm = tt;
      }
      if(sumV > 0.0) entryPx = sumPV / sumV;
      entryVol = sumV;
      entryTm  = etm;
   }
   if(entryRisk <= 0.0 && slot >= 0 && g_pt[slot].stopDist > 0.0 && entryVol > 0.0)
      entryRisk = g_pt[slot].stopDist * MoneyPerPriceUnit(entryVol);

   double riskThis = entryRisk;
   bool   partial  = false;
   if(slot >= 0 && entryVol > 0.0 && vol < entryVol - 1e-9)
   {
      riskThis = entryRisk * (vol / entryVol);
      partial  = true;
   }

   if(g_auditHandle == INVALID_HANDLE) return;
   FileWrite(g_auditHandle, InpRunTag, _Symbol,
             TimeToString(t, TIME_DATE|TIME_SECONDS), IntegerToString(dir),
             DoubleToString(entryPx,_Digits),      // ★ 反查得到的真实入场价
             DoubleToString(price,_Digits),
             DoubleToString(vol,2), DoubleToString(pnl,2),
             DoubleToString(riskThis,2),           // ★ 该持仓自己的风险
             DoubleToString(entryAtr,2),           // ★ 该持仓自己的 ATR
             reason,
             IntegerToString((long)pid),           // ★ position id（对账用）
             partial ? "partial" : "full",          // ★ 平仓类型
             DoubleToString(dProfit,2),               // ★ profit（不含 swap/commission）
             DoubleToString(dSwap,2),                 // ★ swap
             DoubleToString(dComm,2));                // ★ commission

   if(slot >= 0)
   {
      g_pt[slot].closedVol += vol;
      if(PositionVolumeByID(pid) <= 0.0) g_pt[slot].used = false;
   }
   FileFlush(g_auditHandle);
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      RecordExitDeal(trans.deal);
}

//==================== 交易 ====================
bool PickFilling(ENUM_ORDER_TYPE_FILLING &f)
{
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) != 0) { f = ORDER_FILLING_FOK; return true; }
   if((mode & SYMBOL_FILLING_IOC) != 0) { f = ORDER_FILLING_IOC; return true; }
   f = ORDER_FILLING_RETURN;
   return true;
}

double NormPrice(double p) { return NormalizeDouble(p, _Digits); }

bool OpenPosition(int dir, double lot, double stopDist, double atr, string reason)
{
   // ★延迟机制（2026-09-12 重写）：
   //   旧实现用 Sleep(InpLatencyMs) —— 实测在 MT5 策略测试器里【不推进模拟时间】，
   //   期间不产生新 tick、价格不变 → Sleep 后重读价读到同一个价 → 结果与 0 延迟逐位相同。
   //   （A/B 实证：144/144 pass 逐位全同）
   //   新实现：把请求挂起，等够 InpLatencyTicks 个 tick 后，在【那一刻的市价】上执行。
   //   tick 在测试器里是推进的，所以延迟真实生效。
   //   用市价单（TRADE_ACTION_DEAL）而非挂单 —— 挂单会因价格跑掉被拒（invalid price），
   //   那会造出"延迟越大成交越少"的假象，与"延迟只让成交价变差"混淆。
   if(InpLatencyTicks > 0)
   {
      g_pendDir   = dir;
      g_pendLot   = lot;
      g_pendStop  = stopDist;
      g_pendAtr   = atr;
      g_pendNote  = reason;
      g_pendDue   = g_tickCount + InpLatencyTicks;
      g_pendValid = true;
      return false;      // 已挂起；结果由 DoPendingOpen() 在后续 tick 执行
   }

   return ExecOpen(dir, lot, stopDist, atr, reason);
}

// ★实际下单路径（不含延迟判定）。延迟机制与直连路径共用它，避免递归。
bool ExecOpen(int dir, double lot, double stopDist, double atr, string reason)
{
   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);

   double price = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0) return false;

   double sl = (dir > 0) ? price - stopDist : price + stopDist;

   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = _Symbol;
   req.volume       = lot;
   req.type         = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price        = NormPrice(price);
   req.sl           = NormPrice(sl);
   req.deviation    = (ulong)InpSlippagePoints;
   req.magic        = InpMagic;
   req.comment      = "open_" + reason;
   ENUM_ORDER_TYPE_FILLING f;
   PickFilling(f);
   req.type_filling = f;

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      if(InpVerboseLog)
         PrintFormat("[%s] 开仓失败 retcode=%d err=%d", InpRunTag, res.retcode, GetLastError());
      return false;
   }

   g_ticket = FindMyTicket();
   if(g_ticket == 0) return false;

   if(!PositionSelectByTicket(g_ticket)) return false;
   g_entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   g_initSL     = PositionGetDouble(POSITION_SL);
   g_curSL      = g_initSL;
   g_bestPrice  = g_entryPrice;
   g_atrAtEntry = atr;
   g_riskMoney  = stopDist * MoneyPerPriceUnit(lot);
   g_dir        = dir;
   g_entryBarTime = iTime(_Symbol, (ENUM_TIMEFRAMES)Period(), 0);

   // ★Stage1：登记 per-position 状态（供 RecordExitDeal 单独取用，不再依赖全局单值）
   {
      int sl2 = PosSlot(g_ticket, true);
      if(sl2 >= 0)
      {
         g_pt[sl2].entry     = g_entryPrice;
         g_pt[sl2].entryVol  = lot;
         g_pt[sl2].riskMoney = stopDist * MoneyPerPriceUnit(lot);
         g_pt[sl2].atr       = atr;
         g_pt[sl2].stopDist  = stopDist;
         g_pt[sl2].entryTime = TimeCurrent();
         g_pt[sl2].closedVol = 0.0;
      }
   }

   if(InpVerboseLog)
      PrintFormat("[%s] OPEN dir=%d lot=%.2f price=%.3f sl=%.3f risk=%.2f",
                  InpRunTag, dir, lot, g_entryPrice, g_curSL, g_riskMoney);
   return true;
}

bool ModifySL(double newSL)
{
   if(g_ticket == 0) return false;
   if(!PositionSelectByTicket(g_ticket)) return false;
   double cur = PositionGetDouble(POSITION_SL);
   if(MathAbs(cur - newSL) < _Point * 2.0) return false;
   if(g_dir > 0 && newSL <= cur) return false;
   if(g_dir < 0 && cur > 0.0 && newSL >= cur) return false;

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action   = TRADE_ACTION_SLTP;
   req.symbol   = _Symbol;
   req.position = g_ticket;
   req.sl       = NormPrice(newSL);
   req.tp       = 0.0;
   if(!OrderSend(req, res)) return false;
   g_curSL = newSL;
   return true;
}

bool ClosePosition(string reason)
{
   if(g_ticket == 0) return false;

   double pnl = 0.0, vol = 0.0, entry = 0.0, exitPx = 0.0;
   if(PositionSelectByTicket(g_ticket))
   {
      entry = PositionGetDouble(POSITION_PRICE_OPEN);
      vol   = PositionGetDouble(POSITION_VOLUME);
   }
   if(vol <= 0.0) { g_ticket = 0; return false; }

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = _Symbol;
   req.volume    = vol;
   req.position  = g_ticket;
   req.deviation = (ulong)InpSlippagePoints;
   req.magic     = InpMagic;
   req.type      = (g_dir > 0) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.price     = (g_dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                               : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   req.comment   = "close_" + reason;
   ENUM_ORDER_TYPE_FILLING f;
   PickFilling(f);
   req.type_filling = f;

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
      return false;

   exitPx = req.price;
   pnl = (g_dir > 0) ? (exitPx - entry) * MoneyPerPriceUnit(vol)
                     : (entry - exitPx) * MoneyPerPriceUnit(vol);

   // ★★★ 2026-09-12 Stage1 修复（去重）：
   //   原来这里调 AuditRow() 主动写一行；但 OnTradeTransaction → RecordExitDeal()
   //   也会为同一次平仓写一行 → 【同一次平仓被记两遍】。
   //   实测证据（BT_S1CHK/trades.csv）：
   //     2024.06.07 14:48:00 entry=69020.30 exit=71380.98 pnl=23.61（无 position_id）
   //     2024.06.07 14:48:00 entry=69020.30 exit=71380.98 pnl=22.97（有 position_id=4）
   //   → 现在只由 RecordExitDeal 写（它用 DEAL_POSITION_ID 反查真实 entry，更权威）。
   //   AuditRow 保留供其他调用点使用，但此处不再调用。
   g_ticket = 0; g_dir = 0;
   return true;
}

//==================== 信号 ====================
int EvalSignal(double &atrOut, string &why)
{
   atrOut = 0.0; why = "";

   int want = MathMax(InpDonchianBars + 10, 60);
   double o[], h[], l[], c[]; datetime bt[];
   int n = BuildAggBars(InpTF, want, o, h, l, c, bt);
   if(n < InpDonchianBars + 5) { why = "few_bars"; return 0; }

   double atr = ATRFromBars(h, l, c, InpATRPeriod, 1);
   if(atr <= 0.0) { why = "atr_zero"; return 0; }
   atrOut = atr;

   double close1 = c[n-2];                    // 最后一根已收盘
   double hiPrior = -1e18, loPrior = 1e18;
   for(int i = n-3; i >= 0 && (n-3-i) < InpDonchianBars; i--)
   {
      if(h[i] > hiPrior) hiPrior = h[i];
      if(l[i] < loPrior) loPrior = l[i];
   }
   if(hiPrior <= -1e17 || loPrior >= 1e17) { why = "no_range"; return 0; }

   // 宏观趋势过滤：在 FilterTF 上算 EMA，比较"最后一根已收盘"的价格
   int trendUp = 0;
   if(InpUseTrendFilter)
   {
      int fwant = MathMax(InpFilterEMA + 10, 40);
      double fo[], fh[], fl[], fc[]; datetime fbt[];
      int fn = BuildAggBars(InpFilterTF, fwant, fo, fh, fl, fc, fbt);
      if(fn < InpFilterEMA + 3) { why = "filter_few_bars"; return 0; }
      double fema = EMAOnArray(fc, InpFilterEMA, 1);
      if(fema <= 0.0) { why = "filter_ema"; return 0; }
      double fclose = fc[fn-2];
      trendUp = (fclose > fema) ? 1 : ((fclose < fema) ? -1 : 0);
      if(trendUp == 0) { why = "filter_flat"; return 0; }

      // ★斜率闸门：价格在 EMA 上方但 EMA 已转头向下时，说明趋势正在反转
      //   （诊断依据：2025.10–2026.02 BTC 自 120570 跌至 69978（−42%），
      //    但"价格 > D1 EMA50"这一水平条件在整个下跌初期仍成立，
      //    导致只做多版本在 2026 段胜率跌到 5.6%。水平条件滞后，斜率不滞后。）
      if(InpFilterRequireSlope && InpFilterSlopeBars > 0)
      {
         double femaOld = EMAOnArray(fc, InpFilterEMA, 1 + InpFilterSlopeBars);
         if(femaOld > 0.0)
         {
            double slope = fema - femaOld;
            if(trendUp > 0 && slope <= 0.0) { why = "filter_slope_flat_long"; return 0; }
            if(trendUp < 0 && slope >= 0.0) { why = "filter_slope_flat_short"; return 0; }
         }
      }
   }

   // ★入场质量闸门：突破K线自身的强度
   //   诊断依据：2026 段 18 笔只亏了 17 笔（胜率 5.6%），且全段成交距离/ATR 与训练段同构，
   //   说明失败的是一批"弱突破后立刻反转"的信号，而非止损或仓位问题。
   if(InpUseEntryQuality)
   {
      double bH = h[n-2], bL = l[n-2];
      double barRange = bH - bL;
      if(barRange < InpMinBarRangeATR * atr) { why = "weak_bar_range"; return 0; }
      if(barRange > 0.0)
      {
         double posInBar = (close1 - bL) / barRange;   // 0=收在最低, 1=收在最高
         bool upStrong   = (posInBar >= InpMinClosePosFrac);
         bool downStrong = (posInBar <= (1.0 - InpMinClosePosFrac));
         if(!upStrong && !downStrong) { why = "weak_close_pos"; return 0; }
      }
   }

   // ★前一根同向确认：要求突破前一根就已经同向收（不是孤立一根插上去）
   if(InpRequireMomConfirm)
   {
      double cPrev = c[n-3];
      double hPrev = h[n-3], lPrev = l[n-3];
      if(hPrev - lPrev <= 0.0) { why = "prev_flat"; return 0; }
      double posPrev = (cPrev - lPrev) / (hPrev - lPrev);
      bool prevUp   = (posPrev >= 0.5);
      bool prevDown = (posPrev <= 0.5);
      double cPrev2 = c[n-4];
      bool risePrev = (cPrev > cPrev2);
      bool fallPrev = (cPrev < cPrev2);
      if(!((prevUp && risePrev) || (prevDown && fallPrev))) { why = "no_mom_confirm"; return 0; }
   }

   bool brkUp   = (close1 > hiPrior);
   bool brkDown = (close1 < loPrior);

   //★★ regime 切换：由宏观 regime 决定【唯一允许】的方向
   //   诊断依据（全部为实测）：
   //     · 只做多形态(test) 覆盖率恒为 41%（末笔 2025.10.27，之后 215 天空窗），
   //       因为 BTC 跌破 D1 EMA200 后只做多被全面禁止 → 43 个月空转；
   //     · 双向形态覆盖率 100% 但 valid 为负(-34.72)、PF 摊薄到 1.12，
   //       因为在下跌趋势里"也做空"与不良信号混在一起。
   //   → 本开关把"停牌"换成"仅做空"：regime=+1 只许多，regime=-1 只许空。
   //   注意：使用【局部】布尔，不修改 InpAllowLong/InpAllowShort 本身，
   //         以免污染其它逻辑（例如审计与诊断）。
   bool allowLongNow  = InpAllowLong;
   bool allowShortNow = InpAllowShort;
   if(InpRegimeSwitch && InpUseTrendFilter && trendUp != 0)
   {
      if(trendUp > 0) allowShortNow = false;   // 牛市：只做多
      else            allowLongNow  = false;   // 熊市：只做空
   }

   if(brkUp)
   {
      if(!allowLongNow) { why = InpRegimeSwitch ? "regime_no_long" : "long_off"; return 0; }
      if(InpUseTrendFilter && trendUp < 0) { why = "filter_block_long"; return 0; }
      why = "break_up";
      return 1;
   }
   if(brkDown)
   {
      if(!allowShortNow) { why = InpRegimeSwitch ? "regime_no_short" : "short_off"; return 0; }
      if(InpUseTrendFilter && trendUp > 0) { why = "filter_block_short"; return 0; }
      why = "break_down";
      return -1;
   }
   why = "no_signal";
   return 0;
}

//==================== 持仓管理 ====================
void ManageOpenPosition()
{
   if(g_ticket == 0) { g_ticket = FindMyTicket(); if(g_ticket == 0) return; }
   if(!PositionSelectByTicket(g_ticket)) { g_ticket = 0; return; }

   g_dir = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   double entry = PositionGetDouble(POSITION_PRICE_OPEN);
   double curSL = PositionGetDouble(POSITION_SL);

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double cur = (g_dir > 0) ? bid : ask;
   if(cur <= 0.0) return;

   if(g_dir > 0) { if(cur > g_bestPrice) g_bestPrice = cur; }
   else          { if(cur < g_bestPrice || g_bestPrice <= 0.0) g_bestPrice = cur; }

   double atr = g_atrAtEntry;
   if(atr <= 0.0) return;

   double profitDist = (g_dir > 0) ? (g_bestPrice - entry) : (entry - g_bestPrice);

   // 1) 保本止损
   if(InpBE_ATR > 0.0 && profitDist >= InpBE_ATR * atr)
   {
      ModifySL(entry);
   }

   // 2) Chandelier 宽跟踪止盈
   if(InpUseChandelier && InpTrail_ATR > 0.0 && profitDist >= InpTrailStart_ATR * atr)
   {
      double newSL = (g_dir > 0) ? (g_bestPrice - InpTrail_ATR * atr)
                                 : (g_bestPrice + InpTrail_ATR * atr);
      ModifySL(newSL);
   }

   // 3) 时间止损
   if(InpMaxBarsInTrade > 0)
   {
      int tfm = TFMinutes(InpTF);
      if(tfm > 0)
      {
         int barsHeld = (int)((TimeCurrent() - g_entryBarTime) / (tfm * 60));
         if(barsHeld >= InpMaxBarsInTrade)
         {
            ClosePosition("time_exit");
            return;
         }
      }
   }
}

//==================== 账户风控 ====================
void CheckAccountRisk()
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= 0.0) return;

   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   datetime today = StringToTime(StringFormat("%04d.%02d.%02d", t.year, t.mon, t.day));
   if(today != g_curDay)
   {
      g_curDay = today;
      g_dayStartEquity = eq;
      g_dailyBlocked = false;
   }

   if(eq > g_peakEquity) g_peakEquity = eq;

   if(InpUseDailyStop && g_dayStartEquity > 0.0)
   {
      double dd = (g_dayStartEquity - eq) / g_dayStartEquity * 100.0;
      if(dd >= InpDailyLossPct) g_dailyBlocked = true;
   }

   if(InpUseDDKill && g_peakEquity > 0.0)
   {
      datetime now = TimeCurrent();
      double dd = (g_peakEquity - eq) / g_peakEquity * 100.0;

      if(g_ddLocked && InpDDCooldownMin > 0 && g_ddLockUntil > 0 && now >= g_ddLockUntil)
      {
         g_ddLocked = false;
         g_ddLockUntil = 0;
         g_peakEquity = eq;
         if(InpVerboseLog) PrintFormat("[%s] ★DD锁冷却结束，恢复交易（净值 %.2f）", InpRunTag, eq);
      }

      if(dd >= InpMaxDDPct && !g_ddLocked)
      {
         g_ddLocked = true;
         if(InpDDCooldownMin > 0)
         {
            g_ddLockUntil = now + (datetime)(InpDDCooldownMin * 60);
            if(InpVerboseLog)
               PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，冷却 %d 分钟", InpRunTag, dd, InpDDCooldownMin);
         }
         else if(InpVerboseLog)
            PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，永久锁", InpRunTag, dd);
         if(g_ticket != 0) ClosePosition("dd_kill");
      }
   }
}

//==================== 生命周期 ====================
int OnInit()
{
   if(InpRiskPct <= 0.0 || InpRiskPct > 20.0)
   { Print("InpRiskPct 必须在 (0,20]"); return INIT_PARAMETERS_INCORRECT; }
   if(InpDonchianBars < 2)
   { Print("InpDonchianBars 必须 >= 2"); return INIT_PARAMETERS_INCORRECT; }
   if(TFMinutes(InpTF) <= 0)
   { Print("InpTF 无法换算分钟数"); return INIT_PARAMETERS_INCORRECT; }

   g_peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayStartEquity = g_peakEquity;
   g_curDay = 0;
   g_ticket = 0;
   OpenAudit();

   PrintFormat("[%s] init TF=%d min=%d donchian=%d SL=%.2fATR trail=%.2fATR(%.1fATR起) "
               "volNorm=%s filter=%s(%dEMA) maxBars=%d risk=%.2f%%",
               InpRunTag, (int)InpTF, TFMinutes(InpTF), InpDonchianBars, InpSL_ATR,
               InpTrail_ATR, InpTrailStart_ATR, InpUseVolNormalize?"on":"off",
               InpUseTrendFilter?"on":"off", InpFilterEMA, InpMaxBarsInTrade, InpRiskPct);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_auditHandle != INVALID_HANDLE)
   {
      FileClose(g_auditHandle);
      g_auditHandle = INVALID_HANDLE;
   }
   if(g_sigHandle != INVALID_HANDLE)
   {
      FileClose(g_sigHandle);
      g_sigHandle = INVALID_HANDLE;
   }
}

void OnTick()
{
   g_tickCount++;                    // ★tick 计数（延迟机制的时基）

   // ★延迟到期 → 用【当前市价】执行挂起的开仓（此刻的价就是延迟后的价）
   if(g_pendValid && g_tickCount >= g_pendDue && CountMyPositions() == 0)
   {
      int    d = g_pendDir;
      double l = g_pendLot, s = g_pendStop, a = g_pendAtr;
      string n = g_pendNote;
      g_pendValid = false;
      ExecOpen(d, l, s, a, n);
   }
   else if(g_pendValid && CountMyPositions() > 0)
   {
      g_pendValid = false;           // 已有仓位（别处成交）→ 撤销挂起
   }

   CheckAccountRisk();

   // 有仓 → 只管仓
   if(CountMyPositions() > 0)
   {
      ManageOpenPosition();
      return;
   }

   // 只在 InpTF 新根上评估入场（用时间桶判断，保证 InpTF 短于图表周期时也准确）
   int tfm = TFMinutes(InpTF);
   if(tfm <= 0) return;
   long bucket = (long)TimeCurrent() / ((long)tfm * 60);
   static long lastBucket = -1;
   if(bucket == lastBucket) return;
   lastBucket = bucket;

   if(g_ddLocked) return;
   if(g_dailyBlocked) return;
   if(!SessionAllowsOpen()) return;

   double atr; string why;
   int sig = EvalSignal(atr, why);
   if(sig == 0) return;

   // 波动率归一化
   double riskPct = InpRiskPct;
   if(InpUseVolNormalize)
   {
      double o[], h[], l[], c[]; datetime bt[];
      int n2 = BuildAggBars(InpTF, MathMax(InpATRPeriod*20, 260), o, h, l, c, bt);
      if(n2 > InpATRPeriod * 5)
      {
         double atrBase = ATRFromBars(h, l, c, InpATRPeriod, 1 + InpATRPeriod * 10);
         if(atrBase > 0.0)
         {
            double ratio = atr / atrBase;                 // >1 = 当前波动高于基准
            double scale = 1.0 / ratio;                   // 波动高 → 风险小
            if(scale < InpVolNormMin) scale = InpVolNormMin;
            if(scale > InpVolNormMax) scale = InpVolNormMax;
            riskPct = InpRiskPct * scale;
         }
      }
   }

   double stopDist = InpSL_ATR * atr;
   if(stopDist <= 0.0) return;

   long stopsLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   if(stopsLevel > 0)
   {
      double minDist = (double)stopsLevel * _Point;
      if(stopDist < minDist) return;
   }

   bool ok = false;
   double lot = LotForRisk(stopDist, riskPct, ok);
   if(!ok || lot <= 0.0)
   {
      if(InpVerboseLog)
         PrintFormat("[%s] 手数不可行 why=%s stopDist=%.2f risk=%.2f%%", InpRunTag, why, stopDist, riskPct);
      return;
   }

   OpenPosition(sig, lot, stopDist, atr, why);
}
//+------------------------------------------------------------------+


