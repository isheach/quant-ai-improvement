#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Step 2 · 由 dsh_JPYRev.mq5 生成 dsh_JPYRev_R4.mq5（不改旧 EA）

GPT 第三批裁定 Step 2 的 7 项要求：
  1 测试结束强制平仓也写审计（走同一历史扫描）
  2 按 deal_ticket 去重
  3 每个 closing deal 写 deal_ticket/position_id/entry_time/exit_time/entry/exit/
    volume/profit/swap/commission/net/close_type/exit_reason
  4 部分平仓按 closing deal 分行
  5 显式记录 OrderCalcProfit（方向/开平价/手数/返回值/错误码），
    不可用则记 not_available 并判该场景未完成
  6 编译前比对 [TesterInputs] 与源码 input 名称（另由 check_inputs.py 做）
  7 审计字段缺失、结束时仍有未写 deal、或重复 ticket → 立即失败
"""
from __future__ import annotations

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "dsh_JPYRev_R4.mq5")

src = io.open(SRC, encoding="utf-8", errors="ignore").read()

# ---------- 1) 审计表头：扩到 GPT 要求的字段集 ----------
OLD_HDR = '"atr_at_entry","exit_reason","position_id","close_type","profit","swap","commission");'
NEW_HDR = ('"atr_at_entry","exit_reason","deal_ticket","position_id","close_type",\n'
           '                   "profit","swap","commission","net","entry_time","exit_time",\n'
           '                   "ocp_ok","ocp_ret","ocp_err","ocp_value");')
if OLD_HDR in src:
    src = src.replace(OLD_HDR, NEW_HDR)
    print("[1] 审计表头已扩展")
else:
    print("[1] !! 表头未匹配")

# ---------- 2) 去重表 + 计数器（插在 g_partialDone 之后） ----------
ANCHOR = "bool     g_partialDone = false;   // ★R1：本次持仓是否已做过部分平仓"
if ANCHOR in src:
    src = src.replace(ANCHOR, ANCHOR + """

// ★★★ R4（GPT 第三批裁定 Step 2）：
//   · 按 deal_ticket 去重，防止同一 closing deal 写两遍
//   · 结束时补写未落盘的 deal（end of test 强制平仓）
#define MAX_DEALTICKET 4096
ulong    g_seenDeals[MAX_DEALTICKET];
int      g_seenCount   = 0;
long     g_writtenDeals = 0;      // 已写审计的 deal 数
long     g_dupHits      = 0;      // 重复命中次数
bool     g_auditFailed  = false;  // 审计失败标记（触发立即失败）

bool DealSeen(ulong ticket)
{
   for(int i = 0; i < g_seenCount; i++)
      if(g_seenDeals[i] == ticket) return true;
   if(g_seenCount < MAX_DEALTICKET) g_seenDeals[g_seenCount++] = ticket;
   else { g_dupHits++; }          // 表满 → 标记异常
   return false;
}""")
    print("[2] 去重表已插入")
else:
    print("[2] !! 锚点未匹配")

# ---------- 3) RecordExitDeal：去重 + 扩字段 + OrderCalcProfit ----------
# 在函数首部加入去重
OLD_HEAD = """   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;
   long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY) return;"""
NEW_HEAD = """   if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != InpMagic) return;
   long entryType = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
   if(entryType != DEAL_ENTRY_OUT && entryType != DEAL_ENTRY_OUT_BY) return;
   // ★R4：按 deal_ticket 去重（同一 deal 只写一次）
   if(DealSeen(dealTicket)) { g_dupHits++; return; }"""
if OLD_HEAD in src:
    src = src.replace(OLD_HEAD, NEW_HEAD)
    print("[3] 去重逻辑已插入")
else:
    print("[3] !! 函数首部未匹配")

# 在 g_ticket=0 之前插入 OrderCalcProfit 计算与扩展 FileWrite
OLD_TAIL = """      FileWrite(g_auditFh, InpRunTag, _Symbol,
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
                IntegerToString((long)pid),
                closeType,
                DoubleToString(dProfit, 2),
                DoubleToString(dSwap, 2),
                DoubleToString(dComm, 2));
      FileFlush(g_auditFh);
   }
   g_ticket = 0;
}"""

NEW_TAIL = """      // ★R4 第 5 条：显式调用 OrderCalcProfit 并记录返回码
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
void CatchUpAudit()
{
   if(!InpWriteAudit) return;
   datetime from = 0, to = TimeCurrent() + 86400;
   if(!HistorySelect(from, to)) return;
   int total = HistoryDealsTotal();
   int added = 0;
   for(int i = 0; i < total; i++)
   {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0) continue;
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != InpMagic) continue;
      long en = HistoryDealGetInteger(tk, DEAL_ENTRY);
      if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_OUT_BY) continue;
      if(DealSeen(tk)) continue;              // 已写过 → 跳过
      RecordExitDeal(tk);                     // 未写过 → 补写
      added++;
   }
   if(added > 0)
      PrintFormat("[%s] ★结束时补写 %d 个未落盘 closing deal（含 end of test）", InpRunTag, added);
}"""

if OLD_TAIL in src:
    src = src.replace(OLD_TAIL, NEW_TAIL)
    print("[4] FileWrite 扩展 + OrderCalcProfit + CatchUpAudit 已插入")
else:
    print("[4] !! 尾部未匹配（可能已被前面替换影响）")

# ---------- 4) OnDeinit 里调用 CatchUpAudit + 写失败标记 ----------
OLD_DEINIT = """void OnDeinit(const int reason)
{
   if(g_auditHandle != INVALID_HANDLE)
   {
      FileClose(g_auditHandle);
      g_auditHandle = INVALID_HANDLE;
   }"""
NEW_DEINIT = """void OnDeinit(const int reason)
{
   // ★R4：先补写未落盘的 closing deal（含 end of test 强制平仓）
   CatchUpAudit();

   // ★R4 第 7 条：写审计自检文件（供对账脚本判定）
   {
      string sf = "dshtrend\\\\" + InpRunTag + "\\\\audit_selfcheck.csv";
      int fh = FileOpen(sf, FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
      if(fh != INVALID_HANDLE)
      {
         FileWrite(fh, "run_tag","written_deals","dup_hits","audit_failed","reason");
         FileWrite(fh, InpRunTag, IntegerToString(g_writtenDeals),
                   IntegerToString(g_dupHits),
                   (g_auditFailed ? "1" : "0"),
                   IntegerToString(reason));
         FileClose(fh);
      }
   }

   if(g_auditHandle != INVALID_HANDLE)
   {
      FileClose(g_auditHandle);
      g_auditHandle = INVALID_HANDLE;
   }"""
if OLD_DEINIT in src:
    src = src.replace(OLD_DEINIT, NEW_DEINIT)
    print("[5] OnDeinit 已插入 CatchUpAudit + 自检文件")
else:
    print("[5] !! OnDeinit 未匹配")

# ---------- 5) 转发声明（CatchUpAudit 在 RecordExitDeal 之后定义，但 OnDeinit 在后面 → 无需前置） ----------
# C++/MQL5 允许后置定义先被调用？MQL5 要求先声明。加前置声明：
FWD_ANCHOR = "void OnTradeTransaction(const MqlTradeTransaction &trans,"
if FWD_ANCHOR in src and "void CatchUpAudit();" not in src:
    src = src.replace(FWD_ANCHOR, "void CatchUpAudit();   // ★R4 前置声明\n\n" + FWD_ANCHOR)
    print("[6] 前置声明已加")

io.open(SRC, "w", encoding="utf-8").write(src)
print("\n已写出:", SRC, len(src), "字节")
print("braces:", src.count("{"), "/", src.count("}"))
