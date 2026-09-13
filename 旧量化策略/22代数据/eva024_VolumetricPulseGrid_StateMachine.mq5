//+------------------------------------------------------------------+
//|                                   VolumetricPulseGrid_StateMachine_v1.00.mq5  |
//|                         RV High/Low Regime Parameter Version     |
//|  eva024: 网格波动因子改"变指数" factor=ratio^(GridExpLow+GridExpSlope  |
//|          ×ratio)(低≈0.5,参考=1,高随ratio平滑增大),替代clip上下钳制;    |
//|          保留高位安全帽防极端尖刺                                      |
//|  eva013: 波动率判档=唯一“百分比波动”法; 窗口=InpVolWindowMinutes     |
//|  eva010: 趋势门控离场 / pacing开关 / 浮亏熔断 / 趋势止损放宽       |
//|  v1.93: 基线持久化 / 基线可视化 / 做空止盈防负 / 档位切换不重算   |
//|         基线 / 固定长周期RV                                       |
//|  v1.94: 合并高低波动手数 / multiplier_a 指数衰减 / 强制单一档位    |
//|  v1.95: 低于下限可按mult=1交易 / 截止虚拟末单线硬止损             |
//|  v0.95: 三档波动(低/中/高)+各自强制模式 / 参数按档位分块整理       |
//|         全新 OnTester 评分(交易频次+多次回撤惩罚+稳定性)           |
//|         回测内强制重置基线，杜绝优化各 pass 间基线污染             |
//|  v0.96: 波动率分档改为四阈值方向切换(低→中/中→高/高→中/中→低)     |
//|         各边界滞后宽度独立可调；含跨档跳变与顺序校验               |
//|  v0.97: 强制档位语义变更——仅在该档位真实出现时才用其参数开仓，     |
//|         其余真实档位不开新单(含加仓)，仍管理/平掉已有持仓           |
//|  v0.98: 1) 固定长周期RV新增"参照价位"，按 当前价/参照价 线性缩放，   |
//|            标的价位变化时固定RV自动随之调整(RV∝价位)。             |
//|         2) 限定档位模式支持"双档组合"(低+中/低+高/中+高)，可一次   |
//|            只放行两个波动段开仓，便于按高→中→低顺序分段寻优。       |
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//|  eva002（基于 v1.00，交易逻辑零改动，仅叠加“可审计日志”层）        |
//|  -------------------------------------------------------------    |
//|  新增：trade_events / decision_audit / run_config 三类 CSV 输出。  |
//|  全部由 InpEnableTradeAudit 总开关控制；优化(Optimization)时强制     |
//|  关闭，避免多 pass 抢占同一文件、拖慢优化器。                        |
//|  详见文件末尾 “=== eva002 审计日志模块 ===” 区块与 eva_DEVLOG.md。   |
//+------------------------------------------------------------------+
#property copyright "Copyright 2025, Gemini AI User"
#property link      "https://www.mql5.com"
#property version   "1.01"      // eva002：审计日志层（交易逻辑与 v1.00 完全一致）
#property strict

#include <Trade\Trade.mqh>


//--- 输入参数
//==================================================================
//  说明（v0.95）：
//  1) 参数已按"档位"整块归类：先全部【统一】，再全部【中波动】，
//     再全部【高波动】，方便整列填写/对照。
//  2) 中波动是新增的第三档，覆盖 RVLowRatio~RVHighRatio 之间的过渡区，
//     解决"低/高各自调好、合一起变差"的切换问题。
//     再 FORCE_MID 调中波动一整块，再 FORCE_LOW 调低波动一整块。
//  4) v0.98 新增"双档组合"模式：可用 LOW_HIGH 只放行低+高两段开仓
//     (中波动只管理不开新单)，便于在固定一段已调好后再联调另一段；
//     LOW_MID / MID_HIGH 同理。最后切回 AUTO 做联合/前向验证。
//==================================================================

input group "=== 档位与波动率分档（共享） ==="
input int      InpVolWindowMinutes        = 15;       // eva013: 百分比波动的M1窗口(根数=分钟)。太小噪声大、太大滞后

//--- eva012 R1：百分比波动率判档（尺度无关，跨年代/价位稳定；替代“长短比+固定RV缩放”）
//--- 原理：百分比波动 = 短周期RV(点) × point / 当前价 × 100。1k与4k金价上同一波动给出同一%，无需手工乘2/4。
//--- 约束同上：MidToLow < LowToMid <= HighToMid < MidToHigh（单位：%）

input group "=== 共享：手数 / 倍数 / 魔术编号 ==="
input double   InpLotSize                 = 0.01;     // 固定手数（高/中/低波动共用，动态手数关闭时生效）
input int      InpMagicNum                = 123456;   // 魔术编号
input double   InpMultiplierExp           = 1.0;      // multiplier_a 指数：1=原值，0.5=开平方，0.333=开立方，<1抑制极端放大

input group "=== 动态手数（可选，共享） ==="
input bool     InpUseDynamicLot          = false;     // 是否启用动态手数
input bool     InpLotByEquity            = false;     // false=按余额Balance；true=按净值Equity
input double   InpDynBaseCapital         = 200.0;     // 第1档手数所需资金
input double   InpDynBaseLotStep         = 0.01;      // 每提升1档增加多少手
input double   InpDynLevelCoef           = 1.50;      // 每升一档，资金门槛放大系数
input double   InpDynMaxLot              = 0.0;       // 动态手数额外上限（<=0表示不限制）

input group "=== 周末风险时段（共享） ==="
input bool     InpUseWeekendGuard         = true;     // 是否启用周末时段保护
input int      InpFridayCloseOnlyMinutes  = 120;      // 周五收盘前N分钟：三级风险，同时强制使用高波动参数
input int      InpFridayForceCloseMinutes = 30;       // 周五收盘前最后N分钟：四级风险，同时强制使用高波动参数
input int      InpMondayNoOpenMinutes     = 180;      // 每周市场重开后N分钟：二级风险(禁开新单)，同时强制使用高波动参数。v0.99起按服务器真实重开时刻(黄金=周日晚)锚定

input group "=== v1.95 风控增强（共享） ==="
input bool     InpTradeBelowBaseVol       = true;    // 低于下限时是否仍交易（按multiplier_a=1）；false=旧逻辑不交易
input bool     InpUseCutoffLineStop       = true;    // 是否启用"截止虚拟末单线"硬止损

input group "=== v0.99 开盘/重开/止损增强（共享） ==="
input bool     InpCheckTradeModeBeforeOpen = true;   // 开仓前检查品种交易模式：close-only/禁用/方向不符时跳过下单，规避每日/每周重开瞬间的 retcode 10044
input bool     InpResetBaselineOnReopen    = false;  // 市场重开(每日收盘/每周缺口)后，若当前空仓则把基线重置到现价，避免基线与新开盘价相差过大导致"无脑做多/做空"
input int      InpReopenGapMinutes         = 10;     // 相邻 M1 柱间隔 ≥ 此分钟数视为一次"市场重开/缺口"(仅用于上面的基线重置判定，不影响是否禁开仓)

//================== 统 一 参 数 （单一套） ========================
input group "=== 统一模型：距离 = 基准点 ×(当前价/参考价)×(波动%/参考波动%)^指数 ==="
input double   InpRefPrice               = 4000;      // 参考金价；价格缩放 = 当前价/此值（$1000/$4000 自动按比例）
input double   InpRefVolPct              = 0.024;     // 参考波动%；波动因子 = (当前波动%/此值)^指数
input int      InpGridZ                  = 7000;      // 网格基距（点，参考价&参考波动下）★eva023固化为你寻参值
input double   InpGridExpLow             = 0.5;       // 变指数(低波动端)：ratio→0 时指数≈此值。网格指数 = InpGridExpLow + InpGridExpSlope×ratio
input double   InpGridExpSlope           = 0.5;       // 变指数斜率：默认0.5 → 指数(ratio=0)=0.5、(1)=1、(4)=2.5(平滑,高端指数不过大)
input double   InpVolFactorMax           = 40.0;      // 网格波动因子高位安全帽(只防极端尖刺ratio≳4,正常不触发;低端由InpMinGridZ兜底)
input int      InpMinGridZ               = 2000;      // ★网格最小距（点，仅随价、不随波动）：防低波动网格塌陷churn ★eva023固化为你寻参值
input int      InpMoveB                  = 130;       // 空仓基线追价（点）
input double   InpMoveVolExp             = 0.8;       // 追价波动指数
input int      InpCoefC                  = 63;        // 持仓基线移动基数（点）
input double   InpCoefCVolExp            = 0.0;       // 持仓移动波动指数
input double   InpCoefDecay              = 0.85;      // 持仓基线移动：每加一仓的衰减系数
input double   InpUniGridExpCoef         = 1.4;       // 网格扩展系数（马丁：每加一仓网格距×此值）
input int      InpUniMaxPos              = 3;         // 最大同时持仓数
input int      InpUniBaseProfit          = 200000;    // 止盈点数（单一大值；主要由回归基线出场）
input int      InpX_Minutes              = 40;        // 基线计算周期（X分钟）
input int      InpAvgVolumeMinutes       = 50;        // 平均每分钟交易量窗口（分钟）
input double   InpBaseAvgVolumePerMin    = 160;       // multiplier_a 基准量（avg/此值，地板1.0，只放大网格不缩小）
input double   InpMaxAvgVolumePerMin     = 220;       // 截止平均每分钟交易量（超过进二级风险）
input group "=== 风险 / 止损 ==="
input double   InpRiskL2ProfitPerLot     = 1000.0;    // 二级风险每1手盈利提前平仓
input double   InpRiskL3ProfitPerLot     = 0.0;       // 三级风险盈利单平仓阈值（<=0只要盈利就平）
input double   InpRiskL3LossPerLot       = 700.0;     // 三级风险亏损单止损阈值（<=0只要亏损就平）
input double   InpLastOrderLossPerLot    = 800;       // 最后一单亏损/1手 → 全平 + 冷静期
input group "=== 加仓延迟 / 冷静期（pacing_panic 已删，仅保留加仓延迟门闸）==="
input int      InpDelayOrder2Minutes     = 19;        // 第二单最短等待分钟
input int      InpDelayOrder3Minutes     = 13;        // 第三单最短等待分钟
input int      InpDelayOrder4Minutes     = 16;        // 第四单最短等待分钟
input int      InpDelayOrder5Minutes     = 12;        // 第五单最短等待分钟
input int      InpDelayOrder6Minutes     = 8;         // 第六单最短等待分钟
input int      InpCooldownMinutes        = 120;       // 普通冷静期（分钟）
input int      InpBigCooldownMinutes     = 840;       // 大冷静期（分钟）

//================== 中 波 动 参 数 （整块，v0.95新增） =============

//================== 高 波 动 参 数 （整块） ========================

//================== OnTester 评分（仅优化器选 Custom max 时生效） ===

//================== 状态机 / 动量趋势模块 ========================
input group "=== 状态机：行情识别 / 网格方向门闸 ==="
input bool            InpEnableStateMachine          = true;        // 是否启用状态机：RANGE/趋势上涨/趋势下跌
input ENUM_TIMEFRAMES InpTrendTimeframe              = PERIOD_M5;   // 趋势识别周期
input int             InpTrendFastEMAPeriod          = 20;          // 趋势快EMA周期
input int             InpTrendSlowEMAPeriod          = 60;          // 趋势慢EMA周期
input int             InpTrendSlowSlopeLookback      = 3;           // 慢EMA斜率回看根数：慢线当前值 vs N根前
input int             InpTrendBreakoutBars           = 30;          // 突破窗口：收盘突破前N根高/低点；<=0则不要求突破
input bool            InpTrendUseRVFilter            = true;        // 是否要求RVRatio达到阈值才确认趋势
input double          InpTrendMinRVRatio             = 0.020;       // 趋势确认所需最小RVRatio(对比G_RVRatio=百分比波动,典型0.01~0.03)。旧默认1.35是eva019把G_RVRatio改为百分比后遗留的量级错配→闸门常闭→趋势从不确认
input int             InpTrendConfirmBars            = 2;           // 连续确认几根趋势周期K线后切换状态
input bool            InpTrendExitOnFastEMA          = true;        // 趋势退出：收盘跌破/突破快EMA即退出趋势
input bool            InpBlockAgainstTrendGrid       = true;        // 趋势状态下禁止逆势网格开新单
input bool            InpCloseOppositeGridOnTrend    = false;       // 趋势确认后是否立即平掉逆势网格仓位（默认false，避免直接砍仓）
input bool            InpEnableStateMachineLog       = true;        // 是否输出状态切换日志

input group "=== 状态机：顺势趋势单 ==="
input bool            InpEnableTrendOrders           = true;        // 趋势确认后是否开独立顺势单
input int             InpTrendMagicNum               = 223456;      // 趋势单魔术编号；必须与网格不同
input bool            InpTrendUseGridLot             = true;        // 趋势单是否沿用网格当前手数
input double          InpTrendLotSize                = 0.01;        // 趋势单固定手数（未沿用网格手数时生效）
input int             InpTrendMaxPositions           = 1;           // 趋势单最大持仓数（建议先=1）
input int             InpTrendATRPeriod              = 14;          // 趋势单ATR周期
input double          InpTrendSL_ATR_Mult            = 1.50;        // 趋势单初始止损 = ATR倍数
input double          InpTrendTP_ATR_Mult            = 0.00;        // 趋势单固定止盈 = ATR倍数；<=0表示不设置固定TP
input double          InpTrendTrail_ATR_Mult         = 1.20;        // 趋势单移动止损 = ATR倍数；<=0关闭移动止损
input bool            InpTrendCloseOnStateExit       = true;        // 状态回到震荡/反向时，是否平趋势单
input bool            InpTrendRespectRiskGate        = true;        // L2及以上风险时不新开趋势单
input bool            InpTrendRespectCooldown        = true;        // 冷静期内不新开趋势单

input group "=== OnTester 自定义评分 ==="
input double   InpScoreProfitPow          = 1.0;      // 利润幂次：1=线性，0.5=开根(更抗少数大单过拟合)
input double   InpScoreDDRefPct           = 20.0;     // 最大回撤参考%(回撤=此值时该惩罚因子=0.5)
input double   InpScoreDDPow              = 2.0;      // 最大回撤惩罚幂次
input double   InpScoreDDFreqWeight       = 5.0;      // 多次回撤惩罚权重 w（越大越惩罚"多次回撤"）
input double   InpScoreDDMinPct           = 5.0;      // 计入回撤事件的最小深度%（小于此忽略为噪声）
input double   InpScoreTargetTradesPerDay = 6.0;      // 目标每日交易数(注意:1周期含多单,2周期/天≈6)
input double   InpScoreTPDPow             = 1.5;      // 低于目标时的惩罚幂次
input double   InpScoreMinTotalTrades     = 30.0;     // 全程最少交易数；低于则评分压到极小(防统计无意义)
input bool     InpScoreUseDealsForCount   = false;    // false=按STAT_TRADES计数；true=按STAT_DEALS计数
input double   InpScoreSharpeWeight       = 0.0;      // 夏普稳定性权重(>0偏好更平滑净值；默认关闭)
input bool     InpEnableTesterLog         = true;     // 是否在测试结束打印评分明细

input group "=== 回测/优化保护（v0.95） ==="
input bool     InpResetBaselineInTester   = true;     // 回测/优化中每个pass强制重算基线(杜绝pass间基线污染)

input group "=== 调试 ==="
input bool     InpEnableLog               = false;    // 是否输出调试日志

input group "=== eva002 审计日志（优化时自动关闭） ==="
input bool     InpEnableTradeAudit   = false;       // 总开关：输出交易审计CSV。优化(Optimization)时自动强制关闭
input bool     InpAuditDecisions     = true;        // 是否同时输出开仓决策审计(网格触发→放行/被过滤)
input string   InpRunTag             = "";          // 本次运行标签(留空自动用 品种+起始时间 生成 run_id)
input string   InpParamSetId         = "true01_2";  // 参数组ID(写入run_config，多组参数批量回测对账用)
input string   InpStrategyVersion    = "eva002";    // 策略版本标识(写入每行)
input bool     InpAuditUseCommonFile = true;        // CSV写入 Common\Files(跨终端/跨机器可取)；false=本地沙箱 Files

input group "=== 基线可视化（v1.93） ==="
input bool            InpShowBaselineLine  = true;          // 是否在图表上显示基线
input color           InpBaselineLineColor = clrGold;       // 基线颜色
input int             InpBaselineLineWidth = 2;             // 基线线宽
input ENUM_LINE_STYLE InpBaselineLineStyle = STYLE_DASHDOT; // 基线线型

input group "=== 实时状态面板（v0.98） ==="
input bool   InpShowDashboard   = true;        // 是否显示实时状态面板（每分钟刷新一次）
input int    InpDashCorner      = 0;           // 面板角落：0左上 1右上 2左下 3右下
input int    InpDashX           = 12;          // 面板X偏移(像素)
input int    InpDashY           = 22;          // 面板Y偏移(像素)
input int    InpDashFontSize    = 9;           // 面板字号
input string InpDashFont        = "Consolas";  // 面板字体
input color  InpDashTextColor   = clrWhite;    // 面板普通文字颜色

//--- 全局对象
CTrade         trade;

//--- 全局状态
double         G_Baseline = 0.0;
bool           G_BaselineReady = false;
datetime       G_LastCandleTime = 0;
bool           G_IsTradingActive = false;
long           G_HistoricVolumeSum = 0;

//--- 周末时段缓存
int            G_MondayFirstOpenSec = -1;
int            G_FridayLastCloseSec = -1;

//--- v0.99：每周市场重开时刻（直接读服务器会话表；黄金等品种为"周日晚"而非"周一早"）
int            G_WeekReopenDow = -1;   // 重开所在星期(0=周日,1=周一,...)
int            G_WeekReopenSec = -1;   // 重开当天的秒数(0~86399)
datetime       G_PrevM1BarTime = 0;    // v0.99：上一根已处理的 M1 柱时间(用于缺口/重开识别，仅供基线重算)

//--- 风险等级日志缓存
int            G_LastRiskLevel = -1;

//--- 冷静期状态
datetime       G_CooldownUntil = 0;
bool           G_HadProfitSinceLastCooldown = true;

//--- v0.95：回测/评分辅助
datetime       G_TesterStartTime = 0;     // 本次测试起始时间（用于计算每日交易数）
bool           G_SkipBaselinePersist = false; // 回测重置模式下，不向全局变量写基线

//--- v0.98：实时状态面板刷新节流（按M1柱）
datetime       G_LastDashboardBar = 0;

//--- 风险等级定义
enum ENUM_RISK_LEVEL
{
   RISK_LEVEL_1_NORMAL = 1,
   RISK_LEVEL_2_LIMIT  = 2,
   RISK_LEVEL_3_REDUCE = 3,
   RISK_LEVEL_4_EXIT   = 4
};

//--- 加仓节奏检查结果
enum ENUM_ADD_PACING_RESULT
{
   ADD_PACING_ALLOW = 0,
   ADD_PACING_BLOCK = 1
};

//--- 波动率档位
enum ENUM_VOL_REGIME
{
   VOL_REGIME_LOW  = 0,
   VOL_REGIME_MID  = 1,
   VOL_REGIME_HIGH = 2
};

//--- 状态机行情状态
//--- RANGE：震荡/均值回归状态，原网格正常工作
//--- TREND_UP：上涨趋势，禁止逆势空网格，可开独立趋势多单
//--- TREND_DOWN：下跌趋势，禁止逆势多网格，可开独立趋势空单
enum ENUM_MARKET_STATE
{
   MARKET_STATE_RANGE      = 0,
   MARKET_STATE_TREND_UP   = 1,
   MARKET_STATE_TREND_DOWN = 2
};

//--- 当前生效参数快照
struct ActiveStrategyParams
{
   int       x_minutes;
   int       avg_volume_minutes;
   double    base_avg_volume_per_min;
   double    max_avg_volume_per_min;

   int       base_grid_z;
   double    grid_exp_coef;
   int       base_profit;
   double    lot_size;

   int       move_points_b;
   double    coef_c;
   double    coef_decay;

   double    risk_l2_profit_per_lot;
   double    risk_l3_profit_per_lot;
   double    risk_l3_loss_per_lot;

   int       max_total_positions;

   int       delay_order2_minutes;
   int       delay_order3_minutes;
   int       delay_order4_minutes;
   int       delay_order5_minutes;
   int       delay_order6_minutes;

   double    last_order_loss_per_lot;

   int       cooldown_minutes;
   int       big_cooldown_minutes;
};

//--- 当前波动档位状态
ENUM_VOL_REGIME       G_VolRegime = VOL_REGIME_LOW;
ActiveStrategyParams  G_ActiveParams;

//--- v0.97：真实波动档位（始终按RV计算，维持自身滞后状态），
//---        以及"是否允许开新单"的门闸（强制模式下仅该真实档位为true）
ENUM_VOL_REGIME       G_RealVolRegime = VOL_REGIME_LOW;
bool                  G_RegimeOpenAllowed = true;

double                G_RVShortPoints = 0.0;
double                G_RVLongPoints  = 0.0;
double                G_RVRatio       = 1.0;
datetime              G_LastRVCalcBar = 0;

//--- 状态机 / 趋势模块缓存
ENUM_MARKET_STATE     G_MarketState       = MARKET_STATE_RANGE;
int                   G_TrendFastMAHandle = INVALID_HANDLE;
int                   G_TrendSlowMAHandle = INVALID_HANDLE;
int                   G_TrendATRHandle    = INVALID_HANDLE;
datetime              G_LastTrendCalcBar  = 0;
int                   G_TrendUpConfirm    = 0;
int                   G_TrendDownConfirm  = 0;
double                G_TrendFastEMA      = 0.0;
double                G_TrendSlowEMA      = 0.0;
double                G_TrendSlowEMAOld   = 0.0;
double                G_TrendLastClose    = 0.0;
double                G_TrendPrevHigh     = 0.0;
double                G_TrendPrevLow      = 0.0;
double                G_TrendATR          = 0.0;

//--- 持仓快照
struct StrategySnapshot
{
   int       total_count;
   int       buy_count;
   int       sell_count;

   ulong     last_ticket;
   datetime  last_open_time;
   double    last_open_price;
   double    last_open_volume;
   double    last_open_profit;
   ENUM_POSITION_TYPE last_open_type;

   ulong     last_buy_ticket;
   datetime  last_buy_time;
   double    last_buy_price;

   ulong     last_sell_ticket;
   datetime  last_sell_time;
   double    last_sell_price;
};

//==================================================================
//  eva002 审计日志：数据结构 / 全局状态
//  （仅用于记录，不参与任何交易决策；总开关 G_EvaActive 关闭时全部短路）
//==================================================================
//--- 单笔开仓时抓拍的上下文（在下单点填充，下单成功后绑定到 position_id）
struct EvaPendingCtx
{
   bool     valid;
   long     magic;
   int      direction;        // +1=多 -1=空
   string   order_kind;       // "grid" / "trend"
   string   entry_reason;     // grid_buy/grid_sell/trend_buy/trend_sell
   int      order_number;     // 网格加仓序号(1=首单)；趋势单=1
   double   multiplier_a;     // 动态倍数
   double   grid_dist_pts;    // 本单触发所用网格距(点)
   double   tp_dist_pts;      // 止盈距(点)
   // 下方为下单瞬间的环境快照(取自全局)
   int      vol_regime;
   int      real_vol_regime;
   bool     regime_open_allowed;
   int      market_state;
   double   rv_short_pts;
   double   rv_long_pts;
   double   rv_ratio;
   double   baseline;
   int      risk_level;
   double   avg_vol_per_min;
   double   spread_pts;
   double   atr;
};

//--- 已开仓持有记录(等待平仓后落盘一行)
struct EvaOpenRec
{
   bool     used;
   ulong    position_id;
   ulong    deal_in;
   datetime entry_time;
   long     entry_time_msc;
   double   entry_price;
   double   volume;
   double   sl_price;
   double   tp_price;
   EvaPendingCtx ctx;
};

bool          G_EvaActive       = false;   // 运行期实际是否记录(=总开关 且 非优化)
int           G_EvaFhTrades     = INVALID_HANDLE;
int           G_EvaFhAudit      = INVALID_HANDLE;
int           G_EvaFhConfig     = INVALID_HANDLE;
string        G_EvaRunId        = "";
string        G_EvaDir          = "";
double        G_EvaAvgVolForLog = 0.0;     // OnTick 每轮刷新，供下单抓拍用
EvaPendingCtx G_EvaPending;                // 最近一次下单前抓拍的上下文
string        G_EvaExitReason   = "expert_close"; // EA主动平仓的细分原因(平仓前设置)
EvaOpenRec    G_EvaOpen[];                 // 持仓记录表
long          G_EvaWrittenRows  = 0;


//+------------------------------------------------------------------+
//| 函数声明                                                         |
//+------------------------------------------------------------------+
void LoadLowVolParams(ActiveStrategyParams &p);
string RegimeToStr(ENUM_VOL_REGIME r);
void UpdateActiveParams();
bool RecalculateBaselineByMinutes(int minutes);
bool CalcRealizedVolPoints(int minutes, double &rv_points);
bool IsWeekendForcedHighParamTime();
void UpdateVolatilityRegime();

string MarketStateToStr(ENUM_MARKET_STATE s);
bool   InitTrendIndicators();
void   ReleaseTrendIndicators();
bool   UpdateMarketState(bool force_update);
bool   EvaluateTrendSignals(bool &up_signal, bool &down_signal, bool &exit_up, bool &exit_down);
bool   GetTrendATR(double &atr);
int    CountTrendPositions(ENUM_POSITION_TYPE type);
int    CountAllTrendPositions();
double GetTrendOrderLot();
bool   OpenTrendBuyOrder(double lot, double ask, double atr);
bool   OpenTrendSellOrder(double lot, double bid, double atr);
void   CloseTrendPositions(ENUM_POSITION_TYPE type);
void   CloseAllTrendPositions();
void   ManageTrendTrailing();
void   ManageTrendOrders(ENUM_RISK_LEVEL risk_level);

void ResetSnapshot(StrategySnapshot &snap);
void BuildStrategySnapshot(StrategySnapshot &snap);
void AdjustBaseline();
void ManageRiskByLevel(ENUM_RISK_LEVEL level);
bool IsInCooldown();
void StartCooldown(bool big_cooldown);
bool IsTradeRetcodeSuccess(long retcode);
void LogTradeFailure(string action);

int GetVolumeDigits(double step);
double NormalizeVolumeToSymbol(double lots);
double GetLotCapitalReference();
double GetRequiredCapitalForLevel(int level);
double GetCurrentOrderLot();

bool OpenBuyOrder(double lot, double ask, double tp_dist, string comment);
bool OpenSellOrder(double lot, double bid, double tp_dist, string comment);
bool CloseTicket(ulong ticket);

bool CheckLastOrderStopAndCooldown(const StrategySnapshot &snap);
bool CheckCutoffLineStopAndCooldown(const StrategySnapshot &snap);
int GetRequiredDelayMinutes(int next_order_number);
ENUM_ADD_PACING_RESULT CheckAddPacingDelay(ENUM_POSITION_TYPE type,
                                                   const StrategySnapshot &snap,
                                                   double multiplier_a,
                                                   double current_price,
                                                   double point);

void CloseProfitablePositionsByThreshold(double profit_per_lot);
void CloseLosingPositionsByThreshold(double loss_per_lot);
ENUM_RISK_LEVEL GetCurrentRiskLevel(double avg_volume_per_min);
int GetWeekendRiskLevel();

void CloseAllPositions(ENUM_POSITION_TYPE type);
void CloseAllStrategyPositions();
bool CloseNewestStrategyPosition();
bool ClosePositionsNotAllowedByActiveProfile(const StrategySnapshot &snap);

void UpdateHistoricVolumeSum();
int CountPositions(ENUM_POSITION_TYPE type);
int SecondsOfDay(datetime t);
bool GetDaySessionBounds(ENUM_DAY_OF_WEEK day, int &first_open_sec, int &last_close_sec);
bool LoadSessionGuardTimes();
datetime MostRecentWeekdaySecAtOrBefore(datetime now, int target_dow, int target_sec); // v0.99
bool IsSymbolOpenAllowed(ENUM_POSITION_TYPE type);                                      // v0.99
void MaybeResetBaselineOnReopen(datetime new_bar_time);                                 // v0.99
double ComputeMultiplierA(double avg_volume_per_min);                                   // v0.99

double GetSelectedPositionFloatingProfit();

//--- v1.93 新增：基线持久化与可视化
string GetBaselineGlobalVarName();
bool   LoadBaselineFromGlobal();
void   SaveBaselineToGlobal();
string GetBaselineLineName();
void   UpdateBaselineLine();
void   RemoveBaselineLine();

//--- v0.98 新增：实时状态面板
void   UpdateDashboard();
void   RemoveDashboard();

//--- eva002 审计日志模块（仅记录，不影响交易）
void   EvaInit();
void   EvaDeinit();
string EvaPeriodStr(ENUM_TIMEFRAMES tf);
string EvaCsv(string s);
void   EvaCaptureGridPending(int dir, int order_number, double mult,
                             double grid_dist_pts, double tp_dist_pts);
void   EvaCaptureTrendPending(int dir, double atr);
void   EvaBindEntry(long magic);
void   EvaOnDealAdd(ulong deal);
void   EvaSetExit(string reason);
void   EvaWriteDecisionAudit(int dir, int order_number, double mult,
                             double grid_dist_pts, bool allowed, string note);
int    EvaFindOpenSlot(ulong position_id);
int    EvaNewOpenSlot();

//+------------------------------------------------------------------+
//| 初始化                                                           |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNum);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   // v0.95：记录测试起始时间（回测中即为测试区间起点），用于 OnTester 计算每日交易数
   G_TesterStartTime = TimeCurrent();

   // v0.95：是否处于策略测试器中（回测或优化）
   bool is_tester = (bool)MQLInfoInteger(MQL_TESTER);

   // v0.95：回测/优化下若开启重置，则本 pass 不读取、不写入持久化基线，
   //        从而每个参数组合都从同一口径重算基线，杜绝 pass 间的基线污染、保证可复现。
   G_SkipBaselinePersist = (is_tester && InpResetBaselineInTester);

   int max_x = InpX_Minutes;
   int max_avg_vol = InpAvgVolumeMinutes;

   int max_rv = InpVolWindowMinutes;   // eva013: 百分比波动只用一个窗口

   int need_bars = MathMax(max_x + 2, MathMax(max_avg_vol + 2, max_rv + 2));

   if(Bars(_Symbol, PERIOD_M1) < need_bars)
   {
      Print("历史数据不足，无法初始化。need_bars=", need_bars);
      return(INIT_FAILED);
   }

   LoadSessionGuardTimes();

   // v0.99：以当前 M1 柱作为缺口基准，避免 EA 挂载瞬间被误判为"市场重开"
   G_PrevM1BarTime = iTime(_Symbol, PERIOD_M1, 0);


   if(!InitTrendIndicators())
      return(INIT_FAILED);

   UpdateVolatilityRegime();
   UpdateActiveParams();
   UpdateMarketState(true);

   // v0.95：回测重置模式下先清掉可能残留的全局基线，并强制重算；
   //        实盘/不重置模式仍优先从全局变量恢复基线（切周期/视图/重编译不重算）。
   if(G_SkipBaselinePersist)
   {
      if(GlobalVariableCheck(GetBaselineGlobalVarName()))
         GlobalVariableDel(GetBaselineGlobalVarName());

      if(!RecalculateBaselineByMinutes(G_ActiveParams.x_minutes))
      {
         Print("初始化基线失败");
         return(INIT_FAILED);
      }
      G_BaselineReady = true;
   }
   else if(LoadBaselineFromGlobal())
   {
      G_BaselineReady = true;
      if(InpEnableLog)
         Print("已从全局变量恢复基线: ", DoubleToString(G_Baseline, _Digits));
   }
   else
   {
      if(!RecalculateBaselineByMinutes(G_ActiveParams.x_minutes))
      {
         Print("初始化基线失败");
         return(INIT_FAILED);
      }
      G_BaselineReady = true;
      SaveBaselineToGlobal();
   }

   UpdateBaselineLine();

   UpdateHistoricVolumeSum();

   UpdateDashboard();   // v0.98：初始化即显示面板

   G_IsTradingActive = false;
   G_LastCandleTime = iTime(_Symbol, PERIOD_M1, 0);

   EvaInit();   // eva002：初始化审计日志（优化模式下内部会自动禁用）

   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| 反初始化                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   // 仅当用户主动把EA从图表移除时，才清除持久化基线；
   // 切换周期/视图、改参数、重编译、重启MT5都保留基线。
   if(reason == REASON_REMOVE)
   {
      if(GlobalVariableCheck(GetBaselineGlobalVarName()))
         GlobalVariableDel(GetBaselineGlobalVarName());
   }

   ReleaseTrendIndicators();
   RemoveBaselineLine();
   RemoveDashboard();

   EvaDeinit();   // eva002：刷新并关闭审计日志文件
}

//+------------------------------------------------------------------+
//| 成交事件：用于补充记录盈利平仓                                   |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;

   ulong deal = trans.deal;
   if(deal == 0)
      return;

   // eva002：审计记录（含网格与趋势两个魔术号的进/出场），内部按总开关短路
   EvaOnDealAdd(deal);

   if(!HistoryDealSelect(deal))
      return;

   string symbol = HistoryDealGetString(deal, DEAL_SYMBOL);
   if(symbol != _Symbol)
      return;

   long magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
   if(magic != InpMagicNum)
      return;

   long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
   if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_OUT_BY)
      return;

   double pnl = HistoryDealGetDouble(deal, DEAL_PROFIT)
              + HistoryDealGetDouble(deal, DEAL_SWAP)
              + HistoryDealGetDouble(deal, DEAL_COMMISSION);

   if(pnl > 0.0 && !IsInCooldown())
      G_HadProfitSinceLastCooldown = true;
}

//+------------------------------------------------------------------+
//| 主逻辑                                                           |
//+------------------------------------------------------------------+
void OnTick()
{
   UpdateVolatilityRegime();
   UpdateMarketState(false);
   ManageTrendTrailing();

   UpdateDashboard();   // v0.98：内部按M1柱节流，每分钟刷新一次

   datetime current_time = iTime(_Symbol, PERIOD_M1, 0);
   bool isNewMinute = (current_time > G_LastCandleTime);

   if(!G_IsTradingActive)
   {
      if(isNewMinute)
      {
         G_IsTradingActive = true;
         G_LastCandleTime = current_time;
         MaybeResetBaselineOnReopen(current_time);   // v0.99
         AdjustBaseline();
         UpdateHistoricVolumeSum();
      }
      else
      {
         return;
      }
   }
   else if(isNewMinute)
   {
      G_LastCandleTime = current_time;
      MaybeResetBaselineOnReopen(current_time);       // v0.99
      AdjustBaseline();
      UpdateHistoricVolumeSum();
   }

   double ask   = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   long current_tick_vol = 0;
   long vol_array[];
   if(CopyTickVolume(_Symbol, PERIOD_M1, 0, 1, vol_array) == 1)
      current_tick_vol = vol_array[0];

   int volume_window = MathMax(1, G_ActiveParams.avg_volume_minutes);
   double avg_volume_per_min = (double)(G_HistoricVolumeSum + current_tick_vol) / volume_window;
   G_EvaAvgVolForLog = avg_volume_per_min;   // eva002：供下单抓拍上下文

   ENUM_RISK_LEVEL risk_level = GetCurrentRiskLevel(avg_volume_per_min);
   if((int)risk_level != G_LastRiskLevel)
   {
      G_LastRiskLevel = (int)risk_level;
      if(InpEnableLog)
      {
         Print("当前风险等级切换为: ", (int)risk_level,
               "，当前平均每分钟交易量=", DoubleToString(avg_volume_per_min, 2),
               "，当前波动档位=", RegimeToStr(G_VolRegime),
               "，RVShortPoints=", DoubleToString(G_RVShortPoints, 2),
               "，RVLongPoints=", DoubleToString(G_RVLongPoints, 2),
               "，RVRatio=", DoubleToString(G_RVRatio, 2));
      }
   }

   // 四级风险：立即平仓
   if(risk_level == RISK_LEVEL_4_EXIT)
   {
      EvaSetExit("risk4_force_exit");   // eva002
      CloseAllStrategyPositions();
      if(InpTrendCloseOnStateExit)
         CloseAllTrendPositions();
      return;
   }

   StrategySnapshot snap;
   BuildStrategySnapshot(snap);

   // 只有当前波动档位无法保留的仓位，才处理多余仓位
   if(ClosePositionsNotAllowedByActiveProfile(snap))
      BuildStrategySnapshot(snap);

   // 常驻止损：达到当前档位最大持仓数后，最后一单亏损过大则全平 + 冷静期
   if(CheckLastOrderStopAndCooldown(snap))
      return;

   // v1.95：截止虚拟末单线硬止损（不依赖是否达到最大持仓数，解决截止状态止损永不触发）
   if(CheckCutoffLineStopAndCooldown(snap))
      return;

   // 风险等级处理
   ManageRiskByLevel(risk_level);

   // 风险处理后刷新快照
   BuildStrategySnapshot(snap);

   // 正常平仓逻辑
   if(snap.buy_count > 0 && bid >= G_Baseline)
   {
      EvaSetExit("grid_tp_baseline_revert");   // eva002
      CloseAllPositions(POSITION_TYPE_BUY);
      return;
   }

   if(snap.sell_count > 0 && ask <= G_Baseline)
   {
      EvaSetExit("grid_tp_baseline_revert");   // eva002
      CloseAllPositions(POSITION_TYPE_SELL);
      return;
   }

   // 趋势单由独立Magic管理：不受基线平仓逻辑影响
   ManageTrendOrders(risk_level);

   // 二级及以上风险：禁止网格开仓
   if(risk_level >= RISK_LEVEL_2_LIMIT)
      return;

   // 冷静期：禁止开仓
   if(IsInCooldown())
      return;

   // v0.97：强制档位模式下，仅当"真实波动档位"等于所选档位时才允许开新单；
   //        其余真实档位只管理/平掉已有持仓，不开新单(含加仓)。
   //        自动模式下 G_RegimeOpenAllowed 恒为 true，不受影响。
   if(!G_RegimeOpenAllowed)
      return;

   // 基础平均每分钟交易量不足
   // v1.95：默认改为"仍交易，但 multiplier_a 取下限1"（见下方倍数计算的clamp）。
   //        若想恢复旧逻辑（低于下限不开仓），把 InpTradeBelowBaseVol 设为 false。
   if(!InpTradeBelowBaseVol &&
      G_ActiveParams.base_avg_volume_per_min > 0.0 &&
      avg_volume_per_min < G_ActiveParams.base_avg_volume_per_min)
      return;

   // 硬性总持仓上限
   if(G_ActiveParams.max_total_positions > 0 && snap.total_count >= G_ActiveParams.max_total_positions)
      return;

   double multiplier_a = 1.0;
   if(G_ActiveParams.base_avg_volume_per_min > 0.0)
   {
      double raw_multiplier = avg_volume_per_min / G_ActiveParams.base_avg_volume_per_min;

      // v1.94：对 multiplier_a 取指数（如0.5=开平方、0.333=开立方），抑制极端行情下的过度放大
      if(raw_multiplier > 0.0 && InpMultiplierExp > 0.0 && InpMultiplierExp != 1.0)
         multiplier_a = MathPow(raw_multiplier, InpMultiplierExp);
      else
         multiplier_a = raw_multiplier;

      if(multiplier_a < 1.0)
         multiplier_a = 1.0;   // 倍数不应小于1，避免缩小网格/止盈
   }

   bool allow_grid_buy  = true;
   bool allow_grid_sell = true;
   if(InpEnableStateMachine && InpBlockAgainstTrendGrid)
   {
      // 上涨趋势：允许顺势/回调多网格，禁止逆势空网格；下跌趋势反过来
      if(G_MarketState == MARKET_STATE_TREND_DOWN)
         allow_grid_buy = false;
      if(G_MarketState == MARKET_STATE_TREND_UP)
         allow_grid_sell = false;
   }

   // === 多单逻辑 ===
   if(allow_grid_buy && bid < G_Baseline)
   {
      bool open_buy = false;
      double base_dynamic_grid = G_ActiveParams.base_grid_z * point * multiplier_a;
      double final_grid_distance = base_dynamic_grid * MathPow(G_ActiveParams.grid_exp_coef, snap.buy_count);

      if(snap.buy_count == 0)
      {
         if(bid < (G_Baseline - final_grid_distance))
            open_buy = true;
      }
      else
      {
         if(bid < (snap.last_buy_price - final_grid_distance))
            open_buy = true;
      }

      if(open_buy)
      {
         ENUM_ADD_PACING_RESULT pace_buy =
            CheckAddPacingDelay(POSITION_TYPE_BUY, snap, multiplier_a, bid, point);

         if(pace_buy == ADD_PACING_ALLOW)
         {
            if(G_ActiveParams.max_total_positions <= 0 || snap.total_count < G_ActiveParams.max_total_positions)
            {
               double order_lot = GetCurrentOrderLot();
               double tp_dist = G_ActiveParams.base_profit * point * multiplier_a;
               EvaCaptureGridPending(+1, snap.buy_count + 1, multiplier_a,
                                     final_grid_distance / point, tp_dist / point); // eva002
               OpenBuyOrder(order_lot, ask, tp_dist, "VPG Buy");
            }
            else
               EvaWriteDecisionAudit(+1, snap.buy_count + 1, multiplier_a,
                                     final_grid_distance / point, false, "max_total_positions"); // eva002
         }
         else
            EvaWriteDecisionAudit(+1, snap.buy_count + 1, multiplier_a,
                                  final_grid_distance / point, false, "pacing_block"); // eva002
      }
   }

   // === 空单逻辑 ===
   if(allow_grid_sell && bid > G_Baseline)
   {
      bool open_sell = false;
      double base_dynamic_grid = G_ActiveParams.base_grid_z * point * multiplier_a;
      double final_grid_distance = base_dynamic_grid * MathPow(G_ActiveParams.grid_exp_coef, snap.sell_count);

      if(snap.sell_count == 0)
      {
         if(bid > (G_Baseline + final_grid_distance))
            open_sell = true;
      }
      else
      {
         if(bid > (snap.last_sell_price + final_grid_distance))
            open_sell = true;
      }

      if(open_sell)
      {
         ENUM_ADD_PACING_RESULT pace_sell =
            CheckAddPacingDelay(POSITION_TYPE_SELL, snap, multiplier_a, bid, point);

         if(pace_sell == ADD_PACING_ALLOW)
         {
            if(G_ActiveParams.max_total_positions <= 0 || snap.total_count < G_ActiveParams.max_total_positions)
            {
               double order_lot = GetCurrentOrderLot();
               double tp_dist = G_ActiveParams.base_profit * point * multiplier_a;
               EvaCaptureGridPending(-1, snap.sell_count + 1, multiplier_a,
                                     final_grid_distance / point, tp_dist / point); // eva002
               OpenSellOrder(order_lot, bid, tp_dist, "VPG Sell");
            }
            else
               EvaWriteDecisionAudit(-1, snap.sell_count + 1, multiplier_a,
                                     final_grid_distance / point, false, "max_total_positions"); // eva002
         }
         else
            EvaWriteDecisionAudit(-1, snap.sell_count + 1, multiplier_a,
                                  final_grid_distance / point, false, "pacing_block"); // eva002
      }
   }
}

//+------------------------------------------------------------------+
//| 装载低波动参数                                                   |
//+------------------------------------------------------------------+
void LoadLowVolParams(ActiveStrategyParams &p)
{
   p.x_minutes                = InpX_Minutes;
   p.avg_volume_minutes       = InpAvgVolumeMinutes;
   p.base_avg_volume_per_min  = InpBaseAvgVolumePerMin;
   p.max_avg_volume_per_min   = InpMaxAvgVolumePerMin;

   p.lot_size                 = InpLotSize;

   p.coef_decay               = InpCoefDecay;

   p.risk_l2_profit_per_lot   = InpRiskL2ProfitPerLot;
   p.risk_l3_profit_per_lot   = InpRiskL3ProfitPerLot;
   p.risk_l3_loss_per_lot     = InpRiskL3LossPerLot;


   p.delay_order2_minutes     = InpDelayOrder2Minutes;
   p.delay_order3_minutes     = InpDelayOrder3Minutes;
   p.delay_order4_minutes     = InpDelayOrder4Minutes;
   p.delay_order5_minutes     = InpDelayOrder5Minutes;
   p.delay_order6_minutes     = InpDelayOrder6Minutes;

   p.last_order_loss_per_lot  = InpLastOrderLossPerLot;

   p.cooldown_minutes         = InpCooldownMinutes;
   p.big_cooldown_minutes     = InpBigCooldownMinutes;
}

//+------------------------------------------------------------------+
//| 装载高波动参数                                                   |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| 装载中波动参数（v0.95新增）                                       |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| 档位文本（日志用）                                               |
//+------------------------------------------------------------------+
string RegimeToStr(ENUM_VOL_REGIME r)
{
   if(r == VOL_REGIME_HIGH) return "HIGH";
   if(r == VOL_REGIME_MID)  return "MID";
   return "LOW";
}

//+------------------------------------------------------------------+
//| 根据当前波动档位刷新生效参数                                     |
//+------------------------------------------------------------------+
void UpdateActiveParams()
{
   // eva018 统一模型：唯一一套参数(LoadLowVolParams 填基础字段) +
   //   三个距离类字段按  占价% × 当前价 × (当前波动%/参照波动%)^指数  缩放。
   LoadLowVolParams(G_ActiveParams);

   double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(price <= 0.0)
      return;

   double pr_scale = (InpRefPrice > 0.0) ? (price / InpRefPrice) : 1.0;   // 价格缩放($1000/$4000自动按比例)
   double rvpct = G_RVRatio;
   double vf_grid = 1.0, vf_move = 1.0, vf_coef = 1.0;
   if(rvpct > 0.0 && InpRefVolPct > 0.0)
   {
      double rn = rvpct / InpRefVolPct;
      double grid_exp = InpGridExpLow + InpGridExpSlope * rn;  // 变指数：低波动≈0.5、参考(ratio=1)=1、高波动随ratio平滑增大
      vf_grid = MathPow(rn, grid_exp);
      vf_grid = MathMin(InpVolFactorMax, vf_grid);            // 仅高位安全帽防极端尖刺；低端由 InpMinGridZ 兜底
      vf_move = MathPow(rn, InpMoveVolExp);
      vf_coef = MathPow(rn, InpCoefCVolExp);
   }

   double grid_scaled = (double)InpGridZ   * pr_scale * vf_grid;   // 网格基距：随价 × 随波动
   double grid_floor  = (double)InpMinGridZ * pr_scale;            // 网格最小距：随价、不随波动（防低波动塌陷）
   G_ActiveParams.base_grid_z   = (int)MathMax(grid_floor, grid_scaled);
   G_ActiveParams.move_points_b = (int)MathMax(1.0, (double)InpMoveB * pr_scale * vf_move);
   G_ActiveParams.coef_c        =      MathMax(0.0, (double)InpCoefC * pr_scale * vf_coef);

   G_ActiveParams.base_profit         = InpUniBaseProfit;
   G_ActiveParams.grid_exp_coef       = InpUniGridExpCoef;
   G_ActiveParams.max_total_positions = InpUniMaxPos;
}

//+------------------------------------------------------------------+
//| 根据指定分钟数重算基线                                           |
//+------------------------------------------------------------------+
bool RecalculateBaselineByMinutes(int minutes)
{
   int n = MathMax(1, minutes);

   MqlRates rates[];
   if(CopyRates(_Symbol, PERIOD_M1, 1, n, rates) != n)
      return false;

   double sum_price = 0.0;
   for(int i = 0; i < n; i++)
      sum_price += rates[i].close;

   G_Baseline = sum_price / n;

   if(InpEnableLog)
   {
      Print("重算基线完成：minutes=", n,
            ", baseline=", DoubleToString(G_Baseline, _Digits),
            ", regime=", RegimeToStr(G_VolRegime));
   }

   SaveBaselineToGlobal();   // v1.93：持久化
   UpdateBaselineLine();     // v1.93：刷新图线

   return true;
}

//+------------------------------------------------------------------+
//| 波动档位变化后的处理                                             |
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| 计算分钟线Realized Volatility，单位：Point                       |
//+------------------------------------------------------------------+
bool CalcRealizedVolPoints(int minutes, double &rv_points)
{
   rv_points = 0.0;

   int n = MathMax(2, minutes);
   double closes[];

   ArraySetAsSeries(closes, true);

   int copied = CopyClose(_Symbol, PERIOD_M1, 1, n + 1, closes);
   if(copied < n + 1)
      return false;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(point <= 0.0)
      return false;

   double sum_sq = 0.0;

   for(int i = 0; i < n; i++)
   {
      double diff_points = (closes[i] - closes[i + 1]) / point;
      sum_sq += diff_points * diff_points;
   }

   rv_points = MathSqrt(sum_sq / n);
   return true;
}

//+------------------------------------------------------------------+
//| 周一/周五保护时段是否强制使用高波动参数                          |
//+------------------------------------------------------------------+
bool IsWeekendForcedHighParamTime()
{
   if(!InpUseWeekendGuard)
      return false;

   int weekend_level = GetWeekendRiskLevel();
   return (weekend_level >= (int)RISK_LEVEL_2_LIMIT);
}


//+------------------------------------------------------------------+
//| 支持单档(FORCE_*)与双档(LOW_MID/LOW_HIGH/MID_HIGH)               |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| v0.98：所选集合内启用的档位数量                                  |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| v0.98：所选集合内的第一个(最低)启用档位                          |
//+------------------------------------------------------------------+

//+------------------------------------------------------------------+
//| 更新波动率档位                                                   |
//+------------------------------------------------------------------+
void UpdateVolatilityRegime()
{
   // eva019：判档分类器已删。本函数仅在每根新 M1 计算"百分比波动 rv_pct"，
   //         存入 G_RVRatio / G_RVShortPoints 供统一模型的距离缩放使用；随后刷新参数。
   datetime current_bar = iTime(_Symbol, PERIOD_M1, 0);
   if(current_bar != G_LastRVCalcBar)
   {
      G_LastRVCalcBar = current_bar;
      double rv_short = 0.0;
      if(CalcRealizedVolPoints(InpVolWindowMinutes, rv_short))
      {
         double pxr = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double pnt = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
         G_RVShortPoints = rv_short;
         G_RVRatio       = (pxr > 0.0) ? (100.0 * rv_short * pnt / pxr) : 0.0;
      }
   }
   UpdateActiveParams();
}

//+------------------------------------------------------------------+
//| 初始化快照                                                       |
//+------------------------------------------------------------------+
void ResetSnapshot(StrategySnapshot &snap)
{
   snap.total_count = 0;
   snap.buy_count = 0;
   snap.sell_count = 0;

   snap.last_ticket = 0;
   snap.last_open_time = 0;
   snap.last_open_price = 0.0;
   snap.last_open_volume = 0.0;
   snap.last_open_profit = 0.0;
   snap.last_open_type = POSITION_TYPE_BUY;

   snap.last_buy_ticket = 0;
   snap.last_buy_time = 0;
   snap.last_buy_price = 0.0;

   snap.last_sell_ticket = 0;
   snap.last_sell_time = 0;
   snap.last_sell_price = 0.0;
}

//+------------------------------------------------------------------+
//| 当前已选中仓位的浮动盈亏                                         |
//+------------------------------------------------------------------+
double GetSelectedPositionFloatingProfit()
{
   return PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
}

//+------------------------------------------------------------------+
//| 构建持仓快照                                                     |
//+------------------------------------------------------------------+
void BuildStrategySnapshot(StrategySnapshot &snap)
{
   ResetSnapshot(snap);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNum)
         continue;

      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      datetime open_time = (datetime)PositionGetInteger(POSITION_TIME);
      double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double profit = GetSelectedPositionFloatingProfit();
      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);

      snap.total_count++;

      if(type == POSITION_TYPE_BUY)
      {
         snap.buy_count++;
         if(open_time >= snap.last_buy_time)
         {
            snap.last_buy_time = open_time;
            snap.last_buy_price = open_price;
            snap.last_buy_ticket = ticket;
         }
      }
      else if(type == POSITION_TYPE_SELL)
      {
         snap.sell_count++;
         if(open_time >= snap.last_sell_time)
         {
            snap.last_sell_time = open_time;
            snap.last_sell_price = open_price;
            snap.last_sell_ticket = ticket;
         }
      }

      if(open_time >= snap.last_open_time)
      {
         snap.last_open_time = open_time;
         snap.last_open_price = open_price;
         snap.last_open_volume = volume;
         snap.last_open_profit = profit;
         snap.last_ticket = ticket;
         snap.last_open_type = type;
      }
   }
}

//+------------------------------------------------------------------+
//| 调整基线                                                         |
//+------------------------------------------------------------------+
void AdjustBaseline()
{
   StrategySnapshot snap;
   BuildStrategySnapshot(snap);

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double current_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   if(snap.buy_count == 0 && snap.sell_count == 0)
   {
      if(current_price > G_Baseline)
         G_Baseline += G_ActiveParams.move_points_b * point;
      else if(current_price < G_Baseline)
         G_Baseline -= G_ActiveParams.move_points_b * point;
   }
   else
   {
      int net_positions = 0;
      bool move_down = false;

      if(snap.buy_count > snap.sell_count)
      {
         net_positions = snap.buy_count - snap.sell_count;
         move_down = true;
      }
      else if(snap.sell_count > snap.buy_count)
      {
         net_positions = snap.sell_count - snap.buy_count;
         move_down = false;
      }

      if(net_positions > 0)
      {
         double total_move_points = 0.0;
         for(int i = 0; i < net_positions; i++)
            total_move_points += G_ActiveParams.coef_c * MathPow(G_ActiveParams.coef_decay, i);

         if(move_down)
            G_Baseline -= total_move_points * point;
         else
            G_Baseline += total_move_points * point;
      }
   }

   SaveBaselineToGlobal();   // v1.93：每次调整后持久化
   UpdateBaselineLine();     // v1.93：刷新图线
}

//+------------------------------------------------------------------+
//| 分级风险处理                                                     |
//+------------------------------------------------------------------+
void ManageRiskByLevel(ENUM_RISK_LEVEL level)
{
   if(level == RISK_LEVEL_2_LIMIT)
   {
      EvaSetExit("risk2_take_profit");   // eva002
      CloseProfitablePositionsByThreshold(G_ActiveParams.risk_l2_profit_per_lot);
   }
   else if(level == RISK_LEVEL_3_REDUCE)
   {
      EvaSetExit("risk3_take_profit");   // eva002
      CloseProfitablePositionsByThreshold(G_ActiveParams.risk_l3_profit_per_lot);
      EvaSetExit("risk3_cut_loss");      // eva002
      CloseLosingPositionsByThreshold(G_ActiveParams.risk_l3_loss_per_lot);
   }
}

//+------------------------------------------------------------------+
//| 是否在冷静期                                                     |
//+------------------------------------------------------------------+
bool IsInCooldown()
{
   return (TimeTradeServer() < G_CooldownUntil);
}

//+------------------------------------------------------------------+
//| 启动冷静期                                                       |
//+------------------------------------------------------------------+
void StartCooldown(bool big_cooldown)
{
   datetime now = TimeTradeServer();

   if(big_cooldown)
   {
      datetime new_until = now + G_ActiveParams.big_cooldown_minutes * 60;
      if(new_until > G_CooldownUntil)
         G_CooldownUntil = new_until;
   }
   else
   {
      G_CooldownUntil = now + G_ActiveParams.cooldown_minutes * 60;
   }

   G_HadProfitSinceLastCooldown = false;

   if(InpEnableLog)
   {
      if(big_cooldown)
         Print("触发大冷静期，到期时间: ", TimeToString(G_CooldownUntil, TIME_DATE|TIME_MINUTES));
      else
         Print("触发普通冷静期，到期时间: ", TimeToString(G_CooldownUntil, TIME_DATE|TIME_MINUTES));
   }
}

//+------------------------------------------------------------------+
//| 交易结果是否成功                                                 |
//+------------------------------------------------------------------+
bool IsTradeRetcodeSuccess(long retcode)
{
   return (retcode == TRADE_RETCODE_DONE ||
           retcode == TRADE_RETCODE_PLACED ||
           retcode == TRADE_RETCODE_DONE_PARTIAL);
}

//+------------------------------------------------------------------+
//| 统一日志                                                         |
//+------------------------------------------------------------------+
void LogTradeFailure(string action)
{
   if(!InpEnableLog)
      return;

   Print(action,
         " 失败, retcode=", trade.ResultRetcode(),
         ", desc=", trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
//| 根据交易品种的最小手数/步进/最大手数规整手数                     |
//+------------------------------------------------------------------+
int GetVolumeDigits(double step)
{
   for(int i = 0; i <= 8; i++)
   {
      if(MathAbs(step - NormalizeDouble(step, i)) < 1e-8)
         return i;
   }
   return 2;
}

//+------------------------------------------------------------------+
//| 规整手数：严格按照 SYMBOL_VOLUME_STEP 向下取整                    |
//+------------------------------------------------------------------+
double NormalizeVolumeToSymbol(double lots)
{
   if(lots <= 0.0)
      return 0.0;

   double min_vol  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_vol  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double vol_step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

   if(vol_step <= 0.0)
      vol_step = 0.01;

   if(max_vol > 0.0)
      lots = MathMin(lots, max_vol);

   lots = MathFloor((lots + 1e-12) / vol_step) * vol_step;
   lots = NormalizeDouble(lots, GetVolumeDigits(vol_step));

   if(min_vol > 0.0 && lots < min_vol - 1e-12)
      return 0.0;

   return lots;
}

//+------------------------------------------------------------------+
//| 动态手数：取得参考资金                                           |
//+------------------------------------------------------------------+
double GetLotCapitalReference()
{
   if(InpLotByEquity)
      return AccountInfoDouble(ACCOUNT_EQUITY);

   return AccountInfoDouble(ACCOUNT_BALANCE);
}

//+------------------------------------------------------------------+
//| 动态手数：第n档手数所需资金                                      |
//| 公式：BaseCapital * n * coef^(n-1)                               |
//+------------------------------------------------------------------+
double GetRequiredCapitalForLevel(int level)
{
   if(level <= 0)
      return 0.0;

   return InpDynBaseCapital * level * MathPow(InpDynLevelCoef, level - 1);
}


//+------------------------------------------------------------------+
//| 状态机：状态转文字                                               |
//+------------------------------------------------------------------+
string MarketStateToStr(ENUM_MARKET_STATE s)
{
   switch(s)
   {
      case MARKET_STATE_TREND_UP:   return "TREND_UP";
      case MARKET_STATE_TREND_DOWN: return "TREND_DOWN";
      default:                      return "RANGE";
   }
}

//+------------------------------------------------------------------+
//| 状态机：初始化趋势指标句柄                                       |
//+------------------------------------------------------------------+
bool InitTrendIndicators()
{
   if(!InpEnableStateMachine)
      return true;

   int fast_period = MathMax(1, InpTrendFastEMAPeriod);
   int slow_period = MathMax(1, InpTrendSlowEMAPeriod);
   int atr_period  = MathMax(1, InpTrendATRPeriod);

   G_TrendFastMAHandle = iMA(_Symbol, InpTrendTimeframe, fast_period, 0, MODE_EMA, PRICE_CLOSE);
   G_TrendSlowMAHandle = iMA(_Symbol, InpTrendTimeframe, slow_period, 0, MODE_EMA, PRICE_CLOSE);
   G_TrendATRHandle    = iATR(_Symbol, InpTrendTimeframe, atr_period);

   if(G_TrendFastMAHandle == INVALID_HANDLE ||
      G_TrendSlowMAHandle == INVALID_HANDLE ||
      G_TrendATRHandle    == INVALID_HANDLE)
   {
      Print("状态机指标初始化失败：请检查品种/周期/历史数据。TF=", EnumToString(InpTrendTimeframe));
      return false;
   }

   int need_bars = MathMax(slow_period + MathMax(1, InpTrendSlowSlopeLookback) + 5,
                           MathMax(MathMax(1, InpTrendBreakoutBars) + 5, atr_period + 5));
   if(Bars(_Symbol, InpTrendTimeframe) < need_bars)
   {
      Print("状态机趋势周期历史数据不足：TF=", EnumToString(InpTrendTimeframe),
            ", need_bars=", need_bars,
            ", current=", Bars(_Symbol, InpTrendTimeframe));
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| 状态机：释放趋势指标句柄                                         |
//+------------------------------------------------------------------+
void ReleaseTrendIndicators()
{
   if(G_TrendFastMAHandle != INVALID_HANDLE)
   {
      IndicatorRelease(G_TrendFastMAHandle);
      G_TrendFastMAHandle = INVALID_HANDLE;
   }
   if(G_TrendSlowMAHandle != INVALID_HANDLE)
   {
      IndicatorRelease(G_TrendSlowMAHandle);
      G_TrendSlowMAHandle = INVALID_HANDLE;
   }
   if(G_TrendATRHandle != INVALID_HANDLE)
   {
      IndicatorRelease(G_TrendATRHandle);
      G_TrendATRHandle = INVALID_HANDLE;
   }
}

//+------------------------------------------------------------------+
//| 状态机：评估趋势信号                                             |
//+------------------------------------------------------------------+
bool EvaluateTrendSignals(bool &up_signal, bool &down_signal, bool &exit_up, bool &exit_down)
{
   up_signal = false;
   down_signal = false;
   exit_up = false;
   exit_down = false;

   if(G_TrendFastMAHandle == INVALID_HANDLE || G_TrendSlowMAHandle == INVALID_HANDLE)
      return false;

   int slope_lb = MathMax(1, InpTrendSlowSlopeLookback);
   int need = slope_lb + 1;

   double fast[];
   double slow[];
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(slow, true);

   if(CopyBuffer(G_TrendFastMAHandle, 0, 1, need, fast) < need)
      return false;
   if(CopyBuffer(G_TrendSlowMAHandle, 0, 1, need, slow) < need)
      return false;

   double close1 = iClose(_Symbol, InpTrendTimeframe, 1);
   if(close1 <= 0.0)
      return false;

   bool breakout_up = true;
   bool breakout_down = true;
   double prev_high = 0.0;
   double prev_low = 0.0;

   int breakout_bars = InpTrendBreakoutBars;
   if(breakout_bars > 0)
   {
      double highs[];
      double lows[];
      ArraySetAsSeries(highs, true);
      ArraySetAsSeries(lows, true);

      int copied_h = CopyHigh(_Symbol, InpTrendTimeframe, 2, breakout_bars, highs);
      int copied_l = CopyLow (_Symbol, InpTrendTimeframe, 2, breakout_bars, lows);
      if(copied_h < breakout_bars || copied_l < breakout_bars)
         return false;

      int hi_idx = ArrayMaximum(highs, 0, copied_h);
      int lo_idx = ArrayMinimum(lows,  0, copied_l);
      if(hi_idx < 0 || lo_idx < 0)
         return false;

      prev_high = highs[hi_idx];
      prev_low  = lows[lo_idx];

      breakout_up = (close1 > prev_high);
      breakout_down = (close1 < prev_low);
   }

   bool rv_ok = true;
   if(InpTrendUseRVFilter)
      rv_ok = (G_RVRatio >= InpTrendMinRVRatio);

   bool ema_up = (fast[0] > slow[0] && slow[0] > slow[slope_lb]);
   bool ema_down = (fast[0] < slow[0] && slow[0] < slow[slope_lb]);

   up_signal = (rv_ok && ema_up && breakout_up);
   down_signal = (rv_ok && ema_down && breakout_down);

   exit_up = (fast[0] < slow[0]);
   exit_down = (fast[0] > slow[0]);

   if(InpTrendExitOnFastEMA)
   {
      if(close1 < fast[0])
         exit_up = true;
      if(close1 > fast[0])
         exit_down = true;
   }

   G_TrendFastEMA    = fast[0];
   G_TrendSlowEMA    = slow[0];
   G_TrendSlowEMAOld = slow[slope_lb];
   G_TrendLastClose  = close1;
   G_TrendPrevHigh   = prev_high;
   G_TrendPrevLow    = prev_low;

   GetTrendATR(G_TrendATR);

   return true;
}

//+------------------------------------------------------------------+
//| 状态机：更新行情状态                                             |
//+------------------------------------------------------------------+
bool UpdateMarketState(bool force_update)
{
   if(!InpEnableStateMachine)
   {
      G_MarketState = MARKET_STATE_RANGE;
      return true;
   }

   datetime trend_bar = iTime(_Symbol, InpTrendTimeframe, 0);
   if(trend_bar <= 0)
      return false;

   if(!force_update && trend_bar == G_LastTrendCalcBar)
      return true;
   G_LastTrendCalcBar = trend_bar;

   bool up_signal, down_signal, exit_up, exit_down;
   if(!EvaluateTrendSignals(up_signal, down_signal, exit_up, exit_down))
      return false;

   if(up_signal)
      G_TrendUpConfirm++;
   else
      G_TrendUpConfirm = 0;

   if(down_signal)
      G_TrendDownConfirm++;
   else
      G_TrendDownConfirm = 0;

   int confirm_need = MathMax(1, InpTrendConfirmBars);
   ENUM_MARKET_STATE old_state = G_MarketState;
   ENUM_MARKET_STATE new_state = old_state;

   // 反向趋势连续确认优先，其次才是普通退出
   if(G_TrendUpConfirm >= confirm_need)
      new_state = MARKET_STATE_TREND_UP;
   else if(G_TrendDownConfirm >= confirm_need)
      new_state = MARKET_STATE_TREND_DOWN;
   else
   {
      if(old_state == MARKET_STATE_TREND_UP && exit_up)
         new_state = MARKET_STATE_RANGE;
      else if(old_state == MARKET_STATE_TREND_DOWN && exit_down)
         new_state = MARKET_STATE_RANGE;
   }

   if(new_state != old_state)
   {
      G_MarketState = new_state;

      if(InpEnableStateMachineLog)
      {
         Print("状态机切换：", MarketStateToStr(old_state), " -> ", MarketStateToStr(new_state),
               ", close=", DoubleToString(G_TrendLastClose, _Digits),
               ", fastEMA=", DoubleToString(G_TrendFastEMA, _Digits),
               ", slowEMA=", DoubleToString(G_TrendSlowEMA, _Digits),
               ", slowEMA_old=", DoubleToString(G_TrendSlowEMAOld, _Digits),
               ", RVRatio=", DoubleToString(G_RVRatio, 3),
               ", upConfirm=", G_TrendUpConfirm,
               ", downConfirm=", G_TrendDownConfirm);
      }

      // 可选：趋势确认后，直接清理逆势网格仓位。默认关闭，避免一确认趋势就强制砍仓。
      if(InpCloseOppositeGridOnTrend)
      {
         EvaSetExit("trend_close_opposite_grid");   // eva002
         if(new_state == MARKET_STATE_TREND_UP)
            CloseAllPositions(POSITION_TYPE_SELL);
         else if(new_state == MARKET_STATE_TREND_DOWN)
            CloseAllPositions(POSITION_TYPE_BUY);
      }
   }

   return true;
}

//+------------------------------------------------------------------+
//| 趋势模块：取得ATR                                                |
//+------------------------------------------------------------------+
bool GetTrendATR(double &atr)
{
   atr = 0.0;
   if(G_TrendATRHandle == INVALID_HANDLE)
      return false;

   double atr_buf[];
   ArraySetAsSeries(atr_buf, true);
   if(CopyBuffer(G_TrendATRHandle, 0, 1, 1, atr_buf) < 1)
      return false;

   atr = atr_buf[0];
   return (atr > 0.0);
}

//+------------------------------------------------------------------+
//| 趋势模块：统计趋势单                                             |
//+------------------------------------------------------------------+
int CountTrendPositions(ENUM_POSITION_TYPE type)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpTrendMagicNum)
         continue;
      if(PositionGetInteger(POSITION_TYPE) == type)
         count++;
   }
   return count;
}

int CountAllTrendPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpTrendMagicNum)
         continue;
      count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| 趋势模块：趋势单手数                                             |
//+------------------------------------------------------------------+
double GetTrendOrderLot()
{
   if(InpTrendUseGridLot)
      return GetCurrentOrderLot();
   return NormalizeVolumeToSymbol(InpTrendLotSize);
}

//+------------------------------------------------------------------+
//| 趋势模块：开独立趋势多单                                         |
//+------------------------------------------------------------------+
bool OpenTrendBuyOrder(double lot, double ask, double atr)
{
   lot = NormalizeVolumeToSymbol(lot);
   if(lot <= 0.0 || atr <= 0.0)
      return false;

   if(InpCheckTradeModeBeforeOpen && !IsSymbolOpenAllowed(POSITION_TYPE_BUY))
      return false;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist = MathMax((double)stops_level * point, point);

   double sl_dist = MathMax(InpTrendSL_ATR_Mult * atr, min_dist);
   double sl = NormalizeDouble(ask - sl_dist, _Digits);

   double tp = 0.0;
   if(InpTrendTP_ATR_Mult > 0.0)
   {
      double tp_dist = MathMax(InpTrendTP_ATR_Mult * atr, min_dist);
      tp = NormalizeDouble(ask + tp_dist, _Digits);
   }

   trade.SetExpertMagicNumber(InpTrendMagicNum);
   bool ok = trade.Buy(lot, _Symbol, ask, sl, tp, "VPG Trend Buy");
   long ret = trade.ResultRetcode();
   trade.SetExpertMagicNumber(InpMagicNum);

   if(!ok || !IsTradeRetcodeSuccess(ret))
   {
      LogTradeFailure("Trend Buy");
      return false;
   }
   EvaCaptureTrendPending(+1, atr); EvaBindEntry(InpTrendMagicNum);   // eva002
   return true;
}

//+------------------------------------------------------------------+
//| 趋势模块：开独立趋势空单                                         |
//+------------------------------------------------------------------+
bool OpenTrendSellOrder(double lot, double bid, double atr)
{
   lot = NormalizeVolumeToSymbol(lot);
   if(lot <= 0.0 || atr <= 0.0)
      return false;

   if(InpCheckTradeModeBeforeOpen && !IsSymbolOpenAllowed(POSITION_TYPE_SELL))
      return false;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist = MathMax((double)stops_level * point, point);

   double sl_dist = MathMax(InpTrendSL_ATR_Mult * atr, min_dist);
   double sl = NormalizeDouble(bid + sl_dist, _Digits);

   double tp = 0.0;
   if(InpTrendTP_ATR_Mult > 0.0)
   {
      double tp_dist = MathMax(InpTrendTP_ATR_Mult * atr, min_dist);
      tp = NormalizeDouble(bid - tp_dist, _Digits);
      if(tp <= 0.0)
         tp = point;
   }

   trade.SetExpertMagicNumber(InpTrendMagicNum);
   bool ok = trade.Sell(lot, _Symbol, bid, sl, tp, "VPG Trend Sell");
   long ret = trade.ResultRetcode();
   trade.SetExpertMagicNumber(InpMagicNum);

   if(!ok || !IsTradeRetcodeSuccess(ret))
   {
      LogTradeFailure("Trend Sell");
      return false;
   }
   EvaCaptureTrendPending(-1, atr); EvaBindEntry(InpTrendMagicNum);   // eva002
   return true;
}

//+------------------------------------------------------------------+
//| 趋势模块：平掉某方向趋势单                                       |
//+------------------------------------------------------------------+
void CloseTrendPositions(ENUM_POSITION_TYPE type)
{
   trade.SetExpertMagicNumber(InpTrendMagicNum);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpTrendMagicNum)
         continue;
      if(PositionGetInteger(POSITION_TYPE) != type)
         continue;

      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      CloseTicket(ticket);
   }
   trade.SetExpertMagicNumber(InpMagicNum);
}

void CloseAllTrendPositions()
{
   trade.SetExpertMagicNumber(InpTrendMagicNum);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpTrendMagicNum)
         continue;

      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      CloseTicket(ticket);
   }
   trade.SetExpertMagicNumber(InpMagicNum);
}

//+------------------------------------------------------------------+
//| 趋势模块：ATR移动止损                                            |
//+------------------------------------------------------------------+
void ManageTrendTrailing()
{
   if(!InpEnableTrendOrders || InpTrendTrail_ATR_Mult <= 0.0)
      return;

   double atr;
   if(!GetTrendATR(atr) || atr <= 0.0)
      return;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   int stops_level = (int)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double min_dist = MathMax((double)stops_level * point, point);
   double trail_dist = MathMax(InpTrendTrail_ATR_Mult * atr, min_dist);

   trade.SetExpertMagicNumber(InpTrendMagicNum);

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpTrendMagicNum)
         continue;

      ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      double old_sl = PositionGetDouble(POSITION_SL);
      double old_tp = PositionGetDouble(POSITION_TP);

      if(type == POSITION_TYPE_BUY)
      {
         double new_sl = NormalizeDouble(bid - trail_dist, _Digits);
         if((old_sl <= 0.0 || new_sl > old_sl + point) && new_sl < bid - min_dist + point * 0.1)
         {
            if(!trade.PositionModify(ticket, new_sl, old_tp) && InpEnableLog)
               LogTradeFailure("Trend Trail Buy");
         }
      }
      else if(type == POSITION_TYPE_SELL)
      {
         double new_sl = NormalizeDouble(ask + trail_dist, _Digits);
         if((old_sl <= 0.0 || new_sl < old_sl - point) && new_sl > ask + min_dist - point * 0.1)
         {
            if(!trade.PositionModify(ticket, new_sl, old_tp) && InpEnableLog)
               LogTradeFailure("Trend Trail Sell");
         }
      }
   }

   trade.SetExpertMagicNumber(InpMagicNum);
}

//+------------------------------------------------------------------+
//| 趋势模块：按状态开/平趋势单                                      |
//+------------------------------------------------------------------+
void ManageTrendOrders(ENUM_RISK_LEVEL risk_level)
{
   if(!InpEnableStateMachine || !InpEnableTrendOrders)
      return;

   // 状态退出时，趋势单不再按网格基线平仓，而是独立退出
   if(InpTrendCloseOnStateExit)
   {
      EvaSetExit("trend_state_exit");   // eva002
      if(G_MarketState == MARKET_STATE_RANGE)
         CloseAllTrendPositions();
      else if(G_MarketState == MARKET_STATE_TREND_UP)
         CloseTrendPositions(POSITION_TYPE_SELL);
      else if(G_MarketState == MARKET_STATE_TREND_DOWN)
         CloseTrendPositions(POSITION_TYPE_BUY);
   }

   if(InpTrendRespectRiskGate && risk_level >= RISK_LEVEL_2_LIMIT)
      return;

   if(InpTrendRespectCooldown && IsInCooldown())
      return;

   int max_pos = MathMax(1, InpTrendMaxPositions);
   int total_trend = CountAllTrendPositions();
   if(total_trend >= max_pos)
      return;

   double atr;
   if(!GetTrendATR(atr) || atr <= 0.0)
      return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double lot = GetTrendOrderLot();

   if(G_MarketState == MARKET_STATE_TREND_UP)
   {
      if(CountTrendPositions(POSITION_TYPE_BUY) <= 0)
         OpenTrendBuyOrder(lot, ask, atr);
   }
   else if(G_MarketState == MARKET_STATE_TREND_DOWN)
   {
      if(CountTrendPositions(POSITION_TYPE_SELL) <= 0)
         OpenTrendSellOrder(lot, bid, atr);
   }
}

//+------------------------------------------------------------------+
//| 取得当前应下手数                                                 |
//+------------------------------------------------------------------+
double GetCurrentOrderLot()
{
   if(!InpUseDynamicLot)
      return NormalizeVolumeToSymbol(G_ActiveParams.lot_size);

   if(InpDynBaseCapital <= 0.0 || InpDynBaseLotStep <= 0.0 || InpDynLevelCoef <= 0.0)
      return NormalizeVolumeToSymbol(G_ActiveParams.lot_size);

   double capital = GetLotCapitalReference();

   int level = 0;
   for(int i = 1; i <= 1000; i++)
   {
      double need_capital = GetRequiredCapitalForLevel(i);
      if(capital + 1e-8 >= need_capital)
         level = i;
      else
         break;
   }

   if(level <= 0)
   {
      if(InpEnableLog)
      {
         Print("动态手数：当前资金不足首档开仓要求，capital=",
               DoubleToString(capital, 2),
               ", need=",
               DoubleToString(GetRequiredCapitalForLevel(1), 2));
      }
      return 0.0;
   }

   double lot = level * InpDynBaseLotStep;

   if(InpDynMaxLot > 0.0 && lot > InpDynMaxLot)
      lot = InpDynMaxLot;

   lot = NormalizeVolumeToSymbol(lot);

   if(InpEnableLog)
   {
      Print("动态手数：capital=", DoubleToString(capital, 2),
            ", level=", level,
            ", lot=", DoubleToString(lot, GetVolumeDigits(SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP))));
   }

   return lot;
}

//+------------------------------------------------------------------+
//| 封装：开多                                                       |
//+------------------------------------------------------------------+
bool OpenBuyOrder(double lot, double ask, double tp_dist, string comment)
{
   lot = NormalizeVolumeToSymbol(lot);

   if(lot <= 0.0)
   {
      if(InpEnableLog)
         Print("Buy取消：手数规整后 <= 0");
      return false;
   }

   // v0.99：开仓前检查品种是否允许开多（close-only/禁用/仅空 时跳过，规避 retcode 10044）
   if(InpCheckTradeModeBeforeOpen && !IsSymbolOpenAllowed(POSITION_TYPE_BUY))
   {
      if(InpEnableLog)
         Print("Buy取消：当前品种不允许开多(可能为 close-only / 交易禁用 / 仅空)。");
      return false;
   }

   bool ok = trade.Buy(lot, _Symbol, ask, 0, ask + tp_dist, comment);
   if(!ok || !IsTradeRetcodeSuccess(trade.ResultRetcode()))
   {
      LogTradeFailure("Buy");
      return false;
   }
   EvaBindEntry(InpMagicNum);   // eva002：把抓拍上下文绑定到刚成交的持仓
   return true;
}

//+------------------------------------------------------------------+
//| 封装：开空                                                       |
//+------------------------------------------------------------------+
bool OpenSellOrder(double lot, double bid, double tp_dist, string comment)
{
   lot = NormalizeVolumeToSymbol(lot);

   if(lot <= 0.0)
   {
      if(InpEnableLog)
         Print("Sell取消：手数规整后 <= 0");
      return false;
   }

   double tp_price = bid - tp_dist;

   // v1.93：做空止盈价为负（极大multiplier_a时可能发生）则改为极小正数，
   // 等价于"实际触不到的止盈"，靠基线回归平仓，不影响下单。
   if(tp_price <= 0.0)
      tp_price = _Point;

   // v0.99：开仓前检查品种是否允许开空（close-only/禁用/仅多 时跳过，规避 retcode 10044）
   if(InpCheckTradeModeBeforeOpen && !IsSymbolOpenAllowed(POSITION_TYPE_SELL))
   {
      if(InpEnableLog)
         Print("Sell取消：当前品种不允许开空(可能为 close-only / 交易禁用 / 仅多)。");
      return false;
   }

   bool ok = trade.Sell(lot, _Symbol, bid, 0, tp_price, comment);
   if(!ok || !IsTradeRetcodeSuccess(trade.ResultRetcode()))
   {
      LogTradeFailure("Sell");
      return false;
   }
   EvaBindEntry(InpMagicNum);   // eva002：把抓拍上下文绑定到刚成交的持仓
   return true;
}

//+------------------------------------------------------------------+
//| 封装：平单                                                       |
//+------------------------------------------------------------------+
bool CloseTicket(ulong ticket)
{
   bool ok = trade.PositionClose(ticket);
   if(!ok || !IsTradeRetcodeSuccess(trade.ResultRetcode()))
   {
      LogTradeFailure("Close ticket " + IntegerToString((long)ticket));
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| 常驻止损：达到当前档位最大持仓数后，最后一单亏损过大则全平+冷静期 |
//+------------------------------------------------------------------+
bool CheckLastOrderStopAndCooldown(const StrategySnapshot &snap)
{
   if(G_ActiveParams.max_total_positions <= 0)
      return false;

   if(snap.total_count < G_ActiveParams.max_total_positions)
      return false;

   if(snap.last_ticket == 0)
      return false;

   if(snap.last_open_profit >= 0.0)
      return false;

   bool stop_hit = false;

   if(G_ActiveParams.last_order_loss_per_lot <= 0.0)
   {
      stop_hit = true;
   }
   else
   {
      double max_loss = G_ActiveParams.last_order_loss_per_lot * snap.last_open_volume;
      if((-snap.last_open_profit) >= max_loss)
         stop_hit = true;
   }

   if(!stop_hit)
      return false;

   if(InpEnableLog)
      Print("触发常驻止损：达到当前波动档位最大持仓数后，最后一单亏损过大，全平 + 冷静期。");

   EvaSetExit("last_order_stop");   // eva002
   CloseAllStrategyPositions();
   StartCooldown(!G_HadProfitSinceLastCooldown);

   return true;
}

//+------------------------------------------------------------------+
//| 获取某一单序号所需等待分钟数                                     |
//+------------------------------------------------------------------+
int GetRequiredDelayMinutes(int next_order_number)
{
   switch(next_order_number)
   {
      case 2: return G_ActiveParams.delay_order2_minutes;
      case 3: return G_ActiveParams.delay_order3_minutes;
      case 4: return G_ActiveParams.delay_order4_minutes;
      case 5: return G_ActiveParams.delay_order5_minutes;
      case 6: return G_ActiveParams.delay_order6_minutes;
      default: return 0;
   }
}

//+------------------------------------------------------------------+
//| 加仓延迟门闸（eva020：pacing_panic 已删，单边改由趋势状态机处理）   |
//+------------------------------------------------------------------+
ENUM_ADD_PACING_RESULT CheckAddPacingDelay(ENUM_POSITION_TYPE type,
                                                   const StrategySnapshot &snap,
                                                   double multiplier_a,
                                                   double current_price,
                                                   double point)
{
   int current_side_count = (type == POSITION_TYPE_BUY) ? snap.buy_count : snap.sell_count;

   if(current_side_count <= 0)
      return ADD_PACING_ALLOW;

   int next_order_number = current_side_count + 1;

   if(G_ActiveParams.max_total_positions > 0 && next_order_number > G_ActiveParams.max_total_positions)
      return ADD_PACING_ALLOW;

   datetime last_open_time = (type == POSITION_TYPE_BUY) ? snap.last_buy_time : snap.last_sell_time;

   if(last_open_time <= 0)
      return ADD_PACING_ALLOW;

   int delay_minutes = GetRequiredDelayMinutes(next_order_number);
   if(delay_minutes <= 0)
      return ADD_PACING_ALLOW;

   datetime now = TimeTradeServer();
   if(now >= last_open_time + delay_minutes * 60)
      return ADD_PACING_ALLOW;

   // eva020：原 pacing_panic（加仓延迟期内价格已冲到下下单区域 → 全平止损）已删除。
   //   该机制本是用"价格在很短时间冲过下下单位置"来判定单边行情并止损；现改由趋势
   //   状态机识别单边、平掉逆势网格来替代。此处仅保留"加仓延迟门闸"：未到延迟时间→暂不加仓。
   return ADD_PACING_BLOCK;
}

//+------------------------------------------------------------------+
//| 平掉盈利达到阈值的仓位                                           |
//+------------------------------------------------------------------+
void CloseProfitablePositionsByThreshold(double profit_per_lot)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNum)
         continue;

      double volume = PositionGetDouble(POSITION_VOLUME);
      double profit = GetSelectedPositionFloatingProfit();

      if(profit <= 0.0)
         continue;

      bool need_close = (profit_per_lot <= 0.0 || profit >= profit_per_lot * volume);
      if(need_close)
      {
         ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
         CloseTicket(ticket);
      }
   }
}

//+------------------------------------------------------------------+
//| 平掉亏损达到阈值的仓位                                           |
//+------------------------------------------------------------------+
void CloseLosingPositionsByThreshold(double loss_per_lot)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNum)
         continue;

      double volume = PositionGetDouble(POSITION_VOLUME);
      double profit = GetSelectedPositionFloatingProfit();

      if(profit >= 0.0)
         continue;

      bool need_close = (loss_per_lot <= 0.0 || (-profit) >= loss_per_lot * volume);
      if(need_close)
      {
         ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
         CloseTicket(ticket);
      }
   }
}

//+------------------------------------------------------------------+
//| 获取当前风险等级                                                 |
//+------------------------------------------------------------------+
ENUM_RISK_LEVEL GetCurrentRiskLevel(double avg_volume_per_min)
{
   int level = (int)RISK_LEVEL_1_NORMAL;

   if(avg_volume_per_min > G_ActiveParams.max_avg_volume_per_min)
      level = (int)RISK_LEVEL_2_LIMIT;

   if(InpUseWeekendGuard)
   {
      int weekend_level = GetWeekendRiskLevel();
      if(weekend_level > level)
         level = weekend_level;
   }

   return (ENUM_RISK_LEVEL)level;
}

//+------------------------------------------------------------------+
//| 周末时段风险等级                                                 |
//+------------------------------------------------------------------+
int GetWeekendRiskLevel()
{
   if(G_MondayFirstOpenSec < 0 || G_FridayLastCloseSec < 0 || G_WeekReopenDow < 0)
      LoadSessionGuardTimes();

   datetime now = TimeTradeServer();
   MqlDateTime tm;
   TimeToStruct(now, tm);

   int now_sec = tm.hour * 3600 + tm.min * 60 + tm.sec;

   if(tm.day_of_week == FRIDAY && G_FridayLastCloseSec > 0)
   {
      int level4_start = MathMax(0, G_FridayLastCloseSec - InpFridayForceCloseMinutes * 60);
      int level3_start = MathMax(0, G_FridayLastCloseSec - InpFridayCloseOnlyMinutes * 60);

      if(now_sec >= level4_start && now_sec < G_FridayLastCloseSec)
         return (int)RISK_LEVEL_4_EXIT;

      if(now_sec >= level3_start && now_sec < level4_start)
         return (int)RISK_LEVEL_3_REDUCE;
   }

   // v0.99：每周市场重开后 N 分钟禁开仓（二级风险）。
   // 不再写死"周一"，而是用服务器会话表识别的真实重开时刻(黄金=周日晚)，
   // 并用绝对时间比较，自动跨越午夜(如周日22:00 + 180min 落到周一01:00)。
   if(G_WeekReopenDow >= 0 && G_WeekReopenSec >= 0 && InpMondayNoOpenMinutes > 0)
   {
      datetime reopen_dt = MostRecentWeekdaySecAtOrBefore(now, G_WeekReopenDow, G_WeekReopenSec);
      if(reopen_dt > 0)
      {
         datetime l2_end = reopen_dt + (datetime)InpMondayNoOpenMinutes * 60;
         if(now >= reopen_dt && now < l2_end)
            return (int)RISK_LEVEL_2_LIMIT;
      }
   }

   return (int)RISK_LEVEL_1_NORMAL;
}

//+------------------------------------------------------------------+
//| 平某一方向仓位                                                   |
//+------------------------------------------------------------------+
void CloseAllPositions(ENUM_POSITION_TYPE type)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNum)
         continue;

      if(PositionGetInteger(POSITION_TYPE) != type)
         continue;

      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      CloseTicket(ticket);
   }
}

//+------------------------------------------------------------------+
//| 平掉本策略当前品种的全部仓位                                     |
//+------------------------------------------------------------------+
void CloseAllStrategyPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNum)
         continue;

      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
      CloseTicket(ticket);
   }
}

//+------------------------------------------------------------------+
//| 平掉本策略当前品种最新的一笔仓位                                 |
//+------------------------------------------------------------------+
bool CloseNewestStrategyPosition()
{
   ulong newest_ticket = 0;
   datetime newest_time = 0;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNum)
         continue;

      datetime open_time = (datetime)PositionGetInteger(POSITION_TIME);
      ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);

      if(newest_ticket == 0 || open_time >= newest_time)
      {
         newest_time = open_time;
         newest_ticket = ticket;
      }
   }

   if(newest_ticket == 0)
      return false;

   return CloseTicket(newest_ticket);
}

//+------------------------------------------------------------------+
//| 当前档位无法保留的仓位处理                                       |
//+------------------------------------------------------------------+
bool ClosePositionsNotAllowedByActiveProfile(const StrategySnapshot &snap)
{
   int max_allowed = G_ActiveParams.max_total_positions;

   if(max_allowed <= 0)
      return false;

   if(snap.total_count <= max_allowed)
      return false;

   int excess = snap.total_count - max_allowed;

   if(InpEnableLog)
   {
      Print("当前波动档位无法保留全部仓位：total=",
            snap.total_count,
            ", max_allowed=",
            max_allowed,
            ", 将平掉最新的多余仓位数量=",
            excess);
   }

   for(int k = 0; k < excess; k++)
      CloseNewestStrategyPosition();

   return true;
}

//+------------------------------------------------------------------+
//| 更新历史交易量                                                   |
//+------------------------------------------------------------------+
void UpdateHistoricVolumeSum()
{
   G_HistoricVolumeSum = 0;
   int historic_bars = MathMax(1, G_ActiveParams.avg_volume_minutes) - 1;

   if(historic_bars > 0)
   {
      long volumes[];
      if(CopyTickVolume(_Symbol, PERIOD_M1, 1, historic_bars, volumes) == historic_bars)
      {
         for(int i = 0; i < historic_bars; i++)
            G_HistoricVolumeSum += volumes[i];
      }
   }
}

//+------------------------------------------------------------------+
//| 统计某一方向持仓                                                 |
//+------------------------------------------------------------------+
int CountPositions(ENUM_POSITION_TYPE type)
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      string symbol = PositionGetSymbol(i);
      if(symbol != _Symbol)
         continue;

      if(PositionGetInteger(POSITION_MAGIC) != InpMagicNum)
         continue;

      if(PositionGetInteger(POSITION_TYPE) == type)
         count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| 取得当天秒数                                                     |
//+------------------------------------------------------------------+
int SecondsOfDay(datetime t)
{
   MqlDateTime tm;
   TimeToStruct(t, tm);
   return (tm.hour * 3600 + tm.min * 60 + tm.sec);
}

//+------------------------------------------------------------------+
//| 读取指定星期的交易时段                                           |
//+------------------------------------------------------------------+
bool GetDaySessionBounds(ENUM_DAY_OF_WEEK day, int &first_open_sec, int &last_close_sec)
{
   first_open_sec = -1;
   last_close_sec = -1;

   datetime from, to;

   for(uint i = 0; ; i++)
   {
      if(!SymbolInfoSessionTrade(_Symbol, day, i, from, to))
         break;

      int from_sec = SecondsOfDay(from);
      int to_sec   = SecondsOfDay(to);

      if(to_sec == 0 && from_sec > 0)
         to_sec = 24 * 3600;

      if(first_open_sec < 0 || from_sec < first_open_sec)
         first_open_sec = from_sec;

      if(last_close_sec < 0 || to_sec > last_close_sec)
         last_close_sec = to_sec;
   }

   return (first_open_sec >= 0 && last_close_sec >= 0);
}

//+------------------------------------------------------------------+
//| 载入周一/周五交易时段缓存                                        |
//+------------------------------------------------------------------+
bool LoadSessionGuardTimes()
{
   int monday_open = -1, monday_close = -1;
   int friday_open = -1, friday_close = -1;

   bool ok_mon = GetDaySessionBounds(MONDAY, monday_open, monday_close);
   bool ok_fri = GetDaySessionBounds(FRIDAY, friday_open, friday_close);

   if(ok_mon)
      G_MondayFirstOpenSec = monday_open;

   if(ok_fri)
      G_FridayLastCloseSec = friday_close;

   // v0.99：识别"每周市场重开"所在星期与秒数（直接读服务器会话表）。
   // 规则：周末缺口后的第一个有会话的交易日即重开日。
   //   - 黄金/外汇等：周日通常已有会话(如周日22:00~24:00) → 重开日=周日。
   //   - 若周日无会话：退回到周一首个开盘 → 重开日=周一。
   G_WeekReopenDow = -1;
   G_WeekReopenSec = -1;

   int sun_open = -1, sun_close = -1;
   if(GetDaySessionBounds(SUNDAY, sun_open, sun_close) && sun_open >= 0)
   {
      G_WeekReopenDow = (int)SUNDAY;   // 0
      G_WeekReopenSec = sun_open;
   }
   else if(ok_mon && monday_open >= 0)
   {
      G_WeekReopenDow = (int)MONDAY;   // 1
      G_WeekReopenSec = monday_open;
   }

   if(!ok_mon || !ok_fri)
   {
      Print("警告：无法读取交易时段，周末保护可能不会生效。");
      return false;
   }

   if(InpEnableLog)
      Print("每周重开识别：重开星期=", G_WeekReopenDow,
            "(0=周日 1=周一)，重开秒=", G_WeekReopenSec,
            " (", G_WeekReopenSec/3600, "时", (G_WeekReopenSec%3600)/60, "分, 服务器时间)");

   return true;
}

//+------------------------------------------------------------------+
//| v0.99：取 now 之前(含当下)最近一次"指定星期+当天秒数"的绝对时刻   |
//| 用于把"重开星期+重开秒"换算成可与 now 直接比较的服务器绝对时间。 |
//+------------------------------------------------------------------+
datetime MostRecentWeekdaySecAtOrBefore(datetime now, int target_dow, int target_sec)
{
   if(target_dow < 0 || target_sec < 0)
      return 0;

   MqlDateTime tm;
   TimeToStruct(now, tm);

   int now_dow = tm.day_of_week;                       // 0=周日 ... 6=周六
   int now_sec = tm.hour * 3600 + tm.min * 60 + tm.sec;

   datetime today_midnight = now - now_sec;            // 今日 00:00:00（服务器）
   int days_back = (now_dow - target_dow + 7) % 7;     // 回退到目标星期需要的天数

   datetime cand = today_midnight - (datetime)days_back * 86400 + (datetime)target_sec;

   // 若算出的时刻还在未来（目标星期=今天但秒数大于当前），回退一周到上一次重开
   if(cand > now)
      cand -= 7 * 86400;

   return cand;
}

//+------------------------------------------------------------------+
//| v0.99：当前品种是否允许"开新仓"（区分多/空方向）                 |
//| 仅 SYMBOL_TRADE_MODE_FULL 允许双向开仓；LONGONLY/SHORTONLY 仅对  |
//| 应方向；CLOSEONLY/DISABLED 一律禁止 → 规避每日/每周重开瞬间10044。|
//+------------------------------------------------------------------+
bool IsSymbolOpenAllowed(ENUM_POSITION_TYPE type)
{
   long mode = (long)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE);

   switch((int)mode)
   {
      case SYMBOL_TRADE_MODE_FULL:      return true;
      case SYMBOL_TRADE_MODE_LONGONLY:  return (type == POSITION_TYPE_BUY);
      case SYMBOL_TRADE_MODE_SHORTONLY: return (type == POSITION_TYPE_SELL);
      default:                          return false; // DISABLED / CLOSEONLY
   }
}

//+------------------------------------------------------------------+
//| v0.99：与开仓逻辑一致的放大倍数计算（供越界止损复用）            |
//+------------------------------------------------------------------+
double ComputeMultiplierA(double avg_volume_per_min)
{
   double multiplier_a = 1.0;
   if(G_ActiveParams.base_avg_volume_per_min > 0.0)
   {
      double raw_multiplier = avg_volume_per_min / G_ActiveParams.base_avg_volume_per_min;

      if(raw_multiplier > 0.0 && InpMultiplierExp > 0.0 && InpMultiplierExp != 1.0)
         multiplier_a = MathPow(raw_multiplier, InpMultiplierExp);
      else
         multiplier_a = raw_multiplier;

      if(multiplier_a < 1.0)
         multiplier_a = 1.0;
   }
   return multiplier_a;
}

//+------------------------------------------------------------------+
//| v0.99：市场重开(每日收盘/每周缺口)后按需把基线重算到现价附近     |
//| 仅在"空仓"时执行，避免持仓中重算基线打乱网格/止盈与平仓判定。   |
//| 通过相邻 M1 柱时间缺口识别重开；该判定只影响基线，不禁开仓，     |
//| 故不会因极端行情误拦交易。                                       |
//+------------------------------------------------------------------+
void MaybeResetBaselineOnReopen(datetime new_bar_time)
{
   if(!InpResetBaselineOnReopen)
   {
      G_PrevM1BarTime = new_bar_time;
      return;
   }

   if(G_PrevM1BarTime > 0 && InpReopenGapMinutes > 0)
   {
      int gap_sec = (int)(new_bar_time - G_PrevM1BarTime);
      if(gap_sec >= InpReopenGapMinutes * 60)
      {
         // 仅空仓时重置（避免持仓中改基线打乱网格/止盈/平仓判定）
         StrategySnapshot s;
         BuildStrategySnapshot(s);
         if(s.total_count == 0)
         {
            double mid = (SymbolInfoDouble(_Symbol, SYMBOL_BID) +
                          SymbolInfoDouble(_Symbol, SYMBOL_ASK)) / 2.0;
            if(mid > 0.0)
            {
               G_Baseline = NormalizeDouble(mid, _Digits);
               G_BaselineReady = true;
               SaveBaselineToGlobal();   // 持久化
               UpdateBaselineLine();     // 刷新图线
               if(InpEnableLog)
                  Print("市场重开(缺口=", gap_sec / 60, "分钟)且空仓 → 基线已重置到现价：",
                        DoubleToString(G_Baseline, _Digits));
            }
         }
         else if(InpEnableLog)
         {
            Print("市场重开(缺口=", gap_sec / 60, "分钟)但持仓中 → 不重置基线。");
         }
      }
   }

   G_PrevM1BarTime = new_bar_time;
}

//+------------------------------------------------------------------+
//| v0.99：开满上限单数后的"越界止损"（可选）                        |
//| 已开满 max 单后，占优方向若再一口气冲过【下一单 + 下下单】的合计 |
//| 网格距(≈第 max+2 单位置)→ 全平 + 冷静期。沿用恐慌平仓的距离口径。|
//+------------------------------------------------------------------+
//==================================================================
//  === eva002 审计日志模块（实现） ===
//  设计要点：
//   1) 不参与任何交易决策；G_EvaActive 关闭时所有函数立即返回。
//   2) 优化(Optimization)模式强制关闭，避免多 pass 抢占同一文件。
//   3) 进场上下文在下单点抓拍(G_EvaPending)，下单成功后用 EvaBindEntry
//      绑定到 position_id；平仓在 OnTradeTransaction 落盘成一行。
//   4) 出场原因优先用券商/测试器给的 DEAL_REASON(tp/sl)，EA 主动平仓
//      则用平仓前 EvaSetExit 设置的细分原因。
//==================================================================

//--- 周期字符串
string EvaPeriodStr(ENUM_TIMEFRAMES tf)
{
   string s = EnumToString(tf);          // 形如 PERIOD_M5
   string pre = "PERIOD_";
   int p = StringFind(s, pre);
   if(p == 0) s = StringSubstr(s, StringLen(pre));
   return s;
}

//--- CSV 字段转义(含逗号/引号/换行时加引号)
string EvaCsv(string s)
{
   bool need = (StringFind(s, ",") >= 0 || StringFind(s, "\"") >= 0 ||
                StringFind(s, "\n") >= 0 || StringFind(s, "\r") >= 0);
   if(!need) return s;
   string out = "";
   int n = StringLen(s);
   for(int i = 0; i < n; i++)
   {
      ushort c = StringGetCharacter(s, i);
      if(c == '"') out += "\"\"";
      else         out += ShortToString(c);
   }
   return "\"" + out + "\"";
}

string EvaTimeIso(datetime t){ return TimeToString(t, TIME_DATE | TIME_SECONDS); }

//--- 出场原因设置(EA 主动平仓前调用)
void EvaSetExit(string reason)
{
   if(!G_EvaActive) return;
   G_EvaExitReason = reason;
}

//--- 持仓记录表：按 position_id 查找/新建槽位
int EvaFindOpenSlot(ulong position_id)
{
   int n = ArraySize(G_EvaOpen);
   for(int i = 0; i < n; i++)
      if(G_EvaOpen[i].used && G_EvaOpen[i].position_id == position_id)
         return i;
   return -1;
}
int EvaNewOpenSlot()
{
   int n = ArraySize(G_EvaOpen);
   for(int i = 0; i < n; i++)
      if(!G_EvaOpen[i].used)
         return i;
   ArrayResize(G_EvaOpen, n + 1);
   G_EvaOpen[n].used = false;
   return n;
}

//--- 用当前全局状态填充“环境快照”到 pending
void EvaFillEnv(EvaPendingCtx &c)
{
   c.vol_regime          = (int)G_VolRegime;
   c.real_vol_regime     = (int)G_RealVolRegime;
   c.regime_open_allowed = G_RegimeOpenAllowed;
   c.market_state        = (int)G_MarketState;
   c.rv_short_pts        = G_RVShortPoints;
   c.rv_long_pts         = G_RVLongPoints;
   c.rv_ratio            = G_RVRatio;
   c.baseline            = G_Baseline;
   c.risk_level          = G_LastRiskLevel;
   c.avg_vol_per_min     = G_EvaAvgVolForLog;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double pt  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   c.spread_pts = (pt > 0 ? (ask - bid) / pt : 0.0);
   c.atr        = G_TrendATR;
}

//--- 抓拍网格进场上下文(下单点调用)
void EvaCaptureGridPending(int dir, int order_number, double mult,
                           double grid_dist_pts, double tp_dist_pts)
{
   if(!G_EvaActive) return;
   EvaPendingCtx c;
   c.valid        = true;
   c.magic        = InpMagicNum;
   c.direction    = dir;
   c.order_kind   = "grid";
   c.entry_reason = (dir > 0 ? "grid_buy" : "grid_sell");
   c.order_number = order_number;
   c.multiplier_a = mult;
   c.grid_dist_pts= grid_dist_pts;
   c.tp_dist_pts  = tp_dist_pts;
   EvaFillEnv(c);
   G_EvaPending = c;
   // 同步写一条“放行”的决策审计
   EvaWriteDecisionAudit(dir, order_number, mult, grid_dist_pts, true, "opened");
}

//--- 抓拍趋势进场上下文(趋势开仓函数内调用)
void EvaCaptureTrendPending(int dir, double atr)
{
   if(!G_EvaActive) return;
   EvaPendingCtx c;
   c.valid        = true;
   c.magic        = InpTrendMagicNum;
   c.direction    = dir;
   c.order_kind   = "trend";
   c.entry_reason = (dir > 0 ? "trend_buy" : "trend_sell");
   c.order_number = 1;
   c.multiplier_a = 1.0;
   c.grid_dist_pts= 0.0;
   c.tp_dist_pts  = 0.0;
   EvaFillEnv(c);
   c.atr = atr;
   G_EvaPending = c;
}

//--- 下单成功后：把 pending 绑定到刚成交的持仓
void EvaBindEntry(long magic)
{
   if(!G_EvaActive) return;
   if(!G_EvaPending.valid) return;

   ulong pos_id = trade.ResultOrder();        // 对冲账户：开仓订单号==持仓号
   ulong deal   = trade.ResultDeal();
   datetime etime = TimeCurrent();
   long etime_msc = (long)TimeCurrent() * 1000;
   double eprice = 0.0, evol = 0.0, sl = 0.0, tp = 0.0;

   if(deal > 0 && HistoryDealSelect(deal))
   {
      if(pos_id == 0) pos_id = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      eprice    = HistoryDealGetDouble(deal, DEAL_PRICE);
      evol      = HistoryDealGetDouble(deal, DEAL_VOLUME);
      etime_msc = (long)HistoryDealGetInteger(deal, DEAL_TIME_MSC);
      etime     = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
   }
   // 读取该持仓当前 SL/TP（趋势单有 SL，网格单有 TP）
   if(pos_id > 0 && PositionSelectByTicket(pos_id))
   {
      if(eprice <= 0.0) eprice = PositionGetDouble(POSITION_PRICE_OPEN);
      if(evol   <= 0.0) evol   = PositionGetDouble(POSITION_VOLUME);
      sl = PositionGetDouble(POSITION_SL);
      tp = PositionGetDouble(POSITION_TP);
   }
   if(pos_id == 0) return;   // 无法定位持仓号则放弃(极少见)

   int slot = EvaFindOpenSlot(pos_id);
   if(slot < 0) slot = EvaNewOpenSlot();

   G_EvaOpen[slot].used          = true;
   G_EvaOpen[slot].position_id   = pos_id;
   G_EvaOpen[slot].deal_in       = deal;
   G_EvaOpen[slot].entry_time    = etime;
   G_EvaOpen[slot].entry_time_msc= etime_msc;
   G_EvaOpen[slot].entry_price   = eprice;
   G_EvaOpen[slot].volume        = evol;
   G_EvaOpen[slot].sl_price      = sl;
   G_EvaOpen[slot].tp_price      = tp;
   G_EvaOpen[slot].ctx           = G_EvaPending;

   G_EvaPending.valid = false;   // 消费掉，避免被下一单误用
}

//--- DEAL_REASON → 文本
string EvaDealReasonStr(long r)
{
   switch((int)r)
   {
      case DEAL_REASON_CLIENT:   return "client";
      case DEAL_REASON_EXPERT:   return "expert";
      case DEAL_REASON_SL:       return "sl";
      case DEAL_REASON_TP:       return "tp";
      case DEAL_REASON_SO:       return "stopout";
      default:                   return "other";
   }
}

//--- 成交事件：进场补绑 + 出场落盘
void EvaOnDealAdd(ulong deal)
{
   if(!G_EvaActive) return;
   if(!HistoryDealSelect(deal)) return;

   string sym = HistoryDealGetString(deal, DEAL_SYMBOL);
   if(sym != _Symbol) return;

   long magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
   bool is_grid  = (magic == InpMagicNum);
   bool is_trend = (magic == InpTrendMagicNum);
   if(!is_grid && !is_trend) return;

   long entry = HistoryDealGetInteger(deal, DEAL_ENTRY);
   ulong pos_id = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);

   //=== 进场：若 EvaBindEntry 因某些填充模式未抓到，则在此兜底补一条记录 ===
   if(entry == DEAL_ENTRY_IN)
   {
      if(EvaFindOpenSlot(pos_id) >= 0) return;   // 已绑定，跳过
      int slot = EvaNewOpenSlot();
      G_EvaOpen[slot].used          = true;
      G_EvaOpen[slot].position_id   = pos_id;
      G_EvaOpen[slot].deal_in       = deal;
      G_EvaOpen[slot].entry_time    = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
      G_EvaOpen[slot].entry_time_msc= (long)HistoryDealGetInteger(deal, DEAL_TIME_MSC);
      G_EvaOpen[slot].entry_price   = HistoryDealGetDouble(deal, DEAL_PRICE);
      G_EvaOpen[slot].volume        = HistoryDealGetDouble(deal, DEAL_VOLUME);
      G_EvaOpen[slot].sl_price      = 0.0;
      G_EvaOpen[slot].tp_price      = 0.0;
      EvaPendingCtx c; c.valid = true; c.magic = magic;
      c.direction    = (HistoryDealGetInteger(deal, DEAL_TYPE) == DEAL_TYPE_BUY ? +1 : -1);
      c.order_kind   = (is_trend ? "trend" : "grid");
      c.entry_reason = (is_trend ? "trend_unbound" : "grid_unbound");
      c.order_number = 0; c.multiplier_a = 1.0; c.grid_dist_pts = 0.0; c.tp_dist_pts = 0.0;
      EvaFillEnv(c);
      G_EvaOpen[slot].ctx = c;
      return;
   }

   //=== 出场：落盘一行 ===
   if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
   {
      int slot = EvaFindOpenSlot(pos_id);

      datetime xtime    = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
      long     xtimemsc = (long)HistoryDealGetInteger(deal, DEAL_TIME_MSC);
      double   xprice   = HistoryDealGetDouble(deal, DEAL_PRICE);
      double   profit   = HistoryDealGetDouble(deal, DEAL_PROFIT);
      double   comm     = HistoryDealGetDouble(deal, DEAL_COMMISSION);
      double   swap     = HistoryDealGetDouble(deal, DEAL_SWAP);
      double   net      = profit + comm + swap;
      long     draw     = HistoryDealGetInteger(deal, DEAL_REASON);
      string   drstr    = EvaDealReasonStr(draw);

      // 出场原因：券商/测试器给的 tp/sl/stopout 优先；expert 用我们设置的细分原因
      string exit_reason = drstr;
      if(drstr == "expert" || drstr == "client" || drstr == "other")
         exit_reason = G_EvaExitReason;

      // 取进场上下文(兜底为空)
      EvaOpenRec rec;
      if(slot >= 0) rec = G_EvaOpen[slot];
      else
      {
         rec.used = true; rec.position_id = pos_id; rec.deal_in = 0;
         rec.entry_time = 0; rec.entry_time_msc = 0; rec.entry_price = 0;
         rec.volume = HistoryDealGetDouble(deal, DEAL_VOLUME);
         rec.sl_price = 0; rec.tp_price = 0;
         rec.ctx.valid = false; rec.ctx.magic = magic;
         rec.ctx.direction = (HistoryDealGetInteger(deal, DEAL_TYPE) == DEAL_TYPE_SELL ? +1 : -1);
         rec.ctx.order_kind = (is_trend ? "trend" : "grid");
         rec.ctx.entry_reason = "unknown"; rec.ctx.order_number = 0;
         rec.ctx.multiplier_a = 0; rec.ctx.grid_dist_pts = 0; rec.ctx.tp_dist_pts = 0;
         rec.ctx.vol_regime = -1; rec.ctx.real_vol_regime = -1; rec.ctx.regime_open_allowed = false;
         rec.ctx.market_state = -1; rec.ctx.rv_short_pts = 0; rec.ctx.rv_long_pts = 0;
         rec.ctx.rv_ratio = 0; rec.ctx.baseline = 0; rec.ctx.risk_level = -1;
         rec.ctx.avg_vol_per_min = 0; rec.ctx.spread_pts = 0; rec.ctx.atr = 0;
      }

      long hold_sec = (rec.entry_time > 0 ? (long)(xtime - rec.entry_time) : 0);

      if(G_EvaFhTrades != INVALID_HANDLE)
      {
         FileWrite(G_EvaFhTrades,
            EvaCsv(G_EvaRunId),
            EvaCsv(InpStrategyVersion),
            EvaCsv(InpParamSetId),
            EvaCsv(_Symbol),
            EvaCsv(EvaPeriodStr((ENUM_TIMEFRAMES)Period())),
            (string)pos_id,
            (string)rec.deal_in,
            (string)deal,
            EvaCsv(rec.ctx.order_kind),
            (string)rec.ctx.direction,
            EvaCsv(rec.ctx.entry_reason),
            EvaCsv(exit_reason),
            EvaCsv(drstr),
            (string)rec.ctx.order_number,
            EvaTimeIso(rec.entry_time),
            (string)rec.entry_time_msc,
            DoubleToString(rec.entry_price, _Digits),
            EvaTimeIso(xtime),
            (string)xtimemsc,
            DoubleToString(xprice, _Digits),
            DoubleToString(rec.volume, 2),
            DoubleToString(rec.sl_price, _Digits),
            DoubleToString(rec.tp_price, _Digits),
            DoubleToString(profit, 2),
            DoubleToString(comm, 2),
            DoubleToString(swap, 2),
            DoubleToString(net, 2),
            (string)hold_sec,
            (string)rec.ctx.vol_regime,
            (string)rec.ctx.real_vol_regime,
            (rec.ctx.regime_open_allowed ? "1" : "0"),
            (string)rec.ctx.market_state,
            DoubleToString(rec.ctx.rv_short_pts, 2),
            DoubleToString(rec.ctx.rv_long_pts, 2),
            DoubleToString(rec.ctx.rv_ratio, 4),
            DoubleToString(rec.ctx.multiplier_a, 4),
            DoubleToString(rec.ctx.grid_dist_pts, 1),
            DoubleToString(rec.ctx.tp_dist_pts, 1),
            DoubleToString(rec.ctx.baseline, _Digits),
            (string)rec.ctx.risk_level,
            DoubleToString(rec.ctx.avg_vol_per_min, 2),
            DoubleToString(rec.ctx.spread_pts, 1),
            DoubleToString(rec.ctx.atr, _Digits));
         FileFlush(G_EvaFhTrades);
         G_EvaWrittenRows++;
      }

      if(slot >= 0) G_EvaOpen[slot].used = false;   // 释放槽位
   }
}

//--- 决策审计(网格触发→放行/被过滤)
void EvaWriteDecisionAudit(int dir, int order_number, double mult,
                           double grid_dist_pts, bool allowed, string note)
{
   if(!G_EvaActive || !InpAuditDecisions) return;
   if(G_EvaFhAudit == INVALID_HANDLE) return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double pt  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double spr = (pt > 0 ? (ask - bid) / pt : 0.0);

   FileWrite(G_EvaFhAudit,
      EvaCsv(G_EvaRunId),
      EvaTimeIso(TimeCurrent()),
      (string)((long)TimeCurrent() * 1000),
      EvaCsv(_Symbol),
      (dir > 0 ? "buy" : "sell"),
      (string)order_number,
      (allowed ? "1" : "0"),
      EvaCsv(note),
      (string)(int)G_VolRegime,
      (string)(int)G_RealVolRegime,
      (G_RegimeOpenAllowed ? "1" : "0"),
      (string)(int)G_MarketState,
      DoubleToString(G_RVRatio, 4),
      DoubleToString(mult, 4),
      DoubleToString(grid_dist_pts, 1),
      (string)G_LastRiskLevel,
      DoubleToString(G_EvaAvgVolForLog, 2),
      DoubleToString(spr, 1),
      DoubleToString(G_Baseline, _Digits),
      DoubleToString(bid, _Digits));
   FileFlush(G_EvaFhAudit);
}

//--- 初始化：决定是否记录、建目录、开文件、写 run_config
void EvaInit()
{
   G_EvaActive = false;
   ArrayResize(G_EvaOpen, 0);
   G_EvaPending.valid = false;
   G_EvaExitReason = "expert_close";

   if(!InpEnableTradeAudit) return;

   // 优化模式强制关闭(多 pass 抢文件 + 拖慢)；单次回测/实盘正常记录
   if((bool)MQLInfoInteger(MQL_OPTIMIZATION))
   {
      Print("eva002: 检测到优化模式(Optimization)，审计日志已自动关闭。");
      return;
   }

   // 生成 run_id
   string tag = InpRunTag;
   if(tag == "")
   {
      string stamp = TimeToString(G_TesterStartTime, TIME_DATE | TIME_MINUTES);
      StringReplace(stamp, ".", "");
      StringReplace(stamp, ":", "");
      StringReplace(stamp, " ", "_");
      tag = _Symbol + "_" + stamp + "_" + IntegerToString((int)(GetTickCount() % 100000));
   }
   G_EvaRunId = tag;
   G_EvaDir   = "eva_audit/" + G_EvaRunId;

   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpAuditUseCommonFile) flags |= FILE_COMMON;

   G_EvaFhTrades = FileOpen(G_EvaDir + "/eva_trade_events.csv", flags, ',');
   G_EvaFhAudit  = FileOpen(G_EvaDir + "/eva_decision_audit.csv", flags, ',');
   G_EvaFhConfig = FileOpen(G_EvaDir + "/eva_run_config.csv", flags, ',');

   if(G_EvaFhTrades == INVALID_HANDLE)
   {
      Print("eva002: 无法创建 trade_events 文件 err=", GetLastError(), "，审计已关闭。");
      EvaDeinit();
      return;
   }
   G_EvaActive = true;

   // 表头：trade_events
   FileWrite(G_EvaFhTrades,
      "run_id","strategy_version","param_set_id","symbol","timeframe",
      "position_id","deal_in","deal_out","order_kind","direction",
      "entry_reason","exit_reason","deal_reason_raw","order_number",
      "entry_time","entry_time_msc","entry_price","exit_time","exit_time_msc","exit_price",
      "volume","sl_price","tp_price","profit","commission","swap","net_pnl","holding_seconds",
      "vol_regime","real_vol_regime","regime_open_allowed","market_state",
      "rv_short_pts","rv_long_pts","rv_ratio","multiplier_a","grid_dist_pts","tp_dist_pts",
      "baseline_at_entry","risk_level_at_entry","avg_vol_per_min","spread_pts_at_entry","atr_at_entry");
   FileFlush(G_EvaFhTrades);

   // 表头：decision_audit
   if(G_EvaFhAudit != INVALID_HANDLE)
   {
      FileWrite(G_EvaFhAudit,
         "run_id","time","time_msc","symbol","direction","order_number","allowed","note",
         "vol_regime","real_vol_regime","regime_open_allowed","market_state",
         "rv_ratio","multiplier_a","grid_dist_pts","risk_level","avg_vol_per_min",
         "spread_pts","baseline","price");
      FileFlush(G_EvaFhAudit);
   }

   // run_config：一行(键参数快照；多组参数批量回测对账用)
   if(G_EvaFhConfig != INVALID_HANDLE)
   {
      FileWrite(G_EvaFhConfig,
         "run_id","strategy_version","param_set_id","symbol","timeframe",
         "tester","optimization","start_time","account_currency","initial_balance",
         "regime_mode","magic","trend_magic","lot_size","use_dynamic_lot",
         "vol_window_min","vol_pct_midlow","vol_pct_lowmid","vol_pct_highmid","vol_pct_midhigh","vol_pct_highabs",
         "enable_state_machine","trend_tf","fast_ema","slow_ema",
         "uni_grid_explow","uni_grid_expslope","uni_base_profit","uni_max_pos");
      FileWrite(G_EvaFhConfig,
         EvaCsv(G_EvaRunId), EvaCsv(InpStrategyVersion), EvaCsv(InpParamSetId),
         EvaCsv(_Symbol), EvaCsv(EvaPeriodStr((ENUM_TIMEFRAMES)Period())),
         ((bool)MQLInfoInteger(MQL_TESTER) ? "1" : "0"),
         ((bool)MQLInfoInteger(MQL_OPTIMIZATION) ? "1" : "0"),
         EvaTimeIso(G_TesterStartTime),
         EvaCsv(AccountInfoString(ACCOUNT_CURRENCY)),
         DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
         "AUTO", (string)InpMagicNum, (string)InpTrendMagicNum,
         DoubleToString(InpLotSize, 2), (InpUseDynamicLot ? "1" : "0"),
         (string)InpVolWindowMinutes,
         "0","0","0","0","0",   // eva019：判档阈值已删，占位保持列数
         (InpEnableStateMachine ? "1" : "0"),
         EvaPeriodStr(InpTrendTimeframe), (string)InpTrendFastEMAPeriod, (string)InpTrendSlowEMAPeriod,
         DoubleToString(InpGridExpLow,2), DoubleToString(InpGridExpSlope,2),
         (string)InpUniBaseProfit, (string)InpUniMaxPos);
      FileFlush(G_EvaFhConfig);
      FileClose(G_EvaFhConfig);
      G_EvaFhConfig = INVALID_HANDLE;
   }

   PrintFormat("eva002: 审计日志已启用 run_id=%s 目录=%s\\Files\\%s",
               G_EvaRunId, (InpAuditUseCommonFile ? "Common" : "Terminal"), G_EvaDir);
}

//--- 收尾：关闭文件
void EvaDeinit()
{
   if(G_EvaFhTrades != INVALID_HANDLE){ FileFlush(G_EvaFhTrades); FileClose(G_EvaFhTrades); G_EvaFhTrades = INVALID_HANDLE; }
   if(G_EvaFhAudit  != INVALID_HANDLE){ FileFlush(G_EvaFhAudit);  FileClose(G_EvaFhAudit);  G_EvaFhAudit  = INVALID_HANDLE; }
   if(G_EvaFhConfig != INVALID_HANDLE){ FileFlush(G_EvaFhConfig); FileClose(G_EvaFhConfig); G_EvaFhConfig = INVALID_HANDLE; }
   if(G_EvaActive)
      PrintFormat("eva002: 审计日志已关闭，本次共记录 %I64d 笔交易。run_id=%s", G_EvaWrittenRows, G_EvaRunId);
   G_EvaActive = false;
}

//+------------------------------------------------------------------+
//| OnTester                                                         |
//+------------------------------------------------------------------+
double OnTester()
{
   //================================================================
   // v0.95 自定义评分（优化器须选 "Custom max" 才会生效）
   //
   //   score = profit^p * Dmax * Dfreq * Tfreq * S
   //
   //   - profit^p     : 利润幂次(p<1 抑制少数大单过拟合)
   //   - Dmax         : 最大回撤惩罚(看最深那一次)
   //   - Dfreq        : 多次回撤惩罚(Σ深度^2，多次/深回撤被重罚)
   //   - Tfreq        : 交易频次惩罚(低于目标每日交易数则扣分)
   //   - S            : 夏普稳定性(默认关闭)
   //   亏损或样本过少 → 直接返回极低分，让优化器淘汰。
   //================================================================
   double profit   = TesterStatistics(STAT_PROFIT);
   double dd_pct   = TesterStatistics(STAT_EQUITY_DDREL_PERCENT); // 最大相对净值回撤%
   double sharpe   = TesterStatistics(STAT_SHARPE_RATIO);
   double n_trades = InpScoreUseDealsForCount ? TesterStatistics(STAT_DEALS)
                                              : TesterStatistics(STAT_TRADES);

   // --- 样本过少：统计无意义，直接淘汰（保留微弱梯度=交易数本身）
   if(n_trades < InpScoreMinTotalTrades)
      return n_trades * 1e-6;

   // --- 亏损：返回负利润，确保排在所有盈利结果之后
   if(profit <= 0.0)
      return profit;

   // --- (1) 利润项
   double p = (InpScoreProfitPow > 0.0) ? InpScoreProfitPow : 1.0;
   // eva016：跨度无关——用“每笔期望”(profit/trades)替代“总利润”，跑1年/2个月相近数据得相近分
   double expectancy  = (n_trades > 0.0) ? (profit / n_trades) : 0.0;
   double profit_term = MathPow(MathMax(expectancy, 0.0), p);

   // --- (2) 最大回撤惩罚
   double dd_ref = (InpScoreDDRefPct > 0.0) ? InpScoreDDRefPct : 20.0;
   double dd_pow = (InpScoreDDPow   > 0.0) ? InpScoreDDPow   : 2.0;
   double dmax   = 1.0 / (1.0 + MathPow(dd_pct / dd_ref, dd_pow));

   // --- (3) 多次回撤惩罚：扫描成交历史重建余额曲线，统计每段回撤的相对深度
   double sum_sq_depth = 0.0;
   int    dd_episodes  = 0;
   {
      double start_balance = TesterStatistics(STAT_INITIAL_DEPOSIT);
      if(start_balance <= 0.0)
         start_balance = 1.0;

      if(HistorySelect(0, TimeCurrent()))
      {
         double bal       = start_balance;
         double peak       = bal;
         double trough     = bal;
         bool   in_dd      = false;
         double min_depth  = InpScoreDDMinPct / 100.0; // 转为小数

         int deals = HistoryDealsTotal();
         for(int i = 0; i < deals; i++)
         {
            ulong ticket = HistoryDealGetTicket(i);
            if(ticket == 0)
               continue;
            if(HistoryDealGetInteger(ticket, DEAL_MAGIC) != InpMagicNum)
               continue;

            double dp = HistoryDealGetDouble(ticket, DEAL_PROFIT)
                      + HistoryDealGetDouble(ticket, DEAL_SWAP)
                      + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
            bal += dp;

            if(bal >= peak)
            {
               // 创新高：结算上一段回撤
               if(in_dd)
               {
                  double depth = (peak - trough) / peak;
                  if(depth >= min_depth)
                  {
                     sum_sq_depth += depth * depth;
                     dd_episodes++;
                  }
                  in_dd = false;
               }
               peak   = bal;
               trough = bal;
            }
            else
            {
               if(!in_dd) { in_dd = true; trough = bal; }
               else if(bal < trough) trough = bal;
            }
         }

         // 收尾：测试结束时仍处于回撤中
         if(in_dd && peak > 0.0)
         {
            double depth = (peak - trough) / peak;
            if(depth >= min_depth)
            {
               sum_sq_depth += depth * depth;
               dd_episodes++;
            }
         }
      }
   }
   // eva016：跨度无关——用“平均每段回撤深度²”(总和/段数)替代累加和(累加随回测时长增长)
   double avg_sq_depth = (dd_episodes > 0) ? (sum_sq_depth / dd_episodes) : 0.0;
   double dfreq = 1.0 / (1.0 + InpScoreDDFreqWeight * avg_sq_depth);

   // --- (4) 交易频次惩罚
   double days = (double)(TimeCurrent() - G_TesterStartTime) / 86400.0;
   if(days < 1.0)
      days = 1.0;
   double tpd    = n_trades / days;
   double target = (InpScoreTargetTradesPerDay > 0.0) ? InpScoreTargetTradesPerDay : 1.0;
   double tfreq  = 1.0;
   if(tpd < target)
   {
      double r_pow = (InpScoreTPDPow > 0.0) ? InpScoreTPDPow : 1.0;
      tfreq = MathPow(tpd / target, r_pow);
   }

   // --- (5) 夏普稳定性（可选）
   double s = 1.0 + InpScoreSharpeWeight * MathMax(0.0, sharpe);

   double score = profit_term * dmax * dfreq * tfreq * s;

   if(InpEnableTesterLog)
   {
      PrintFormat("OnTester[v0.95] score=%.2f | profit=%.2f pterm=%.2f | DD%%=%.2f Dmax=%.3f | episodes=%d Σd^2=%.4f Dfreq=%.3f | trades=%.0f days=%.1f tpd=%.2f Tfreq=%.3f | sharpe=%.2f S=%.3f",
                  score, profit, profit_term, dd_pct, dmax,
                  dd_episodes, avg_sq_depth, dfreq,
                  n_trades, days, tpd, tfreq, sharpe, s);
   }

   return score;
}

//+------------------------------------------------------------------+
//| v1.93：基线持久化 —— 全局变量名                                  |
//| key 形如 VPG_Baseline_<品种>_<魔术编号>，换品种/魔术互不干扰      |
//+------------------------------------------------------------------+
string GetBaselineGlobalVarName()
{
   return StringFormat("VPG_Baseline_%s_%d", _Symbol, InpMagicNum);
}

//+------------------------------------------------------------------+
//| 从全局变量读取基线；不存在或非法时返回false                       |
//+------------------------------------------------------------------+
bool LoadBaselineFromGlobal()
{
   string name = GetBaselineGlobalVarName();

   if(!GlobalVariableCheck(name))
      return false;

   double val = GlobalVariableGet(name);

   if(val <= 0.0)
      return false;

   G_Baseline = val;
   return true;
}

//+------------------------------------------------------------------+
//| 把当前基线写入全局变量（持久化）                                  |
//+------------------------------------------------------------------+
void SaveBaselineToGlobal()
{
   if(G_SkipBaselinePersist)   // v0.95：回测重置模式不写入，避免污染后续 pass
      return;

   if(G_Baseline <= 0.0)
      return;

   GlobalVariableSet(GetBaselineGlobalVarName(), G_Baseline);
}

//+------------------------------------------------------------------+
//| v1.93：基线可视化 —— 图表对象名                                  |
//+------------------------------------------------------------------+
string GetBaselineLineName()
{
   return StringFormat("VPG_BaselineLine_%d", InpMagicNum);
}

//+------------------------------------------------------------------+
//| 创建/刷新基线水平线                                              |
//+------------------------------------------------------------------+
void UpdateBaselineLine()
{
   string name = GetBaselineLineName();

   if(!InpShowBaselineLine)
   {
      RemoveBaselineLine();
      return;
   }

   if(G_Baseline <= 0.0)
      return;

   if(ObjectFind(0, name) < 0)
   {
      if(!ObjectCreate(0, name, OBJ_HLINE, 0, 0, G_Baseline))
         return;

      ObjectSetInteger(0, name, OBJPROP_COLOR, InpBaselineLineColor);
      ObjectSetInteger(0, name, OBJPROP_WIDTH, InpBaselineLineWidth);
      ObjectSetInteger(0, name, OBJPROP_STYLE, InpBaselineLineStyle);
      ObjectSetInteger(0, name, OBJPROP_BACK, true);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetString(0, name, OBJPROP_TOOLTIP, "VPG Baseline");
   }

   ObjectSetDouble(0, name, OBJPROP_PRICE, G_Baseline);
   ObjectSetInteger(0, name, OBJPROP_COLOR, InpBaselineLineColor);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, InpBaselineLineWidth);
   ObjectSetInteger(0, name, OBJPROP_STYLE, InpBaselineLineStyle);

   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| 移除基线水平线                                                   |
//+------------------------------------------------------------------+
void RemoveBaselineLine()
{
   string name = GetBaselineLineName();
   if(ObjectFind(0, name) >= 0)
      ObjectDelete(0, name);
}

//+------------------------------------------------------------------+
//| v1.95：截止"虚拟末单线"硬止损                                    |
//| 思路：即便因截止（量过大/过小）无法加仓到最大持仓数，也按"截止   |
//| 上限对应的 multiplier_a"推算出末单（第max单）应处的价格线，价格  |
//| 越过该线再亏损一段缓冲后强制全平 + 冷静期。                       |
//| 注意：线距离 ∝ base_grid_z × mult_cap × Σ(coef^k)，其中 mult_cap |
//| = (max_avg/base_avg) 经指数衰减后取值。比值很大时线会很远、止损  |
//| 偏宽松；可用 InpMultiplierExp(<1) 收窄，或调小 last_order_loss。  |
//+------------------------------------------------------------------+
bool CheckCutoffLineStopAndCooldown(const StrategySnapshot &snap)
{
   if(!InpUseCutoffLineStop)
      return false;

   if(snap.total_count <= 0)
      return false;

   int max_n = G_ActiveParams.max_total_positions;
   if(max_n <= 0)
      return false;

   if(G_ActiveParams.base_avg_volume_per_min <= 0.0 ||
      G_ActiveParams.max_avg_volume_per_min  <= 0.0)
      return false;

   // 方向：取占优方向；多空持平视为对冲，跳过
   bool is_long;
   if(snap.buy_count > snap.sell_count)
      is_long = true;
   else if(snap.sell_count > snap.buy_count)
      is_long = false;
   else
      return false;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   // 按截止上限计算 multiplier_a（与开仓口径一致：取指数、下限为1）
   double raw_cap = G_ActiveParams.max_avg_volume_per_min / G_ActiveParams.base_avg_volume_per_min;
   double mult_cap = raw_cap;
   if(raw_cap > 0.0 && InpMultiplierExp > 0.0 && InpMultiplierExp != 1.0)
      mult_cap = MathPow(raw_cap, InpMultiplierExp);
   if(mult_cap < 1.0)
      mult_cap = 1.0;

   // 末单（第 max_n 单）相对基线的累计网格距离：Σ_{k=0}^{max_n-1} coef^k
   double coef = G_ActiveParams.grid_exp_coef;
   double geom;
   if(MathAbs(coef - 1.0) < 1e-9)
      geom = (double)max_n;
   else
      geom = (MathPow(coef, max_n) - 1.0) / (coef - 1.0);

   double cum_dist  = G_ActiveParams.base_grid_z * point * mult_cap * geom;
   double last_line = is_long ? (G_Baseline - cum_dist) : (G_Baseline + cum_dist);

   // 把"每手亏损货币"换算为越线后的价格缓冲
   double loss_dist = 0.0;
   if(G_ActiveParams.last_order_loss_per_lot > 0.0)
   {
      double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
      double tick_size  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      if(tick_value > 0.0 && tick_size > 0.0)
         loss_dist = G_ActiveParams.last_order_loss_per_lot * tick_size / tick_value;
   }

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   bool stop_hit = false;
   if(is_long)
   {
      if(bid <= last_line - loss_dist)
         stop_hit = true;
   }
   else
   {
      if(ask >= last_line + loss_dist)
         stop_hit = true;
   }

   if(!stop_hit)
      return false;

   if(InpEnableLog)
      Print("触发截止虚拟末单线硬止损：dir=", (is_long ? "LONG" : "SHORT"),
            ", baseline=", DoubleToString(G_Baseline, _Digits),
            ", last_line=", DoubleToString(last_line, _Digits),
            ", mult_cap=", DoubleToString(mult_cap, 3),
            ", cum_dist(pt)=", DoubleToString(cum_dist / (point > 0.0 ? point : 1.0), 0),
            ", loss_buffer(pt)=", DoubleToString(loss_dist / (point > 0.0 ? point : 1.0), 0));

   EvaSetExit("cutoff_line_stop");   // eva002
   CloseAllStrategyPositions();
   StartCooldown(!G_HadProfitSinceLastCooldown);
   return true;
}


//+------------------------------------------------------------------+
//| v0.98：实时状态面板 —— 角落对应的锚点                            |
//+------------------------------------------------------------------+
ENUM_ANCHOR_POINT DashAnchorForCorner(ENUM_BASE_CORNER c)
{
   switch(c)
   {
      case CORNER_RIGHT_UPPER: return ANCHOR_RIGHT_UPPER;
      case CORNER_LEFT_LOWER:  return ANCHOR_LEFT_LOWER;
      case CORNER_RIGHT_LOWER: return ANCHOR_RIGHT_LOWER;
      default:                 return ANCHOR_LEFT_UPPER; // CORNER_LEFT_UPPER
   }
}

//+------------------------------------------------------------------+
//| v0.98：创建/更新单行标签                                         |
//+------------------------------------------------------------------+
void SetDashLabel(int idx, int total, string text, color clr)
{
   string name = StringFormat("VPG_Dash_%d_%d", InpMagicNum, idx);

   ENUM_BASE_CORNER  corner = (ENUM_BASE_CORNER)InpDashCorner;
   ENUM_ANCHOR_POINT anchor = DashAnchorForCorner(corner);

   bool lower = (corner == CORNER_LEFT_LOWER || corner == CORNER_RIGHT_LOWER);

   int line_h = InpDashFontSize + 6;
   // 下方角落时反向堆叠，使第0行始终在整块面板顶部
   int stack  = lower ? (total - 1 - idx) : idx;
   int y      = InpDashY + stack * line_h;

   if(ObjectFind(0, name) < 0)
   {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, name, OBJPROP_BACK, false);
   }

   ObjectSetInteger(0, name, OBJPROP_CORNER,    corner);
   ObjectSetInteger(0, name, OBJPROP_ANCHOR,    anchor);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, InpDashX);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE,  InpDashFontSize);
   ObjectSetString (0, name, OBJPROP_FONT,      InpDashFont);
   ObjectSetString (0, name, OBJPROP_TEXT,      text);
   ObjectSetInteger(0, name, OBJPROP_COLOR,     clr);
}

//+------------------------------------------------------------------+
//| v0.98：移除面板全部标签                                          |
//+------------------------------------------------------------------+
void RemoveDashboard()
{
   for(int i = 0; i < 32; i++)
   {
      string name = StringFormat("VPG_Dash_%d_%d", InpMagicNum, i);
      if(ObjectFind(0, name) >= 0)
         ObjectDelete(0, name);
   }
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| v0.98：刷新实时状态面板（按M1柱节流，每分钟一次）                |
//| 显示：短/长RV、当前与真实档位、开仓门闸、每分钟量与放大倍数、    |
//|       风险等级、冷静期(含到期时间)、基线、做多/做空下一档触发价  |
//+------------------------------------------------------------------+
void UpdateDashboard()
{
   if(!InpShowDashboard)
   {
      RemoveDashboard();
      return;
   }

   // 优化模式 / 非可视化回测下不绘制（无图表、且浪费资源）
   if(MQLInfoInteger(MQL_OPTIMIZATION))
      return;
   if(MQLInfoInteger(MQL_TESTER) && !MQLInfoInteger(MQL_VISUAL_MODE))
      return;

   // 每分钟（每根M1柱）刷新一次
   datetime cur_bar = iTime(_Symbol, PERIOD_M1, 0);
   if(cur_bar == G_LastDashboardBar)
      return;
   G_LastDashboardBar = cur_bar;

   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(point <= 0.0)
      return;

   // ---- 每分钟交易量（与 OnTick 同口径：历史窗口 + 当前柱）----
   int win = MathMax(1, G_ActiveParams.avg_volume_minutes);
   long vol_sum = 0;
   if(win > 1)
   {
      long hv[];
      if(CopyTickVolume(_Symbol, PERIOD_M1, 1, win - 1, hv) == win - 1)
         for(int i = 0; i < win - 1; i++)
            vol_sum += hv[i];
   }
   long cur_v = 0;
   long c0[];
   if(CopyTickVolume(_Symbol, PERIOD_M1, 0, 1, c0) == 1)
      cur_v = c0[0];
   double avg_vol = (double)(vol_sum + cur_v) / win;

   // ---- 放大倍数 multiplier_a（与 OnTick 同口径）----
   double mult = 1.0;
   if(G_ActiveParams.base_avg_volume_per_min > 0.0)
   {
      double raw = avg_vol / G_ActiveParams.base_avg_volume_per_min;
      if(raw > 0.0 && InpMultiplierExp > 0.0 && InpMultiplierExp != 1.0)
         mult = MathPow(raw, InpMultiplierExp);
      else
         mult = raw;
      if(mult < 1.0)
         mult = 1.0;
   }

   // ---- 持仓快照与下一档触发价 ----
   StrategySnapshot snap;
   BuildStrategySnapshot(snap);

   double base_dyn  = G_ActiveParams.base_grid_z * point * mult;
   double buy_dist  = base_dyn * MathPow(G_ActiveParams.grid_exp_coef, snap.buy_count);
   double sell_dist = base_dyn * MathPow(G_ActiveParams.grid_exp_coef, snap.sell_count);
   double next_buy  = (snap.buy_count  == 0 ? G_Baseline : snap.last_buy_price)  - buy_dist;
   double next_sell = (snap.sell_count == 0 ? G_Baseline : snap.last_sell_price) + sell_dist;

   double order_lot = GetCurrentOrderLot();

   ENUM_RISK_LEVEL rl = GetCurrentRiskLevel(avg_vol);
   bool cooling = IsInCooldown();

   // ---- 文案 ----
   string mode_str = "统一模型";   // eva019：已无档位切换

   string risk_str;
   switch(rl)
   {
      case RISK_LEVEL_2_LIMIT:  risk_str = "L2 限制开仓"; break;
      case RISK_LEVEL_3_REDUCE: risk_str = "L3 减仓";     break;
      case RISK_LEVEL_4_EXIT:   risk_str = "L4 离场";     break;
      default:                  risk_str = "L1 正常";     break;
   }

   color reg_col = (G_VolRegime == VOL_REGIME_HIGH) ? clrOrangeRed
                 : (G_VolRegime == VOL_REGIME_MID)  ? clrGold
                                                    : clrDeepSkyBlue;
   color gate_col = G_RegimeOpenAllowed ? clrLime : clrSilver;
   color risk_col = (rl >= RISK_LEVEL_3_REDUCE) ? clrOrangeRed
                  : (rl == RISK_LEVEL_2_LIMIT)  ? clrGold
                                                : clrLime;
   color cool_col = cooling ? clrOrangeRed : clrLime;
   color state_col = (G_MarketState == MARKET_STATE_TREND_UP)   ? clrLime
                   : (G_MarketState == MARKET_STATE_TREND_DOWN) ? clrOrangeRed
                                                                : clrSilver;

   string cool_txt;
   if(cooling)
      cool_txt = "冷静期: 是  到 " + TimeToString(G_CooldownUntil, TIME_DATE|TIME_MINUTES);
   else
      cool_txt = "冷静期: 否";

   // ---- 逐行装配 ----
   string L[24];
   color  C[24];
   int    n = 0;

   L[n]="VolumetricPulseGrid v0.98";                                       C[n]=clrAqua;            n++;
   L[n]="刷新 "+TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES);        C[n]=clrSilver;          n++;
   L[n]="------------------------------";                                  C[n]=clrDimGray;         n++;
   L[n]="状态机: "+MarketStateToStr(G_MarketState)
        +"   趋势确认 U/D: "+IntegerToString(G_TrendUpConfirm)+"/"+IntegerToString(G_TrendDownConfirm); C[n]=state_col; n++;
   L[n]="模式: "+mode_str+"   开仓门闸: "+(G_RegimeOpenAllowed?"放行":"暂停"); C[n]=gate_col;        n++;
   L[n]="档位(参数): "+RegimeToStr(G_VolRegime)+"   真实: "+RegimeToStr(G_RealVolRegime); C[n]=reg_col; n++;
   L[n]="RV短: "+DoubleToString(G_RVShortPoints,1)
        +"   RV长: "+DoubleToString(G_RVLongPoints,1)
        +"   比值: "+DoubleToString(G_RVRatio,3);                          C[n]=InpDashTextColor;   n++;
   L[n]="每分钟量: "+DoubleToString(avg_vol,1)
        +"  (基准"+DoubleToString(G_ActiveParams.base_avg_volume_per_min,1)
        +" 上限"+DoubleToString(G_ActiveParams.max_avg_volume_per_min,0)+")"; C[n]=InpDashTextColor; n++;
   L[n]="放大倍数: "+DoubleToString(mult,2)+"   下单手数: "+DoubleToString(order_lot,2); C[n]=InpDashTextColor; n++;
   L[n]="风险等级: "+risk_str;                                             C[n]=risk_col;           n++;
   L[n]=cool_txt;                                                          C[n]=cool_col;           n++;
   L[n]="------------------------------";                                  C[n]=clrDimGray;         n++;
   L[n]="基线: "+DoubleToString(G_Baseline,_Digits)
        +"   现价: "+DoubleToString(bid,_Digits);                          C[n]=clrGold;            n++;
   L[n]="做多触发价: "+DoubleToString(next_buy,_Digits)
        +"  (第"+IntegerToString(snap.buy_count+1)+"单)";                   C[n]=clrDeepSkyBlue;     n++;
   L[n]="做空触发价: "+DoubleToString(next_sell,_Digits)
        +"  (第"+IntegerToString(snap.sell_count+1)+"单)";                  C[n]=clrViolet;          n++;
   L[n]="趋势EMA: F"+DoubleToString(G_TrendFastEMA,_Digits)
        +" S"+DoubleToString(G_TrendSlowEMA,_Digits)
        +" ATR"+DoubleToString(G_TrendATR,_Digits);                       C[n]=InpDashTextColor;   n++;
   L[n]="网格持仓: 多"+IntegerToString(snap.buy_count)
        +" 空"+IntegerToString(snap.sell_count)
        +" / 上限"+IntegerToString(G_ActiveParams.max_total_positions);    C[n]=InpDashTextColor;   n++;
   L[n]="趋势持仓: 多"+IntegerToString(CountTrendPositions(POSITION_TYPE_BUY))
        +" 空"+IntegerToString(CountTrendPositions(POSITION_TYPE_SELL))
        +" / 上限"+IntegerToString(MathMax(1, InpTrendMaxPositions));      C[n]=state_col;          n++;

   for(int i = 0; i < n; i++)
      SetDashLabel(i, n, L[i], C[i]);

   // 清理可能多余的旧行
   for(int i = n; i < 32; i++)
   {
      string nm = StringFormat("VPG_Dash_%d_%d", InpMagicNum, i);
      if(ObjectFind(0, nm) >= 0)
         ObjectDelete(0, nm);
   }

   ChartRedraw(0);
}
