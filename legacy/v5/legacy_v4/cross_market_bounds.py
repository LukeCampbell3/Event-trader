#!/usr/bin/env python3
"""Dependence-free valid bounds for P+R/P+A/R+A; marginal estimates are conditional."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from ladder_lasso import load_quotes,implied
ROOT=Path(__file__).resolve().parent
PAIR={'PA':('P','A'),'PR':('P','R'),'RA':('R','A')}

def survival(seq,k):
    if k<=0:return 1.
    if k>=len(seq):return 0.
    return float(seq[k])

def bounds_ge(xs,ys,k):
    # For integer X,Y and any possible dependence:
    # P(X+Y>=k) >= max_t [Sx(t)+Sy(k-t)-1]_+
    # P(X+Y>=k) <= min_t [Sx(t)+Sy(k-t+1)] capped to 1.
    low=0.; high=1.
    for t in range(-len(ys)-1,len(xs)+2):
        low=max(low,survival(xs,t)+survival(ys,k-t)-1)
        high=min(high,survival(xs,t)+survival(ys,k-t+1))
    return max(0.,low),min(1.,high)

def compare(ladder_path,quotes_path,out):
    ladder=pd.read_csv(ladder_path,keep_default_na=False)
    quotes=load_quotes(quotes_path)
    combo=quotes[(quotes.book=='UnidentifiedScreenshotBook')&quotes.market.isin(PAIR)]
    res=[]
    lookup={}
    for (ev,p,m),g in ladder[ladder.book=='bet365'].groupby(['event_id','player','market']):
        lookup[(ev,p,m)]=g.sort_values('threshold_at_least')
    for (ev,p,m,k),g in combo.groupby(['event_id','player','market','k']):
        cat1,cat2=PAIR[m]
        a=lookup.get((ev,p,cat1));b=lookup.get((ev,p,cat2))
        if a is None or b is None:continue
        ka=a.p_over_market_implied_estimate.to_numpy(float)
        kb=b.p_over_market_implied_estimate.to_numpy(float)
        la=a.p_over_model_range_low.to_numpy(float)
        lb=b.p_over_model_range_low.to_numpy(float)
        ua=a.p_over_model_range_high.to_numpy(float)
        ub=b.p_over_model_range_high.to_numpy(float)
        # Create PMFs with top overflow bin, consistent with modeling cap
        pma=-np.diff(np.r_[ka,0]); pmb=-np.diff(np.r_[kb,0]);pma=pma/pma.sum();pmb=pmb/pmb.sum()
        p_indep=float(np.convolve(pma,pmb)[int(k):].sum())
        p_min,_=bounds_ge(la,lb,int(k));_,p_max=bounds_ge(ua,ub,int(k))
        over=g[g.side=='over'];under=g[g.side=='under']
        if len(over)!=1 or len(under)!=1:continue
        q_over=implied(over.iloc[0].odds);q_under=implied(under.iloc[0].odds)
        fair=q_over/(q_over+q_under)
        res.append({'event_id':ev,'player':p,'market':m,'line':float(g.line.iloc[0]),'published_over_odds':str(over.iloc[0].odds),'published_under_odds':str(under.iloc[0].odds),'screenshot_vigfree_over':round(float(fair),5),'independence_scenario_p_over':round(p_indep,5),'correlation_free_lower_conditional':round(p_min,5),'correlation_free_upper_conditional':round(p_max,5),'over_break_even':round(q_over,5),'under_break_even':round(q_under,5),'over_worstcase_roi_conditional':round(p_min/ q_over-1,5),'under_worstcase_roi_conditional':round((1-p_max)/q_under-1,5),'decision':'NOT_VERIFIED_DIFFERENT_SOURCE_UNSYNCHRONIZED_AND_ASSUMED_MARGINS'})
    d=pd.DataFrame(res)
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    d.to_csv(out,index=False)
    summary={'pairs_evaluated':len(d),'min_conditional_roi_over_positive_count':int((d.over_worstcase_roi_conditional>0).sum()) if len(d) else 0,'min_conditional_roi_under_positive_count':int((d.under_worstcase_roi_conditional>0).sum()) if len(d) else 0,'certified_executable_edges':0,'note':'Marginals estimated using a price-margin model from DIFFERENT book and unknown capture synchronization. Bounds are dependency-free conditional on those marginals, NOT verified confidence bounds on true probabilities or actionable bets.'}
    (Path(out).parent/'cross_market_summary.json').write_text(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    print(json.dumps(compare(ROOT/'results/inferred_full_ladders.csv',ROOT/'data/archived_published_quotes_2026-10-20.csv',ROOT/'results/cross_market_combo_bounds.csv'),indent=2))
