# v8 research result — 2026-10-21

## Objective

Replace an hourly notification with a stand-alone Polymarket US player-prop and
NBA game-event research/paper-trading bot, preserving previous market dynamics,
Lasso, alternate ladder and joint probability model work.

## Data audit

- Real book capture attempts via this sandbox: **blocked by DNS/network**.
- Polymarket US official SDK discovery/BBO: verified by publisher docs; parser
  tested against format-compatible mock response, **not against a live feed**.
- No new real, synchronized, two-sided sportsbook reference prices acquired.
- 2026-10-20 archived prices previously collected: do NOT meet synchronous/
  executable criteria; **zero candidates certified**.

## Synthetic QA (not real market evidence)

- Artificial exhibition market with two reference two-way sportsbook pairs:
  exchange YES ask 45¢, YES bid 42¢, fee-reserve 1¢/share, slip-reserve .5¢.
  Conditional lower probability ~53.35%; conditional lower ROI ~14.73%.
  Flagged as a **conditional paper research signal** only, as deliberately planted.
- Another fictional market with exchange ask 58¢ vs similar reference fair
  probabilities correctly rejected as no conditional edge.
- Unreviewed resolution rules correctly block apparent positive ROI.
- Inactive/mismatched/stale quotes, one-book input, insufficient depth/spread,
  missing reverse prices, missing timestamp, market past start all fail safely.

## Release gate

**No live orders have been or will be placed by this version.** Proof of
repeatable live odds discrepancy and statistically supported future performance
is not established. The venue adapter's correct authenticated fee handling and
fill reconciliation remain to be integrated and independently verified.

## Strategy under test

`conditional_p_lower = min(p_de-vig independent books) - probability_uncertainty
  - disagreement_multiplier * [max(p_de-vig) - min(p_de-vig)]`

`screen_ROI_lower = conditional_p_lower / (best_US_ask + fee_reserve + slip_reserve) - 1`

**Important:** these are *sensitivity intervals conditional on bookmaker inputs*.
They are not mathematically valid bounds on the unknown true chance and cannot
certify value from prices alone.

## Primary next milestone

Provide a synced, compliant historical market and two-way sportsbook data source
or run `discover-us` on a network-enabled runner, verify actual NBA player props
availability, then paper-trade the strategy across chronologically held-out games.
