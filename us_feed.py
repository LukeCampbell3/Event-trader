"""Public Polymarket US reader (separate from international Polymarket.com).

Use official `polymarket-us` Python SDK. Contract manifest must be reviewed
manually: a title match is not proof of an identical settlement condition.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from market_engine import Contract, ExchangeQuote, dump_jsonl


def utc_now():return datetime.now(timezone.utc).isoformat()


def _number(obj):
    if isinstance(obj,dict):
        if obj.get('value') is None: raise ValueError('missing price value')
        return float(obj['value'])
    return float(obj)


def parse_us_book(contract: Contract, bbo: dict, depth: dict, fee_reserve: float,
                  captured: str | None = None) -> ExchangeQuote:
    """Expected response envelope from official SDK: {'marketData':{bestBid,bestAsk}}.
    For YES contract ask-depth, we require order book offers with *known* size field;
    refuse if unknown instead of inventing executable liquidity.
    """
    bb=bbo.get('marketData')
    book=depth.get('marketData')
    if not isinstance(bb,dict) or not isinstance(book,dict):
        raise ValueError('unexpected Polymarket US BBO/book format')
    if bb.get('bestBid') is None or bb.get('bestAsk') is None:
        raise ValueError('no two-sided quote')
    bid,ask=_number(bb['bestBid']),_number(bb['bestAsk'])
    levels=book.get('offers') or book.get('asks')
    if not isinstance(levels,list): raise ValueError('missing book offer depth')
    shares=0
    for level in levels:
        try:
            px=_number(level.get('price'))
            if abs(px-ask)>1e-6:continue
            quantity=level.get('qtyDecimal',level.get('quantity',level.get('qty',level.get('size'))))
            if quantity is not None:shares+=int(float(quantity))
        except (ValueError,TypeError):continue
    q=ExchangeQuote(contract_id=contract.contract_id,captured_utc=captured or utc_now(),
        yes_bid=bid,yes_ask=ask, yes_ask_depth=shares,
        fee_per_share_cap=fee_reserve,source='Polymarket_US',
        market_status=contract.market_status,provenance='official_US_SDK_live_BBO')
    if not q.valid():raise ValueError('unusable bid/ask')
    return q


def _client():
    try:
        from polymarket_us import PolymarketUS
    except ImportError as e:
        raise RuntimeError('Install official SDK: pip install polymarket-us') from e
    return PolymarketUS()


def discover_nba(output: str, query: str = 'NBA', client=None):
    """Public raw search. For discovery only; NO auto mapping or trading."""
    owned = client is None
    c=client or _client()
    try:
        data=c.search.query({'query':query})
        Path(output).parent.mkdir(parents=True,exist_ok=True)
        Path(output).write_text(json.dumps({'captured_utc':utc_now(),'provider':'Polymarket_US',
             'unreviewed_results':data},indent=2,default=str))
        return data
    finally:
        if owned:c.close()


def capture_us(contracts: list[Contract], output: str, fee_reserve: float,
               client=None) -> tuple[list[ExchangeQuote],list[dict]]:
    owned=client is None
    c=client or _client()
    q=[]; rejected=[]
    try:
        for contract in contracts:
            try:
                if not contract.valid() or not contract.rules_verified:
                    raise ValueError('contract not manually verified')
                stamp=utc_now()
                bbo=c.markets.bbo(contract.market_slug)
                depth=c.markets.book(contract.market_slug)
                q.append(parse_us_book(contract,bbo,depth,fee_reserve,stamp))
            except (KeyError,TypeError,ValueError,RuntimeError) as ex:
                rejected.append({'contract_id':contract.contract_id,'reason':str(ex)})
    finally:
        if owned:c.close()
    dump_jsonl(output,[x.__dict__ for x in q]);return q,rejected
