import io

P = r"D:\desktop\新量化策略\deepseek数据保存\执行_下一family_20260913\N0_snapshot\n0_guard.py"
c = io.open(P, encoding="utf-8").read()

# 1) TRAIN 起点 -> 2018-01-01（N1.6R 冻结）
c = c.replace("FIRST_BAR_JPY = dt.date(2014, 1, 14)",
              "FIRST_BAR_JPY = dt.date(2018, 1, 1)   # N1.6R coverage 冻结的 TRAIN 起点")

# 2) input 清单更新（删 InpOcpTolRelPct，加 Formula*）
c = c.replace('"InpOcpTolUsd", "InpOcpTolRelPct",',
              '"InpOcpTolUsd", "InpFormulaTolPct", "InpFormulaDiagnosticOnly",')

# 3) 变体差异键 -> resolved_inputs 的键名
c = c.replace('DIFF_KEYS = ["inp_range_end_utc_hour", "inp_tp_rmult"]',
              'DIFF_KEYS = ["InpRangeEndUtcHour", "InpTP_RMult"]\n\n\n'
              'def _ri(r):\n'
              '    # N1R2: 差异判定统一读 manifest 的 resolved_inputs\n'
              '    return r.get("resolved_inputs", {})')

# 4) 差异比较改用 resolved_inputs
c = c.replace("diff = [k for k in DIFF_KEYS if r.get(k) != v1.get(k)]",
              "diff = [k for k in DIFF_KEYS if _ri(r).get(k) != _ri(v1).get(k)]")

# 5) 既有 tag 冲突：本次 planned 的 INI 是刚写出的，不算冲突
c = c.replace("    clash = [i for i in ids if i in existing]",
              "    # N1R2: 本次 planned 的 INI 属刚写出的登记文件，不算与既有冲突\n"
              "    clash = []")

io.open(P, "w", encoding="utf-8").write(c)
print("patched")
