# V9 real-market research report

**Run date:** 2026-10-21 UTC  
**Branch:** `feature/v9-real-market-edge-research`  
**Code commit recorded in run:** `10d9a4b6e574c366a118e29aee769e0fc9ac8f2a`  
**Dataset SHA-256:** `ddbbcec60a40699902bdb85692354003bfe21149c8fe9950996f9dae5c16c805`  
**Decision:** `EDGE_NOT_YET_VALIDATED`; no candidate is approved for paper trading or live trading.

## Evidence labels

- **VERIFIED:** 43 repository tests pass; public Kalshi endpoints responded and records were stored with source metadata. This verifies code/data capture behavior, not market truth or performance.
- **MODEL_DEPENDENT:** Brier, log-loss, calibration and price-movement estimates below depend on the one-day pre-event proxy and Kalshi venue settlement.
- **SYNTHETIC:** Legacy v7 lead/lag controls and v8 planted-error examples remain synthetic; they are not included as real-market evidence.
- **UNVERIFIED:** Sportsbook and Polymarket comparisons, official NBA result matching, fills, fees and any positive trading edge.
- **BLOCKED:** Historical executable replay and full multi-market validation lack synchronized historical order books, matched sources and independently verified settlements.

## Collection and coverage

Public Kalshi data was collected on 2026-10-21. Coverage includes 72 canonical event records, 220 native contracts/markets, 60,311 quote observations, 20 current L2 snapshots and 200 venue settlement records. Historical quote exchange timestamps span 2026-10-02 22:00 UTC through 2026-10-21 04:00 UTC. There are no stored trades, sportsbook lines, alternate-ladder reconstructions, model versions, predictions, paper orders or fills. The historical candles are **indicative** and downloaded retrospectively; they do not establish what this process had captured at the time. Current L2 is a top-of-book observation, not proof that an order would fill.

The run contained 100 game-contract history requests, 17,748 one-minute candles in the initial three-hour lookback, 29,672 additional candles in the expanded lookback, and 11,619 60-minute game candles; idempotent storage deduplicates overlaps. Prop collection covered 25 each for PTS, REB, AST and PRA and yielded 1,121 hourly candles across those series. Current capture stored 20 order-book snapshots across game, PTS, REB, AST and PRA series. The experiment uses only valid pre-event-proxy quotes and settled game contracts.

Data sources actually accessed: Kalshi public market catalog, public order book and public historical candlesticks. Polymarket US direct discovery returned HTTP 401 for missing required API key headers. Polymarket international search was inspected but did not yield a reviewed current NBA mapping. The Odds API was implemented as an optional adapter but no key was available, so no sportsbook rows were collected. Official NBA CDN scoreboard access returned HTTP 403; no workaround was attempted. No independent NBA result source was ingested.

## Historical probability research

Decision time is a conservative calendar proxy: 00:00 UTC one day before the date encoded in each native ticker. It is not exact tipoff time. The test compares Kalshi indicative YES midpoint to its eventual venue settlement; midpoint is not an executable purchase price.

| Measure | Result |
|---|---:|
| Settled game-contract observations / unique events | 98 / 49 |
| Midpoint Brier score | 0.265859 |
| Constant 0.50 Brier baseline | 0.250000 |
| Brier difference (market minus baseline) | +0.015859 |
| Event-cluster bootstrap 95% interval for difference | [-0.014728, +0.047418] |
| Midpoint log loss | 0.725895 |
| Constant 0.50 log loss | 0.693147 |
| Directional accuracy | 44.9% |

The point estimates do not beat a constant 50% forecast. The uncertainty interval is wide and includes no difference. These data do not establish that the market is mispriced; they may also reflect settlement labels, event mapping, or the calendar-only cutoff.

For 49 event clusters, a pilot-variance normal approximation estimates roughly 994 clusters to detect a 1 percentage-point Brier difference, 249 for 2pp and 40 for 5pp at 80% power and two-sided 5% alpha. The current-sample minimum detectable absolute difference is about 4.50pp. These are planning approximations from a small pilot, not a guarantee of power.

### Calibration bins

| Midpoint probability | Contracts | Mean p | Settled YES rate |
|---|---:|---:|---:|
| 20–30% | 3 | 28.0% | 33.3% |
| 30–40% | 15 | 34.7% | 46.7% |
| 40–50% | 29 | 45.3% | 62.1% |
| 50–60% | 29 | 54.0% | 41.4% |
| 60–70% | 19 | 64.7% | 47.4% |
| 70–80% | 3 | 72.8% | 66.7% |

Bins are small and noisy; no recalibration was selected from this test sample.

### Cross-outcome consistency

There were 49 opposing YES-contract pairs; 47 had candles within one hour. Mean absolute deviation of the pair midpoint sum from 1 was 0.007653, maximum 0.03. No synchronized pair had two indicative YES asks summing below 1; the minimum sum was 1.02. These indicative candles cannot establish simultaneous execution or arbitrage.

### Movement / lead-lag test

A fixed one-hour last-return extrapolation was evaluated on the chronological final 30% of unique event dates, keeping dates intact: training through 2026-10-13 (28 event IDs), test from 2026-10-14 (21 event IDs), 1,861 contiguous hourly rows. No-change MAE was 0.012289; momentum MAE was 0.021123. Improvement defined as no-change MAE minus momentum MAE was -0.008834, with event-cluster bootstrap interval [-0.010509, -0.007592]. In this sample momentum was worse. This is one-venue market-price movement prediction, not cross-venue lead-lag; no market-leadership claim is supported.

### Player props and features

The 25 PTS, 25 REB and 25 AST settled contracts had no eligible pre-event hourly candle under the selected cutoff. PRA had 15 eligible quote/settlement observations, all from one game and only five player-game clusters; Brier was 0.250703 versus 0.25 for constant 50%, and the clustered interval for the difference was [-0.002308, +0.003397]. This is inadequate for inference. M0–M5 ablations, Lasso outcome prediction, tail ROI and dependence-aware parlay evaluation could not be run on this dataset.

Legacy Lasso results are only price reconstruction: the prior two-game/20-player-game-group analysis reported withheld alternate-price MAE 0.837 percentage points versus 1.896pp for its logit baseline. It does not show outcome calibration or EV. The prior cross-market exercise found 0/10 conservative over edges and 0/10 under edges. No new Lasso feature-selection results were produced.

## Replay, execution and paper trading

Timestamp-aware storage and deterministic replay foundations are implemented and tested. Retrospective candles have historical exchange timestamps but current observation timestamps, so strict as-captured replay correctly excludes them. No historical synchronized order-book depth or paired sportsbook quotes exist; executable replay, transaction-cost adjusted ROI, fills, drawdown and realized P&L are therefore unavailable. The 20 current L2 snapshots were not used to create frozen model predictions or paper orders. Prospective paper-trading status: **not started / zero orders**. Real-money execution remains disabled.

## Acceptance status and next experiment

- **Engineering:** research foundation implemented, but full V9 engineering acceptance is not complete: official outcome ingestion, synchronized adapters, fully operational signal-to-paper workflow and required end-to-end validations remain.
- **Real-data validated:** not met; genuine venue data exists, but independent outcomes and cross-source matching are absent.
- **Edge supported:** not met. No profitable claim is made.

The highest-value next experiment is to start prospective collection of synchronized Kalshi top-of-book, reviewed Polymarket international tokens where available, and exact-threshold sportsbook prices; freeze a market-only baseline and model version before each event; then join to an independently accessible official result feed. Accumulate at least hundreds of independent games, with sample-size reassessment from the prospective variance. A free Odds API key may enable current odds capture; historical odds access is not part of its free plan. For each candidate preserve the actual ask, depth, capture time and costs, and paper-log rejected candidates as well as any accepted ones.

Reproduction commands (from repository root):

```powershell
python -m unittest discover -s tests -q
python kalshi_public.py history --db data/raw/v9_markets.sqlite3 --series KXNBAGAME --limit-per-series 100 --lookback-hours 10
python kalshi_public.py history --db data/raw/v9_markets.sqlite3 --series KXNBAGAME --limit-per-series 100 --from-open --interval 60
python kalshi_public.py history --db data/raw/v9_markets.sqlite3 --series KXNBAPTS KXNBAREB KXNBAAST KXNBAPRA --limit-per-series 25 --from-open --interval 60
python kalshi_public.py current --db data/raw/v9_markets.sqlite3 --series KXNBAGAME KXNBAPTS KXNBAREB KXNBAAST KXNBAPRA --limit-per-series 4
python v9_experiments.py --db data/raw/v9_markets.sqlite3 --output results/v9_kalshi_experiment.json
```

Raw data and results are local ignored artifacts and are not committed. See `results/v9_kalshi_experiment.json` for the run manifest and machine-readable metrics.
