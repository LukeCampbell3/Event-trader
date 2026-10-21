# Paper trading

The existing `recording.py` ledger freezes conditional v8 signals before event start and deduplicates by contract/time/ask. Its P&L omits actual fees and fill uncertainty; it must be called quote-based paper accounting.

V9's normalized schema adds predictions, model versions, paper orders, paper fills, settlements, experiments and data-quality flags. Decisions need immutable model/config references, independently sourced probability and uncertainty, executable quote/depth, fee/slippage assumptions and rejection rationale. Rejections belong in the opportunity funnel.

For current sportsbook snapshots, set `ODDS_API_KEY` from an optional provider free account and run `python odds_api.py`; start with small event/market selections to stay inside the provider's monthly quota. Historical sportsbook odds are paid-plan-only and are not required for basic ingestion, but the absence of free historical sportsbook snapshots is a key blocker for aligned retrospective cross-market research.

No live trading is introduced. `live_guard.send_live_order` remains hard-disabled. The present collector only reads public market data. Historical settlements pulled from a venue are attributed to that venue, not silently described as official game data.
