"""Deterministic synthetic DATA GENERATOR. NEVER represents real sportsbook odds."""
from datetime import datetime,timezone,timedelta
from pathlib import Path
import math,csv
import numpy as np
from scipy.stats import poisson
from joint_engine import MARKETS

def make(path,conflict=False):
    cap=20
    p=np.arange(cap+1)
    weights=[poisson.pmf(p,m) for m in (10,5,3)]
    for i,w in enumerate(weights):
        w[-1]+=1-w.sum();weights[i]=w/w.sum()
    pg=np.einsum('i,j,k->ijk',*weights)
    P,R,A=np.meshgrid(p,p,p,indexing='ij');cats={'P':P,'R':R,'A':A,'PA':P+A,'PR':P+R,'RA':R+A,'PRA':P+R+A}
    thresholds={'P':[8,10,12],'R':[3,5,7],'A':[2,3,5],
      'PA':[12,15,18],'PR':[13,16,19],'RA':[6,8,11],'PRA':[15,18,20]}
    now=datetime.now(timezone.utc)
    when=(now-timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
    tip=(now+timedelta(hours=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
    quotes=[]
    for m,lines in thresholds.items():
        for k in lines:
            fair=float(pg[cats[m]>=k].sum())
            # One-sided odds have a known margin in this fixture, but real markets do not.
            # Produce paired prices whose normalized probabilities match the synthetic truth.
            price_over=fair*1.06;price_under=(1-fair)*1.06
            # round American odds to nearest integer, standardized odds >= +/- 100
            def dec2american(prob):
                dec=1/prob
                return int(round((dec-1)*100 if dec>=2 else -100/(dec-1)))
            po=dec2american(price_over);pu=dec2american(price_under)
            if conflict and m=='PA' and k==15:po=+400
            quotes.append(dict(event_id='SYN@SYN_2026-10-22',player='Synthetic Player',book='SyntheticBook',market=m,
              line=k-.5,over_odds=po,under_odds=pu,captured_at=when,commence_time=tip,source='SYNTHETIC_TEST_ONLY',source_type='synthetic'))
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,'w',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=list(quotes[0]));wr.writeheader();wr.writerows(quotes)
    return quotes
if __name__=='__main__':make('data/SYNTHETIC_21_PAIR_QUOTES_NOT_REAL.csv')
