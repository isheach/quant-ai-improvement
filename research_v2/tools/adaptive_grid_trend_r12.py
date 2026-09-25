from __future__ import annotations
import csv,json,math,itertools,statistics
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'旧量化策略'/'31代数据'/'eva_data'/'eva_data'/'XAUUSDm'/'m1'
OUT=ROOT/'research_v2'/'runs'/'adaptive_grid_trend_r12'
REPORT=ROOT/'research_v2'/'reviews'/'adaptive_grid_trend_r12'
POINT=0.001; CONTRACT=100.0; START=datetime(2023,7,1); END=datetime(2026,6,30,23,59,59); HOLDOUT_START=datetime(2026,4,1)

@dataclass
class Bar:
    t:datetime; o:float; h:float; l:float; c:float; spread:float
    @property
    def bid(self): return self.c-self.spread*POINT/2
    @property
    def ask(self): return self.c+self.spread*POINT/2

def month_range(a,b):
    y,m=a.year,a.month
    while (y,m)<=(b.year,b.month):
        yield y,m
        m+=1
        if m==13:y,m=y+1,1

def load_m30(start=START,end=END):
    raw=[]
    for y,m in month_range(start,end):
        p=DATA/f'{y:04d}-{m:02d}.csv'
        if not p.exists(): continue
        with p.open(newline='',encoding='utf-8-sig') as f:
            for x in csv.DictReader(f):
                t=datetime.strptime(x['time_iso'],'%Y.%m.%d %H:%M:%S')
                if start<=t<=end:
                    raw.append((t,float(x['open']),float(x['high']),float(x['low']),float(x['close']),float(x['spread'])))
    raw.sort(); out=[]; cur=None; rows=[]
    for r in raw:
        t,o,h,l,c,s=r; key=t.replace(minute=(t.minute//30)*30,second=0,microsecond=0)
        if cur is None or cur[0]!=key:
            if cur is not None:
                _,o0,h0,c0,c1,_=cur; out.append(Bar(cur[0],o0,h0,cur[3],c1,statistics.median(z[5] for z in rows)))
            cur=[key,o,h,l,c,s]; rows=[r]
        else:
            cur[2]=max(cur[2],h); cur[3]=min(cur[3],l); cur[4]=c; rows.append(r)
    if cur:
        _,o0,h0,c0,c1,_=cur; out.append(Bar(cur[0],o0,h0,c0,c1,statistics.median(z[5] for z in rows)))
    return out

def ema(v,n):
    out=[None]*len(v)
    if len(v)>=n:
        out[n-1]=sum(v[:n])/n; a=2/(n+1)
        for i in range(n,len(v)): out[i]=a*v[i]+(1-a)*out[i-1]
    return out

def atr(bs,n=24):
    tr=[]
    for i,b in enumerate(bs): tr.append(b.h-b.l if i==0 else max(b.h-b.l,abs(b.h-bs[i-1].c),abs(b.l-bs[i-1].c)))
    return ema(tr,n)

def er(closes,n=24):
    out=[None]*len(closes)
    for i in range(n,len(closes)):
        den=sum(abs(closes[j]-closes[j-1]) for j in range(i-n+1,i+1)); out[i]=None if den==0 else abs(closes[i]-closes[i-n])/den
    return out

def floor_lot(x): return max(0.01,math.floor(x/0.01+1e-9)*0.01) if x>=0.01 else 0.0

def annualized(net,equity,days): return (equity/500.0)**(365/max(days,1))-1 if equity>0 else -1.0

_CACHE={}
def metrics(trades,initial_balance,days,balance,maxdd,rejected,diag,record):
    net=sum(t['net'] for t in trades); eq=initial_balance+net
    grid=[t for t in trades if t['module']=='grid']; trend=[t for t in trades if t['module']=='trend']
    return {'net':net,'equity':eq,'annualized':annualized(net,eq,days),'max_dd':maxdd,
            'trades':len(trades),'win_rate':sum(t['net']>0 for t in trades)/len(trades) if trades else 0,
            'rejected':rejected,'grid_trades':len(grid),'trend_trades':len(trend),
            'grid_layer2_rate':sum(t['layers']>=2 for t in grid)/len(grid) if grid else 0,
            'grid_avg_layers':sum(t['layers'] for t in grid)/len(grid) if grid else 0,
            'grid_net':sum(t['net'] for t in grid),'trend_net':sum(t['net'] for t in trend),
            'controller_updates':diag['updates'],'avg_spacing_mult':statistics.mean(diag['spacing']) if diag['spacing'] else 1.0,
            'avg_trend_risk_mult':statistics.mean(diag['trend_risk']) if diag['trend_risk'] else 1.0,
            'trades_detail':trades if record else None,'controller_detail':diag if record else None}

def simulate(bs,p,start_idx=0,end_idx=None,initial_balance=500.0,adaptive=True,record=False):
    end_idx=len(bs)-1 if end_idx is None else end_idx
    if id(bs) not in _CACHE:
        closes=[b.c for b in bs]; _CACHE[id(bs)]=(atr(bs,24),er(closes,24),ema(closes,24),ema(closes,96))
    A,E,fast,slow=_CACHE[id(bs)]
    balance=initial_balance; peak=balance; maxdd=0; basket=[]; trades=[]; rejected=0; i=start_idx+30; cooldown=0; trend_trade=False
    spacing_mult=1.0; trend_risk_mult=1.0; recent_grid=[]; recent_trend=[]
    diag={'updates':0,'spacing':[],'trend_risk':[],'events':[]}
    def quote(b,side,entry): return b.ask if side>0 and entry else b.bid if side>0 else b.bid if entry else b.ask
    def close_basket(ix,reason):
        nonlocal balance,basket,peak,maxdd,cooldown,trend_trade,recent_grid,recent_trend
        if not basket:return
        b=bs[ix]; side=basket[0]['side']; vol=sum(x['vol'] for x in basket); avg=sum(x['entry']*x['vol'] for x in basket)/vol
        ex=quote(b,side,False); net=side*(ex-avg)*CONTRACT*vol; balance+=net
        module='trend' if trend_trade else 'grid'
        tr={'entry_i':basket[0]['i'],'exit_i':ix,'side':side,'volume':vol,'avg_entry':avg,'exit':ex,'net':net,'reason':reason,'layers':len(basket),'module':module,'spacing_mult_at_entry':basket[0].get('spacing_mult',1.0),'trend_risk_mult_at_entry':basket[0].get('trend_risk_mult',1.0)}
        trades.append(tr)
        (recent_trend if module=='trend' else recent_grid).append(tr)
        basket=[]; trend_trade=False; cooldown=p['cooldown']; peak=max(peak,balance); maxdd=max(maxdd,(peak-balance)/max(peak,1e-9))
    def update_controller(ix):
        nonlocal spacing_mult,trend_risk_mult
        if not adaptive or ix%48!=0:return
        old_s,old_t=spacing_mult,trend_risk_mult
        g=recent_grid[-12:]; t=recent_trend[-8:]
        if len(g)>=6:
            l2=sum(x['layers']>=2 for x in g)/len(g)
            loss=sum(x['net']<0 for x in g)/len(g)
            # High layer saturation means the current grid is too narrow; move slowly.
            if l2>0.50: spacing_mult=min(1.40,spacing_mult+0.04)
            elif l2<0.18 and len(g)>=8 and loss<0.60: spacing_mult=max(0.82,spacing_mult-0.025)
            if loss>0.68 and l2>0.35: spacing_mult=min(1.40,spacing_mult+0.025)
        if len(t)>=5:
            tw=sum(x['net']>0 for x in t)/len(t)
            if tw<0.34 or sum(x['net'] for x in t[-3:])<0: trend_risk_mult=max(0.65,trend_risk_mult-0.08)
            elif tw>0.62 and sum(x['net'] for x in t[-5:])>0: trend_risk_mult=min(1.15,trend_risk_mult+0.035)
        if abs(spacing_mult-old_s)>1e-9 or abs(trend_risk_mult-old_t)>1e-9:
            diag['events'].append({'i':ix,'time':bs[ix].t.isoformat(),'spacing_before':old_s,'spacing_after':spacing_mult,'trend_risk_before':old_t,'trend_risk_after':trend_risk_mult,'grid_n':len(g),'trend_n':len(t)})
        diag['updates']+=1; diag['spacing'].append(spacing_mult); diag['trend_risk'].append(trend_risk_mult)
    while i<end_idx:
        b=bs[i]; a=A[i]
        if a is None or E[i] is None or fast[i] is None or slow[i] is None: i+=1; continue
        update_controller(i)
        n=p['breakout_bars']; lo=max(start_idx,i-n)
        prior_hi=max(x.h for x in bs[lo:i]); prior_lo=min(x.l for x in bs[lo:i])
        trend_up=fast[i]>slow[i] and b.c>prior_hi and (a/max(b.c,1e-9))>=p['trend_rv']
        trend_dn=fast[i]<slow[i] and b.c<prior_lo and (a/max(b.c,1e-9))>=p['trend_rv']
        trend=(E[i]>=p['trend_er'] and abs(fast[i]-slow[i])>=p['trend_slope']*a)
        breakout_side=1 if trend_up else -1 if trend_dn else 0
        if basket:
            side=basket[0]['side']; vol=sum(x['vol'] for x in basket); avg=sum(x['entry']*x['vol'] for x in basket)/vol
            adverse=(side>0 and b.l<=avg-p['stop_atr']*a) or (side<0 and b.h>=avg+p['stop_atr']*a)
            target=avg+side*(p['trend_tp_atr'] if trend_trade else p['tp_atr'])*a
            hit_tp=(side>0 and b.h>=target) or (side<0 and b.l<=target)
            if adverse: close_basket(i,'trend_stop' if trend_trade else 'basket_stop'); i+=1; continue
            if hit_tp: close_basket(i,'trend_tp' if trend_trade else 'basket_tp'); i+=1; continue
            if trend_trade and ((side>0 and fast[i]<slow[i]) or (side<0 and fast[i]>slow[i])): close_basket(i,'trend_exit'); i+=1; continue
            if i-basket[0]['i']>=(p['trend_max_hold'] if trend_trade else p['max_hold']): close_basket(i,'max_hold'); i+=1; continue
            if len(basket)<p['max_layers'] and (not trend or (side>0 and fast[i]>slow[i]) or (side<0 and fast[i]<slow[i])):
                next_level=avg-side*p['spacing_atr']*spacing_mult*a
                crossed=(side>0 and b.l<=next_level) or (side<0 and b.h>=next_level)
                if crossed:
                    ex=quote(bs[min(i+1,end_idx)],side,True); risk=p['risk_fraction']*max(balance,0); vol=floor_lot(risk/(p['stop_atr']*a*CONTRACT))
                    if vol>=0.01 and balance>0 and balance-risk>0: basket.append({'i':i+1,'side':side,'entry':ex,'vol':vol,'spacing_mult':spacing_mult,'trend_risk_mult':trend_risk_mult})
                    else: rejected+=1
        if not basket and cooldown<=0:
            z=(b.c-fast[i])/a
            if trend: bias=1 if fast[i]>slow[i] else -1; side=breakout_side
            else: side=1 if z<=-p['entry_z'] else -1 if z>=p['entry_z'] else 0
            if side:
                is_trend=bool(trend and breakout_side); stopdist=(p['trend_stop_atr'] if is_trend else p['stop_atr'])*a
                risk=(p['trend_risk_fraction']*trend_risk_mult if is_trend else p['risk_fraction'])*max(balance,0)
                vol=floor_lot(risk/(stopdist*CONTRACT)); ex=quote(bs[min(i+1,end_idx)],side,True)
                if vol>=0.01 and balance>0 and balance-risk>0:
                    trend_trade=is_trend; basket=[{'i':i+1,'side':side,'entry':ex,'vol':vol,'spacing_mult':spacing_mult,'trend_risk_mult':trend_risk_mult}]
                else: rejected+=1
        cooldown=max(0,cooldown-1); i+=1
    if basket: close_basket(end_idx,'end')
    days=max((bs[end_idx].t-bs[start_idx].t).total_seconds()/86400,1)
    return metrics(trades,initial_balance,days,balance,maxdd,rejected,diag,record)

def idx_month(bs,y,m): return next((i for i,b in enumerate(bs) if b.t.year==y and b.t.month==m),None)
def month_add(y,m,n):
    z=y*12+m-1+n; return z//12,z%12+1

def folds(bs):
    out=[]; y,m=2023,7
    while True:
        tr0=(y,m); va0=month_add(y,m,6); te0=month_add(y,m,9); te2=month_add(*te0,2); te3=month_add(*te0,3)
        if te2[0]*12+te2[1]-1>2025*12+12-1: break
        ids=[idx_month(bs,*q) for q in [tr0,va0,te0,te3]]
        if any(x is None for x in ids): break
        out.append({'train_start':ids[0],'train_end':ids[1]-1,'val_start':ids[1],'val_end':ids[2]-1,'test_start':ids[2],'test_end':ids[3],
          'calendar':{'train':f'{tr0[0]}-{tr0[1]:02d}..{month_add(*va0,-1)[0]}-{month_add(*va0,-1)[1]:02d}','validation':f'{va0[0]}-{va0[1]:02d}..{month_add(*te0,-1)[0]}-{month_add(*te0,-1)[1]:02d}','test':f'{te0[0]}-{te0[1]:02d}..{te2[0]}-{te2[1]:02d}'}})
        y,m=month_add(y,m,3)
    return out

def choose(bs,f):
    grid=[]
    for ez,sp,tp,sl,bo,trv,tts,ttp,trf in itertools.product([0.8,1.0],[0.5,0.7],[0.3,0.5],[1.0,1.5],[8,16],[0.00035,0.0007],[0.8,1.0],[1.5,2.5,3.0],[0.015,0.02,0.03]):
        grid.append({'entry_z':ez,'spacing_atr':sp,'tp_atr':tp,'stop_atr':sl,'trend_er':0.50,'trend_slope':0.55,'trend_rv':trv,'breakout_bars':bo,'trend_stop_atr':tts,'trend_tp_atr':ttp,'trend_max_hold':96,'trend_risk_fraction':trf,'risk_fraction':0.01,'max_layers':2,'max_hold':96,'cooldown':4})
    ranked=[]
    for p in grid:
        tr=simulate(bs,p,f['train_start'],f['train_end'],adaptive=True); va=simulate(bs,p,f['val_start'],f['val_end'],adaptive=True)
        score=0.40*va['annualized']+0.18*tr['annualized']-4.5*max(va['max_dd'],tr['max_dd'])+(0.15 if va['net']>0 else -0.15)+(0.10 if tr['net']>0 else -0.10)-0.000015*max(va['rejected'],tr['rejected'])
        ranked.append((score,p,tr,va))
    ranked.sort(key=lambda x:x[0],reverse=True)
    return ranked[:10]

def clean(x): return {k:v for k,v in x.items() if k not in ('trades_detail','controller_detail')}

def main():
    OUT.mkdir(parents=True,exist_ok=True); REPORT.mkdir(parents=True,exist_ok=True)
    bs=load_m30(); fs=folds(bs); selected=[]; tests=[]; baseline_tests=[]
    for fi,f in enumerate(fs):
        top=choose(bs,f); score,p,tr,va=top[0]
        te=simulate(bs,p,f['test_start'],f['test_end'],adaptive=True,record=True)
        base=simulate(bs,p,f['test_start'],f['test_end'],adaptive=False,record=True)
        selected.append({'fold':fi,'calendar':f['calendar'],'params':p,'train':clean(tr),'validation':clean(va),'selection_score':score,'top_candidates':[{'score':x[0],'params':x[1],'validation':clean(x[3])} for x in top[:5]]})
        tests.append({'fold':fi,'calendar':f['calendar'],'params':p,'adaptive':clean(te),'trades':te['trades_detail'],'controller':te['controller_detail']})
        baseline_tests.append({'fold':fi,'calendar':f['calendar'],'fixed':clean(base)})
    alltr=[t for x in tests for t in x['trades']]; allbase=[x['fixed'] for x in baseline_tests]
    net=sum(t['net'] for t in alltr); eq=500+net; days=(datetime(2026,1,1)-datetime(2023,7,1)).days
    bnet=sum(x['net'] for x in allbase); beq=500+bnet
    summary={'folds':len(fs),'adaptive_test_net':net,'adaptive_test_equity':eq,'adaptive_test_annualized':annualized(net,eq,days),'adaptive_test_trades':len(alltr),'adaptive_test_max_fold_dd':max(x['adaptive']['max_dd'] for x in tests),'fixed_test_net':bnet,'fixed_test_equity':beq,'fixed_test_annualized':annualized(bnet,beq,days),'fixed_test_trades':sum(x['trades'] for x in allbase),'fixed_test_max_fold_dd':max(x['max_dd'] for x in allbase),'target_20pct_met':annualized(net,eq,days)>=0.20}
    p=selected[-1]['params']; h0=idx_month(bs,2026,4); h1=len(bs)-1
    hold=simulate(bs,p,h0,h1,adaptive=True,record=True); hold_fixed=simulate(bs,p,h0,h1,adaptive=False,record=True)
    bridge0=idx_month(bs,2026,1); bridge1=h0
    bridge=simulate(bs,p,bridge0,bridge1,adaptive=True,record=True)
    out={'data_scope':'2023-07..2026-06','training_validation_test_protocol':'6m train / 3m validation / 3m test, step 3m','blank_holdout':'2026-04..2026-06','controller_design':{'grid_layer2_high':'>50% of last 12 grid baskets => spacing +0.04, capped 1.40x','grid_layer2_low':'<18% after at least 8 baskets and loss rate <60% => spacing -0.025, floor 0.82x','trend_weak':'last 8 trend trades win rate <34% or last 3 net negative => trend risk -0.08, floor 0.65x','trend_strong':'last 8 trend trades win rate >62% and last 5 net positive => trend risk +0.035, cap 1.15x','update_interval':'48 bars, about one day','no_holdout_feedback':True},'folds':fs,'selected':selected,'tests':tests,'baseline_tests':baseline_tests,'summary':summary,'bridge_2026Q1':clean(bridge),'holdout':{'calendar':'2026-04..2026-06','adaptive':clean(hold),'fixed':clean(hold_fixed),'trades':hold['trades_detail'],'controller':hold['controller_detail']}}
    (OUT/'ROLLING_RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=['# R12 参数反馈控制器研究报告','',json.dumps({'summary':summary,'bridge_2026Q1':clean(bridge),'holdout':{'adaptive':clean(hold),'fixed':clean(hold_fixed)}},ensure_ascii=False,indent=2),'']
    (REPORT/'R12_FINAL_REPORT.md').write_text('\n'.join(report),encoding='utf-8')
    print(json.dumps({'bars':len(bs),'folds':len(fs),'summary':summary,'bridge_2026Q1':clean(bridge),'holdout':{'adaptive':clean(hold),'fixed':clean(hold_fixed)}},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
