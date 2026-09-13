//+------------------------------------------------------------------+
//|  dsh_TrendCore.mq5                                               |
//|  DeepSeek / 新量化策略 — 核心趋势策略（单品种、单一职责）              |
//|                                                                  |
//|  ================== 为什么重写而不是继续改 eva028 ==================
//|  倒序审计 eva028（37 代最新）后确认它有三个结构性问题：                |
//|                                                                  |
//|  1) 【网格子系统实际是死的】stage1_full 参数下 2 年 0 成交：          |
//|     优化器把 InpGridZ 从设计默认 7000 抬到 20000（优化上边界），       |
//|     网格距变成 $20~25，在 60 分钟基线上几乎永不触发。                  |
//|     → 而且就算调回来也不赚钱：纯网格 6 档 2 年净利 −72~+43。           |
//|       根因：网格单均毛利润 $0.15 < 往返点差 $0.40。                    |
//|  2) 【风控层是"哑"的】永久锁 15/25/40%/关 → 结果完全相同；            |
//|     日损开/关 → 完全相同。因为回撤只到 10.9%，从未触发。               |
//|  3) 【精度参数留优化空间】8 个参数（快EMA/确认根数/RV阈值/ADX/         |
//|     Vol-Gate 三阈值）在 stage1_full 里仍标 Y。实测代价：              |
//|     优化过的参数集 训练 +272 / 验证 −44；锁回设计默认后              |
//|     训练 +76 / 验证 +243。→ 训练集越好看，样本外越差。                 |
//|                                                                  |
//|  ================== 本 EA 的设计原则 ==================
//|  A. 【只做趋势，不做网格】网格已被证伪，删掉 60% 的代码和全部耦合。
//|  B. 【全部风险用"账户百分比"表达】不用绝对美元、不用点数。
//|     这样同一套参数能跨本金、跨品种直接复用（旧项目最大的迁移障碍）。
//|  C. 【精度参数永不进优化空间】见 LOCKED 区，只能在源码里改。
//|  D. 【机制必须可验证】每次出场都写 exit_reason，用计数确认真的触发过。
//|  E. 【对称多空】不依赖单边行情（验证期是牛市，必须能反向赚钱才算数）。
//|                                                                  |
//|  ================== 策略逻辑 ==================
//|  趋势周期：M5（与旧项目一致，实测有效）
//|  入场（做多，做空对称）：
//|    - 快EMA > 慢EMA
//|    - 慢EMA 斜率 > 0（当前 vs N 根前）
//|    - 收盘价突破前 N 根的 M5 高点
//|    - 已实现波动率 RV% >= 阈值（低波动时不开仓 —— 旧项目 Vol-Gate 的教训）
//|    - 无持仓（单仓模式，避免加仓复杂度）
//|  出场（按优先级）：
//|    - 初始止损 = k1 × ATR(M5)                → sl
//|    - 移动止损 = 最高价 - k2 × ATR(M5)        → trail
//|    - 固定止盈 = k3 × ATR(M5)，k3<=0 则关闭    → tp
//|    - 趋势反转（快慢EMA 交叉反向）             → trend_exit
//|    - 日内亏损达上限                            → daily_stop
//|    - 净值高水位回撤达上限（永久锁）             → dd_kill
//|                                                                  |
//|  仓位：风险 = 净值 × InpRiskPct%，止损距离反推手数，
//|        手数下限用品种的 volume_min（不足则跳过该信号，不冒险超仓）。
//+------------------------------------------------------------------+
#property copyright "DeepSeek"
#property version   "1.00"
#property strict

//==================== 输入参数 ====================
input group "=== 手数 / 风险（全部按账户百分比）==="
input double InpRiskPct          = 1.5;    // 每笔风险 = 净值的百分之几
input double InpMaxLot           = 1.00;   // 手数上限（防计算异常）
input bool   InpUseEquityForRisk = true;   // true=按净值算风险；false=按余额
input bool   InpAllowMinLotOvershoot = true; // 算出的手数小于券商最小手时，允许按最小手交易
input double InpMinLotMaxRiskPct = 3.0;    // 上述模式下的风险硬上限（占净值%）；超过就放弃该信号

input group "=== 趋势识别（M5）==="
input ENUM_TIMEFRAMES InpTrendTF       = PERIOD_M5;
input int    InpFastEMA          = 15;     // 快EMA周期
input int    InpSlowEMA          = 60;     // 慢EMA周期
input int    InpSlopeLookback    = 4;      // 慢EMA斜率回看根数
input int    InpBreakoutBars     = 30;     // 收盘突破前N根高/低点
input bool   InpUseTrendConfirm  = true;   // 是否要求连续N根确认
input int    InpTrendConfirmBars = 3;      // 连续确认根数
input bool   InpAllowLong        = true;
input bool   InpAllowShort       = true;

input group "=== 波动率闸门（RV% = 100×RMS(1分钟收盘差)/现价）==="
input bool   InpUseRVGate        = true;   // 低波动时不开新仓
input int    InpRVWindowMinutes  = 15;     // RV 计算窗口（M1 根数）
input double InpRVMinPct         = 0.020;  // RV% 低于此值 → 不开新仓

input group "=== 止损 / 止盈 / 移动止损（全部 ATR(M5) 倍数）==="
input int    InpATRPeriod        = 14;
input double InpSL_ATR           = 2.5;    // 初始止损
input double InpTrail_ATR        = 3.0;    // 移动止损（<=0 关闭）
input double InpTrailStart_ATR   = 1.0;    // 浮盈超过此倍数ATR后才启动移动
input double InpTP_ATR           = 0.0;    // 固定止盈（<=0 关闭）
input bool   InpExitOnCross      = true;   // 快慢EMA反向交叉即平仓

input group "=== 账户级风控（净值百分比）==="
input bool   InpUseDailyStop     = true;
input double InpDailyLossPct     = 3.0;    // 日内亏损上限（占净值%）
input bool   InpUseDDKill        = true;
input double InpMaxDDPct         = 20.0;   // 净值高水位回撤上限（永久锁）
input bool   InpStopAfterDDLock = false; // ★false=评估口径(冷却棘轮) / true=交付口径(达上限即永久停) 
input int    InpDDCooldownMin = 1440;  // ★DD锁冷却分钟（>0=冷却后自动解锁；0=旧行为永久锁）
input bool   InpResetDDOnInit    = false;  // 仅人工复位用

input group "=== 交易时段过滤 ==="
input bool   InpUseSessionFilter = true;
input int    InpTradeStartHour   = 8;      // 服务器时间，交易起始小时
input int    InpTradeEndHour     = 21;     // 服务器时间，交易结束小时（含）
input bool   InpNoFridayLate     = true;   // 周五收盘前N小时不开新仓
input int    InpFridayStopHour   = 18;

input group "=== 杂项 ==="
input long   InpMagic            = 20260911;
input string InpRunTag           = "trend_core";
input bool   InpWriteAudit       = true;
input double InpDDMinDepthPct = 2.0;    // 回撤事件最小深度%（小于此视为噪声，不计入事件统计）
input double InpSlippagePoints   = 50;
// ★模拟真实网络延迟：读价 → Sleep(InpLatencyMs) → 用【新价】下单。
//   实测意义：0 延迟会系统性高估高频策略；300ms 更接近零售实盘。
input int    InpLatencyMs       = 300;   // 模拟下单延迟（毫秒）
input bool   InpVerboseLog       = false;

//==================== 精度参数锁定区 ====================
// ★铁律：这些决定"信号精度"的参数绝不参与寻优。
//   旧项目 6 次翻车全部源于优化器把它们压到边界；实测代价见文件头。
//   要改只能改源码，不许用 .set 覆盖成优化变量。
// 实际生效值 = 上面的 input（源码默认即为设计值），此处仅作声明与自检。

//==================== 全局状态 ====================
int      g_hFast = INVALID_HANDLE;
int      g_hSlow = INVALID_HANDLE;
int      g_hATR  = INVALID_HANDLE;

long     g_lastBarM5     = -1;
long     g_lastRVM1      = -1;
double   g_rvPct         = 0.0;

int      g_confirmUp     = 0;
int      g_confirmDown   = 0;
int      g_prevTrend     = 0;      // 1=多, -1=空, 0=无

// 仓位管理
ulong    g_ticket        = 0;
double   g_entryPrice    = 0.0;
double   g_initSL        = 0.0;
double   g_curSL         = 0.0;
double   g_bestPrice     = 0.0;
double   g_atrAtEntry    = 0.0;
double   g_riskMoney     = 0.0;

// 账户级风控
datetime g_curDay        = 0;
double   g_dayStartEquity= 0.0;
bool     g_dailyBlocked  = false;
double   g_peakEquity    = 0.0;
bool     g_ddLocked      = false;
datetime g_ddLockUntil = 0;      // ★DD 冷却解锁时间（0=当前未处于冷却）

// 统计
long     g_nTrades = 0, g_nWin = 0;
double   g_sumWin = 0.0, g_sumLoss = 0.0;
double   g_worstLoss = 0.0, g_bestWin = 0.0;

// 手数被拒原因计数（诊断用：定位小账户到底卡在哪一步）
long     g_lotRejTick = 0, g_lotRejNoOver = 0, g_lotRejCap = 0;

// 最近一次手数计算的详情（只读打印用）
double   g_lastPerLot = 0.0, g_lastRiskMoney = 0.0, g_lastCap = 0.0, g_lastMinLotRisk = 0.0;
double   g_lastStopDist = 0.0;
double   g_lastLatencySlip = 0.0;  // ★最近一次延迟造成的滑点（价格单位，>0=不利）
double   g_lastAtrDist = 0.0, g_lastStopsLevel = 0.0;
long     g_stopsLevelBumps = 0;

//==================== ★回撤事件统计（用户明确要求的指标）====================
// 用户要求："不要只看回撤，要看一年内回撤了几次、每次回撤多少" ——
//   这比"最大回撤"更有意义：最大回撤只描述最坏一次，而"次数 × 每次深度 × 恢复时间"
//   才决定实盘时会不会中途被震出去 / 心态崩掉 / 被强平。
// 做法：在线跟踪"回撤事件"(drawdown episode)：
//   从高水位开始 → 记录最低点 → 直到净值重新创高（恢复）为止，算一次完整事件。
int      g_ddEpisodes    = 0;      // 已恢复的事件数
double   g_ddSumPct      = 0.0;    // 已恢复事件的深度总和
double   g_ddWorstPct    = 0.0;    // 最深的一次
double   g_ddSumRecoverH = 0.0;    // 恢复用时总和（小时）
int      g_ddOpenCount   = 0;      // 未恢复（含测试结束时仍在水下）
int      g_ddOver10 = 0, g_ddOver15 = 0, g_ddOver20 = 0, g_ddOver25 = 0, g_ddOver30 = 0;

// 当前事件状态
bool     g_epActive      = false;
datetime g_epStart       = 0;
double   g_epPeakEq      = 0.0;
double   g_epTroughEq    = 0.0;
datetime g_epTroughTime  = 0;
double   g_epTroughPct   = 0.0;    // 事件内最深百分比
double   g_epTroughUsd   = 0.0;

// 自然月抽样（"一年内几次"按月看最直观）
int      g_curMon        = -1;
double   g_monStartEq    = 0.0;
double   g_monPeakEq     = 0.0;
double   g_monTroughEq   = 0.0;
double   g_monWorstPct   = 0.0;
int      g_monSamples    = 0;

int      g_ddFh = INVALID_HANDLE;
int      g_monFh = INVALID_HANDLE;

void DDEpisodeLog(const string kind, double recoverH)
{
   if(g_ddFh == INVALID_HANDLE) return;
   FileWrite(g_ddFh,
             InpRunTag, kind,
             TimeToString(g_epStart, TIME_DATE|TIME_SECONDS),
             TimeToString(g_epTroughTime, TIME_DATE|TIME_SECONDS),
             TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
             DoubleToString(g_epPeakEq, 2),
             DoubleToString(g_epTroughEq, 2),
             DoubleToString(g_epTroughUsd, 2),
             DoubleToString(g_epTroughPct, 2),
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

void DDStartEpisode(datetime now, double eq)
{
   g_epActive     = true;
   g_epStart      = now;
   g_epPeakEq     = (g_peakEquity > eq ? g_peakEquity : eq);
   if(g_epPeakEq <= 0.0) g_epPeakEq = eq;
   g_epTroughEq   = eq;
   g_epTroughTime = now;
   g_epTroughPct  = 0.0;
   g_epTroughUsd  = 0.0;
}

void DDMonthRoll(datetime now)
{
   MqlDateTime t; TimeToStruct(now, t);
   int ym = t.year * 12 + t.mon;
   if(ym == g_curMon) return;
   if(g_curMon > 0 && g_monSamples > 0 && g_monFh != INVALID_HANDLE)
   {
      int y = (g_curMon - 1) / 12;
      int m = g_curMon - y * 12;
      FileWrite(g_monFh, InpRunTag, StringFormat("%04d-%02d", y, m),
                DoubleToString(g_monStartEq, 2), DoubleToString(g_monPeakEq, 2),
                DoubleToString(g_monTroughEq, 2), DoubleToString(g_monWorstPct, 2),
                (string)g_monSamples);
      FileFlush(g_monFh);
   }
   g_curMon      = ym;
   g_monStartEq  = AccountInfoDouble(ACCOUNT_EQUITY);
   g_monPeakEq   = g_monStartEq;
   g_monTroughEq = g_monStartEq;
   g_monWorstPct = 0.0;
   g_monSamples  = 0;
}

void DDTrack(datetime now, double eq)
{
   DDMonthRoll(now);

   g_monSamples++;
   if(eq > g_monPeakEq) g_monPeakEq = eq;
   if(eq < g_monTroughEq) g_monTroughEq = eq;
   if(g_monPeakEq > 0.0)
   {
      double mp = (g_monPeakEq - g_monTroughEq) / g_monPeakEq * 100.0;
      if(mp > g_monWorstPct) g_monWorstPct = mp;
   }

   if(!g_epActive) { DDStartEpisode(now, eq); return; }

   if(eq > g_epPeakEq)
   {
      if(g_epTroughPct >= InpDDMinDepthPct) DDCloseEpisode();
      else g_epActive = false;               // 深度不够，当噪声丢弃
      DDStartEpisode(now, eq);
      return;
   }

   if(eq < g_epTroughEq)
   {
      g_epTroughEq   = eq;
      g_epTroughTime = now;
      if(g_epPeakEq > 0.0)
      {
         g_epTroughPct = (g_epPeakEq - eq) / g_epPeakEq * 100.0;
         g_epTroughUsd = g_epPeakEq - eq;
      }
   }
}
// 审计
int      g_auditFh = INVALID_HANDLE;

//==================== 前置声明 ====================
// (MQL5 不做两遍扫描，被 OnTick 用到的函数必须在前面可见)
double ContractPerLot();
double MoneyPerPricePerLot();
bool   HasPosition();
bool   HasPosition();
bool   ClosePosition(string reason);
bool   ModifySL(double newSL);
void   ManageOpenPosition();
void   DumpPositions(string tag);
bool   EnsureIndicators();
int    CountMyPositions();
ulong  FindMyTicket();
void   RefreshAccountRisk();
double PosTP();
long   PosType();
double PosOpen();
string ExitFhName()
{
   return "dshtrend/" + InpRunTag + "/trades.csv";
}
string ExitDirName()
{
   return "dshtrend/" + InpRunTag;
}

// (移除 Point()/Digits() 包装函数：_Point 与 _Digits 是 MQL5 内置全局变量，直接用即可；
//  自定义同名函数会与内置冲突 —— 编译报 error 271 'override system function')

double NormPrice(double p) { return NormalizeDouble(p, _Digits); }

// ★成交模式：必须匹配品种支持的模式，否则 order send 会被拒。
//   不同券商/品种支持 FOK 或 IOC（或两者），这里按 SYMBOL_FILLING_MODE 动态选。
ENUM_ORDER_TYPE_FILLING PickFilling()
{
   long mode = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if((mode & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   if((mode & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

// 手数对齐到 volume_step
double AlignLot(double lot)
{
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   if(vstep <= 0.0) vstep = 0.01;
   // ★修复（2026-09-11，GPT-子审 MSG-006 指出 + 我实测确认）：
   //   原来用 MathFloor(lot/vstep + 0.5)（=四舍五入）。实测后果：
   //     风险预算 4.50 USD（300×1.5%），理想手数 0.0245 → 被抬到 0.03
   //     → 实际风险 15.69 USD = 超预算 248%。
   //   取整方向必须向下（floor），宁可少开也不能超风险。
   lot = MathFloor(lot / vstep + 1e-9) * vstep;
   if(lot < vmin) lot = vmin;
   if(vmax > 0.0 && lot > vmax) lot = vmax;
   if(InpMaxLot > 0.0 && lot > InpMaxLot) lot = InpMaxLot;
   // 规范化小数位
   int vd = 0; double s = vstep;
   while(s < 1.0 && vd < 8) { s *= 10.0; vd++; }
   return NormalizeDouble(lot, vd);
}

// ★核心：把"止损价格距离"换算成"每手亏损多少钱"
//   用 TICK_VALUE/TICK_SIZE（每手每tick的账户货币价值），这是 MT5 的正道。
//   旧项目把 TICK_VALUE 当成"每手每点的美元价值"直接用，在 tick_size != point
//   的品种上会错；这里显式做除法。
// ★★ 每手每单位价格变动的账户货币价值 —— 两个口径，按"报价货币是否等于账户货币"选
//
// 实测结论（决定了小账户能不能交易）：
//   ① 报价货币 == 账户货币（黄金 XAUUSD、比特币 BTCUSD）：
//        盈亏 = contract_size × 手数 × Δ价格   → 每手每1.0价格 = contract_size
//      验证：BTCUSDm 0.01手 112281.24 → 114066.23（Δ=1784.99）
//            实测 +17.69 ≈ 1 × 0.01 × 1784.99 ✅
//      验证：XAUUSDm 0.01手 Δ$1 = $1 ✅
//   ② 报价货币 != 账户货币（美元兑日元 USDJPY）需要即期汇率换算，但
//      **测试器给这类品种的 TICK_VALUE 是错的**：实测真实 USDJPYm 的 tv
//      从 0.695 漂到 14355，一笔本该 +$0.64 的交易变成 −$1511（差 143 倍）。
//      → 结论：**USDJPY 在本测试环境下不可交易，不要用它做研究。**
//
// 因此优先用口径①；只有确实需要货币换算时才退回 TICK_VALUE，
// 并对 TICK_VALUE 做合理性校验（防止漂移成垃圾值）。
double MoneyPerPricePerLot()
{
   double cs   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
   double bid  = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double pt   = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   string prof = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_PROFIT);
   string acc  = AccountInfoString(ACCOUNT_CURRENCY);

   if(cs > 0.0)
   {
      if(prof == acc)
         return cs;                       // 口径①：无换算

      double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tv > 0.0 && ts > 0.0 && bid > 0.0)
      {
         double ratio    = tv / ts;
         double expected = cs / bid;
         if(ratio > expected / 50.0 && ratio < expected * 50.0)
            return ratio;
         PrintFormat("[%s] TICK_VALUE 异常(tv=%s ts=%s ratio=%s 期望≈%s)，改用合约口径",
                     InpRunTag, DoubleToString(tv,6), DoubleToString(ts,8),
                     DoubleToString(ratio,4), DoubleToString(expected,4));
         return expected;
      }
      return (bid > 0.0) ? cs / bid : 0.0;
   }
   double tv2 = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double ts2 = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv2 > 0.0 && ts2 > 0.0 && pt > 0.0) return tv2 / ts2;
   return 0.0;
}
double LossPerLotForDistance(double priceDist)
{
   double mpp = MoneyPerPricePerLot();
   if(mpp <= 0.0) return 0.0;
   return priceDist * mpp;    // 每 1 手
}

// 按风险百分比反推手数；返回 0 表示不可行（所需手数低于券商下限）
double LotForRisk(double stopDistPrice, double &riskUsed)
{
   riskUsed = 0.0;
   double base = InpUseEquityForRisk ? AccountInfoDouble(ACCOUNT_EQUITY)
                                     : AccountInfoDouble(ACCOUNT_BALANCE);
   double riskMoney = base * InpRiskPct / 100.0;
   double perLot = LossPerLotForDistance(stopDistPrice);
   if(perLot <= 0.0)
   {
      g_lotRejTick++;
      return 0.0;
   }

   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lot = riskMoney / perLot;
   g_lastPerLot = perLot; g_lastRiskMoney = riskMoney;
   g_lastCap = base * InpMinLotMaxRiskPct / 100.0;
   g_lastMinLotRisk = vmin * perLot;
   g_lastStopDist = stopDistPrice;

   if(lot < vmin)
   {
      // ★小账户现实：算出来比最小手还小。
      //   两种处置：
      //     InpAllowMinLotOvershoot=false → 跳过该信号（严格不超风险预算，但会漏掉大量机会）
      //     InpAllowMinLotOvershoot=true  → 按最小手交易，但只接受
      //        "最小手风险 ≤ 净值 × InpMinLotMaxRiskPct%" 的信号
      //   （后者是小账户唯一能实际跑起来的模式：0.01 手是硬地板，无法再细分）
      if(!InpAllowMinLotOvershoot) { g_lotRejNoOver++; return 0.0; }

      double minLotRisk = vmin * perLot;
      double cap = base * InpMinLotMaxRiskPct / 100.0;
      if(minLotRisk > cap) { g_lotRejCap++; return 0.0; }   // 最小手也太贵 → 放弃这个信号

      lot = vmin;
      riskUsed = minLotRisk;
      return lot;
   }

   // ★修复：取整后必须按【最终手数】重算风险并复核
   //   （原代码只对"低于最小手"的分支复核，普通分支取整后没复核）
   lot = AlignLot(lot);
   riskUsed = lot * perLot;

   // 取整（向下）+ 最小手兜底后，风险可能仍超预算 → 再夹一次
   if(riskUsed > riskMoney)
   {
      // 试着降低一档手数
      double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
      if(vstep <= 0.0) vstep = 0.01;
      double lower = NormalizeDouble(lot - vstep, 8);
      if(lower >= vmin)
      {
         lot = lower;
         riskUsed = lot * perLot;
      }
      // 若已经是最小手仍超预算，则看是否在最小手豁免范围内
      if(riskUsed > riskMoney)
      {
         if(!InpAllowMinLotOvershoot || lot > vmin + 1e-9) { g_lotRejCap++; return 0.0; }
         double cap = base * InpMinLotMaxRiskPct / 100.0;
         if(riskUsed > cap) { g_lotRejCap++; return 0.0; }
      }
   }
   return lot;
}

// ★新周期判定：不要用 iTime(_Symbol, tf, 0)
//   实测：在测试器里对自定义品种取大周期当前 bar 时间会返回 0，
//   导致 IsNewBar 永远返回 false、EA 一笔都不开（H1/H4 全 0 成交）。
//   改成用服务器时间算"桶编号"，完全不依赖任何周期序列。
bool IsNewBucket(ENUM_TIMEFRAMES tf, long &store)
{
   int tfm = TFMinutes(tf);
   if(tfm <= 0) return false;
   long bucket = (long)TimeCurrent() / ((long)tfm * 60);
   if(bucket == store) return false;
   store = bucket;
   return true;
}

bool IsNewBar(ENUM_TIMEFRAMES tf, datetime &store)
{
   datetime t = iTime(_Symbol, tf, 0);
   if(t <= 0) return false;
   if(t == store) return false;
   store = t;
   return true;
}

//==================== 波动率（沿用旧项目验证过的 RMS 口径）====================
// G_RVRatio = 100 × RMS(1分钟收盘差) / 现价
bool CalcRV(double &rvPct)
{
   rvPct = 0.0;
   int n = MathMax(2, InpRVWindowMinutes);
   double closes[];
   ArraySetAsSeries(closes, true);
   if(CopyClose(_Symbol, PERIOD_M1, 1, n + 1, closes) < n + 1) return false;

   double pt = _Point;
   if(pt <= 0.0) return false;

   double sumSq = 0.0;
   for(int i = 0; i < n; i++)
   {
      double d = (closes[i] - closes[i + 1]) / pt;
      sumSq += d * d;
   }
   double rvPoints = MathSqrt(sumSq / n);
   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0) return false;

   rvPct = 100.0 * (rvPoints * pt) / price;
   return true;
}

//==================== 时段过滤 ====================
bool SessionAllowsOpen()
{
   if(!InpUseSessionFilter) return true;
   MqlDateTime t; TimeToStruct(TimeCurrent(), t);
   if(t.day_of_week == 0 || t.day_of_week == 6) return false;   // 周末
   if(InpNoFridayLate && t.day_of_week == 5 && t.hour >= InpFridayStopHour) return false;
   if(InpTradeStartHour <= InpTradeEndHour)
      return (t.hour >= InpTradeStartHour && t.hour <= InpTradeEndHour);
   // 跨午夜
   return (t.hour >= InpTradeStartHour || t.hour <= InpTradeEndHour);
}

//==================== 指标 ====================
double EMA(int handle, int shift)
{
   double buf[];
   ArraySetAsSeries(buf, true);
   if(CopyBuffer(handle, 0, shift, 1, buf) < 1) return 0.0;
   return buf[0];
}

//==================== 账户级风控 ====================
void RefreshAccountRisk()
{
   datetime now = TimeCurrent();
   MqlDateTime t; TimeToStruct(now, t);
   t.hour = 0; t.min = 0; t.sec = 0;
   datetime day = StructToTime(t);

   if(day != g_curDay)
   {
      g_curDay = day;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      g_dailyBlocked = false;
   }

   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq > g_peakEquity) g_peakEquity = eq;

   DDTrack(now, eq);   // ★回撤事件跟踪（一年几次 / 每次多深 / 恢复多久）

   if(InpUseDailyStop && g_dayStartEquity > 0.0)
   {
      double dd = (g_dayStartEquity - eq) / g_dayStartEquity * 100.0;
      if(dd >= InpDailyLossPct)
      {
         if(!g_dailyBlocked)
            PrintFormat("[%s] 日内亏损达上限 %.2f%% (起始净值 %.2f 现 %.2f)，今日停止开新仓",
                        InpRunTag, dd, g_dayStartEquity, eq);
         g_dailyBlocked = true;
      }
   }

   if(InpUseDDKill && g_peakEquity > 0.0)
   {
      double dd = (g_peakEquity - eq) / g_peakEquity * 100.0;

      // ★★冷却解锁 = 分段棘轮（2026-09-11 修正）
      //   旧永久锁的问题：账户越赚→高水位越高→越容易触发→成功即自杀。
      //   但"只放行不重置"也不行：高水位仍指向历史峰值，解锁后立刻会再次触发，
      //   等于"每 24 小时放行一瞬间"的循环刹车，回撤照样能到 96%。
      //   正确做法：解锁时把高水位【重置到当前净值】——
      //     于是 InpMaxDDPct 变成"从每个阶段高点起算的有界回撤上限"，
      //     且会在净值恢复后自动建立新的、更高的阶段高点。
      //   ⚠️ 注意：这仍不是"全程回撤 ≤ InpMaxDDPct"的保证。
      //     账户从峰值 H 跌到 H*(1-c) 后，只要在超过冷却时间后继续下跌，
      //     就会进入"跌破→冷却→再跌破"的阶梯下降，累计回撤可以超过 c。
      //     真正确立上限需要 InpStopAfterDDLock=true（达到上限后不再交易）。
      if(g_ddLocked && InpDDCooldownMin > 0 && g_ddLockUntil > 0 && now >= g_ddLockUntil)
      {
         g_ddLocked = false;
         g_ddLockUntil = 0;
         g_peakEquity = eq;          // ★重置阶段高水位（棘轮）
         PrintFormat("[%s] ★DD冷却结束，建立新阶段高点 %.2f，恢复交易", InpRunTag, eq);
      }

      // ★交付口径：达到回撤上限后彻底停止（真正的回撤封顶）
      if(InpStopAfterDDLock && g_peakEquity > 0.0 && dd >= InpMaxDDPct)
      {
         if(!g_ddLocked)
         {
            g_ddLocked = true;
            PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，按交付口径【永久停止】（峰值 %.2f 现 %.2f）",
                        InpRunTag, dd, g_peakEquity, eq);
            ClosePosition("dd_kill");
         }
         return;    // 不再进入下面的冷却逻辑
      }

      if(dd >= InpMaxDDPct && !g_ddLocked)
      {
         g_ddLocked = true;
         if(InpDDCooldownMin > 0)
         {
            g_ddLockUntil = now + (datetime)(InpDDCooldownMin * 60);
            PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，冷却 %d 分钟后解锁（峰值 %.2f 现 %.2f）",
                        InpRunTag, dd, InpDDCooldownMin, g_peakEquity, eq);
         }
         else
            PrintFormat("[%s] ★净值回撤 %.2f%% 达上限，永久锁（InpDDCooldownMin=0）", InpRunTag, dd);
         ClosePosition("dd_kill");
      }
   }
}

//==================== 持仓管理 ====================
// 统计本 EA 的持仓数量（按 magic + symbol）
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

// 找出本 EA 的持仓 ticket（取第一个）
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

bool HasPosition()
{
   // ★不能只靠缓存的 g_ticket：仓位可能被券商侧 SL/TP 平掉，
   //   那样 g_ticket 会失效，而导致 EA 重复开仓。
   //   每次都按 magic 重新查一遍，并用查到的结果纠正 g_ticket。
   int n = CountMyPositions();
   if(n == 0) { g_ticket = 0; return false; }

   if(n > 1 && InpVerboseLog)
      PrintFormat("[%s] 警告：发现 %d 个本 EA 持仓（应为 1）", InpRunTag, n);

   if(g_ticket == 0 || !PositionSelectByTicket(g_ticket))
   {
      ulong tk = FindMyTicket();
      if(tk == 0) { g_ticket = 0; return false; }
      // 说明这个仓位不是我们记录的（例如被 SL 平掉后又有遗留）→ 重新绑定
      if(g_ticket != tk && InpVerboseLog)
         PrintFormat("[%s] 重新绑定持仓 ticket %I64u", InpRunTag, tk);
      g_ticket = tk;
   }
   return true;
}

//+------------------------------------------------------------------+
//| 纯诊断：打印 PositionsTotal 与每个持仓的字段，定位"看不到仓位"的原因   |
//+------------------------------------------------------------------+
void DumpPositions(string tag)
{
   int total = PositionsTotal();
   PrintFormat("[%s][DUMP %s] PositionsTotal=%d  我的magic=%I64d  symbol=%s",
               InpRunTag, tag, total, InpMagic, _Symbol);
   for(int i = 0; i < total; i++)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) { PrintFormat("   [%d] PositionGetTicket=0 err=%d", i, GetLastError()); continue; }
      PrintFormat("   [%d] ticket=%I64u symbol='%s' magic=%I64d type=%I64d vol=%.2f",
                  i, tk,
                  PositionGetString(POSITION_SYMBOL),
                  PositionGetInteger(POSITION_MAGIC),
                  PositionGetInteger(POSITION_TYPE),
                  PositionGetDouble(POSITION_VOLUME));
   }
}

// 同步持仓跟踪状态（每次有新仓/检测到异常时调用）
void SyncPositionTracking(double atr)
{
   if(!HasPosition()) return;
   g_entryPrice = PosOpen();
   g_initSL     = PosSL();
   g_curSL      = g_initSL;
   g_bestPrice  = g_entryPrice;
   if(atr > 0.0) g_atrAtEntry = atr;
}

long PosType() { return PositionGetInteger(POSITION_TYPE); }
double PosOpen() { return PositionGetDouble(POSITION_PRICE_OPEN); }
double PosSL()   { return PositionGetDouble(POSITION_SL); }
double PosTP()   { return PositionGetDouble(POSITION_TP); }
double PosVol()  { return PositionGetDouble(POSITION_VOLUME); }

//==================== 成交跟踪（★关键修正）====================
// 教训：EA 把 SL 设在券商侧托管，仓位可能被 **券商侧 SL** 平掉，
//       此时 EA 的平仓函数根本不会被调用 → 用"自己的计数器 + 自己的平仓函数"
//       统计盈亏会严重漏记。实测：报告 72 笔，我的审计只有 4 笔（漏了 94%）。
// 正确做法：用 MT5 的**成交历史（HistoryDeal）**统计 —— 让终端给出真实盈亏
//       和真实出场原因（deal.reason 能区分 SL / TP / 手动 / 强平）。
// 这也正是旧项目 eva 家族 OnTradeTransaction + deal.reason 的思路（对的，继承）。

double g_realizedPnL = 0.0;   // 本 EA 累计已实现盈亏（来自终端，权威）
long   g_dealsOut    = 0;

string DealReasonStr(long r)
{
   switch((int)r)
   {
      case DEAL_REASON_SL:       return "sl";
      case DEAL_REASON_TP:       return "tp";
      case DEAL_REASON_SO:       return "stopout";
      case DEAL_REASON_EXPERT:   return "expert";
      case DEAL_REASON_CLIENT:   return "client";
      case DEAL_REASON_MOBILE:   return "mobile";
      case DEAL_REASON_WEB:      return "web";
      case DEAL_REASON_ROLLOVER: return "rollover";
      case DEAL_REASON_VMARGIN:  return "variation_margin";
      case DEAL_REASON_SPLIT:    return "split";
   }
   return "other";
}

void RecordExitDeal(ulong dealTicket)
{
   if(!HistoryDealSelect(dealTicket)) return;
   if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;

   long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY) return;

   double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                 + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                 + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
   double price  = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
   double vol    = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
   long   reason = HistoryDealGetInteger(dealTicket, DEAL_REASON);
   // ★修复（2026-09-11，GPT-子审 MSG-006 指出）：ClosePosition() 主动平仓时,
   //   DEAL_REASON 恒为 DEAL_REASON_EXPERT，导致审计里 tp/trend_exit/dd_kill 全部
   //   退化成 "expert"，归因分析失真。改为优先解析我们自己在 comment 里写的白名单标签。
   string reasonStr = "";
   {
      string cmt = HistoryDealGetString(dealTicket, DEAL_COMMENT);
      if(StringFind(cmt, "dd_kill")     >= 0) reasonStr = "dd_kill";
      else if(StringFind(cmt, "trend_exit") >= 0) reasonStr = "trend_exit";
      else if(StringFind(cmt, "daily_stop") >= 0) reasonStr = "daily_stop";
      else if(StringFind(cmt, "time")       >= 0) reasonStr = "time";
      else if(StringFind(cmt, "tp")         >= 0) reasonStr = "tp";
      else if(StringFind(cmt, "trail")      >= 0) reasonStr = "trail";
      else reasonStr = DealReasonStr(reason);   // 服务器侧 sl/tp/stopout 保持权威
   }
   datetime t    = (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
   long   dtype  = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
   int    dir    = (dtype == DEAL_TYPE_SELL) ? 1 : -1;   // 出场是卖出 → 原仓为多

   g_realizedPnL += profit;
   g_dealsOut++;
   g_nTrades++;
   if(profit > 0.0) { g_nWin++; g_sumWin += profit; if(profit > g_bestWin) g_bestWin = profit; }
   else             { g_sumLoss += profit; if(profit < g_worstLoss) g_worstLoss = profit; }

   if(g_auditFh != INVALID_HANDLE)
   {
      FileWrite(g_auditFh,
                InpRunTag, _Symbol,
                TimeToString(t, TIME_DATE|TIME_SECONDS),
                (string)dir,
                DoubleToString(g_entryPrice, _Digits),
                DoubleToString(price, _Digits),
                DoubleToString(vol, 2),
                DoubleToString(profit, 2),
                DoubleToString(g_riskMoney, 2),
                DoubleToString(g_atrAtEntry, _Digits),
                reasonStr);
      FileFlush(g_auditFh);
   }

   if(InpVerboseLog)
      PrintFormat("[%s] EXIT %s dir=%d vol=%.2f price=%.3f pnl=%.2f 累计=%.2f",
                  InpRunTag, DealReasonStr(reason), dir, vol, price, profit, g_realizedPnL);

   g_ticket = 0; g_curSL = 0.0; g_bestPrice = 0.0;
}

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      RecordExitDeal(trans.deal);
}

void AuditTrade(int dir, double entry, double exitPx, double vol,
                double pnl, double riskMoney, string reason, double atr)
{
   // 保留此函数仅为兼容；统计现在统一由 RecordExitDeal（成交历史）负责，
   // 避免"手动平仓"与"券商侧止损平仓"两条路径重复计数或漏计。
   return;
}

bool ClosePosition(string reason)
{
   if(!HasPosition()) return false;

   int    dir  = (int)PosType();
   double vol  = PosVol();
   double entry= PosOpen();
   double atr  = g_atrAtEntry;

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action   = TRADE_ACTION_DEAL;
   req.symbol   = _Symbol;
   req.position = g_ticket;
   req.volume   = vol;
   req.deviation= (ulong)InpSlippagePoints;
   req.magic    = InpMagic;
   req.comment  = "close_" + reason;
   req.comment  = "close_" + reason;
   // ★平仓同样加延迟（实盘中平仓指令也要走网络）
   if(InpLatencyMs > 0) Sleep(InpLatencyMs);
   req.type     = (dir == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.type_filling = PickFilling();
   req.price    = (dir == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                             : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      PrintFormat("[%s] 平仓失败 reason=%s retcode=%d err=%d",
                  InpRunTag, reason, res.retcode, GetLastError());
      return false;
   }

   // 统计与审计统一由 OnTradeTransaction → RecordExitDeal（读成交历史）完成，
   // 这里只负责发出平仓指令，避免两条路径重复计数。
   if(InpVerboseLog)
      PrintFormat("[%s] CLOSE-REQUEST %s dir=%d vol=%.2f @%.3f",
                  InpRunTag, reason, dir, vol, res.price);

   g_ticket = 0; g_curSL = 0.0; g_bestPrice = 0.0;
   return true;
}

double ContractPerLot()
{
   // 每手每 1 单位价格变动的账户货币价值
   return LossPerLotForDistance(1.0);
}

bool OpenPosition(int dir, double stopDistPrice, double atr, string reason)
{
   double riskUsed = 0.0;
   double lot = LotForRisk(stopDistPrice, riskUsed);
   if(lot <= 0.0)
   {
      if(InpVerboseLog)
         PrintFormat("[%s] 跳过信号：最小手 %.2f 已超风险预算（止损距离 %.3f）",
                     InpRunTag, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN), stopDistPrice);
      return false;
   }

   // ★★模拟真实网络延迟（零售实盘约 200-400ms）
   //   机制：先读价 → Sleep(InpLatencyMs) → 重新读价 → 用新价下单。
   //   为什么必须做：0 延迟回测会系统性高估高频策略；延迟期间价格会移动，
   //   而止损是相对【成交价】设的，所以延迟会同时改变入场价与止损位。
   double price = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(InpLatencyMs > 0)
   {
      Sleep(InpLatencyMs);
      double p2 = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                            : SymbolInfoDouble(_Symbol, SYMBOL_BID);
      if(p2 > 0.0)
      {
         g_lastLatencySlip = (p2 - price) * ((dir > 0) ? 1.0 : -1.0);  // >0 = 不利滑点
         price = p2;
      }
   }
   double sl = (dir > 0) ? price - stopDistPrice : price + stopDistPrice;

   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action    = TRADE_ACTION_DEAL;
   req.symbol    = _Symbol;
   req.volume    = lot;
   req.type      = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price     = price;
   req.sl        = NormPrice(sl);
   req.deviation = (ulong)InpSlippagePoints;
   req.magic     = InpMagic;
   req.comment   = "open_" + reason;
   req.type_filling = PickFilling();

   if(!OrderSend(req, res) || (res.retcode != TRADE_RETCODE_DONE &&
                               res.retcode != TRADE_RETCODE_PLACED))
   {
      PrintFormat("[%s] 开仓失败 retcode=%d err=%d", InpRunTag, res.retcode, GetLastError());
      return false;
   }

   // 取回真实 ticket
   // ★无条件导出一次持仓视图，用来定位"开仓后看不到仓位"的真因
   {
      static int dbgCount = 0;
      if(dbgCount < 8) { DumpPositions("after_send"); dbgCount++; }
   }
   g_ticket = FindMyTicket();
   if(g_ticket == 0)
   {
      PrintFormat("[%s] ★开仓后找不到持仓（positions=%d）", InpRunTag, CountMyPositions());
      return false;
   }

   g_entryPrice = PosOpen();
   g_initSL     = PosSL();
   g_curSL      = g_initSL;
   g_bestPrice  = g_entryPrice;
   g_atrAtEntry = atr;
   g_riskMoney  = riskUsed;

   if(InpVerboseLog)
      PrintFormat("[%s] OPEN %s dir=%d lot=%.2f price=%.3f sl=%.3f risk=%.2f (%.2f%%)",
                  InpRunTag, reason, dir, lot, g_entryPrice, g_curSL,
                  riskUsed, riskUsed / AccountInfoDouble(ACCOUNT_EQUITY) * 100.0);
   return true;
}

//==================== 趋势信号（改用原生多周期视图）====================
// 返回 1=做多信号, -1=做空信号, 0=无
int EvalSignal(double &atr, string &why)
{
   atr = 0.0; why = "";

   TFView v;
   if(!GetView(InpTrendTF, InpBreakoutBars, v)) { why = "no_view"; return 0; }
   atr = v.atr;
   if(atr <= 0.0) { why = "atr_zero"; return 0; }

   bool breakoutUp = true, breakoutDown = true;
   if(InpBreakoutBars > 0)
   {
      breakoutUp   = (v.close1 > v.hiPrior);
      breakoutDown = (v.close1 < v.loPrior);
   }

   bool up   = (v.fast > v.slow) && (v.slow > v.slowOld) && breakoutUp;
   bool down = (v.fast < v.slow) && (v.slow < v.slowOld) && breakoutDown;

   // 连续确认
   if(InpUseTrendConfirm && InpTrendConfirmBars > 1)
   {
      if(up)   g_confirmUp   = MathMin(g_confirmUp + 1,   1000);
      else     g_confirmUp   = 0;
      if(down) g_confirmDown = MathMin(g_confirmDown + 1, 1000);
      else     g_confirmDown = 0;
      if(up   && g_confirmUp   < InpTrendConfirmBars) { why = "confirm_up";   return 0; }
      if(down && g_confirmDown < InpTrendConfirmBars) { why = "confirm_down"; return 0; }
   }

   if(up)   { why = "trend_up";   return 1; }
   if(down) { why = "trend_down"; return -1; }
   why = "no_signal";
   return 0;
}

// 趋势是否已反向（用于 ExitOnCross）
int TrendDirection()
{
   TFView v;
   if(!GetView(InpTrendTF, 1, v)) return 0;
   if(v.fast > v.slow) return 1;
   if(v.fast < v.slow) return -1;
   return 0;
}

//==================== 原生多周期计算（★关键设计）====================
// 为什么不用 iMA/iATR？
//   实测：在策略测试器里对**自定义品种**调用 iMA(_Symbol, PERIOD_H1, ...)
//   会稳定失败，err=4805（ERR_INDICATOR_CANNOT_CREATE）——测试器不为
//   这类品种同步大周期序列，于是整个 EA 一笔都开不出来。
// 解决：只用 M1 序列（测试器一定提供），**自己合成大周期 bar 并算 EMA/ATR**。
//   好处：①不依赖测试器的多周期支持，任何周期都能用；
//         ②每个 tick 都是"当前最新值"，没有多周期同步延迟；
//         ③数学完全自洽、可审计。

// ★★ ENUM_TIMEFRAMES 的真实取值（实测，务必记住）
//   PERIOD_M1=1  M5=5  M15=15  M30=30   ← 分钟类正好等于分钟数
//   PERIOD_H1=16385  H2=16386  H3=16387  H4=16388  H6=16390  H8=16392  H12=16396
//   PERIOD_D1=16408   W1=32769   MN1=49153   PERIOD_CURRENT=0
//   我第一版按"小时数×60"写 switch（H1→60），结果 TFMinutes 返回 0
//   → 新周期判定永远 false → H1/H4 **一笔都没开**，而且不报任何错。
//   教训：不要把枚举当成数值用。
int TFMinutes(ENUM_TIMEFRAMES tf)
{
   if(tf == PERIOD_CURRENT) tf = (ENUM_TIMEFRAMES)Period();
   int v = (int)tf;
   if(v <= 0) return 0;

   if(v < 16385) return v;                    // 1..30 → 分钟类，值即分钟数

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
   if(v >= 16398 && v < 32769) return 1440;   // D1 系列
   if(v >= 32769 && v < 49153) return 10080;  // W1
   return 43200;                              // MN1
}
// 把 M1 序列按 tf 分钟聚合成 OHLC bar 数组（index 0 = 最早，最后一个是"未收盘"的当前 bar）
int BuildAggBars(ENUM_TIMEFRAMES tf, int wantBars,
                 double &o[], double &h[], double &l[], double &c[])
{
   int tfm = TFMinutes(tf);
   if(tfm <= 1 || wantBars < 2) return 0;
   int needM1 = tfm * (wantBars + 2);

   MqlRates m1[];
   ArraySetAsSeries(m1, false);   // ★按时间正序，便于从头聚合
   ResetLastError();
   int got = CopyRates(_Symbol, PERIOD_M1, 0, needM1, m1);
   g_diagLastM1 = got;
   if(got < tfm * 2)
   {
      return 0;
   }

   ArrayResize(o, 0); ArrayResize(h, 0); ArrayResize(l, 0); ArrayResize(c, 0);

   long curBucket = -1;
   double bo = 0, bh = 0, bl = 0, bc = 0;
   bool open = false;

   for(int i = 0; i < got; i++)
   {
      long bucket = (long)m1[i].time / ((long)tfm * 60);
      if(!open || bucket != curBucket)
      {
         if(open)
         {
            int n = ArraySize(c);
            ArrayResize(o, n + 1); ArrayResize(h, n + 1);
            ArrayResize(l, n + 1); ArrayResize(c, n + 1);
            o[n] = bo; h[n] = bh; l[n] = bl; c[n] = bc;
         }
         curBucket = bucket;
         bo = m1[i].open; bh = m1[i].high; bl = m1[i].low; bc = m1[i].close;
         open = true;
      }
      else
      {
         if(m1[i].high > bh) bh = m1[i].high;
         if(m1[i].low  < bl) bl = m1[i].low;
         bc = m1[i].close;
      }
   }
   if(open)
   {
      int n = ArraySize(c);
      ArrayResize(o, n + 1); ArrayResize(h, n + 1);
      ArrayResize(l, n + 1); ArrayResize(c, n + 1);
      o[n] = bo; h[n] = bh; l[n] = bl; c[n] = bc;
   }
   return ArraySize(c);
}

// 在收盘价数组上算 EMA（返回"已完成 bar"的 EMA 值；shift=0 表示最后一个已完成 bar）
// 注意：数组最后一个元素是未收盘 bar，所以要跳过它
double EMAOnArray(const double &arr[], int period, int shift)
{
   int n = ArraySize(arr);
   int lastClosed = n - 1;
   if(lastClosed < period + shift) return 0.0;

   int endIdx = lastClosed - shift;      // 要算到的那个 bar 的下标
   double k = 2.0 / (period + 1.0);

   // 以第一个 bar 的收盘价作为 EMA 起点，向前推进到 endIdx
   double ema = arr[0];
   for(int i = 1; i <= endIdx; i++)
      ema = arr[i] * k + ema * (1.0 - k);
   return ema;
}

// Wilder ATR（在聚合 bar 上，返回最后一个已完成 bar 的 ATR）
double ATRFromBars(const double &h[], const double &l[], const double &c[],
                   int period, int shift)
{
   int n = ArraySize(c);
   int lastClosed = n - 1;
   if(lastClosed < period + shift + 1) return 0.0;
   int endIdx = lastClosed - shift;

   double atr = 0.0;
   // 初始 ATR = 前 period 根 TR 的均值
   for(int i = 1; i <= period; i++)
      atr += MathMax(h[i] - l[i],
                     MathMax(MathAbs(h[i] - c[i - 1]), MathAbs(l[i] - c[i - 1])));
   atr /= period;

   for(int i = period + 1; i <= endIdx; i++)
   {
      double tr = MathMax(h[i] - l[i],
                          MathMax(MathAbs(h[i] - c[i - 1]), MathAbs(l[i] - c[i - 1])));
      atr = (atr * (period - 1) + tr) / period;
   }
   return atr;
}

//==================== 多周期快照 ====================
// 诊断计数（定位"某周期 0 成交"的真因；统计见 OnDeinit）
int g_diagCalls=0, g_diagNoM1=0, g_diagFewBars=0, g_diagNoBreak=0, g_diagBadEma=0, g_diagOK=0;
int g_diagLastM1=0, g_diagLastAgg=0;
double g_diagLastClose=0, g_diagLastFast=0, g_diagLastSlow=0, g_diagLastAtr=0;

struct TFView
{
   bool     ok;
   double   fast;        // 快EMA（已完成 bar）
   double   slow;        // 慢EMA
   double   slowOld;     // 慢EMA N 根前
   double   atr;
   double   close1;      // 上一根已收盘 bar 的收盘价
   double   hiPrior;     // 前 N 根已收盘 bar 的最高价（不含上一根）
   double   loPrior;     // 前 N 根的最低价
   int      bars;
};

bool GetView(ENUM_TIMEFRAMES tf, int breakoutBars, TFView &v)
{
   v.ok = false;
   g_diagCalls++;
   double o[], h[], l[], c[];
   int want = MathMax(InpSlowEMA + InpSlopeLookback + breakoutBars + 5, 60);
   int n = BuildAggBars(tf, want, o, h, l, c);
   g_diagLastAgg = n;
   if(n < InpSlowEMA + InpSlopeLookback + 3) { g_diagFewBars++; return false; }

   v.bars    = n;
   v.fast    = EMAOnArray(c, InpFastEMA, 1);
   v.slow    = EMAOnArray(c, InpSlowEMA, 1);
   v.slowOld = EMAOnArray(c, InpSlowEMA, 1 + InpSlopeLookback);
   v.atr     = ATRFromBars(h, l, c, InpATRPeriod, 1);
   v.close1  = c[n - 2];                      // 最后一根已收盘 bar
   g_diagLastClose = v.close1;
   g_diagLastFast  = v.fast;
   g_diagLastSlow  = v.slow;
   g_diagLastAtr   = v.atr;

   // 前 breakoutBars 根（在 close1 之前）的高低点
   v.hiPrior = -1e18; v.loPrior = 1e18;
   int cnt = 0;
   for(int i = n - 3; i >= 0 && cnt < breakoutBars; i--, cnt++)
   {
      if(h[i] > v.hiPrior) v.hiPrior = h[i];
      if(l[i] < v.loPrior) v.loPrior = l[i];
   }
   if(cnt < breakoutBars) { g_diagNoBreak++; return false; }
   if(v.hiPrior <= -1e17 || v.loPrior >= 1e17) { g_diagNoBreak++; return false; }

   v.ok = (v.fast > 0.0 && v.slow > 0.0 && v.slowOld > 0.0 && v.atr > 0.0);
   if(v.ok) g_diagOK++; else g_diagBadEma++;
   return v.ok;
}

//==================== 生命周期 ====================
int OnInit()
{
   if(InpRiskPct <= 0.0 || InpRiskPct > 20.0)
   { Print("InpRiskPct 必须在 (0,20] 之间"); return INIT_PARAMETERS_INCORRECT; }
   if(InpFastEMA >= InpSlowEMA)
   { Print("InpFastEMA 必须小于 InpSlowEMA"); return INIT_PARAMETERS_INCORRECT; }

   g_hFast = INVALID_HANDLE;
   g_hSlow = INVALID_HANDLE;
   g_hATR  = INVALID_HANDLE;
   // ★指标不在这里创建（见 EnsureIndicators 注释：大周期会在 OnInit 报 err=4805）

   g_peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_dayStartEquity = g_peakEquity;

   if(InpWriteAudit)
   {
      FolderCreate("dshtrend", FILE_COMMON);
      FolderCreate(ExitDirName(), FILE_COMMON);
      g_auditFh = FileOpen(ExitFhName(), FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_auditFh != INVALID_HANDLE)
         FileWrite(g_auditFh, "run_tag","symbol","time","dir","entry","exit",
                   "vol","pnl","risk_money","atr_at_entry","exit_reason");

      // ★回撤事件 / 月度回撤 明细文件
      g_ddFh = FileOpen("dshtrend/" + InpRunTag + "/dd_episodes.csv",
                        FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_ddFh != INVALID_HANDLE)
         FileWrite(g_ddFh, "run_tag","kind","peak_time","trough_time","end_time",
                   "peak_equity","trough_equity","dd_usd","dd_pct","recover_hours");
      g_monFh = FileOpen("dshtrend/" + InpRunTag + "/dd_monthly.csv",
                         FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(g_monFh != INVALID_HANDLE)
         FileWrite(g_monFh, "run_tag","month","equity_start","equity_peak",
                   "equity_trough","dd_pct","samples");
   }

   PrintFormat("[%s] 启动: %s digits=%d point=%s vol_min=%.2f vol_step=%.2f "
               "tick_value=%s tick_size=%s 每手每单位价格=%s",
               InpRunTag, _Symbol, _Digits, DoubleToString(_Point, 8),
               SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN),
               SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP),
               DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE), 8),
               DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE), 8),
               DoubleToString(LossPerLotForDistance(1.0), 6));
   PrintFormat("[%s] 风险=%.2f%%净值  止损=%.1f×ATR(M5)  移动=%.1f×ATR  止盈=%.1f×ATR  "
               "RV闸门=%s(%.3f%%)",
               InpRunTag, InpRiskPct, InpSL_ATR, InpTrail_ATR, InpTP_ATR,
               InpUseRVGate?"开":"关", InpRVMinPct);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   PrintFormat("[%s] 视图诊断: 调用=%d bars不足=%d 突破不足=%d EMA异常=%d 正常=%d  最后 aggBars=%d close=%s fast=%s slow=%s atr=%s",
               InpRunTag, g_diagCalls, g_diagFewBars, g_diagNoBreak, g_diagBadEma, g_diagOK,
               g_diagLastAgg, DoubleToString(g_diagLastClose,3),
               DoubleToString(g_diagLastFast,3), DoubleToString(g_diagLastSlow,3),
               DoubleToString(g_diagLastAtr,3));
   PrintFormat("[%s] 手数诊断: 无tick值=%d 未允许超最小手=%d 超风险上限=%d | 最后 perLot=%s riskMoney=%s cap=%s 最小手风险=%s tv=%s ts=%s 最后止损距离=%s",
               InpRunTag, (int)g_lotRejTick, (int)g_lotRejNoOver, (int)g_lotRejCap,
               DoubleToString(g_lastPerLot,4), DoubleToString(g_lastRiskMoney,2),
               DoubleToString(g_lastCap,2), DoubleToString(g_lastMinLotRisk,4),
               DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE),6),
               DoubleToString(SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE),8),
               DoubleToString(g_lastStopDist,6));
   PrintFormat("[%s] 止损诊断: ATR止损距离=%s  stopsLevel=%s 被抬高次数=%d",
               InpRunTag, DoubleToString(g_lastAtrDist,6), DoubleToString(g_lastStopsLevel,1),
               (int)g_stopsLevelBumps);
   if(g_auditFh != INVALID_HANDLE) { FileFlush(g_auditFh); FileClose(g_auditFh); }
   // ★收尾：把当前未恢复的回撤事件也记下来（标记 still_open），并输出汇总
   if(g_epActive && g_epTroughPct >= InpDDMinDepthPct)
   {
      g_ddOpenCount++;
      DDEpisodeLog("still_open", (double)(TimeCurrent() - g_epStart) / 3600.0);
   }
   if(g_curMon > 0 && g_monSamples > 0 && g_monFh != INVALID_HANDLE)
   {
      int y = (g_curMon - 1) / 12, mm = g_curMon - y * 12;
      FileWrite(g_monFh, InpRunTag, StringFormat("%04d-%02d", y, mm),
                DoubleToString(g_monStartEq, 2), DoubleToString(g_monPeakEq, 2),
                DoubleToString(g_monTroughEq, 2), DoubleToString(g_monWorstPct, 2),
                (string)g_monSamples);
      FileFlush(g_monFh);
   }
   if(g_ddFh  != INVALID_HANDLE) { FileFlush(g_ddFh);  FileClose(g_ddFh); }
   if(g_monFh != INVALID_HANDLE) { FileFlush(g_monFh); FileClose(g_monFh); }

   double ddAvg  = (g_ddEpisodes > 0) ? g_ddSumPct / g_ddEpisodes : 0.0;
   double recAvg = (g_ddEpisodes > 0) ? g_ddSumRecoverH / g_ddEpisodes : 0.0;
   PrintFormat("[%s] DD_EVENTS 已恢复=%d 未恢复=%d 平均深度=%.2f%% 最深=%.2f%% 平均恢复=%.1fh | >=10%%:%d >=15%%:%d >=20%%:%d >=25%%:%d >=30%%:%d",
               InpRunTag, g_ddEpisodes, g_ddOpenCount, ddAvg, g_ddWorstPct, recAvg,
               g_ddOver10, g_ddOver15, g_ddOver20, g_ddOver25, g_ddOver30);

   double wr = (g_nTrades > 0) ? 100.0 * (double)g_nWin / (double)g_nTrades : 0.0;
   PrintFormat("[%s] === 结束 reason=%d 交易=%d 胜率=%.1f%% 总盈利=%.2f 总亏损=%.2f "
               "最大单盈=%.2f 最大单亏=%.2f 日损阻断=%s 回撤锁=%s ===",
               InpRunTag, reason, (int)g_nTrades, wr, g_sumWin, g_sumLoss,
               g_bestWin, g_worstLoss,
               g_dailyBlocked?"是":"否", g_ddLocked?"是":"否");
}

//==================== 主循环 ====================
void OnTick()
{
   RefreshAccountRisk();

   // 0) 指标延迟创建（大周期序列需要时间同步）

   // 1) 每根 M1 更新波动率
   if(IsNewBucket(PERIOD_M1, g_lastRVM1))
   {
      double rv;
      if(CalcRV(rv)) g_rvPct = rv;
   }

   // 2) 管理已有持仓（每 tick 都做，及时止损）
   if(HasPosition())
   {
      ManageOpenPosition();
      return;   // 单仓模式：有仓时不开新仓
   }

   // 3) 只在 M5 新根上评估入场
   if(!IsNewBucket(InpTrendTF, g_lastBarM5)) return;

   if(g_ddLocked) return;
   if(g_dailyBlocked) return;
   if(!SessionAllowsOpen()) return;

   if(InpUseRVGate && g_rvPct > 0.0 && g_rvPct < InpRVMinPct) return;

   double atr; string why;
   int sig = EvalSignal(atr, why);
   if(sig == 0)
   {
      // 诊断：统计"信号为什么没出来"（周期性打印，便于定位 0 成交的原因）
      static int dbg = 0; static int c1=0,c2=0,c3=0,c4=0,c5=0,c6=0;
      if(why == "bars") c1++;
      else if(why == "ema") c2++;
      else if(why == "bars2") c3++;
      else if(why == "confirm_up" || why == "confirm_down") c4++;
      else if(why == "no_signal") c5++;
      else c6++;
      dbg++;
      if(InpVerboseLog && dbg % 300 == 0)
         PrintFormat("[%s] 信号诊断 样本=%d bars=%d ema=%d bars2=%d confirm=%d nosig=%d other=%d 最后why=%s",
                     InpRunTag, dbg, c1, c2, c3, c4, c5, c6, why);
      return;
   }
   if(sig > 0 && !InpAllowLong)  return;
   if(sig < 0 && !InpAllowShort) return;

   double stopDist = InpSL_ATR * atr;
   if(stopDist <= 0.0) return;
   g_lastAtrDist = stopDist;

   // 检查券商最小止损距离
   long stopsLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   g_lastStopsLevel = (double)stopsLevel;
   if(stopsLevel > 0)
   {
      double minDist = (double)stopsLevel * _Point;
      if(stopDist < minDist)
      {
         stopDist = minDist;
         g_stopsLevelBumps++;
      }
   }

   OpenPosition(sig, stopDist, atr, why);
}

//==================== 持仓管理实现 ====================
void ManageOpenPosition()
{
   if(!HasPosition()) return;

   int    dir  = (int)PosType();
   double open = PosOpen();
   double atr  = g_atrAtEntry;
   if(atr <= 0.0) atr = 1.0;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double cur = (dir == POSITION_TYPE_BUY) ? bid : ask;

   // 更新最优价
   if(dir == POSITION_TYPE_BUY)
   {
      if(bid > g_bestPrice) g_bestPrice = bid;
   }
   else
   {
      if(g_bestPrice == 0.0 || ask < g_bestPrice) g_bestPrice = ask;
   }

   // 1) 固定止盈
   if(InpTP_ATR > 0.0)
   {
      double tpDist = InpTP_ATR * atr;
      if(dir == POSITION_TYPE_BUY  && bid >= open + tpDist) { ClosePosition("tp"); return; }
      if(dir == POSITION_TYPE_SELL && ask <= open - tpDist) { ClosePosition("tp"); return; }
   }

   // 2) 趋势反向交叉平仓
   if(InpExitOnCross)
   {
      int td = TrendDirection();
      if(dir == POSITION_TYPE_BUY  && td < 0) { ClosePosition("trend_exit"); return; }
      if(dir == POSITION_TYPE_SELL && td > 0) { ClosePosition("trend_exit"); return; }
   }

   // 3) 移动止损（浮盈超过 TrailStart_ATR 倍 ATR 后启动）
   if(InpTrail_ATR > 0.0)
   {
      double profitDist = (dir == POSITION_TYPE_BUY) ? (g_bestPrice - open)
                                                     : (open - g_bestPrice);
      if(profitDist >= InpTrailStart_ATR * atr)
      {
         double newSL = (dir == POSITION_TYPE_BUY) ? (g_bestPrice - InpTrail_ATR * atr)
                                                   : (g_bestPrice + InpTrail_ATR * atr);
         newSL = NormPrice(newSL);
         bool better = (dir == POSITION_TYPE_BUY) ? (newSL > g_curSL + _Point)
                                                  : (newSL < g_curSL - _Point || g_curSL == 0.0);
         if(better)
         {
            if(ModifySL(newSL)) g_curSL = newSL;
         }
      }
   }
   // 注：初始止损由券商侧 SL 托管（下单时已设），所以即使 EA 掉线也能保护。
}

bool ModifySL(double newSL)
{
   if(!HasPosition()) return false;
   MqlTradeRequest req; MqlTradeResult res;
   ZeroMemory(req); ZeroMemory(res);
   req.action   = TRADE_ACTION_SLTP;
   req.symbol   = _Symbol;
   req.position = g_ticket;
   req.sl       = newSL;
   req.tp       = PosTP();
   if(!OrderSend(req, res) ||
      (res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_PLACED))
   {
      if(InpVerboseLog)
         PrintFormat("[%s] 修改SL失败 retcode=%d err=%d", InpRunTag, res.retcode, GetLastError());
      return false;
   }
   return true;
}
//+------------------------------------------------------------------+













