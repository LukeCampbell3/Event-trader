# Statistical validation status

## Baseline findings

The legacy v4 report has two games and 60 withheld alternate thresholds across 20 player-game groups. Nested/grouped Lasso lowered error in reconstruction of quoted alternate prices. This is not outcome calibration. Its cross-market dependence checks reported 0/10 conservative over edges and 0/10 under edges.

The v7 lead-lag positive and negative controls are simulated. They are not real-market evidence. The v8 fixture intentionally plants one conditional signal and must not be scored as a strategy experiment.

## Metrics and split protocol

Use chronological train/validation/test periods; group by game and player-game; keep complete alternate families together. Freeze model choices before the final test. Compare market-only baseline against ladder shape, cross-market constraints, movement, opportunity/environment, and regularized residual features on identical events. Report Brier, log loss, calibration, price movement MAE, closing-line value, net returns only where executable, drawdown, trade count and depth. Use game-cluster bootstrap and family-wise/multiple-test controls.

## Power and promotion

For a binary outcome, minimum sample size depends on baseline rate, effect size, alpha, power and clustering. Estimate it before prospective evaluation; do not interpret a small hit-rate sample. Model promotion needs calibration and conservative EV surviving realistic fees plus out-of-sample/prospective results. No candidate currently satisfies this gate.

## V9 automated coverage

`tests/test_v9_research.py`, `tests/test_kalshi_public.py`, and `tests/test_odds_api.py` verify threshold identity, strict rule mismatch rejection, timestamp order, future data exclusion, idempotent storage, executable-vs-indicative classification, provider parsing and deterministic replay. These are mathematical/engineering checks only.
