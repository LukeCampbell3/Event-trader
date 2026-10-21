"""Build only ARTIFICIAL TEST fixture. No statement about real prices."""
from dataclasses import asdict
from pathlib import Path
from market_engine import Contract,ExchangeQuote,SportsbookPair,dump_jsonl

D='data/synthetic'

def make(output=D):
    Path(output).mkdir(parents=True,exist_ok=True)
    start='2026-11-01T23:59:00+00:00';now='2026-10-21T12:30:00+00:00'
    cats=[
        Contract('TEST_PLAYER_A_POINTS25','test-yes-player-a-25','EXHIBITION_TEST_ONLY','player_prop','player-a-id','points',24.5,'full_game_incl_ot',start,'test_rules_agree',True),
        Contract('TEST_GAME_A_WIN','test-team-a-wins','EXHIBITION_TEST_ONLY','game_winner','team-a','wins',0.,'full_game_incl_ot',start,'test_rules_agree',True),
        Contract('TEST_UNREVIEWED','test-unreviewed','EXHIBITION_TEST_ONLY','player_prop','player-b-id','assists',5.5,'full_game_incl_ot',start,'unreviewed_rules',False),
    ]
    qs=[ExchangeQuote('TEST_PLAYER_A_POINTS25',now,.42,.45,50,.01,provenance='SYNTHETIC_DO_NOT_BET'),
        ExchangeQuote('TEST_GAME_A_WIN',now,.55,.58,50,.01,provenance='SYNTHETIC_DO_NOT_BET'),
        ExchangeQuote('TEST_UNREVIEWED',now,.33,.38,50,.01,provenance='SYNTHETIC_DO_NOT_BET')]
    refs=[SportsbookPair('TEST_PLAYER_A_POINTS25',b,now,y,n,'test_rules_agree','SYNTHETIC_DO_NOT_BET') for b,y,n in [('bookA',-150,+130),('bookB',-145,+120)]]
    refs += [SportsbookPair('TEST_GAME_A_WIN',b,now,y,n,'test_rules_agree','SYNTHETIC_DO_NOT_BET') for b,y,n in [('bookA',-135,+115),('bookB',-137,+118)]]
    refs += [SportsbookPair('TEST_UNREVIEWED',b,now,-200,+170,'unreviewed_rules','SYNTHETIC_DO_NOT_BET') for b in ('bookA','bookB')]
    dump_jsonl(f'{output}/contracts.jsonl',[asdict(x) for x in cats]);dump_jsonl(f'{output}/exchange.jsonl',[asdict(x) for x in qs]);dump_jsonl(f'{output}/sportsbooks.jsonl',[asdict(x) for x in refs]);
    Path(f'{output}/README.txt').write_text('100% SYNTHETIC FICTIONAL EXHIBITION. Prices are planted to test logic. NEVER ACTIONABLE.\n')
    return cats,qs,refs,now

if __name__=='__main__':
    _,_,_,asof=make();print('Synthetic fixture created for',asof)
