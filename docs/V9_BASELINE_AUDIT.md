# V9 baseline audit

Audit date: 2026-10-21. Branch: `feature/v9-real-market-edge-research`.

## State and evidence

- Starting checkout was clean on `main` at `b260c32`; the requested feature branch was created from that commit. No unrelated working changes were present.
- Current v8 core is in `market_engine.py`, `us_feed.py`, `sportsbook_csv.py`, `recording.py`, and `live_guard.py`. The live submission function is intentionally disabled.
- Synthetic fixtures and their tests are useful for math and fail-closed behavior only. They do not measure accuracy, return, or fill quality.
- Existing sources include a public Polymarket US SDK adapter; an older international Polymarket/Kalshi candle reader; v5 prop-line ingestion, ladder reconstruction and joint-statistic optimization; an append-only-style pregame ledger; and an experimental motion function.
- Existing report `legacy/v5/legacy_v4/VALIDATION_REPORT.md` documents 280 public-excerpt quote rows for two games, price interpolation and an assumed-vig model. Lasso improves reconstruction of hidden *quoted prices* in those examples, not player outcomes. Ten cross-market calculations yielded zero positive conservative conditional candidates and zero executable edges.
- `legacy/v7_experiment.py` contains a simulated positive control and negative control. The market process is artificial; its output is not evidence about real market dynamics.

## Verified working at baseline

- Two-way American odds conversion and de-vig normalization.
- Conditional screening with quote freshness, source skew, depth, spread, rule match, and a reference-source exclusion.
- Polymarket US book parser with required bid, ask, and offer depth fields (validated with mocks).
- Interior logit ladder interpolation and safe rejection of nonmonotone ladders.
- Paper signal deduplication, freeze-before-start checks, settlement and summary (SQLite).
- Fail-closed live submission guard.

## Untested or not established

- Polymarket US adapter has not been validated against a live authenticated account/session. Although SDK documentation describes public discovery, direct unauthenticated REST probing in this environment returned HTTP 401 `Missing required API key headers`.
- Existing Kalshi history reader was code, not a completed ingestion run. Its historical candles lack order-level fill guarantees.
- No accepted synchronized free sportsbook feed, no saved real multi-venue paired quotes, and no official NBA outcomes feed were present at baseline.
- No deterministic event-sourced replay, normalized research database, cross-venue contract equivalence proof, chronological walk-forward model, statistical power analysis, or prospective real paper ledger was present.
- Current paper summary ignores actual fees and fill behavior. The screen's conservative probability adjustment is a sensitivity rule, not a calibrated lower confidence bound.

## Assumptions and statistical risks

- De-vigged sportsbook consensus is treated as a conditional reference, not truth.
- Lasso price reconstruction can overfit a small, dependent quote sample; adjacent alternates are not independent event outcomes.
- Existing motion uses first-to-last slope and coarse alignment, not an out-of-sample predictive lead/lag test. It does not demonstrate market leadership.
- Player thresholds, markets and observations overlap; naive row-level confidence intervals would be too narrow.
- Historical API data retrieved today do not establish that those data were captured or available locally at their event timestamps. A candle timestamp is not a documented publication timestamp.
- Kalshi venue-reported settlement is useful for venue-contract grading but is not yet independently matched to an official NBA result record.

## Information leakage and replay readiness

Baseline is not ready for historical executable replay. A screenshot/article quote is not synchronized, an exchange candle is indicative, and settlement/status fields must not enter the prediction feature set. V9 adds separate `exchange_ts`, `observed_ts`, and `processed_ts`; replay only consumes rows observed by the decision time. Retrospectively downloaded candles therefore cannot be represented as historically captured observations.

## Coverage

Baseline test suite: `tests/test_engine.py` covers the v8 synthetic math and safe-screen behavior, parser mocks, and paper persistence. The legacy v5 tests cover prop import, settlement lookup and joint-probability math. Neither is strategy validation. New v9 tests are listed in `docs/STATISTICAL_VALIDATION.md` as implemented.

## Main limitations to real edge validation

1. A sufficiently long, timestamped history of synchronized L2 and paired sportsbook prices.
2. Deterministic canonical event/player/rules mapping reviewed against native contracts.
3. Independent official game/player outcomes, including DNP and void handling.
4. Prospective observations and frozen model versions across enough independent games.
5. Fill/fee/slippage evidence at trade size. Until then, historical results are probability research or indicative replay, not executable P&L.
