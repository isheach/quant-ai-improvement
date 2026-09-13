//+------------------------------------------------------------------+
//|  dsh_TickClock.mq5 —— ★延迟口径校准探针（不交易，只测量）           |
//|                                                                  |
//|  作者：日元滚动 · 网格策略线研究代理（DeepSeek 子代理）· 2026-09-12 |
//|                                                                  |
//|  ==== 为什么需要它 ====                                            |
//|  全项目的延迟口径都建在 `InpLatencyTicks` 这个【tick 计数】上：     |
//|    · runexp.py L88/L109/L122/L206 —— 四个 BASE_* 字典全部写着      |
//|      "InpLatencyTicks": "1"                                       |
//|    · 日元线的 `jyrg-008`（1 tick）与 `jyrg-lat0`（0 tick）差出      |
//|      net −13.57 vs −9.84、DD 8.14% vs 7.10%                       |
//|  → 但**没有人知道 1 个 tick 在 Model=2 里等于多少模拟时间**。       |
//|  → 如果 1 tick ≈ 15 秒（Model=2 每根 M1 约生成 4 个 tick 的常见说法），|
//|    那么"施加了 300ms 延迟"这整句话在全项目都是**不成立的**：        |
//|    实际施加的是 ~15 秒，是目标值的 50 倍；而 300ms ≈ 0.02 个 tick，  |
//|    **在 Model=2 里根本无法表示**。                                  |
//|                                                                  |
//|  ==== 它测什么 ====                                                |
//|   ① OnTick 被调用的总次数                                          |
//|   ② 模拟时间跨度（首 tick → 末 tick）                               |
//|   ③ 平均每个 tick 之间的模拟秒数  ← ★这就是"1 tick = ? 秒"          |
//|   ④ 走过多少根 M1 bar → 平均每根 M1 生成几个 tick                   |
//|   ⑤ tick 间隔的分布（min / p50 / p90 / max）                       |
//|                                                                  |
//|  ==== 怎么用 ====                                                  |
//|   在测试器里跑【很短】的窗口即可（建议 1 个月，Model=2），          |
//|   它不交易、不改仓、不碰任何品种，只读 TimeCurrent()。              |
//|   结果同时打印到日志并写到：                                        |
//|     Common\Files\dshtrend\<InpRunTag>\tickclock.txt                 |
//+------------------------------------------------------------------+
#property copyright "DeepSeek JPY rolling line"
#property version   "1.00"
#property strict

input string InpRunTag      = "tickclock";   // 审计目录名（纯 ASCII）
input bool   InpWriteFile   = true;          // 是否写 tickclock.txt（FILE_COMMON）
input int    InpPrintEvery  = 100000;        // 每 N 个 tick 打印一次进度（0=不打）

//==================== 状态 ====================
long     g_ticks        = 0;
datetime g_firstTime    = 0;
datetime g_lastTime     = 0;
long     g_firstM1      = 0;     // 首 tick 所在 M1 桶
long     g_lastM1       = 0;
long     g_m1Buckets    = 0;     // 走过的不同 M1 桶数
long     g_prevBucket   = -1;

// 间隔统计（秒）
long     g_sumGapSec    = 0;
long     g_minGapSec    = -1;
long     g_maxGapSec    = 0;
long     g_gap0         = 0;     // 与上一 tick 同一秒（gap=0）的次数
long     g_gapHist[8];           // <1s, 1-2, 2-5, 5-15, 15-30, 30-60, 60-300, >=300

int      g_fh = INVALID_HANDLE;

//==================== 工具 ====================
string AuditDir() { return "dshtrend/" + InpRunTag; }

int TFBucket(datetime t, int secPerBar)
{
   return (int)((long)t / (long)secPerBar);
}

void BucketGap(long gapSec)
{
   if(gapSec <= 0)                              g_gapHist[0]++;
   else if(gapSec < 2)                          g_gapHist[1]++;
   else if(gapSec < 5)                          g_gapHist[2]++;
   else if(gapSec < 15)                         g_gapHist[3]++;
   else if(gapSec < 30)                         g_gapHist[4]++;
   else if(gapSec < 60)                         g_gapHist[5]++;
   else if(gapSec < 300)                        g_gapHist[6]++;
   else                                         g_gapHist[7]++;
}

//==================== 生命周期 ====================
int OnInit()
{
   for(int i = 0; i < 8; i++) g_gapHist[i] = 0;

   if(InpWriteFile)
   {
      FolderCreate("dshtrend", FILE_COMMON);
      FolderCreate(AuditDir(), FILE_COMMON);
      g_fh = FileOpen(AuditDir() + "/tickclock.txt",
                      FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   }

   PrintFormat("[%s] init ok symbol=%s model=测试器当前设置 周期=%d 分钟",
               InpRunTag, _Symbol, Period());
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   double spanSec = 0.0;
   if(g_firstTime > 0 && g_lastTime >= g_firstTime)
      spanSec = (double)(g_lastTime - g_firstTime);

   double secPerTick = (g_ticks > 1) ? spanSec / (double)(g_ticks - 1) : 0.0;
   double ticksPerM1 = (g_m1Buckets > 0) ? (double)g_ticks / (double)g_m1Buckets : 0.0;
   double avgGap    = (g_ticks > 1) ? (double)g_sumGapSec / (double)(g_ticks - 1) : 0.0;

   string L = "";
   L += "=== dsh_TickClock " + _Symbol + " ===\r\n";
   L += "run_tag=" + InpRunTag + "\r\n";
   L += "chart_period_min=" + IntegerToString(Period()) + "\r\n";
   L += "ticks_total=" + IntegerToString((int)g_ticks) + "\r\n";
   L += "first_tick=" + TimeToString(g_firstTime, TIME_DATE|TIME_SECONDS) + "\r\n";
   L += "last_tick=" + TimeToString(g_lastTime, TIME_DATE|TIME_SECONDS) + "\r\n";
   L += "span_seconds=" + DoubleToString(spanSec, 1) + "\r\n";
   L += "span_hours=" + DoubleToString(spanSec/3600.0, 3) + "\r\n";
   L += "m1_buckets=" + IntegerToString((int)g_m1Buckets) + "\r\n";
   L += "ticks_per_M1=" + DoubleToString(ticksPerM1, 3) + "\r\n";
   L += "★avg_seconds_per_tick=" + DoubleToString(secPerTick, 3) + "\r\n";
   L += "avg_gap_seconds=" + DoubleToString(avgGap, 3) + "\r\n";
   L += "min_gap_seconds=" + IntegerToString((int)g_minGapSec) + "\r\n";
   L += "max_gap_seconds=" + IntegerToString((int)g_maxGapSec) + "\r\n";
   L += "gap==0_count=" + IntegerToString((int)g_gap0) + "\r\n";
   L += "gap_hist[<1s,1-2,2-5,5-15,15-30,30-60,60-300,>=300]="
        + IntegerToString((int)g_gapHist[0]) + ","
        + IntegerToString((int)g_gapHist[1]) + ","
        + IntegerToString((int)g_gapHist[2]) + ","
        + IntegerToString((int)g_gapHist[3]) + ","
        + IntegerToString((int)g_gapHist[4]) + ","
        + IntegerToString((int)g_gapHist[5]) + ","
        + IntegerToString((int)g_gapHist[6]) + ","
        + IntegerToString((int)g_gapHist[7]) + "\r\n";
   // ★换算：把项目里用到的几个 tick 数折算成模拟时间
   L += "--- latency calibration ---\r\n";
   L += "1_tick_seconds="  + DoubleToString(secPerTick*1.0,  2) + "\r\n";
   L += "3_ticks_seconds=" + DoubleToString(secPerTick*3.0,  2) + "\r\n";
   L += "30_ticks_seconds="+ DoubleToString(secPerTick*30.0, 2) + "\r\n";
   L += "300ms_in_ticks="  + DoubleToString((secPerTick>0 ? 0.300/secPerTick : 0.0), 5) + "\r\n";

   if(g_fh != INVALID_HANDLE)
   {
      FileWriteString(g_fh, L);
      FileClose(g_fh);
   }

   PrintFormat("[%s] === TICKCLOCK ticks=%d span=%.0fs (%.2fh) m1=%d ticks/M1=%.2f "
               "★sec/tick=%.3f minGap=%ds maxGap=%ds gap0=%d ===",
               InpRunTag, (int)g_ticks, spanSec, spanSec/3600.0, (int)g_m1Buckets,
               ticksPerM1, secPerTick, (int)g_minGapSec, (int)g_maxGapSec, (int)g_gap0);
   PrintFormat("[%s] === 换算: 1tick=%.1fs  3ticks=%.1fs  30ticks=%.1fs  300ms=%.5f tick ===",
               InpRunTag, secPerTick, secPerTick*3, secPerTick*30,
               (secPerTick > 0 ? 0.300/secPerTick : 0.0));
}

//==================== 主循环（只测量，不交易）====================
void OnTick()
{
   datetime now = TimeCurrent();
   if(now <= 0) return;

   g_ticks++;

   if(g_firstTime == 0)
   {
      g_firstTime = now;
      g_firstM1   = TFBucket(now, 60);
      g_prevBucket = g_firstM1;
      g_m1Buckets  = 1;
      g_lastTime   = now;
      return;
   }

   long gap = (long)now - (long)g_lastTime;
   if(gap < 0) gap = 0;
   g_sumGapSec += gap;
   if(g_minGapSec < 0 || gap < g_minGapSec) g_minGapSec = gap;
   if(gap > g_maxGapSec) g_maxGapSec = gap;
   if(gap == 0) g_gap0++;
   BucketGap(gap);

   long b = TFBucket(now, 60);
   if(b != g_prevBucket) { g_m1Buckets++; g_prevBucket = b; }

   g_lastTime = now;

   if(InpPrintEvery > 0 && (g_ticks % (long)InpPrintEvery) == 0)
      PrintFormat("[%s] progress ticks=%d t=%s m1=%d",
                  InpRunTag, (int)g_ticks, TimeToString(now, TIME_DATE|TIME_SECONDS),
                  (int)g_m1Buckets);
}
//+------------------------------------------------------------------+
