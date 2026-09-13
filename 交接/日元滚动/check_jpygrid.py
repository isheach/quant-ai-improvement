# -*- coding: utf-8 -*-
"""
check_jpygrid.py —— dsh_JPYGrid.mq5 交付前自检（不编译，纯静态）
  ① 括号配平（去注释/字符串后）
  ② 每个被调用的自定义函数都必须在【首次使用之前】定义（MQL5 允许前向引用，但我不依赖它）
  ③ 所有 Inp* 标识符都已声明为 input
  ④ 所有 FileOpen / FolderCreate / FileIsExist 都带 FILE_COMMON（父代理硬要求）
  ⑤ 关键机制必须存在：OnTradeTransaction、HistorySelectByPosition、InpLatencyMs、三层硬上限
  ⑥ 字节数 + SHA256
"""
import hashlib
import re
import sys
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else
           r"D:\desktop\新量化策略\deepseek数据保存\交接\日元滚动\dsh_JPYGrid.mq5")

raw = SRC.read_bytes()
text = raw.decode("utf-8", errors="replace")
fails, warns, oks = [], [], []


def ok(m):    oks.append(m)
def warn(m):  warns.append(m)
def fail(m):  fails.append(m)


# ---------- 0. 编码 / BOM ----------
if raw[:3] == b"\xef\xbb\xbf":
    warn("文件带 UTF-8 BOM（MT5 能读，但历史上我们一律不用 BOM）")
else:
    ok("无 BOM")

# ---------- 1. 去注释 + 去字符串（先字符串后注释，避免 // 在字符串里被误删）----------
def strip_code(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            i += 1
            while i < n:
                if s[i] == '\\':
                    i += 2
                    continue
                if s[i] == '"':
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        if c == "'":
            i += 1
            while i < n:
                if s[i] == '\\':
                    i += 2
                    continue
                if s[i] == "'":
                    i += 1
                    break
                i += 1
            out.append("''")
            continue
        if c == '/' and i + 1 < n and s[i + 1] == '/':
            while i < n and s[i] not in '\r\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and s[i + 1] == '*':
            i += 2
            while i + 1 < n and not (s[i] == '*' and s[i + 1] == '/'):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


code = strip_code(text)
code_noch = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)

# ---------- 2. 配平 ----------
for op, cl, name in [("{", "}", "大括号"), ("(", ")", "圆括号"), ("[", "]", "方括号")]:
    a, b = code_noch.count(op), code_noch.count(cl)
    if a == b:
        ok(f"{name}配平 {a}/{b}")
    else:
        fail(f"{name}不配平：{op}={a} {cl}={b} 差 {a-b}")

# ---------- 3. 函数定义顺序 ----------
FUNC_RE = re.compile(
    r'(?m)^[ \t]*(?:void|int|bool|double|string|long|ulong|datetime|'
    r'ENUM_ORDER_TYPE_FILLING)\s+([A-Za-z_]\w*)\s*\(', re.M)

defs = [(m.group(1), code_noch[:m.start()].count("\n") + 1) for m in FUNC_RE.finditer(code_noch)]
def_line = {}
for name, ln in defs:
    def_line.setdefault(name, ln)
ok(f"自定义函数 {len(def_line)} 个：" + ", ".join(sorted(def_line)))

# 找出所有 CALL 形式的标识符（名字后紧跟 '(' 且不是定义处）
CALL_RE = re.compile(r'([A-Za-z_]\w*)\s*\(')
# MQL5 内置 / 关键字白名单（本 EA 实际用到的）
BUILTIN = set("""
if for while switch return sizeof
Print PrintFormat StringFormat StringLen StringFind StringSubstr DoubleToString
IntegerToString TimeToString NormalizeDouble MathAbs MathMax MathMin MathPow MathFloor
TimeCurrent TimeToStruct TimeToStruct MqlDateTime ZeroMemory SymbolInfoDouble
SymbolInfoInteger SymbolInfoString AccountInfoDouble AccountInfoInteger PositionsTotal
PositionGetTicket PositionGetString PositionGetInteger PositionGetDouble
PositionSelectByTicket OrderSend CopyRates ArrayResize ArraySize ArraySetAsSeries
FileOpen FileWrite FileWriteString FileFlush FileClose FolderCreate HistoryDealSelect
HistoryDealGetString HistoryDealGetInteger HistoryDealGetDouble HistorySelectByPosition
HistoryDealsTotal HistoryDealGetTicket ResetLastError GetLastError Sleep Period
MqlTradeRequest MqlTradeResult MqlRates MqlTradeTransaction
""".split())

calls = {}
for m in CALL_RE.finditer(code_noch):
    name = m.group(1)
    if name in BUILTIN or name in def_line:
        continue
    ln = code_noch[:m.start()].count("\n") + 1
    calls.setdefault(name, ln)
if calls:
    fail("疑似调用未定义函数：" + ", ".join(f"{k}(L{v})" for k, v in sorted(calls.items())))
else:
    ok("无未定义函数调用")

# 定义前使用检查
early = []
for name, ln in def_line.items():
    for m in CALL_RE.finditer(code_noch):
        if m.group(1) != name:
            continue
        uln = code_noch[:m.start()].count("\n") + 1
        if uln < ln:
            # 排除函数定义那一行本身（原型行）
            early.append((name, uln, ln))
            break
if early:
    warn("存在定义前调用（MQL5 允许，但已尽量避免）：" +
         ", ".join(f"{n}@L{u}<L{d}" for n, u, d in early))
else:
    ok("所有自定义函数都在首次使用之前定义")

# ---------- 4. input 参数 ----------
inputs = {}
for m in re.finditer(r'(?m)^[ \t]*input\s+([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*=\s*([^;]+);', code_noch):
    inputs[m.group(2)] = m.group(3).strip()
if not inputs:
    fail("没解析出任何 input 参数")
else:
    ok(f"input 参数 {len(inputs)} 个")

used_inp = set(re.findall(r'\b(Inp[A-Za-z0-9_]*)\b', code_noch))
undeclared = sorted(used_inp - set(inputs))
if undeclared:
    fail("使用了未声明的 Inp* 参数：" + ", ".join(undeclared))
else:
    ok(f"全部 {len(used_inp)} 个 Inp* 标识符都已声明")

unused = sorted(set(inputs) - used_inp - {"InpTF"})
if unused:
    warn("声明但未使用（可能只是口径标记）：" + ", ".join(unused))

# ---------- 5. FILE_COMMON 硬要求 ----------
bad_common = []
for fn in ("FileOpen", "FolderCreate", "FileIsExist"):
    for m in re.finditer(fn + r'\s*\(', code_noch):
        # 取到该调用匹配的右括号
        i = m.end() - 1
        depth = 0
        while i < len(code_noch):
            if code_noch[i] == '(':
                depth += 1
            elif code_noch[i] == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        args = code_noch[m.end():i]
        if "FILE_COMMON" not in args:
            bad_common.append((fn, code_noch[:m.start()].count("\n") + 1))
if bad_common:
    fail("缺少 FILE_COMMON：" + ", ".join(f"{f}@L{l}" for f, l in bad_common))
else:
    ok("所有 FileOpen/FolderCreate/FileIsExist 都带 FILE_COMMON")

# ---------- 6. 关键机制 ----------
mech = {
    "OnTradeTransaction 实现": "void OnTradeTransaction(" in code_noch,
    "HistorySelectByPosition 反查入场腿": "HistorySelectByPosition(" in code_noch,
    "InpLatencyMs 出现在下单路径": code_noch.count("InpLatencyMs") >= 2,
    "三层硬上限：MaxLayers": "InpMaxLayers" in code_noch,
    "三层硬上限：MaxTotalLot": "InpMaxTotalLot" in code_noch,
    "三层硬上限：BasketStopPct": "InpBasketStopPct" in code_noch,
    "最坏浮亏记录 baskets.csv": "max_float_pct" in text and "WriteBasketRow" in code_noch,
    "InpTFMinutes 防枚举坑": "InpTFMinutes" in code_noch,
    "净额账户自动关做空": "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING" in code_noch,
    "tick 级延迟真实机制": "InpLatencyTicks" in code_noch and "g_pendTicks" in code_noch,
}
for k, v in mech.items():
    (ok if v else fail)(("机制存在: " if v else "机制缺失: ") + k)


# ---------- 6b. CSV 表头列数 vs FileWrite 参数个数 ----------
def call_args(s, start_paren):
    """返回从 '(' 起的顶层逗号切分参数列表"""
    depth, i, args, cur = 0, start_paren, [], []
    while i < len(s):
        c = s[i]
        if c in "([{":
            depth += 1
            if depth == 1:
                i += 1
                continue
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                args.append("".join(cur).strip())
                return [a for a in args if a != ""]
        if depth == 1 and c == ",":
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    return [a for a in args if a != ""]


handle_of = {}
for m in re.finditer(r'(\w+)\s*=\s*FileOpen\s*\(', code_noch):
    handle_of[m.group(1)] = m.start()
# 找每个 FileWrite(handle, ...) 里第一参数是表头字符串的情况
csv_headers = {}
for m in re.finditer(r'FileWrite\s*\(\s*(\w+)\s*,', code_noch):
    h = m.group(1)
    lp = code_noch.index("(", m.start())
    args = call_args(code_noch, lp)
    if len(args) >= 2 and args[1] == '""':
        # 表头：第一参数是 handle，往后的字符串字面量就是列名 -> 需要回到 raw 数
        pass
# 直接在 raw 里按 FileWrite(<handle>, "a","b",...) 数表头
name_re = re.compile(r'FileWrite\s*\(\s*(\w+)\s*,\s*((?:"[^"]*"\s*,\s*)*"[^"]*")\s*\)', re.S)
hdr_counts = {}
for m in name_re.finditer(text):
    h = m.group(1)
    cols = re.findall(r'"([^"]*)"', m.group(2))
    if h not in hdr_counts and len(cols) > 3:
        hdr_counts[h] = cols

# 写入端：所有 FileWrite(handle, ...) 且第一参数不是表头
write_counts = {}
for m in re.finditer(r'FileWrite\s*\(\s*(\w+)\s*,', code_noch):
    h = m.group(1)
    lp = code_noch.index("(", m.start())
    args = call_args(code_noch, lp)
    n = len(args) - 1
    write_counts.setdefault(h, []).append((n, code_noch[:m.start()].count("\n") + 1))

csv_ok = True
for h, cols in hdr_counts.items():
    for n, ln in write_counts.get(h, []):
        if n != len(cols):
            fail(f"CSV 列数不匹配：句柄 {h} 表头 {len(cols)} 列，但 L{ln} 的 FileWrite 写了 {n} 个值")
            csv_ok = False
if csv_ok:
    for h, cols in hdr_counts.items():
        ok(f"CSV 列数一致：{h} 表头 {len(cols)} 列，写入端 {len(write_counts.get(h, []))} 处全部匹配")

# ---------- 7. 交付指纹 ----------
sha = hashlib.sha256(raw).hexdigest().upper()
out = []
out.append("=" * 78)
out.append(f"文件      : {SRC}")
out.append(f"字节数    : {len(raw)}")
out.append(f"行数      : {text.count(chr(10))+1}")
out.append(f"SHA256    : {sha}")
out.append(f"input 个数: {len(inputs)}")
out.append("=" * 78)
out.append(f"[OK]   {len(oks)}")
for m in oks:
    out.append("   + " + m)
if warns:
    out.append(f"[WARN] {len(warns)}")
    for m in warns:
        out.append("   ! " + m)
if fails:
    out.append(f"[FAIL] {len(fails)}")
    for m in fails:
        out.append("   X " + m)
out.append("=" * 78)
out.append("自检结果：" + ("全部通过" if not fails else f"{len(fails)} 项失败"))
out.append("=" * 78)
out.append("")
out.append("---- input 参数清单（名称 = 默认值  |  类型）----")
for m in re.finditer(r'(?m)^[ \t]*input\s+([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*=\s*([^;]+);', code_noch):
    out.append(f"  {m.group(2):<26} = {m.group(3).strip():<12} [{m.group(1)}]")

report = "\n".join(out)
Path(SRC.parent / "selftest_JPYGrid.txt").write_text(report, encoding="utf-8")

print("=" * 78)
print(f"bytes   : {len(raw)}")
print(f"lines   : {text.count(chr(10))+1}")
print(f"SHA256  : {sha}")
print(f"inputs  : {len(inputs)}")
print(f"OK={len(oks)}  WARN={len(warns)}  FAIL={len(fails)}")
print(f"RESULT  : {'ALL PASS' if not fails else str(len(fails)) + ' FAILED'}")
print(f"report  -> {SRC.parent / 'selftest_JPYGrid.txt'}")
print("=" * 78)
