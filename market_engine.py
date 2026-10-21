"""NBA market-only research engine. Quotes are NOT true outcome probabilities.

Read-only analysis and paper trading; every signal is conditional on reference
markets being better calibrated than the quoted exchange ask. No live edge claimed.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from collections import defaultdict
from statistics import median
from pathlib import Path
import csv, json, math


def parse_time(value: str) -> datetime:
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not t.tzinfo: raise ValueError('timestamp must include timezone')
    return t.astimezone(timezone.utc)


def american_implied(odds: int) -> float:
    if odds == 0: raise ValueError('zero is not valid American odds')
    return abs(odds)/(abs(odds)+100) if odds < 0 else 100/(100+odds)


def devig_two_way(yes: int, no: int) -> float:
    py, pn = american_implied(yes), american_implied(no)
    if not (0.99 <= py+pn <= 1.25):
        raise ValueError('invalid two-way market overround')
    return py/(py+pn)


@dataclass(frozen=True)
class Contract:
    """Reviewed *exact* match between event-specific Polymarket & sportsbook markets.

    Do not compare ordinary sportsbook DNP-void prop with a prediction-market
    contract with different DNP/OT/resolution rules. `rules_verified` is manual.
    """
    contract_id: str
    market_slug: str
    game_id: str
    kind: str                # player_prop, game_winner, game_total, team_total
    participant_id: str     # normalized player ID or team identifier
    stat: str               # points/rebounds/assists/PRA/wins/total etc.
    threshold: float        # standardized YES event over half-line, or 0 for WIN
    period: str             # full_game_incl_ot, regulation
    start_utc: str
    settlement_rule_id: str
    rules_verified: bool = False
    market_status: str = 'open'

    def valid(self) -> bool:
        return (bool(self.contract_id and self.game_id and self.market_slug and self.settlement_rule_id)
                and self.kind in {'player_prop','game_winner','game_total','team_total'}
                and self.period in {'full_game_incl_ot','regulation'}
                and self.market_status == 'open'
                and math.isfinite(self.threshold)
                and parse_time(self.start_utc).tzinfo is not None)


@dataclass(frozen=True)
class ExchangeQuote:
    contract_id: str
    captured_utc: str
    yes_bid: float
    yes_ask: float
    yes_ask_depth: int
    fee_per_share_cap: float  # conservative configured, must be verified before live
    source: str = 'Polymarket_US'
    market_status: str = 'open'
    provenance: str = 'unknown'

    def valid(self):
        return (0 <= self.yes_bid <= self.yes_ask < 1 and self.yes_ask > 0
                and self.yes_ask_depth >= 0 and self.fee_per_share_cap >= 0
                and self.market_status == 'open')


@dataclass(frozen=True)
class SportsbookPair:
    contract_id: str
    sportsbook: str
    captured_utc: str
    american_yes: int
    american_no: int
    rule_id: str
    quote_source: str
    executable_confirmed: bool = False

    def probability(self) -> float:
        return devig_two_way(self.american_yes, self.american_no)


@dataclass(frozen=True)
class ScreenConfig:
    max_quote_age_seconds: int = 120
    max_cross_source_skew_seconds: int = 180
    min_independent_books: int = 2
    probability_uncertainty: float = 0.025
    disagreement_multiplier: float = 0.5
    min_worst_case_roi: float = 0.04
    slippage_reserve_per_share: float = 0.005
    min_depth_shares: int = 3
    max_fraction_top_book: float = 0.2
    target_shares: int = 1
    max_spread: float = 0.1
    require_rules: bool = True


def evaluate(contracts: list[Contract], quotes: list[ExchangeQuote], references: list[SportsbookPair],
             asof: str, config: ScreenConfig = ScreenConfig()) -> list[dict]:
    """Signal is CONDITIONAL, not verified true EV. The target's own price is excluded.
    Requires 2+ independent paired sportsbook quotes for *identical* settlement.
    p_lower = min(two-way p) - quoted market disagreement/2 - explicit uncertainty.
    This is a sensitivity lower estimate, never a statistical confidence bound.
    """
    now = parse_time(asof)
    cs = {c.contract_id: c for c in contracts}
    qs = defaultdict(list); rs = defaultdict(list)
    for q in quotes: qs[q.contract_id].append(q)
    for r in references: rs[r.contract_id].append(r)
    results=[]
    for id, c in cs.items():
        reasons=[]
        try:
            if not c.valid(): reasons.append('invalid_contract')
        except ValueError: reasons.append('invalid_timestamp')
        if config.require_rules and not c.rules_verified: reasons.append('unverified_resolution_rules')
        if parse_time(c.start_utc) <= now: reasons.append('already_started')
        snapshots=sorted(qs.get(id,[]),key=lambda x:parse_time(x.captured_utc),reverse=True)
        q=snapshots[0] if snapshots else None
        if q is None or not q.valid(): reasons.append('missing_or_invalid_exchange_bbo')
        if q and (parse_time(q.captured_utc) > now or (now-parse_time(q.captured_utc)).total_seconds() > config.max_quote_age_seconds):
            reasons.append('stale_or_future_exchange_quote')
        if q and q.yes_ask - q.yes_bid > config.max_spread: reasons.append('wide_spread')
        if q and q.yes_ask_depth < max(config.min_depth_shares, math.ceil(config.target_shares/config.max_fraction_top_book)):
            reasons.append('insufficient_depth')
        compatible={}
        for r in sorted(rs.get(id,[]),key=lambda x:parse_time(x.captured_utc),reverse=True):
            try:
                t = parse_time(r.captured_utc)
                if r.rule_id != c.settlement_rule_id or t > now or not 0 <= (now-t).total_seconds() <= config.max_quote_age_seconds:continue
                if q and abs((t-parse_time(q.captured_utc)).total_seconds()) > config.max_cross_source_skew_seconds:continue
                if r.sportsbook == q.source if q else False: continue
                if r.sportsbook not in compatible:
                    compatible[r.sportsbook] = r.probability()
            except (ValueError, TypeError): continue
        vals=list(compatible.values())
        if len(vals) < config.min_independent_books: reasons.append('insufficient_independent_paired_books')
        p_mid=median(vals) if vals else None
        range_pp=max(vals)-min(vals) if vals else 1.0
        p_floor=max(0,min(vals) - config.probability_uncertainty - range_pp*config.disagreement_multiplier) if vals else None
        cost=q.yes_ask + q.fee_per_share_cap + config.slippage_reserve_per_share if q else None
        roi_mid=p_mid/cost-1 if p_mid is not None and cost and cost>0 else None
        roi_low=p_floor/cost-1 if p_floor is not None and cost and cost>0 else None
        if cost is not None and cost>=1: reasons.append('all_in_cost_above_payout')
        if roi_low is None or roi_low < config.min_worst_case_roi: reasons.append('no_conditional_margin')
        results.append(dict(contract_id=id, game_id=c.game_id, market_slug=c.market_slug, kind=c.kind,
            player_or_team=c.participant_id, stat=c.stat, threshold=c.threshold,
            exchange_bid=q.yes_bid if q else None,exchange_ask=q.yes_ask if q else None,
            book_count=len(vals), reference_p=round(p_mid,6) if p_mid is not None else None,
            p_lower_conditional=round(p_floor,6) if p_floor is not None else None,
            disagreement_pp=round(100*range_pp,3),
            cost_per_share=round(cost,6) if cost is not None else None,
            roi_mid_conditional=round(100*roi_mid,3) if roi_mid is not None else None,
            roi_lower_conditional=round(100*roi_low,3) if roi_low is not None else None,
            screen_pass=not bool(reasons), executable_edge_verified=False,
            research_only=True, reasons=sorted(set(reasons)), asof=asof))
    return sorted(results,key=lambda r: r['roi_lower_conditional'] if r['roi_lower_conditional'] is not None else -1000, reverse=True)


def inferred_ladder(points: list[tuple[int,float]], thresholds: list[int]) -> list[dict]:
    """Logit interpolation *only within* observed paired alternate thresholds.
    No inferred point is independent evidence. Impossible curves get rejected.
    """
    known=sorted(points)
    if len(known)<2 or len({t for t,p in known})!=len(known): raise ValueError('need >=2 distinct thresholds')
    if any(not 0<p<1 for t,p in known): raise ValueError('probs must be interior')
    if any(known[i+1][1] > known[i][1]+1e-8 for i in range(len(known)-1)):
        raise ValueError('nonmonotone ladder: quarantine')
    def logit(p): return math.log(p/(1-p))
    def logistic(z): return 1/(1+math.exp(-z))
    out=[]
    for t in thresholds:
        if not known[0][0]<=t<=known[-1][0]:
            out.append(dict(threshold=t,p=None,kind='out_of_range')); continue
        if t in dict(known):
            out.append(dict(threshold=t,p=dict(known)[t],kind='observed'));continue
        for (lo,p0),(hi,p1) in zip(known,known[1:]):
            if lo<t<hi:
                w=(t-lo)/(hi-lo)
                out.append(dict(threshold=t,p=logistic((1-w)*logit(p0)+w*logit(p1)),kind='inferred_not_independent'))
                break
    return out


def market_motion(snapshots: list[dict], max_skew_seconds: int = 60) -> list[dict]:
    """No velocity from isolated quotes; no unmatched event combining.
    Requires >=3 observations per venue for the *same contract* and two venues.
    """
    g=defaultdict(lambda: defaultdict(list))
    for x in snapshots:
        if not 0<float(x['probability'])<1: continue
        g[x['contract_id']][x['source']].append((parse_time(x['timestamp']),float(x['probability'])))
    result=[]
    for k,sources in g.items():
        aligned={}
        for source,rows in sources.items():
            rows=sorted(set(rows))
            if len(rows)<3: continue
            duration=(rows[-1][0]-rows[0][0]).total_seconds()
            if duration<60: continue
            v=(rows[-1][1]-rows[0][1])/(duration/3600)
            aligned[source]=(v,rows[0],rows[-1])
        if len(aligned)<2:continue
        starts=[v[1][0] for v in aligned.values()];ends=[v[2][0] for v in aligned.values()]
        if (max(starts)-min(starts)).total_seconds()>max_skew_seconds:continue
        if (max(ends)-min(ends)).total_seconds()>max_skew_seconds:continue
        vs=[v[0] for v in aligned.values()];direction=sum(1 for v in vs if v>0)-sum(1 for v in vs if v<0)
        result.append(dict(contract_id=k,venues=len(aligned),median_velocity_pp_hour=round(100*median(vs),3),
                           agreement=round(max(sum(v>0 for v in vs),sum(v<0 for v in vs))/len(vs),3),
                           direction='up' if direction>0 else 'down' if direction<0 else 'mixed',
                           convergence_pp=round(100*((max(v[1][1] for v in aligned.values())-min(v[1][1] for v in aligned.values()))-
                               (max(v[2][1] for v in aligned.values())-min(v[2][1] for v in aligned.values()))),3),
                           actionable_signal=False))
    return result


def load_jsonl(path: str):
    with open(path,encoding='utf8') as f:
        return [json.loads(x) for x in f if x.strip()]

def dump_jsonl(path: str, rows: list[dict]):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,'w',encoding='utf8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True)+'\n')


def read_contracts(path):return [Contract(**r) for r in load_jsonl(path)]
def read_quotes(path):return [ExchangeQuote(**r) for r in load_jsonl(path)]
def read_books(path):return [SportsbookPair(**r) for r in load_jsonl(path)]


def evaluate_no_research(contracts: list[Contract],quotes: list[ExchangeQuote],
                         references: list[SportsbookPair],asof:str,
                         config:ScreenConfig=ScreenConfig())->list[dict]:
    """Symmetric opposing-outcome *research* screen.

    Some US exchanges represent NO as selling/shorting the YES instrument.
    The theoretical NO entry 1-YES bid is NOT necessarily tradeable after
    borrow/margin, commissions, capacity, and short-side execution mechanics.
    These rows are NEVER actionable and cannot enter the paper ledger.
    """
    now=parse_time(asof); cs={x.contract_id:x for x in contracts}
    by=defaultdict(list)
    for x in references:by[x.contract_id].append(x)
    out=[]
    for q in quotes:
        c=cs.get(q.contract_id)
        if not c or not q.valid():continue
        vals=[]
        for r in by[q.contract_id]:
            if (r.rule_id!=c.settlement_rule_id or parse_time(r.captured_utc)>now or
                (now-parse_time(r.captured_utc)).total_seconds()>config.max_quote_age_seconds):continue
            try:vals.append((r.sportsbook,1-r.probability()))
            except ValueError:continue
        distinct={}
        for v,p in vals:distinct[v]=p
        x=list(distinct.values())
        p_lower=max(0,min(x)-config.probability_uncertainty-
                    (max(x)-min(x))*config.disagreement_multiplier) if x else None
        no_price=1-q.yes_bid  # theoretical equivalent only
        theoretical_cost=no_price+q.fee_per_share_cap+config.slippage_reserve_per_share
        out.append(dict(contract_id=q.contract_id,outcome='NO',theoretical_no_ask=round(no_price,5),
            reference_no_p=median(x) if x else None,
            conditional_no_roi_lower_pct=round(100*(p_lower/theoretical_cost-1),3) if p_lower is not None else None,
            reference_books=len(x), tradable=False,screen_pass=False,
            reason='NO_SHORT_EXECUTION_RULES_AND_LIQUIDITY_UNVERIFIED'))
    return out
