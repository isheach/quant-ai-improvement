//+------------------------------------------------------------------+
//|                                       eva005_TickDataExporter.mq5 |
//|   行情数据导出脚本（第2代）—— 在 eva001 基础上修复“只导到部分历史”问题  |
//|                                                                  |
//|   关键改动（详见 eva_DEVLOG.md / eva005 条目）：                    |
//|   1) 加入“强制下载 + 等待重试”：CopyRates/CopyTicksRange 只返回      |
//|      本地已缓存的历史，MT5 后台异步下载，故必须循环等待，否则只会拿到  |
//|      最近若干月（这正是上一版只导出近月数据的根因）。                  |
//|   2) tick 与 K 线的年月区间分开：K 线可全程(如 2014→今)，tick 默认    |
//|      只取近几年——券商真实 tick 历史通常只有最近几年，老年份不存在，     |
//|      分开可避免在不存在的老 tick 上空等数小时。                       |
//|   3) 价格精度：输出位数 = max(品种Digits, InpForceMinDigits)，默认    |
//|      最少 3 位，确保 3 位报价(黄金 point=0.001)不被截断；并在开头明确   |
//|      打印检测到的 Digits/Point，便于核对。                           |
//|   4) 预检：打印每个周期“实际可用最早日期”(SERIES_FIRSTDATE)，         |
//|      让你一眼看清券商到底有多少历史。                                 |
//|   5) 生成 <root>/<symbol>/meta.json，记录 digits/point，供 eva006   |
//|      Python 自动识别点值(不必每次手填 --point)。                     |
//+------------------------------------------------------------------+
#property copyright "eva pipeline"
#property version   "2.00"
#property script_show_inputs
#property strict

//--- 品种
input string InpExportSymbol   = "";        // 导出品种（留空=当前图表品种，建议 XAUUSD）

//--- K 线区间（可全程，如 2014→今）
input int    InpFromYear       = 2014;      // K线-起始年
input int    InpFromMonth      = 1;         // K线-起始月(1-12)
input int    InpToYear         = 2026;      // K线-结束年(含)
input int    InpToMonth        = 12;        // K线-结束月(含,1-12)

//--- tick 区间（默认只近几年；券商真实 tick 历史通常较浅）
input int    InpTickFromYear   = 2022;      // tick-起始年
input int    InpTickFromMonth  = 1;         // tick-起始月
input int    InpTickToYear     = 2026;      // tick-结束年(含)
input int    InpTickToMonth    = 12;        // tick-结束月(含)

//--- 导出内容
input bool   InpExportTicks    = true;      // 导出真实 tick(COPY_TICKS_ALL)
input bool   InpExportM1       = true;      // 导出 M1
input bool   InpExportM5       = true;      // 导出 M5
input bool   InpExportM15      = false;     // 导出 M15

//--- 下载等待（解决“只导到部分历史”的核心参数）
input int    InpSyncWaitSec    = 120;       // 每周期“整体历史同步”最长等待秒数
input int    InpMaxRetries     = 30;        // 单块数据(月/天)下载重试次数
input int    InpRetrySleepMs   = 300;       // 每次重试间隔(毫秒)

//--- 输出
input string InpOutRoot        = "eva_data";// 输出根目录名(位于 Files 内)
input bool   InpUseCommonFiles = true;      // true=写 Common\Files(跨终端可取)；false=本地沙箱
input bool   InpOverwrite      = true;      // 已存在的月文件是否覆盖；false=跳过(断点续传)
input bool   InpSkipEmptyMonth = true;      // 无数据月份不生成空文件
input int    InpForceMinDigits = 3;         // 价格最少小数位(黄金3位防截断)；实际取 max(品种Digits, 此值)
input int    InpPricePrecision = -1;        // 手动指定价格小数位：-1=用上面的自动规则

//--- 全局
int    G_SymDigits = 2;
int    G_OutDigits = 3;
double G_Point     = 0.01;

//+------------------------------------------------------------------+
int FileFlagsCsv()
{
   int f = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFiles) f |= FILE_COMMON;
   return f;
}

datetime MonthStart(int y, int m)
{
   MqlDateTime t; t.year=y; t.mon=m; t.day=1; t.hour=0; t.min=0; t.sec=0;
   return StructToTime(t);
}
void NextMonth(int y, int m, int &ny, int &nm)
{
   if(m >= 12){ ny=y+1; nm=1; } else { ny=y; nm=m+1; }
}
string MM(int m){ return (m<10?"0":"") + IntegerToString(m); }
string IsoTime(datetime t){ return TimeToString(t, TIME_DATE | TIME_SECONDS); }
string Px(double p){ return DoubleToString(p, G_OutDigits); }

//+------------------------------------------------------------------+
//| 强制下载并等待某周期历史回溯到 from（K线）                        |
//| 返回该周期实际可用的最早日期(0=失败)                              |
//+------------------------------------------------------------------+
datetime EnsureBarsHistory(string symbol, ENUM_TIMEFRAMES tf, datetime from)
{
   datetime first = 0;
   datetime deadline = TimeLocal() + InpSyncWaitSec;
   MqlRates tmp[];
   while(TimeLocal() < deadline)
   {
      // 触发后台下载：请求 from 附近的少量K线
      ResetLastError();
      CopyRates(symbol, tf, from, 3, tmp);
      // 触发整条序列同步
      datetime stop = TimeCurrent();
      Bars(symbol, tf, from, stop);
      first = (datetime)SeriesInfoInteger(symbol, tf, SERIES_FIRSTDATE);

      if(first > 0 && first <= from)
         return first;            // 已覆盖请求起点
      if(IsStopped()) break;
      Sleep(500);
   }
   // 超时：返回当前已知最早日期(可能晚于 from，表示券商只有这么多)
   if(first <= 0) first = (datetime)SeriesInfoInteger(symbol, tf, SERIES_FIRSTDATE);
   return first;
}

//+------------------------------------------------------------------+
//| 带重试的 CopyRates（按时间范围）                                  |
//+------------------------------------------------------------------+
int CopyRatesRetry(string symbol, ENUM_TIMEFRAMES tf, datetime from, datetime to, MqlRates &rates[])
{
   for(int a=0; a<=InpMaxRetries; a++)
   {
      ResetLastError();
      int got = CopyRates(symbol, tf, from, to, rates);
      if(got > 0) return got;
      int err = GetLastError();
      // 4401/4073/4074 等：历史仍在加载 → 等待重试
      if(got < 0 || err==4401 || err==4073 || err==4074 || err==4066)
      {
         if(IsStopped()) return got;
         Sleep(InpRetrySleepMs);
         continue;
      }
      return 0;   // 该区间确实无数据
   }
   return 0;
}

//+------------------------------------------------------------------+
//| 带重试的 CopyTicksRange                                          |
//+------------------------------------------------------------------+
int CopyTicksRetry(string symbol, MqlTick &ticks[], ulong from_msc, ulong to_msc, int max_retries)
{
   for(int a=0; a<=max_retries; a++)
   {
      ResetLastError();
      int got = CopyTicksRange(symbol, ticks, COPY_TICKS_ALL, from_msc, to_msc);
      if(got > 0) return got;
      int err = GetLastError();
      if(got < 0 || err==4401 || err==4073 || err==4074 || err==4066)
      {
         if(IsStopped()) return got;
         Sleep(InpRetrySleepMs);
         continue;
      }
      return 0;
   }
   return 0;
}

//+------------------------------------------------------------------+
//| 导出某月 tick（按天分片 + 重试）                                  |
//+------------------------------------------------------------------+
long ExportMonthTicks(string symbol, int y, int m, string out_root, datetime tick_avail_from)
{
   string rel = out_root + "/" + symbol + "/ticks/" + IntegerToString(y) + "-" + MM(m) + ".csv";
   if(!InpOverwrite && FileIsExist(rel, InpUseCommonFiles?FILE_COMMON:0))
   { PrintFormat("  [ticks] %d-%s 已存在，跳过", y, MM(m)); return 0; }

   datetime m_start = MonthStart(y, m);
   int ny, nm; NextMonth(y, m, ny, nm);
   datetime m_end = MonthStart(ny, nm);

   // 整月早于券商可用 tick 起点 → 直接跳过(避免空等)
   if(tick_avail_from > 0 && m_end <= tick_avail_from)
   { PrintFormat("  [ticks] %d-%s 早于券商可用tick起点(%s)，跳过", y, MM(m), IsoTime(tick_avail_from)); return 0; }

   MqlTick ticks[];
   long total = 0;
   int fh = INVALID_HANDLE;

   for(datetime day = m_start; day < m_end; day += 86400)
   {
      datetime day_end = day + 86400;
      if(day_end > m_end) day_end = m_end;
      ulong from_msc = (ulong)day * 1000;
      ulong to_msc   = (ulong)day_end * 1000 - 1;

      // 早于可用起点的日跳过
      if(tick_avail_from > 0 && day_end <= tick_avail_from) continue;

      int got = CopyTicksRetry(symbol, ticks, from_msc, to_msc, InpMaxRetries);
      if(got <= 0) continue;

      if(fh == INVALID_HANDLE)
      {
         fh = FileOpen(rel, FileFlagsCsv(), ',');
         if(fh == INVALID_HANDLE){ PrintFormat("  [ticks] 打开失败 %s err=%d", rel, GetLastError()); return -1; }
         FileWrite(fh, "time_msc","time_iso","bid","ask","last","volume","volume_real","flags","spread_pts");
      }
      for(int i=0;i<got;i++)
      {
         double spr = (ticks[i].ask>0 && ticks[i].bid>0) ? (ticks[i].ask-ticks[i].bid)/G_Point : 0.0;
         FileWrite(fh, (string)ticks[i].time_msc, IsoTime(ticks[i].time),
                   Px(ticks[i].bid), Px(ticks[i].ask), Px(ticks[i].last),
                   (string)ticks[i].volume, DoubleToString(ticks[i].volume_real,2),
                   (string)ticks[i].flags, DoubleToString(spr,1));
      }
      total += got;
   }

   if(fh != INVALID_HANDLE){ FileFlush(fh); FileClose(fh); PrintFormat("  [ticks] %d-%s 导出 %I64d 条 → %s", y, MM(m), total, rel); }
   else PrintFormat("  [ticks] %d-%s 无数据", y, MM(m));
   return total;
}

//+------------------------------------------------------------------+
//| 导出某月 K 线（重试）                                            |
//+------------------------------------------------------------------+
long ExportMonthBars(string symbol, ENUM_TIMEFRAMES tf, string tf_name, int y, int m, string out_root)
{
   string rel = out_root + "/" + symbol + "/" + tf_name + "/" + IntegerToString(y) + "-" + MM(m) + ".csv";
   if(!InpOverwrite && FileIsExist(rel, InpUseCommonFiles?FILE_COMMON:0))
   { PrintFormat("  [%s] %d-%s 已存在，跳过", tf_name, y, MM(m)); return 0; }

   datetime m_start = MonthStart(y, m);
   int ny, nm; NextMonth(y, m, ny, nm);
   datetime m_end = MonthStart(ny, nm) - 1;

   MqlRates rates[];
   int got = CopyRatesRetry(symbol, tf, m_start, m_end, rates);
   if(got <= 0){ PrintFormat("  [%s] %d-%s 无数据", tf_name, y, MM(m)); return 0; }

   int fh = FileOpen(rel, FileFlagsCsv(), ',');
   if(fh == INVALID_HANDLE){ PrintFormat("  [%s] 打开失败 %s err=%d", tf_name, rel, GetLastError()); return -1; }
   FileWrite(fh, "time","time_iso","open","high","low","close","tick_volume","spread","real_volume");
   for(int i=0;i<got;i++)
      FileWrite(fh, (string)(long)rates[i].time, IsoTime(rates[i].time),
                Px(rates[i].open), Px(rates[i].high), Px(rates[i].low), Px(rates[i].close),
                (string)rates[i].tick_volume, (string)rates[i].spread, (string)rates[i].real_volume);
   FileFlush(fh); FileClose(fh);
   PrintFormat("  [%s] %d-%s 导出 %d 根 → %s", tf_name, y, MM(m), got, rel);
   return got;
}

//+------------------------------------------------------------------+
//| 探测某周期实际可用最早日期(用于预检/打印)                         |
//+------------------------------------------------------------------+
datetime ProbeBarsFirstDate(string symbol, ENUM_TIMEFRAMES tf, datetime want_from)
{
   return EnsureBarsHistory(symbol, tf, want_from);
}
datetime ProbeTicksFirstDate(string symbol, datetime want_from)
{
   // 从 want_from 起，按月向后探测，找到第一个有 tick 的月份起点
   datetime now = TimeCurrent();
   int y, m; { MqlDateTime t; TimeToStruct(want_from,t); y=t.year; m=t.mon; }
   MqlTick tk[];
   while(MonthStart(y,m) < now)
   {
      datetime ms = MonthStart(y,m);
      int ny,nm; NextMonth(y,m,ny,nm);
      datetime me = MonthStart(ny,nm);
      int got = CopyTicksRetry(symbol, tk, (ulong)ms*1000, (ulong)me*1000-1, MathMin(5,InpMaxRetries));
      if(got > 0) return tk[0].time;   // 该月第一条 tick 时间
      y=ny; m=nm;
      if(IsStopped()) break;
   }
   return 0;
}

//+------------------------------------------------------------------+
//| 写 meta.json（供 eva006 自动识别点值）                           |
//+------------------------------------------------------------------+
void WriteMeta(string symbol, string out_root, datetime m1_first, datetime tick_first)
{
   string rel = out_root + "/" + symbol + "/meta.json";
   int fh = FileOpen(rel, FILE_WRITE|FILE_TXT|FILE_ANSI | (InpUseCommonFiles?FILE_COMMON:0));
   if(fh == INVALID_HANDLE){ PrintFormat("写 meta.json 失败 err=%d", GetLastError()); return; }
   string js = "{\n";
   js += "  \"symbol\": \"" + symbol + "\",\n";
   js += "  \"symbol_digits\": " + IntegerToString(G_SymDigits) + ",\n";
   js += "  \"output_digits\": " + IntegerToString(G_OutDigits) + ",\n";
   js += "  \"point\": " + DoubleToString(G_Point, G_OutDigits+2) + ",\n";
   js += "  \"m1_first_date\": \"" + (m1_first>0?IsoTime(m1_first):"") + "\",\n";
   js += "  \"tick_first_date\": \"" + (tick_first>0?IsoTime(tick_first):"") + "\",\n";
   js += "  \"generated\": \"" + IsoTime(TimeCurrent()) + "\"\n";
   js += "}\n";
   FileWriteString(fh, js);
   FileClose(fh);
   PrintFormat("已写 meta.json: digits=%d point=%s → %s", G_OutDigits, DoubleToString(G_Point,G_OutDigits+2), rel);
}

//+------------------------------------------------------------------+
void OnStart()
{
   string symbol = (InpExportSymbol=="" ? _Symbol : InpExportSymbol);
   if(!SymbolSelect(symbol, true)){ PrintFormat("无法选择品种 %s，请先在市场报价中添加。", symbol); return; }

   if(!(bool)TerminalInfoInteger(TERMINAL_CONNECTED))
      Print("⚠️ 终端未连接服务器，历史可能无法下载。请先连线后重试。");

   G_SymDigits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   G_Point     = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(G_Point <= 0) G_Point = MathPow(10, -G_SymDigits);
   if(InpPricePrecision >= 0) G_OutDigits = InpPricePrecision;
   else                       G_OutDigits = MathMax(G_SymDigits, InpForceMinDigits);

   PrintFormat("==== eva005 导出 %s ====", symbol);
   PrintFormat("品种报价: SYMBOL_DIGITS=%d, SYMBOL_POINT=%s → 输出位数=%d",
               G_SymDigits, DoubleToString(G_Point, 8), G_OutDigits);
   if(G_SymDigits < InpForceMinDigits)
      PrintFormat("提示: 检测到品种为 %d 位。若你确信黄金应为 3 位，请确认当前图表品种(%s)是否为 3 位的那个变体；"
                  "本脚本已按 max(品种位数,%d)=%d 位输出，不会截断 3 位精度。",
                  G_SymDigits, symbol, InpForceMinDigits, G_OutDigits);

   PrintFormat("K线区间 %d-%s ~ %d-%s ；tick区间 %d-%s ~ %d-%s",
               InpFromYear,MM(InpFromMonth),InpToYear,MM(InpToMonth),
               InpTickFromYear,MM(InpTickFromMonth),InpTickToYear,MM(InpTickToMonth));
   PrintFormat("写入: %s\\Files\\%s\\%s  (等待%ds, 重试%d×%dms)",
               (InpUseCommonFiles?"Common":"Terminal"), InpOutRoot, symbol,
               InpSyncWaitSec, InpMaxRetries, InpRetrySleepMs);

   // ---- 预检：把历史下载触发起来，并打印实际可用最早日期 ----
   datetime want_bars_from = MonthStart(InpFromYear, InpFromMonth);
   datetime want_tick_from = MonthStart(InpTickFromYear, InpTickFromMonth);

   Print("---- 预检/触发历史下载（可能需要较久，请耐心等待）----");
   datetime m1_first  = InpExportM1 ? ProbeBarsFirstDate(symbol, PERIOD_M1, want_bars_from) : 0;
   datetime m5_first  = InpExportM5 ? ProbeBarsFirstDate(symbol, PERIOD_M5, want_bars_from) : 0;
   if(InpExportM1) PrintFormat("M1 可用最早: %s", m1_first>0?IsoTime(m1_first):"未知");
   if(InpExportM5) PrintFormat("M5 可用最早: %s", m5_first>0?IsoTime(m5_first):"未知");

   datetime tick_first = 0;
   if(InpExportTicks)
   {
      tick_first = ProbeTicksFirstDate(symbol, want_tick_from);
      PrintFormat("tick 可用最早: %s %s", tick_first>0?IsoTime(tick_first):"未找到",
                  tick_first>0?"":"(该券商在所选起点后无真实tick；老年份真实tick通常不存在)");
   }

   WriteMeta(symbol, InpOutRoot, m1_first, tick_first);

   // ---- 导出 K 线（全程区间） ----
   long grand_bars = 0;
   {
      long from_key=(long)InpFromYear*12+(InpFromMonth-1), to_key=(long)InpToYear*12+(InpToMonth-1);
      if(to_key >= from_key)
      {
         int y=InpFromYear, m=InpFromMonth;
         while((long)y*12+(m-1) <= to_key)
         {
            if(InpExportM1)  grand_bars += ExportMonthBars(symbol, PERIOD_M1,  "m1",  y, m, InpOutRoot);
            if(InpExportM5)  grand_bars += ExportMonthBars(symbol, PERIOD_M5,  "m5",  y, m, InpOutRoot);
            if(InpExportM15) grand_bars += ExportMonthBars(symbol, PERIOD_M15, "m15", y, m, InpOutRoot);
            int ny,nm; NextMonth(y,m,ny,nm); y=ny; m=nm;
            if(IsStopped()) break;
         }
      }
   }

   // ---- 导出 tick（独立区间） ----
   long grand_ticks = 0;
   if(InpExportTicks)
   {
      long from_key=(long)InpTickFromYear*12+(InpTickFromMonth-1), to_key=(long)InpTickToYear*12+(InpTickToMonth-1);
      if(to_key >= from_key)
      {
         int y=InpTickFromYear, m=InpTickFromMonth;
         while((long)y*12+(m-1) <= to_key)
         {
            long r = ExportMonthTicks(symbol, y, m, InpOutRoot, tick_first);
            if(r > 0) grand_ticks += r;
            int ny,nm; NextMonth(y,m,ny,nm); y=ny; m=nm;
            if(IsStopped()) break;
         }
      }
   }

   PrintFormat("==== eva005 完成: tick=%I64d 条, bar=%I64d 根 ====", grand_ticks, grand_bars);
   Print("若 K线/ tick 数量仍明显偏少：1) 确认终端已连线；2) Tools→Options→Charts 把"
         "“Max bars in chart”设为 Unlimited；3) 真实 tick 想要更久，可先在测试器用"
         "“Every tick based on real ticks”模式跑一遍该区间(会缓存真实tick)，再运行本脚本导出。");
}
//+------------------------------------------------------------------+
