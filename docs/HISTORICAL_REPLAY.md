# Historical replay

`ResearchStore` persists native quote observations with separate exchange, local-observation and processing times. `replay_decisions` orders decision times deterministically and only reads rows whose source/event and observation times are no later than the decision. Settlement data are not joined into model features.

Only an `EXECUTABLE` row with displayed ask quantity meeting the configured depth is classed as executable replay. Historical candles are always `INDICATIVE_OR_RESEARCH`; their price cannot produce executable P&L. Every replay row preserves quote ID and source.

For retrospective API downloads, local observation time is today. Such rows do not pass a historical as-of replay. Rewriting the local observation time to a candle timestamp would fabricate capture history, so the system refuses that shortcut. For now, historical candle calibration can be analyzed separately with an explicit retrospective-data caveat.

Run manifests should include dataset hash, git commit, decision grid, model/config, data provenance, split boundaries, run timestamp, and output hash. No outcomes are admitted to predictors.
