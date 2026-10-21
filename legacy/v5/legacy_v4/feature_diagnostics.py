#!/usr/bin/env python3
"""Cross-game generalization, compact Lasso feature ablations, and group bootstrap uncertainty."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.special import expit,logit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Lasso
from sklearn.model_selection import GroupKFold,GridSearchCV
from ladder_lasso import load_quotes,holdouts,FEATURE_NAMES

ROOT=Path(__file__).resolve().parent
L=load_quotes(ROOT/'data'/'archived_published_quotes_2026-10-20.csv')
ex=holdouts(L)
X=np.stack([e['features'] for e in ex]);grp=np.array([e['holdout_group'] for e in ex]); event=np.array([e['group_id'].split('|')[0] for e in ex]);
target=np.array([e['target_implied'] for e in ex]);base_logit=np.array([e['baseline_logit'] for e in ex]); base=expit(base_logit)
sets={
    'no_lasso':[],
    'local_curve_only':[0,1,2,3,4,5,6,7],
    'local_curve_plus_thresholds':[0,1,2,3,4,5,6,7,8,9],
    'local_curve_plus_market':[0,1,2,3,4,5,6,7,10,11,12,13],
    'all_features':list(range(len(FEATURE_NAMES))),
}

def model_predict(tr,te,cols):
    tr=np.asarray(tr);te=np.asarray(te)
    if not cols:return np.asarray(base[te]),None,None
    yy=logit(target[tr])-base_logit[tr]
    inn=min(4,len(np.unique(grp[tr])))
    if inn<2:return expit(base_logit[te]+np.median(yy)),None,None
    gs=GridSearchCV(Pipeline([('scale',StandardScaler()),('lasso',Lasso(max_iter=20000))]),
        {'lasso__alpha':np.logspace(-4,0,25)},
        scoring='neg_mean_absolute_error',cv=GroupKFold(n_splits=inn),n_jobs=1)
    gs.fit(X[tr][:,cols],yy,groups=grp[tr]);m=gs.best_estimator_
    return expit(base_logit[te]+m.predict(X[te][:,cols])),float(gs.best_params_['lasso__alpha']),m.named_steps['lasso'].coef_.tolist()

outs=[];details=[]
for name,cols in sets.items():
    pred=np.zeros(len(ex))
    for train,test in GroupKFold(n_splits=5).split(X,groups=grp):
        pp,alpha,coefs=model_predict(train,test,cols);pred[test]=pp
    outs.append({'split':'grouped_players_within_games','feature_set':name,'n_heldout':len(ex),'MAE_pp':round(float(np.mean(np.abs(pred-target))*100),3)})
    for e,pr,t in zip(ex,pred,target):details.append({'split':'grouped_players_within_games','feature_set':name,'group':e['holdout_group'],'event':e['group_id'].split('|')[0],'player':e['player'],'market':e['market'],'actual_quote_p':t,'predict_p':pr,'abs_error_pp':abs(t-pr)*100})
    for held_event in np.unique(event):
        tr=np.where(event!=held_event)[0];te=np.where(event==held_event)[0]
        pp,alpha,coefs=model_predict(tr,te,cols)
        outs.append({'split':'holdout_entire_game_'+held_event,'feature_set':name,'n_heldout':len(te),'MAE_pp':round(float(np.mean(abs(pp-target[te]))*100),3)})
        for i,pr in zip(te,pp):
            e=ex[i];details.append({'split':'holdout_entire_game_'+held_event,'feature_set':name,'group':e['holdout_group'],'event':held_event,'player':e['player'],'market':e['market'],'actual_quote_p':target[i],'predict_p':pr,'abs_error_pp':abs(target[i]-pr)*100})
out=pd.DataFrame(outs)
out.to_csv(ROOT/'results'/'lasso_feature_ablations.csv',index=False)
d=pd.DataFrame(details);d.to_csv(ROOT/'results'/'lasso_crossgame_predictions.csv',index=False)
# Cluster bootstrap CIs for difference in MAE pp across heldout player-game groups
wide=d[d.split=='grouped_players_within_games'].pivot_table(index=['group','event','player','market'],columns='feature_set',values='abs_error_pp').reset_index()
bygroup=wide.groupby('group')[[c for c in sets]].mean(); arr=(bygroup['no_lasso']-bygroup['all_features']).values
rng=np.random.default_rng(1976);delta=np.mean(arr);rep=np.array([np.mean(rng.choice(arr,size=len(arr),replace=True)) for _ in range(2000)])
results={'feature_ablations':outs,'cluster_bootstrap_lasso_minus_baseline_reduction_pp_mean':round(float(delta),3),'cluster_bootstrap_95pct_descriptive_ci_pp':[round(float(x),3) for x in np.quantile(rep,[.025,.975])], 'bootstrap_notes':'Resample 20 player-game groups, descriptive uncertainty for quoting-price interpolation only, not confidence of betting edge.'}
(ROOT/'results'/'feature_report.json').write_text(json.dumps(results,indent=2))
print(out.to_string(index=False));print('cluster boot improvement',delta,results['cluster_bootstrap_95pct_descriptive_ci_pp'])
