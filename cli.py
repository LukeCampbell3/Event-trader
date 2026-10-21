"""CLI for read-only Polymarket US market bot, paper trade simulator, tests."""
from __future__ import annotations
import argparse, json, csv
from datetime import datetime,timezone
from pathlib import Path
from market_engine import (Contract, ExchangeQuote, SportsbookPair, ScreenConfig,
                           evaluate, inferred_ladder, market_motion,
                           read_contracts,read_quotes,read_books,dump_jsonl,load_jsonl)
from us_feed import discover_nba, capture_us
from sportsbook_csv import import_pairs
from recording import record_paper,settle,summary


def run():
    p=argparse.ArgumentParser(description='NBA probability-flow bot: research + PAPER ONLY')
    sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('discover-us',help='Dump public Polymarket US search output, no orders')
    d.add_argument('--query',default='NBA');d.add_argument('--output',default='data/discovered_us.json')
    f=sub.add_parser('capture-us',help='Capture actual BBO using reviewed manifest')
    f.add_argument('--contracts',required=True); f.add_argument('--output',required=True)
    f.add_argument('--fee-reserve',type=float,default=.025)
    sb=sub.add_parser('import-sportsbook-csv')
    sb.add_argument('--csv',required=True);sb.add_argument('--contracts',required=True);sb.add_argument('--output',required=True)
    a=sub.add_parser('evaluate')
    a.add_argument('--contracts',required=True);a.add_argument('--exchange',required=True)
    a.add_argument('--sportsbooks',required=True);a.add_argument('--asof',required=True)
    a.add_argument('--output',default='results/screens.jsonl');a.add_argument('--paper-db')
    l=sub.add_parser('ladder')
    l.add_argument('--points',required=True,help='JSON list [[threshold,p],...] from VERIFIED paired markets')
    l.add_argument('--min',type=int,required=True);l.add_argument('--max',type=int,required=True)
    l.add_argument('--output',default='results/inferred_ladder.jsonl')
    m=sub.add_parser('motion')
    m.add_argument('--snapshots',required=True);m.add_argument('--output',default='results/motion.jsonl')
    s=sub.add_parser('settle-paper')
    s.add_argument('--db',required=True);s.add_argument('--outcomes',required=True)
    st=sub.add_parser('paper-summary');st.add_argument('--db',required=True)
    args=p.parse_args()
    if args.command=='discover-us':
        discover_nba(args.output,args.query)
        print('Unreviewed discovery saved. Rules must be verified manually.')
    elif args.command=='capture-us':
        q,rejections=capture_us(read_contracts(args.contracts),args.output,args.fee_reserve)
        print(f'Captured {len(q)} US exchange books; rejected={len(rejections)}')
        if rejections:print(json.dumps(rejections,indent=2))
    elif args.command=='import-sportsbook-csv':
        qs,rejected=import_pairs(args.csv,args.contracts,args.output)
        print(json.dumps({'imported_pairs':len(qs),'rejected':rejected},indent=2))
    elif args.command=='evaluate':
        contracts=read_contracts(args.contracts)
        out=evaluate(contracts,read_quotes(args.exchange),read_books(args.sportsbooks),args.asof)
        dump_jsonl(args.output,out)
        print(json.dumps({'evaluated':len(out),'conditional_screen_flags':sum(x['screen_pass'] for x in out),
                          'verified_executable_edges':0,
                          'output':args.output,'rejection_reason_counts':{
                              key:sum(key in r['reasons'] for r in out)
                              for key in sorted({j for r in out for j in r['reasons']})}},indent=2))
        if args.paper_db:
            n=record_paper(args.paper_db,out,{c.contract_id:c for c in contracts},args.asof)
            print(f'Paper signals frozen: {n}. No orders submitted.')
    elif args.command=='ladder':
        known=json.loads(Path(args.points).read_text())
        out=inferred_ladder([(int(t),float(v)) for t,v in known],list(range(args.min,args.max+1)))
        dump_jsonl(args.output,out);print('Generated',len(out),'levels. Inferred levels are not evidence.')
    elif args.command=='motion':
        out=market_motion(load_jsonl(args.snapshots));dump_jsonl(args.output,out)
        print('Analyzed',len(out),'aligned repeated-price series')
    elif args.command=='settle-paper':
        outcomes=json.loads(Path(args.outcomes).read_text())
        print('Settled:',settle(args.db,outcomes,datetime.now(timezone.utc).isoformat()))
    elif args.command=='paper-summary':print(json.dumps(summary(args.db),indent=2))

if __name__=='__main__':run()
