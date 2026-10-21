# NBA Polymarket Trader v8 — PAPER-ONLY RESEARCH SYSTEM

**STATUS: NOT PROFIT VALIDATED. NO REAL ORDERS. 0 verified actionable edges.**

This version redirects the prior v7 shoal (lead/lag / convergence) into a US-oriented
Polymarket player-prop + game-event scanner. It deliberately does not automate trading
until a statistically supported strategy, legally accessible account, execution
semantics, fees, and position reconciliation have passed independent certification.

## Official venue distinction

- **Polymarket US**: official `polymarket-us` Python SDK, public market discovery,
  `markets.bbo(slug)` and `markets.book(slug)`; authenticated order methods exist
  but **our `send_live_order()` is hard-disabled**. Use if eligible in your jurisdiction.
- **Polymarket.com (international)**: different platform. The previous
  `legacy/shoal_v7.py` and the v7 package support read-only international market
  data as a possible information signal. *Do not route live U.S. orders to it.*
- **Sportsbooks**: reference prices must be sourced independently and have both
  YES and NO (e.g. over and under) at the *exact same threshold*, within a
  synchronized time window. No legal claim of executable sportsbook hedges.

## What the engine can do

1. Discover NBA listings on Polymarket US through the official SDK. Save raw JSON
   for an analyst to review, **not fuzzy-auto-map**.
2. Capture current bid, ask and **top-of-book offer depth** for explicitly mapped,
   resolution-reviewed US markets; missing fields block capture.
3. Ingest synchronized two-sided sportsbook odds and remove their margin.
4. Derive conservative **conditional** probability and ROI screens with reference
   disagreement penalty, quote age checks, fee / slippage reserves, spreads and
   depth controls. The target's own exchange price is *not* used as a probability
   reference. This is an assumption-driven estimate, **not a true EV guarantee**.
5. Examine player props and game winners/totals **only with exact event and
   settlement identifiers**. Market periods, rules, DNP, void, and OT must match.
6. Interpolate *interior* alternate probabilities in logit space; mark estimated
   points as inferred. No extrapolation used to establish an edge.
7. Compute multi-venue probability velocity, directional agreement and
   convergence from 3+ time-aligned observations per venue. Motion is a feature,
   not independently verified alpha.
8. Freeze paper decisions before tipoff in SQLite, dedupe repeats and settle once.
9. Evaluate the opposing NO outcome as **informational only** until the short-side
   execution and liquidity semantics are verified for the US venue.
10. Carry forward the v5 joint P/R/A/PA/PR/RA/PRA solver and correlated parlay
   mathematics in `legacy/v5/`. No assumed independence for same-game parlays.

## Try it immediately with the clearly artificial data

```bash
python make_fixture.py
python -m unittest discover -s tests -v
python cli.py evaluate \
  --contracts data/synthetic/contracts.jsonl \
  --exchange data/synthetic/exchange.jsonl \
  --sportsbooks data/synthetic/sportsbooks.jsonl \
  --asof 2026-10-21T12:30:00+00:00 \
  --output results/synthetic_screen.jsonl \
  --paper-db results/synthetic_paper.db
python cli.py paper-summary --db results/synthetic_paper.db
```

Every fixture contract, name, game, and price is **FAKE** and exists to test the
algorithm. A 14.7% conditional ROI on the planted error demonstrates detection
and does not imply the existence of a real bet.

## Free API workflow (environment with network connectivity)

```bash
pip install -r requirements.txt
python cli.py discover-us --query NBA --output data/us_discovery.json
# Inspect sports, player props, event times, resolution and cancel rules
# Build your manually reviewed contracts.jsonl (format: data/synthetic/contracts.jsonl)
python cli.py capture-us --contracts contracts.jsonl \
  --fee-reserve 0.025 --output data/live_exchange.jsonl
# Enter independently captured, time-aligned sportsbook O/U odds (or
# implement a supported licensed data feed) in the JSONL sportsbook format.
python cli.py evaluate --contracts contracts.jsonl \
  --exchange data/live_exchange.jsonl --sportsbooks sportsbook_pairs.jsonl \
  --asof '2026-11-01T18:00:00+00:00' --output results/screens.jsonl \
  --paper-db results/ledger.db
```

The `--asof` is illustrative. For a real scan, use the same real UTC time at capture.
**Do not fabricate source timestamps or mark review fields true without review.**
The US API may change shapes or restrict particular endpoints; parser integration
has been unit-tested with mocks, not authenticated against a live market here.

## Prospectively validate before considering real orders

- Collect and freeze pregame opportunities, including *rejections*, with
  immutable capture times, market IDs, rule versions and liquidity.
- Grade against actual settlement for many games; compare Brier/log loss against
  de-vig consensus on **the same events**, compute clustered ROI bootstrap and
  closing-line value, with multiple-testing protection.
- Test time-aligned lead/lag out of sample; restrict to genuinely tradable prices.
- Prove that any genuine arbitrage covers all settlement outcomes **after fees**.
- Assess access restrictions and independently verify bid/ask/fee and order preview.
- Implement/certify live fill reconciliation, cancel/retry, stop-loss, capital limits,
  simultaneous positions and settlement before enabling network trading.

The live entry point `live_guard.send_live_order()` intentionally raises
`LIVE_SUBMISSION_NOT_RELEASE_READY`. It is **not** an executor. Never paste wallet
keys or US API private credentials into this chat or source files.

## Known limitations

- The sandbox executing this research cannot reach Polymarket US or sportsbook
  servers directly; live fetch and authenticated execution were **not tested**.
- No real paired sportsbook quote feed is attached. The prior Oct 20 published
  excerpts are unsynchronized and not safe for execution.
- Usable alternating prop markets depend on what Polymarket US actually lists.
- The illustrative per-share fee reserve is **not a verified fee schedule**.
- Price-shopping advantage or motion does not equal proof of positive expected ROI.
- Paper trades are *screens*, not proof of practical fill. The paper P&L currently
  omits actual exchange fees and cannot substitute for live-execution analysis.

### Convert captured sportsbook pairs from CSV

If your provider or bookmaker offers an authorized CSV export of paired odds,
use `data/sportsbook_csv_template.csv` and run:

```bash
python cli.py import-sportsbook-csv --csv book_export.csv \
  --contracts contracts.jsonl --output sportsbook_pairs.jsonl
```

A missing side, unknown event mapping, invented capture timestamp or settlement
mismatch is rejected. This is not a live sportsbook scraper; use an authorized
source and verify that odds are still offered before any trading decision.

### Optional external market sensors

The prior v7 read-only Kalshi and international Polymarket.com adapters and
lead/lag simulation are retained under `legacy/`. They can provide reference
probability flow but must not be treated as tradable US Polymarket order books.
No cross-venue contract arbitrage is valid without identical rules, fresh asks,
size, and the ability to trade *both* venues in your jurisdiction.
