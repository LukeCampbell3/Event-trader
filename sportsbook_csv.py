"""Strict import of actual captured sportsbook over+under pairs from CSV.

This does NOT scrape and cannot establish a live price. Provider exports or
independently captured quotes must carry truthful timestamps and provenance.
"""
from __future__ import annotations
import csv
from pathlib import Path
from market_engine import SportsbookPair,read_contracts,dump_jsonl,parse_time

REQUIRED={'contract_id','sportsbook','captured_utc','american_yes','american_no','rule_id','quote_source'}

def import_pairs(csv_path, contracts_path, output_path):
    contracts={c.contract_id:c for c in read_contracts(contracts_path)}
    saved=[];rejected=[]
    with open(csv_path,newline='',encoding='utf8') as f:
        reader=csv.DictReader(f)
        if not REQUIRED <= set(reader.fieldnames or []):
            raise ValueError('missing required CSV fields: '+str(sorted(REQUIRED-set(reader.fieldnames or []))))
        for line,r in enumerate(reader,start=2):
            try:
                c=contracts[r['contract_id']]
                parse_time(r['captured_utc'])
                if r['rule_id'] != c.settlement_rule_id:raise ValueError('settlement mismatch')
                if not r['quote_source'].strip():raise ValueError('missing source')
                pair=SportsbookPair(r['contract_id'],r['sportsbook'].strip(),r['captured_utc'],
                    int(r['american_yes']),int(r['american_no']),r['rule_id'],r['quote_source'],
                    r.get('executable_confirmed','').lower() in ('true','1'))
                pair.probability()  # checks overround
                if not pair.sportsbook:raise ValueError('missing bookmaker')
                saved.append(pair)
            except (KeyError,ValueError) as ex:
                rejected.append({'line':line,'reason':str(ex)})
    dump_jsonl(output_path,[r.__dict__ for r in saved])
    return saved,rejected
