"""Paper order ledger and prospectively frozen prediction tracking (no live sends)."""
from __future__ import annotations
import sqlite3, json, hashlib
from datetime import datetime, timezone
from pathlib import Path


def ensure_schema(db_path):
    Path(db_path).parent.mkdir(exist_ok=True,parents=True)
    conn=sqlite3.connect(db_path)
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS candidates (
      id TEXT PRIMARY KEY, captured_utc TEXT NOT NULL,
      contract_id TEXT NOT NULL, event_id TEXT NOT NULL,
      target_start TEXT NOT NULL, quote_price REAL NOT NULL,
      conditional_p REAL NOT NULL, conditional_roi REAL NOT NULL,
      price_source TEXT NOT NULL, original_json TEXT NOT NULL,
      outcome INTEGER, settled_utc TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_candidates_contract ON candidates(contract_id);
    ''')
    conn.commit();return conn


def record_paper(db_path, screening: list[dict], contracts: dict, now_utc: str, allow_zero=False):
    """Freeze paper selections before tipoff; reject hindsight and duplicates."""
    now=datetime.fromisoformat(now_utc.replace('Z','+00:00'))
    if now.tzinfo is None:raise ValueError('need timezone aware UTC now')
    conn=ensure_schema(db_path); inserted=0
    try:
        for x in screening:
            if not x['screen_pass'] or x['p_lower_conditional'] is None:continue
            c=contracts[x['contract_id']]
            start=datetime.fromisoformat(c.start_utc.replace('Z','+00:00'))
            if now>=start:continue
            key=hashlib.sha256(f'{x["contract_id"]}|{now_utc}|{x["exchange_ask"]}'.encode()).hexdigest()
            cur=conn.execute('''INSERT OR IGNORE INTO candidates (
              id,captured_utc,contract_id,event_id,target_start,quote_price,
              conditional_p,conditional_roi,price_source,original_json)
              VALUES(?,?,?,?,?,?,?,?,?,?)''',
              (key,now_utc,x['contract_id'],c.game_id,c.start_utc,
              x['exchange_ask'],x['p_lower_conditional'],x['roi_lower_conditional'],
              'Polymarket_US',json.dumps(x,sort_keys=True)))
            inserted+=cur.rowcount
        conn.commit()
        return inserted
    finally:conn.close()


def settle(db_path, outcomes: dict[str,int],settled_utc: str):
    conn=ensure_schema(db_path);changed=0
    try:
        for key,value in outcomes.items():
            if value not in (0,1):raise ValueError('settlement must be YES=1 or NO=0')
            changed+=conn.execute('UPDATE candidates SET outcome=?,settled_utc=? WHERE contract_id=? AND outcome IS NULL',
                (value,settled_utc,key)).rowcount
        conn.commit();return changed
    finally:conn.close()


def summary(db_path):
    conn=ensure_schema(db_path)
    try:
        rows=conn.execute('SELECT event_id,contract_id,quote_price,outcome,conditional_p FROM candidates').fetchall()
        n=len(rows);settled=[x for x in rows if x[3] is not None]
        # each contract is one paper share bought at best quoted ask; no realized fills,
        # subtract fees/slippage only in screening ROI and do not call this realized ROI.
        pnl=sum((o-price) for g,c,price,o,p in settled)
        return {'total_paper_signals':n,'settled_signals':len(settled),
                'unique_events':len({x[0] for x in settled}),
                'hit_rate':sum(x[3] for x in settled)/len(settled) if settled else None,
                'paper_pnl_before_actual_fees':round(pnl,4),
                'paper_roi_on_quoted_spend':round(pnl/sum(x[2] for x in settled),4) if settled else None,
                'prospective_edge_verified':False}
    finally:conn.close()
