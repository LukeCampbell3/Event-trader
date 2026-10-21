"""Public, unauthenticated Kalshi NBA market-data capture and indicative replay.

Market catalogs and live order books are fetched from Kalshi's public Trade API.
Historical candles are explicitly INDICATIVE: candle OHLC data does not prove a
fillable order at that price. No order or authenticated endpoint is called.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import time
from time import monotonic, sleep
from contextlib import closing

import requests

from v9_research import ResearchStore

BASE = "https://api.elections.kalshi.com/trade-api/v2"
NBA_SERIES = ("KXNBAGAME", "KXNBAPTS", "KXNBAREB", "KXNBAAST", "KXNBAPRA", "KXNBAPA", "KXNBAPR", "KXNBARA")


class KalshiPublic:
    def __init__(self, session=None, timeout=20):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.last_request = 0.0

    def get(self, path, params=None):
        for attempt in range(6):
            wait = 0.2 - (monotonic() - self.last_request)
            if wait > 0: sleep(wait)
            response = self.session.get(BASE + path, params=params, timeout=self.timeout)
            self.last_request = monotonic()
            if response.status_code == 429 and attempt < 5:
                retry = response.headers.get("Retry-After")
                sleep(float(retry) if retry else min(2 ** attempt, 20))
                continue
            response.raise_for_status()
            return response.json()
        raise requests.HTTPError("Kalshi public API rate limit persisted after retries")

    def markets(self, series: str, status: str, limit: int = 1000):
        cursor = None
        found = []
        while True:
            params = {"series_ticker": series, "status": status, "limit": min(limit, 1000)}
            if cursor: params["cursor"] = cursor
            page = self.get("/markets", params)
            found.extend(page.get("markets", []))
            cursor = page.get("cursor")
            if not cursor or len(found) >= limit: break
        return found[:limit]

    def orderbook(self, ticker):
        return self.get(f"/markets/{ticker}/orderbook")

    def candles(self, series, ticker, start_ts, end_ts, interval=1):
        return self.get(f"/series/{series}/markets/{ticker}/candlesticks",
                        {"start_ts": start_ts, "end_ts": end_ts, "period_interval": interval})


def _id(*parts):
    return hashlib.sha256("|".join(str(x) for x in parts).encode()).hexdigest()


def _upsert_market(db_path, market, source="Kalshi"):
    ticker = market["ticker"]
    event_id = market.get("event_ticker")
    contract = f"{source}:{ticker}"
    meta = json.dumps(market, sort_keys=True)
    series = ticker.split("-",1)[0]
    stat = {"KXNBAPTS":"PTS","KXNBAREB":"REB","KXNBAAST":"AST","KXNBAPRA":"PRA","KXNBAPA":"PA","KXNBAPR":"PR","KXNBARA":"RA"}.get(series)
    kind = "player_prop" if stat else "game_winner" if series == "KXNBAGAME" else "unmapped"
    strike = market.get("floor_strike")
    threshold = float(strike)+0.5 if stat and strike is not None and market.get("strike_type")=="greater" else strike
    rules_text = "\n".join(x for x in (market.get("rules_primary"),market.get("rules_secondary")) if x)
    rules_hash = hashlib.sha256(rules_text.encode()).hexdigest() if rules_text else None
    custom = market.get("custom_strike") or {}
    player_id = custom.get("basketball_player")
    team_id = custom.get("basketball_team")
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("INSERT OR IGNORE INTO venues(venue_id,display_name,metadata_json) VALUES(?,?,?)",(source,source,"{}"))
        if event_id:
            db.execute("INSERT OR IGNORE INTO events(event_id,sport,start_utc,native_ids_json) VALUES(?,?,?,?)",
                       (f"{source}:{event_id}","NBA",None,json.dumps({"source":source,"native_event_id":event_id,"event_date":_native_date(event_id)})))
        if player_id:
            db.execute("INSERT OR IGNORE INTO players(player_id,display_name,native_ids_json) VALUES(?,?,?)",
                       (str(player_id),market.get("title","").split(":",1)[0],json.dumps({source:str(player_id)})))
        if team_id:
            db.execute("INSERT OR IGNORE INTO teams(team_id,display_name,native_ids_json) VALUES(?,?,?)",
                       (str(team_id),market.get("yes_sub_title"),json.dumps({source:str(team_id)})))
        if rules_hash:
            db.execute("INSERT OR IGNORE INTO contract_rules(rules_hash,source,rules_text,structured_json) VALUES(?,?,?,?)",
                       (rules_hash,source,rules_text,json.dumps({"rules_primary":market.get("rules_primary"),"rules_secondary":market.get("rules_secondary")})))
        db.execute("INSERT OR IGNORE INTO markets(market_id,source,native_market_id,canonical_event_id,contract_id,status,opened_utc,closed_utc,source_metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
                   (contract, source, ticker, None, contract, market.get("status"), market.get("open_time"), market.get("close_time"), meta))
        db.execute("INSERT OR IGNORE INTO contracts(contract_id,source,native_event_id,native_market_id,native_contract_id,player_id,team_id,stat,threshold,threshold_convention,outcome_side,rules_hash,rules_json,equivalence_status,market_kind,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (contract, source, event_id, ticker, ticker, player_id, team_id, stat, threshold,
                    "at_least" if stat and threshold is not None else None, "YES", rules_hash,
                    json.dumps({"rules_primary":market.get("rules_primary"),"rules_secondary":market.get("rules_secondary")} if rules_text else {}),
                    "UNVERIFIED", kind, meta))
        db.execute("INSERT OR IGNORE INTO data_quality_flags(flag_id,entity_type,entity_id,flagged_ts,severity,reason,details_json) VALUES(?,?,?,?,?,?,?)",
                   (_id(source,ticker,"canonical_unverified"),"market",ticker,datetime.now(timezone.utc).isoformat(),"INFO","NATIVE_MARKET_NOT_CANONICALLY_MATCHED",json.dumps({"source":source,"native_event_id":event_id})))
        return contract


def _native_date(event_id):
    match = re.search(r"-(\d{2}[A-Z]{3}\d{2})", event_id or "")
    if not match: return None
    try: return datetime.strptime(match.group(1), "%y%b%d").date().isoformat()
    except ValueError: return None


def capture_current(api: KalshiPublic, store: ResearchStore, series=NBA_SERIES,
                    max_markets=1000, pause=0.03):
    """Capture current L1 books. Data are venue-native; canonical event mapping is absent."""
    captured = datetime.now(timezone.utc).isoformat()
    markets_seen = books_saved = errors = 0
    per_series = {}
    for ticker in series:
        rows = api.markets(ticker, "open", max_markets)
        per_series[ticker] = len(rows)
        for market in rows:
            markets_seen += 1
            contract = _upsert_market(store.path, market)
            try:
                payload = api.orderbook(market["ticker"])
                book = payload.get("orderbook_fp") or payload.get("orderbook") or {}
                yes = book.get("yes_dollars") or book.get("yes") or []
                no = book.get("no_dollars") or book.get("no") or []
                yes_top = max(((float(p), float(q)) for p,q in yes), default=None)
                no_top = max(((float(p), float(q)) for p,q in no), default=None)
                if not yes_top or not no_top:
                    errors += 1; continue
                bid, _bid_qty = yes_top
                ask, ask_qty = 1.0-no_top[0], no_top[1]
                if not 0 <= bid <= ask <= 1:
                    errors += 1; continue
                raw = {"market": market, "orderbook": payload}
                quote_row = {
                    "source":"Kalshi", "native_event_id":market.get("event_ticker"),
                    "native_market_id":market["ticker"], "native_contract_id":market["ticker"],
                    "contract_id":contract, "bid":bid, "ask":ask, "quantity":ask_qty,
                    "observed_ts":captured, "exchange_ts":None, "capture_method":"public_trade_api_orderbook",
                    "price_kind":"EXECUTABLE", "provenance":"Kalshi public L2 book; local capture time; native contract not independently mapped",
                    "raw_json":raw}
                quote_row["quote_id"] = _id(json.dumps(quote_row,sort_keys=True))
                inserted = store.add_quote(quote_row)
                if inserted:
                    books_saved += 1
                    with closing(sqlite3.connect(store.path)) as db, db:
                        db.execute("PRAGMA foreign_keys=ON")
                        db.execute("INSERT OR IGNORE INTO orderbook_snapshots(snapshot_id,quote_id,bids_json,asks_json,captured_ts) VALUES(?,?,?,?,?)",
                                   (_id(market["ticker"],captured), quote_row["quote_id"], json.dumps(yes), json.dumps(no), captured))
            except (requests.RequestException, ValueError, KeyError, TypeError):
                errors += 1
            if pause: time.sleep(pause)
    return {"captured_utc":captured,"source":"Kalshi public Trade API","series_counts":per_series,
            "markets_seen":markets_seen,"book_quotes_inserted":books_saved,"errors":errors,
            "canonical_event_matches":0,"credentials_used":False}


def capture_settled_candles(api: KalshiPublic, store: ResearchStore, series=("KXNBAGAME",),
                            limit_per_series=250, lookback_hours=6, pause=0.03,
                            full_from_open=False, interval=1):
    """Fetch recent settled-market candles and venue settlement labels.

    Candle prices are indicative; settlement labels are source-provided, not
    independently checked against official NBA box scores.
    """
    captured = datetime.now(timezone.utc).isoformat()
    markets_seen = candles_saved = settled = errors = 0
    range_end = int(datetime.now(timezone.utc).timestamp())
    for series_ticker in series:
        for market in api.markets(series_ticker, "settled", limit_per_series):
            markets_seen += 1
            contract = _upsert_market(store.path, market)
            close = market.get("close_time") or market.get("expiration_time")
            if full_from_open and market.get("open_time"):
                open_dt = datetime.fromisoformat(market["open_time"].replace("Z", "+00:00"))
                start_ts = int(open_dt.timestamp())
                end_ts = int(datetime.fromisoformat(close.replace("Z", "+00:00")).timestamp()) if close else range_end
            elif close:
                close_dt = datetime.fromisoformat(close.replace("Z", "+00:00"))
                end_ts = int(close_dt.timestamp())
                start_ts = max(end_ts-int(timedelta(hours=lookback_hours).total_seconds()), 0)
            else:
                end_ts, start_ts = range_end, range_end-int(timedelta(hours=lookback_hours).total_seconds())
            outcome = 1 if market.get("result") == "yes" else 0 if market.get("result") == "no" else None
            if outcome is not None:
                with closing(sqlite3.connect(store.path)) as db, db:
                    settlement_ts=market.get("settlement_ts") or close or captured
                    db.execute("INSERT OR IGNORE INTO settlements(contract_id,settled_ts,outcome,source,native_settlement_id,provenance,raw_json) VALUES(?,?,?,?,?,?,?)",
                               (contract, settlement_ts, outcome, "Kalshi", market.get("ticker"),
                                "Kalshi market result field; not independently verified with NBA official results", json.dumps(market,sort_keys=True)))
                    settled += db.total_changes
            try:
                response = api.candles(series_ticker, market["ticker"], start_ts, end_ts, interval=interval)
                for candle in response.get("candlesticks", []):
                    yes_bid = candle.get("yes_bid", {}).get("close_dollars")
                    yes_ask = candle.get("yes_ask", {}).get("close_dollars")
                    end_period = candle.get("end_period_ts")
                    if yes_bid is None or yes_ask is None or end_period is None: continue
                    exchange_ts = datetime.fromtimestamp(int(end_period),timezone.utc).isoformat()
                    try:
                        inserted = store.add_quote({
                            "source":"Kalshi", "native_event_id":market.get("event_ticker"),
                            "native_market_id":market["ticker"], "native_contract_id":market["ticker"],
                            "contract_id":contract,"bid":float(yes_bid),"ask":float(yes_ask),
                            "quantity":None,"exchange_ts":exchange_ts,"observed_ts":captured,
                            "capture_method":f"public_historical_candlesticks_interval_{interval}m",
                            "price_kind":"INDICATIVE","provenance":"Kalshi public OHLC close prices; candle snapshots are not proof of executable fills",
                            "raw_json":candle})
                        candles_saved += int(inserted)
                    except ValueError: errors += 1
            except requests.RequestException:
                errors += 1
            if pause: time.sleep(pause)
    return {"captured_utc":captured,"source":"Kalshi public Trade API","series":list(series),
            "settled_markets_seen":markets_seen,"indicative_candles_inserted":candles_saved,
            "venue_settlements_seen":settled,"errors":errors,
            "official_outcome_verification":False,"execution_class":"INDICATIVE"}


def hydrate_normalized_catalog(store: ResearchStore):
    """Idempotently derive source-native event/participant/rule rows from raw markets."""
    with closing(sqlite3.connect(store.path)) as db, db:
        raw = [x[0] for x in db.execute("SELECT source_metadata_json FROM markets ORDER BY market_id")]
    for payload in raw:
        _upsert_market(store.path,json.loads(payload))
    return {"native_markets_hydrated":len(raw),"canonical_event_matches":0,
            "status":"native identifiers only; cross-market equivalence remains unverified"}


def main():
    parser = argparse.ArgumentParser(description="Capture public Kalshi NBA research data (read-only)")
    sub = parser.add_subparsers(dest="command",required=True)
    p = sub.add_parser("current"); p.add_argument("--db",default="data/raw/v9_markets.sqlite3"); p.add_argument("--max-per-series",type=int,default=1000)
    h = sub.add_parser("history"); h.add_argument("--db",default="data/raw/v9_markets.sqlite3"); h.add_argument("--series",nargs="*",default=["KXNBAGAME"]); h.add_argument("--limit-per-series",type=int,default=250); h.add_argument("--lookback-hours",type=int,default=6); h.add_argument("--full-from-open",action="store_true"); h.add_argument("--interval-minutes",type=int,choices=[1,60,1440],default=1)
    n = sub.add_parser("hydrate"); n.add_argument("--db",default="data/raw/v9_markets.sqlite3")
    args = parser.parse_args(); store = ResearchStore(args.db); api = KalshiPublic()
    if args.command=="current": result=capture_current(api,store,max_markets=args.max_per_series)
    elif args.command=="history": result=capture_settled_candles(api,store,args.series,args.limit_per_series,args.lookback_hours,full_from_open=args.full_from_open,interval=args.interval_minutes)
    else: result=hydrate_normalized_catalog(store)
    print(json.dumps(result,indent=2))

if __name__ == "__main__": main()
