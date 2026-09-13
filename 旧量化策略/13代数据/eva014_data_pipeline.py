# -*- coding: utf-8 -*-
"""
eva014_data_pipeline.py  ——  PyCharm 直接运行版

============================  怎么用（重要）  ============================
本文件靠最上面的  MODE  这一个变量来决定“跑哪个功能”。
要切换功能 = 改 MODE 的字符串；跑完想跑别的就再改回去。没有别的开关。

  MODE 可选值：
    "enrich"    给 trade_events 加 MFE/MAE、问题单分类（最常用）
    "volscan"   ★算训练集内“百分比波动”的真实范围，用来校准 EA 的 InpVolPct_* 阈值
    "followup"  平仓后价格路径分析（某出场原因不止损会不会回归）
    "aggregate" 只做聚合表
    "slice"     导出一段行情
    "request"   按 JSON 批量导出行情
    "cache"     把各月行情并成一个缓存文件

  ▶ 想跑 volscan：把下面写成  MODE = "volscan"  →  点 Run。
    结果看控制台输出（百分比波动各分位 + 阈值建议），明细在 enriched/volscan_summary.csv。
    跑完想回到日常：把 MODE 改回 "enrich" 即可。
========================================================================

行情仓库：eva_data/XAUUSDm/{ticks,m1,m5,m15}/YYYY-MM.csv + meta.json
"""

import os
import json
import glob
import time
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count

# =====================================================================
#                          CONFIG —— 只改这里
# =====================================================================
# ↓↓↓ 这一行就是“总开关”：改成 "volscan" 就是跑 volscan，改成 "enrich" 就是跑 enrich ↓↓↓
MODE = "enrich"              # 可选: "enrich" | "volscan" | "followup" | "aggregate" | "slice" | "request" | "cache"
# ↑↑↑ 例：要量化百分比波动范围 → 写 MODE = "volscan"，点 Run；跑完改回 "enrich"          ↑↑↑

ROOT   = "eva_data"
SYMBOL = "XAUUSDm"
OUTDIR = "enriched"

POINT        = None          # None=从 meta.json 自动；或写 0.001 强制
BIG_MOVE_USD = 3.0           # “大顺向/大不利”阈值（美元）

TRADES   = "eva_audit/run_xxx/eva_trade_events.csv"
PATH_TF  = "tick"            # 算 MFE/MAE 用 tick 还是 m1；tick 缺失自动回退 m1

N_WORKERS = 0                # 0=自动(CPU核数-1)；1=单进程(调试/复现)；>1=指定进程数
PROGRESS  = True             # 是否显示进度条/ETA

# --- slice ---
SLICE_TF="m1"; SLICE_START="2024-03-05 13:00"; SLICE_END="2024-03-05 15:00"; SLICE_OUT="seg.csv"
# --- request ---
REQUEST_FILE="my_request.json"
# --- followup（平仓后价格路径分析，用于 A 反事实）---
FOLLOWUP_SRC          = "enriched/trade_enriched.csv"   # 也可填原始 trade_events.csv
FOLLOWUP_EXIT_REASONS = ["pacing_panic_stop"]           # 要分析的出场原因（可多个）
FOLLOWUP_HORIZONS_H   = [1, 2, 4, 8, 24, 48, 72]        # 平仓后观察的时窗(小时)
FOLLOWUP_TF           = "tick"                           # 路径周期；缺失自动回退 m1
# --- volscan 专用（仅当 MODE="volscan" 时生效）：量化训练集内“百分比波动”的真实范围 ---
VOLSCAN_START   = "2025-01-01"      # 扫描起（与 EA 训练窗口一致）
VOLSCAN_END     = "2026-04-24"      # 扫描止
VOLSCAN_WINDOWS = [10, 15, 30, 60]  # 对应 EA 的 InpVolWindowMinutes（分钟=M1根数）；扫几个看窗口敏感性
# =====================================================================


def log(msg):
    print(f"[eva] {msg}", flush=True)


# ---------------------------------------------------------------------
#  进度条（无 tqdm 依赖；装了 tqdm 则用它）
# ---------------------------------------------------------------------
try:
    from tqdm import tqdm as _tqdm
    def progress_iter(it, total, desc):
        return _tqdm(it, total=total, desc=desc, ncols=80) if PROGRESS else it
except Exception:
    class _Bar:
        def __init__(self, total, desc):
            self.total=max(total,1); self.desc=desc; self.n=0; self.t0=time.time()
        def update(self,k=1):
            self.n+=k; frac=self.n/self.total; el=time.time()-self.t0
            eta=el/frac-el if frac>0 else 0
            bar=("#"*int(frac*30)).ljust(30)
            print(f"\r[eva] {self.desc} |{bar}| {self.n}/{self.total} ETA {eta:5.1f}s",end="",flush=True)
        def close(self):
            print(f"\r[eva] {self.desc} |{'#'*30}| {self.n}/{self.total} 用时 {time.time()-self.t0:5.1f}s",flush=True)
    def progress_iter(it, total, desc):
        if not PROGRESS:
            for x in it: yield x
            return
        bar=_Bar(total,desc)
        for x in it:
            yield x; bar.update(1)
        bar.close()


# ---------------------------------------------------------------------
#  meta / 路径
# ---------------------------------------------------------------------
def read_meta(root, symbol):
    p=os.path.join(root,symbol,"meta.json"); meta={}
    if os.path.exists(p):
        try: meta=json.load(open(p,"r",encoding="utf-8"))
        except Exception as e: log(f"meta.json 读取失败({e})，用缺省")
    if not meta.get("point"): meta["point"]=0.001
    return meta

def resolve_point(meta):
    return float(POINT) if POINT is not None else float(meta.get("point",0.001))

def tf_name(tf): return "ticks" if tf in ("tick","ticks") else tf
def tf_dir(root,symbol,tf): return os.path.join(root,symbol,tf_name(tf))

def months_between(t0,t1):
    out=[]; y,m=t0.year,t0.month
    while (y<t1.year) or (y==t1.year and m<=t1.month):
        out.append(f"{y:04d}-{m:02d}")
        m+=1
        if m>12: m=1; y+=1
    return out

def _load_month_arrays(base, tf, ym):
    """某月 CSV → (t_ms[int64], hi, lo)，按时间排序；缺失返回 None。"""
    path=os.path.join(base,f"{ym}.csv")
    if not os.path.exists(path): return None
    try: df=pd.read_csv(path)
    except Exception: return None
    if tf_name(tf)=="ticks":
        t=pd.to_numeric(df["time_msc"],errors="coerce")
        bid=pd.to_numeric(df.get("bid"),errors="coerce"); ask=pd.to_numeric(df.get("ask"),errors="coerce")
        hi=np.maximum(bid,ask); lo=np.minimum(bid,ask)
    else:
        if "time_iso" in df.columns:
            t=pd.to_datetime(df["time_iso"],errors="coerce").astype("datetime64[ms]").astype("int64")
        else:
            t=pd.to_numeric(df["time"],errors="coerce")*1000
        hi=pd.to_numeric(df["high"],errors="coerce"); lo=pd.to_numeric(df["low"],errors="coerce")
    m=pd.notna(t)&pd.notna(hi)&pd.notna(lo)
    t=np.asarray(t[m],dtype="int64"); hi=np.asarray(hi[m]); lo=np.asarray(lo[m])
    order=np.argsort(t,kind="mergesort")
    return t[order], hi[order], lo[order]

def _partial_extrema(arr, t0_ms, t1_ms):
    """返回 [t0,t1] 与该月数据交集内的 (Hi_max, Lo_min, has_data)。"""
    if arr is None: return np.nan, np.nan, False
    t,hi,lo=arr
    a=np.searchsorted(t,t0_ms,side="left"); b=np.searchsorted(t,t1_ms,side="right")
    if b<=a: return np.nan, np.nan, False
    return float(hi[a:b].max()), float(lo[a:b].min()), True


# ---------------------------------------------------------------------
#  多进程 worker：处理「某一日历月」covering 的所有交易（该月文件只读一次）
# ---------------------------------------------------------------------
def _process_calendar_month(args):
    """args=(ym, recs, cfg)；recs=[(idx,t0ms,t1ms)]。返回该月对各交易的局部极值。"""
    ym, recs, cfg = args
    arr = _load_month_arrays(tf_dir(cfg["root"],cfg["symbol"],cfg["ptf"]), cfg["ptf"], ym)
    out=[]
    for idx,t0,t1 in recs:
        H,L,ok=_partial_extrema(arr,t0,t1)
        if ok: out.append((idx,H,L))
    return out

def _process_calendar_month_m1(args):
    ym, recs, cfg = args
    arr=_load_month_arrays(tf_dir(cfg["root"],cfg["symbol"],"m1"),"m1",ym)
    out=[]
    for idx,t0,t1 in recs:
        H,L,ok=_partial_extrema(arr,t0,t1)
        if ok: out.append((idx,H,L))
    return out


# ---------------------------------------------------------------------
#  MODE = enrich
# ---------------------------------------------------------------------
def run_enrich():
    T=time.time(); os.makedirs(OUTDIR,exist_ok=True)

    log("[阶段 1/5] 读取 meta.json + 交易表 …")
    meta=read_meta(ROOT,SYMBOL); point=resolve_point(meta); big=float(BIG_MOVE_USD)
    tr=pd.read_csv(TRADES)
    tr["entry_time"]=pd.to_datetime(tr["entry_time"],format="%Y.%m.%d %H:%M:%S",errors="coerce")
    tr["exit_time"] =pd.to_datetime(tr["exit_time"], format="%Y.%m.%d %H:%M:%S",errors="coerce")
    log(f"           交易 {len(tr)} 笔 | point={point} | big=${big} | path_tf={PATH_TF}")

    log("[阶段 2/5] 建「月→该月需处理的交易」映射（每月文件全局只读一次）…")
    # 关键：一笔交易由它「跨越的每个月」分别贡献局部极值；最终再合并取极值。
    month_map={}; entry_dir={}; needed=[]
    for idx,r in tr.iterrows():
        t0,t1=r["entry_time"],r["exit_time"]
        if pd.isna(t0) or pd.isna(t1): continue
        t0ms=int(t0.value//10**6); t1ms=int(t1.value//10**6)
        for ym in months_between(t0,t1):
            month_map.setdefault(ym,[]).append((idx,t0ms,t1ms))
        entry_dir[idx]=(float(r["entry_price"]),int(r["direction"]))
        needed.append(idx)
    cfg={"root":ROOT,"symbol":SYMBOL,"ptf":PATH_TF}
    tasks=[(ym,recs,cfg) for ym,recs in sorted(month_map.items())]
    log(f"           覆盖 {len(tasks)} 个日历月，{len(needed)} 笔参与计算")

    nw=(max(cpu_count()-1,1) if N_WORKERS==0 else int(N_WORKERS))
    log(f"[阶段 3/5] 并行计算各月局部极值并合并（进程数={nw}）…")
    Hmax={}; Lmin={}; have_tick=set()
    def absorb(chunk):
        for idx,H,L in chunk:
            Hmax[idx]=H if idx not in Hmax else max(Hmax[idx],H)
            Lmin[idx]=L if idx not in Lmin else min(Lmin[idx],L)
            have_tick.add(idx)
    if nw<=1:
        for t in progress_iter(tasks,len(tasks),"MFE/MAE(单进程)"):
            absorb(_process_calendar_month(t))
    else:
        with Pool(nw) as pool:
            for chunk in progress_iter(pool.imap_unordered(_process_calendar_month,tasks),
                                       len(tasks),"MFE/MAE(多进程)"):
                absorb(chunk)

    # tick 缺失的交易 → 用 m1 回退（通常极少）
    miss=[i for i in needed if i not in have_tick]
    src_map={i:PATH_TF for i in have_tick}
    if miss and PATH_TF in ("tick","ticks"):
        log(f"[阶段 3b] {len(miss)} 笔无 tick，回退 m1 …")
        mm={}
        for idx in miss:
            t0=tr.loc[idx,"entry_time"]; t1=tr.loc[idx,"exit_time"]
            t0ms=int(t0.value//10**6); t1ms=int(t1.value//10**6)
            for ym in months_between(t0,t1):
                mm.setdefault(ym,[]).append((idx,t0ms,t1ms))
        for t in progress_iter([(ym,recs,cfg) for ym,recs in sorted(mm.items())],len(mm),"m1回退"):
            for idx,H,L in _process_calendar_month_m1(t):
                Hmax[idx]=H if idx not in Hmax else max(Hmax[idx],H)
                Lmin[idx]=L if idx not in Lmin else min(Lmin[idx],L)
                src_map[idx]="m1"

    log("[阶段 4/5] 由极值算 MFE/MAE + 问题单分类 …")
    def mfe_mae(idx):
        if idx not in Hmax: return np.nan,np.nan,"none"
        ep,d=entry_dir[idx]; H=Hmax[idx]; L=Lmin[idx]
        if d>=0: return H-ep, ep-L, src_map.get(idx,"none")
        else:    return ep-L, H-ep, src_map.get(idx,"none")
    res={i:mfe_mae(i) for i in tr.index}
    tr["mfe_usd"]=[res[i][0] for i in tr.index]
    tr["mae_usd"]=[res[i][1] for i in tr.index]
    tr["path_source"]=[res[i][2] for i in tr.index]
    tr["realized_move_usd"]=(tr["exit_price"]-tr["entry_price"]).abs()
    tr["capture_ratio"]=np.where(tr["mfe_usd"]>0, tr["realized_move_usd"]/tr["mfe_usd"], np.nan)

    def classify(r):
        pnl,mfe,mae=r["net_pnl"],r["mfe_usd"],r["mae_usd"]
        if not (np.isfinite(mfe) and np.isfinite(mae)): return "no_path"
        if mae>=big: return "deep_underwater"
        if pnl<0 and mfe>=big: return "gaveback_loss"
        if pnl>0 and np.isfinite(r["capture_ratio"]) and r["capture_ratio"]<0.3 and mfe>=big: return "early_exit"
        return "normal"
    tr["problem_tag"]=tr.apply(classify,axis=1)

    log("[阶段 5/5] 写出文件 …")
    tr.to_csv(os.path.join(OUTDIR,"trade_enriched.csv"),index=False)
    tr[tr["problem_tag"].isin(["deep_underwater","gaveback_loss","early_exit"])] \
      .to_csv(os.path.join(OUTDIR,"problem_trades.csv"),index=False)
    _write_aggregates(tr)
    log("问题单分布: "+", ".join(f"{k}={v}" for k,v in tr["problem_tag"].value_counts().items()))
    log(f"全部完成，总用时 {time.time()-T:.1f}s。输出目录: {OUTDIR}/")
    return tr


# ---------------------------------------------------------------------
#  聚合 / slice / request / cache
# ---------------------------------------------------------------------
def _agg(g):
    pnl=g["net_pnl"]; gp=pnl[pnl>0].sum(); gl=-pnl[pnl<0].sum()
    return pd.Series({"n":len(g),"net_pnl":pnl.sum(),"win_rate":(pnl>0).mean(),
                      "avg_pnl":pnl.mean(),"max_loss":pnl.min(),
                      "profit_factor":(gp/gl) if gl>0 else np.inf})

def _write_aggregates(tr):
    os.makedirs(OUTDIR,exist_ok=True); tr=tr.copy()
    if "entry_time" in tr.columns:
        tr["year"]=pd.to_datetime(tr["entry_time"],errors="coerce").dt.year
    tr.groupby(["order_kind","entry_reason"],dropna=False).apply(_agg).reset_index() \
      .to_csv(os.path.join(OUTDIR,"signal_performance.csv"),index=False)
    cols=[c for c in ["vol_regime","real_vol_regime","market_state","year"] if c in tr.columns]
    tr.groupby(cols,dropna=False).apply(_agg).reset_index() \
      .to_csv(os.path.join(OUTDIR,"regime_performance.csv"),index=False)
    log("写出 signal_performance.csv / regime_performance.csv")

def run_aggregate():
    src=os.path.join(OUTDIR,"trade_enriched.csv")
    if not os.path.exists(src): src=TRADES
    _write_aggregates(pd.read_csv(src))

def _load_path_df(root,symbol,tf,t0,t1):
    base=tf_dir(root,symbol,tf); mm=months_between(t0,t1); frames=[]
    for ym in progress_iter(mm,len(mm),f"load {tf}"):
        arr=_load_month_arrays(base,tf,ym)
        if arr is not None:
            t,hi,lo=arr; frames.append(pd.DataFrame({"t_ms":t,"hi":hi,"lo":lo}))
    if not frames: return None
    d=pd.concat(frames,ignore_index=True); d["time"]=pd.to_datetime(d["t_ms"],unit="ms")
    return d.loc[(d["time"]>=t0)&(d["time"]<=t1)].reset_index(drop=True)

def run_slice():
    os.makedirs(OUTDIR,exist_ok=True)
    d=_load_path_df(ROOT,SYMBOL,SLICE_TF,pd.to_datetime(SLICE_START),pd.to_datetime(SLICE_END))
    if d is None or len(d)==0: log("该区间无数据。"); return
    d.to_csv(os.path.join(OUTDIR,SLICE_OUT),index=False); log(f"切片 → {OUTDIR}/{SLICE_OUT}（{len(d)} 行）")

def run_request():
    os.makedirs(OUTDIR,exist_ok=True)
    spec=json.load(open(REQUEST_FILE,"r",encoding="utf-8")); reqs=spec.get("requests",[]); log(f"请求 {len(reqs)} 条")
    for i,q in enumerate(reqs):
        d=_load_path_df(ROOT,SYMBOL,q.get("timeframe","m1"),pd.to_datetime(q["start"]),pd.to_datetime(q["end"]))
        out=os.path.join(OUTDIR,q.get("out",f"req_{i}.csv"))
        if d is None or len(d)==0: log(f"  #{i} 无数据"); continue
        d.to_csv(out,index=False); log(f"  #{i} → {out}（{len(d)} 行）")

def run_cache():
    os.makedirs(OUTDIR,exist_ok=True)
    for tf in ["ticks","m1","m5","m15"]:
        files=sorted(glob.glob(os.path.join(tf_dir(ROOT,SYMBOL,tf),"*.csv")))
        if not files: continue
        frames=[pd.read_csv(fp) for fp in progress_iter(files,len(files),f"cache {tf}")]
        big=pd.concat(frames,ignore_index=True)
        dst=os.path.join(OUTDIR,f"cache_{tf}.parquet")
        try: big.to_parquet(dst,index=False)
        except Exception:
            dst=os.path.join(OUTDIR,f"cache_{tf}.csv"); big.to_csv(dst,index=False)
        log(f"缓存 {tf}: {len(files)} 月 → {dst}（{len(big)} 行）")


# ---------------------------------------------------------------------
#  MODE = followup —— 平仓后价格路径分析（A 反事实：不止损会回归还是更糟）
# ---------------------------------------------------------------------
def run_followup():
    T=time.time(); os.makedirs(OUTDIR,exist_ok=True)
    log("[followup 1/3] 读取来源表 + 筛选目标出场 …")
    df=pd.read_csv(FOLLOWUP_SRC)
    df["entry_time"]=pd.to_datetime(df["entry_time"],format="%Y.%m.%d %H:%M:%S",errors="coerce")
    df["exit_time"] =pd.to_datetime(df["exit_time"], format="%Y.%m.%d %H:%M:%S",errors="coerce")
    sub=df[df["exit_reason"].isin(FOLLOWUP_EXIT_REASONS)].copy()
    sub=sub.dropna(subset=["entry_time","exit_time"]).reset_index(drop=True)
    log(f"           命中 {len(sub)} 笔（出场原因 {FOLLOWUP_EXIT_REASONS}）")
    if len(sub)==0: log("无目标交易，结束。"); return

    base_p=tf_dir(ROOT,SYMBOL,FOLLOWUP_TF); base_m1=tf_dir(ROOT,SYMBOL,"m1")
    Hs=sorted(FOLLOWUP_HORIZONS_H); maxH=Hs[-1]
    cache={}
    def get_month(base,tf,ym):
        key=(base,ym)
        if key not in cache: cache[key]=_load_month_arrays(base,tf,ym)
        return cache[key]

    log("[followup 2/3] 逐笔扫描平仓后价格 …")
    rows=[]
    for _,r in progress_iter(sub.iterrows(), len(sub), "followup"):
        ep=float(r["entry_price"]); xp=float(r["exit_price"]); d=int(r["direction"])
        t_exit=r["exit_time"]; t_end=t_exit+pd.Timedelta(hours=maxH)
        t0ms=int(t_exit.value//10**6)
        # 收集 [exit, exit+maxH] 的 (t,hi,lo)
        seg_t=[]; seg_hi=[]; seg_lo=[]; src=FOLLOWUP_TF
        for ym in months_between(t_exit,t_end):
            arr=get_month(base_p,FOLLOWUP_TF,ym)
            if arr is None: continue
            t,hi,lo=arr; a=np.searchsorted(t,t0ms,side="left"); b=np.searchsorted(t,int(t_end.value//10**6),side="right")
            if b>a: seg_t.append(t[a:b]); seg_hi.append(hi[a:b]); seg_lo.append(lo[a:b])
        if not seg_t and FOLLOWUP_TF in ("tick","ticks"):   # 回退 m1
            src="m1"
            for ym in months_between(t_exit,t_end):
                arr=get_month(base_m1,"m1",ym)
                if arr is None: continue
                t,hi,lo=arr; a=np.searchsorted(t,t0ms,side="left"); b=np.searchsorted(t,int(t_end.value//10**6),side="right")
                if b>a: seg_t.append(t[a:b]); seg_hi.append(hi[a:b]); seg_lo.append(lo[a:b])
        rec={"entry_time":r["entry_time"],"exit_time":t_exit,"direction":d,
             "entry_price":ep,"exit_price":xp,"net_pnl":r.get("net_pnl",np.nan),"path_source":src if seg_t else "none"}
        if not seg_t:
            rows.append(rec); continue
        T_=np.concatenate(seg_t); HI=np.concatenate(seg_hi); LO=np.concatenate(seg_lo)
        o=np.argsort(T_,kind="mergesort"); T_=T_[o]; HI=HI[o]; LO=LO[o]
        # 首次回到入场价(保本)的时间
        if d>=0: touch=np.where(HI>=ep)[0]
        else:    touch=np.where(LO<=ep)[0]
        rec["recover_to_entry_hours"]=((T_[touch[0]]-t0ms)/3.6e6) if len(touch) else np.nan
        for H in Hs:
            hb=t0ms+H*3600*1000; idx=np.where(T_<=hb)[0]
            if len(idx)==0:
                rec[f"further_mae_usd_{H}h"]=np.nan; rec[f"pnl_if_held_{H}h"]=np.nan; continue
            j=idx[-1]; hi_h=HI[:j+1].max(); lo_h=LO[:j+1].min()
            # 相对入场：若继续扛，期间最大额外不利(美元)
            rec[f"further_mae_usd_{H}h"]= (ep-lo_h) if d>=0 else (hi_h-ep)
            # 若恰好持有到 H 末按市价平：盈亏(美元)
            last_mid=(HI[j]+LO[j])/2.0
            rec[f"pnl_if_held_{H}h"]=(last_mid-ep)*d
        rows.append(rec)

    out=pd.DataFrame(rows)
    log("[followup 3/3] 写出 + 汇总 …")
    out.to_csv(os.path.join(OUTDIR,"followup.csv"),index=False)
    # 控制台汇总：回归率 + 继续扛的盈亏
    n=len(out); rec_h=out["recover_to_entry_hours"]
    for H in Hs:
        within=(rec_h<=H).sum()
        pcol=f"pnl_if_held_{H}h"; mcol=f"further_mae_usd_{H}h"
        if pcol in out:
            med_pnl=out[pcol].median(); win=(out[pcol]>0).mean()*100; med_mae=out[mcol].median()
            log(f"  {H:>2}h内回到入场价: {within}/{n} ({100*within/n:.0f}%) | "
                f"继续扛到{H}h 盈亏中位 ${med_pnl:.1f}, 翻正率 {win:.0f}%, 期间额外浮亏中位 ${med_mae:.1f}")
    log(f"完成，详见 {OUTDIR}/followup.csv（用时 {time.time()-T:.1f}s）")
    return out


def _load_m1_close(root, symbol, ym):
    """读某月 M1 → (t_ms[int64], close[float])，按时间排序；缺失 None。"""
    path = os.path.join(tf_dir(root, symbol, "m1"), f"{ym}.csv")
    if not os.path.exists(path): return None
    try: df = pd.read_csv(path)
    except Exception: return None
    if "time_iso" in df.columns:
        t = pd.to_datetime(df["time_iso"], errors="coerce").astype("datetime64[ms]").astype("int64")
    else:
        t = pd.to_numeric(df["time"], errors="coerce")*1000
    c = pd.to_numeric(df.get("close"), errors="coerce")
    m = pd.notna(t) & pd.notna(c)
    t = np.asarray(t[m], dtype="int64"); c = np.asarray(c[m], dtype="float64")
    o = np.argsort(t, kind="mergesort")
    return t[o], c[o]


def run_volscan():
    """复刻 EA 公式：百分比波动 = 100 * RMS(每分钟收盘差, 窗口W分钟) / 当前价。
    输出训练集内该值的分布(各分位)，并对多个窗口W做敏感性，给阈值建议。"""
    os.makedirs(OUTDIR, exist_ok=True)
    t0 = pd.to_datetime(VOLSCAN_START); t1 = pd.to_datetime(VOLSCAN_END)
    log(f"[volscan] 载入 M1 收盘 {VOLSCAN_START}~{VOLSCAN_END} …")
    months = months_between(t0 - pd.Timedelta(days=2), t1)   # 多带2天热身
    frames = []
    for ym in progress_iter(months, len(months), "load m1"):
        arr = _load_m1_close(ROOT, SYMBOL, ym)
        if arr is not None:
            tt, cc = arr; frames.append(pd.DataFrame({"t": tt, "c": cc}))
    if not frames:
        log("未找到 M1 数据（检查 eva_data/XAUUSDm/m1/）。"); return
    d = pd.concat(frames, ignore_index=True).drop_duplicates("t").sort_values("t").reset_index(drop=True)
    d["time"] = pd.to_datetime(d["t"], unit="ms")
    d = d[(d["time"] >= t0) & (d["time"] <= t1 + pd.Timedelta(days=1))].reset_index(drop=True)
    log(f"[volscan] 有效分钟数 {len(d)}")
    if len(d) < 100: log("数据太少。"); return

    diff = d["c"].diff()                       # 每分钟收盘差(价格单位)
    price = d["c"].values
    rows = []
    rep = {}
    for W in VOLSCAN_WINDOWS:
        rms = np.sqrt((diff.pow(2)).rolling(W).mean()).values
        rv_pct = 100.0 * rms / price           # = 100 * RMS / price（point 已约掉）
        sr = pd.Series(rv_pct).replace([np.inf, -np.inf], np.nan).dropna()
        q = sr.quantile([.01,.05,.25,.33,.5,.66,.75,.95,.99]).round(5)
        rep[W] = q
        log(f"  窗口 W={W:>3} 分钟 | 百分比波动%: min {sr.min():.5f}  p5 {q[.05]:.5f}  "
            f"p50 {q[.5]:.5f}  p95 {q[.95]:.5f}  max {sr.max():.5f}")
        rows.append({"W":W,"min":round(sr.min(),5),**{f"p{int(k*100)}":v for k,v in q.items()},
                     "max":round(sr.max(),5)})
    pd.DataFrame(rows).to_csv(os.path.join(OUTDIR,"volscan_summary.csv"), index=False)

    # 用默认窗口(列表第2个或第1个)给阈值建议：三分位做 低/中/高 边界
    Wdef = VOLSCAN_WINDOWS[1] if len(VOLSCAN_WINDOWS) > 1 else VOLSCAN_WINDOWS[0]
    q = rep[Wdef]
    p33, p50, p66 = q[.33], q[.5], q[.66]
    log(f"\n[volscan] 基于 W={Wdef} 的阈值建议（含滞后带，可作 InpVolPct_* 起点）：")
    log(f"  InpVolPct_MidToLow  ≈ {p33*0.9:.5f}")
    log(f"  InpVolPct_LowToMid  ≈ {p33:.5f}")
    log(f"  InpVolPct_HighToMid ≈ {p66:.5f}")
    log(f"  InpVolPct_MidToHigh ≈ {p66*1.1:.5f}")
    log(f"  优化范围参考：低边在 [{q[.05]:.5f}, {p50:.5f}]，高边在 [{p50:.5f}, {q[.95]:.5f}]")
    log(f"[volscan] 明细 → {OUTDIR}/volscan_summary.csv")


def main():
    log(f"MODE = {MODE}")
    {"enrich":run_enrich,"aggregate":run_aggregate,"slice":run_slice,
     "request":run_request,"cache":run_cache,"followup":run_followup,
     "volscan":run_volscan}.get(
        MODE, lambda:(_ for _ in ()).throw(ValueError(f"未知 MODE: {MODE}")))()


if __name__=="__main__":
    main()
