from __future__ import annotations
import csv,json,math,hashlib,sys
from dataclasses import dataclass,asdict
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT.parent/'旧量化策略/31代数据/eva_data/eva_data/XAUUSDm/m1'
PROTOCOL='R2.1-P4'
POINT=0.001; CONTRACT=100.0; LOT=0.01; ACCOUNT=500.0
START=datetime(2023,1,1); END=datetime(2024,5,31,23,59,59)
@dataclass
class Bar: t:datetime; o:float; h:float; l:float; c:float; spread_pts:float

def load_m30():
 rows=[]
 for y,m in [(2023,m) for m in range(1,13)]+[(2024,m) for m in range(1,6)]:
  p=DATA/f'{y:04d}-{m:02d}.csv'
  with p.open(newline='',encoding='utf-8-sig') as f:
   for x in csv.DictReader(f):
    t=datetime.strptime(x['time_iso'],'%Y.%m.%d %H:%M:%S')
    if not(START<=t<=END): continue
    rows.append((t,float(x['open']),float(x['high']),float(x['low']),float(x['close']),float(x['spread'])))
 rows.sort(key=lambda z:z[0]); out=[]; cur=None
 for t,o,h,l,c,s in rows:
  key=t.replace(minute=(t.minute//30)*30,second=0)
  if cur is None or cur[0]!=key:
   if cur: out.append(Bar(*cur))
   cur=[key,o,h,l,c,s]
  else:
   cur[2]=max(cur[2],h); cur[3]=min(cur[3],l); cur[4]=c; cur[5]=s
 if cur: out.append(Bar(*cur))
 return out

def atr(bs,n=14):
 tr=[]
 for i,b in enumerate(bs): tr.append(b.h-b.l if i==0 else max(b.h-b.l,abs(b.h-bs[i-1].c),abs(b.l-bs[i-1].c)))
 out=[None]*len(bs)
 if len(tr)>=n:
  out[n-1]=sum(tr[:n])/n
  for i in range(n,len(tr)): out[i]=(out[i-1]*(n-1)+tr[i])/n
 return out

def sma(v,n,i): return sum(v[i-n+1:i+1])/n if i>=n-1 else None
def sma_series(v,n):
 o=[None]*len(v)
 if len(v)>=n:
  q=sum(v[:n]); o[n-1]=q/n
  for i in range(n,len(v)): q+=v[i]-v[i-n]; o[i]=q/n
 return o
def ema(v,n):
 o=[None]*len(v)
 if len(v)>=n:
  o[n-1]=sum(v[:n])/n; a=2/(n+1)
  for i in range(n,len(v)): o[i]=a*v[i]+(1-a)*o[i-1]
 return o
def er(v,n,i):
 if i<n:return None
 den=sum(abs(v[j]-v[j-1]) for j in range(i-n+1,i+1)); return None if den==0 else abs(v[i]-v[i-n])/den

def pnl(side,entry,exit,lot=LOT): return side*(exit-entry)*CONTRACT*lot
def spread_cost(b,lot=LOT): return b.spread_pts*POINT*CONTRACT*lot
def make_trade(side,entry,exit,entry_i,exit_i,reason,stop_risk,cost):
 gross=pnl(side,entry,exit); net=gross-cost; return {'side':side,'entry':entry,'exit':exit,'entry_i':entry_i,'exit_i':exit_i,'gross':gross,'cost':cost,'net':net,'reason':reason,'initial_stop_risk':stop_risk,'r':net/stop_risk if stop_risk else None}

def simulate(bs,kind,param):
 closes=[b.c for b in bs]; A=atr(bs); trades=[]; pos=None; maxhold=48
 ema_cache={n:ema(closes,n) for n in (12,24,36,48,72)}
 sma_cache={n:sma_series(closes,n) for n in (24,48)}
 def close(i,price,reason):
  nonlocal pos
  if pos is not None:
   b=bs[i]; cost=pos['entry_cost']+spread_cost(b); trades.append(make_trade(pos['side'],pos['entry'],price,pos['entry_i'],i,reason,pos['risk'],cost)); pos=None
 for i in range(30,len(bs)-1):
  b=bs[i]; nxt=bs[i+1]
  if pos:
   stop=pos['stop']; age=i-pos['entry_i']
   if (pos['side']==1 and b.l<=stop) or (pos['side']==-1 and b.h>=stop): close(i,stop,'stop'); continue
   if age>=maxhold: close(i,b.c,'max_hold'); continue
   if kind=='T':
    f=ema_cache[param['fast']]; s=ema_cache[param['slow']]
    if f[i] and s[i] and ((pos['side']==1 and f[i]<s[i]) or (pos['side']==-1 and f[i]>s[i])): close(i,b.c,'reverse')
   elif kind=='MR':
    ma=sma_cache[param['mean']][i]
    if ma and ((pos['side']==1 and b.c>=ma) or (pos['side']==-1 and b.c<=ma)): close(i,b.c,'mean_exit')
  if pos is None and A[i] and A[i]>0:
   side=None; stopdist=None
   if kind=='T':
    f=ema_cache[param['fast']]; s=ema_cache[param['slow']]
    if f[i] and s[i] and f[i]>s[i]: side=1
    elif f[i] and s[i] and f[i]<s[i]: side=-1
    stopdist=A[i]*param['sl']; stopdist=stopdist if side else None
   elif kind=='MR':
    ma=sma_cache[param['mean']][i]; dev=(b.c-ma)/A[i] if ma else 0
    if dev<=-param['dev']: side=1
    elif dev>=param['dev']: side=-1
    stopdist=A[i]*param['sl'] if side else None
   elif kind=='G':
    ma=sma_cache[param['mean']][i]; dev=(b.c-ma)/A[i] if ma else 0
    if dev<=-param['entry']: side=1
    elif dev>=param['entry']: side=-1
    stopdist=A[i]*param['basket_sl'] if side else None
   if side and stopdist:
    entry=nxt.o + (b.spread_pts*POINT if side==1 else -b.spread_pts*POINT)
    stop=entry-side*stopdist; risk=abs(stopdist)*CONTRACT*LOT
    pos={'side':side,'entry':entry,'entry_i':i+1,'stop':stop,'risk':risk,'entry_cost':spread_cost(nxt)}
 # close at last close
 if pos: close(len(bs)-1,bs[-1].c,'end')
 return trades

def simulate_grid(bs,param):
 closes=[b.c for b in bs]; A=atr(bs); ma24=sma_series(closes,24); trades=[]; basket=None
 max_layers=param['max_layers']; layer_lot=LOT/max_layers
 for i in range(30,len(bs)-1):
  b=bs[i]; nxt=bs[i+1]
  if basket:
   side=basket['side']; stop=basket['stop']; age=i-basket['first_i']
   stop_hit=(side==1 and b.l<=stop) or (side==-1 and b.h>=stop)
   if stop_hit or age>=48 or (side==1 and b.c>=ma24[i]) or (side==-1 and b.c<=ma24[i]):
    for leg in basket['legs']:
     ex=stop if stop_hit else b.c
     trades.append(make_trade(side,leg['entry'],ex,leg['entry_i'],i,'basket_exit',basket['risk']/max_layers,leg['cost']+spread_cost(b,leg['lot'])))
    basket=None; continue
   dist=A[i]*param['layer_dist'] if A[i] else None
   if dist and len(basket['legs'])<max_layers:
    adverse=(basket['anchor']-b.c) if side==1 else (b.c-basket['anchor'])
    if adverse>=dist*len(basket['legs']):
     ent=nxt.o+(b.spread_pts*POINT if side==1 else -b.spread_pts*POINT)
     basket['legs'].append({'entry':ent,'entry_i':i+1,'cost':spread_cost(nxt,layer_lot),'lot':layer_lot}); basket['anchor']=ent
  if basket is None and A[i] and ma24[i]:
   dev=(b.c-ma24[i])/A[i]; side=1 if dev<=-param['entry'] else -1 if dev>=param['entry'] else None
   if side:
    dist=A[i]*param['basket_sl']; entry=nxt.o+(b.spread_pts*POINT if side==1 else -b.spread_pts*POINT)
    basket={'side':side,'first_i':i+1,'stop':entry-side*dist,'risk':dist*CONTRACT*LOT,'anchor':entry,'legs':[{'entry':entry,'entry_i':i+1,'cost':spread_cost(nxt,layer_lot),'lot':layer_lot}]}
 if basket:
  b=bs[-1]
  for leg in basket['legs']: trades.append(make_trade(basket['side'],leg['entry'],b.c,leg['entry_i'],len(bs)-1,'end',basket['risk']/max_layers,leg['cost']+spread_cost(b,leg['lot'])))
 return trades

def controller(bs,level):
 closes=[b.c for b in bs]; A=atr(bs); states=[]
 for i,b in enumerate(bs):
  e=er(closes,24,i); a=A[i]
  if e is None or a is None: states.append('NO_TRADE')
  elif e>=level and b.spread_pts*POINT < a*0.5: states.append('TREND')
  elif e<=level*0.65 and b.spread_pts*POINT < a*0.5: states.append('RANGE')
  else: states.append('NO_TRADE')
 return states

def simulate_controller(bs,level):
 # deterministic one-position controller: T or MR entry/exit rules, no overlap
 closes=[b.c for b in bs]; A=atr(bs); states=controller(bs,level); trades=[]; pos=None
 ema_cache={n:ema(closes,n) for n in (12,36)}; sma_cache={n:sma_series(closes,n) for n in (24,)}
 for i in range(30,len(bs)-1):
  b=bs[i]; nxt=bs[i+1]
  if pos:
   if (pos['side']==1 and b.l<=pos['stop']) or (pos['side']==-1 and b.h>=pos['stop']):
    ex=pos['stop']; trades.append(make_trade(pos['side'],pos['entry'],ex,pos['entry_i'],i,'stop',pos['risk'],pos['entry_cost']+spread_cost(b))); pos=None
   elif i-pos['entry_i']>=48 or states[i]=='NO_TRADE' or states[i]!=pos['state']:
    ex=b.c; trades.append(make_trade(pos['side'],pos['entry'],ex,pos['entry_i'],i,'state_exit',pos['risk'],pos['entry_cost']+spread_cost(b))); pos=None
  if pos is None and A[i] and states[i] in ('TREND','RANGE'):
   side=None
   if states[i]=='TREND':
    f=ema_cache[12]; s=ema_cache[36]; side=1 if f[i] and s[i] and f[i]>s[i] else -1 if f[i] and s[i] and f[i]<s[i] else None
   else:
    ma=sma_cache[24][i]; dev=(b.c-ma)/A[i] if ma else 0; side=1 if dev<=-1.0 else -1 if dev>=1.0 else None
   if side:
    dist=A[i]*1.8; entry=nxt.o+(b.spread_pts*POINT if side==1 else -b.spread_pts*POINT)
    pos={'side':side,'entry':entry,'entry_i':i+1,'stop':entry-side*dist,'risk':dist*CONTRACT*LOT,'entry_cost':spread_cost(nxt),'state':states[i]}
 if pos:
  b=bs[-1]; trades.append(make_trade(pos['side'],pos['entry'],b.c,pos['entry_i'],len(bs)-1,'end',pos['risk'],pos['entry_cost']+spread_cost(b)))
 return trades,states

def summary(trades):
 net=sum(t['net'] for t in trades); gross=sum(t['net'] for t in trades if t['net']>0); loss=-sum(t['net'] for t in trades if t['net']<0); eq=ACCOUNT; peak=ACCOUNT; dd=0
 for t in trades:
  eq+=t['net']; peak=max(peak,eq); dd=max(dd,(peak-eq)/peak)
 return {'trades':len(trades),'net_profit':round(net,4),'final_equity':round(eq,4),'max_drawdown':round(dd,6),'win_rate':round(sum(t['net']>0 for t in trades)/len(trades),6) if trades else None,'profit_factor':round(gross/loss,6) if loss else None,'cost_total':round(sum(t['cost'] for t in trades),4),'r_sum':round(sum(t['r'] for t in trades if t['r'] is not None),6),'top10_winner_contribution':round(sum(sorted([t['net'] for t in trades if t['net']>0],reverse=True)[:10])/net,6) if net else None}

def main(outdir):
 bs=load_m30(); outdir.mkdir(parents=True,exist_ok=True); base={'bars_m30':len(bs),'first':bs[0].t.isoformat(),'last':bs[-1].t.isoformat()}
 configs=[]
 for fast,slow in [(12,36),(24,72)]:
  for sl in [1.5,2.5]: configs.append((f'T_F{fast}_S{slow}_SL{sl}','T',{'fast':fast,'slow':slow,'sl':sl}))
 for mean,dev in [(24,1.0),(24,1.5),(48,1.0),(48,1.5)]: configs.append((f'MR_M{mean}_D{dev}','MR',{'mean':mean,'dev':dev,'sl':1.5}))
 for entry,max_layers in [(1.0,2),(1.0,3),(1.5,2),(1.5,3)]: configs.append((f'G_E{entry}_L{max_layers}','G',{'mean':24,'entry':entry,'basket_sl':3.0,'layer_dist':0.75,'max_layers':max_layers}))
 for name,level in [('C1',0.25),('C2',0.35),('C3',0.45)]: configs.append((name,'C',{'level':level}))
 results=[]
 for rid,kind,param in configs:
  if kind=='C': trades,states=simulate_controller(bs,param['level']); extra={'state_counts':{x:states.count(x) for x in ('TREND','RANGE','NO_TRADE')}}
  elif kind=='G': trades=simulate_grid(bs,param); extra={}
  else: trades=simulate(bs,kind,param); extra={}
  r={'run_id':rid,'protocol_version':PROTOCOL,'strategy_id':kind,'parameter':param,'data_scope':'2023-01-01..2024-05-31','engine':'local_m1_to_m30_bar_engine','cost_model':'spread_from_bar_spread_only; commission_and_swap_NOT_COMPUTABLE','execution_state':'COMPLETED','research_conclusion':'INCONCLUSIVE_COST_INCOMPLETE','summary':summary(trades),**extra}
  (outdir/rid).mkdir(exist_ok=True)
  (outdir/rid/'run.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  with (outdir/rid/'trades.jsonl').open('w',encoding='utf-8') as f:
   for t in trades:f.write(json.dumps(t,separators=(',',':'))+'\n')
  (outdir/rid/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); results.append(r)
 (outdir/'RESULTS.json').write_text(json.dumps({'base':base,'runs':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'bars':len(bs),'runs':len(results),'results':[{'run_id':r['run_id'],**r['summary']} for r in results]},ensure_ascii=False,indent=2))
if __name__=='__main__': main(Path(sys.argv[1]))
