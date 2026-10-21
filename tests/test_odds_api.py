import sys
import tempfile
import unittest
from pathlib import Path
import sqlite3
from contextlib import closing
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]))
from odds_api import OddsAPI, ingest_payload
from v9_research import ResearchStore


class OddsApiTests(unittest.TestCase):
    def test_missing_key_fails_without_network(self):
        with patch.dict("os.environ",{"ODDS_API_KEY":""},clear=False):
            with self.assertRaises(ValueError): OddsAPI(api_key=None)

    def test_two_sided_player_prop_is_attributed_and_not_canonicalized(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"research.db";store=ResearchStore(path)
            events=[{"id":"event-1","commence_time":"2026-10-21T23:00:00Z","home_team":"A","away_team":"B"}]
            payload=[{"id":"event-1","bookmakers":[{"key":"fanduel","last_update":"2026-10-21T12:00:00Z","markets":[{"key":"player_points","last_update":"2026-10-21T12:01:00Z","outcomes":[{"name":"Over","description":"Player X","price":-110,"point":24.5},{"name":"Under","description":"Player X","price":105,"point":24.5}]}]}]}]
            result=ingest_payload(store,events,"2026-10-21T12:02:00Z",payload)
            self.assertEqual(result["sportsbook_outcomes_inserted"],2)
            with closing(sqlite3.connect(path)) as db, db:
                rows=db.execute("SELECT stat,threshold,outcome_side,american_odds,decimal_odds,exchange_ts,contract_id FROM sportsbook_lines ORDER BY outcome_side").fetchall()
            self.assertEqual(rows[0][0:4],("PTS",24.5,"OVER",-110))
            self.assertAlmostEqual(rows[0][4],1+100/110)
            self.assertEqual(rows[0][5],"2026-10-21T12:01:00+00:00")
            self.assertIsNone(rows[0][6])
            self.assertEqual(rows[1][2:4],("UNDER",105))
            self.assertAlmostEqual(rows[1][4],2.05)


if __name__=="__main__":unittest.main()
