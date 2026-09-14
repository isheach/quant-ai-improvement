import datetime
import hashlib
import io
import json
import os

OUT = r"D:\desktop\新量化策略\deepseek数据保存\执行_下一family_20260913\N0_snapshot\JSB30_planned_runs.jsonl"
SRC = r"D:\desktop\新量化策略\deepseek数据保存\mql5\dshtools\dsh_JSB30.mq5"
EX5 = os.path.join(os.environ["APPDATA"], "MetaQuotes", "Terminal",
                   "53785E099C927DB68A545C249CDBCE06",
                   "MQL5", "Experts", "dshtrend", "dsh_JSB30.ex5")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest().upper()


sh, eh = sha(SRC), sha(EX5)
rows = [json.loads(l) for l in io.open(OUT, encoding="utf-8") if l.strip()]
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
for r in rows:
    r["expert_source_sha256"] = sh
    r["ex5_sha256"] = eh
    r["source_bytes"] = os.path.getsize(SRC)
    r["ex5_bytes"] = os.path.getsize(EX5)
    r["inp_ocp_tol_usd"] = 0.05
    r["n1r_status"] = "frozen"
    r["compile"] = "0 errors / 0 warnings (MetaEditor64, MT5 build 6184)"
    r["refrozen_at_local"] = now
    r["n1_hash_superseded"] = ("E3E80B296AC82B560C56C949D3DC3E3FEEF5511E33B27B58D3E8E36C71235A69 / "
                              "7559C19F1FB87ED62C23EDBB30D7840A8BD11FC4E189F64E89A561C34905B45D (N1 needs_repair)")
with io.open(OUT, "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("已更新 %d 条" % len(rows))
print("  N1R source:", sh)
print("  N1R ex5   :", eh)
