import tempfile,unittest
from datetime import timedelta
from pathlib import Path
import numpy as np
from joint_engine import Quote, read_quotes, sync_status, parse_time, states_and_indicator, build_A,bound_probabilities,analyze_group,run
from prospective import freeze,settle
from parlays import analyze_parlay
from synthetic_fixture import make

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.file=self.root/'quotes.csv';make(self.file)
        self.q,errors=read_quotes(self.file)
        self.asof=(parse_time(self.q[0].captured_at)+timedelta(minutes=1)).isoformat()
        self.prior=(parse_time(self.q[0].captured_at)-timedelta(minutes=1)).isoformat()
        self.assertEqual(errors,[])
    def test_paired_and_snapshot(self):
        self.assertEqual(len(self.q),21)
        self.assertEqual(sync_status(self.q),'SYNCHRONIZED_PREGAME')
    def test_half_integer_event_math(self):
        f,indicator,n,K=states_and_indicator(self.q)
        pa=next(q for q in self.q if q.market=='PA')
        arr=indicator(pa)
        self.assertTrue(np.array_equal(arr,(f[0]+f[2]>=pa.k)))
    def test_monotone_bound_interval(self):
        f,ind,n,K=states_and_indicator(self.q)
        train=[q for q in self.q if q.market!='PA']
        A,lo,hi,cent=build_A(train,ind)
        target=next(q for q in self.q if q.market=='PA')
        res=bound_probabilities(A,lo,hi,ind(target).astype(float))
        self.assertEqual(res['status'],'OK')
        self.assertTrue(0<=res['low']<=res['high']<=1)
    def test_holdout_family_no_leak(self):
        targets=[q for q in self.q if q.market=='PA']
        f,ind,n,K=states_and_indicator(self.q)
        A,_,_,_=build_A([q for q in self.q if q.market!='PA'],ind)
        self.assertEqual(A.shape[0],len(self.q)-len(targets))
        self.assertEqual(A.shape[1],n)
    def test_nesting_deterministic_edge(self):
        # If P>=5 with probability >=.75, P+A>=5 must be >=.75.
        q1=Quote('e','p','b','P',4.5,.8,.2,'2026-10-20T20:00:00Z','2026-10-21T00:00:00Z','','')
        q2=Quote('e','p','b','PA',4.5,1/3,None,'2026-10-20T20:00:00Z','2026-10-21T00:00:00Z','','')
        f,ind,n,K=states_and_indicator([q1,q2])
        A,lo,hi,_=build_A([q1],ind,paired=.005)
        r=bound_probabilities(A,lo,hi,ind(q2).astype(float))
        self.assertGreater(r['low'],.78)
        self.assertGreater(r['low']/(1/3)-1,1.3)
    def test_extra_combo_markets_do_not_widen_bounds(self):
        f,ind,n,K=states_and_indicator(self.q)
        target=next(q for q in self.q if q.market=='PA' and q.line==14.5)
        def get(train):
            A,lo,hi,_=build_A(train,ind)
            return bound_probabilities(A,lo,hi,ind(target).astype(float))
        b0=get([q for q in self.q if q.market in ('P','R','A')])
        b1=get([q for q in self.q if q.market!='PA'])
        self.assertEqual(b0['status'],b1['status'])
        self.assertGreaterEqual(b1['low']+1e-6,b0['low'])
        self.assertLessEqual(b1['high']-1e-6,b0['high'])
        self.assertLess(b1['high']-b1['low'],b0['high']-b0['low']-.02)
    def test_correlated_parlay_bound(self):
        legs=[dict(market='P',line=9.5,side='over'),dict(market='PA',line=14.5,side='over')]
        result=analyze_parlay(self.q,legs,'+225')
        self.assertEqual(result['status'],'OK')
        self.assertTrue(0<=result['p_min']<=result['p_max']<=1)
        self.assertEqual(result['source'],'CORRELATED_SAME_PLAYER_JOINT_LP')
    def test_unsynced_archive_cannot_certify(self):
        q=self.q[0];mis=Quote(q.event_id,q.player,q.book,q.market,q.line,q.over,q.under,'','',q.source,q.provenance)
        self.assertEqual(sync_status([mis]),'UNVERIFIED_CAPTURE_TIMESTAMPS')
    def test_family_result_run(self):
        a=run(self.file,self.root/'run',asof=self.asof)
        self.assertGreater(a['results'],0)
        self.assertEqual(a['verified_executable_bets'],0)
        self.assertEqual(a['group_audits'][0]['sync_status'],'SYNCHRONIZED_PREGAME')
    def test_freeze_requires_truthful_pre_game(self):
        import pandas as pd
        a=run(self.file,self.root/'run',asof=self.asof)
        ledger=self.root/'ledger.jsonl'
        with self.assertRaisesRegex(ValueError,'Synthetic'):
            freeze(self.file,self.root/'run/family_holdout_bounds.csv',ledger,self.asof)
        eid=freeze(self.file,self.root/'run/family_holdout_bounds.csv',ledger,self.asof,allow_synthetic_test=True)
        self.assertTrue(eid)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            freeze(self.file,self.root/'run/family_holdout_bounds.csv',ledger,self.asof,allow_synthetic_test=True)
        score=self.root/'box.csv';pd.DataFrame([{'event_id':'SYN@SYN_2026-10-22','player':'Synthetic Player','P':13,'R':7,'A':4}]).to_csv(score,index=False)
        settle_result=settle(ledger,score,self.root/'outcomes.csv')
        self.assertGreater(settle_result['graded_forecasts'],0)
    def test_reject_fake_future_snapshot(self):
        self.assertEqual(sync_status(self.q,asof=self.prior),'FUTURE_QUOTES_RELATIVE_TO_ASOF')

if __name__=='__main__':unittest.main()
