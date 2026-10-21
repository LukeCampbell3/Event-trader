# Market convergence and movement research

`market_engine.market_motion` is retained as a legacy summary feature. V9 adds `probability_motion` for per-contract/per-venue probability velocity, acceleration, cross-venue dispersion and a same-time dispersion-change indicator. It does not assert predictiveness.

Midpoints are descriptive only. Use bid/ask sides when evaluating execution, and never compare incompatible outcome rules. Quotes need source timestamps and staleness checks; rows without a supported mapping stay venue-native.

Lead-lag evaluation must pair past movement at A with a strictly later movement at B, keep timestamp availability, and compare against no-change and consensus baselines. Concurrent correlation is not prediction. Historical candle endpoint timestamps downloaded retrospectively do not prove local availability then; those records are only suitable for indicative probability research unless an availability assumption is separately justified.

No real multi-venue lead-lag result is claimed in this release. The previous v7 fish experiment is explicitly synthetic.
