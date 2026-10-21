import sys
import tempfile
import unittest
from pathlib import Path
import sqlite3
from contextlib import closing

sys.path.insert(0,str(Path(__file__).parents[1]))
from kalshi_public import KalshiPublic, capture_current
from v9_research import ResearchStore


class FakeKalshi:
    def markets(self,series,status,limit):
        if series!="KXNBAGAME": return []
        return [{"ticker":"KXNBAGAME-26OCT30BOSNYK-BOS","event_ticker":"KXNBAGAME-26OCT30BOSNYK",
                 "status":"active","open_time":"2026-10-21T10:00:00Z","close_time":"2026-10-30T23:00:00Z",
                 "title":"Boston wins","yes_sub_title":"Boston","custom_strike":{"basketball_team":"team-1"},
                 "rules_primary":"Boston wins.","rules_secondary":"Full game.","result":""}]
    def orderbook(self,ticker):
        return {"orderbook_fp":{"yes_dollars":[["0.40","5"]],"no_dollars":[["0.55","7"]]}}


class KalshiIngestionTests(unittest.TestCase):
    def test_l2_ingestion_populates_native_entities_and_depth(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"v9.db"; store=ResearchStore(path)
            result=capture_current(FakeKalshi(),store,series=("KXNBAGAME","KXNBAPTS"),max_markets=5,pause=0)
            self.assertEqual(result["book_quotes_inserted"],1)
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(db.execute("select count(*) from events").fetchone()[0],1)
                self.assertEqual(db.execute("select count(*) from contract_rules").fetchone()[0],1)
                self.assertEqual(db.execute("select bid,ask,quantity,price_kind from quotes").fetchone(),(.4,.44999999999999996,7.0,"EXECUTABLE"))
                self.assertEqual(db.execute("select count(*) from orderbook_snapshots").fetchone()[0],1)


class RetryTests(unittest.TestCase):
    def test_non_429_http_error_is_not_retried(self):
        class Response:
            status_code=503
            headers={}
            def raise_for_status(self): raise RuntimeError("server failure")
        class Session:
            calls=0
            def get(self,*a,**k): self.calls+=1; return Response()
        session=Session(); api=KalshiPublic(session=session)
        with self.assertRaises(RuntimeError): api.get("/markets")
        self.assertEqual(session.calls,1)

    def test_rate_limit_retries_using_retry_after(self):
        class Response:
            def __init__(self,status): self.status_code=status; self.headers={"Retry-After":"0"}
            def raise_for_status(self):
                if self.status_code>=400: raise RuntimeError("HTTP error")
            def json(self): return {"markets":[]}
        class Session:
            calls=0
            def get(self,*a,**k):
                self.calls+=1
                return Response(429 if self.calls==1 else 200)
        session=Session();api=KalshiPublic(session=session)
        self.assertEqual(api.get("/markets"),{"markets":[]})
        self.assertEqual(session.calls,2)


if __name__=="__main__":unittest.main()
