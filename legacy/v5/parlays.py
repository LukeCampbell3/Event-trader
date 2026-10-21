#!/usr/bin/env python3
"""Same-player correlated-parlay probability bounds on exact event intersections.
The book's *actual repriced SGP payout* must be supplied. No independence shortcut.
"""
import argparse,json
import numpy as np
from joint_engine import read_quotes,states_and_indicator,build_A,bound_probabilities,parse_time,sync_status,implied

def analyze_parlay(quotes,legs,parlay_odds,margin=.15,paired=.015):
    if not legs:raise ValueError('no legs')
    if len({(x.event_id,x.player,x.book) for x in quotes})!=1:
        raise ValueError("use one player's sportsbook snapshot per same-player parlay")
    legkeys=[(x['market'],float(x['line']),x['side']) for x in legs]
    used=[]
    for market,line,side in legkeys:
        matches=[q for q in quotes if q.market==market and q.line==line]
        if len(matches)!=1:raise ValueError('parlay leg absent from posted quote snapshot')
        if side not in ('over','under'):raise ValueError('bad parlay side')
        used.extend(matches)
    # Exclude all priced selections being tested; otherwise a parlay can price itself.
    train=[q for q in quotes if q not in used]
    _,ind,n,K=states_and_indicator(quotes)
    event=np.ones(n,dtype=bool)
    for q,(_,_,side) in zip(used,legkeys):
        v=ind(q)
        event &= v if side=='over' else ~v
    A,lo,hi,_=build_A(train,ind,margin,paired)
    bound=bound_probabilities(A,lo,hi,event.astype(float))
    if bound['status']!='OK':return bound
    br=implied(parlay_odds)
    result={'status':'OK','p_min':bound['low'],'p_max':bound['high'],
      'parlay_odds':parlay_odds,'break_even':br,'worst_case_roi_conditional':bound['low']/br-1,
      'snapshot_status':sync_status(quotes),'heldout_legs':len(used),
      'source':'CORRELATED_SAME_PLAYER_JOINT_LP',
      'not_guaranteed_true_ev':True,
      'note':'Player props from different players require cross-player joint model; cannot use this same-player engine.'}
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--quotes',required=True);ap.add_argument('--event',required=True);ap.add_argument('--player',required=True);ap.add_argument('--book',required=True)
    ap.add_argument('--legs-json',required=True,help='JSON array of {market,line,side}');ap.add_argument('--parlay-odds',required=True)
    a=ap.parse_args(); q,_=read_quotes(a.quotes)
    selected=[x for x in q if (x.event_id,x.player,x.book)==(a.event,a.player,a.book)]
    print(json.dumps(analyze_parlay(selected,json.loads(a.legs_json),a.parlay_odds),indent=2))
if __name__=='__main__':main()
