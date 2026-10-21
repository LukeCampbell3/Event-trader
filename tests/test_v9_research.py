import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from v9_research import MarketIdentity, ResearchStore, canonical_threshold, compare_contracts, replay_decisions, probability_motion


class V9ResearchTests(unittest.TestCase):
    def test_equivalent_threshold_conventions(self):
        self.assertEqual(canonical_threshold("PTS", "at_least", 25), 25)
        self.assertEqual(canonical_threshold("PTS", "over", 24.5), 25)
        self.assertEqual(canonical_threshold("PTS", "over", 25.5), 26)

    def test_rule_mismatch_fails_equivalence(self):
        fields = dict(sport="NBA", event_date="2026-10-21", participant_id="p1", stat="PTS",
                      threshold=24.5, convention="over", period="full_game", overtime=True,
                      void_rule_id="void-a", participation_rule_id="dnp-void")
        a = MarketIdentity.player_prop(**fields)
        b = MarketIdentity.player_prop(**{**fields, "void_rule_id":"void-b"})
        self.assertFalse(compare_contracts(a,b)["equivalent"])
        self.assertIn("void_rule_id", compare_contracts(a,b)["differences"])

    def test_quote_timestamp_order_and_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            store = ResearchStore(Path(d)/"research.db")
            row = dict(source="Kalshi",native_market_id="M1",contract_id="C1",bid=.4,ask=.5,quantity=10,
                       exchange_ts="2026-10-21T12:00:00Z",observed_ts="2026-10-21T12:00:01Z",
                       price_kind="EXECUTABLE",provenance="test")
            self.assertTrue(store.add_quote(row))
            self.assertFalse(store.add_quote(row))
            bad = {**row,"native_market_id":"M2","exchange_ts":"2026-10-21T12:00:02Z"}
            with self.assertRaises(ValueError): store.add_quote(bad)

    def test_replay_excludes_future_quotes_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            store = ResearchStore(Path(d)/"research.db")
            base = dict(source="Kalshi",contract_id="C1",bid=.4,ask=.5,quantity=10,
                        exchange_ts="2026-10-21T12:00:00Z",price_kind="EXECUTABLE",provenance="test")
            store.add_quote({**base,"native_market_id":"M1","observed_ts":"2026-10-21T12:00:01Z"})
            store.add_quote({**base,"native_market_id":"M1","bid":.45,"ask":.55,
                             "exchange_ts":"2026-10-21T12:10:00Z","observed_ts":"2026-10-21T12:10:01Z"})
            result = replay_decisions(store,["2026-10-21T12:05:00Z"])
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]["ask"],.5)
            self.assertEqual(result,replay_decisions(store,["2026-10-21T12:05:00Z"]))
            self.assertEqual(result[0]["replay_class"],"EXECUTABLE")

    def test_indicative_never_counts_as_executable(self):
        with tempfile.TemporaryDirectory() as d:
            store = ResearchStore(Path(d)/"research.db")
            store.add_quote(dict(source="Kalshi",native_market_id="M1",contract_id="C1",bid=.4,ask=.5,
                                 quantity=None,exchange_ts="2026-10-21T12:00:00Z",
                                 observed_ts="2026-10-21T12:00:01Z",price_kind="INDICATIVE",provenance="candle"))
            result = replay_decisions(store,["2026-10-21T12:00:02Z"])
            self.assertEqual(result[0]["replay_class"],"INDICATIVE_OR_RESEARCH")

    def test_motion_marks_synchronized_convergence(self):
        rows=[]
        for minute,pa,pb in [(0,.50,.70),(1,.52,.68),(2,.55,.65)]:
            stamp=f"2026-10-21T12:0{minute}:00Z"
            rows.extend([{"contract_id":"C","source":"A","probability":pa,"timestamp":stamp},
                         {"contract_id":"C","source":"B","probability":pb,"timestamp":stamp}])
        result=probability_motion(rows)[0]
        self.assertTrue(result["synchronized_for_dispersion_change"])
        self.assertTrue(result["convergence"])
        self.assertFalse(result["divergence"])
        self.assertIsNotNone(result["venue_signals"][0]["latest"]["acceleration_per_second2"])


if __name__ == "__main__": unittest.main()
