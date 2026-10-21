# Probability engine

Existing v8 functions remain available in `market_engine.py`: American-odds conversion, two-way de-vigging, conditional reference screens, and interior logit interpolation. Legacy v5 contains Lasso ladder reconstruction and joint P/R/A probability feasibility tools.

## Evidence classes

- A directly quoted threshold is observed market price evidence, not a true probability.
- A de-vigged price is a margin-adjusted market estimate under the selected de-vig method.
- A ladder interpolation is inferred and cannot be reused as independent evidence.
- A model estimate must identify model version, training data, features and uncertainty.
- A conditional ROI screen is not a confidence interval or verified EV.

## Validation requirements

Evaluate held-out complete market families and chronological groups. Report Brier score, log loss, calibration by probability band, interval coverage/width, unique game/player counts, and dependence-aware uncertainty. Reconstruction MAE measures price-curve reconstruction only. It does not demonstrate outcome calibration.

## Current boundary

No real player-prop outcome probability model is validated. The existing cross-market bounds are dependence-aware but conditional on assumed marginal curves and broad. Do not promote an opportunity until independent outcomes, costs, executable price and held-out uncertainty are available.
