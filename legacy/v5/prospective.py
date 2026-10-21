#!/usr/bin/env python3
"""Append-only paper-trading ledger and ex-ante outcome scoring.
Only accepts fully synchronized PRE-GAME snapshots; NEVER rewrites history.
"""
import argparse, csv, hashlib, json, math
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
from joint_engine import read_quotes, sync_status, parse_time, implied

MARKETS={'P':('P',),'R':('R',),'A':('A',),'PA':('P','A'),'PR':('P','R'),'RA':('R','A'),'PRA':('P','R','A')}


def evidence_hash(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def freeze(quotes_csv,analysis_csv,ledger_path,asof,allow_synthetic_test=False):
    q,issues=read_quotes(quotes_csv)
    if issues:raise ValueError(f'Unresolved quote parsing issues: {issues[:3]}')
    if not allow_synthetic_test and any('synthetic' in (x.source+' '+x.provenance).lower() for x in q):
        raise ValueError('Synthetic fixture cannot be frozen as prospective real-world forecasts')
    rows=pd.read_csv(analysis_csv).fillna('')
    stamp=parse_time(asof)
    if not stamp:raise ValueError('asof must be timezone-aware UTC')
    if stamp>datetime.now(timezone.utc):raise ValueError('Cannot freeze forecasts at a future asof timestamp')
    tipoffs=[parse_time(x.commence_time) for x in q]
    if any(t is None or t<=datetime.now(timezone.utc) for t in tipoffs):
        raise ValueError('Cannot claim an ex-ante freeze after tipoff')
    if len(rows)==0:raise ValueError('No predictions to freeze')
    for r in rows.to_dict('records'):
        matched=[x for x in q if x.event_id==str(r['event_id']) and x.player==str(r['player']) and x.book==str(r['book'])]
        if not matched or sync_status(matched,asof)!='SYNCHRONIZED_PREGAME':
            raise ValueError(f'No synchronized pregame provenance for {r["player"]}')
        if float(r['inferred_p_min'])>float(r['inferred_p_max']):raise ValueError('invalid bounds')
    manifest={'record_type':'FROZEN_PREGAME_PREDICTIONS','asof_utc':stamp.isoformat(),'quotes_sha256':evidence_hash(quotes_csv),
      'analysis_sha256':evidence_hash(analysis_csv),'predictions':rows.to_dict('records'),
      'note':'Paper predictions. Ex-ante market-derived probabilities; not user wagers or proven value.'}
    entry_id=hashlib.sha256(json.dumps(manifest,sort_keys=True,default=str).encode()).hexdigest()
    manifest['entry_id']=entry_id
    manifest['created_at_utc']=datetime.now(timezone.utc).isoformat()
    path=Path(ledger_path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        prior=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if any(x['entry_id']==entry_id for x in prior):raise ValueError('Duplicate forecast freeze refused')
    with path.open('a') as f:f.write(json.dumps(manifest,sort_keys=True,default=str)+'\n')
    return entry_id


def settle(ledger,boxscore_csv,out_csv):
    data=pd.read_csv(boxscore_csv).fillna('')
    needed={'event_id','player','P','R','A'}
    if not needed.issubset(data.columns):raise ValueError(f'Box-score input missing {needed-set(data.columns)}')
    actual={ (str(r.event_id),str(r.player)):r for r in data.itertuples() }
    entries=[json.loads(s) for s in Path(ledger).read_text().splitlines() if s.strip()]
    out=[]
    for e in entries:
        for r in e['predictions']:
            match=actual.get((str(r['event_id']),str(r['player'])))
            if match is None:continue
            cat=str(r['target_market']);k=int(math.floor(float(r['target_line']))+1)
            total=sum(int(getattr(match,m)) for m in MARKETS[cat])
            win=(total>=k) if r['side']=='over' else (total<k)
            central=float(r['market_conditioned_central_estimate']);brier=(central-float(win))**2
            odds_prob=float(r['quoted_break_even'])
            profit=(1/odds_prob-1) if win else -1.
            out.append({'entry_id':e['entry_id'],'event_id':r['event_id'],'player':r['player'],
                'market':cat,'line':r['target_line'],'side':r['side'],'recorded_asof':e['asof_utc'],
                'stat_total':total,'hit':int(win),'central_brier':round(brier,6),
                'quoted_break_even_brier':round((odds_prob-float(win))**2,6),
                'hypothetical_unit_return':round(profit,5),
                'was_real_wager':False,'selected_as_edge':r.get('classification')=='RESEARCH_SIGNAL_REQUIRES_CONFIRMATION'})
    Path(out_csv).parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(out).to_csv(out_csv,index=False)
    return {'graded_forecasts':len(out),'note':'Ex-ante paper forecasts. Counts are not independent when player/game/threshold overlap.',
            'unique_events':len(set(x['event_id'] for x in out))}


def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='op',required=True)
    f=sub.add_parser('freeze');f.add_argument('--allow-synthetic-test',action='store_true');f.add_argument('--quotes',required=True);f.add_argument('--analysis',required=True);f.add_argument('--asof',required=True);f.add_argument('--ledger',default='results/pregame_ledger.jsonl')
    s=sub.add_parser('settle');s.add_argument('--ledger',required=True);s.add_argument('--boxscore',required=True);s.add_argument('--output',required=True)
    a=ap.parse_args();v=freeze(a.quotes,a.analysis,a.ledger,a.asof,allow_synthetic_test=a.allow_synthetic_test) if a.op=='freeze' else settle(a.ledger,a.boxscore,a.output)
    print(json.dumps(v,indent=2))
if __name__=='__main__':main()
