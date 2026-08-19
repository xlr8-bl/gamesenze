# Operations runbook

## Daily rhythm

| When | What | Where |
|---|---|---|
| Continuous | T-1h lineups | Cloudflare Worker (per-minute cron) |
| 04:00 UTC | Sync fixtures, sync odds, then draft picks | `nightly-analysis.yml` |
| Morning | **A person reads every draft** | `python -m gamesenze.jobs.review_queue` |
| 07:30 UTC | Yesterday's audit | `daily-qa-audit.yml` |
| Hourly :20 | Worker fallback catch-up (lineups only) | `worker-fallback.yml` |

Odds snapshots are *not* on the Worker's per-minute cron, despite the original
plan. SportsGameOdds — the vendor that plan assumed — turned out, discovered
live, to cover only MLS and the Champions League on its free tier; none of
this product's target leagues. The Odds API replaced it, and its billing
model (one credit per league's whole board, not per fixture) made a once-daily
pull ahead of `nightly_analysis` the practical cadence rather than a per-minute
one — see `gamesenze/providers/odds_api.py` and `gamesenze/jobs/odds_sync.py`.
One consequence worth knowing: every odds snapshot currently carries the same
`window_label` ("daily"), so there is no true closing-line capture yet
(REQ-QA-5 wants one as close to kickoff as practical). Tracked as a follow-up,
not silently skipped — increasing `odds_sync` frequency is a budget config
change (`PROVIDER_BUDGETS["odds_api"]` in `config.py`), not a rewrite.

Actions timing drifts by 10-30 minutes. That is expected and harmless here —
nothing on Actions is time-critical.

## When something fires

### An unresolved QA flag blocks a fixture

The daily audit exits non-zero and the workflow goes red. This is the intended
behaviour: unresolved blocking flags mean the next publication cycle must not
run until a person has looked.

```sql
select id, entity_id, issue, detail, raised_at
  from qa_flags
 where resolved_at is null and severity = 'block'
 order by raised_at;
```

Resolve with a note explaining what was decided, not just that it was closed:

```sql
update qa_flags
   set resolved_at = now(), resolved_by = 'ash',
       resolution_note = 'FBref had the wrong fixture; API-Football correct'
 where id = 42;
```

### A score mismatch halts settlement

Two sources disagree on a final score. **Do not pick the one that agrees with
the pick.** Check a third source, correct the wrong row, then resolve the flag.
Settlement stays blocked until the score check passes — that is REQ-QA-1 and it
has no override.

### An unresolved team name

A source sent a spelling we do not know. The fixture is blocked from
publication and the name is in the backlog:

```bash
python -m gamesenze.jobs.aliases backlog
```

The suggestions are ranked by string similarity and are **only** suggestions. A
0.94 match that is wrong corrupts data exactly as thoroughly as a 0.4 one, and
nothing downstream can tell the difference. Confirm against the fixture's
opponent and kickoff before adding the alias.

### Budget at 80% / 90% / 100%

No action needed — the ladder handles it and the board tells readers what is
happening. Investigate *why* it happened:

```sql
select job, count(*), max(called_at)
  from api_calls
 where called_at > now() - interval '24 hours'
 group by job order by 2 desc;
```

The usual cause is retries against a failing endpoint. The 20-30 call reserve
exists for exactly this, which is why it is not spent in the plan.

### A scrape failed

Cached data is used and its age shows in the UI. Not urgent. If the same source
fails twice running, the site changed its HTML — re-parse from the archive
rather than re-fetching:

```sql
select fetched_at, request_url, parser_version
  from data_provenance
 where source = 'fbref' and raw_response is not null
 order by fetched_at desc limit 5;
```

This is what REQ-SCRAPE-5 buys. Without the raw archive that history is gone.

### Supabase near 500MB

`daily-qa-audit.yml` runs the prune and alerts at 400MB. If it is still
climbing, shorten `PROVENANCE_RETENTION_DAYS` in `gamesenze/config.py` — raw
responses are almost always the cause.

## Setting up competition coverage (one-time)

Fixtures are only synced for competitions that have been resolved against
API-Football's own `/leagues` endpoint — nothing is guessed. Two independent
lookups for the same competition produced conflicting numeric IDs during
development, which is exactly the failure mode this step exists to prevent.

**From a terminal:**

```bash
python -m gamesenze.jobs.resolve_competitions
```

Interactive: it searches each competition in `gamesenze/competitions.py`,
shows every candidate the vendor actually returned, and you pick the right one
by number (or skip). Safe to stop and re-run — it only prompts for whatever
is still unresolved. Re-run it each pre-season, since seasons roll over and a
stale `resolved_season` would sync last year's fixtures under this year's date.

**From a phone, no terminal at all:** two GitHub Actions workflows do the same
job in two steps, both triggered from the Actions tab's "Run workflow" button.
Pick the feature branch in the branch dropdown if this has not been merged to
`main` yet — `workflow_dispatch` runs whatever branch you select, but the file
has to exist there.

1. **"Resolve competitions — 1. show candidates"** — reads only, writes
   nothing. Open the run once it finishes and read the log: every unresolved
   competition's real API-Football candidates, e.g.

   ```
   key: premier_league
     [1] id=39    'Premier League'      England   League  season 2025
     [2] id=570   'Premier League Cup'  England   Cup     season 2025
   ```

2. **"Resolve competitions — 2. confirm picks"** — has one text box, `picks`.
   Fill in the id you want per competition as `key=id`, comma-separated:
   `premier_league=39,la_liga=140,serie_a=135,...`. It re-checks each id
   against what the vendor actually returned before writing anything — a
   typo'd number is rejected, not silently accepted.

Then, from either path, and on every future run:

```bash
python -m gamesenze.jobs.fixture_sync
```

Or from a phone: the existing **"Nightly analysis"** workflow already runs
this as its first step — "Run workflow" on that one covers fixture sync,
drafting, and the review queue report in a single tap.

Populates `fixtures` for every resolved competition. Unresolved team names
block that one fixture (not the whole run) and land in the alias backlog —
see `python -m gamesenze.jobs.aliases backlog` above.

**Second vendor, found live:** API-Football's free tier only reaches
2022-2024 ("Free plans do not have access to this season") — useless for
live fixtures, though still fine for the historical data the backtest layer
wants. football-data.org's free tier covers the current season for 9 of the
17: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Champions League,
Eredivisie, Primeira Liga, Championship. The other 8 (UEL, UECL, six domestic
cups) have no free live source yet.

Resolve football-data.org the same way, from a terminal:

```bash
python -m gamesenze.jobs.resolve_football_data
```

Shows the vendor's whole competition list once (it is small — a curated
catalogue, not API-Football's thousands of amateur leagues) and asks for the
short code (`PL`, `PD`, `SA`, ...) for each of the 9, typed and verified
against that same list — a typo is rejected, not guessed at.

Or from a phone: **"Resolve football-data.org — 1. show codes"** then
**"... — 2. confirm codes"**, same two-step pattern as the API-Football
workflows, with `key=code` pairs instead of `key=id`.

**Known gap:** standings-derived stakes tags (`top_four_clash`,
`relegation_battle`, `neighbours_in_table`, `dead_rubber_for_one_side`) are not
computed yet — there is no `standings` table, so `nightly_analysis` currently
runs `stakes_tags()` against a minimal input that can only produce
run-in/rest/derby-type tags, never position-based ones. This does not block
publication (the gate only requires the computation to have run, and it does),
it just means position-based stakes are silently absent rather than present.
Tracked, not forgotten.

## Drills

Run these before the first paid subscriber, and after any change to the ladder.

**Degradation ladder, end to end.** Move the counter and confirm each rung:

```sql
update api_budget set calls_used = 2000  -- 80%
 where provider = 'sportsgameodds' and period = to_char(now(), 'YYYY-MM');
select ladder_rung from v_budget_status;
select count(*) from due_odds_snapshots(now(), 10, 20);
```

Expect: 2000 → `reduced`, 2250 → `closing_only` (intermediate captures stop,
the lock capture does not), 2500 → `exhausted` (nothing due, nothing
publishes). `tests/test_sql_behaviour.py` asserts all of this.

**Worker CPU under real load.** §2.3 says verify rather than assume. Hit the
manual endpoint while several fixtures are due and check the reported CPU time
in `wrangler tail`:

```bash
curl https://gamesenze-snapshot.<subdomain>.workers.dev/run
npx wrangler tail --format pretty
```

If CPU approaches 10ms, the fix is already designed for: the Worker fires a
`workflow_dispatch` at `worker-fallback.yml` instead of doing the work itself.

**Restore.** `weekly-backup.yml` does this every Sunday, but run it by hand
once so you have watched it work:

```bash
pg_dump --no-owner --no-acl -Fc "$DATABASE_URL" -f backup.dump
createdb restore_test && pg_restore --no-owner --no-acl -d restore_test backup.dump
python -m gamesenze.jobs.verify_restore \
  --source "$DATABASE_URL" --restored postgresql://localhost/restore_test
```

**Injected failure matchday.** Before launch, run a full matchday with faults
deliberately introduced: a corrupted odds payload, a renamed team, a killed
Worker, a score mismatch. The right outcome is fewer picks published and every
fault visible in the next morning's audit — not a silent recovery.

## Things that should never happen

If any of these are true, stop publishing until it is understood.

- A pick published without `reviewed_by` set.
- A settled pick whose outcome came from one source.
- A row in `v_missing_closing_lines` for a fixture that finished days ago.
- A backtest reporting `as_of_correct = false`.
- A fixture with odds but no resolved `home_team_id` / `away_team_id`.
