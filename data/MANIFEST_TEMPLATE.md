# Rule-reviewed Polymarket US market manifest

Each line of `contracts.jsonl` contains a contract object. The schema is visible
in `data/synthetic/contracts.jsonl`. `contract_id` must be uniquely mapped to
an actual US API market slug. Never fabricate a match from a similar player name.

Required human checks before rules_verified=true:
* Same event (including fixture date, player ID/team ID, period, overtime).
* Identical cutoffs ("25+" == over 24.5, not over 25.5).
* Same settlement for DNP/void, game cancellation, postponed games.
* Yes/no mapping correct for both venue and sportsbook.
* No unlisted alternate player-stat category assumed available on Polymarket US.
* Contract market in state OPEN, with tradeable asks and actual offer volume.

Sportsbook pairs JSONL schema:
{
  "contract_id": "MATCHED_ID", "sportsbook": "A", "captured_utc": "UTC_ISO",
  "american_yes": -110, "american_no": -110,
  "rule_id": "REVIEWED_IDENTICAL_RULE_FINGERPRINT",
  "quote_source": "LIVE_PROVIDER_OR_EXPORT_ID", "executable_confirmed": false
}

For game winner, use YES = named team wins; for player points use YES =
statistic exceeds half-integer cutoff; both need exact settlement handling.
