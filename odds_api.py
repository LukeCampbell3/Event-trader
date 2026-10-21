"""Optional free-tier The Odds API reader for current NBA sportsbook odds.

Read-only. API keys are read from ODDS_API_KEY and are never printed or stored.
Free plans can collect current prices; the provider documents historical odds as
paid-plan-only, so this adapter does not claim free historical sportsbook data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing

import requests

from v9_research import ResearchStore, utc

BASE="https://api.the-odds-api.com/v4"
SPORT="basketball_nba"
STAT_KEYS={"player_points":"PTS","player_rebounds":"REB","player_assists":"AST","player_threes":"3PM",
           "player_points_rebounds":"PR","player_points_assists":"PA","player_rebounds_assists":"RA",
           "player_points_rebounds_assists":"PRA"}


class OddsAPIError(RuntimeError):
    """Sanitized network error; provider URLs can contain the API key."""


class OddsAPI:
    def __init__(self, api_key=None, session=None, timeout=20):
        self.api_key=api_key or os.environ.get("ODDS_API_KEY")
        if not self.api_key: raise ValueError("ODDS_API_KEY is not set; obtain the provider's free key and set it in the environment")
        self.session=session or requests.Session(); self.timeout=timeout

    def get(self,path,params=None):
        query=dict(params or {});query["apiKey"]=self.api_key
        try: response=self.session.get(BASE+path,params=query,timeout=self.timeout)
        except requests.RequestException as exc: raise OddsAPIError("network failure; URL redacted") from None
        if response.status_code>=400: raise OddsAPIError(f"provider returned HTTP {response.status_code}; URL redacted")
        return response.json(),dict(response.headers)

    def events(self): return self.get(f"/sports/{SPORT}/events",{})

    def current_game_odds(self, markets="h2h,spreads,totals", regions="us"):
        return self.get(f"/sports/{SPORT}/odds",{"regions":regions,"markets":markets,"oddsFormat":"american"})

    def current_event_props(self,event_id,markets,regions="us"):
        return self.get(f"/sports/{SPORT}/events/{event_id}/odds",{"regions":regions,"markets":markets,"oddsFormat":"american"})


def _line_id(*parts):return hashlib.sha256("|".join(str(x) for x in parts).encode()).hexdigest()


def ingest_payload(store: ResearchStore, events: list[dict], observed_ts: str,
                   source_payloads: list[dict] | None = None):
    """Persist bookmaker two-sided outcomes without guessing canonical matches."""
    observed=utc(observed_ts).isoformat(); event_by_id={str(e.get("id")):e for e in events if e.get("id")}
    lines=0; event_count=0
    with closing(sqlite3.connect(store.path)) as db, db:
        for event in events:
            event_id=str(event.get("id") or "")
            if not event_id: continue
            start=event.get("commence_time")
            if start: start=utc(start).isoformat()
            db.execute("INSERT OR IGNORE INTO events(event_id,sport,start_utc,home_team_id,away_team_id,native_ids_json) VALUES(?,?,?,?,?,?)",
                       (f"TheOddsAPI:{event_id}","NBA",start,None,None,json.dumps({"source":"TheOddsAPI","native_event_id":event_id,"home_team":event.get("home_team"),"away_team":event.get("away_team")})))
            event_count+=1
        for payload in source_payloads or []:
            eid=str(payload.get("id") or "")
            if eid not in event_by_id: continue
            for bookmaker in payload.get("bookmakers",[]):
                book=str(bookmaker.get("key") or bookmaker.get("title") or "unknown")
                for market in bookmaker.get("markets",[]):
                    key=market.get("key");stat=STAT_KEYS.get(key,key)
                    ex_ts=market.get("last_update") or bookmaker.get("last_update")
                    try: ex_ts=utc(ex_ts).isoformat() if ex_ts else None
                    except ValueError: ex_ts=None
                    outcomes=market.get("outcomes",[])
                    for outcome in outcomes:
                        price=outcome.get("price")
                        if price is None or float(price)==0: continue
                        name=str(outcome.get("name") or "")
                        desc=str(outcome.get("description") or "")
                        side=name.upper() if name.lower() in {"over","under"} else name
                        point=outcome.get("point")
                        row_raw={"event":event_by_id[eid],"bookmaker":bookmaker,"market":market,"outcome":outcome}
                        identifier=_line_id("TheOddsAPI",book,eid,key,desc,point,side,price,ex_ts)
                        dec=(1+float(price)/100) if float(price)>0 else (1+100/abs(float(price)))
                        cursor=db.execute("INSERT OR IGNORE INTO sportsbook_lines(line_id,source,sportsbook,native_event_id,contract_id,stat,threshold,outcome_side,american_odds,decimal_odds,exchange_ts,observed_ts,provenance,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (identifier,"TheOddsAPI",book,eid,None,stat,float(point) if point is not None else None,side,
                             int(price) if float(price).is_integer() else None,dec,ex_ts,observed,
                             "The Odds API provider quote; no canonical contract mapping; source timestamp retained",
                             json.dumps(row_raw,sort_keys=True)))
                        lines+=cursor.rowcount
    return {"provider_events":event_count,"sportsbook_outcomes_inserted":lines,"canonical_contract_matches":0}


def collect(store: ResearchStore, api: OddsAPI, include_props=False, max_events=4,
            prop_markets="player_points,player_rebounds,player_assists,player_threes,player_points_rebounds_assists"):
    observed=datetime.now(timezone.utc).isoformat()
    events,headers=api.events()
    if isinstance(events,dict): events=events.get("events",[])
    selected=events[:max_events]
    responses=[]
    if not include_props:
        response,odds_headers=api.current_game_odds()
        responses.append((response,odds_headers))
    else:
        for event in selected:
            response,odds_headers=api.current_event_props(event["id"],prop_markets)
            responses.append((response,odds_headers))
    payloads=[]
    for response,_ in responses:
        if isinstance(response,dict): payloads.append(response)
        else: payloads.extend(response)
    result=ingest_payload(store,events,observed,payloads)
    return {"captured_utc":observed,"source":"The Odds API","markets_mode":"NBA player props" if include_props else "game odds",
            **result,"api_key_used":True,"raw_payload_saved":True,
            "quota_remaining_headers":[h.get("x-requests-remaining") for _,h in responses if h.get("x-requests-remaining") is not None]}


def main():
    parser=argparse.ArgumentParser(description="Capture current NBA sportsbook quotes using a configured free-tier Odds API key")
    parser.add_argument("--db",default="data/raw/v9_markets.sqlite3");parser.add_argument("--include-props",action="store_true");parser.add_argument("--max-events",type=int,default=4)
    parser.add_argument("--prop-markets",default="player_points,player_rebounds,player_assists,player_threes,player_points_rebounds_assists")
    a=parser.parse_args()
    try:
        result=collect(ResearchStore(a.db),OddsAPI(),a.include_props,a.max_events,a.prop_markets)
        print(json.dumps(result,indent=2))
    except ValueError as exc: print(f"CONFIGURATION_ERROR: {exc}")
    except OddsAPIError as exc: print(f"ODDS_API_REQUEST_FAILED: {exc}")

if __name__=="__main__":main()
