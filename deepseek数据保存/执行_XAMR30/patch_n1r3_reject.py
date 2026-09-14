import io
import re

P = r"D:\desktop\新量化策略\deepseek数据保存\mql5\dshtools\dsh_XAMR30.mq5"
c = io.open(P, encoding="utf-8").read()

# ============================================================
# §三 修复：reject audit 的状态污染
# ============================================================
start = c.index("void WriteReject(datetime tSrv, string reason,")
end = c.index("void OpenAudit()")

new_wr = '''// ★★★ N1R3 修复 2：reject audit 不再依赖历史全局状态
//   GPT 复核指出：WriteReject() 直接读 g_pend* 全局，而 EvaluateSignalBar()
//   每根 bar 开头并不把这些 snapshot 全部清零，导致：
//     · atr_out_of_regime 行带着【上一根 bar】的 XAU timestamp / return
//     · cross_asset_missing_bar 行写入了 iBarShift(exact=false) 返回的
//       【最近的旧 XAU bar】timestamp，把"不存在"写成了"存在"
//   → 污染后续失败机制统计。
//   修复：显式传入本次 candidate 的 local snapshot；未计算字段一律留空。
//   另加 nearest_xau_bar_time 作为【诊断字段】，与 exact 严格区分。
#define REJECT_COLS 18
#define RADD(x) { int _n = ArraySize(rf); ArrayResize(rf, _n + 1); rf[_n] = (x); }

void WriteReject(datetime tSrv, string reason,
                 double rawLot, double finalLot, double riskBudget, double actualRisk, int ocpErr,
                 double zScore, bool zValid,
                 double atr14, bool atrValid,
                 double p20, double p80, bool pctValid,
                 datetime exactXauT, datetime nearestXauT, double xauRet, bool xauValid)
{
   if(!InpWriteRejectAudit || g_rejectFh == INVALID_HANDLE) return;

   string rf[];
   ArrayResize(rf, 0);
   RADD(InpRunTag);                                                              // 0
   RADD(_Symbol);                                                                // 1
   RADD(TimeToString(g_curUtcDay, TIME_DATE));                                    // 2 utc_day
   RADD(TimeToString(tSrv, TIME_DATE|TIME_SECONDS));                              // 3 signal_bar_time
   RADD(reason);                                                                  // 4 reason
   RADD(zValid    ? DoubleToString(zScore, 5) : "");                              // 5 z_score
   RADD(atrValid  ? DoubleToString(atr14, _Digits) : "");                         // 6 atr14
   RADD(pctValid  ? DoubleToString(p20, _Digits) : "");                           // 7 atr_p20
   RADD(pctValid  ? DoubleToString(p80, _Digits) : "");                           // 8 atr_p80
   // ★exact XAU：只有真实精确匹配才写；否则留空（绝不写 nearest）
   RADD((xauValid && exactXauT > 0) ? TimeToString(exactXauT, TIME_DATE|TIME_MINUTES) : "");  // 9 xau_bar_time
   RADD(xauValid ? DoubleToString(xauRet, 6) : "");                               // 10 xau_return
   // ★诊断字段：nearest bar（仅用于调试，不得与 exact 混淆）
   RADD((nearestXauT > 0) ? TimeToString(nearestXauT, TIME_DATE|TIME_MINUTES) : "");          // 11 nearest_xau_bar_time
   RADD(DoubleToString(rawLot, 4));                                               // 12 raw_lot
   RADD(DoubleToString(finalLot, 2));                                             // 13 final_lot
   RADD(DoubleToString(riskBudget, 2));                                           // 14 risk_budget
   RADD(DoubleToString(actualRisk, 2));                                           // 15 actual_risk
   RADD(IntegerToString(ocpErr));                                                 // 16 ocp_err
   RADD("0");                                                                     // 17 server_utc_offset
   #undef RADD

   if(ArraySize(rf) != REJECT_COLS)
   {
      g_auditFailed = true;
      PrintFormat("[%s] ★★REJECT SCHEMA FAIL: 列数 %d != %d → 拒绝写入",
                  InpRunTag, ArraySize(rf), REJECT_COLS);
      SetFatal("reject 审计列数与表头不一致");
      return;
   }
   g_lastWriteBytes = FileWrite(g_rejectFh, rf[0], rf[1], rf[2], rf[3], rf[4], rf[5], rf[6],
             rf[7], rf[8], rf[9], rf[10], rf[11], rf[12], rf[13], rf[14], rf[15], rf[16], rf[17]);
   if(g_lastWriteBytes <= 0)
   { g_auditFailed = true; PrintFormat("[%s] ★AUDIT FAIL: reject FileWrite=%u", InpRunTag, g_lastWriteBytes); SetFatal("reject 写入失败"); }
   FileFlush(g_rejectFh);
}

'''
c = c[:start] + new_wr + c[end:]

# ---- REJECT_HEADER 与 REJECT_COLS 对齐（加 nearest_xau_bar_time / server_utc_offset）----
old_h = c[c.index("const string REJECT_HEADER ="):c.index("bool HeaderUnique")]
new_h = '''const string REJECT_HEADER =
   "run_tag,symbol,utc_day,signal_bar_time,reason,"
   "z_score,atr14,atr_p20,atr_p80,"
   "xau_bar_time,xau_return,nearest_xau_bar_time,"
   "raw_lot,final_lot,risk_budget,actual_risk,ocp_err,server_utc_offset";

'''
c = c.replace(old_h, new_h)
# 移除旧的 REJECT_COLS 定义（若有重复）
c = c.replace("#define REJECT_COLS 16\n", "")

io.open(P, "w", encoding="utf-8").write(c)
print("patched; braces:", c.count("{"), "/", c.count("}"))
