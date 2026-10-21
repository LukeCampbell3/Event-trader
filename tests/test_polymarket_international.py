import sys
import tempfile
import unittest
from pathlib import Path
import sqlite3
from contextlib import closing

sys.path.insert(0,str(Path(__file__).parents[1]))
from polymarket_international import capture, parse_book
from v9_research import ResearchStore


class Response:
    def raise_for_status(self): pass
    def json(self): return {"bids":[{"price":"0.40","size":"10"},{"price":"0.42","size":"5"}],
                            "asks":[{"price":"0.46","size":"3"},{"price":"0.46","size":"4"},{"price":"0.47","size":"10"}]}


class Session:
    def get(self,*args,**kwargs): return Response()


class PolymarketInternationalTests(unittest.TestCase):
    def test_orderbook_parser_uses_best_levels_and_depth(self):
        q=parse_book("C","E","M","T",Response().json(),"2026-10-21T12:00:00Z")
        self.assertEqual((q["bid"],q["ask"],q["quantity"]),(.42,.46,7.0))
        self.assertEqual(q["source"],"Polymarket_International")

    def test_only_explicit_reviewed_mapping_is_ingested(self):
        with tempfile.TemporaryDirectory() as d:
            manifest=Path(d)/"map.csv"
            manifest.write_text("contract_id,canonical_event_id,native_event_id,native_market_id,token_id,token_outcome_side,participant_id,market_kind,stat,threshold,threshold_convention,period,overtime,rules_verified,reviewed,resolution_rules\n"
                "C1,E1,NATIVE_E,M1,T1,YES,player-1,player_prop,PTS,25,at_least,full_game,true,true,true,Full game points incl OT\n"
                "C2,E2,NATIVE_E2,M2,T2,YES,player-2,player_prop,REB,10,at_least,full_game,true,false,false,Unreviewed\n",encoding="utf-8")
            dbpath=Path(d)/"store.db"
            result=capture(str(manifest),str(dbpath),session=Session())
            self.assertEqual(result["books_inserted"],1)
            self.assertEqual(len(result["rejected"]),1)
            with closing(sqlite3.connect(dbpath)) as db,db:
                self.assertEqual(db.execute("select source,native_contract_id,outcome_side,quantity from quotes").fetchone(),("Polymarket_International","T1","YES",7.0))
                self.assertEqual(db.execute("select equivalence_status from contracts").fetchone()[0],"REVIEWED")

    def test_crossed_book_rejected(self):
        with self.assertRaises(ValueError):
            parse_book("C","E","M","T",{"bids":[{"price":"0.6","size":"1"}],"asks":[{"price":"0.5","size":"1"}]},"2026-10-21T12:00:00Z")


if __name__=="__main__":unittest.main()
