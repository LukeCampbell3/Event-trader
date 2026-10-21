# Archived NBA alternate-line inference — research results

Date of quoted games: **2026-10-20**. Run uses archived odds and no game results. This is a reconstruction/backtest of quote interpolation, **not a verified profitable strategy**.

## Coverage

- 280 archived quote records, 115 player/book/market groups.
- 39 groups have >=3 ordered over thresholds and support conditional full-ladder inference.
- 75 groups have <3 thresholds and are marked `INSUFFICIENT_THRESHOLDS`.
- One article ladder (Karl-Anthony Towns rebounds) is quarantined for a logical order inversion.
- Generated 2,739 estimated integer-threshold rows: 279 *interpolated but not quoted*, 2,320 *extrapolated*, 140 *observed anchor* rows. Most of the full ladder outside the quoted region is strongly assumption-dependent; do not price bets from the tails as though they were directly observed.

## Nested grouped Lasso experiment

Target: raw implied probability of a **held-out alternate line**, predicted from the adjacent easier/harder published alternate lines *from the same event/player/book/market*. (This target includes bookmaker margin; this tests curve reconstruction, not fair betting probability.)

- 60 hidden thresholds across 20 distinct event-player groups; other props from the held-out player-game are excluded from both Lasso training and model selection.
- Uncorrected linear-probability interpolation MAE: **5.210 percentage points**.
- Uncorrected logit-space interpolation MAE: **1.896 pp**.
- Nested GroupKFold Lasso residual correction MAE: **0.837 pp**.
- Mean player-cluster bootstrap estimate of logit-baseline-to-Lasso MAE reduction: **1.068 pp**, descriptive 95% bootstrap interval **0.746–1.402 pp**. This only describes quote-reconstruction error on two games; not a valid CI for future ROI.

Feature ablation (held-out players, MAE pp): baseline **1.896**, local curvature/neighbor probabilities **0.918**, adding threshold locations **0.879**, adding category flags **0.860**, all **0.837**. Hence shape of the neighbor odds curve is the essential ingredient; additional categories and features provide modest gains and are not yet robustly required.

Entire-game holdouts: training PHI-NYK and testing OKC-SAS (15 quotes), MAE **0.653 pp** for all-feature Lasso vs **2.077 pp** baseline. Training OKC-SAS and testing PHI-NYK (45 quotes), **1.208 pp** vs **1.836 pp** baseline. A reduced local-feature model was within 0.007 pp on OKC-SAS and tied on PHI-NYK; favor simplicity until additional games validate category terms.

## Illustrative Brunson inferred points ladder from archived bet365 quotes

| Points >= | Status | Market-implied estimate | Sensitivity envelope |
|--|--|--:|--:|
| 20 | Observed line -650 | 81.8% | 76.8–86.7% |
| 22 | Interpolated | 74.7% | 70.1–79.9% |
| 25 | Observed line -190 | 61.8% | 58.5–67.5% |
| 28 | Interpolated | 48.1% | 45.6–54.0% |
| 30 | Observed line +140 | 39.3% | 37.2–44.6% |
| 35 | Observed line +350 | 21.0% | 19.8–23.5% |

Notes: the observed column names **quoted thresholds**, but the probabilities at those thresholds remain estimates due to one-sided pricing. The central model uses an assumed 6% overround. The envelope varies assumed margin and curve family, not true-world uncertainty.

## Cross-market falsification

Ten P+A/P+R/R+A main-line targets are paired with conditional inferred bet365 marginal ladders; target combo quotes are from a separate, unidentified screenshot sportsbook. A dependence-free Makarov-type bound calculation is performed with conservative margin/model sensitivity inputs.

- 10 targets evaluated.
- **0** positive lower-bound-ROI over candidates.
- **0** positive lower-bound-ROI under candidates.
- **0** certified, current, executable edges.
- Example: Towns P+A over 24.5, screenshot vig-free over ~47.8%; model independence scenario ~46.0%; dependence-free *conditional* possible range ~21.3–79.6%. The latter is far too wide to establish value. Other market/time assumptions expand uncertainty, not narrow it.

## Takeaway

It is feasible to **create conditional full probability ladders** from publicly available partial alternates; they help estimate odds curves and identify malformed prices. Lasso meaningfully improves interpolation of bookmaker quotations but has not been tested enough to justify using it as an outcome forecast. Unrestricted player-stat correlation still makes joint market bounds too wide. Additional synchronized two-sided markets and cross-market constraints are required before claiming robust betting value.
