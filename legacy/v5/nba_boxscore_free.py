#!/usr/bin/env python3
"""Fetch completed official NBA box scores for prospective scoring, without odds or history.
https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{gameId}.json
Provider event IDs are NOT NBA game IDs. Supply both IDs explicitly.
"""
import argparse,csv,json,re
from pathlib import Path

def parse_final_boxscore(payload,event_id,expected_game_id=None):
    g=payload.get('game',{})
    if int(g.get('gameStatus',-1))!=3:raise ValueError('Refusing to grade incomplete NBA game')
    gameid=str(g.get('gameId',''))
    if expected_game_id and gameid!=str(expected_game_id):raise ValueError('NBA game ID mismatch')
    if not event_id:raise ValueError('provider event ID must be supplied; never guess game mapping')
    out=[]
    for side in ['homeTeam','awayTeam']:
        for p in g.get(side,{}).get('players',[]):
            st=p.get('statistics',{})
            if not st:continue
            name=(p.get('name') or (str(p.get('firstName',''))+' '+str(p.get('familyName','')))).strip()
            if not name:continue
            out.append({'event_id':event_id,'player':name,
                        'P':int(st['points']),'R':int(st['reboundsTotal']),'A':int(st['assists']),
                        'nba_game_id':gameid,'source':'NBA_OFFICIAL_LIVE_BOX_SCORE_FINAL'})
    return out

def fetch(game_id):
    import requests
    if not re.fullmatch(r'\d{10}',game_id):raise ValueError('NBA game id must be 10 digits')
    url=f'https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json'
    res=requests.get(url,timeout=20,headers={'User-Agent':'nba-market-joint-v5/1.0'})
    res.raise_for_status();return res.json()

def main():
    ap=argparse.ArgumentParser();source=ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--nba-game-id');source.add_argument('--saved-json')
    ap.add_argument('--expected-nba-game-id');ap.add_argument('--provider-event-id',required=True)
    ap.add_argument('--output',required=True);a=ap.parse_args()
    raw=fetch(a.nba_game_id) if a.nba_game_id else json.loads(Path(a.saved_json).read_text())
    rows=parse_final_boxscore(raw,a.provider_event_id,a.expected_nba_game_id or a.nba_game_id)
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['event_id','player','P','R','A','nba_game_id','source']);w.writeheader();w.writerows(rows)
    print(json.dumps({'players':len(rows),'output':str(output),'note':'Check player-name matches against odds provider before grading.'}))
if __name__=='__main__':main()
