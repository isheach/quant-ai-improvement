import io

P = r"D:\desktop\新量化策略\deepseek数据保存\mql5\dshtools\dsh_XAMR30.mq5"
c = io.open(P, encoding="utf-8").read()

old = c[c.index("bool EvaluateSignalBar(int tShift)"):c.index("//==================== 生命周期 ====================")]

new = '''bool EvaluateSignalBar(int tShift)
{
   // ★★★ N1R3：每个 candidate 开始时先把 snapshot 全部清零，
   //   且 reject 写入显式传参（不再依赖历史全局状态）。
   datetime cbar = iTime(_Symbol, TF(), tShift);

   // ---- 1) EMA48（★N1R3：改为 iMA 权威实现；取不到即拒绝，不 fallback）----
   double emaT = 0.0;
   if(!EmaReady(tShift, emaT))
   {
      g_rejSigma++;
      WriteReject(cbar, "sigma_invalid", 0,0,0,0,0,
                  0.0, false,            // z 未算出
                  0.0, false,            // ATR 未算出
                  0.0, 0.0, false,       // P20/P80 未算出
                  0, 0, 0.0, false);     // XAU 未检查
      return false;
   }
   double eT = iClose(_Symbol, TF(), tShift) - emaT;
   double sigT = 0.0;
   if(!SigmaBeforeT(tShift, sigT))
   {
      g_rejSigma++;
      WriteReject(cbar, "sigma_invalid", 0,0,0,0,0,
                  0.0, false,
                  0.0, false,
                  0.0, 0.0, false,
                  0, 0, 0.0, false);
      return false;
   }
   double zT = eT / sigT;
   g_pendZ = zT; g_pendEma = emaT; g_pendRes = eT; g_pendSig = sigT;

   if(MathAbs(zT) < InpZThreshold) { g_skipNoSignal++; return false; }

   // ---- 2) ATR14 与 regime ----
   double a[];
   if(CopyBuffer(g_atrHandle, 0, tShift, 1, a) != 1)
   {
      g_rejAtrInsuf++;
      WriteReject(cbar, "atr_insufficient", 0,0,0,0,0,
                  zT, true, 0.0, false, 0.0, 0.0, false, 0, 0, 0.0, false);
      return false;
   }
   double atrT = a[0];
   g_pendAtr = atrT;
   double p20 = 0.0, p80 = 0.0;
   if(!AtrPercentile(tShift, p20, p80) || atrT <= 0.0)
   {
      g_rejAtrInsuf++;
      WriteReject(cbar, "atr_insufficient", 0,0,0,0,0,
                  zT, true, atrT, true, 0.0, 0.0, false, 0, 0, 0.0, false);
      return false;
   }
   g_pendP20 = p20; g_pendP80 = p80;
   if(atrT < p20 || atrT > p80)
   {
      g_rejAtrRegime++;
      // ★此处 XAU 尚未检查 → xau_bar_time / xau_return 一律留空
      WriteReject(cbar, "atr_out_of_regime", 0,0,0,0,0,
                  zT, true, atrT, true, p20, p80, true, 0, 0, 0.0, false);
      return false;
   }

   // ---- 3) 跨品种 exact timestamp ----
   datetime jt = cbar;
   int sx = iBarShift(InpInfoSymbol, PERIOD_M30, jt, false);
   int xbars = iBars(InpInfoSymbol, PERIOD_M30);
   bool exact = false;
   datetime xt = 0, nearestXau = 0;
   double xo = 0.0, xc = 0.0;
   if(sx >= 0 && sx < xbars)
   {
      nearestXau = iTime(InpInfoSymbol, PERIOD_M30, sx);   // ★诊断用
      if(nearestXau == jt)
      {
         exact = true; xt = nearestXau;
         xo = iOpen(InpInfoSymbol, PERIOD_M30, sx);
         xc = iClose(InpInfoSymbol, PERIOD_M30, sx);
      }
   }
   // ★只有在 exact 命中时才把 XAU 快照写进 g_pend*（否则保持 0，避免污染）
   g_pendXauT = exact ? xt : 0;
   g_pendXauO = exact ? xo : 0.0;
   g_pendXauC = exact ? xc : 0.0;
   double xr = (exact && xo > 0.0) ? (xc / xo - 1.0) : 0.0;
   g_pendXauR = exact ? xr : 0.0;

   if(!exact)
   {
      g_rejXauMissing++;
      // ★exact XAU 不存在 → xau_bar_time / xau_return 必须留空；
      //   nearest 只写进独立诊断字段
      WriteReject(jt, "cross_asset_missing_bar", 0,0,0,0,0,
                  zT, true, atrT, true, p20, p80, true,
                  0, nearestXau, 0.0, false);
      return false;
   }

   // ---- 4) 方向 ----
   int dir = (zT > 0) ? -1 : 1;           // trade_direction = -sign(z)
   if(dir > 0 && !InpAllowLong)  { g_skipNoSignal++; return false; }
   if(dir < 0 && !InpAllowShort) { g_skipNoSignal++; return false; }

   // ---- 5) cross-asset filter（V2 关闭此步，但 exact 要求已在步骤 3 强制）----
   if(InpCrossAssetFilter)
   {
      bool ok = (xr != 0.0) && ((xr > 0 && zT > 0) || (xr < 0 && zT < 0));
      g_pendXauPass = ok ? 1 : 0;
      if(!ok)
      {
         g_rejXauFail++;
         WriteReject(jt, "cross_asset_filter_fail", 0,0,0,0,0,
                     zT, true, atrT, true, p20, p80, true,
                     xt, nearestXau, xr, true);
         return false;
      }
   }
   else g_pendXauPass = 0;

   g_pendSignalBar = jt;
   g_signalCloseTime = (datetime)((long)jt + 1800);
   g_pendDir = dir;
   return true;
}

'''
c = c.replace(old, new)

# OpenTrade 里的 risk reject 调用补参数
c = c.replace("      WriteReject(now, rs, 0, 0, rb, ar, oerr);",
              "      WriteReject(now, rs, 0, 0, rb, ar, oerr,\n"
              "                  g_pendZ, (g_pendZ != 0.0), g_pendAtr, (g_pendAtr > 0.0),\n"
              "                  g_pendP20, g_pendP80, (g_pendP80 > 0.0),\n"
              "                  g_pendXauT, 0, g_pendXauR, (g_pendXauT > 0));")

io.open(P, "w", encoding="utf-8").write(c)
print("braces:", c.count("{"), "/", c.count("}"))
