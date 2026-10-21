import json,unittest
from pathlib import Path
from nba_boxscore_free import parse_final_boxscore
ROOT=Path(__file__).resolve().parents[1]
class BoxscoreTests(unittest.TestCase):
    def test_official_format_only_final(self):
        fixture=json.loads((ROOT/'data/SYNTHETIC_NBA_FINAL_BOXSCORE_NOT_REAL.json').read_text())
        parsed=parse_final_boxscore(fixture,'SYN@SYN_2026-10-22','0022600001')
        self.assertEqual(parsed[0]['P'],13)
        self.assertEqual(parsed[0]['R'],7)
        self.assertEqual(parsed[0]['A'],4)
        fixture['game']['gameStatus']=2
        with self.assertRaisesRegex(ValueError,'incomplete'):
            parse_final_boxscore(fixture,'SYN@SYN_2026-10-22','0022600001')
    def test_mismatched_id_rejected(self):
        fixture=json.loads((ROOT/'data/SYNTHETIC_NBA_FINAL_BOXSCORE_NOT_REAL.json').read_text())
        with self.assertRaisesRegex(ValueError,'mismatch'):
            parse_final_boxscore(fixture,'SYN@SYN_2026-10-22','0022600002')
if __name__=='__main__':unittest.main()
