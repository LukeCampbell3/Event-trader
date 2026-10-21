"""v7 FULL finite experiment: real HTML excerpts + controlled lead/lag simulation.
Never reports the synthetic experiment as a real profitable sports market.
"""
from __future__ import annotations
import csv, json, math, random
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from shoal import load_quotes, normalize_sportsbook, price_screen, monotone_ladders, save_csv

HERE=Path(__file__).resolve().parent
D=HERE/'data';O=HERE/'results';O.mkdir(parents=True,exist_ok=True)

def real_moneyline():
    rows=load_quotes(D/'PUBLIC_EXCERPT_UNSYNCHRONIZED_moneyline.csv')
    fair=normalize_sportsbook(rows)
    tabs=[]
    for outcome in ['ATL','ORL']:
        vals=[(src,p) for (game,market,src,t,oc),p in fair.items() if oc==outcome]
        b=next(x for x in rows if x.source=='Kalshi' and x.outcome==outcome)
        pmin=min(p for src,p in vals);pmax=max(p for src,p in vals);pmean=sum(p for src,p in vals)/len(vals)
        tabs.append(dict(game=b.game,outcome=outcome,source='Kalshi',published_bid=b.bid,published_ask=b.ask,
                         reference_books=len(vals),fair_range_low=pmin,fair_range_high=pmax,mean_fair=pmean,
                         edge_before_fees=pmean-b.ask,low_edge_with_2pp_robust_pad=pmin-.02-b.ask,
                         low_edge_with_assumed_2c_fee=pmin-.02-b.ask-.02,
                         website_prices_not_simultaneously_timestamped=True,live_executable=False,
                         real_positive_ev_proven=False))
    save_csv(O/'oct21_public_moneyline_comparison.csv',tabs)
    no_quotes=price_screen(rows,'2026-10-21T11:00:00Z')
    return tabs,len([x for x in no_quotes if x['conditional_screen']])


def features(lower, upper, middle):
    l,u=lower,upper
    x1,x2,y= l['threshold'],u['threshold'],middle['threshold']
    pl,pu=l['p'],u['p']
    alpha=(y-x1)/(x2-x1)
    logit_est=float(expit((1-alpha)*logit(pl)+alpha*logit(pu)))
    line_est=pl*(1-alpha)+pu*alpha
    # Only neighbors, no target. Lasso corrects the logit curve.
    X=[alpha,alpha*(1-alpha),pl,pu,pu-pl,(pu-pl)/(x2-x1),x2-x1,
       1. if l['stat']=='P' else 0.,1. if l['stat']=='R' else 0.]
    return np.array(X),line_est,logit_est


def ladder_reconstruction():
    with open(D/'PUBLIC_INDICATIVE_KALSHI_LADDERS_OCT21.csv') as f:
        quotes=list(csv.DictReader(f))
    for r in quotes:r['threshold']=int(r['threshold']);r['p']=float(r['p'])
    audits=monotone_ladders(quotes)
    save_csv(O/'ladder_monotonicity.csv',audits)
    groups=defaultdict(list)
    for r in quotes:groups[(r['player'],r['stat'])].append(r)
    records=[]
    for (player,stat), ladder in groups.items():
        r=sorted(ladder,key=lambda x:x['threshold'])
        for i in range(1,len(r)-1):
            x,linear,baseline=features(r[i-1],r[i+1],r[i])
            records.append(dict(player=player,stat=stat,threshold=r[i]['threshold'],observed=r[i]['p'],
                                linear=linear,logit_interpolation=baseline,X=x))
    X=np.stack([r['X'] for r in records]);y=np.array([r['observed']-r['logit_interpolation'] for r in records])
    group_labels=np.array([r['player'] for r in records]); preds=np.full(len(records),np.nan)
    gkf=GroupKFold(n_splits=min(5,len(set(group_labels))))
    alpha_chosen=[]
    for train,test in gkf.split(X,y,group_labels):
        # Fixed regularization grid selected using grouped CV on training data.
        gtrain=group_labels[train]; folds=min(3,len(set(gtrain)))
        if folds>=2:
            inner=GroupKFold(folds)
            # Pipeline to standardize inside fit; our fold splits are group-safe.
            model=LassoCV(alphas=np.logspace(-5,-1,16),cv=list(inner.split(X[train],y[train],gtrain)),
                           max_iter=10000,random_state=41)
            scale=StandardScaler().fit(X[train]);model.fit(scale.transform(X[train]),y[train]);
            preds[test]=np.clip([records[k]['logit_interpolation'] for k in test] + model.predict(scale.transform(X[test])),0,1)
            alpha_chosen.append(float(model.alpha_))
        else:preds[test]=[records[k]['logit_interpolation'] for k in test]
    for i,r in enumerate(records):
        r['lasso_group_out']=preds[i];del r['X']
    save_csv(O/'oct21_ladder_holdouts.csv',records)
    # Cluster-bootstrap by player, not by quote: repeated thresholds are dependent.
    by_player=defaultdict(list)
    for r in records:by_player[r['player']].append(r)
    rng=np.random.default_rng(314159)
    players=list(by_player);delta=[]
    for rep in range(2500):
        batch=[r for p in rng.choice(players,len(players),replace=True) for r in by_player[p]]
        diff=np.mean([abs(r['observed']-r['logit_interpolation'])-
                      abs(r['observed']-r['lasso_group_out']) for r in batch])
        delta.append(diff)
    delta_ci=[round(float(v)*100,3) for v in np.quantile(delta,[.025,.975])]
    err={label:float(np.mean([abs(r['observed']-r[label]) for r in records])) for label in ['linear','logit_interpolation','lasso_group_out']}
    return dict(published_indicator_thresholds=len(quotes),ladders=len(groups),interior_holdouts=len(records),
       monotonic_violations=sum(a['violations'] for a in audits),
       price_indicator_mae_pp={k:round(v*100,3) for k,v in err.items()},
       lasso_alphas=alpha_chosen,lasso_mae_gain_95pct_cluster_bootstrap_ci_pp=delta_ci,
       game_holdout_count=0,
       limitation='One game, group-held-out players; not out-of-game and not outcomes calibration')


def fish_simulation(seed=175, N=5000, lag_steps=3, controls=False):
    """Out-of-sample frozen signal test on an explicitly ARTIFICIAL market.
    Underlying 'true' fair p is hidden from the policy; revealed only for scoring.
    Synthetic venue Kalshi/Poly update quickly, slow book is stale by lag_steps.
    """
    rng=np.random.default_rng(seed);cand=[]
    decision_t=25;final_t=37
    for i in range(N):
        p=np.clip(.50+rng.normal(0,.10),.20,.80)
        truth=[float(p)]
        for t in range(final_t+1):truth.append(float(np.clip(truth[-1]+rng.normal(0,.015),.05,.95)))
        # Sources have independent quote noise; middle/high is unavailable to policy.
        a=np.clip(truth[decision_t]+rng.normal(0,.003),.01,.99)
        b=np.clip(truth[decision_t]+rng.normal(0,.003),.01,.99)
        stale=np.clip(truth[decision_t-lag_steps]+rng.normal(0,.003),.01,.99)
        book_cost=min(.99,stale+.022) # artificial vig
        # Show explicit school-of-fish direction/velocity: fast sources moving in same direction,
        # compared with their t-3 values. Need lookback data not outcome.
        a_prev=np.clip(truth[decision_t-3]+rng.normal(0,.003),.01,.99)
        b_prev=np.clip(truth[decision_t-3]+rng.normal(0,.003),.01,.99)
        fast=(a+b)/2;agree=(a>a_prev and b>b_prev)
        disagreement=fast-book_cost
        selected=agree and (disagreement > .028)
        future=truth[final_t]
        realized=int(rng.random()<future)
        cand.append((selected,fast,book_cost,future,realized,disagreement))
    selected=[r for r in cand if r[0]]
    all_count=len(cand)
    if selected:
        realized_roi=float(np.mean([y/cost-1 for sel,fast,cost,truth,y,diff in selected]))
        conditional_roi=float(np.mean([truth/cost-1 for sel,fast,cost,truth,y,diff in selected]))
        quote_gap=float(np.mean([diff for sel,fast,cost,truth,y,diff in selected]))
        win_rate=float(np.mean([y for sel,fast,cost,truth,y,diff in selected]))
    else:realized_roi=conditional_roi=quote_gap=win_rate=None
    return dict(synthetic_only=True,scenario='lagged_book' if lag_steps else 'no_lag_negative_control',
       n_independent_games=N,selected=len(selected),selection_rate=len(selected)/all_count,
       hit_rate=win_rate,mean_true_expected_roi=conditional_roi,realized_roi=realized_roi,
       mean_fast_minus_slow_book_pp=100*quote_gap if quote_gap is not None else None,
       policy_frozen_before_outcomes=True)


def main():
    money, certified=real_moneyline(); ladder=ladder_reconstruction()
    a=fish_simulation(lag_steps=3);b=fish_simulation(lag_steps=0)
    repeat=[fish_simulation(seed=400+i,N=2500,lag_steps=3) for i in range(10)]
    save_csv(O/'SYNTHETIC_seed_stability_not_real.csv',repeat)
    # Existing archive cannot be genuine intraday velocity study; all missing capture timestamps.
    archived=pd.read_csv(HERE/'legacy_v5'/'data'/'archived_oct20_unsynchronized.csv')
    fields=list(archived.columns)
    stale=int(archived['captured_at'].isna().sum()) if 'captured_at' in fields else len(archived)
    result={'sample':'Oct 21 published ATL-ORL indicative excerpts + Oct 20 archival checks',
            'real_book_pairs':5,'real_predmarket_bid_ask_indicators':2,
            'usable_synchronized_moneyline_pairs':0,'timestamp_qualified_true_edge_selections':certified,
            'real_moneyline':money,'kalshi_ladder_diagnostics':ladder,
            'historical_replay_archive_rows':len(archived),'archive_timestamp_missing_rows':stale,
            'real_leadlag_tests_valid':0,'synthetic_lead_lag_positive_control':a,'synthetic_negative_control':b,
            'SYNTHETIC_mean_true_roi_repeated':float(np.mean([x['mean_true_expected_roi'] for x in repeat if x['selected']])),
            'SYNTHETIC_realized_roi_range_repeated':[float(np.min([x['realized_roi'] for x in repeat if x['selected']])),float(np.max([x['realized_roi'] for x in repeat if x['selected']]))],
            'real_venue_arb_confirmed':0,'real_positive_ev_confirmed':0}
    (O/'RESULTS.json').write_text(json.dumps(result,indent=2,default=float));print(json.dumps(result,indent=2,default=float))

if __name__=='__main__':main()
