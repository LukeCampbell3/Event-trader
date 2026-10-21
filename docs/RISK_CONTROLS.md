# Risk controls and model promotion

The release is research-only. Live order submission remains disabled in `live_guard.py`. Public adapters make GET requests only. Credentials are not needed by the Kalshi public collector and no secrets were collected.

Opportunity classes must remain evidence-specific: `UNVERIFIED`, `RESEARCH_ONLY`, `MODEL_DEPENDENT`, `PAPER_ELIGIBLE`, `ROBUST_CANDIDATE`, or `EXECUTABLE_ARBITRAGE`. The last four require progressively stronger independent calibration, uncertainty, cost, depth and portfolio/settlement evidence. No price gap alone qualifies.

Risk checks for future paper orders: exact settlement equivalence, fresh executable ask and size, cost-adjusted EV, conservative probability bound, caps on per-event exposure and correlated outcomes, and settlement/void mapping. Missing information results in `NO_TRADE`.
