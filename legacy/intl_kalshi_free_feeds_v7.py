"""Free public Kalshi / Polymarket read-only adapters; fail closed.

Explicit native-to-canonical mappings are mandatory. Never auto-equate contracts
whose settlement rules, event window, overtime, or voiding rules differ.

Use on a machine with Internet access; this hosted container blocks API DNS.
"""
import csv, json, argparse, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from shoal import Quote, dump_quotes, americana_prob

KALSHI='https://external-api.kalshi.com/trade-api/v2'
POLY_GAMMA='https://gamma-api.polymarket.com'
POLY_CLOB='https://clob.polymarket.com'


def now_iso(): return datetime.now(timezone.utc).isoformat()

def request_json(url, params=None, session=None):
    resp=(session or requests).get(url,params=params,timeout=15,headers={'User-Agent':'nba-market-research/0.7 read-only'})
    resp.raise_for_status()
    return resp.json()


def parse_kalshi(m, mapping, capture):
    """Use actual ask-side prices; no midpoint as executable entry.
    Ignore stale last price and UI 'chance'.
    """
    q=[]
    if str(m.get('status','')).lower() not in ('open','active'):return q
    for side in ('yes','no'):
        outcome=mapping.get(f'{side}_outcome','').strip()
        if not outcome:continue
        bid=m.get(f'{side}_bid_dollars')
        ask=m.get(f'{side}_ask_dollars')
        if ask is None or bid is None:continue
        q.append(Quote(mapping['game'],mapping['market'],outcome,'Kalshi','exchange',capture,mapping['start'],float(bid),float(ask),
                       float(m.get('volume_fp') or 0),float(m.get(f'{side}_ask_size_fp') or 0),
                       float(mapping.get('fee') or 0),f"kalshi_api:{m['ticker']}",mapping.get('rules_verified','').lower()=='true'))
    return q


def parse_poly_book(book, mapping, capture):
    bids=book.get('bids') or [];asks=book.get('asks') or []
    if not bids or not asks:return []
    best_bid=max(float(r['price']) for r in bids)
    best_ask=min(float(r['price']) for r in asks)
    qty=sum(float(r['size']) for r in asks if abs(float(r['price'])-best_ask)<1e-8)
    return [Quote(mapping['game'],mapping['market'],mapping['outcome'],'Polymarket','exchange',capture,mapping['start'],
                  best_bid,best_ask,float(mapping.get('volume') or 0),qty,float(mapping.get('fee') or 0),
                  f"polymarket_clob:{mapping['native_id']}",mapping.get('rules_verified','').lower()=='true')]


def sportsbook_pair(american_rows):
    out=[]
    for r in american_rows:
        out.append(Quote(r['game'],r['market'],r['outcome'],r['source'],'sportsbook',r['timestamp'],r['start'],None,
                         americana_prob(r['american_odds']),float(r.get('volume') or 0),
                         float(r.get('size') or 0),0.,r.get('provenance') or 'sportsbook_export',
                         str(r.get('rules_verified','')).lower()=='true'))
    return out


def fetch_mapped(mapping_path, provider, out, raw_dir):
    with open(mapping_path,newline='') as f:mapping=[r for r in csv.DictReader(f) if r['provider'].lower()==provider]
    if not mapping:raise ValueError('No explicit canonical mappings for '+provider)
    capture=now_iso();q=[];raw={}; rawdir=Path(raw_dir);rawdir.mkdir(parents=True,exist_ok=True)
    if provider=='kalshi':
        groups={r['event_ticker'] for r in mapping}
        found={}
        for event in groups:
            cursor=None
            while True:
                params={'event_ticker':event,'limit':100,'status':'open'}
                if cursor:params['cursor']=cursor
                doc=request_json(f'{KALSHI}/markets',params)
                for m in doc.get('markets',[]):found[m['ticker']]=m
                cursor=doc.get('cursor')
                if not cursor:break
        for row in mapping:
            native=found.get(row['native_id'])
            if native:
                raw[row['native_id']]=native
                q.extend(parse_kalshi(native,row,capture))
    elif provider=='polymarket':
        for row in mapping:
            doc=request_json(f'{POLY_CLOB}/book',{'token_id':row['native_id']})
            raw[row['native_id']]=doc
            q.extend(parse_poly_book(doc,row,capture))
            time.sleep(.10)
    else:raise ValueError('Unsupported provider')
    (rawdir/(provider+'_raw_'+capture.replace(':','-')+'.json')).write_text(json.dumps({'captured_at':capture,'documents':raw},indent=2))
    dump_quotes(out,q)
    print(f'{provider}: {len(q)} trade-side quotes mapped, {len(raw)} raw market records; created {out}')
    return q

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--provider',choices=['kalshi','polymarket'],required=True)
    a.add_argument('--mapping',required=True);a.add_argument('--output',required=True)
    a.add_argument('--raw-dir',default='data/raw')
    args=a.parse_args()
    try:fetch_mapped(args.mapping,args.provider,args.output,args.raw_dir)
    except (requests.RequestException,ValueError,KeyError) as ex:
        sys.exit(f'NO_LIVE_CAPTURE: {type(ex).__name__}: {ex}')
