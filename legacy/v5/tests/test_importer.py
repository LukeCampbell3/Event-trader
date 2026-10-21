import json,unittest
from pathlib import Path
from datetime import datetime,timezone
from propline_free import parse,utc
from joint_engine import sync_status,read_quotes
from import_propline import main as cli_main
from unittest.mock import patch
import tempfile

ROOT=Path(__file__).resolve().parents[1]
class ImporterTests(unittest.TestCase):
    def test_saved_provider_paired_prices(self):
        payload=json.loads((ROOT/'data/SYNTHETIC_PROP_PROVIDER_RESPONSE_NOT_REAL.json').read_text())
        paired,audit=parse(payload,as_of=utc('2026-10-20T21:00:00Z'),max_age_minutes=15)
        self.assertEqual(len(paired),3)
        self.assertEqual(audit['paired_rows'],3)
        self.assertEqual({r['market'] for r in paired},{'P'})
        self.assertTrue(all('captured_at' in r for r in paired))
    def test_import_cli_rejects_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'quotes.csv'
            args=['import_propline.py','--saved-json',str(ROOT/'data/SYNTHETIC_PROP_PROVIDER_RESPONSE_NOT_REAL.json'),
                  '--asof','2026-10-20T22:00:00Z','--max-age-minutes','10','--output',str(out)]
            with patch('sys.argv',args):cli_main()
            quotes,issues=read_quotes(out)
            self.assertEqual(len(quotes),0)
    def test_import_cli_keeps_snapshot_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'quotes.csv'
            args=['import_propline.py','--saved-json',str(ROOT/'data/SYNTHETIC_PROP_PROVIDER_RESPONSE_NOT_REAL.json'),
                  '--asof','2026-10-20T21:00:00Z','--output',str(out)]
            with patch('sys.argv',args):cli_main()
            q,issues=read_quotes(out)
            self.assertEqual(len(q),3)
            self.assertEqual(sync_status(q,asof='2026-10-20T21:00:00Z'),'SYNCHRONIZED_PREGAME')
if __name__=='__main__':unittest.main()
