//+------------------------------------------------------------------+
//|                                       eva001_TickDataExporter.mq5 |
//|   行情数据导出脚本（tick + M1/M5/M15/策略周期），按 品种/周期/月 分块 |
//|                                                                  |
//|   作用：通过 MQL5 官方接口 CopyTicksRange / CopyRates 把 MT5 本地   |
//|         能访问的历史数据导出为 CSV，构建独立行情数据仓库。           |
//|         不解析任何 MT5 底层私有文件，输出尽量无损（time_msc 全精度， |
//|         价格按品种 Digits 全精度）。                                |
//|                                                                  |
//|   用法：把脚本拖到目标品种(如 XAUUSD)图表上运行，弹窗里设置年月区间   |
//|         与要导出的周期，点确定即可。导出完成后在日志里会打印路径。     |
//|                                                                  |
//|   产物目录结构（默认写入 Common\Files，跨终端/跨机器可取用）：        |
//|     <OutRoot>/XAUUSD/ticks/2024-01.csv                            |
//|     <OutRoot>/XAUUSD/m1/2024-01.csv                               |
//|     <OutRoot>/XAUUSD/m5/2024-01.csv                               |
//|     <OutRoot>/XAUUSD/m15/2024-01.csv                              |
//|                                                                  |
//|   配套：eva003_data_pipeline.py 直接读取该目录做切片与分析。          |
//+------------------------------------------------------------------+
#property copyright "eva pipeline"
#property version   "1.00"
#property script_show_inputs
#property strict

//--- 导出区间与内容
input string InpExportSymbol   = "";        // 导出品种（留空=当前图表品种，建议 XAUUSD）
input int    InpFromYear       = 2018;      // 起始年
input int    InpFromMonth      = 1;         // 起始月(1-12)
input int    InpToYear         = 2026;      // 结束年（含）
input int    InpToMonth        = 12;        // 结束月（含，1-12）

input bool   InpExportTicks    = true;      // 导出真实 tick（COPY_TICKS_ALL）
input bool   InpExportM1       = true;      // 导出 M1 K线
input bool   InpExportM5       = true;      // 导出 M5 K线
input bool   InpExportM15      = false;     // 导出 M15 K线

input string InpOutRoot        = "eva_data";// 输出根目录名（位于 Files 内）
input bool   InpUseCommonFiles = true;      // true=写入 Common\Files（跨终端可取）；false=本地沙箱 Files
input bool   InpOverwrite      = true;      // 已存在的月文件是否覆盖；false=跳过（便于断点续传/增量）
input bool   InpSkipEmptyMonth = true;      // 无数据的月份不生成空文件
input int    InpPricePrecision = -1;        // 价格小数位：-1=按品种 Digits（推荐，无损）；>=0 手动指定

//+------------------------------------------------------------------+
int FileFlagsCsv()
{
   int f = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFiles)
      f |= FILE_COMMON;
   return f;
}
int FileFlagsCheck()
{
   int f = FILE_READ;
   if(InpUseCommonFiles)
      f |= FILE_COMMON;
   return f;
}

//--- 月份起点 datetime
datetime MonthStart(int y, int m)
{
   MqlDateTime t;
   t.year = y; t.mon = m; t.day = 1;
   t.hour = 0; t.min = 0; t.sec = 0;
   return StructToTime(t);
}
//--- 下一月起点
void NextMonth(int y, int m, int &ny, int &nm)
{
   if(m >= 12) { ny = y + 1; nm = 1; }
   else        { ny = y;     nm = m + 1; }
}

//--- 两位月份字符串
string MM(int m){ return (m < 10 ? "0" : "") + IntegerToString(m); }

//--- ISO 时间字符串（秒级，用于人读；机读以 time_msc 为准）
string IsoTime(datetime t)
{
   return TimeToString(t, TIME_DATE | TIME_SECONDS); // "YYYY.MM.DD HH:MM:SS"
}

//--- 价格格式化（无损：按 Digits）
int    G_Digits = 2;
double G_Point  = 0.01;
string Px(double p){ return DoubleToString(p, G_Digits); }

//+------------------------------------------------------------------+
//| 导出某月 tick（按天分片，避免单次内存过大）                       |
//| 返回写出的 tick 数；-1 表示失败                                   |
//+------------------------------------------------------------------+
long ExportMonthTicks(string symbol, int y, int m, string out_root)
{
   string rel = out_root + "/" + symbol + "/ticks/" + IntegerToString(y) + "-" + MM(m) + ".csv";

   if(!InpOverwrite && FileIsExist(rel, InpUseCommonFiles ? FILE_COMMON : 0))
   {
      PrintFormat("  [ticks] %d-%s 已存在，跳过", y, MM(m));
      return 0;
   }

   datetime m_start = MonthStart(y, m);
   int ny, nm; NextMonth(y, m, ny, nm);
   datetime m_end = MonthStart(ny, nm);

   // 先收集到内存，确认有数据再开文件，避免空文件
   MqlTick ticks[];
   long total = 0;

   int fh = INVALID_HANDLE;

   // 按天分片
   for(datetime day = m_start; day < m_end; day += 86400)
   {
      datetime day_end = day + 86400;
      if(day_end > m_end) day_end = m_end;

      ulong from_msc = (ulong)day * 1000;
      ulong to_msc   = (ulong)day_end * 1000 - 1;

      int got = CopyTicksRange(symbol, ticks, COPY_TICKS_ALL, from_msc, to_msc);
      if(got <= 0)
         continue;

      if(fh == INVALID_HANDLE)
      {
         fh = FileOpen(rel, FileFlagsCsv(), ',');
         if(fh == INVALID_HANDLE)
         {
            PrintFormat("  [ticks] 打开文件失败 %s err=%d", rel, GetLastError());
            return -1;
         }
         // 表头
         FileWrite(fh, "time_msc", "time_iso", "bid", "ask", "last",
                       "volume", "volume_real", "flags", "spread_pts");
      }

      for(int i = 0; i < got; i++)
      {
         double spread_pts = (ticks[i].ask > 0 && ticks[i].bid > 0)
                             ? (ticks[i].ask - ticks[i].bid) / G_Point : 0.0;
         FileWrite(fh,
                   (string)ticks[i].time_msc,
                   IsoTime(ticks[i].time),
                   Px(ticks[i].bid),
                   Px(ticks[i].ask),
                   Px(ticks[i].last),
                   (string)ticks[i].volume,
                   DoubleToString(ticks[i].volume_real, 2),
                   (string)ticks[i].flags,
                   DoubleToString(spread_pts, 1));
      }
      total += got;
   }

   if(fh != INVALID_HANDLE)
   {
      FileFlush(fh);
      FileClose(fh);
      PrintFormat("  [ticks] %d-%s 导出 %I64d 条 → %s", y, MM(m), total, rel);
   }
   else if(!InpSkipEmptyMonth)
   {
      fh = FileOpen(rel, FileFlagsCsv(), ',');
      if(fh != INVALID_HANDLE)
      {
         FileWrite(fh, "time_msc", "time_iso", "bid", "ask", "last",
                       "volume", "volume_real", "flags", "spread_pts");
         FileClose(fh);
      }
      PrintFormat("  [ticks] %d-%s 无数据(已写空文件)", y, MM(m));
   }
   else
   {
      PrintFormat("  [ticks] %d-%s 无数据(跳过)", y, MM(m));
   }
   return total;
}

//+------------------------------------------------------------------+
//| 导出某月 K线                                                     |
//+------------------------------------------------------------------+
long ExportMonthBars(string symbol, ENUM_TIMEFRAMES tf, string tf_name, int y, int m, string out_root)
{
   string rel = out_root + "/" + symbol + "/" + tf_name + "/" + IntegerToString(y) + "-" + MM(m) + ".csv";

   if(!InpOverwrite && FileIsExist(rel, InpUseCommonFiles ? FILE_COMMON : 0))
   {
      PrintFormat("  [%s] %d-%s 已存在，跳过", tf_name, y, MM(m));
      return 0;
   }

   datetime m_start = MonthStart(y, m);
   int ny, nm; NextMonth(y, m, ny, nm);
   datetime m_end = MonthStart(ny, nm) - 1;

   MqlRates rates[];
   int got = CopyRates(symbol, tf, m_start, m_end, rates);
   if(got <= 0)
   {
      if(!InpSkipEmptyMonth)
      {
         int fh0 = FileOpen(rel, FileFlagsCsv(), ',');
         if(fh0 != INVALID_HANDLE)
         {
            FileWrite(fh0, "time", "time_iso", "open", "high", "low", "close",
                           "tick_volume", "spread", "real_volume");
            FileClose(fh0);
         }
      }
      PrintFormat("  [%s] %d-%s 无数据", tf_name, y, MM(m));
      return 0;
   }

   int fh = FileOpen(rel, FileFlagsCsv(), ',');
   if(fh == INVALID_HANDLE)
   {
      PrintFormat("  [%s] 打开文件失败 %s err=%d", tf_name, rel, GetLastError());
      return -1;
   }
   FileWrite(fh, "time", "time_iso", "open", "high", "low", "close",
                 "tick_volume", "spread", "real_volume");

   for(int i = 0; i < got; i++)
   {
      FileWrite(fh,
                (string)(long)rates[i].time,
                IsoTime(rates[i].time),
                Px(rates[i].open),
                Px(rates[i].high),
                Px(rates[i].low),
                Px(rates[i].close),
                (string)rates[i].tick_volume,
                (string)rates[i].spread,
                (string)rates[i].real_volume);
   }
   FileFlush(fh);
   FileClose(fh);
   PrintFormat("  [%s] %d-%s 导出 %d 根 → %s", tf_name, y, MM(m), got, rel);
   return got;
}

//+------------------------------------------------------------------+
//| 入口                                                             |
//+------------------------------------------------------------------+
void OnStart()
{
   string symbol = (InpExportSymbol == "" ? _Symbol : InpExportSymbol);

   // 确保品种已在“市场报价”中并已同步历史
   if(!SymbolSelect(symbol, true))
   {
      PrintFormat("无法选择品种 %s，请先在市场报价中添加。", symbol);
      return;
   }

   G_Digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(InpPricePrecision >= 0) G_Digits = InpPricePrecision;
   G_Point  = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(G_Point <= 0) G_Point = MathPow(10, -G_Digits);

   PrintFormat("==== eva001 导出开始: %s  区间 %d-%s ~ %d-%s ====",
               symbol, InpFromYear, MM(InpFromMonth), InpToYear, MM(InpToMonth));
   PrintFormat("写入位置: %s\\Files\\%s\\%s  (Digits=%d)",
               (InpUseCommonFiles ? "Common" : "Terminal"), InpOutRoot, symbol, G_Digits);

   // 校验区间
   long from_key = (long)InpFromYear * 12 + (InpFromMonth - 1);
   long to_key   = (long)InpToYear   * 12 + (InpToMonth   - 1);
   if(to_key < from_key)
   {
      Print("结束月份早于起始月份，已终止。");
      return;
   }

   long grand_ticks = 0, grand_bars = 0;
   int  y = InpFromYear, m = InpFromMonth;

   while(true)
   {
      long key = (long)y * 12 + (m - 1);
      if(key > to_key) break;

      PrintFormat("---- %d-%s ----", y, MM(m));

      if(InpExportTicks)
      {
         long r = ExportMonthTicks(symbol, y, m, InpOutRoot);
         if(r > 0) grand_ticks += r;
      }
      if(InpExportM1)
         grand_bars += ExportMonthBars(symbol, PERIOD_M1, "m1", y, m, InpOutRoot);
      if(InpExportM5)
         grand_bars += ExportMonthBars(symbol, PERIOD_M5, "m5", y, m, InpOutRoot);
      if(InpExportM15)
         grand_bars += ExportMonthBars(symbol, PERIOD_M15, "m15", y, m, InpOutRoot);

      int ny, nm; NextMonth(y, m, ny, nm);
      y = ny; m = nm;
   }

   PrintFormat("==== eva001 导出完成: 共 tick=%I64d 条, bar=%I64d 根 ====", grand_ticks, grand_bars);
   PrintFormat("提示: 若 tick 数为 0，多为该券商历史中心无对应真实 tick；可在“品种-导入”或工具栏下载历史后重试。");
}
//+------------------------------------------------------------------+
