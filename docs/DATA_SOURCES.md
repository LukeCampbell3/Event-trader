# Data sources and ingestion status

All internal timestamps are UTC. Captures must retain source-native identifiers and raw source payloads. A venue-native market is not canonicalized by title similarity.

## Kalshi public Trade API

- Base URL: `https://api.elections.kalshi.com/trade-api/v2`.
- Public market list, L2 book, and historical candlesticks are accessed without credentials by `kalshi_public.py`.
- NBA series currently targeted: `KXNBAGAME`, `KXNBAPTS`, `KXNBAREB`, `KXNBAAST`, `KXNBAPRA`, `KXNBAPA`, `KXNBAPR`, `KXNBARA`.
- Current order-book captures use top YES bid and top YES ask derived from the opposing NO bid, with displayed quantity. They are classified `EXECUTABLE` as observed book prices at capture time, not as guaranteed fills.
- Historical candle closes are `INDICATIVE`; they do not contain queue priority or guarantee fill. Venue settlement/result fields are retained with source provenance, not treated as independent NBA official validation.
- API smoke check on 2026-10-21 succeeded: public Sports series query returned 4,022 entries; `KXNBAGAME` open query returned 98 markets; public orderbook returned depth. Exact capture counts are recorded in each run manifest.
- Official API reference: [Kalshi API documentation](https://docs.kalshi.com/).

## Polymarket

- Polymarket US and Polymarket international are separate products and are not cross-mapped.
- US reader remains `us_feed.py`, based on the official [Polymarket US Python SDK](https://github.com/Polymarket/polymarket-us-python). SDK docs describe public discovery/BBO/book methods. Direct unauthenticated endpoint probe during this run returned HTTP 401 with a missing API key header. No credentials were available; no key was requested or stored.
- The older international reader under `legacy/` can query public price history, but those prices are indicative and do not establish historical executable bids/asks. Do not mix US and international market contracts.
- No Polymarket history or order book is used in the reported real-data experiment until exact contracts are resolved and timestamp availability is documented.

## Sportsbooks

- Added optional The Odds API ingestion via `odds_api.py`. Its provider currently advertises a free starter tier with 500 credits/month, NBA markets and major US bookmakers; current odds require a free API key in `ODDS_API_KEY`. Historical odds are excluded from the free tier and require a paid plan, so this adapter only collects current odds. It supports player points/rebounds/assists/threes/PRA when returned for the event and two-sided outcomes are stored separately. Provider/bookmaker event matching remains unverified until explicitly mapped. Source docs: [current pricing and coverage](https://the-odds-api.com/) and [API endpoint docs](https://the-odds-api.com/liveapi/guides/v4/).
- No API key was available in this run; no sportsbook rows are counted in real-data experiment metrics.
- CSV import remains available when a user has an authorized provider export. No login/CAPTCHA bypass or inferred missing price is used.

## NBA outcomes

- The requested official NBA CDN scoreboard endpoint `https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json` returned HTTP 403 in this environment on 2026-10-21. No access controls were bypassed.
- Kalshi result fields are retained separately as venue settlement labels; they are not labeled independently verified official box scores.
- Box-score/result integration remains blocked until an accessible authorized official source or user-provided official export is configured.

## Data categories

`EXECUTABLE` = timestamped live order book with displayed size; not a fill guarantee.
`INDICATIVE` = historical candle or non-order quote.
`TRADE` = transaction record.
`INFERRED` = interpolation/reconstructed probability.
`MODEL` = model forecast.
`SYNTHETIC` = generated fixture only.

The SQLite `quotes.price_kind` constraint enforces these distinctions. API payloads and local capture timestamps are retained. API secrets are not used by the public Kalshi adapter.
