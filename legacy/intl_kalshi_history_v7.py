"""No-auth historical quote/history readers for lag/velocity research.
Kalshi candle bid/ask fields: research-visible at period end, not necessarily
continuous executable liquidity. Polymarket history is an INDICATIVE price,
not a best ask; deliberately excluded from trade-price screening.
"""
import argparse,csv,json,sys
from datetime import datetime,timezone
from pathlib import Path
import requests
from shoal import Quote,dump_quotes,save_csv
from free_feeds import KALSHI,POLY_CLOB,request_json


def timeiso(epoch):return datetime.fromtimestamp(int(epoch),timezone.utc).isoformat()

def parse_kalshi_candles(doc,entry):
    out=[]
    for c in doc.get('candlesticks',[]):
        try:
            bid=float(c['yes_bid']['close_dollars']);ask=float(c['yes_ask']['close_dollars'])
            if not 0<=bid<=ask<1:continue
            out.append(Quote(entry['game'],entry['market'],entry['outcome'],'Kalshi','exchange',
                timeiso(c['end_period_ts']),entry['start'],bid,ask,float(c.get('volume_fp') or 0),0,
                float(entry.get('fee') or 0),'kalshi_HISTORICAL_CANDLE_NOT_VERIFIED_EXECUTION',False))
        except (TypeError,ValueError,KeyError):continue
    return out

def parse_poly_history(doc,entry):
    out=[]
    for obs in doc.get('history',[]):
        try:
            p=float(obs['p']);t=timeiso(obs['t'])
            if 0<p<1:
                out.append(Quote(entry['game'],entry['market'],entry['outcome'],'Polymarket','indicative',
                    t,entry['start'],p,p,0,0,0,
                    'polymarket_HISTORICAL_INDICATIVE_NOT_EXECUTABLE',False))
        except (ValueError,KeyError):continue
    return out

def fetch_history(mapping_file, from_ts, to_ts, out_file, raw_dir):
    entries=list(csv.DictReader(open(mapping_file,newline='')))
    quotes=[];raw={}
    for e in entries:
        if e['provider']=='kalshi':
            if not e.get('series_ticker') or not e.get('native_id'):raise ValueError('Kalshi series_ticker and native_id required')
            url=f"{KALSHI}/series/{e['series_ticker']}/markets/{e['native_id']}/candlesticks"
            doc=request_json(url,dict(start_ts=from_ts,end_ts=to_ts,period_interval=1))
            new=parse_kalshi_candles(doc,e)
        elif e['provider']=='polymarket':
            url=f"{POLY_CLOB}/prices-history"
            doc=request_json(url,dict(market=e['native_id'],startTs=from_ts,endTs=to_ts,fidelity=1))
            new=parse_poly_history(doc,e)
        else:continue
        raw[e['provider']+':'+e['native_id']]=doc
        quotes.extend(new)
    Path(raw_dir).mkdir(parents=True,exist_ok=True)
    (Path(raw_dir)/'raw_historical.json').write_text(json.dumps(raw))
    dump_quotes(out_file,quotes)
    return quotes

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mapping',required=True);p.add_argument('--from-epoch',type=int,required=True)
    p.add_argument('--to-epoch',type=int,required=True);p.add_argument('--output',required=True);p.add_argument('--raw-dir',default='data/raw')
    a=p.parse_args()
    try:
        q=fetch_history(a.mapping,a.from_epoch,a.to_epoch,a.output,a.raw_dir)
        print(f'Collected {len(q)} historical points. Polymarket mids are not executable prices.')
    except (requests.RequestException,ValueError,KeyError) as e:sys.exit('HISTORY_UNAVAILABLE: '+repr(e))
