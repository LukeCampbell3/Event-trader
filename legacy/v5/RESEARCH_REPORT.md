# v5 Execution and research report

Date of source odds: October 20, 2026. Code assembled and executed in the current session. **No live authenticated odds fetch or betslip verification was performed.**

## What was actually run

- All 16 unit/integration tests: **PASS** (probability identity, cross-market monotone bounds, held-out family isolation, synthetic planted price mismatch, correlated parlay, source timestamp validation, free-provider parser, synthetic ledger freezing, official-NBA-format final box-score validation).
- Synchronized **synthetic** dataset: 21 paired betting markets across seven market families, three distinct thresholds each; **42 over/under held-out tests** and zero certified real bets.
- Real prior archive: **280 original side quote rows**, representing 208 normalized quote markets across two games and several sportsbooks. All lack usable snapshot timestamps. Therefore **zero quotes qualify as synchronized pregame evidence** under strict-mode release rules; no actionable candidates.
- Research-only Knicks–76ers screenshot input: 82 held-out over/under comparisons (including 48 combo sides) across a subset of players and categories. **Zero conditional positive-edge signals**. The narrowest probability interval spanned approximately **94.1 percentage points**. Results are *not* live odds and should not be backdated.
- The synthetic paper-ledger + mock final box score pipeline can be executed and produces graded paper predictions. It does **not** measure real performance.

## Why actual combo ladders change the answer

Synthetic paired market fixture, all inputs created by an artificial independent Poisson distribution, purely for unit testing. Here is how additional observed combo-market constraints alter a *withheld* family result:

| Target event | Marginals-only bound width | With other combo families | Width improvement |
| --- | ---: | ---: | ---: |
| PA >= 15 | 75.66 pp | 68.56 pp | 7.10 pp |
| PR >= 16 | 80.96 pp | 62.56 pp | 18.41 pp |
| PRA >= 15 | 75.88 pp | 49.64 pp | 26.24 pp |
| PRA >= 18 | 100.00 pp | 71.08 pp | 28.92 pp |
| PRA >= 20 | 100.00 pp | 64.73 pp | 35.27 pp |

Those experiments show **identification improvement** from independent *observed* combo thresholds. They do not establish any bookmaker currently misprices those outcomes. Some RA targets did not improve, highlighting that additional constraints aren't always informative.

## Preserved prior Lasso result (v4)

The earlier v4 tests found held-out quoted-price reconstruction mean absolute error of 1.896 pp for logit interpolation and 0.837 pp for grouped Lasso, across the previously selected set of archived ladders. These are archived results preserved in `legacy_v4`, not an updated estimate of outcome-prediction accuracy. We **do not** count Lasso-interpolated probabilities as new independent sportsbook constraints, as doing so would artificially narrow the LP intervals.

## Statistical gates before selecting real bets

1. Feed has timestamped, identifiable sportsbook prices captured before game start, without stale or conflicting sides.
2. Every target family is completely removed before using other observed prices to estimate the target's probability range.
3. Quote consistency is feasible under documented margin and quote-error sensitivity scenarios; inconsistent groups are rejected rather than force-fitted.
4. A candidate's minimum *conditional* ROI exceeds the offered break-even price by a threshold and survives reasonable sensitivity checks.
5. Price availability is checked on the actual sportsbook; the target is **not** certified merely because a stale article differs.
6. Record both accepted and rejected predictions prospectively and score outcomes across independent game/player clusters over time.

Even after these gates, distribution-based relative pricing can be useful without constituting a proof of *true* EV. The strongest guarantee is an executable, terms-checked arbitrage; all other claims require validation of assumptions and outcomes.

## Outcome

**Engineering: operational and tested. Pricing alpha: not demonstrated.** The bottleneck is now reliable, synchronized, two-sided alternate combo coverage across books and games, followed by prospective calibration. No legitimate result can be obtained by endlessly optimizing the same small, unsynchronized October 20 slate.
