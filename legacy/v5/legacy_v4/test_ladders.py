import json,unittest
from pathlib import Path
import numpy as np
import pandas as pd
from ladder_lasso import implied, load_quotes, group_knots,check_order,inferred_ladder,holdouts
from cross_market_bounds import bounds_ge
ROOT=Path(__file__).resolve().parent
class ModelTests(unittest.TestCase):
 def test_odds_conversion(self):
  self.assertAlmostEqual(implied('-110'),110/210)
  self.assertAlmostEqual(implied('+200'),1/3)
 def test_quarantine_known_bad_ladder(self):
  q=load_quotes(ROOT/'data/archived_published_quotes_2026-10-20.csv')
  bad=q[(q.player=='Karl-Anthony Towns')&(q.book=='bet365')&(q.market=='R')]
  self.assertFalse(check_order(group_knots(bad)))
 def test_fair_one_sided_not_greater_than_raw(self):
  q=load_quotes(ROOT/'data/archived_published_quotes_2026-10-20.csv');g=q[(q.player=='Jalen Brunson')&(q.book=='bet365')&(q.market=='P')]
  ks=group_knots(g)
  self.assertTrue(all(t['p']<=t['raw_p'] for t in ks))
 def test_discrete_distribution_valid(self):
  q=load_quotes(ROOT/'data/archived_published_quotes_2026-10-20.csv');g=q[(q.player=='Tyrese Maxey')&(q.book=='bet365')&(q.market=='P')]
  knots=group_knots(g)
  ks,s,lo,hi,pm=inferred_ladder(knots,'P')
  self.assertAlmostEqual(np.sum(pm),1.,places=10)
  self.assertTrue(np.all(np.diff(s)<=1e-8))
  self.assertTrue(np.all(lo<=s+1e-8));self.assertTrue(np.all(hi>=s-1e-8))
  self.assertAlmostEqual(s[0],1.)
 def test_degenerate_discrete_bounds(self):
  x=np.array([1.,1.,0.]);y=np.array([1.,0.])
  self.assertEqual(bounds_ge(x,y,1),(1.,1.))
  self.assertEqual(bounds_ge(x,y,2),(0.,0.))
 def test_bernoulli_dependence(self):
  x=np.array([1.,.5,0.]);y=np.array([1.,.5,0.])
  lo,hi=bounds_ge(x,y,1)
  self.assertLessEqual(lo,.75);self.assertGreaterEqual(hi,.75)
  self.assertAlmostEqual(lo,.5);self.assertAlmostEqual(hi,1.)
 def test_holdouts_only_interior(self):
  x=load_quotes(ROOT/'data/archived_published_quotes_2026-10-20.csv');h=holdouts(x)
  self.assertEqual(len(h),60)
  self.assertTrue(all(e['k']>=0 for e in h))
 def test_deliverable_outputs(self):
  z=json.loads((ROOT/'results/summary.json').read_text())
  self.assertEqual(z['groups_inferred_conditional'],39)
  self.assertEqual(z['groups_quarantined'],1)
  self.assertFalse(z['captured_timestamp_complete'])
 def test_bounds_audit_has_no_bets(self):
  z=json.loads((ROOT/'results/cross_market_summary.json').read_text())
  self.assertEqual(z['certified_executable_edges'],0)
  self.assertGreater(z['pairs_evaluated'],0)
if __name__=='__main__':unittest.main()
