# Operations runbook

## Daily rhythm

| When | What | Where |
|---|---|---|
| Continuous | Odds snapshots, T-1h lineups | Cloudflare Worker (per-minute cron) |
| 04:00 UTC | Nightly analysis drafts picks | `nightly-analysis.yml` |
| Morning | **A person reads every draft** | `python -m gamesenze.jobs.review_queue` |
| 07:30 UTC | Yesterday's audit | `daily-qa-audit.yml` |
| Hourly :20 | Worker fallback catch-up | `worker-fallback.yml` |

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
