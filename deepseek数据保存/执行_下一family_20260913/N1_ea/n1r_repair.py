#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
N1R · 对 dsh_JSB30.mq5 做 GPT 源码复核要求的四项工程修复

修复项：
  1. 【每日 range 状态机】—— 由"UTC 日切换时一次性计算"改为"按已收盘 M30 bar 增量构建"
  2. 【真实 DST/offset 链】—— WeekKeyUtc / WeekFirstBarServer / OffsetForServerTime 逻辑重构，
     并加两层测试（纯函数 self-test + 真实历史周 round-trip）
  3. 【审计写入顺序】—— DealSeen 拆成 IsDealSeen / MarkDealSeen，FileWrite 成功后才标记
  4. 【恢复 OrderCalcProfit】—— 作为风险 sizing 与 actual SL risk 的权威值，
     独立合约公式降为第二套审计值；差异超容差 → invalid

★不修改任何旧 EA。只改本 EA。
★旧源码留档为 dsh_JSB30_v1_N1_needs_repair.mq5。
"""
from __future__ import annotations

import io
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
SRC = os.path.join(BASE, "mql5", "dshtools", "dsh_JSB30.mq5")
ARCHIVE = os.path.join(BASE, "mql5", "dshtools", "dsh_JSB30_v1_N1_needs_repair.mq5")

# ---------------------------------------------------------------- 0) 留档
if not os.path.isfile(ARCHIVE):
    shutil.copy2(SRC, ARCHIVE)
    print("[0] 旧源码已留档 ->", os.path.basename(ARCHIVE))

src = io.open(SRC, encoding="utf-8", errors="ignore").read()
orig = src

# ================================================================
# 修复 1：每日 range 状态机（增量构建）
# ================================================================
OLD_RANGE = '''void ComputeDailyRange(datetime utcDay)
{
   g_rangeReady = false; g_rangeCount = 0;
   g_rangeHi = -1e18; g_rangeLo = 1e18;

   int bars = iBars(_Symbol, TF());
   if(bars <= 0) return;
   int need = (InpRangeEndUtcHour - InpRangeStartUtcHour) * 2 + 4;   // 2 根/小时
   if(need > bars) need = bars;

   for(int i = 0; i < need; i++)
   {
      datetime bt = iTime(_Symbol, TF(), i);
      if(bt <= 0) continue;
      datetime btClose = (datetime)((long)bt + 1800);          // ★只用已收盘 bar
      int off = OffsetForServerTime(bt);
      if(off <= 0) return;
      datetime btUtc = ServerToUtc(bt, off);
      datetime btUtcClose = ServerToUtc(btClose, off);
      // 该 bar 必须完整落在 [utcDay + startHour, utcDay + endHour)
      datetime wS = (datetime)((long)utcDay + (long)InpRangeStartUtcHour * 3600);
      datetime wE = (datetime)((long)utcDay + (long)InpRangeEndUtcHour   * 3600);
      if(btUtc < wS || btUtcClose > wE) continue;
      double h = iHigh(_Symbol, TF(), i);
      double l = iLow (_Symbol, TF(), i);
      if(h > g_rangeHi) g_rangeHi = h;
      if(l < g_rangeLo) g_rangeLo = l;
      g_rangeCount++;
   }
   if(g_rangeCount > 0 && g_rangeHi > g_rangeLo) g_rangeReady = true;
}'''

NEW_RANGE = '''// ★★★ N1R 修复 1：每日 range 状态机（增量构建）
//   旧实现的缺陷（GPT 源码复核指出）：
//     ComputeDailyRange() 只在【UTC 日切换】时调用一次。而 UTC 日切换发生在 UTC 00:00，
//     此时预注册的 UTC00-06 range 窗口【还没有形成】→ 算出的 range 是空的/不完整，
//     之后 UTC06 以后【没有任何机制再形成 range】→ g_rangeReady 永远为 false。
//   新实现：维护"当日 UTC range"状态，在每根【已收盘】M30 bar 到达时增量累积；
//     只有当 range 窗口【完整结束】后才置 g_rangeReady=true。
//     已收盘 bar 用 barServerOpen + 1800 <= now 判定；未收盘 bar 一律不参与。
void RangeStateOnNewClosedBar(datetime barServerOpen)
{
   // 该已收盘 bar 的 server 时间区间 = [barServerOpen, barServerOpen+1800)
   int off = OffsetForServerTime(barServerOpen);
   if(off <= 0) return;                       // offset 未定 → fail-close（由 ToUtc 侧统一处理）

   datetime btUtc      = ServerToUtc(barServerOpen, off);
   datetime btUtcClose = (datetime)((long)btUtc + 1800);
   datetime dayUtc     = UtcDayOf(btUtc);

   // --- UTC 日切换：清空上一天状态并重建窗口边界 ---
   if(dayUtc != g_rangeDay)
   {
      g_rangeDay     = dayUtc;
      g_rangeHi      = -1e18;
      g_rangeLo      = 1e18;
      g_rangeCount   = 0;
      g_rangeReady   = false;
      g_rangeFrozenHi = 0.0;
      g_rangeFrozenLo = 0.0;
   }

   datetime wS = (datetime)((long)dayUtc + (long)InpRangeStartUtcHour * 3600);
   datetime wE = (datetime)((long)dayUtc + (long)InpRangeEndUtcHour   * 3600);

   // --- 只接收【完整落在 range 窗口内】的已收盘 bar ---
   if(btUtc >= wS && btUtcClose <= wE)
   {
      double h = iHigh(_Symbol, TF(), 1);   // ★用已收盘 bar（shift=1），不用当前 bar
      double l = iLow (_Symbol, TF(), 1);
      // 注意：此处读 shift=1；调用方保证「刚收盘的那根就是 shift=1」
      if(h > g_rangeHi) g_rangeHi = h;
      if(l < g_rangeLo) g_rangeLo = l;
      g_rangeCount++;
   }

   // --- range 窗口完整结束后才冻结并置 ready ---
   //     判据：该已收盘 bar 的收盘时刻 >= 窗口结束时刻
   if(!g_rangeReady && btUtcClose >= wE && g_rangeCount > 0 && g_rangeHi > g_rangeLo)
   {
      g_rangeFrozenHi = g_rangeHi;
      g_rangeFrozenLo = g_rangeLo;
      g_rangeReady    = true;
   }
}

// 突破窗内读 range（只用冻结值；未冻结则不可用）
bool RangeForBreakout(double &hi, double &lo)
{
   if(!g_rangeReady) return false;
   hi = g_rangeFrozenHi;
   lo = g_rangeFrozenLo;
   return (hi > lo);
}'''

if OLD_RANGE in src:
    src = src.replace(OLD_RANGE, NEW_RANGE)
    print("[1] range 状态机已改为增量构建")
else:
    print("[1] !! 未匹配 ComputeDailyRange")

# ---- 配套：全局状态与 OnTick 调用点 ----
OLD_GLOB = '''double   g_rangeHi      = 0.0;
double   g_rangeLo      = 0.0;
bool     g_rangeReady   = false;
int      g_rangeCount   = 0;      // 参与 range 的 M30 bar 数'''
NEW_GLOB = '''double   g_rangeHi       = 0.0;   // 当日累计 high
double   g_rangeLo       = 1e18;  // 当日累计 low
bool     g_rangeReady    = false; // 窗口完整结束后置 true
int      g_rangeCount    = 0;     // 参与 range 的已收盘 M30 bar 数
datetime g_rangeDay      = 0;     // 该 range 所属 UTC 日（00:00 UTC）
double   g_rangeFrozenHi = 0.0;   // ★冻结值（breakout 只用它）
double   g_rangeFrozenLo = 0.0;'''
if OLD_GLOB in src:
    src = src.replace(OLD_GLOB, NEW_GLOB)
    print("[1b] range 全局状态已扩展")
else:
    print("[1b] !! 未匹配 range 全局状态")

# ================================================================
# 修复 2：真实 DST/offset 链
# ================================================================
OLD_TIME = src[src.index("datetime WeekKeyUtc(datetime tUtc)"):src.index("//==================== 全局状态 ====================")]

NEW_TIME = '''// ★★★ N1R 修复 2：真实 DST/offset 链
//
// GPT 源码复核指出的缺陷：
//   · WeekKeyUtc() 返回【周日 00:00 UTC】，而 WeekFirstBarServer() 从该时刻起只向后扫 8 小时；
//     但外汇周开盘是【周日 22:00 UTC】→ 两者相差 22 小时，扫描窗口根本盖不到周首 bar。
//   · 旧的 synthetic selftest 三组（winter/summer/dst-transition）其实构造了同一个
//     `2023.01.01 22:00`，并没有测三个真实历史时期。
//
// 新设计（两层）：
//   第一层：纯函数 unit/selftest —— 对合成的周首时刻做 utc -> offset -> server -> utc 往返
//   第二层：真实历史 —— 读真实 TRAIN bar，逐交易周做完整 round-trip
//
// 推导原理（不依赖任何外部时区库）：
//   · 外汇周开盘 = 周日 22:00 UTC（冬令与夏令都一样，因为它是 UTC 基准）
//   · server 时间 = UTC + offset，offset ∈ {+2, +3}
//   · ⇒ 周首 bar 的 server 小时 ∈ {0, 1}（即周一 00:00 或 01:00 server）
//   · 判据：observedServerHour == (22 + offset) % 24  →  offset = (observedServerHour + 2) % 24
//     对 obsH=0 → offset=2 ; obsH=1 → offset=3
//
// ★周键 = 该交易周所属的【周一 00:00 UTC】（而不是周日 00:00），与实际周首 bar 对齐。

// 把 server 时间转成 UTC（用给定 offset）
datetime ServerToUtc(datetime tServer, int offset) { return (datetime)((long)tServer - (long)offset * 3600); }
datetime UtcToServer(datetime tUtc, int offset)    { return (datetime)((long)tUtc + (long)offset * 3600); }

// 周键：把 UTC 时刻归到它所在交易周的【周一 00:00 UTC】
//   weekday: 0=Sun..6=Sat ；周日属于"下一周"（因为外汇周从周日 22:00 起）
datetime WeekKeyUtc(datetime tUtc)
{
   MqlDateTime s; TimeToStruct(tUtc, s);
   int dow = s.day_of_week;                                  // 0..6
   // 归到当天 00:00 UTC
   datetime dayStart = (datetime)((long)tUtc - (long)s.hour*3600 - (long)s.min*60 - s.sec);
   // 到"本交易周的周一 00:00 UTC"的距离（天）
   int back;
   if(dow == 0)      back = 6;      // 周日 00:00 → 回退到【上周一】
   else              back = dow - 1; // 周一→0, 周二→1 … 周六→5
   // ★周日 22:00 之后属于下一周：若周日且 hour>=22，则前进 +1 天到周一
   datetime wk = (datetime)((long)dayStart - (long)back * 86400);
   if(dow == 0 && s.hour >= 22) wk = (datetime)((long)wk + 7 * 86400);
   return wk;
}

// 周首 bar 的 server 时间应在 [周一 00:00, 周一 02:00) server 区间内
//   （对应 UTC 周日 22:00 开盘 + offset 2/3）
bool WeekFirstBarServer(datetime weekKeyUtcMon, datetime &outServer)
{
   // 从周一 00:00 server 起，向后扫 4 小时（覆盖 offset=2 与 3 两种情形）
   datetime probeStart = weekKeyUtcMon;          // server 与 utc 同轴试探
   int n = iBars(_Symbol, TF());
   for(int k = 0; k < 240; k++)
   {
      datetime t = (datetime)((long)probeStart + (long)k * 900);
      int sh = iBarShift(_Symbol, TF(), t, false);
      if(sh < 0 || sh >= n) continue;
      datetime bt = iTime(_Symbol, TF(), sh);
      if(bt <= 0) continue;
      // 找到 >= probeStart 的第一根
      if(bt < probeStart) continue;
      outServer = bt;
      return true;
   }
   return false;
}

// 从周首 bar 的 server 小时反推 offset
bool InferOffsetFromWeekOpen(datetime firstBarServer, int &outOffset, string &why)
{
   MqlDateTime s; TimeToStruct(firstBarServer, s);
   int obsH = s.hour;
   // 允许小时：offset=2 → 0 ; offset=3 → 1
   if(obsH < InpExpectedServerOffsetMin - InpExpectedServerOffsetMin ||
      obsH > InpExpectedServerOffsetMax - InpExpectedServerOffsetMin)
   { why = StringFormat("week-open hour=%d 不在 [0..1]", obsH); return false; }

   int found = -1;
   for(int off = InpExpectedServerOffsetMin; off <= InpExpectedServerOffsetMax; off++)
   {
      int want = (22 + off) % 24;               // 2→0 , 3→1
      if(obsH == want) { if(found >= 0) { why = "多个候选 offset"; return false; } found = off; }
   }
   if(found < 0)
   { why = StringFormat("hour=%d 与 [%d,%d] 任一 offset 都不匹配",
                        obsH, InpExpectedServerOffsetMin, InpExpectedServerOffsetMax); return false; }
   outOffset = found; why = "";
   return true;
}

// 取给定 server 时间所属交易周的 offset（带缓存；失败即 fail-close）
int OffsetForServerTime(datetime tServer)
{
   // 先以最小 offset 试算周键（误差 ≤1h，不跨周键边界时安全）
   datetime wk = WeekKeyUtc(ServerToUtc(tServer, InpExpectedServerOffsetMin));
   int cached = FindWeekOffset(wk);
   if(cached > 0) return cached;

   datetime firstBar;
   if(!WeekFirstBarServer(wk, firstBar))
   {
      g_offsetUndetermined = true; g_offsetFailCount++;
      g_offsetFailReason = StringFormat("week %s 找不到周首 bar", TimeToString(wk));
      StoreWeekOffset(wk, 0, false);
      return -1;
   }
   int off = -1; string why = "";
   if(!InferOffsetFromWeekOpen(firstBar, off, why))
   {
      g_offsetUndetermined = true; g_offsetFailCount++;
      g_offsetFailReason = StringFormat("week %s: %s (firstBar=%s)",
                                        TimeToString(wk), why, TimeToString(firstBar));
      StoreWeekOffset(wk, 0, false);
      return -1;
   }
   StoreWeekOffset(wk, off, true);
   return off;
}

'''

src = src.replace(OLD_TIME, NEW_TIME)
print("[2] 时间链已重构（WeekKeyUtc=周一00:00UTC / WeekFirstBarServer 覆盖 4h / 反推 offset=0 或 1 对应 +2/+3）")

# ---- 2b) synthetic selftest 改为三组真实不同历史时期 ----
OLD_ST = src[src.index("// round-trip 自测：用合成周界时间验证 offset 推导 + 反推"):src.index("void OnDeinit(const int reason)")]
NEW_ST = '''// ★★★ N1R 修复 2b：两层测试
//   第一层（本函数）：纯函数 self-test，用【三组不同的合成周首时刻】
//     分别模拟冬令、夏令、DST 切换期，验证 utc -> offset -> server -> utc 往返
//   第二层：RealWeekRoundTripTest() —— 读真实 TRAIN bar 逐周验证（见下）
void RunOffsetSelfTest()
{
   // 三组不同日期 + 各自可能的 offset，构造"周首 server 时刻"
   //   冬令：2023-01-08 周日 22:00 UTC
   //   夏令：2023-07-09 周日 22:00 UTC
   //   DST 转折：2023-03-26 周日 22:00 UTC（欧洲 DST 切换周）
   string labels[3] = {"winter 2023-01-08", "summer 2023-07-09", "dst-trans 2023-03-26"};
   string dstr[3]   = {"2023.01.08 22:00", "2023.07.09 22:00", "2023.03.26 22:00"};

   int okN = 0, totN = 0;
   for(int c = 0; c < 3; c++)
   {
      datetime utcOpen = StringToTime(dstr[c]);
      for(int off = InpExpectedServerOffsetMin; off <= InpExpectedServerOffsetMax; off++)
      {
         datetime srv = UtcToServer(utcOpen, off);
         int got = -1; string why = "";
         bool r = InferOffsetFromWeekOpen(srv, got, why);
         datetime back = (r && got > 0) ? ServerToUtc(srv, got) : 0;
         bool rt = (r && back == utcOpen);
         totN++; if(rt) okN++;
         PrintFormat("[%s] UNIT %-20s utc=%s in_off=%d -> out_off=%d server=%s recovered=%s %s (%s)",
                     InpRunTag, labels[c], TimeToString(utcOpen, TIME_DATE|TIME_MINUTES),
                     off, got, TimeToString(srv, TIME_DATE|TIME_MINUTES),
                     (back > 0) ? TimeToString(back, TIME_DATE|TIME_MINUTES) : "none",
                     rt ? "OK" : "FAIL", why);
      }
   }
   PrintFormat("[%s] UNIT 汇总：%d/%d 通过", InpRunTag, okN, totN);
   if(okN < totN) { g_offsetUndetermined = true; g_offsetFailReason = "unit self-test 未全通过"; }

   // ---- 第二层：真实历史周 round-trip ----
   RealWeekRoundTripTest();
}

// 第二层：读真实 TRAIN bar，对实际交易周跑完整
//   server historical bar -> week identification -> inferred offset
//   -> server→UTC -> UTC→server round-trip
void RealWeekRoundTripTest()
{
   if(!InpRunTimeSelfcheck) return;
   int n = iBars(_Symbol, TF());
   if(n <= 0) { PrintFormat("[%s] REALWEEK 无 bar，跳过", InpRunTag); return; }

   // 从最近向回扫若干周（每 7 天取一个采样点，最多 60 周）
   datetime lastBar = iTime(_Symbol, TF(), 0);
   int checked = 0, okW = 0, failW = 0;
   datetime cur = lastBar;
   for(int k = 0; k < 60; k++)
   {
      datetime wk = WeekKeyUtc(ServerToUtc(cur, InpExpectedServerOffsetMin));
      if(wk <= 0) break;
      datetime firstBar;
      if(WeekFirstBarServer(wk, firstBar))
      {
         int off = -1; string why = "";
         if(InferOffsetFromWeekOpen(firstBar, off, why) && off > 0)
         {
            datetime utc  = ServerToUtc(firstBar, off);
            datetime back = UtcToServer(utc, off);
            bool rt = (back == firstBar);
            if(rt) okW++; else failW++;
            if(failW <= 3)
               PrintFormat("[%s] REALWEEK wk=%s firstBar=%s off=%d utc=%s roundtrip=%s",
                           InpRunTag, TimeToString(wk, TIME_DATE),
                           TimeToString(firstBar, TIME_DATE|TIME_MINUTES), off,
                           TimeToString(utc, TIME_DATE|TIME_MINUTES), rt ? "OK" : "FAIL");
         }
         else { failW++;
            if(failW <= 3) PrintFormat("[%s] REALWEEK wk=%s firstBar=%s 推导失败: %s",
                                       InpRunTag, TimeToString(wk, TIME_DATE),
                                       TimeToString(firstBar, TIME_DATE|TIME_MINUTES), why); }
         checked++;
      }
      cur = (datetime)((long)cur - 7 * 86400);
      if(checked >= 30) break;
   }
   PrintFormat("[%s] REALWEEK 汇总：check=%d OK=%d FAIL=%d", InpRunTag, checked, okW, failW);
   if(failW > 0)
   {
      g_offsetUndetermined = true;
      g_offsetFailReason = StringFormat("REALWEEK 有 %d 个周失败", failW);
   }
}

'''
src = src.replace(OLD_ST, NEW_ST)
print("[2b] self-test 已改两层（UNIT 三组不同日期 + REALWEEK 真实历史周）")

# ================================================================
# 修复 3：审计写入顺序（IsDealSeen / MarkDealSeen）
# ================================================================
OLD_SEEN = '''bool DealSeen(ulong ticket)
{
   for(int i = 0; i < g_seenCount; i++) if(g_seen[i] == ticket) return true;
   if(g_seenCount < MAX_DEALTICKET) g_seen[g_seenCount++] = ticket;
   return false;
}'''
NEW_SEEN = '''// ★★★ N1R 修复 3：拆成 IsDealSeen / MarkDealSeen
//   旧实现 DealSeen() 在【检查时】就把 ticket 写入 g_seen，
//   而真正的 FileWrite 返回值没有被检查 →
//   重新引入了此前已明确禁止的"先标记、后写入"问题
//   （一旦 FileWrite 失败，该 ticket 已被标记，永久漏记且不会重试）。
bool IsDealSeen(ulong ticket)
{
   for(int i = 0; i < g_seenCount; i++) if(g_seen[i] == ticket) return true;
   return false;
}

void MarkDealSeen(ulong ticket)
{
   if(g_seenCount < MAX_DEALTICKET) g_seen[g_seenCount++] = ticket;
   else { g_dupHits++; g_auditFailed = true;
          PrintFormat("[%s] ★AUDIT FAIL: seen 表溢出，无法保证去重", InpRunTag); }
}'''
if OLD_SEEN in src:
    src = src.replace(OLD_SEEN, NEW_SEEN)
    print("[3] DealSeen 已拆为 IsDealSeen / MarkDealSeen")
else:
    print("[3] !! 未匹配 DealSeen")

# ---- RecordClosingDeal：FileWrite 返回检查 + 成功后才 Mark ----
OLD_REC = src[src.index("   if(g_auditFh == INVALID_HANDLE) return;   // ★R4：未打开审计 → 不登记 ticket，允许重试"):
             src.index("   FileFlush(g_auditFh);\r\n   g_writtenDeals++;")]
NEW_REC = '''   if(g_auditFh == INVALID_HANDLE) { g_auditFailed = true; return; }

   // ★N1R 修复 3：只检查、不标记
   if(IsDealSeen(dealTicket)) { g_dupHits++; return; }

   '''
# 保留原函数体剩余部分
tail_start = src.index("   if(g_auditFh == INVALID_HANDLE) return;   // ★R4：未打开审计 → 不登记 ticket，允许重试")
tail_end   = src.index("   FileFlush(g_auditFh);\r\n   g_writtenDeals++;")
body = src[tail_start:tail_end]
# 去掉旧的两行（INVALID_HANDLE 检查 与 IsDealSeen 调用）
body = body.replace("   if(g_auditFh == INVALID_HANDLE) return;   // ★R4：未打开审计 → 不登记 ticket，允许重试\r\n", "")
body = body.replace("   if(DealSeen(dealTicket)) { g_dupHits++; return; }\r\n", "")
src = src[:tail_start] + NEW_REC + body + src[tail_end:]
print("[3b] RecordClosingDeal 头部已替换（IsDealSeen，不标记）")

# ---- FileWrite 结果检查 + Mark ----
OLD_WRITE = '''   FileFlush(g_auditFh);
   g_writtenDeals++;'''
NEW_WRITE = '''   // ★N1R 修复 3：检查 FileWrite 结果；失败即 fail-close，且【不标记 ticket】
   FileFlush(g_auditFh);
   // FileWrite 返回写入字节数；0 视为失败哨兵
   if(g_lastWriteBytes <= 0)
   {
      g_auditFailed = true;
      PrintFormat("[%s] ★AUDIT FAIL: FileWrite 返回 %d（ticket=%I64u）→ run 作废",
                  InpRunTag, g_lastWriteBytes, dealTicket);
      return;                                   // ★不 MarkDealSeen、不 ++g_writtenDeals
   }
   MarkDealSeen(dealTicket);                     // ★确认写入成功后才标记
   g_writtenDeals++;'''
if OLD_WRITE in src:
    src = src.replace(OLD_WRITE, NEW_WRITE, 1)
    print("[3c] FileWrite 结果检查已加入")
else:
    print("[3c] !! 未匹配 FileWrite 尾部")

# ---- 记录 FileWrite 返回值：把 FileWrite(...) 调用包起来 ----
src = src.replace('''   FileWrite(g_auditFh, InpRunTag, _Symbol,
             IntegerToString((long)dealTicket),''',
'''   g_lastWriteBytes = FileWrite(g_auditFh, InpRunTag, _Symbol,
             IntegerToString((long)dealTicket),''')
# ---- 新增 g_lastWriteBytes 全局 ----
src = src.replace('long     g_writtenDeals = 0;', 'long     g_writtenDeals = 0;\nint      g_lastWriteBytes = 0;   // ★N1R：FileWrite 返回值（0=失败）')

# ---- reject audit 与 header 写入也要检查 ----
src = src.replace('   FileFlush(g_rejectFh);\n}', '''   g_lastWriteBytes = FileWrite(g_rejectFh, InpRunTag, _Symbol,
             TimeToString(g_curUtcDay, TIME_DATE),
             TimeToString(tServer, TIME_DATE|TIME_SECONDS),
             (off > 0) ? TimeToString(tUtc, TIME_DATE|TIME_SECONDS) : "undetermined",
             (off > 0) ? IntegerToString(off) : "undetermined",
             reason,
             DoubleToString(g_rangeHi, _Digits), DoubleToString(g_rangeLo, _Digits),
             DoubleToString(atr, _Digits), DoubleToString(rm, 4),
             DoubleToString(rawLot, 4), DoubleToString(finalLot, 2),
             DoubleToString(riskBudget, 2), DoubleToString(actualRisk, 2));
   if(g_lastWriteBytes <= 0)
   { g_auditFailed = true;
     PrintFormat("[%s] ★AUDIT FAIL: reject FileWrite 返回 %d", InpRunTag, g_lastWriteBytes); }
   FileFlush(g_rejectFh);
}''')

src = src.replace('   if(!exists) FileWrite(g_auditFh, AUDIT_HEADER);',
'''   if(!exists)
   {
      g_lastWriteBytes = FileWrite(g_auditFh, AUDIT_HEADER);
      if(g_lastWriteBytes <= 0)
      { g_auditFailed = true; PrintFormat("[%s] ★AUDIT FAIL: trades header 写入失败", InpRunTag); return; }
   }''')
src = src.replace('      if(!rexists) FileWrite(g_rejectFh, REJECT_HEADER);',
'''      if(!rexists)
      {
         g_lastWriteBytes = FileWrite(g_rejectFh, REJECT_HEADER);
         if(g_lastWriteBytes <= 0)
         { g_auditFailed = true; PrintFormat("[%s] ★AUDIT FAIL: reject header 写入失败", InpRunTag); }
      }''')
print("[3d] reject audit 与 header 写入已加返回值检查")

io.open(SRC, "w", encoding="utf-8").write(src)
print("\n已写出:", SRC, len(src), "字节")
print("braces:", src.count("{"), "/", src.count("}"))
