"""Risk gates and OFF-by-default live execution adapter.

No method will place an order until an external certification file demonstrates
prospective validation and execution assumptions have been reviewed. The official
US SDK's authenticated order preview is checked first. Not production certified.
"""
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json, math, os

class LiveOrderBlocked(RuntimeError):pass

@dataclass(frozen=True)
class Limits:
    max_stake_usd: float=5.0
    max_bankroll_fraction: float=0.005
    max_open_exposure_fraction: float=0.02
    min_required_roi: float=0.05
    max_spread: float=0.04
    max_quote_age_seconds: int=20


def arm_check(candidate, contract, quote, bankroll_usd, current_exposure_usd,
              certification_path: str, limits:Limits=Limits(),
              explicitly_enabled:bool=False, user_approved:bool=False, now=None):
    if not explicitly_enabled or not user_approved:
        raise LiveOrderBlocked('Live trading requires separate deliberate arming and approval')
    f=Path(certification_path)
    if not f.is_file():raise LiveOrderBlocked('No prospective validation certificate; PAPER ONLY')
    cert=json.loads(f.read_text())
    if cert.get('status')!='approved' or not cert.get('execution_qa_passed'):
        raise LiveOrderBlocked('Strategy not independently certified')
    if cert.get('unique_player_games',0)<300 or cert.get('prospective_dates',0)<20:
        raise LiveOrderBlocked('Not enough frozen prospective validation')
    if cert.get('bootstrap_roi_lower',-1)<=0 or cert.get('brier_delta_vs_market',1)>=0:
        raise LiveOrderBlocked('No positive prospective benchmark evidence')
    if not candidate.get('screen_pass') or candidate.get('executable_edge_verified'):
        # screen pass is a conditional proxy; certified execution logic still rechecks
        raise LiveOrderBlocked('Candidate not a conditional price screen')
    if not contract.rules_verified or contract.market_status!='open' or not quote.valid():
        raise LiveOrderBlocked('Contract rules or live quote invalid')
    stamp=datetime.fromisoformat(quote.captured_utc.replace('Z','+00:00'))
    now=now or datetime.now(timezone.utc)
    if (now-stamp).total_seconds()<0 or (now-stamp).total_seconds()>limits.max_quote_age_seconds:
        raise LiveOrderBlocked('Quote stale')
    if now>=datetime.fromisoformat(contract.start_utc.replace('Z','+00:00')):
        raise LiveOrderBlocked('Game already started')
    if quote.yes_ask-quote.yes_bid>limits.max_spread:raise LiveOrderBlocked('Spread too wide')
    if candidate['roi_lower_conditional'] < 100*limits.min_required_roi:
        raise LiveOrderBlocked('Conditional ROI below execution floor')
    if quote.yes_ask_depth < 5:raise LiveOrderBlocked('Insufficient top-of-book depth')
    if bankroll_usd<=0 or current_exposure_usd<0:raise LiveOrderBlocked('Missing bankroll data')
    stake=min(limits.max_stake_usd,bankroll_usd*limits.max_bankroll_fraction)
    if current_exposure_usd+stake>bankroll_usd*limits.max_open_exposure_fraction:
        raise LiveOrderBlocked('Portfolio exposure limit')
    shares=math.floor(stake/quote.yes_ask)
    if shares<1 or shares>quote.yes_ask_depth*0.2:
        raise LiveOrderBlocked('Liquidity/size mismatch')
    return shares


def paper_preview(candidate):
    return {'mode':'PAPER_ONLY', 'contract_id':candidate['contract_id'],
            'conditional_roi_pct':candidate['roi_lower_conditional'],
            'not_actual_probability':True,
            'warning':'NO VERIFIED POSITIVE EV. No network order submitted.'}


def send_live_order(*args, **kwargs):
    """Deliberately fails closed until fully verified US SDK integration tests
    and account reconciliation are complete. Live authenticated US order calls
    belong here AFTER, not before, successful strategy validation.
    """
    raise LiveOrderBlocked('LIVE_SUBMISSION_NOT_RELEASE_READY; paper trading and pricing research only')
