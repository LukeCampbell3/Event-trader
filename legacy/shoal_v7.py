"""Shoal v7. Research-only, probability-market dynamics and conservative screening.

Odds are prices, not measurements of true event probability. A positive statistical
screen is NOT proof of positive EV; executable arb needs size, rules and fees.
"""
from __future__ import annotations
import csv, math, statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def dt(x):
    return datetime.fromisoformat(x.replace('Z', '+00:00')).astimezone(timezone.utc) if x else None

def americana_prob(x):
    x = int(x)
    return abs(x)/(abs(x)+100) if x < 0 else 100/(x+100)

def decimal_from_american(x):
    x=int(x)
    return (1+100/abs(x)) if x<0 else (1+x/100)

def kalshi_general_taker_fee_per_contract(price, contracts=100, multiplier=1.0):
    """Generic fee sensitivity only: ceil(0.07*C*P*(1-P)*M, cents)/C.
    Check current market-specific fee schedule; result is NOT an account quote.
    """
    if not (0 < price < 1) or contracts<1 or multiplier<0:raise ValueError('Invalid contract/fee parameters')
    return math.ceil(100*0.07*contracts*price*(1-price)*multiplier-1e-10)/100/contracts

def trimmean(x):
    x=sorted(x)
    if len(x)>=7: x=x[1:-1]
    return statistics.mean(x)

@dataclass(frozen=True)
class Quote:
    game: str
    market: str
    outcome: str
    source: str
    venue_type: str
    timestamp: str
    start: str
    bid: float|None
    ask: float|None
    volume: float=0.0
    size: float=0.0
    fee: float=0.0
    provenance: str='snapshot'
    rules_verified: bool=False

    def valid(self):
        return bool(self.bid is None or 0 <= self.bid <= 1) and bool(self.ask is None or 0 < self.ask < 1) and (self.bid is None or self.ask is None or self.bid <= self.ask)


def load_quotes(p):
    out=[]
    with open(p, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            obj=Quote(r['game'],r['market'],r['outcome'],r['source'],r['venue_type'],r['timestamp'],r['start'],
                float(r['bid']) if r.get('bid') else None, float(r['ask']) if r.get('ask') else None,
                float(r.get('volume') or 0),float(r.get('size') or 0),float(r.get('fee') or 0),r.get('provenance') or 'snapshot',
                str(r.get('rules_verified','')).lower() in ('true','1','yes'))
            if not obj.valid(): raise ValueError('Crossed, negative or invalid quote '+repr(obj))
            out.append(obj)
    return out

HEADERS=['game','market','outcome','source','venue_type','timestamp','start','bid','ask','volume','size','fee','provenance','rules_verified']

def dump_quotes(path, quotes):
    import dataclasses
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path,'w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=HEADERS);w.writeheader()
        for q in quotes:w.writerow(dataclasses.asdict(q))


def normalize_sportsbook(rows):
    """De-vig *paired* mutually exclusive exhaustive outcomes, same book/snapshot.
    No inference for one-sided lines or unrelated settlement definitions.
    """
    groups=defaultdict(list)
    for q in rows:
        if q.venue_type=='sportsbook' and q.ask is not None:
            groups[(q.game,q.market,q.source,q.timestamp)].append(q)
    fair={}
    for k,rows in groups.items():
        outcomes={q.outcome for q in rows}
        if len(rows)!=2 or len(outcomes)!=2:continue
        total=sum(q.ask for q in rows)
        if not 0.99<=total<=1.20: continue
        for q in rows:fair[(q.game,q.market,q.source,q.timestamp,q.outcome)]=q.ask/total
    return fair


def price_screen(quotes, asof, max_age_seconds=900, source_pad=0.015, min_references=2):
    """Examines executable ask versus other paired sportsbook de-vig prices.
    Lower bound = min reference p - source_pad (not a confidence interval).
    Calls 'edge' *conditional* only, never certified true positive EV.
    """
    now=dt(asof)
    fair=normalize_sportsbook(quotes)
    out=[]
    for target in quotes:
        if target.venue_type!='exchange' or target.ask is None:continue
        ts=dt(target.timestamp); start=dt(target.start)
        recent=bool(now and ts and 0<= (now-ts).total_seconds()<=max_age_seconds)
        pregame=bool(ts and start and ts<start and now<start)
        refs=[]
        for (game,market,src,t,outcome),p in fair.items():
            if (game,market,outcome)!=(target.game,target.market,target.outcome):continue
            pt=dt(t)
            if pt and ts and abs((ts-pt).total_seconds())<=max_age_seconds and pt<dt(target.start):refs.append((src,p))
        unique={name:p for name,p in refs}
        enough=len(unique)>=min_references
        lower=(min(unique.values())-source_pad) if enough else None
        upper=(max(unique.values())+source_pad) if enough else None
        estimated=trimmean(list(unique.values())) if enough else None
        entry=target.ask+target.fee
        gross=(estimated/entry-1) if estimated is not None else None
        worst=(lower/entry-1) if lower is not None else None
        # This could be a conditional discrepancy, but true alpha requires
        # prospective/out-of-sample outcomes + execution verification.
        conditional=bool(recent and pregame and enough and lower is not None and lower>entry+0.02 and target.rules_verified and target.size>=1)
        out.append(dict(game=target.game, market=target.market,outcome=target.outcome,source=target.source,
            quoted_ask=target.ask,fee_per_share=target.fee,executable_cost=entry,asof=asof,
            paired_independent_books=len(unique),ref_fair=estimated,ref_low=lower,ref_high=upper,
            conditional_roi_central=gross,conditional_roi_lower=worst,
            fresh=recent,pregame=pregame,price_size_known=target.size>=1,
            rules_verified=target.rules_verified,conditional_screen=conditional,
            true_ev_verified=False,book_values=','.join(f'{x}:{y:.4f}' for x,y in sorted(unique.items()))))
    return out


def linear_slope_per_hour(pts):
    # pts list of (seconds, fair midpoint). Only use >=3 distinct observations.
    pts=sorted(set(pts))
    if len(pts)<3:return None
    xs=[x/3600 for x,y in pts];ys=[y for x,y in pts]
    centerx=statistics.mean(xs);centery=statistics.mean(ys)
    denom=sum((x-centerx)**2 for x in xs)
    return sum((x-centerx)*(y-centery) for x,y in zip(xs,ys))/denom if denom>0 else None


def dynamics(quotes, asof, window_seconds=3600, max_skew_seconds=300):
    """Velocity/convergence from *timestamped repeated* quotes only.
    Source slopes cannot be estimated from a single page capture.
    """
    now=dt(asof)
    fair=normalize_sportsbook(quotes)
    groups=defaultdict(list)
    for q in quotes:
        t=dt(q.timestamp)
        if not t or not now or not 0<= (now-t).total_seconds()<=window_seconds:continue
        if q.venue_type=='sportsbook':
            p=fair.get((q.game,q.market,q.source,q.timestamp,q.outcome))
        else:
            p=(q.bid+q.ask)/2 if q.ask is not None and q.bid is not None else None
        if p is not None:groups[(q.game,q.market,q.outcome,q.source)].append((t.timestamp(),p))
    rows=[]; entities=defaultdict(list)
    for (game,market,outcome,source),series in groups.items():
        clean=sorted(set(series))
        slope=linear_slope_per_hour(clean)
        if slope is None:continue
        if max(x for x,p in clean)-min(x for x,p in clean)<120:continue
        latest=max(clean)
        entities[(game,market,outcome)].append((source,slope,latest[1],clean))
    for (game,market,outcome),x in entities.items():
        if len(x)<2:continue
        first_times=[z[3][0][0] for z in x];last_times=[z[3][-1][0] for z in x]
        if max(first_times)-min(first_times)>max_skew_seconds or max(last_times)-min(last_times)>max_skew_seconds:continue
        velocities=[z[1] for z in x]; avg=statistics.median(velocities)
        matching=sum(1 for z in velocities if z*avg>0)
        latest_vals=[z[2] for z in x]
        first_vals=[z[3][0][1] for z in x]
        width_current=max(latest_vals)-min(latest_vals)
        width_initial=max(first_vals)-min(first_vals)
        rows.append(dict(game=game,market=market,outcome=outcome,venues=len(x),
            median_velocity_pp_hour=100*avg, directional_agreement=matching/len(x) if avg else 0.,
            price_dispersion_pp=100*width_current,convergence_pp=100*(width_initial-width_current),
            source_slopes=';'.join(f'{src}:{v*100:.2f}' for src,v,_,_ in x),
            sufficient_history=True))
    return rows


def lead_lag_test(quotes, source_a, source_b, step_seconds=300):
    """Lagged correlation of changes for *one exact* contract, for research only.
    We deliberately report sample size: 3 points cannot establish leadership.
    """
    groups=defaultdict(lambda:defaultdict(dict))
    for q in quotes:
        if q.source not in (source_a,source_b) or q.bid is None or q.ask is None:continue
        t=dt(q.timestamp)
        if t is None:continue
        ix=int(t.timestamp()//step_seconds)
        groups[(q.game,q.market,q.outcome)][q.source][ix]=(q.ask+q.bid)/2
    out=[]
    for (game,market,outcome),g in groups.items():
        a=g.get(source_a,{});b=g.get(source_b,{})
        common=sorted(set(a)&set(b));
        if len(common)<8:continue
        changes_a={i:a[i]-a[i-1] for i in common if i-1 in a};changes_b={i:b[i]-b[i-1] for i in common if i-1 in b}
        def pearson(xs,ys):
            if len(xs)<6:return None
            v=statistics.pstdev(xs)*statistics.pstdev(ys)
            return sum((x-statistics.mean(xs))*(y-statistics.mean(ys)) for x,y in zip(xs,ys))/len(xs)/v if v>1e-12 else None
        lag_scores=[]
        for lag in range(0,5):
            pair=[(changes_a[i],changes_b[i+lag]) for i in changes_a if i+lag in changes_b]
            corr=pearson([p[0] for p in pair],[p[1] for p in pair]) if pair else None
            lag_scores.append((lag,corr,len(pair)))
        valid=[x for x in lag_scores if x[1] is not None]
        if valid:
            best=max(valid,key=lambda z:z[1]);out.append(dict(game=game,market=market,outcome=outcome,
                leader=source_a,follower=source_b,lag_intervals=best[0],r=best[1],
                pairs=best[2],unadjusted_exploratory=True))
    return out


def monotone_ladders(ladder_records):
    """Returns violations of p(threshold+1)<=p(threshold) for SAME provider/player/stat.
    Probabilities displayed on sites are NOT verified executable asks.
    """
    groups=defaultdict(list)
    for r in ladder_records:
        groups[(r['game'],r['source'],r['player'],r['stat'])].append(r)
    out=[]
    for (game,source,player,stat),rows in groups.items():
        rows=sorted(rows,key=lambda r:float(r['threshold']))
        checks=[]
        for a,b in zip(rows,rows[1:]):
            checks.append(max(0.,float(b['p'])-float(a['p'])))
        out.append(dict(game=game,source=source,player=player,stat=stat,
            thresholds=len(rows),violations=sum(1 for d in checks if d>1e-7),
            maximum_violation_pp=100*max(checks,default=0)))
    return out


def save_csv(path, data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    if not data:return
    with open(path,'w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
