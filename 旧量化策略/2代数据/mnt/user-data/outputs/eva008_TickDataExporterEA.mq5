//+------------------------------------------------------------------+
//|                                     eva008_TickDataExporterEA.mq5 |
//|  行情数据导出 EA（第3代/eva008）——在“策略测试器”里运行，导出完整历史 |
//|                                                                  |
//|  为什么要做成 EA + 测试器（解决 eva005 实时脚本只导到近月的根因）：   |
//|   - 实时图表上的脚本读的是“终端实时历史缓存”，深层历史不自动拉满，    |
//|     所以只看到近几个月；                                            |
//|   - 而“策略测试器”会为回测区间装载【完整历史】(2014→今)，EA 在测试器  |
//|     里能看到每一个 tick / 每一根 bar，并且【可以写文件】。           |
//|   - 因此把导出器做成 EA，在测试器里“收一个写一个”，即可拿到完整数据。  |
//|                                                                  |
//|  用法（重点）：                                                    |
//|   A) 导出完整 M1/M5（推荐先做，覆盖 2014→今，量大但稳）：             |
//|      策略测试器 → 品种 XAUUSDm → 周期随意 → 日期 2014.01.01~今 →     |
//|      模型选 “1 minute OHLC” → Optimization=Disabled →             |
//|      InpExportM1=true, InpExportM5=true, InpExportTicks=false → 开始。|
//|   B) 导出真实 tick（按需，建议只取近几年，文件巨大）：               |
//|      模型选 “Every tick based on real ticks” → 日期设近几年 →       |
//|      InpExportTicks=true（bar 可同时导）→ 开始。                    |
//|                                                                  |
//|  产物与 eva005 同构，可被 eva008 的 Python 直接读取：               |
//|      <root>/XAUUSDm/{ticks,m1,m5,m15}/YYYY-MM.csv  + meta.json     |
//|  注意：M1/M5 的 tick_volume = 价格变化次数（你策略用的“量”），       |
//|        来自 Exness 历史，不脱离实盘。                               |
//+------------------------------------------------------------------+
#property copyright "eva pipeline"
#property version   "3.00"
#property strict

input bool   InpExportTicks    = false;     // 导出真实 tick（必须用“real ticks”模型，否则是合成tick）
input bool   InpExportM1       = true;      // 导出 M1
input bool   InpExportM5       = true;      // 导出 M5
input bool   InpExportM15      = false;     // 导出 M15

input string InpTickFromDate   = "";        // 仅导出该日期之后的 tick（留空=不限），如 2022.01.01
input string InpTickToDate     = "";        // 仅导出该日期之前的 tick（留空=不限）

input string InpOutRoot        = "eva_data";// 输出根目录名(位于 Files 内)
input bool   InpUseCommonFiles = true;      // true=写 Common\Files(跨终端可取)
input int    InpForceMinDigits = 3;         // 价格最少小数位(黄金3位防截断)
input int    InpPricePrecision = -1;        // 手动指定价格小数位：-1=用 max(品种Digits, ForceMinDigits)
input int    InpFlushEveryN    = 5000;      // 每写 N 行 flush 一次(性能/安全折中)

//--- 数据流（tick / 每个周期一个）
struct EvaStream
{
   int      handle;
   int      cur_year;
   int      cur_mon;
   string   subdir;
   bool     is_tick;
   long     count;
   datetime last_bar_time;   // 仅 bar 用：已写出的最后一根 bar 的时间
};

EvaStream G_Tick, G_M1, G_M5, G_M15;

int      G_OutDigits = 3;
int      G_SymDigits = 3;
double   G_Point     = 0.001;
bool     G_Active    = false;
datetime G_TickFrom  = 0;
datetime G_TickTo    = 0;
long     G_LastTickMsc = 0;
datetime G_MinTime = 0, G_MaxTime = 0;        // 观测到的数据时间范围
datetime G_TickMinTime = 0, G_TickMaxTime = 0;
long     G_TotalTicks = 0, G_TotalBars = 0;
int      G_ReportedMonth = -1;

//+------------------------------------------------------------------+
int FileFlagsCsv()
{
   int f = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFiles) f |= FILE_COMMON;
   return f;
}
string MM(int m){ return (m<10?"0":"") + IntegerToString(m); }
string IsoTime(datetime t){ return TimeToString(t, TIME_DATE | TIME_SECONDS); }
string Px(double p){ return DoubleToString(p, G_OutDigits); }

void StreamInit(EvaStream &s, string subdir, bool is_tick)
{
   s.handle = INVALID_HANDLE; s.cur_year = -1; s.cur_mon = -1;
   s.subdir = subdir; s.is_tick = is_tick; s.count = 0; s.last_bar_time = 0;
}

void StreamClose(EvaStream &s)
{
   if(s.handle != INVALID_HANDLE){ FileFlush(s.handle); FileClose(s.handle); s.handle = INVALID_HANDLE; }
}

//--- 按月轮转：若 t 的年月与当前文件不同，则关旧开新并写表头
void StreamRotate(EvaStream &s, string symbol, datetime t)
{
   MqlDateTime d; TimeToStruct(t, d);
   if(s.handle != INVALID_HANDLE && d.year == s.cur_year && d.mon == s.cur_mon)
      return;

   StreamClose(s);
   s.cur_year = d.year; s.cur_mon = d.mon;
   string rel = InpOutRoot + "/" + symbol + "/" + s.subdir + "/" +
                IntegerToString(d.year) + "-" + MM(d.mon) + ".csv";
   s.handle = FileOpen(rel, FileFlagsCsv(), ',');
   if(s.handle == INVALID_HANDLE)
   {
      PrintFormat("[eva008] 打开文件失败 %s err=%d", rel, GetLastError());
      return;
   }
   if(s.is_tick)
      FileWrite(s.handle, "time_msc","time_iso","bid","ask","last",
                          "volume","volume_real","flags","spread_pts");
   else
      FileWrite(s.handle, "time","time_iso","open","high","low","close",
                          "tick_volume","spread","real_volume");

   if(d.mon != G_ReportedMonth)
   {
      G_ReportedMonth = d.mon;
      PrintFormat("[eva008] 导出进行中… 当前 %d-%s", d.year, MM(d.mon));
   }
}

//+------------------------------------------------------------------+
//| 写一行 tick                                                      |
//+------------------------------------------------------------------+
void WriteTick(string symbol, const MqlTick &tk)
{
   if(G_TickFrom > 0 && tk.time < G_TickFrom) return;
   if(G_TickTo   > 0 && tk.time > G_TickTo)   return;

   StreamRotate(G_Tick, symbol, tk.time);
   if(G_Tick.handle == INVALID_HANDLE) return;

   double spr = (tk.ask>0 && tk.bid>0) ? (tk.ask - tk.bid)/G_Point : 0.0;
   FileWrite(G_Tick.handle,
             (string)tk.time_msc, IsoTime(tk.time),
             Px(tk.bid), Px(tk.ask), Px(tk.last),
             (string)tk.volume, DoubleToString(tk.volume_real,2),
             (string)tk.flags, DoubleToString(spr,1));
   G_Tick.count++; G_TotalTicks++;
   if((G_Tick.count % InpFlushEveryN) == 0) FileFlush(G_Tick.handle);

   if(G_TickMinTime == 0) G_TickMinTime = tk.time;
   G_TickMaxTime = tk.time;
}

//+------------------------------------------------------------------+
//| 写一根 bar（指定 shift）                                          |
//+------------------------------------------------------------------+
void WriteBar(EvaStream &s, string symbol, ENUM_TIMEFRAMES tf, int shift)
{
   datetime bt = iTime(symbol, tf, shift);
   if(bt <= 0) return;
   if(bt <= s.last_bar_time) return;   // 已写过，避免重复

   StreamRotate(s, symbol, bt);
   if(s.handle == INVALID_HANDLE) return;

   FileWrite(s.handle,
             (string)(long)bt, IsoTime(bt),
             Px(iOpen(symbol,tf,shift)), Px(iHigh(symbol,tf,shift)),
             Px(iLow(symbol,tf,shift)),  Px(iClose(symbol,tf,shift)),
             (string)iTickVolume(symbol,tf,shift),
             (string)(long)iSpread(symbol,tf,shift),
             (string)iRealVolume(symbol,tf,shift));
   s.last_bar_time = bt; s.count++; G_TotalBars++;
   if((s.count % InpFlushEveryN) == 0) FileFlush(s.handle);

   if(G_MinTime == 0) G_MinTime = bt;
   G_MaxTime = bt;
}

//--- 检测新 bar：若 shift0 时间变化，说明 shift1 那根已收盘 → 写 shift1
void HandleBarStream(EvaStream &s, string symbol, ENUM_TIMEFRAMES tf, bool enabled)
{
   if(!enabled) return;
   datetime t0 = iTime(symbol, tf, 0);
   if(t0 <= 0) return;
   // 写出所有已收盘但尚未写的 bar（通常只 1 根；跳空/首根时可能多根）
   for(int shift = 1; shift <= 2; shift++)
   {
      datetime bt = iTime(symbol, tf, shift);
      if(bt > 0 && bt > s.last_bar_time)
         WriteBar(s, symbol, tf, shift);
   }
}

//+------------------------------------------------------------------+
//| 写 meta.json                                                     |
//+------------------------------------------------------------------+
void WriteMeta(string symbol)
{
   string rel = InpOutRoot + "/" + symbol + "/meta.json";
   int fh = FileOpen(rel, FILE_WRITE|FILE_TXT|FILE_ANSI | (InpUseCommonFiles?FILE_COMMON:0));
   if(fh == INVALID_HANDLE){ PrintFormat("[eva008] 写 meta.json 失败 err=%d", GetLastError()); return; }
   string js = "{\n";
   js += "  \"symbol\": \"" + symbol + "\",\n";
   js += "  \"symbol_digits\": " + IntegerToString(G_SymDigits) + ",\n";
   js += "  \"output_digits\": " + IntegerToString(G_OutDigits) + ",\n";
   js += "  \"point\": " + DoubleToString(G_Point, G_OutDigits+2) + ",\n";
   js += "  \"exported_by\": \"eva008_TickDataExporterEA(tester)\",\n";
   js += "  \"bar_first_date\": \"" + (G_MinTime>0?IsoTime(G_MinTime):"") + "\",\n";
   js += "  \"bar_last_date\": \""  + (G_MaxTime>0?IsoTime(G_MaxTime):"") + "\",\n";
   js += "  \"tick_first_date\": \"" + (G_TickMinTime>0?IsoTime(G_TickMinTime):"") + "\",\n";
   js += "  \"tick_last_date\": \""  + (G_TickMaxTime>0?IsoTime(G_TickMaxTime):"") + "\",\n";
   js += "  \"total_ticks\": " + IntegerToString(G_TotalTicks) + ",\n";
   js += "  \"total_bars\": "  + IntegerToString(G_TotalBars) + ",\n";
   js += "  \"generated\": \"" + IsoTime(TimeCurrent()) + "\"\n";
   js += "}\n";
   FileWriteString(fh, js);
   FileClose(fh);
}

//+------------------------------------------------------------------+
int OnInit()
{
   // 优化模式：多 pass 会抢同一文件 → 直接禁用导出
   if((bool)MQLInfoInteger(MQL_OPTIMIZATION))
   {
      Print("[eva008] 检测到 Optimization 模式：导出已禁用。请把测试器的 Optimization 设为 Disabled 再单次运行。");
      G_Active = false;
      return(INIT_SUCCEEDED);
   }
   if(!(bool)MQLInfoInteger(MQL_TESTER))
      Print("[eva008] ⚠️ 本 EA 设计用于【策略测试器】单次回测导出完整历史；实时挂载只能拿到近月数据。");

   G_SymDigits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   G_Point     = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(G_Point <= 0) G_Point = MathPow(10, -G_SymDigits);
   G_OutDigits = (InpPricePrecision >= 0) ? InpPricePrecision : MathMax(G_SymDigits, InpForceMinDigits);

   G_TickFrom = (InpTickFromDate=="" ? 0 : StringToTime(InpTickFromDate));
   G_TickTo   = (InpTickToDate==""   ? 0 : StringToTime(InpTickToDate));

   StreamInit(G_Tick, "ticks", true);
   StreamInit(G_M1,   "m1",    false);
   StreamInit(G_M5,   "m5",    false);
   StreamInit(G_M15,  "m15",   false);

   G_Active = true;
   PrintFormat("[eva008] 导出启动: %s  SYMBOL_DIGITS=%d point=%s 输出位数=%d",
               _Symbol, G_SymDigits, DoubleToString(G_Point,8), G_OutDigits);
   PrintFormat("[eva008] 内容: ticks=%s M1=%s M5=%s M15=%s  写入=%s\\Files\\%s\\%s",
               (InpExportTicks?"是":"否"), (InpExportM1?"是":"否"),
               (InpExportM5?"是":"否"), (InpExportM15?"是":"否"),
               (InpUseCommonFiles?"Common":"Terminal"), InpOutRoot, _Symbol);
   if(InpExportTicks)
      Print("[eva008] 提醒: 仅当测试器模型为“Every tick based on real ticks”时，tick 才是真实tick。");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(!G_Active) return;

   // 1) tick
   if(InpExportTicks)
   {
      MqlTick tk;
      if(SymbolInfoTick(_Symbol, tk))
      {
         if(tk.time_msc >= G_LastTickMsc)   // 单调，避免极端乱序
         {
            WriteTick(_Symbol, tk);
            G_LastTickMsc = tk.time_msc;
         }
      }
   }

   // 2) bars（任何模型都能拿到真实历史 K 线，含 tick_volume）
   HandleBarStream(G_M1,  _Symbol, PERIOD_M1,  InpExportM1);
   HandleBarStream(G_M5,  _Symbol, PERIOD_M5,  InpExportM5);
   HandleBarStream(G_M15, _Symbol, PERIOD_M15, InpExportM15);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(!G_Active) return;

   // 收尾：把最后一根（shift 0）bar 也写出来
   if(InpExportM1)  WriteBar(G_M1,  _Symbol, PERIOD_M1,  0);
   if(InpExportM5)  WriteBar(G_M5,  _Symbol, PERIOD_M5,  0);
   if(InpExportM15) WriteBar(G_M15, _Symbol, PERIOD_M15, 0);

   StreamClose(G_Tick); StreamClose(G_M1); StreamClose(G_M5); StreamClose(G_M15);

   WriteMeta(_Symbol);

   PrintFormat("[eva008] 导出完成: ticks=%I64d, bars=%I64d", G_TotalTicks, G_TotalBars);
   if(G_MinTime>0)
      PrintFormat("[eva008] bar 时间范围: %s ~ %s", IsoTime(G_MinTime), IsoTime(G_MaxTime));
   if(G_TickMinTime>0)
      PrintFormat("[eva008] tick 时间范围: %s ~ %s", IsoTime(G_TickMinTime), IsoTime(G_TickMaxTime));
   PrintFormat("[eva008] 已写 meta.json。用 eva008_data_pipeline.py 读取 %s 仓库进行分析。", _Symbol);
}
//+------------------------------------------------------------------+
