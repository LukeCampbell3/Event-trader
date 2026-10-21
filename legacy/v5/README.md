# NBA Market-Only Joint Probability Engine — v5

## Status

**Working research system, not a validated profitable betting strategy.** No real executable positive-EV pick has been established. It uses current sportsbook odds rather than historical player game logs for model construction. Prices are not ground-truth player probabilities; derived probabilities are conditional on the quoted-price assumptions. No sportsbook account access, bets, cloud jobs, or GitHub workflow has been executed.

The major improvement from v4 is that **all seven market families** can constrain the *same joint probability table* for `P` (points), `R` (rebounds), `A` (assists), `PA`, `PR`, `RA`, and `PRA`:

- Preserve every observed *book/player/game/threshold/timestamp* distinctly. Pair both over and under when available; one-sided milestones stay one-sided.
- Demand snapshots from one named sportsbook taken within 15 minutes of each other and **before game start**. Missing timestamps, tipoffs or unknown provenance => no actionable claims.
- Use observed prices only for event probability constraints. **Inferred alternate-line probabilities from v4 are never independent observations.**
- Hold out the entire target market family before computing the **minimum and maximum** chance of winning the offered over or under across every compatible joint distribution.
- Use an optional *central* entropy-tilted joint distribution, with a prior inferred from **observed component lines** when available. This central estimate is explicitly model-dependent and is not the same as a lower-bound certificate.
- For same-player multi-leg parlays, optimize the probability of the exact event intersection instead of multiplying leg probabilities. Require the actual sportsbook *same-game-parlay quote*, not the product of component payouts.
- Log pregame predictions in an append-only paper ledger and settle them later from final official NBA box scores; report future Brier/ROI, with game/player-level dependence in mind.

## No-cost data ingestion

[PropLine documentation](https://github.com/proplineapi/propline-python/blob/main/README.md) documents a free API key, NBA player points/rebounds/assists and PA/PR/RA/PRA markets. Some sportsbooks expose `line_type` alternate or milestone levels. **No API can force a sportsbook to offer alternate combo thresholds.** The live authenticated API was NOT exercised here because no key was available.

`import_propline.py` wraps the preserved `propline_free.py` parser from our previous prototype. It ignores DFS/pick'em pseudo-odds, flags bad timestamps, prevents over/under price pairing across different captures, preserves one-sided milestones without fabricating an under, and emits normalized CSV for the joint solver.

### Run with a free key (PowerShell)

```powershell
pip install -r requirements.txt
$env:PROPLINE_API_KEY = 'your-key-here'
python import_propline.py --fetch --output data/provider_snapshot.csv
python joint_engine.py --quotes data/provider_snapshot.csv --output results/live
```

### Linux / macOS

```bash
python -m pip install -r requirements.txt
export PROPLINE_API_KEY='your-key-here'
python import_propline.py --fetch --output data/provider_snapshot.csv
python joint_engine.py --quotes data/provider_snapshot.csv --output results/live
```

### Saved provider snapshots (offline/reproducible)

```bash
python import_propline.py --saved-json saved_provider_response.json \
  --asof '2026-10-20T21:00:00Z' --output data/saved_snapshot.csv
python joint_engine.py --quotes data/saved_snapshot.csv --output results/saved \
  --asof '2026-10-20T21:00:00Z'
```

Do not use `--asof` to pretend that a late-captured quote was available earlier: every price must carry its *own captured_at*, and the solver checks both quote timestamps and tipoff.

### Manual hosted use (no local Python)

`.github_workflow_example.yml` is a manual-only GitHub Actions example. Copy it to `.github/workflows/nba-research.yml` in **a repository that you choose**, add `PROPLINE_API_KEY` as a GitHub secret, then run the workflow from the Actions tab and open its artifact. **Nothing was uploaded or scheduled by this project.** Do not commit your API key.

## Reproduce the tests

```bash
python -m unittest discover -s tests -v
python synthetic_fixture.py
python joint_engine.py --quotes data/SYNTHETIC_21_PAIR_QUOTES_NOT_REAL.csv \
  --output results/synthetic
python joint_engine.py --quotes data/archived_oct20_unsynchronized.csv \
  --output results/archive_strict
python joint_engine.py --quotes data/archived_oct20_unsynchronized.csv \
  --allow-unsynced-research --book UnidentifiedScreenshotBook \
  --skip-entropy --output results/archive_diagnostics
```

The synthetic fixture regenerates a simulated event 3 hours in the future. All files named `SYNTHETIC` are artificial, not published sportsbook offers. Archived October 20 data lack `captured_at` and `commence_time`, so default production screening correctly skips them. The archive's public article odds are **not verified sportsbook betslip prices**.

## Prospectively freeze and score

Freeze only real, timestamped, pre-tipoff snapshots (test fixtures are refused by default):

```bash
python prospective.py freeze --quotes data/provider_snapshot.csv \
  --analysis results/live/family_holdout_bounds.csv \
  --asof '2026-10-22T23:00:00Z' \
  --ledger results/pregame_ledger.jsonl
```

The freeze refuses future `asof` values, in-progress games, incomplete provenance, duplicates and synthetic samples. The ledger includes a `created_at_utc` and hashes the source CSV and all model outputs; it is append-only but **not tamper-proof against an administrator**. Replays performed after tipoff are not authentic prospective forecasts.

Completed NBA boxes (10-digit NBA *game ID* is different from the odds provider event ID):

```bash
python nba_boxscore_free.py --nba-game-id 0022400061 \
  --provider-event-id 'YOUR_PROVIDER_EVENT_ID' --output results/boxscore.csv
python prospective.py settle --ledger results/pregame_ledger.jsonl \
  --boxscore results/boxscore.csv --output results/settlements.csv
```

The sample game ID above is an API format example only, **not** the October 20 game. The official NBA CDN endpoint is [`boxscore_{gameId}.json`](https://cdn.nba.com/static/json/liveData/boxscore/boxscore_0022400061.json). `nba_boxscore_free.py` refuses nonfinal games and mismatched NBA game IDs. Names must match the odds source exactly; do not silently merge aliases.

## Evaluate same-player parlay pricing

```bash
python parlays.py --quotes data/provider_snapshot.csv \
  --event 'PROVIDER_EVENT_ID' --player 'PLAYER NAME' --book draftkings \
  --legs-json '[{"market":"P","line":24.5,"side":"over"},{"market":"PA","line":30.5,"side":"under"}]' \
  --parlay-odds '+250'
```

**Same-game quoted parlay odds are required.** The engine refuses to pretend separately quoted single-leg odds multiply into an executable same-game payout. Different-player combinations require a joint player-game model and are **not** priced by this module.

## Key outputs

| File | Meaning |
| --- | --- |
| `results/.../family_holdout_bounds.csv` | Conditional probability interval and worst-case ROI for over *and* under with complete market-family exclusion. |
| `results/.../audit.json` | Timestamp status, parsing issues, solver errors and conditional signal counts. |
| `results/synthetic/bounds_ablations.csv` | Controlled change in held-out bounds when other combo families are added. |
| `results/SYNTHETIC_ONLY_scored.csv` | Artificial paper-trading settlement pipeline test, not real forecast accuracy. |
| `legacy_v4/` | Prior reconstructed per-integer ladders and grouped Lasso test source/results, preserved for comparison. |

## Statistical interpretation and limitations

`market-conditioned central estimate` is a regularized entropy projection of a product-of-marginals prior; it is *not* a directly observed win rate. The LP min/max bounds require assumptions about fair probabilities of sportsbook prices (default paired normalized ±1.5 probability points; one-sided total-margin range 0–15%). Neither constitutes a statistical confidence interval on actual outcomes. Sensitivity-test those assumptions before treating conditional deviations as meaningful.

The state space uses exact **event-preserving compression**: if the highest quoted threshold is `K`, each stat value above `K` is represented by `K` because every supported event is a nonnegative sum tested at or below `K`. This remains exact for the input event predicates, and does NOT imply that all exact tail stat totals are known. The program fails instead of overallocating state arrays if `(K+1)^3 > 200,000`.

No arbitrage or profitable selection is *proven* just because a source article displays contradictory prices. Actionability also requires verified ability to place bets at the published odds and valid settlement/payout rules. Price-family validation, a research signal, and true positive expected value are different evidentiary levels.

## Next dataset milestone

Capture **3–8 contemporaneous over/under thresholds** for each available combo family and its individual components, plus enough different games to validate grouped calibration and bet returns. Evaluate *whole-family holdouts* and prospective outcomes. One-sided ladders help shape estimation, but they alone seldom narrow all dependence-free bounds enough to verify candidate bets.
