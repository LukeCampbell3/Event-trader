#!/usr/bin/env python3
"""Import PropLine saved provider JSON or make a permitted live request with free key.
Only 2-sided, timestamp-valid markets become trusted paired quotes; one-sided
milestones remain 1-sided ranges (never fake the opposite line).
"""
import argparse,csv,json,os
from pathlib import Path
from datetime import datetime,timezone
from propline_free import fetch,parse,utc

def main():
    ap=argparse.ArgumentParser()
    src=ap.add_mutually_exclusive_group(required=True);src.add_argument('--saved-json');src.add_argument('--fetch',action='store_true')
    ap.add_argument('--output',default='data/provider_quotes.csv');ap.add_argument('--asof',help='ISO UTC snapshot time for replay, only with saved JSON')
    ap.add_argument('--max-age-minutes',type=float,default=15)
    a=ap.parse_args()
    if a.fetch:
        if a.asof:ap.error('--asof is only for saved provider responses')
        payload,quota=fetch(os.getenv('PROPLINE_API_KEY'))
        asof=datetime.now(timezone.utc)
    else:
        payload=json.loads(Path(a.saved_json).read_text());quota={};asof=utc(a.asof) if a.asof else datetime.now(timezone.utc)
    if not asof:ap.error('asof must include UTC offset')
    paired,diagnostics=parse(payload,max_age_minutes=a.max_age_minutes,as_of=asof)
    milestones=diagnostics.pop('milestones',[])
    rows=[]
    for r in paired:
        rows.append({'event_id':r['event_id'],'player':r['player'],'book':r['book'],'market':r['market'],
          'line':r['line'],'over_odds':r['over_odds'],'under_odds':r['under_odds'],
          'captured_at':r['captured_at'],'commence_time':r['commence_time'],
          'source':'PropLine','source_type':r['line_type']})
    for r in milestones:
        rows.append({'event_id':r['event_id'],'player':r['player'],'book':r['book'],'market':r['market'],
          'line':r['line'],'over_odds':r['odds'],'under_odds':'',
          'captured_at':r['captured_at'],'commence_time':r['commence_time'],
          'source':'PropLine','source_type':'one_sided_milestone'})
    out=Path(a.output);out.parent.mkdir(exist_ok=True,parents=True)
    fields=['event_id','player','book','market','line','over_odds','under_odds','captured_at','commence_time','source','source_type']
    with out.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    diagnostics.update(source='saved-json' if not a.fetch else 'free-api',quotes=len(rows),pairs=len(paired),one_sided=len(milestones),quota=quota)
    (out.parent/'provider_import_audit.json').write_text(json.dumps(diagnostics,indent=2))
    print(json.dumps({k:diagnostics[k] for k in ['source','quotes','pairs','one_sided']},indent=2))
if __name__=='__main__':main()
