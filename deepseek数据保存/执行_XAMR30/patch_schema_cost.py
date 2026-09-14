import io

P = r"D:\desktop\新量化策略\deepseek数据保存\mql5\dshtools\dsh_XAMR30.mq5"
c = io.open(P, encoding="utf-8").read()

# ---- 表头：在 deal_profit 后加 swap/commission/net（裁定 §6 允许"至少"这些字段，补全便于对账）----
c = c.replace('"ocp_expected_pl,deal_profit,formula_value,formula_diff,"',
              '"ocp_expected_pl,deal_profit,swap,commission,net,formula_value,formula_diff,"')
c = c.replace("#define AUDIT_COLS 38", "#define AUDIT_COLS 41")

# ---- 写入数组：补 3 个字段，并把 formula_* 重编号 ----
c = c.replace('   ADD(DoubleToString(dp, 4));                                                       // 32 deal_profit\n'
              '   ADD(DoubleToString(fV, 4));                                                       // 33 formula_value\n'
              '   ADD(DoubleToString(fDiff, 4));                                                    // 34 formula_diff\n'
              '   ADD(closeType);                                                                   // 35 close_type\n'
              '   ADD(reason);                                                                      // 36 exit_reason\n'
              '   ADD("0");                                                                         // 37 server_utc_offset',
              '   ADD(DoubleToString(dp, 4));                                                       // 32 deal_profit\n'
              '   ADD(DoubleToString(ds, 2));                                                       // 33 swap\n'
              '   ADD(DoubleToString(dc, 2));                                                       // 34 commission\n'
              '   ADD(DoubleToString(net, 2));                                                      // 35 net\n'
              '   ADD(DoubleToString(fV, 4));                                                       // 36 formula_value\n'
              '   ADD(DoubleToString(fDiff, 4));                                                    // 37 formula_diff\n'
              '   ADD(closeType);                                                                   // 38 close_type\n'
              '   ADD(reason);                                                                      // 39 exit_reason\n'
              '   ADD("0");                                                                         // 40 server_utc_offset')

# ---- FileWrite 参数：从 38 个扩到 41 个 ----
old_fw = ('   g_lastWriteBytes = FileWrite(g_auditFh, f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8],\n'
          '             f[9], f[10], f[11], f[12], f[13], f[14], f[15], f[16], f[17], f[18],\n'
          '             f[19], f[20], f[21], f[22], f[23], f[24], f[25], f[26], f[27], f[28],\n'
          '             f[29], f[30], f[31], f[32], f[33], f[34], f[35], f[36], f[37]);')
new_fw = ('   g_lastWriteBytes = FileWrite(g_auditFh, f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8],\n'
          '             f[9], f[10], f[11], f[12], f[13], f[14], f[15], f[16], f[17], f[18],\n'
          '             f[19], f[20], f[21], f[22], f[23], f[24], f[25], f[26], f[27], f[28],\n'
          '             f[29], f[30], f[31], f[32], f[33], f[34], f[35], f[36], f[37], f[38],\n'
          '             f[39], f[40]);')
if old_fw in c:
    c = c.replace(old_fw, new_fw)
    print("FileWrite 已扩到 41 参数")
else:
    print("!! FileWrite 块未匹配")

io.open(P, "w", encoding="utf-8").write(c)
print("braces:", c.count("{"), "/", c.count("}"))
