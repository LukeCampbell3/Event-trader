import sys, unittest, tempfile, json, copy
from pathlib import Path
from datetime import datetime,timezone,timedelta
sys.path.insert(0,str(Path(__file__).parents[1]))
from market_engine import *
from make_fixture import make
from us_feed import parse_us_book, capture_us
from recording import record_paper,settle,summary
from live_guard import arm_check,send_live_order,LiveOrderBlocked

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cs,self.qs,self.refs,self.asof=make(self.tmp.name)
    def run_screen(self,qs=None,refs=None,cs=None,cfg=None,asof=None):
        return evaluate(cs if cs is not None else self.cs, qs if qs is not None else self.qs,
                        refs if refs is not None else self.refs, asof or self.asof,cfg or ScreenConfig())
    def find(self,x,id):return next(z for z in x if z['contract_id']==id)
    def test_devig(self):self.assertAlmostEqual(devig_two_way(-110,-110),.5)
    def test_bad_overround(self):
        with self.assertRaises(ValueError):devig_two_way(-10000,-10000)
    def test_screen_finds_planted_error_conditional(self):
        x=self.find(self.run_screen(),'TEST_PLAYER_A_POINTS25')
        self.assertTrue(x['screen_pass']);self.assertFalse(x['executable_edge_verified']);self.assertGreater(x['roi_lower_conditional'],4)
    def test_no_edge_on_fair_ask(self):
        x=self.find(self.run_screen(),'TEST_GAME_A_WIN');self.assertFalse(x['screen_pass'])
    def test_rules_fail_closed(self):
        x=self.find(self.run_screen(),'TEST_UNREVIEWED');self.assertFalse(x['screen_pass']);self.assertIn('unverified_resolution_rules',x['reasons'])
    def test_quote_stale(self):
        q=[ExchangeQuote(**{**x.__dict__,'captured_utc':'2026-10-20T01:00:00+00:00'}) if x.contract_id=='TEST_PLAYER_A_POINTS25' else x for x in self.qs]
        x=self.find(self.run_screen(qs=q),'TEST_PLAYER_A_POINTS25');self.assertFalse(x['screen_pass']);self.assertIn('stale_or_future_exchange_quote',x['reasons'])
    def test_quote_in_future(self):
        q=[ExchangeQuote(**{**x.__dict__,'captured_utc':'2026-10-21T12:40:00+00:00'}) if x.contract_id=='TEST_PLAYER_A_POINTS25' else x for x in self.qs]
        self.assertFalse(self.find(self.run_screen(qs=q),'TEST_PLAYER_A_POINTS25')['screen_pass'])
    def test_liquidity(self):
        q=[ExchangeQuote(**{**x.__dict__,'yes_ask_depth':0}) if x.contract_id=='TEST_PLAYER_A_POINTS25' else x for x in self.qs]
        self.assertIn('insufficient_depth',self.find(self.run_screen(qs=q),'TEST_PLAYER_A_POINTS25')['reasons'])
    def test_spread(self):
        q=[ExchangeQuote(**{**x.__dict__,'yes_bid':.1}) if x.contract_id=='TEST_PLAYER_A_POINTS25' else x for x in self.qs]
        self.assertIn('wide_spread',self.find(self.run_screen(qs=q),'TEST_PLAYER_A_POINTS25')['reasons'])
    def test_one_book_fail(self):
        r=[x for x in self.refs if x.sportsbook=='bookA']
        self.assertIn('insufficient_independent_paired_books',self.find(self.run_screen(refs=r),'TEST_PLAYER_A_POINTS25')['reasons'])
    def test_no_opposing_price_fails(self):
        r=[SportsbookPair(**{**x.__dict__,'american_no':-10000}) if x.contract_id=='TEST_PLAYER_A_POINTS25' else x for x in self.refs]
        self.assertIn('insufficient_independent_paired_books',self.find(self.run_screen(refs=r),'TEST_PLAYER_A_POINTS25')['reasons'])
    def test_book_mismatched_rules(self):
        r=[SportsbookPair(**{**x.__dict__,'rule_id':'wrong'}) if x.contract_id=='TEST_PLAYER_A_POINTS25' else x for x in self.refs]
        self.assertFalse(self.find(self.run_screen(refs=r),'TEST_PLAYER_A_POINTS25')['screen_pass'])
    def test_started(self):
        x=self.find(self.run_screen(asof='2026-11-02T00:05:00+00:00'),'TEST_PLAYER_A_POINTS25')
        self.assertIn('already_started',x['reasons'])
    def test_no_extrapolation(self):
        r=inferred_ladder([(20,.75),(30,.30)],[15,20,25,30,35]);self.assertIsNone(r[0]['p']);self.assertIsNone(r[-1]['p']);self.assertEqual(r[2]['kind'],'inferred_not_independent')
    def test_monotonic(self):
        with self.assertRaises(ValueError):inferred_ladder([(20,.3),(25,.6)],[22])
    def test_inferred_not_independent(self):
        x=inferred_ladder([(20,.7),(25,.5)],[21]);self.assertEqual(x[0]['kind'],'inferred_not_independent')
    def test_no_motion_single_snapshot(self):
        self.assertEqual(market_motion([dict(contract_id='A',source='x',probability=.5,timestamp=self.asof)]),[])
    def test_motion_multiple_venues(self):
        arr=[]
        for i in range(3):
            for venue in ['a','b']:
                arr.append(dict(contract_id='X',source=venue,probability=.40+i*.02+(0 if venue=='a' else .01),timestamp=f'2026-10-21T12:{i*3:02}:00+00:00'))
        self.assertEqual(market_motion(arr)[0]['direction'],'up')
    def test_paper_duplicate_immutable(self):
        x=self.run_screen();path=Path(self.tmp.name)/'paper.db';cm={c.contract_id:c for c in self.cs}
        self.assertEqual(record_paper(path,x,cm,self.asof),1)
        self.assertEqual(record_paper(path,x,cm,self.asof),0)
        self.assertEqual(summary(path)['total_paper_signals'],1)
    def test_paper_settle(self):
        x=self.run_screen();path=Path(self.tmp.name)/'paper.db'
        record_paper(path,x,{c.contract_id:c for c in self.cs},self.asof)
        self.assertEqual(settle(path,{'TEST_PLAYER_A_POINTS25':1},'2026-11-02T01:00:00Z'),1)
        self.assertEqual(settle(path,{'TEST_PLAYER_A_POINTS25':0},'2026-11-02T02:00:00Z'),0)
        self.assertEqual(summary(path)['hit_rate'],1)
    def test_live_guard_missing_certificate(self):
        x=self.find(self.run_screen(),'TEST_PLAYER_A_POINTS25')
        with self.assertRaises(LiveOrderBlocked):arm_check(x,self.cs[0],self.qs[0],1000,0,'/no/file',explicitly_enabled=True,user_approved=True)
    def test_live_network_kill_switch(self):
        with self.assertRaises(LiveOrderBlocked):send_live_order('anything')
    def test_book_parse_US(self):
        b={'marketData':{'bestBid':{'value':'0.43'},'bestAsk':{'value':'0.46'}}}
        book={'marketData':{'offers':[{'price':{'value':'0.46'},'qtyDecimal':'15'}, {'price':{'value':'0.47'},'qtyDecimal':'10'}]}}
        q=parse_us_book(self.cs[0],b,book,.01,self.asof)
        self.assertEqual(q.yes_ask_depth,15);self.assertAlmostEqual(q.yes_ask,.46)
    def test_parse_us_reject_missing_depth(self):
        b={'marketData':{'bestBid':{'value':'0.43'},'bestAsk':{'value':'0.46'}}}
        with self.assertRaises(ValueError):parse_us_book(self.cs[0],b,{},.01,self.asof)
    def test_real_feed_requires_rules(self):
        class Fake:
            def __init__(self): self.n=0
            class markets:
                @staticmethod
                def bbo(s):return {'marketData':{'bestBid':{'value':'0.4'},'bestAsk':{'value':'0.44'}}}
                @staticmethod
                def book(s):return {'marketData':{'offers':[{'price':{'value':'0.44'},'qtyDecimal':'10'}]}}
        q,rej=capture_us([self.cs[2]],str(Path(self.tmp.name)/'us.jsonl'),.01,client=Fake())
        self.assertFalse(q);self.assertEqual(len(rej),1)
    def test_capture_fake_us(self):
        class Fake:
            class markets:
                @staticmethod
                def bbo(s):return {'marketData':{'bestBid':{'value':'0.41'},'bestAsk':{'value':'0.45'}}}
                @staticmethod
                def book(s):return {'marketData':{'offers':[{'price':'0.45','quantity':20}]}}
        q,rej=capture_us([self.cs[0]],str(Path(self.tmp.name)/'us.jsonl'),.02,client=Fake())
        self.assertEqual(len(q),1);self.assertFalse(rej)

if __name__=='__main__':unittest.main()

class OppositeSideTests(unittest.TestCase):
    def test_no_is_informational_only(self):
        with tempfile.TemporaryDirectory() as t:
            c,q,r,asof=make(t)
            rows=evaluate_no_research(c,q,r,asof)
            self.assertEqual(len(rows),3)
            self.assertFalse(any(x['tradable'] or x['screen_pass'] for x in rows))
            self.assertAlmostEqual(rows[0]['theoretical_no_ask'],.58)

class SportsbookImporterTests(unittest.TestCase):
    def test_valid_pairs(self):
        from sportsbook_csv import import_pairs
        with tempfile.TemporaryDirectory() as d:
            make(d)
            csv_path=Path(d)/'pair.csv';out=Path(d)/'pairs.jsonl'
            csv_path.write_text('contract_id,sportsbook,captured_utc,american_yes,american_no,rule_id,quote_source\n'
                'TEST_PLAYER_A_POINTS25,bookA,2026-10-21T12:30:00+00:00,-150,+130,test_rules_agree,live-fake\n')
            q,rejected=import_pairs(csv_path,Path(d)/'contracts.jsonl',out)
            self.assertEqual(len(q),1);self.assertFalse(rejected)
    def test_wrong_rules_rejected(self):
        from sportsbook_csv import import_pairs
        with tempfile.TemporaryDirectory() as d:
            make(d);csv_path=Path(d)/'pair.csv'
            csv_path.write_text('contract_id,sportsbook,captured_utc,american_yes,american_no,rule_id,quote_source\n'
                'TEST_PLAYER_A_POINTS25,bookA,2026-10-21T12:30:00+00:00,-150,+130,WRONG,live-fake\n')
            q,rejected=import_pairs(csv_path,Path(d)/'contracts.jsonl',Path(d)/'out.jsonl')
            self.assertFalse(q);self.assertEqual(rejected[0]['reason'],'settlement mismatch')
