import io
import os
import re

SRC = r"D:\desktop\新量化策略\deepseek数据保存\mql5\dshtools\dsh_JSB30.mq5"
OUT = r"D:\desktop\新量化策略\deepseek数据保存\执行_下一family_20260913\N0_snapshot\JSB30_static_inputs_final.md"

s = io.open(SRC, encoding="utf-8", errors="ignore").read()
ins = re.findall(r"^\s*input\s+([A-Za-z_][\w:]*)\s+(\w+)\s*=\s*([^;]+);\s*(?://\s*(.*))?$",
                 s, re.M)
print("从 source 提取 input 数:", len(ins))

L = []
L.append("# JSB30 静态输入表（N1R2 · 由源码自动生成，零漂移）")
L.append("")
L.append("- ★本表由 `dsh_JSB30.mq5` 的 input 声明【自动生成】，避免手工维护造成漂移")
L.append("- 四方一致性（source / 本表 / INI `[TesterInputs]` / manifest `resolved_inputs`）")
L.append("  由 `n0_fourway.py` 强制检查；任何缺项、额外项、值不一致 → 拒绝运行")
L.append("")
L.append("| # | 名称 | 类型 | 默认值 | 说明 |")
L.append("|---|---|---|---|---|")
for i, (t, n, v, c) in enumerate(ins, 1):
    L.append("| %d | `%s` | %s | %s | %s |" % (i, n, t, v.strip(), c.strip()))
L.append("")
L.append("## 变体差异（★只允许这两处）")
L.append("")
L.append("| input | V1 (baseline) | V2 | V3 |")
L.append("|---|---|---|---|")
L.append("| `InpRangeEndUtcHour` | 6（expected 12 bars） | **3（expected 6 bars）** | 6 |")
L.append("| `InpTP_RMult` | 1.5 | 1.5 | **1.0** |")
L.append("")
L.append("## 固定口径")
L.append("")
L.append("```")
L.append("TRAIN = 2018-01-01 ~ 2024-05-31     （N1.6R coverage 冻结）")
L.append("VALID = 2024-06-01 ~ 2025-05-31")
L.append("server_utc_offset = 0                （N1R2 实测裁定，server == UTC）")
L.append("OCP 主判据 = |DEAL_PROFIT - OCP| <= 0.05 USD")
L.append("独立公式 = diagnostic only（不参与 pass/fail）")
L.append("range 完整性 = rangeCount == expected（V1/V3: 12, V2: 6），否则当天不交易")
L.append("```")
L.append("")

io.open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("已重建:", OUT, os.path.getsize(OUT), "字节")
