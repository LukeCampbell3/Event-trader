"""Read-only Polymarket international CLOB L2 capture via explicit mappings.

This adapter is deliberately separate from Polymarket US. It will not search or
fuzzy-map markets: only rows explicitly reviewed in a manifest are queried.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import hashlib
import json
import sqlite3
from contextlib import closing

import requests

from v9_research import ResearchStore

CLOB="https://clob.polymarket.com"


def _digest(value):return hashlib.sha256(str(value).encode()).hexdigest()
def _flag(value):return 1 if str(value).strip().lower() in {"1","true","yes"} else 0


def parse_book(contract_id: str, native_event_id: str, native_market_id: str,
               token_id: str, book: dict, observed_ts: str, outcome_side="YES"):
    bids=book.get("bids") or []; asks=book.get("asks") or []
    if not bids or not asks: raise ValueError("one-sided or empty CLOB book")
    bid_price=max(float(x["price"]) for x in bids)
    ask_price=min(float(x["price"]) for x in asks)
    if not 0 < bid_price <= ask_price < 1: raise ValueError("invalid or crossed CLOB book")
    ask_depth=sum(float(x["size"]) for x in asks if abs(float(x["price"])-ask_price)<1e-12)
    if ask_depth <= 0: raise ValueError("no positive displayed ask depth")
    return {"quote_id":_digest("polymarket-intl|"+token_id+"|"+observed_ts),
            "source":"Polymarket_International","native_event_id":native_event_id,
            "native_market_id":native_market_id,"native_contract_id":token_id,
            "contract_id":contract_id,"outcome_side":outcome_side,"bid":bid_price,"ask":ask_price,"quantity":ask_depth,
            "observed_ts":observed_ts,"exchange_ts":None,"capture_method":"public_clob_l2",
            "price_kind":"EXECUTABLE","provenance":"Polymarket international public CLOB; local capture timestamp; native contract manually reviewed",
            "raw_json":book}


def _ingest_mapping(store: ResearchStore,row:dict):
    source="Polymarket_International"; cid=row["contract_id"]; eid=row["canonical_event_id"]
    native_event=row["native_event_id"]; native_market=row["native_market_id"]
    rules=row["resolution_rules"]; rule_hash=_digest(rules)
    metadata={k:v for k,v in row.items() if k not in {"resolution_rules"}}
    with closing(sqlite3.connect(store.path)) as db,db:
        db.execute("INSERT OR IGNORE INTO events(event_id,sport,native_ids_json) VALUES(?,?,?)",
                   (eid,"NBA",json.dumps({source:native_event,"reviewed":True})))
        db.execute("INSERT OR IGNORE INTO contract_rules(rules_hash,source,rules_text,structured_json) VALUES(?,?,?,?)",
                   (rule_hash,source,rules,json.dumps({"reviewed":True})))
        db.execute("INSERT OR IGNORE INTO contracts(contract_id,source,native_event_id,native_market_id,native_contract_id,canonical_event_id,player_id,stat,threshold,threshold_convention,outcome_side,period,overtime,rules_hash,rules_json,equivalence_status,market_kind,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid,source,native_event,native_market,row["token_id"],eid,row.get("participant_id") or None,
             row.get("stat") or None,float(row["threshold"]) if row.get("threshold") else None,
             row.get("threshold_convention") or None,row["token_outcome_side"].upper(),row.get("period") or None,
             _flag(row.get("overtime")),rule_hash,json.dumps({"resolution_rules":rules}),"REVIEWED",row.get("market_kind") or "unknown",json.dumps(metadata,sort_keys=True)))
        db.execute("INSERT OR IGNORE INTO markets(market_id,source,native_market_id,canonical_event_id,contract_id,status,source_metadata_json) VALUES(?,?,?,?,?,?,?)",
                   (f"{source}:{native_market}",source,native_market,eid,cid,"open",json.dumps(metadata,sort_keys=True)))


def capture(manifest: str,db_path: str,session=None,timeout=20):
    store=ResearchStore(db_path)
    with open(manifest,newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
    captured=datetime.now(timezone.utc).isoformat(); quotes=[]; rejected=[]
    client=session or requests.Session()
    for row in rows:
        try:
            if row.get("reviewed","").lower()!="true" or row.get("rules_verified","").lower()!="true":
                raise ValueError("mapping and settlement rules must be manually reviewed")
            required=("contract_id","canonical_event_id","native_event_id","native_market_id","token_id","token_outcome_side","resolution_rules")
            if any(not row.get(k) for k in required): raise ValueError("missing required exact mapping field")
            if row["token_outcome_side"].upper() not in {"YES","NO"}: raise ValueError("token_outcome_side must be YES or NO")
            _ingest_mapping(store,row)
            response=client.get(CLOB+"/book",params={"token_id":row["token_id"]},timeout=timeout)
            response.raise_for_status(); payload=response.json()
            quote=parse_book(row["contract_id"],row["native_event_id"],row["native_market_id"],row["token_id"],payload,captured,row["token_outcome_side"].upper())
            if store.add_quote(quote):
                quotes.append(quote)
                with closing(sqlite3.connect(db_path)) as db,db:
                    db.execute("INSERT OR IGNORE INTO orderbook_snapshots(snapshot_id,quote_id,bids_json,asks_json,captured_ts) VALUES(?,?,?,?,?)",
                               (_digest(row["token_id"]+captured),quote["quote_id"],json.dumps(payload.get("bids",[])),json.dumps(payload.get("asks",[])),captured))
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
            # Public CLOB URLs contain no credentials. Rejections remain specific
            # but raw response/error objects are not copied into the database.
            rejected.append({"contract_id":row.get("contract_id"),"reason":str(exc)})
    return {"captured_utc":captured,"venue":"Polymarket international","books_inserted":len(quotes),
            "rejected":rejected,"auth_used":False,"cross_venue_equivalences_inferred":0}


def main():
    p=argparse.ArgumentParser(description="Capture only manually reviewed Polymarket international CLOB contracts")
    p.add_argument("--manifest",required=True);p.add_argument("--db",default="data/raw/v9_markets.sqlite3")
    a=p.parse_args();print(json.dumps(capture(a.manifest,a.db),indent=2))

if __name__=="__main__":main()
