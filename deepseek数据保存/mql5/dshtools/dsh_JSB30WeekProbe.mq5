//+------------------------------------------------------------------+
//|  dsh_JSB30WeekProbe.mq5 — 历史周界探针（第二层：Tester）           |
//|                                                                  |
//|  在 Strategy Tester 里对真实 USDJPYm 运行，只读记录：              |
//|    · 每个交易周的第一根 / 最后一根 M1 与 M30 bar 的 tester 时间戳   |
//|    · 周日/周一边界                                                 |
//|    · 当周由代码推导出的 UTC                                       |
//|                                                                  |
//|  ★不预先假设 open = UTC 22:00。                                    |
//|  ★不下单、不交易。                                                 |
//|  输出：Common\Files\dshtrend\JSB30TIME\week_probe_<tag>.txt        |
//+------------------------------------------------------------------+
#property copyright "dsh"
#property version   "1.00"
#property strict

input string InpRunTag      = "WEEKPROBE";
input int    InpMaxWeeks    = 40;

// ---- 与 EA 一致的两种 offset 假设，用于对照 ----
//   H0：server == UTC（Exness 官方口径 UTC+0）
//   H2/H3：旧的"周日 22:00 UTC 开市"反推
int      g_off     = -1;
string   g_offWhy  = "";

int Fh = INVALID_HANDLE;

void W(const string s)
{
   Print("wkprobe: ", s);
   if(Fh != INVALID_HANDLE) FileWrite(Fh, s);
}

// 周键：UTC 下的"周一 00:00"（含周日 22:00 后归下一周）
datetime WeekKeyUtc(datetime tUtc)
{
   MqlDateTime s; TimeToStruct(tUtc, s);
   int dow = s.day_of_week;
   datetime dayStart = (datetime)((long)tUtc - (long)s.hour*3600 - (long)s.min*60 - s.sec);
   int back = (dow == 0) ? 6 : dow - 1;
   datetime wk = (datetime)((long)dayStart - (long)back * 86400);
   if(dow == 0 && s.hour >= 22) wk = (datetime)((long)wk + 7 * 86400);
   return wk;
}

void OnInit()
{
   string dir = "dshtrend\\JSB30TIME";
   FolderCreate("dshtrend", FILE_COMMON);
   FolderCreate(dir, FILE_COMMON);
   string fn = dir + "\\week_probe_" + InpRunTag + ".txt";
   Fh = FileOpen(fn, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(Fh == INVALID_HANDLE) Fh = FileOpen(fn, FILE_WRITE|FILE_TXT|FILE_ANSI);
}

void OnTick()
{
   static bool done = false;
   if(done) return;
   done = true;

   W("=== dsh_JSB30WeekProbe ===");
   W("run_tag=" + InpRunTag);
   W("symbol=" + _Symbol);
   W("server=" + AccountInfoString(ACCOUNT_SERVER));
   W("build=" + IntegerToString((int)TerminalInfoInteger(TERMINAL_BUILD)));
   W("TimeCurrent_at_first_tick=" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
   W("TimeGMT_at_first_tick=" + TimeToString(TimeGMT(), TIME_DATE|TIME_SECONDS));
   W("TimeTradeServer=" + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS));
   W("server_minus_GMT_sec=" + IntegerToString((int)((long)TimeCurrent() - (long)TimeGMT())));
   W("");

   int barsM1 = iBars(_Symbol, PERIOD_M1);
   int barsM30 = iBars(_Symbol, PERIOD_M30);
   W(StringFormat("tester_bars: M1=%d M30=%d", barsM1, barsM30));
   if(barsM1 > 0)
   {
      W("M1 first=" + TimeToString(iTime(_Symbol, PERIOD_M1, barsM1 - 1), TIME_DATE|TIME_MINUTES));
      W("M1 last =" + TimeToString(iTime(_Symbol, PERIOD_M1, 0), TIME_DATE|TIME_MINUTES));
   }
   if(barsM30 > 0)
   {
      W("M30 first=" + TimeToString(iTime(_Symbol, PERIOD_M30, barsM30 - 1), TIME_DATE|TIME_MINUTES));
      W("M30 last =" + TimeToString(iTime(_Symbol, PERIOD_M30, 0), TIME_DATE|TIME_MINUTES));
   }
   W("");

   // ---- 逐周：找每周第一根 M1 与最后一根 M1 ----
   W("--- per-week boundaries (tester timestamps, NO offset assumption) ---");
   W("week_key_utc | first_M1 | last_M1 | first_dow | first_hour | last_dow | last_hour");

   if(barsM1 <= 0) { W("no M1 bars"); if(Fh != INVALID_HANDLE) FileClose(Fh); return; }

   datetime firstBar = iTime(_Symbol, PERIOD_M1, barsM1 - 1);
   datetime lastBar  = iTime(_Symbol, PERIOD_M1, 0);

   // 从第一根 bar 起，按周扫描
   datetime cur = firstBar;
   int weeks = 0;
   while(cur <= lastBar && weeks < InpMaxWeeks)
   {
      datetime wk = WeekKeyUtc(cur);
      datetime wEnd = (datetime)((long)wk + 7 * 86400);
      // 该周第一根
      int shFirst = iBarShift(_Symbol, PERIOD_M1, wk, false);
      int shLast  = iBarShift(_Symbol, PERIOD_M1, (datetime)((long)wEnd - 60), false);
      datetime bFirst = 0, bLast = 0;
      if(shFirst >= 0 && shFirst < barsM1) bFirst = iTime(_Symbol, PERIOD_M1, shFirst);
      if(shLast  >= 0 && shLast  < barsM1) bLast  = iTime(_Symbol, PERIOD_M1, shLast);

      MqlDateTime s1, s2;
      if(bFirst > 0) TimeToStruct(bFirst, s1);
      if(bLast  > 0) TimeToStruct(bLast,  s2);

      W(StringFormat("%s | %s | %s | dow=%d h=%02d | dow=%d h=%02d",
                     TimeToString(wk, TIME_DATE),
                     (bFirst > 0) ? TimeToString(bFirst, TIME_DATE|TIME_MINUTES) : "none",
                     (bLast  > 0) ? TimeToString(bLast,  TIME_DATE|TIME_MINUTES) : "none",
                     (bFirst > 0) ? s1.day_of_week : -1, (bFirst > 0) ? s1.hour : -1,
                     (bLast  > 0) ? s2.day_of_week : -1, (bLast  > 0) ? s2.hour : -1));

      cur = wEnd;
      weeks++;
   }
   W("");
   W(StringFormat("weeks_recorded=%d", weeks));
   W("interpretation_hint: 若 first_M1 的 dow=1(周一) 且 hour=00 或 01，");
   W("  则 tester timestamp 很可能已含 offset；若 dow=0(周日) 且 hour=21 或 22，");
   W("  则 tester timestamp 近似 UTC（外汇周界在 UTC 周日 21:05/22:05 开市）");
   if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; }
   Print("wkprobe: 完成");
}

void OnDeinit(const int reason) { if(Fh != INVALID_HANDLE) { FileClose(Fh); Fh = INVALID_HANDLE; } }
//+------------------------------------------------------------------+
