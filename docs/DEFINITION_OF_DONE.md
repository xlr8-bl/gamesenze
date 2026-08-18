# Definition of done — §10

State of each item in this repository. "Code complete" means the mechanism
exists and is tested here; it does not mean it has been run against live
accounts, which needs credentials this repository does not have.

## Infrastructure

| Item | State |
|---|---|
| Private repo, Actions enabled, minutes tracked | Workflows written; budget documented at ~488 of 2,000 min/mo |
| Cloudflare Workers cron firing; **CPU verified under real load** | Worker written and typechecked, designed to stay off the CPU path. **Verification is a deploy-time step** — see the drill in `docs/OPERATIONS.md` |
| Supabase schema deployed with QA tables | 7 migrations, applied and exercised against Postgres 16 in CI |
| Netlify auto-deploy from main | `deploy-frontend.yml`; static export builds clean |
| Weekly `pg_dump` **with a tested restore** | `weekly-backup.yml` dumps, restores into a throwaway Postgres, and compares row counts before upload |

## Budget

| Item | State |
|---|---|
| `api_budget` increments on every vendor call | `MeteredClient` reserves before the request; no client bypasses it |
| Degradation verified at 80 / 90 / 100% | Tested in `test_budget_and_degradation.py` and `test_sql_behaviour.py` |
| 7 consecutive days under 85% on every provider | **Runtime observation.** Needs live operation |

## Data quality

| Item | State |
|---|---|
| Range validation on all ingested fields | Layer 1, §5.1 table implemented verbatim; boundaries tested inclusive |
| Cross-source verification on scores, lineups, xG | Layer 2 with the §5.2 tolerances; settlement gated on REQ-QA-1 |
| Team alias table populated for covered leagues | 54 teams across 3 leagues seeded; unknown names block and enter the backlog |
| Sample gates enforced with UI data-limit blocks | Layer 4; excluded factors render as text on the pick |
| Publication gate blocking on any failed check | Layer 5, all nine checks, blocks recorded with reasons |
| Daily audit running, alerting on unresolved flags | Layer 6; exits non-zero on unresolved blocking flags |
| Provenance recorded for every ingested record | `data_provenance` written before parsing, pruned at 60 days |

## Analysis integrity

| Item | State |
|---|---|
| `get_features_as_of()` used everywhere; zero full-season lookups | Enforced by `lookahead_lint.py` in `weekly-backtest.yml`, not by convention |
| Backtest harness verified point-in-time correct | Future-dated rows raise rather than being filtered; tested |
| Closing line captured for every pick | `capture_closing_lines()` plus `v_missing_closing_lines` as the standing check |
| Calibration tracked alongside win rate | Brier, ECE and Wilson intervals persisted per run |

## Operational

| Item | State |
|---|---|
| Full matchday dry run with injected failures | **Not done.** Needs live vendor accounts; procedure in `docs/OPERATIONS.md` |
| Degradation ladder exercised end to end | Exercised in tests; the live drill is in the runbook |
| 14 consecutive days clean before first paid subscriber | **Runtime observation** |

## Summary

Everything that can be built and proven without live credentials is built and
proven. Four items are genuinely outstanding and all four require a running
deployment: the Worker CPU measurement, the 7-day and 14-day observation
windows, and the injected-failure matchday.
