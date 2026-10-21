"""Deterministic, read-only research primitives for v9.

The store preserves raw observations and their provenance.  Replay never lets an
observation with an exchange or local timestamp after the decision time enter a
feature row.  Nothing in this module submits orders.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import sqlite3
from contextlib import closing


def utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return dt.astimezone(timezone.utc)


def canonical_threshold(stat: str, convention: str, threshold: float) -> int:
    """Return the minimum integer stat value that settles YES.

    Supported conventions are explicit: ``at_least`` (e.g. 25+) and ``over``
    (e.g. over 24.5). Ambiguous/non-integer-equivalent lines are rejected.
    """
    if not stat or convention not in {"at_least", "over"}:
        raise ValueError("stat and an explicit threshold convention are required")
    x = float(threshold)
    if convention == "at_least":
        if not x.is_integer():
            raise ValueError("at_least threshold must be an integer")
        return int(x)
    # Integer-valued stats: over x means strictly greater than x.
    return int(x) + 1


@dataclass(frozen=True)
class MarketIdentity:
    sport: str
    event_date: str
    participant_id: str
    market_type: str
    stat: str
    yes_minimum: int | None
    period: str
    overtime: bool
    void_rule_id: str
    participation_rule_id: str

    @classmethod
    def player_prop(cls, *, sport: str, event_date: str, participant_id: str,
                    stat: str, threshold: float, convention: str,
                    period: str, overtime: bool, void_rule_id: str,
                    participation_rule_id: str) -> "MarketIdentity":
        return cls(sport.upper(), event_date, participant_id, "player_prop", stat.upper(),
                   canonical_threshold(stat, convention, threshold), period, overtime,
                   void_rule_id, participation_rule_id)


def compare_contracts(a: MarketIdentity, b: MarketIdentity) -> dict[str, Any]:
    """Strict equivalence decision with auditable reason codes."""
    fields = asdict(a)
    differences = [k for k, v in fields.items() if v != asdict(b)[k]]
    return {"equivalent": not differences,
            "reason": "EXACT_CANONICAL_MATCH" if not differences else "MISMATCH:" + ",".join(differences),
            "differences": differences,
            "identity_hash": hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
            if not differences else None}


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, sport TEXT NOT NULL, start_utc TEXT, home_team_id TEXT, away_team_id TEXT, native_ids_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS players(player_id TEXT PRIMARY KEY, display_name TEXT, native_ids_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS teams(team_id TEXT PRIMARY KEY, display_name TEXT, native_ids_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS venues(venue_id TEXT PRIMARY KEY, display_name TEXT, metadata_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS contracts(contract_id TEXT PRIMARY KEY, source TEXT NOT NULL, native_event_id TEXT, native_market_id TEXT, native_contract_id TEXT, canonical_event_id TEXT, player_id TEXT, team_id TEXT, stat TEXT, threshold REAL, threshold_convention TEXT, outcome_side TEXT, period TEXT, overtime INTEGER, rules_hash TEXT, rules_json TEXT NOT NULL DEFAULT '{}', equivalence_status TEXT NOT NULL DEFAULT 'UNVERIFIED', market_kind TEXT, metadata_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS contract_rules(rules_hash TEXT PRIMARY KEY, source TEXT NOT NULL, rules_text TEXT NOT NULL, structured_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS markets(market_id TEXT PRIMARY KEY, source TEXT NOT NULL, native_market_id TEXT NOT NULL, canonical_event_id TEXT, contract_id TEXT, status TEXT, opened_utc TEXT, closed_utc TEXT, source_metadata_json TEXT NOT NULL DEFAULT '{}', UNIQUE(source,native_market_id));
CREATE TABLE IF NOT EXISTS quotes(quote_id TEXT PRIMARY KEY, source TEXT NOT NULL, native_event_id TEXT, native_market_id TEXT NOT NULL, native_contract_id TEXT, canonical_event_id TEXT, contract_id TEXT, player_id TEXT, stat TEXT, threshold REAL, outcome_side TEXT, bid REAL, ask REAL, quantity REAL, exchange_ts TEXT, observed_ts TEXT NOT NULL, processed_ts TEXT NOT NULL, capture_method TEXT, price_kind TEXT NOT NULL CHECK(price_kind IN ('EXECUTABLE','INDICATIVE','TRADE','INFERRED','MODEL','SYNTHETIC')), provenance TEXT NOT NULL, fee_json TEXT NOT NULL DEFAULT '{}', raw_json TEXT NOT NULL DEFAULT '{}', UNIQUE(source,native_market_id,native_contract_id,exchange_ts,price_kind));
CREATE INDEX IF NOT EXISTS quotes_replay ON quotes(observed_ts,exchange_ts,contract_id);
CREATE TABLE IF NOT EXISTS orderbook_snapshots(snapshot_id TEXT PRIMARY KEY, quote_id TEXT NOT NULL REFERENCES quotes(quote_id), bids_json TEXT NOT NULL, asks_json TEXT NOT NULL, captured_ts TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS market_trades(trade_id TEXT PRIMARY KEY, source TEXT NOT NULL, native_market_id TEXT NOT NULL, native_trade_id TEXT, price REAL NOT NULL, quantity REAL, exchange_ts TEXT NOT NULL, observed_ts TEXT NOT NULL, provenance TEXT NOT NULL, raw_json TEXT NOT NULL DEFAULT '{}', UNIQUE(source,native_market_id,native_trade_id));
CREATE TABLE IF NOT EXISTS sportsbook_lines(line_id TEXT PRIMARY KEY, source TEXT NOT NULL, sportsbook TEXT NOT NULL, native_event_id TEXT, contract_id TEXT, stat TEXT, threshold REAL, outcome_side TEXT, american_odds INTEGER, decimal_odds REAL, exchange_ts TEXT, observed_ts TEXT NOT NULL, provenance TEXT NOT NULL, raw_json TEXT NOT NULL DEFAULT '{}', UNIQUE(source,sportsbook,native_event_id,contract_id,outcome_side,observed_ts));
CREATE TABLE IF NOT EXISTS alternate_ladders(ladder_id TEXT PRIMARY KEY, source TEXT NOT NULL, contract_id TEXT NOT NULL, threshold REAL NOT NULL, probability REAL NOT NULL, status TEXT NOT NULL CHECK(status IN ('OBSERVED','INFERRED')), uncertainty_low REAL, uncertainty_high REAL, observed_ts TEXT NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS predictions(prediction_id TEXT PRIMARY KEY, experiment_id TEXT, model_version TEXT NOT NULL, contract_id TEXT NOT NULL, decision_ts TEXT NOT NULL, p_model REAL, p_market REAL, lower_bound REAL, features_json TEXT NOT NULL, decision TEXT NOT NULL, replay_class TEXT NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_orders(order_id TEXT PRIMARY KEY, prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id), side TEXT NOT NULL, limit_price REAL NOT NULL, quantity REAL NOT NULL, submitted_ts TEXT NOT NULL, state TEXT NOT NULL, rationale TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_fills(fill_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES paper_orders(order_id), price REAL NOT NULL, quantity REAL NOT NULL, fill_ts TEXT NOT NULL, fill_model TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settlements(contract_id TEXT NOT NULL, settled_ts TEXT NOT NULL, outcome INTEGER NOT NULL CHECK(outcome IN (0,1)), source TEXT NOT NULL, native_settlement_id TEXT, provenance TEXT NOT NULL, raw_json TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(contract_id,settled_ts));
CREATE TABLE IF NOT EXISTS research_experiments(experiment_id TEXT PRIMARY KEY, created_ts TEXT NOT NULL, git_commit TEXT, dataset_hash TEXT NOT NULL, config_json TEXT NOT NULL, train_start TEXT, train_end TEXT, validation_start TEXT, validation_end TEXT, test_start TEXT, test_end TEXT, results_json TEXT, interpretation TEXT, promotion_decision TEXT);
CREATE TABLE IF NOT EXISTS model_versions(model_version TEXT PRIMARY KEY, created_ts TEXT NOT NULL, code_commit TEXT, config_json TEXT NOT NULL, feature_list_json TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS data_quality_flags(flag_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, flagged_ts TEXT NOT NULL, severity TEXT NOT NULL, reason TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}');
"""


class ResearchStore:
    """Idempotent SQLite store; raw JSON remains available for reprocessing."""
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript(SCHEMA)
            columns={r[1] for r in db.execute("PRAGMA table_info(sportsbook_lines)")}
            if "exchange_ts" not in columns: db.execute("ALTER TABLE sportsbook_lines ADD COLUMN exchange_ts TEXT")

    def add_quote(self, row: dict[str, Any]) -> bool:
        required = {"source", "native_market_id", "observed_ts", "price_kind", "provenance"}
        if not required.issubset(row):
            raise ValueError(f"missing quote fields: {sorted(required-set(row))}")
        observed = utc(row["observed_ts"])
        exchange = utc(row["exchange_ts"]) if row.get("exchange_ts") else None
        if exchange and exchange > observed:
            raise ValueError("exchange timestamp cannot follow local observation timestamp")
        if row["price_kind"] in {"EXECUTABLE", "INDICATIVE"}:
            bid, ask = row.get("bid"), row.get("ask")
            if bid is None or ask is None or not (0 <= float(bid) <= float(ask) <= 1):
                raise ValueError("quote prices must be ordered probabilities in [0,1]")
        if row["price_kind"] == "EXECUTABLE" and row.get("quantity") is None:
            raise ValueError("executable quote requires observed quantity")
        data = dict(row)
        data["observed_ts"] = observed.isoformat()
        data["exchange_ts"] = exchange.isoformat() if exchange else None
        data.setdefault("quote_id", hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest())
        data.setdefault("processed_ts", datetime.now(timezone.utc).isoformat())
        columns = ["quote_id","source","native_event_id","native_market_id","native_contract_id","canonical_event_id","contract_id","player_id","stat","threshold","outcome_side","bid","ask","quantity","exchange_ts","observed_ts","processed_ts","capture_method","price_kind","provenance","fee_json","raw_json"]
        vals = []
        for col in columns:
            v = data.get(col)
            if col.endswith("_json") and not isinstance(v, str): v = json.dumps(v if v is not None else {}, sort_keys=True)
            vals.append(v)
        with closing(sqlite3.connect(self.path)) as db, db:
            cur = db.execute(f"INSERT OR IGNORE INTO quotes({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", vals)
            return cur.rowcount == 1

    def observations_asof(self, decision_ts: str, *, contract_id: str | None = None) -> list[dict[str, Any]]:
        t = utc(decision_ts).isoformat()
        sql = "SELECT * FROM quotes WHERE observed_ts<=? AND (exchange_ts IS NULL OR exchange_ts<=?)"
        args: list[Any] = [t, t]
        if contract_id:
            sql += " AND contract_id=?"; args.append(contract_id)
        sql += " ORDER BY COALESCE(exchange_ts,observed_ts),observed_ts,quote_id"
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            return [dict(x) for x in db.execute(sql, args)]

    def dataset_hash(self) -> str:
        digest = hashlib.sha256()
        tables = {
            "contracts":"contract_id,metadata_json,rules_hash,equivalence_status",
            "markets":"market_id,source_metadata_json",
            "quotes":"quote_id,source,native_market_id,contract_id,bid,ask,quantity,exchange_ts,observed_ts,price_kind,provenance,raw_json",
            "orderbook_snapshots":"snapshot_id,quote_id,bids_json,asks_json,captured_ts",
            "market_trades":"trade_id,price,quantity,exchange_ts,provenance,raw_json",
            "sportsbook_lines":"line_id,american_odds,decimal_odds,exchange_ts,observed_ts,provenance,raw_json",
            "alternate_ladders":"ladder_id,threshold,probability,status,observed_ts,provenance",
            "settlements":"contract_id,settled_ts,outcome,source,provenance,raw_json",
        }
        with closing(sqlite3.connect(self.path)) as db, db:
            for table, columns in tables.items():
                rows = db.execute(f"SELECT {columns} FROM {table} ORDER BY 1").fetchall()
                digest.update(table.encode()+b"\0")
                for row in rows:
                    digest.update(json.dumps(row,sort_keys=True,default=str,separators=(",",":")).encode()+b"\n")
        return digest.hexdigest()


def replay_decisions(store: ResearchStore, decision_times: Iterable[str],
                     min_book_depth: float = 1.0) -> list[dict[str, Any]]:
    """Chronological market-state replay; no settlement joins or order creation.

    An ask is executable only for an explicitly executable quote with ask depth.
    Every other price observation is probability research / indicative replay.
    """
    out = []
    for dt in sorted(decision_times, key=utc):
        rows = store.observations_asof(dt)
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            key = (row["source"], row["contract_id"] or row["native_market_id"])
            latest[key] = row
        for (source, contract), row in sorted(latest.items()):
            executable = row["price_kind"] == "EXECUTABLE" and (row["quantity"] or 0) >= min_book_depth
            out.append({"decision_ts": utc(dt).isoformat(), "source": source,
                        "contract_id": contract, "bid": row["bid"], "ask": row["ask"],
                        "quantity": row["quantity"], "price_kind": row["price_kind"],
                        "replay_class": "EXECUTABLE" if executable else "INDICATIVE_OR_RESEARCH",
                        "observation_ts": row["observed_ts"], "quote_id": row["quote_id"]})
    return out


def probability_motion(observations: list[dict[str, Any]], max_skew_seconds: int = 60) -> list[dict[str, Any]]:
    """Per-contract, per-venue velocity/acceleration and dispersion snapshots."""
    groups: dict[tuple[str,str], list[tuple[datetime,float]]] = {}
    for r in observations:
        p = r.get("probability")
        if p is None and r.get("bid") is not None and r.get("ask") is not None:
            p = (float(r["bid"])+float(r["ask"]))/2
        if p is None or not 0 < float(p) < 1: continue
        timestamp=r.get("exchange_ts") or r.get("observed_ts") or r.get("timestamp")
        if not timestamp: continue
        groups.setdefault((str(r["contract_id"]), str(r["source"])), []).append((utc(timestamp), float(p)))
    by_contract: dict[str,list[dict[str,Any]]] = {}
    for (contract, source), series in groups.items():
        series = sorted(set(series)); derived = []
        for i in range(1, len(series)):
            dt = (series[i][0]-series[i-1][0]).total_seconds()
            if dt <= 0: continue
            v = (series[i][1]-series[i-1][1])/dt
            a = None
            if len(derived) and (series[i][0]-series[i-2][0]).total_seconds()>0:
                a = (v-derived[-1]["velocity_per_second"])/dt
            derived.append({"ts":series[i][0].isoformat(),"previous_ts":series[i-1][0].isoformat(),
                            "probability":series[i][1],"previous_probability":series[i-1][1],
                            "velocity_per_second":v,"acceleration_per_second2":a})
        if derived:
            by_contract.setdefault(contract,[]).append({"source":source,"latest":derived[-1],"points":len(series)})
    out=[]
    for contract, venues in sorted(by_contract.items()):
        probs=[v["latest"]["probability"] for v in venues]
        velocities=[v["latest"]["velocity_per_second"] for v in venues]
        previous = [v["latest"]["previous_probability"] for v in venues]
        current_times=[utc(v["latest"]["ts"]) for v in venues]
        previous_times=[utc(v["latest"]["previous_ts"]) for v in venues]
        synchronized=(len(venues)>1 and (max(current_times)-min(current_times)).total_seconds()<=max_skew_seconds
                      and (max(previous_times)-min(previous_times)).total_seconds()<=max_skew_seconds)
        convergence=(max(probs)-min(probs) < max(previous)-min(previous)) if synchronized else None
        divergence=(max(probs)-min(probs) > max(previous)-min(previous)) if synchronized else None
        out.append({"contract_id":contract,"venues":len(venues),"dispersion":max(probs)-min(probs),
                    "velocity_dispersion":max(velocities)-min(velocities),
                    "median_velocity_per_second":sorted(velocities)[len(velocities)//2],
                    "convergence":convergence,"divergence":divergence,
                    "synchronized_for_dispersion_change":synchronized,
                    "venue_signals":venues,"predictive_evidence":False})
    return out

