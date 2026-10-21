#!/usr/bin/env python3
"""Market-only cross-family probability bounds for integer NBA stats.

Observed bookmaker prices form probability constraints; inferred prices NEVER do.
Bounds do not assume points/rebounds/assists independence. Central estimates
use an expressly model-dependent entropy tilt, NOT a proof of a true edge.
"""
from __future__ import annotations
import argparse, json, hashlib, math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import linprog, minimize
from scipy.special import logsumexp, logit, expit
from scipy.interpolate import PchipInterpolator
from scipy.stats import norm

MARKETS = {'P': (0,), 'R': (1,), 'A': (2,), 'PA': (0,2), 'PR': (0,1), 'RA': (1,2), 'PRA': (0,1,2)}
PRIOR_MEANS=(23.,7.,5.)


def implied(odd: Any)->float:
    x=float(str(odd).replace('+',''))
    if not math.isfinite(x) or abs(x)<100:raise ValueError(f'Invalid American odds: {odd}')
    return 100/(x+100) if x>0 else -x/(100-x)


def to_decimal(odd: Any)->float:
    return 1/implied(odd)


def american_from_implied(p:float)->str:
    if not 0<p<1: return ''
    decimal=1/p
    return f'+{round((decimal-1)*100)}' if decimal>=2 else str(round(-100/(decimal-1)))


def parse_time(t: Any):
    if t is None or str(t).strip() in ('','nan','NaT'):return None
    try:
        dt=datetime.fromisoformat(str(t).replace('Z','+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError,TypeError):return None


def _limit(line):
    x=float(line)
    if x<0 or abs(x*2-round(x*2))>1e-8 or abs(x-math.floor(x)-.5)>1e-8:raise ValueError('Expected nonnegative half-integer thresholds')
    return int(math.floor(x)+1)

@dataclass(frozen=True)
class Quote:
    event_id:str
    player:str
    book:str
    market:str
    line:float
    over:float|None
    under:float|None
    captured_at:str
    commence_time:str
    source:str
    provenance:str
    @property
    def k(self):return _limit(self.line)
    @property
    def key(self):return (self.event_id,self.player,self.book,self.market,self.line)


def read_quotes(file: str|Path)->tuple[list[Quote],list[str]]:
    df=pd.read_csv(file,keep_default_na=False)
    needed={'event_id','player','book','market','line'}
    if not needed.issubset(df):raise ValueError(f'Missing fields: {needed-set(df)}')
    long='side' in df and 'odds' in df
    quotes=[];issues=[]
    if long:
        groupby=['event_id','player','book','market','line']
        grouped=df.groupby(groupby,dropna=False,sort=True)
    else:
        grouped=[(None,df.iloc[[i]]) for i in range(len(df))]
    for _,g in grouped:
        first=g.iloc[0]
        m=str(first['market']).upper().strip()
        if m not in MARKETS:continue
        try:
            line=float(first['line']);_limit(line)
            if long:
                odds={}
                for _,r in g.iterrows():
                    side=str(r['side']).lower().strip()
                    if side not in ('over','under'):raise ValueError('unsupported side')
                    if side in odds:raise ValueError('duplicate side / unsplit snapshots')
                    odds[side]=str(r['odds'])
                over=implied(odds['over']) if 'over' in odds else None
                under=implied(odds['under']) if 'under' in odds else None
            else:
                over=implied(first['over_odds']) if str(first.get('over_odds','')).strip() else None
                under=implied(first['under_odds']) if str(first.get('under_odds','')).strip() else None
            if over is None and under is None:raise ValueError('no prices')
            if over is not None and under is not None and not .995<=over+under<=1.5:raise ValueError('invalid overround')
            # Reject differently captured sides within the paired market.
            timestamps={str(x) for x in g.get('captured_at',pd.Series([''])).tolist()}
            if len(timestamps)>1:raise ValueError('sides captured at different times')
            quote=Quote(str(first['event_id']),str(first['player']),str(first['book']),m,line,
              over,under,str(first.get('captured_at','')),str(first.get('commence_time','')),
              str(first.get('source_url',first.get('source',''))),str(first.get('source_type',first.get('line_type',''))))
            quotes.append(quote)
        except (ValueError,TypeError,KeyError) as ex:issues.append(f"{first.get('player','?')}:{m}:{first.get('line','?')}: {ex}")
    return quotes,issues


def sync_status(quotes:list[Quote],asof:str|None=None,max_skew_minutes=15):
    if not quotes:return 'NO_QUOTES'
    timestamps=[parse_time(q.captured_at) for q in quotes]
    if any(t is None for t in timestamps):return 'UNVERIFIED_CAPTURE_TIMESTAMPS'
    if (max(timestamps)-min(timestamps)).total_seconds()>max_skew_minutes*60:return 'UNSYNCHRONIZED_QUOTES'
    commence=[parse_time(q.commence_time) for q in quotes]
    if any(t is None for t in commence):return 'UNKNOWN_TIPOFF_TIME'
    if len({t.isoformat() for t in commence})!=1:return 'TIPOFF_CONFLICT'
    if max(timestamps)>=min(commence):return 'IN_GAME_OR_POSTGAME_QUOTE'
    # For live runs, a synchronized historical snapshot alone is insufficient:
    # the latest quote also must be fresh relative to the current run.
    reference=parse_time(asof) if asof else datetime.now(timezone.utc)
    if reference is None:return 'INVALID_ASOF'
    if max(timestamps)>reference:return 'FUTURE_QUOTES_RELATIVE_TO_ASOF'
    if (reference-max(timestamps)).total_seconds()>max_skew_minutes*60:return 'STALE_SNAPSHOT'
    if asof:
        t=parse_time(asof)
        if not t:return 'INVALID_ASOF'
        if any(x>t for x in timestamps):return 'FUTURE_QUOTES_RELATIVE_TO_ASOF'
        if t>=min(commence):return 'ASOF_AFTER_TIPOFF'
    return 'SYNCHRONIZED_PREGAME'


def constraint(q:Quote,one_sided_margin=.15,paired_margin=.015):
    if q.over is not None and q.under is not None:
        fair=q.over/(q.over+q.under)
        return max(0.,fair-paired_margin),min(1.,fair+paired_margin),fair,'PAIRED_VIG_REMOVAL'
    if q.over is not None:
        return max(0.,q.over/(1+one_sided_margin)),min(1.,q.over),None,'ONE_SIDED_MARGIN_RANGE'
    return max(0.,1-q.under),min(1.,1-q.under/(1+one_sided_margin)),None,'ONE_SIDED_MARGIN_RANGE'


def states_and_indicator(queries:list[Quote]):
    if not queries:raise ValueError('No queries')
    # Exact event-preserving state compression: values >=K can be represented
    # by K for ALL nonnegative sum threshold events with k<=K.
    K=max(q.k for q in queries)
    if (K+1)**3>200000:raise ValueError(f'State count {(K+1)**3:,} exceeds configured safety maximum')
    ax=np.arange(K+1,dtype=np.int16)
    P,R,A=np.meshgrid(ax,ax,ax,indexing='ij')
    flat=[P.ravel(),R.ravel(),A.ravel()]
    def indicator(q):return np.sum([flat[i] for i in MARKETS[q.market]],axis=0)>=q.k
    return flat,indicator,(K+1)**3,K


def build_A(quotes,ind,margin=.15,paired=.015):
    masks=[ind(q) for q in quotes]
    matrix=sparse.csr_matrix(np.stack(masks).astype(np.float64)) if masks else sparse.csr_matrix((0,0))
    intervals=[constraint(q,margin,paired) for q in quotes]
    lo=np.array([v[0] for v in intervals]); hi=np.array([v[1] for v in intervals]);cent=np.array([v[2] if v[2] is not None else (v[0]+v[1])/2 for v in intervals])
    return matrix,lo,hi,cent


def bound_probabilities(A,low,high,c):
    n=c.shape[0]
    one=sparse.csr_matrix(np.ones((1,n)))
    if A.shape[0]:
        aub=sparse.vstack([A,-A],format='csr');bub=np.r_[high,-low]
    else:aub=None;bub=None
    params=dict(A_ub=aub,b_ub=bub,A_eq=one,b_eq=[1.],bounds=(0,None),method='highs')
    lo=linprog(c,**params)
    if not lo.success:return {'status':'CONSTRAINTS_INFEASIBLE','reason':lo.message}
    hi=linprog(-c,**params)
    if not hi.success:return {'status':'CONSTRAINTS_INFEASIBLE','reason':hi.message}
    return {'status':'OK','low':float(lo.fun),'high':float(-hi.fun)}


def observed_marginal_prior(train,flat,margin=.15,paired=.015):
    """Market-derived, regularized product-of-marginals PRIOR ONLY.

    Anchors use only observed singles in train, with holdout family fully
    excluded. Never reintroduce this inferred curve as a probability constraint.
    Returns None if any component is missing/contradictory.
    """
    K=int(max(v.max() for v in flat))
    marginal=[]
    for m,idx,sd in [('P',0,7.),('R',1,3.5),('A',2,2.8)]:
        anchors=sorted((q.k,constraint(q,margin,paired)[2] if q.over is not None and q.under is not None else
                  (constraint(q,margin,paired)[0]+constraint(q,margin,paired)[1])/2)
                       for q in train if q.market==m)
        if not anchors:return None
        xs=np.array([v[0] for v in anchors],dtype=float)
        probs=np.array([v[1] for v in anchors],dtype=float)
        if any(np.diff(xs)<=0) or any(np.diff(probs)>=0):return None
        target=np.arange(K+2,dtype=float)
        if len(xs)==1:
            mu=(xs[0]-.5)-sd*norm.isf(np.clip(probs[0],1e-5,1-1e-5))
            surv=norm.sf((target-.5-mu)/sd)
        else:
            logits=logit(np.clip(probs,1e-6,1-1e-6))
            vals=PchipInterpolator(xs,logits)(np.clip(target,xs[0],xs[-1])) if len(xs)>=3 else np.interp(np.clip(target,xs[0],xs[-1]),xs,logits)
            sl=(logits[1]-logits[0])/(xs[1]-xs[0]);sr=(logits[-1]-logits[-2])/(xs[-1]-xs[-2])
            vals=np.where(target<xs[0],logits[0]+sl*(target-xs[0]),vals)
            vals=np.where(target>xs[-1],logits[-1]+sr*(target-xs[-1]),vals)
            surv=expit(vals)
        surv[0]=1.
        surv=np.minimum.accumulate(np.clip(surv,0,1))
        # Event-preserving compression: the final bin means >=K, not exactly K.
        pmf=np.maximum(0.,surv[:-1]-surv[1:])
        pmf[-1]+=surv[-1]
        pmf/=pmf.sum()
        marginal.append(np.clip(pmf,1e-10,1))
    vals=sum(np.log(marginal[i])[flat[i]] for i in range(3))
    return vals-logsumexp(vals)


def entropy_central(A,cent,flat,prior_means=PRIOR_MEANS,soft_sd=.035,prior_log=None):
    """Explicitly model-dependent, regularized exponential tilt of a broad prior.
    Not a distribution-free or calibrated inference of actual outcomes.
    """
    coords=[v.astype(float) for v in flat]
    if prior_log is not None:
        prior=prior_log.copy()
    else:
        prior=np.zeros(len(coords[0]))
        for a,mean in zip(coords,prior_means):
            std=max(2.5,np.sqrt(mean)*1.8)
            prior-=0.5*((a-mean)/std)**2
        prior-=logsumexp(prior)
    if len(cent)==0:return np.exp(prior)
    def fun(lam):
        weights=prior-A.T.dot(lam)
        logZ=logsumexp(weights)
        prob=np.exp(weights-logZ)
        val=logZ+cent.dot(lam)+0.5*soft_sd**2*(lam@lam)
        grad=cent-A.dot(prob)+soft_sd**2*lam
        return val,grad
    opt=minimize(fun,np.zeros(len(cent)),jac=True,method='L-BFGS-B',options={'maxiter':140,'ftol':1e-10})
    vals=prior-A.T.dot(opt.x)
    return np.exp(vals-logsumexp(vals))


def analyze_group(quotes:list[Quote],*,target_families=('P','R','A','PA','PR','RA','PRA'),margin=.15,paired=.015,asof=None,max_skew_minutes=15,max_targets=200,skip_entropy=False):
    """Leave all observations of target family out; no inferred quotes in LP."""
    status=sync_status(quotes,asof,max_skew_minutes)
    flat,ind,n,K=states_and_indicator(quotes)
    rows=[];constraints_issue=[]
    for market in target_families:
        train=[q for q in quotes if q.market!=market]
        test=[q for q in quotes if q.market==market]
        if not test:continue
        A,lo,hi,cent=build_A(train,ind,margin,paired)
        pcentral=None
        for target in test[:max_targets]:
            c=ind(target).astype(float)
            b=bound_probabilities(A,lo,hi,c)
            if b['status']!='OK':
                constraints_issue.append({'family':market,'reason':b['reason']});continue
            if pcentral is None and not skip_entropy:
                pcentral=entropy_central(A,cent,flat,prior_log=observed_marginal_prior(train,flat,margin,paired))
            p_hat=float(c@pcentral) if pcentral is not None else float('nan')
            desired=constraint(target,margin,paired)
            over_be=target.over if target.over is not None else None
            under_be=target.under if target.under is not None else None
            # Whichever side exists can be candidate; mid fit vs quoted is diagnostic only.
            for side,prob_low,prob_high,be in [
                ('over',b['low'],b['high'],over_be),('under',1-b['high'],1-b['low'],under_be)]:
                if be is None:continue
                worst=prob_low/be-1
                # Research-only unless captured sync; even if synced, markets are assumptions, not true EV proof
                grade=('RESEARCH_SIGNAL_REQUIRES_CONFIRMATION' if worst>.02 and status=='SYNCHRONIZED_PREGAME'
                       else 'NO_ROBUST_PRICE_EDGE' if worst<=.02 else 'UNVERIFIED_PROVENANCE')
                rows.append(dict(event_id=target.event_id,player=target.player,book=target.book,
                  target_market=market,target_line=target.line,side=side,
                  posted_american_odds=american_from_implied(be),quoted_break_even=round(be,6),
                  inferred_p_min=round(prob_low,6),inferred_p_max=round(prob_high,6),
                  market_conditioned_central_estimate=round(p_hat if side=='over' else 1-p_hat,6) if pcentral is not None else '',
                  worst_case_roi_given_market_constraints=round(worst,5),
                  market_implied_target_fair=round(desired[2],6) if desired[2] is not None else '',
                  market_inconsistent_with_withheld_family=bool(desired[2] is not None and (desired[2]<b['low']-paired or desired[2]>b['high']+paired)),
                  fitted_market_constraints=len(train),state_count=n,
                  heldout_family=market,quote_validation=status,classification=grade,
                  probability_interval_is_true_confidence_interval=False,
                  model_warning='Bounds conditional on quote error/margin assumptions, not true win-probability guarantees.'))
    return rows,{'sync_status':status,'state_cap_exact_event_preserving':K,'state_count':n,
                  'test_rows':len(rows),'constraint_issues':constraints_issue,
                  'certified_positive_ev':0}


def run(input_csv,output_dir,*,allow_unsynced=False,margin=.15,paired=.015,asof=None,player=None,book=None,max_groups=None,skip_entropy=False,target_families=('P','R','A','PA','PR','RA','PRA')):
    quotes,parse_issues=read_quotes(input_csv)
    groups={}
    for q in quotes:groups.setdefault((q.event_id,q.player,q.book),[]).append(q)
    all_rows=[];summary=[]
    processed=0
    for k,gg in groups.items():
        if player and player.lower() not in k[1].lower():continue
        if book and book.lower()!=k[2].lower():continue
        if len({q.market for q in gg})<2:continue
        if max_groups is not None and processed>=max_groups:break
        processed+=1
        stat=sync_status(gg,asof)
        if stat!='SYNCHRONIZED_PREGAME' and not allow_unsynced:
            summary.append({'group':k,'sync_status':stat,'status':'SKIPPED_UNVERIFIED'});continue
        try:
            rows,diag=analyze_group(gg,asof=asof,margin=margin,paired=paired,skip_entropy=skip_entropy,target_families=target_families)
            all_rows.extend(rows)
            summary.append({'group':k,**diag})
        except Exception as e:
            summary.append({'group':k,'status':'ENGINE_FAILURE','reason':str(e)})
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    columns=['event_id','player','book','target_market','target_line','side','quoted_break_even','inferred_p_min','inferred_p_max','market_conditioned_central_estimate','worst_case_roi_given_market_constraints','market_inconsistent_with_withheld_family','fitted_market_constraints','heldout_family','quote_validation','classification','posted_american_odds','market_implied_target_fair']
    pd.DataFrame(all_rows).reindex(columns=columns).to_csv(out/'family_holdout_bounds.csv',index=False)
    audit={'data_type':'ARCHIVED_REPLAY' if allow_unsynced else 'SYNCHRONIZED_PROSPECTIVE_INPUT','quote_rows':len(quotes),'parse_issues':parse_issues,'group_audits':summary,
      'results':len(all_rows),'conditional_positive_research_signals':sum(r['worst_case_roi_given_market_constraints']>.02 for r in all_rows),
      'verified_executable_bets':0,
      'interpretation':'No true EV guarantee from sportsbook-implied prices. No new alternate line may be counted as an independent constraint unless actually quoted and synchronized.'}
    (out/'audit.json').write_text(json.dumps(audit,indent=2,default=str))
    return audit


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--quotes',required=True);p.add_argument('--output',default='results');p.add_argument('--allow-unsynced-research',action='store_true')
    p.add_argument('--one-sided-max-margin',type=float,default=.15)
    p.add_argument('--paired-probability-tolerance',type=float,default=.015)
    p.add_argument('--asof',default=None)
    p.add_argument('--player',default=None);p.add_argument('--book',default=None)
    p.add_argument('--max-groups',type=int,default=None)
    p.add_argument('--skip-entropy',action='store_true',help='Bounds only, faster')
    p.add_argument('--target-markets',default='P,R,A,PA,PR,RA,PRA')
    a=p.parse_args()
    result=run(a.quotes,a.output,allow_unsynced=a.allow_unsynced_research,
      margin=a.one_sided_max_margin,paired=a.paired_probability_tolerance,asof=a.asof,player=a.player,book=a.book,max_groups=a.max_groups,skip_entropy=a.skip_entropy,target_families=tuple(x.strip() for x in a.target_markets.split(',')))
    print(json.dumps({'quote_rows':result['quote_rows'],'results':result['results'],
      'research_signals':result['conditional_positive_research_signals'],
      'executable_bets':result['verified_executable_bets']},indent=2))
if __name__=='__main__':main()
