# Pitch Side

Curated football and NBA analysis, running on $0.00/month of infrastructure.

The organising idea is in one sentence from the PRD: **an unpublished pick
costs nothing; a published pick built on bad data costs the track record, and
the track record is the entire business.** Every gate in this repository fails
closed, and a day with no picks is a normal day.

---

## Layout

| Path | What it is |
|---|---|
| `db/migrations/` | Schema, ingest triggers, and the cadence/ladder functions the Worker calls |
| `db/seed/` | Canonical teams and their known spellings for three leagues |
| `pitchside/qa/` | Data quality layers 1-6 |
| `pitchside/backtest/` | Layer 7: point-in-time features, closing-line evaluation, calibration |
| `pitchside/analysis/` | The model and stakes tags |
| `pitchside/providers/` | Vendor clients, all budget-metered |
| `pitchside/scrape/` | Self-collected data, throttled and archived raw |
| `pitchside/jobs/` | GitHub Actions entry points |
| `workers/snapshot/` | The Cloudflare Worker: everything time-critical |
| `web/` | Static Next.js board and combo builder |
| `tests/` | 176 tests, including SQL/Python parity |

## Where work runs, and why

Scheduling is split by whether timing matters.

**GitHub Actions scheduled workflows do not run on time.** Delays of 10-30
minutes are normal, GitHub does not guarantee timing, and it does not notify
you when a scheduled run fails. So nothing time-critical lives there.

| Workload | Runner |
|---|---|
| Odds snapshots, T-1h lineup watch, closing line | Cloudflare Workers cron |
| Nightly analysis, weekly scrapes, audits, backtests | GitHub Actions (private repo) |

The Worker is deliberately thin. The free tier allows **10ms CPU per
invocation**, so it never parses a vendor payload: it relays the response body
as text into `odds_ingest_queue`, and a Postgres trigger does the flattening
where CPU is free. All the cadence arithmetic lives in `snapshot_plan()` and
`due_odds_snapshots()` for the same reason.

That duplication — cadence in SQL *and* Python — is intentional, because the
Worker cannot run Python and the fallback job cannot run inside Postgres.
`tests/test_sql_parity.py` pins the two implementations to identical output so
they cannot drift.

## Budgets

Targets sit at ~80% of each ceiling. The remaining margin absorbs a re-run
after a failed job or a source that needs a second call; a pipeline tuned to
98% fails the first time anything goes wrong.

| Provider | Ceiling | Planned |
|---|---|---|
| API-Football | 100/day | 70/day |
| SportsGameOdds | 2,500 objects/mo | 2,000/mo |
| GitHub Actions | 2,000 min/mo | ~488 min/mo |
| Cloudflare Workers | 100k req/day | ~1,440/day |
| Supabase | 500MB | ~380MB |

Every vendor call reserves budget *before* the request (`pitchside/budget.py`).
Counting afterwards means a crash between request and write leaves us believing
we have room we do not.

The degradation ladder is a pure function of those counters, so the Worker, the
jobs and the frontend all reach the same conclusion:

| Usage | Effect |
|---|---|
| 80% | Cadence halved outside T-3h (16 → 12 snapshots) |
| 90% | Closing snapshots only (→ 1) |
| 100% | Last-known prices with visible timestamps; **no new picks** |

The at-lock capture survives every rung. Losing it would not save meaningful
budget and would destroy the only honest measure of whether we found an edge.

## Getting started

```bash
pip install -e ".[dev,scrape]"
cp .env.example .env            # fill in DATABASE_URL and keys

python -m pitchside.jobs.migrate
python -m pitchside.jobs.seed   # teams and aliases BEFORE any ingestion
```

Run the tests. The SQL-level ones need a Postgres; without `TEST_DATABASE_URL`
they skip rather than fail.

```bash
createdb pitchside
psql -d pitchside -c "create schema auth;
  create function auth.uid() returns uuid language sql stable as \$\$
    select null::uuid \$\$;"
for f in db/migrations/0*.sql; do psql -d pitchside -f "$f"; done

TEST_DATABASE_URL=postgresql://localhost/pitchside pytest -q
ruff check pitchside tests
```

Deploying the Worker and the site:

```bash
cd workers/snapshot && npx wrangler secret put SPORTSGAMEODDS_KEY  # etc.
npx wrangler deploy

cd web && npm ci && npm run build     # static export to web/out
```

## Operational notes

**Team names come first.** "Man Utd" / "Manchester Utd" / "Manchester United" /
"Man United" are one team across four sources, and unresolved mismatches are
the largest source of silent corruption in a multi-source pipeline — they do
not error, they join the wrong rows. Every ingested record resolves through
`team_aliases` or is refused. Nothing is ever guessed, however close the match
looks. Work the backlog with:

```bash
python -m pitchside.jobs.aliases backlog
python -m pitchside.jobs.aliases add fbref "Nott'ham Forest" <team-id>
```

**Every pick is read by a person.** `human_reviewed` is a gate check, not a
convention. The nightly job drafts; `python -m pitchside.jobs.review_queue`
shows what is waiting. At 4-6 picks a day this is 20-30 minutes, and it is the
binding constraint on volume — not compute.

**Backtests are guilty until proven innocent.** `get_features_as_of()` is the
only way to read match history, `pitchside/jobs/lookahead_lint.py` fails the
build on a full-season lookup or a wall-clock call in feature code, and results
below 100 picks report themselves as not evidence. Selection uses the price we
could have seen; evaluation uses the close.

**Backups are tested, not assumed.** Supabase free has no automated backups.
The weekly workflow dumps, restores into a throwaway Postgres, and compares row
counts table by table before uploading. An untested backup is a guess.

## What this does not do

- No pre-filled bet slips, affiliate links, or commission tracking anywhere.
  The combo builder shows maths; the subscriber places the bet themselves.
- No live in-play data, premium expected lineups, or 140+ book coverage. Those
  are Tier 4 and cost money.
- No automatic publication. Ever.

## Documentation

- `docs/OPERATIONS.md` — runbook, degradation drills, what to do when a gate fires
- `docs/DEFINITION_OF_DONE.md` — the §10 checklist and its current state
- `db/migrations/README.md` — how migrations are applied
