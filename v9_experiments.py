"""Run reproducible, explicitly qualified diagnostics on the V9 SQLite store."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import json
import math
import random
import re
import sqlite3
import subprocess
from contextlib import closing
from statistics import stdev

from v9_research import ResearchStore, utc


def _event_date(native_id: str):
    m = re.search(r"-(\d{2}[A-Z]{3}\d{2})", native_id)
    if not m: return None
    try: return datetime.strptime(m.group(1), "%y%b%d").date()
    except ValueError: return None


def _bootstrap_cluster_ci(rows, metric, reps=3000, seed=41):
    grouped = defaultdict(list)
    for r in rows: grouped[r["event_id"]].append(r)
    events = sorted(grouped)
    if len(events) < 2: return None
    rng = random.Random(seed)
    vals=[]
    for _ in range(reps):
        sample=[r for _ in events for e in [rng.choice(events)] for r in grouped[e]]
        vals.append(sum(metric(r) for r in sample)/len(sample))
    vals.sort()
    return [round(vals[int(.025*reps)],6), round(vals[min(reps-1,int(.975*reps))],6)]


def _scores(p, y):
    p = min(1-1e-12,max(1e-12,p))
    return (p-y)**2, -(y*math.log(p)+(1-y)*math.log(1-p))


def _power_estimate(rows, cluster_key, margin=.01):
    grouped=defaultdict(list)
    for r in rows: grouped[r[cluster_key]].append(_scores(r["p"],r["y"])[0]-.25)
    means=[sum(x)/len(x) for x in grouped.values()]
    if len(means)<2: return {"clusters":len(means),"cluster_sd":None,"estimated_clusters_for_1pp_improvement_80pct_power":None}
    sigma=stdev(means)
    # Normal approximation: two-sided alpha=.05, 80% power, paired score difference.
    return {"clusters":len(means),"cluster_sd_brier_difference":round(sigma,6),
            "approx_required_clusters_for_1pp":math.ceil(((1.96+.84)*sigma/.01)**2),
            "approx_required_clusters_for_2pp":math.ceil(((1.96+.84)*sigma/.02)**2),
            "approx_required_clusters_for_5pp":math.ceil(((1.96+.84)*sigma/.05)**2),
            "assumptions":"Normal approximation, paired Brier difference, alpha=.05 two-sided, 80% power; pilot variance only"}


def analyze(db_path: str, output: str):
    store = ResearchStore(db_path)
    with sqlite3.connect(db_path) as db:
        db.row_factory=sqlite3.Row
        market_rows=db.execute("SELECT native_market_id,contract_id,source_metadata_json FROM markets WHERE source='Kalshi' ORDER BY native_market_id").fetchall()
        quote_count=db.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
    market_samples=[]
    prop_samples=[]
    prop_eligible=defaultdict(int)
    prop_priced=defaultdict(int)
    movement_series=[]
    db_conn=sqlite3.connect(db_path)
    db_conn.row_factory=sqlite3.Row
    for market_row in market_rows:
        ticker=market_row["native_market_id"]
        meta=json.loads(market_row["source_metadata_json"])
        event_id=meta.get("event_ticker")
        date=_event_date(ticker)
        if not event_id or not date: continue
        with db_conn:
            settlement=db_conn.execute("SELECT outcome FROM settlements WHERE contract_id=? ORDER BY settled_ts DESC LIMIT 1",(market_row["contract_id"],)).fetchone()
        if settlement is None: continue
        prop_stat=next((x for x in ("PTS","REB","AST","PRA") if ticker.startswith("KXNBA"+x+"-")),None)
        if prop_stat: prop_eligible[prop_stat]+=1
        # Conservative calendar-only decision time: 00:00 UTC one day before
        # the event date encoded by Kalshi. No in-game or settlement prices.
        decision=datetime.combine(date,datetime.min.time(),tzinfo=timezone.utc)-timedelta(days=1)
        qrows=db_conn.execute("SELECT bid,ask,exchange_ts,capture_method FROM quotes WHERE contract_id=? AND price_kind='INDICATIVE' AND exchange_ts<=? ORDER BY exchange_ts",(market_row["contract_id"],decision.isoformat())).fetchall()
        usable=[]
        for q in qrows:
            if q["bid"] is None or q["ask"] is None: continue
            bid,ask=float(q["bid"]),float(q["ask"])
            if 0 <= bid <= ask <= 1 and 0 < (bid+ask)/2 < 1:
                usable.append(q)
        if usable:
            q=usable[-1]
            p=(float(q["bid"])+float(q["ask"]))/2
            sample={"event_id":event_id,"event_date":str(date),"contract_id":market_row["contract_id"],"p":p,"y":int(settlement[0]),"decision_ts":decision.isoformat(),"quote_ts":q["exchange_ts"],"price_kind":"INDICATIVE","source":"Kalshi"}
            if ticker.startswith("KXNBAGAME-"):
                sample["bid"]=float(q["bid"]);sample["ask"]=float(q["ask"])
                market_samples.append(sample)
            elif ticker.startswith(("KXNBAPTS-","KXNBAREB-","KXNBAAST-","KXNBAPRA-")):
                prop_priced[prop_stat]+=1
                prop_samples.append(sample)
        # One-hour candle change prediction, only candles ending before the
        # same pre-event cutoff. Dataset is retrospective; this tests price
        # dynamics, not evidence of local capture at the historical time.
        mrows=(db_conn.execute("SELECT bid,ask,exchange_ts FROM quotes WHERE contract_id=? AND price_kind='INDICATIVE' AND capture_method='public_historical_candlesticks_interval_60m' AND exchange_ts<=? ORDER BY exchange_ts",(market_row["contract_id"],decision.isoformat())).fetchall()
               if ticker.startswith("KXNBAGAME-") else [])
        points=[]
        for q in mrows:
            if q["bid"] is None or q["ask"] is None: continue
            p=(float(q["bid"])+float(q["ask"]))/2
            if 0 < p < 1: points.append((utc(q["exchange_ts"]),p))
        for (t0,p0),(t1,p1),(t2,p2) in zip(points,points[1:],points[2:]):
            if abs((t1-t0).total_seconds()-3600)>300 or abs((t2-t1).total_seconds()-3600)>300: continue
            movement_series.append({"event_id":event_id,"event_date":str(date),"t1":t1.isoformat(),
                                    "actual_next":p2,"no_change":p1,"momentum":min(.999999,max(.000001,p1+(p1-p0)))})
    db_conn.close()

    by_event=defaultdict(list)
    for r in market_samples: by_event[r["event_id"]].append(r)
    metrics={"market_observations":len(market_samples),"unique_settled_events":len(by_event)}
    if market_samples:
        bs=[];ll=[];acc=[];base=[]
        for r in market_samples:
            b,l=_scores(r["p"],r["y"]);bs.append(b);ll.append(l);acc.append(int((r["p"]>=.5)==bool(r["y"])));base.append(.25)
        metrics.update({"market_price_brier":round(sum(bs)/len(bs),6),"constant_50pct_brier":.25,
                        "brier_difference_vs_50pct":round(sum(bs)/len(bs)-.25,6),
                        "market_price_log_loss":round(sum(ll)/len(ll),6),"constant_50pct_log_loss":round(math.log(2),6),
                        "directional_accuracy":round(sum(acc)/len(acc),6),
                        "brier_event_cluster_bootstrap_95pct":_bootstrap_cluster_ci(market_samples,lambda r:_scores(r["p"],r["y"])[0]),
                        "brier_difference_vs_50pct_cluster_bootstrap_95pct":_bootstrap_cluster_ci(market_samples,lambda r:_scores(r["p"],r["y"])[0]-.25),
                        "sample_size_estimate":_power_estimate(market_samples,"event_id"),
                        "calibration_bins":[]})
        edges=[0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1.000001]
        for lo,hi in zip(edges,edges[1:]):
            g=[r for r in market_samples if lo<=r["p"]<hi]
            if g: metrics["calibration_bins"].append({"low":lo,"high":hi,"n_contracts":len(g),"n_events":len({r['event_id'] for r in g}),"mean_probability":round(sum(r["p"] for r in g)/len(g),4),"observed_yes_rate":round(sum(r["y"] for r in g)/len(g),4)})
    else: metrics.update({"market_price_brier":None,"market_price_log_loss":None,"directional_accuracy":None})

    paired=[g for g in by_event.values() if len(g)==2]
    paired_sync=[g for g in paired if abs((utc(g[0]["quote_ts"])-utc(g[1]["quote_ts"])).total_seconds())<=3600]
    metrics["opposing_contract_consistency"]={"paired_events":len(paired),
        "mean_absolute_midpoint_sum_minus_one":round(sum(abs(sum(r["p"] for r in g)-1) for g in paired)/len(paired),6) if paired else None,
        "max_absolute_midpoint_sum_minus_one":round(max((abs(sum(r["p"] for r in g)-1) for g in paired),default=0),6),
        "synchronized_pairs_within_one_hour":len(paired_sync),
        "synchronized_pairs_with_two_yes_asks_below_one":sum(1 for g in paired_sync if sum(r["ask"] for r in g)<1),
        "minimum_synchronized_two_yes_ask_sum":round(min((sum(r["ask"] for r in g) for g in paired_sync),default=0),6),
        "classification":"INDICATIVE_MIDPOINT_DIAGNOSTIC_ONLY; no execution or arbitrage inference"}

    prop_by_stat=defaultdict(list)
    for row in prop_samples:
        stat=next((x for x in ("PTS","REB","AST","PRA") if row["contract_id"].startswith("Kalshi:KXNBA"+x+"-")),"OTHER")
        # Multiple alternate thresholds/stat families for a player-game cluster.
        ticker=row["contract_id"].split(":",1)[1]
        native_event=ticker.split("-",1)[1].split("-",1)[0]
        suffix=ticker.split(native_event,1)[1].strip("-")
        player=suffix.rsplit("-",1)[0] if "-" in suffix else suffix
        row["cluster_id"]=native_event+"|"+player
        prop_by_stat[stat].append(row)
    prop_metrics={}
    for stat,rows in sorted(prop_by_stat.items()):
        brier=sum(_scores(r["p"],r["y"])[0] for r in rows)/len(rows)
        logloss=sum(_scores(r["p"],r["y"])[1] for r in rows)/len(rows)
        clustered=[{**r,"event_id":r["cluster_id"]} for r in rows]
        prop_metrics[stat]={"contract_observations":len(rows),"unique_games":len({r["event_id"] for r in rows}),
            "unique_player_game_clusters":len({r["cluster_id"] for r in rows}),"market_midpoint_brier":round(brier,6),
            "constant_50pct_brier":.25,"brier_difference_vs_50pct":round(brier-.25,6),
            "market_midpoint_log_loss":round(logloss,6),"constant_50pct_log_loss":round(math.log(2),6),
            "cluster_bootstrap_brier_difference_95pct":_bootstrap_cluster_ci(clustered,lambda r:_scores(r["p"],r["y"])[0]-.25),
            "sample_size_estimate":_power_estimate(clustered,"event_id")}
    metrics["player_prop_calibration"]=prop_metrics
    metrics["player_prop_pregame_coverage"]={stat:{"settled_contracts_in_database":prop_eligible[stat],"contracts_with_eligible_pre_event_candle":prop_priced[stat]} for stat in ("PTS","REB","AST","PRA")}

    # Market-only, fixed zero-parameter momentum ablation. Chronological 70/30
    # split by event date; no selected parameters and no outcome features.
    events=sorted({r["event_id"]:r["event_date"] for r in movement_series}.items(),key=lambda x:x[1])
    test_ids={e for e,_ in events[int(len(events)*.7):]}
    holdout=[r for r in movement_series if r["event_id"] in test_ids]
    if holdout:
        mae0=sum(abs(r["actual_next"]-r["no_change"]) for r in holdout)/len(holdout)
        mae1=sum(abs(r["actual_next"]-r["momentum"]) for r in holdout)/len(holdout)
        metrics["one_hour_momentum_test"]={"method":"last one-hour probability change extrapolated one hour; clipped to (0,1)",
             "split":"chronological last 30% of unique event tickers","train_event_count":len(events)-len(test_ids),
             "test_event_count":len(test_ids),"test_rows":len(holdout),"no_change_MAE":round(mae0,6),"momentum_MAE":round(mae1,6),
             "MAE_improvement_positive_is_better":round(mae0-mae1,6),
             "cluster_bootstrap_95pct_improvement":_bootstrap_cluster_ci(holdout,lambda r:abs(r["actual_next"]-r["no_change"])-abs(r["actual_next"]-r["momentum"]))}
    else: metrics["one_hour_momentum_test"]={"test_rows":0,"reason":"insufficient contiguous, pre-event hourly candles"}

    counts={}
    with sqlite3.connect(db_path) as db:
        for table in ("events","contracts","markets","quotes","orderbook_snapshots","market_trades","sportsbook_lines","alternate_ladders","predictions","paper_orders","paper_fills","settlements","research_experiments","model_versions","data_quality_flags"):
            counts[table]=db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        dt=db.execute("SELECT MIN(exchange_ts),MAX(exchange_ts) FROM quotes WHERE exchange_ts IS NOT NULL").fetchone()
    try: commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    except Exception: commit=None
    manifest={"experiment_id":"v9-kalshi-public-20261021","created_utc":datetime.now(timezone.utc).isoformat(),
              "git_commit":commit,"dataset_sha256":store.dataset_hash(),"dataset_counts":counts,
              "quote_exchange_timestamp_range_utc":dt,"historical_event_sample_policy":"Kalshi KXNBAGAME binary contracts with venue settlement and indicative midpoint no later than 00:00 UTC one day before event date in native ticker",
              "limitations":["Retrospective public candles were not locally captured at historical event time; this is indicative probability research, not strict as-captured historical replay.","Kalshi venue settlement labels have not been independently checked against official NBA records.","Event date is known but exact scheduled tipoff timestamp was not retrievable; one-day calendar buffer was used as a conservative pre-event proxy.","No synchronized sportsbook or Polymarket comparison data are in this experiment.","No L2 depth is available in historical candles; no executable return or P&L is calculated."]}
    result={"manifest":manifest,"market_calibration":metrics}
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    experiment_id=manifest["experiment_id"]
    config={"market_series":"KXNBAGAME","quote":"historical Kalshi candle midpoint","decision_rule":"latest quote at or before 00:00 UTC one day before ticker event date","calibration_baseline":"constant 0.5","movement_model":"fixed one-hour last-return extrapolation; chronological last-30-percent event holdout","bootstrap_repetitions":3000,"random_seed":41}
    with closing(sqlite3.connect(db_path)) as db, db:
        db.execute("INSERT OR REPLACE INTO research_experiments(experiment_id,created_ts,git_commit,dataset_hash,config_json,train_start,train_end,test_start,test_end,results_json,interpretation,promotion_decision) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (experiment_id,manifest["created_utc"],manifest["git_commit"],manifest["dataset_sha256"],json.dumps(config,sort_keys=True),
                    events[0][1] if events else None,events[max(0,int(len(events)*.7)-1)][1] if events else None,
                    events[int(len(events)*.7)][1] if len(events)>int(len(events)*.7) else None,events[-1][1] if events else None,
                    json.dumps(metrics,sort_keys=True),"Exploratory indicative venue-price research; insufficient for an edge claim.","EDGE_NOT_YET_VALIDATED"))
        result["manifest"]["dataset_counts"]["research_experiments"]=db.execute("SELECT COUNT(*) FROM research_experiments").fetchone()[0]
    Path(output).write_text(json.dumps(result,indent=2,sort_keys=True))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument("--db",default="data/raw/v9_markets.sqlite3");p.add_argument("--output",default="results/v9_kalshi_experiment.json")
    print(json.dumps(analyze(p.parse_args().db,p.parse_args().output),indent=2))

if __name__=="__main__":main()
