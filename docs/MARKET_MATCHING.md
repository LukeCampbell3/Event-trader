# Contract and event matching

## Current rule

V9 uses `MarketIdentity` in `v9_research.py` for strict comparison. A player-prop key contains sport, event date, stable participant identifier, statistic, minimum integer value that settles YES, period, overtime inclusion, void rule, and participation rule. A comparison returns a reason code and a stable identity hash. Any mismatch rejects equivalence.

For integer-valued stats, `at_least 25` and `over 24.5` both canonicalize to a minimum value of 25. `over 25.5` canonicalizes to 26 and does not match. Fractional/stat-specific definitions require a future explicit rule rather than title-based guesses.

## Required source fields

Keep native event/market/contract IDs, participant IDs, exact threshold text, period, overtime, cancellation/void/DNP rules, and source rule text. A contract remains `UNVERIFIED` until the rules and identity are reviewed. Canonical mappings must retain reviewer, reason, and rule hash in the research record.

## Rejection conditions

Reject missing/ambiguous player or event identifiers, timezone/date mismatch, different stat definitions, threshold cutoff mismatch, regulation/full-game mismatch, overtime mismatch, void/DNP mismatch, or conflicting event postponement rules. Matching player/team names alone is insufficient.

Current Kalshi ingestion stores venue-native markets and deliberately records zero canonical event matches. US Polymarket and international Polymarket are never assumed equivalent.
