# -*- coding: utf-8 -*-
"""check_ea.py <file.mq5> —— 通用 EA 交付前静态自检"""
import hashlib
import re
import sys
from pathlib import Path

p = Path(sys.argv[1])
raw = p.read_bytes()
t = raw.decode("utf-8", errors="replace")


def strip_code(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            i += 1
            while i < n:
                if s[i] == "\\":
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
                if s[i] == "\\":
                    i += 2
                    continue
                if s[i] == "'":
                    i += 1
                    break
                i += 1
            out.append("''")
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            while i < n and s[i] not in "\r\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            i += 2
            while i + 1 < n and not (s[i] == "*" and s[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


code = strip_code(t)
fails = []
print("=" * 74)
print(f"file    : {p.name}")
print(f"bytes   : {len(raw)}")
print(f"lines   : {t.count(chr(10)) + 1}")
print(f"sha256  : {hashlib.sha256(raw).hexdigest().upper()}")
print(f"BOM     : {'YES(!!)' if raw[:3] == b'\\xef\\xbb\\xbf' else 'no'}")
print("=" * 74)

for a, b, nm in [("{", "}", "braces"), ("(", ")", "parens"), ("[", "]", "brackets")]:
    ca, cb = code.count(a), code.count(b)
    st = "OK" if ca == cb else "MISMATCH"
    print(f"  {nm:<9} {ca} / {cb}   {st}")
    if ca != cb:
        fails.append(f"{nm} {ca}/{cb}")

FUNC = re.compile(
    r"(?m)^[ \t]*(?:void|int|bool|double|string|long|ulong|datetime)\s+([A-Za-z_]\w*)\s*\(")
defs = [(m.group(1), code[: m.start()].count("\n") + 1) for m in FUNC.finditer(code)]
dline = {}
for nm, ln in defs:
    dline.setdefault(nm, ln)
print(f"  functions: {', '.join(sorted(dline))}")

inp = re.findall(r"(?m)^[ \t]*input\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*=", code)
print(f"  inputs({len(inp)}): {', '.join(inp)}")

# FILE_COMMON 检查
bad = []
for fn in ("FileOpen", "FolderCreate", "FileIsExist"):
    for m in re.finditer(fn + r"\s*\(", code):
        i, depth = m.end() - 1, 0
        while i < len(code):
            if code[i] == "(":
                depth += 1
            elif code[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        if "FILE_COMMON" not in code[m.end(): i]:
            bad.append(f"{fn}@L{code[:m.start()].count(chr(10)) + 1}")
if bad:
    fails.append("FILE_COMMON missing: " + ", ".join(bad))
    print(f"  !! FILE_COMMON missing: {bad}")
else:
    print(f"  FILE_COMMON: OK ({len(re.findall('FILE_COMMON', code))} occurrences)")

for req in ("int OnInit()", "void OnDeinit(", "void OnTick()"):
    hit = req in code
    print(f"  {req:<20} {'OK' if hit else 'MISSING'}")
    if not hit:
        fails.append(req)

print("=" * 74)
print("RESULT: " + ("ALL PASS" if not fails else f"{len(fails)} FAILED -> {fails}"))
print("=" * 74)
