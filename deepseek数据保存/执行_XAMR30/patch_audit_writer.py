import io
import re

P = r"D:\desktop\新量化策略\deepseek数据保存\mql5\dshtools\dsh_XAMR30.mq5"
c = io.open(P, encoding="utf-8").read()

# ---- 在表头之后加入列数常量 ----
anchor = '"close_type,exit_reason,server_utc_offset";'
add = anchor + """

// ★N1R 修复 3：审计列数常量（用于"写入前断言"，使列漂移成为不可能）
#define AUDIT_COLS 38
#define REJECT_COLS 16
"""
if "AUDIT_COLS" not in c:
    c = c.replace(anchor, add, 1)

# ---- 用数组式写入替换单条超长 FileWrite ----
start = c.index("   g_lastWriteBytes = FileWrite(g_auditFh, InpRunTag, _Symbol,")
end = c.index("   FileFlush(g_auditFh);", start)
old_block = c[start:end]

new_block = '''   // ★N1R：数组式写入 + 列数断言（防止参数与表头错位）
   string f[];
   ArrayResize(f, 0);
   #define ADD(x) { int _n = ArraySize(f); ArrayResize(f, _n + 1); f[_n] = (x); }
   ADD(InpRunTag);
   ADD(_Symbol);
   ADD(IntegerToString((long)dk));
   ADD(IntegerToString((long)pid));
   ADD(TimeToString(g_sigBarTime, TIME_DATE|TIME_SECONDS));                          // 4 signal_bar_open_time
   ADD(TimeToString(g_signalCloseTime, TIME_DATE|TIME_SECONDS));                     // 5 signal_bar_close_time
   ADD(TimeToString((g_entryBarOpenTime > 0) ? g_entryBarOpenTime : entryT, TIME_DATE|TIME_SECONDS)); // 6 entry_bar_open_time
   ADD(TimeToString((g_entryTime > 0) ? g_entryTime : entryT, TIME_DATE|TIME_SECONDS));               // 7 entry_time
   ADD(TimeToString(tS, TIME_DATE|TIME_SECONDS));                                    // 8 exit_time
   ADD(DoubleToString(g_sigZ, 5));                                                   // 9 z_score
   ADD(DoubleToString(g_sigEma, _Digits));                                           // 10 ema48
   ADD(DoubleToString(g_sigRes, _Digits));                                           // 11 residual
   ADD(DoubleToString(g_sigSigma, _Digits));                                         // 12 sigma48
   ADD(DoubleToString(g_sigAtr, _Digits));                                           // 13 atr14
   ADD(DoubleToString(g_sigP20, _Digits));                                           // 14 atr_p20
   ADD(DoubleToString(g_sigP80, _Digits));                                           // 15 atr_p80
   ADD((g_sigXauT > 0) ? TimeToString(g_sigXauT, TIME_DATE|TIME_MINUTES) : "");      // 16 xau_bar_time
   ADD(DoubleToString(g_sigXauO, _Digits));                                          // 17 xau_open
   ADD(DoubleToString(g_sigXauC, _Digits));                                          // 18 xau_close
   ADD(DoubleToString(g_sigXauR, 6));                                                // 19 xau_return
   ADD(InpCrossAssetFilter ? "1" : "0");                                             // 20 cross_asset_filter_enabled
   ADD(IntegerToString(g_sigXauPass));                                               // 21 cross_asset_filter_pass
   ADD(IntegerToString(g_sigAlignExact));                                            // 22 alignment_exact
   ADD((dir > 0) ? "long" : "short");                                                // 23 trade_direction
   ADD(DoubleToString(g_spreadPtsAtEntry, 1));                                       // 24 spread_at_entry_points
   ADD(DoubleToString(g_slPts, 1));                                                  // 25 initial_sl_distance_points
   ADD(DoubleToString(g_tpPts, 1));                                                  // 26 initial_tp_distance_points
   ADD((g_slPts > 0) ? DoubleToString(g_spreadPtsAtEntry / g_slPts, 5) : "");         // 27 spread_over_sl
   ADD((g_tpPts > 0) ? DoubleToString(g_spreadPtsAtEntry / g_tpPts, 5) : "");         // 28 spread_over_tp
   ADD(DoubleToString(g_riskBudget, 2));                                             // 29 risk_budget
   ADD(DoubleToString(g_actualRisk, 2));                                             // 30 actual_initial_sl_risk
   ADD(DoubleToString(ocpV, 4));                                                     // 31 ocp_expected_pl
   ADD(DoubleToString(dp, 4));                                                       // 32 deal_profit
   ADD(DoubleToString(fV, 4));                                                       // 33 formula_value
   ADD(DoubleToString(fDiff, 4));                                                    // 34 formula_diff
   ADD(closeType);                                                                   // 35 close_type
   ADD(reason);                                                                      // 36 exit_reason
   ADD("0");                                                                         // 37 server_utc_offset
   #undef ADD

   if(ArraySize(f) != AUDIT_COLS)
   {
      g_auditFailed = true;
      PrintFormat("[%s] ★★AUDIT SCHEMA FAIL: 写入列数 %d != 表头 %d → 拒绝写入",
                  InpRunTag, ArraySize(f), AUDIT_COLS);
      SetFatal("审计列数与表头不一致");
      return;
   }
   g_lastWriteBytes = FileWrite(g_auditFh, f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8],
             f[9], f[10], f[11], f[12], f[13], f[14], f[15], f[16], f[17], f[18],
             f[19], f[20], f[21], f[22], f[23], f[24], f[25], f[26], f[27], f[28],
             f[29], f[30], f[31], f[32], f[33], f[34], f[35], f[36], f[37]);
'''

c = c[:start] + new_block + c[end:]
io.open(P, "w", encoding="utf-8").write(c)
print("patched; braces:", c.count("{"), "/", c.count("}"))
