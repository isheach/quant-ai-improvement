from __future__ import annotations
import math
def ema(values, period):
 if period<=0: raise ValueError('period must be positive')
 out=[None]*len(values)
 if len(values)<period:return out
 alpha=2/(period+1); out[period-1]=sum(values[:period])/period
 for i in range(period,len(values)): out[i]=alpha*values[i]+(1-alpha)*out[i-1]
 return out
def atr(high,low,close,period):
 if not(len(high)==len(low)==len(close)):raise ValueError('length mismatch')
 tr=[]
 for i in range(len(close)): tr.append(high[i]-low[i] if i==0 else max(high[i]-low[i],abs(high[i]-close[i-1]),abs(low[i]-close[i-1])))
 return ema(tr,period)
def efficiency_ratio(close,lookback):
 out=[None]*len(close)
 for i in range(lookback,len(close)):
  den=sum(abs(close[j]-close[j-1]) for j in range(i-lookback+1,i+1)); out[i]=None if den==0 else abs(close[i]-close[i-lookback])/den
 return out
def round_lot_down(raw,min_lot,step):
 if raw<min_lot:return 0.0
 return round(max(min_lot,math.floor((raw+1e-12)/step)*step),10)
def risk_usd(stop_distance,value_per_price_unit,lots): return stop_distance*value_per_price_unit*lots
