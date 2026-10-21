#!/usr/bin/env python3
"""Market-implied NBA odds ladder reconstruction and held-out-quote Lasso benchmark.

Does NOT model actual game outcomes or identify verified profitable wagers.
Does NOT invent executable sportsbook prices for inferred probabilities.
Does NOT mix sportsbooks/timestamps in a single market ladder.
"""
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator
from scipy.optimize import least_squares
from scipy.special import expit, logit
from scipy.stats import norm
from sklearn.linear_model import Lasso
from sklearn.model_selection import GroupKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error

MARKETS = {'P':100,'R':46,'A':36,'3PM':24,'PA':120,'PR':130,'RA':70,'PRA':180}
FEATURE_NAMES=['base_logit','left_logit','right_logit','logit_drop','interval_width','fraction','fraction_sq','fraction_symmetry','left_threshold','right_threshold','market_P','market_R','market_A','market_3PM']

def decimal_odds(s):
    v = float(str(s).replace(',','').strip())
    if not math.isfinite(v) or abs(v)<100:raise ValueError(f'bad American odds: {s}')
    return 1 + v / 100 if v > 0 else 1 + 100 / (-v)

def implied(s):return 1 / decimal_odds(s)

def load_quotes(path):
    df=pd.read_csv(path, keep_default_na=False)
    needed={'event_id','player','book','market','line','side','odds'}
    if not needed.issubset(df.columns):raise ValueError(f'Missing columns {needed-set(df.columns)}')
    df=df[df.market.isin(MARKETS)&df.side.isin(['over','under'])].copy()
    df['line']=pd.to_numeric(df.line)
    df['k']=np.floor(df.line.to_numpy(dtype=float)+.50001).astype(int)
    df['raw_implied']=df.odds.map(implied)
    # Keep explicitly archived source row; no fabricated current quotes.
    df['group_id']=df.event_id+'|'+df.player+'|'+df.book+'|'+df.market
    return df

def group_knots(g, vig=0.06, wide=0.12):
    # Expect no repeated same-side threshold in the supplied snapshot
    ov=g[g.side=='over'].sort_values('k')
    if ov.k.duplicated().any():raise ValueError('Repeated over quotes: snapshots must be disambiguated by timestamp')
    pairs=[]
    for row in ov.itertuples():
        under=g[(g.side=='under')&(g.k==row.k)]
        if len(under)==1:
            raw_under=float(under.raw_implied.iloc[0]); q=float(row.raw_implied)
            p=q/(q+raw_under)
            method='paired_vig_free'
            lo=max(1e-5,p-.01);hi=min(.99999,p+.01) # *assumed* quote reliability, not confidence intervals
        else:
            q=float(row.raw_implied)
            p=q/(1+vig)
            method='one_sided_margin_assumption'
            lo=q/(1+wide);hi=q # optional assumed margin from 0 to 12%, not statistical CI
        pairs.append({'k':int(row.k),'p':float(p),'lo':float(lo),'hi':float(hi),'raw_p':float(row.raw_implied),'anchor_type':method,'odds':str(row.odds)})
    return pairs

def check_order(knots,eps=1e-8):
    return all(b['raw_p']<a['raw_p']+eps for a,b in zip(knots[:-1],knots[1:]))

def logit_curve(xs,probs,ks,method='pchip'):
    x=np.asarray(xs,dtype=float);y=logit(np.clip(probs,1e-8,1-1e-8));k=np.asarray(ks,dtype=float)
    if len(x)<2:raise ValueError('At least 2 knots required')
    if np.any(np.diff(y)>=0):raise ValueError('Nonmonotone logit anchor sequence')
    if method=='pchip' and len(x)>=3:
        intr=PchipInterpolator(x,y,extrapolate=False)(np.clip(k,x[0],x[-1]))
    else:
        intr=np.interp(np.clip(k,x[0],x[-1]),x,y)
    left_slope=min(-1e-4,(y[1]-y[0])/(x[1]-x[0]))
    right_slope=min(-1e-4,(y[-1]-y[-2])/(x[-1]-x[-2]))
    out=np.asarray(intr)
    out=np.where(k<x[0],y[0]+left_slope*(k-x[0]),out)
    out=np.where(k>x[-1],y[-1]+right_slope*(k-x[-1]),out)
    return expit(out)

def normal_curve(xs,probs,ks):
    x=np.asarray(xs,dtype=float);z=norm.isf(np.clip(probs,1e-5,1-1e-5));
    # 0.5 continuity threshold: P(X>=k) ~ norm.sf((k-.5-mu)/sd)
    slope,intercept=np.polyfit(x-.5,z,1)
    sd = np.clip(1/max(slope,1e-3),.5,100)
    mu = -intercept*sd
    fit=least_squares(lambda t: logit(np.clip(norm.sf((x-.5-t[0])/np.exp(t[1])),1e-6,1-1e-6)) - logit(np.clip(probs,1e-6,1-1e-6)),[mu,math.log(sd)],bounds=([-100,math.log(.5)],[250,math.log(100)]),max_nfev=500)
    mu2,sdl=fit.x
    return norm.sf((np.asarray(ks,dtype=float)-.5-mu2)/np.exp(sdl))

def inferred_ladder(knots,market):
    if len(knots)<3:return None
    if not check_order(knots):return None
    xs=np.array([a['k'] for a in knots],dtype=float)
    kmax=MARKETS[market]
    if xs[-1]>=kmax: kmax=int(xs[-1]+30)
    ks=np.arange(0,kmax+2)
    samples=[]
    for method in ['pchip','linear','normal']:
        for arr in ['lo','p','hi']:
            ps=np.array([a[arr] for a in knots]);ps=np.minimum.accumulate(ps)
            # protect plausible high quotes from inverse ladder errors; reject instead of silently repairing central quotes
            ps=np.minimum.accumulate(ps-(np.arange(len(ps))*1e-7))
            ps=np.clip(ps,1e-6,1-1e-6)
            vals=normal_curve(xs,ps,ks) if method=='normal' else logit_curve(xs,ps,ks,method=method)
            vals[0]=1.0
            vals=np.minimum.accumulate(vals)
            vals=np.clip(vals,0,1)
            samples.append({'method':method,'assumption':arr,'vals':vals})
    c=next(x['vals'] for x in samples if x['method']=='pchip' and x['assumption']=='p')
    stack=np.stack([x['vals'] for x in samples])
    lo,hi=stack.min(axis=0),stack.max(axis=0)
    # Force survival S(0)=1 and cut off far tail into final overflow bin
    mass=(c[:-1]-c[1:])
    mass[-1]+=c[-1]
    mass=np.maximum(mass,0)
    mass=mass/mass.sum()
    return ks[:-1],c[:-1],lo[:-1],hi[:-1],mass

def feature_vector(left,right,k,market):
    k0,k1=float(left['k']),float(right['k'])
    t=(k-k0)/(k1-k0)
    l=logit(np.clip(left['raw_p'],1e-6,1-1e-6));r=logit(np.clip(right['raw_p'],1e-6,1-1e-6))
    baseline=l+(r-l)*t
    return np.array([baseline,l,r,l-r,k1-k0,t,t*t,t*(1-t),k0,k1,
                     *(int(market==m) for m in ['P','R','A','3PM'])],dtype=float)

def holdouts(df):
    examples=[]
    for group_id,g in df.groupby('group_id'):
        if not str(g.book.iloc[0]).startswith('bet365'):continue # don't mix format/source & quote times
        knots=group_knots(g,vig=0.0)
        if len(knots)<3 or not check_order(knots):continue
        market=str(g.market.iloc[0]);player=str(g.player.iloc[0]);event=str(g.event_id.iloc[0]);
        for idx in range(1,len(knots)-1):
            target=knots[idx];left=knots[idx-1];right=knots[idx+1]
            feat=feature_vector(left,right,target['k'],market)
            base=expit(feat[0]);linear=left['raw_p']+(right['raw_p']-left['raw_p'])*(target['k']-left['k'])/(right['k']-left['k'])
            examples.append({'group_id':group_id,'holdout_group':event+'|'+player,'market':market,'player':player,'k':target['k'],'target_implied':target['raw_p'],'baseline_logit':float(feat[0]),'baseline_prob':float(base),'linear_prob':float(linear),'features':feat})
    return examples

def lasso_cv(examples):
    X=np.stack([e['features'] for e in examples]);y=np.array([logit(e['target_implied'])-e['baseline_logit'] for e in examples]);groups=np.array([e['holdout_group'] for e in examples]);truth=np.array([e['target_implied'] for e in examples]);base=np.array([e['baseline_prob'] for e in examples]);linear=np.array([e['linear_prob'] for e in examples]);
    n=min(5,len(np.unique(groups)))
    cv=GroupKFold(n_splits=n)
    lp=np.zeros(len(examples));alphas=[];coeffs=[];folds=[]
    for idx,(tr,te) in enumerate(cv.split(X,y,groups)):
        inner_n=min(4,len(np.unique(groups[tr])))
        est=Pipeline([('scale',StandardScaler()),('lasso',Lasso(max_iter=20000))])
        grid=GridSearchCV(est,{'lasso__alpha':np.logspace(-4,0,25)},cv=GroupKFold(n_splits=inner_n),scoring='neg_mean_absolute_error',n_jobs=1)
        grid.fit(X[tr],y[tr],groups=groups[tr]); model=grid.best_estimator_
        lp[te]=expit(np.array([examples[i]['baseline_logit'] for i in te])+model.predict(X[te]));
        coeffs.append(model.named_steps['lasso'].coef_);alphas.append(float(grid.best_params_['lasso__alpha']));
        folds.extend([{'fold':idx,'player':examples[i]['player'],'market':examples[i]['market'],'target_implied':truth[i],'linear_prob':linear[i],'logit_interp_prob':base[i],'lasso_prob':lp[i]} for i in te])
    out=pd.DataFrame(folds)
    all_metrics={
        'n_heldout_quotes':int(len(truth)),'n_independent_player_game_groups':int(len(np.unique(groups))),
        'linear_probability_mae_pp':round(100*mean_absolute_error(truth,linear),3),
        'linear_logit_mae_pp':round(100*mean_absolute_error(truth,base),3),
        'lasso_residual_mae_pp':round(100*mean_absolute_error(truth,lp),3),
        'best_baseline':'linear_probability' if mean_absolute_error(truth,linear)<mean_absolute_error(truth,base) else 'linear_logit',
        'best_baseline_mae_pp':round(100*min(mean_absolute_error(truth,linear),mean_absolute_error(truth,base)),3),
        'lasso_beats_best_baseline':bool(mean_absolute_error(truth,lp)<min(mean_absolute_error(truth,linear),mean_absolute_error(truth,base))),
        'lasso_alpha_by_fold':alphas,
        'nonzero_feature_frequencies':{name:round(float(np.mean(np.abs(np.array(coeffs)[:,i])>1e-8)),3) for i,name in enumerate(FEATURE_NAMES)},
        'evaluation':'Grouped outer CV by event and player, inner CV by event and player; predicts held-out bookmaker implied prices, NOT true win probabilities.',
    }
    return out,all_metrics

def generate(data_path,out_dir, vig=.06, max_vig=.12):
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    df=load_quotes(data_path)
    diag=[];full=[];samples=[]
    for gid,g in df.groupby('group_id'):
        market=str(g.market.iloc[0]);knots=group_knots(g,vig=vig,wide=max_vig)
        order=check_order(knots)
        status=('QUARANTINE_ORDER_INVERSION' if not order else 'INFERRED_CONDITIONAL' if len(knots)>=3 else 'INSUFFICIENT_THRESHOLDS')
        diag.append({'event_id':g.event_id.iloc[0],'player':g.player.iloc[0],'book':g.book.iloc[0], 'market':market,'observed_over_thresholds':len(knots), 'observed_two_sided_thresholds':sum(k['anchor_type']=='paired_vig_free' for k in knots),'status':status,'source_type':'archived_published_or_screenshot','all_captured_at_present':bool((g.captured_at.astype(str).str.len()>0).all()) if 'captured_at' in g.columns else False})
        if status!='INFERRED_CONDITIONAL':continue
        results=inferred_ladder(knots,market)
        if results is None:continue
        ks,cp,lo,hi,mass=results
        observed_k={k['k']:k for k in knots}
        for i,k in enumerate(ks):
            o=observed_k.get(int(k));full.append({'event_id':g.event_id.iloc[0],'player':g.player.iloc[0],'book':g.book.iloc[0],'market':market,'threshold_at_least':int(k),'is_published_threshold':o is not None,'within_observed_threshold_span':bool(knots[0]['k']<=k<=knots[-1]['k']),'is_extrapolation':bool(k<knots[0]['k'] or k>knots[-1]['k']),'published_over_odds':o['odds'] if o else '', 'p_over_market_implied_estimate':round(float(cp[i]),6),'p_over_model_range_low':round(float(lo[i]),6),'p_over_model_range_high':round(float(hi[i]),6),'estimated_probability_total_bin':round(float(mass[i]),6),'top_bin_includes_all_larger_values':bool(i==len(ks)-1),'quote_status':'observed_price_with_inferred_fair_probability' if o else 'INFERRED_NOT_BETTABLE','range_is_confidence_interval':False,'vig_assumption':vig,'source':'archived_published_quotes_2026-10-20.csv'})
        samples.append({'event_id':str(g.event_id.iloc[0]),'player':str(g.player.iloc[0]),'market':market,'n_knots':len(knots),'p_at_first':knots[0]['p'],'p_at_last':knots[-1]['p']})
    pd.DataFrame(diag).to_csv(out/'ladder_audit.csv',index=False)
    pd.DataFrame(full).to_csv(out/'inferred_full_ladders.csv',index=False)
    pd.DataFrame(samples).to_csv(out/'inferred_group_summary.csv',index=False)
    hold=holdouts(df)
    if len(hold)>=12:
        cvdf,cvmetrics=lasso_cv(hold);cvdf.to_csv(out/'heldout_lasso_predictions.csv',index=False)
    else:cvmetrics={'status':'INSUFFICIENT_HELD_OUT_QUOTES','n':len(hold)}
    adf=pd.DataFrame(diag)
    summary={'input_quote_rows':int(len(df)),'groups':int(len(adf)),'groups_inferred_conditional':int((adf.status=='INFERRED_CONDITIONAL').sum()),'groups_quarantined':int((adf.status=='QUARANTINE_ORDER_INVERSION').sum()),'groups_insufficient':int((adf.status=='INSUFFICIENT_THRESHOLDS').sum()),'inferred_ladder_threshold_rows':len(full),'interpolation_rows':sum((not r['is_published_threshold']) and r['within_observed_threshold_span'] for r in full),'extrapolation_rows':sum(r['is_extrapolation'] for r in full),'captured_timestamp_complete':bool(adf.all_captured_at_present.all()),'lasso_backtest':cvmetrics,'key_caveats':['Observed American odds are quoted prices, not fair probabilities.','One-sided alternate odds use assumed 6% proportional total overround; vary --vig and --max-vig.','The low/high curves are model and margin sensitivity envelopes, NOT distribution-free bounds or confidence intervals.','Full ladders are inferred, not independently observed or confirmed available to bet.','Withholding an interior threshold is price interpolation validation, not outcome calibration.','Do NOT use inferred data as independent constraints to certify value in the original sportsbook.','No proven positive-EV bet identified by this script.']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--input',default='data/archived_published_quotes_2026-10-20.csv');ap.add_argument('--output',default='results');ap.add_argument('--vig',type=float,default=.06);ap.add_argument('--max-vig',type=float,default=.12)
    args=ap.parse_args();print(json.dumps(generate(args.input,args.output,args.vig,args.max_vig),indent=2))
