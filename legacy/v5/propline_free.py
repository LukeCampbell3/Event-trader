#!/usr/bin/env python3
"""Free PropLine NBA sportsbook alternate-line ingestion, no past game stats.

Documentation: https://prop-line.com/docs
Free tier: 1,000 calls/day (provider terms apply). Requires own free API key.
Feed samples and fixtures are never passed off as live odds.

Saved snapshot import requires no network or key:
    python propline_free.py --input-json verified.json --output ladder.csv

Fetch a slate in *one* API call:
    PROPLINE_API_KEY=... python propline_free.py --fetch --output ladder.csv
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import sys
import re
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

API='https://api.prop-line.com/v1/sports/basketball_nba/odds'
MARKETS={
    'player_points':'P',
    'player_rebounds':'R',
    'player_assists':'A',
    'player_threes':'T',
    'player_points_rebounds_assists':'PRA',
    'player_points_assists':'PA',
    'player_points_rebounds':'PR',
    'player_rebounds_assists':'RA',
}
FIELDS=['player','book','market','line','over_odds','under_odds','event_date',
        'event_id','captured_at','home_team','away_team','commence_time',
        'line_type','source_market','source_book','source','player_id']
EXCLUDED={'prizepicks','underdog','sleeper','dabble','parlayplay','draftkings_pick6',
          'draftkingspick6','rebet'}


def utc(text):
    if not text or not isinstance(text,str): return None
    try:
        obj=datetime.fromisoformat(text.strip().replace('Z','+00:00'))
        return obj.astimezone(timezone.utc) if obj.tzinfo else None
    except ValueError: return None


def valid_american(x):
    # Disallow decimal prices or imaginary +80, and booleans, NaN and inf.
    try:
        if isinstance(x,bool):return False
        f=float(x)
        return math.isfinite(f) and abs(f)>=100 and (f>0 or f<0)
    except (ValueError,TypeError):return False


def odds_str(x):
    return ('+' if float(x)>0 else '')+str(int(float(x)))


def nba_events(payload):
    if isinstance(payload,list):return payload
    if isinstance(payload,dict):
        if 'bookmakers' in payload and 'id' in payload:return [payload]
        for k in ('data','events','results'):
            if isinstance(payload.get(k),list):return payload[k]
    raise ValueError('Unsupported PropLine event response structure; refusing to guess')


def parse(payload, *, date=None, player=None, max_age_minutes=15, as_of=None, sportsbook=None):
    """Returns (paired rows, diagnostics); skips anything ambiguous or stale.

    Data with >1 snapshot per exact (event, book, player, market, line) is
    rejected rather than mixing prices from different moments.
    """
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('as_of must include a timezone')
    records=defaultdict(dict)
    notes=Counter()
    issues=[]
    milestones=[]
    considered=0
    for event in nba_events(payload):
        if not isinstance(event,dict) or not event.get('id'):
            notes['skipped_malformed_event']+=1;continue
        date_str=str(event.get('commence_time',''))[:10]
        if date and date_str!=date:continue
        if event.get('sport_key') not in (None,'basketball_nba'):
            notes['skipped_wrong_sport']+=1;continue
        ev=str(event['id'])
        for book in event.get('bookmakers',[]):
            if not isinstance(book,dict):continue
            bk=str(book.get('key','')).lower().strip()
            if not bk:continue
            if sportsbook and bk not in sportsbook:continue
            if bk in EXCLUDED:
                notes['excluded_dfs_or_pickem']+=1;continue
            for market in book.get('markets',[]):
                if not isinstance(market,dict):continue
                key=str(market.get('key',''))
                stat=MARKETS.get(key)
                if not stat:
                    notes['unmapped_market']+=1;continue
                if market.get('period') not in (None,'','full','game'):
                    notes['excluded_period_market']+=1;continue
                if market.get('suspended_at'):
                    notes['excluded_suspended_market']+=1;continue
                timestamp=market.get('last_update')
                ts=utc(timestamp)
                if max_age_minutes is not None and (ts is None or abs((now-ts).total_seconds())>max_age_minutes*60):
                    notes['excluded_stale_or_untimestamped_market']+=1;continue
                if ts is None:
                    notes['excluded_invalid_timestamp']+=1;continue
                for outcome in market.get('outcomes',[]):
                    if not isinstance(outcome,dict):continue
                    name=str(outcome.get('name','')).lower().strip()
                    person=(outcome.get('description') or '').strip()
                    if name not in {'over','under'}:
                        # '29+ Points + Assists' is P(stat >= 29), exactly
                        # equivalent to P(stat > 28.5). It is ONE-SIDED:
                        # no de-vigging and no invented price for the under.
                        nmatch=re.match(r'^(\d+)\+\s',str(outcome.get('name','')).strip())
                        if nmatch and person and valid_american(outcome.get('price')):
                            n=int(nmatch.group(1))
                            if n>=1:
                                milestones.append(dict(player=person,book=bk,market=stat,
                                    line=n-.5,side='over',odds=odds_str(outcome['price']),
                                    event_id=ev,event_date=date_str,captured_at=ts.isoformat(),
                                    home_team=event.get('home_team',''),
                                    away_team=event.get('away_team',''),
                                    commence_time=event.get('commence_time',''),
                                    source='PropLine',line_type='milestone',source_market=key))
                                notes['one_sided_milestones']+=1
                            continue
                        notes['excluded_nonstandard_side']+=1;continue
                    if not person:
                        notes['missing_player_name']+=1;continue
                    if player and player.lower() not in person.lower():continue
                    point=outcome.get('point')
                    try:line=float(point)
                    except (ValueError,TypeError):notes['bad_line']+=1;continue
                    if not math.isfinite(line) or abs(line*2-round(line*2))>1e-8 or (line%1)!=.5:
                        notes['excluded_non_half_integer_line']+=1;continue
                    if not valid_american(outcome.get('price')):
                        notes['invalid_american_price']+=1;continue
                    considered+=1
                    rid=(ev,bk,person.casefold(),stat,line)
                    r=records[rid]
                    if not r:
                        r.update(player=person,book=bk,market=stat,line=line,
                                 event_date=date_str,event_id=ev,
                                 captured_at=ts.isoformat(),
                                 home_team=event.get('home_team',''),away_team=event.get('away_team',''),
                                 commence_time=event.get('commence_time',''),
                                 line_type=outcome.get('line_type') or market.get('line_type') or '',
                                 source_market=key,source_book=bk,source='PropLine',
                                 player_id=outcome.get('player_id') or '')
                    if r['captured_at']!=ts.isoformat():
                        r['ambiguous']=True
                    if name in r:r['ambiguous']=True
                    r[name]=odds_str(outcome['price'])
    good=[]
    for r in records.values():
        if r.get('ambiguous'):
            notes['ambiguous_quote']+=1;continue
        if 'over' not in r or 'under' not in r:
            notes['unpaired_quotations']+=1
            issues.append({k:r[k] for k in ('player','book','market','line','event_id')})
            continue
        a=r['over'];b=r['under']
        # No-vig normalization expects valid betting lines (not arbitraged pairs).
        # Self-contained odds conversion; no import from legacy market_edges
        to_decimal=lambda x: (1 + float(x)/100) if float(x)>0 else (1 + 100/(-float(x)))
        american_prob=lambda odds: 1/to_decimal(odds)
        if american_prob(a)+american_prob(b)<.995:
            notes['negative_overround']+=1;continue
        r['over_odds']=a;r['under_odds']=b
        good.append({k:r.get(k,'') for k in FIELDS})
    good.sort(key=lambda r:(r['event_id'],r['player'].lower(),r['book'],r['market'],r['line']))
    groups=defaultdict(set)
    for r in good:groups[(r['event_id'],r['player'],r['book'],r['market'])].add(r['line'])
    return good, {'status':'VERIFIED_SNAPSHOT_PARSER','price_source':'PropLine',
                  'paired_rows':len(good),'considered_sides':considered,
                  'ladders_with_2_plus_thresholds':sum(len(v)>=2 for v in groups.values()),
                  'ladders_with_3_plus_thresholds':sum(len(v)>=3 for v in groups.values()),
                  'rejections':dict(notes),'unpaired_examples':issues[:25],
                  'milestones':milestones,
                  'warning':'Absent or unavailable alternate lines are NEVER synthesized.'}


def fetch(key,markets=None,timeout=20):
    import requests
    if not key:raise RuntimeError('No PROPLINE_API_KEY. Get a free key at https://prop-line.com/ then set it locally.')
    params={'markets':','.join(markets or MARKETS.keys())}
    try:
        response=requests.get(API,params=params,headers={'X-API-Key':key},timeout=timeout)
        response.raise_for_status()
        return response.json(),{k:v for k,v in response.headers.items() if k.lower() in
                                {'x-daily-remaining','x-daily-limit','date'}}
    except requests.HTTPError as exc:
        # No credentials/token in URLs, and don't echo response body.
        raise RuntimeError(f'PropLine request failed: HTTP {exc.response.status_code}. Check key/quota/market availability.') from None
    except requests.RequestException as exc:
        raise RuntimeError(f'PropLine connection failed: {type(exc).__name__}. Verify network and retry locally.') from None


def run(argv=None):
    parser=argparse.ArgumentParser(description='FREE NBA player prop alternate ladder fetcher')
    src=parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--fetch',action='store_true',help='Get live NBA markets using a free PropLine key')
    src.add_argument('--input-json',help='Parse a real saved PropLine API response; no network')
    parser.add_argument('--output',default='propline_ladders.csv')
    parser.add_argument('--raw-json',help='Optional output raw API snapshot JSON for audit')
    parser.add_argument('--date',help='YYYY-MM-DD event date in UTC (otherwise all active events)')
    parser.add_argument('--player',help='Case-insensitive player substring')
    parser.add_argument('--books',help='Comma-separated sportsbook keys (default all eligible non-DFS)')
    parser.add_argument('--max-age-minutes',type=float,default=15)
    parser.add_argument('--as-of',help='UTC timestamp for offline replay, e.g. 2026-10-20T21:00:00Z')
    args=parser.parse_args(argv)
    if args.max_age_minutes < 0:parser.error('max-age-minutes must be nonnegative')
    if args.fetch:
        payload,quota=fetch(os.environ.get('PROPLINE_API_KEY'))
    else:
        payload=json.loads(Path(args.input_json).read_text(encoding='utf8'))
        quota={}
    now=utc(args.as_of) if args.as_of else datetime.now(timezone.utc)
    if now is None:parser.error('as-of must be a timezone-aware ISO timestamp')
    books={x.strip().lower() for x in args.books.split(',')} if args.books else None
    rows,diag=parse(payload,date=args.date,player=args.player,max_age_minutes=args.max_age_minutes,
                    as_of=now,sportsbook=books)
    milestones=diag.pop('milestones')
    one_side_path=Path(args.output).with_name(Path(args.output).stem+'_one_sided.csv')
    one_side_path.parent.mkdir(parents=True,exist_ok=True)
    one_side_fields=['player','book','market','line','side','odds','event_id','event_date',
                     'captured_at','home_team','away_team','commence_time','source','line_type','source_market']
    with one_side_path.open('w',newline='',encoding='utf8') as fh:
        writer=csv.DictWriter(fh,fieldnames=one_side_fields)
        writer.writeheader();writer.writerows(milestones)
    diag['one_sided_file']=str(one_side_path)
    diag['one_sided_n_plus_markets']=len(milestones)
    diag['quota']=quota
    diag['as_of']=now.isoformat()
    diag['data_kind']='LIVE_REQUEST' if args.fetch else 'SAVED_PROVIDER_SNAPSHOT'
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',newline='',encoding='utf8') as fh:
        writer=csv.DictWriter(fh,fieldnames=FIELDS)
        writer.writeheader();writer.writerows(rows)
    (out.parent/(out.stem+'_diagnostics.json')).write_text(json.dumps(diag,indent=2),encoding='utf8')
    if args.raw_json:Path(args.raw_json).write_text(json.dumps(payload,indent=2),encoding='utf8')
    print(json.dumps(diag,indent=2))
    if not rows:
        print('No usable paired odds. Check event date, quote freshness, market availability and rejected data.',file=sys.stderr)
        return 2
    return 0

if __name__=='__main__':raise SystemExit(run())
