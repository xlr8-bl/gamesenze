"""Populate `fixtures` — the piece nothing else was doing.

Every other job in this pipeline reads a fixture that is already there.
Nothing wrote the first one. This runs nightly, before nightly_analysis, so
there is something for that job to find (§3.5).

Two vendors, split by what each one's free tier actually supports, discovered
live mid-deployment: API-Football's free tier only reaches back to 2022-2024
("Free plans do not have access to this season") — useless for live picks,
but a fine source for the historical data the backtest layer (§5.7) wants.
football-data.org's free tier covers the current season for 9 of our 17
competitions, so that is where live fixtures come from. A competition
resolved only against API-Football has no live source yet and is skipped
here rather than spending its daily budget on a call known to fail.

Only resolved competitions are synced either way. An unresolved
competition_id is not a fixture list we can trust any more than an unresolved
team name is — see resolve_competitions.py and resolve_football_data.py for
why nothing here guesses an ID.
"""

from __future__ import annotations

import asyncio
import logging

from ..normalize import TeamResolver
from ..providers.football_data import FootballData, parse_match
from ._runtime import JobContext, run_job

log = logging.getLogger("gamesenze.fixture_sync")


async def football_data_competitions(ctx: JobContext) -> list[dict]:
    return await ctx.db.fetch(
        """
        select c.id as competition_id, c.name, s.source_id
          from competitions c
          join competition_source_ids s
            on s.competition_id = c.id and s.source = 'football_data'
        """
    )


async def api_football_only_competitions(ctx: JobContext) -> list[dict]:
    """Resolved against API-Football but not football-data.org — no live
    source. Reported so the gap is visible, never called for a live window.
    """
    return await ctx.db.fetch(
        """
        select c.name
          from competitions c
          join competition_source_ids af
            on af.competition_id = c.id and af.source = 'api_football'
         where not exists (
             select 1 from competition_source_ids fd
              where fd.competition_id = c.id and fd.source = 'football_data'
         )
        """
    )


async def upsert_fixtures(
    ctx: JobContext, resolver: TeamResolver, source: str,
    rows: list[tuple[str, dict]],
) -> tuple[int, int]:
    """Insert or refresh a whole batch of fixtures. Returns (synced, blocked).

    Batched rather than one-at-a-time: a nightly sync is ~9 competitions x
    ~40 matches, and a per-match round trip (a lookup, then an insert or an
    update, then a source-id insert) is ~1,000 sequential round trips to
    Supabase — minutes of pure network latency, seen live. Four statements
    total instead: resolve (cached, in-process), look every source_id up at
    once, bulk-update what exists, bulk-insert what does not.

    A fixture whose teams do not both resolve is left out entirely rather
    than written with a guessed team — REQ-DATA-NORM-1, unchanged by the
    batching.
    """
    resolved: dict[str, dict] = {}
    blocked = 0
    for competition_id, parsed in rows:
        home_id = await resolver.try_resolve(source, parsed["home_source_name"])
        away_id = await resolver.try_resolve(source, parsed["away_source_name"])
        if home_id is None or away_id is None:
            blocked += 1
            continue
        # Keyed by source_id so the same match arriving twice in one batch
        # collapses instead of racing itself through the insert below.
        resolved[str(parsed["source_id"])] = {
            "competition_id": competition_id,
            "home_id": home_id,
            "away_id": away_id,
            **parsed,
        }

    if not resolved:
        return 0, blocked

    source_ids = list(resolved)
    existing_rows = await ctx.db.fetch(
        "select source_id, fixture_id from fixture_source_ids "
        "where source = $1 and source_id = any($2::text[])",
        source,
        source_ids,
    )
    existing = {r["source_id"]: str(r["fixture_id"]) for r in existing_rows}

    to_update = [sid for sid in source_ids if sid in existing]
    if to_update:
        await ctx.db.execute(
            """
            update fixtures
               set status = u.status, home_goals = u.home_goals,
                   away_goals = u.away_goals, updated_at = now()
              from unnest($1::uuid[], $2::text[], $3::int[], $4::int[])
                   as u(id, status, home_goals, away_goals)
             where fixtures.id = u.id
            """,
            [existing[sid] for sid in to_update],
            [resolved[sid]["status"] for sid in to_update],
            [resolved[sid]["home_goals"] for sid in to_update],
            [resolved[sid]["away_goals"] for sid in to_update],
        )

    to_create = [sid for sid in source_ids if sid not in existing]
    if to_create:
        created = await ctx.db.fetch(
            """
            insert into fixtures (sport, competition_id, home_team_id,
                                  away_team_id, kickoff_at, status,
                                  home_goals, away_goals, venue)
            select 'football', u.competition_id, u.home_id, u.away_id,
                   u.kickoff_at, u.status, u.home_goals, u.away_goals, u.venue
              from unnest($1::uuid[], $2::uuid[], $3::uuid[], $4::timestamptz[],
                          $5::text[], $6::int[], $7::int[], $8::text[])
                   as u(competition_id, home_id, away_id, kickoff_at, status,
                        home_goals, away_goals, venue)
            returning id, home_team_id, away_team_id, kickoff_at
            """,
            [resolved[s]["competition_id"] for s in to_create],
            [resolved[s]["home_id"] for s in to_create],
            [resolved[s]["away_id"] for s in to_create],
            [resolved[s]["kickoff_at"] for s in to_create],
            [resolved[s]["status"] for s in to_create],
            [resolved[s]["home_goals"] for s in to_create],
            [resolved[s]["away_goals"] for s in to_create],
            [resolved[s]["venue"] for s in to_create],
        )
        # Matched back by (home, away, kickoff) rather than by position, so
        # this does not depend on unnest() preserving array order. That
        # triple is unique within one batch — the same two teams do not
        # kick off twice at the same instant.
        by_triple = {
            (str(r["home_team_id"]), str(r["away_team_id"]), r["kickoff_at"]): str(r["id"])
            for r in created
        }
        pairs = []
        for sid in to_create:
            row = resolved[sid]
            key = (str(row["home_id"]), str(row["away_id"]), row["kickoff_at"])
            fixture_id = by_triple.get(key)
            if fixture_id is not None:
                pairs.append((fixture_id, sid))

        if pairs:
            await ctx.db.execute(
                """
                insert into fixture_source_ids (fixture_id, source, source_id)
                select * from unnest($1::uuid[], $2::text[], $3::text[])
                on conflict (source, source_id) do nothing
                """,
                [p[0] for p in pairs],
                [source] * len(pairs),
                [p[1] for p in pairs],
            )

    return len(resolved), blocked


async def main(ctx: JobContext) -> int:
    resolver = TeamResolver(ctx.db, ctx.clock)
    synced = blocked = 0

    if ctx.settings.football_data_key:
        competitions = await football_data_competitions(ctx)
        if not competitions:
            log.warning(
                "no competitions resolved against football-data.org yet — run "
                "`python -m gamesenze.jobs.resolve_football_data` first"
            )
        client = FootballData(
            ctx.settings.football_data_key, db=ctx.db, meter=ctx.meter,
            clock=ctx.clock,
        )
        # One HTTP call per competition, each a second or more. They are
        # independent, so pay that latency once concurrently rather than
        # nine times in a row. A single competition's failure returns an
        # empty list instead of propagating out of gather() and discarding
        # the other eight competitions' successful fetches.
        async def _fetch(comp):
            try:
                response = await client.matches(comp["source_id"])
            except Exception as exc:  # noqa: BLE001
                log.error("fixture sync failed for %s: %s", comp["name"], exc)
                return comp, []

            errors = (response.body or {}).get("errors")
            if errors:
                log.warning("%s (code=%s): API reported %s",
                            comp["name"], comp["source_id"], errors)
            return comp, (response.body or {}).get("matches", [])

        fetched = await asyncio.gather(*(_fetch(comp) for comp in competitions))

        rows = [
            (comp["competition_id"], parse_match(raw))
            for comp, body_matches in fetched
            for raw in body_matches
        ]
        synced, blocked = await upsert_fixtures(
            ctx, resolver, "football_data", rows
        )
    else:
        log.warning("FOOTBALL_DATA_KEY not set; no live fixture source available")

    unsourced = await api_football_only_competitions(ctx)
    if unsourced:
        names = ", ".join(c["name"] for c in unsourced)
        log.info(
            "no live source for: %s (resolved against api_football only, "
            "whose free tier cannot serve the current season — see "
            "docs/OPERATIONS.md)",
            names,
        )

    log.info("%d fixture(s) synced, %d blocked on unresolved team names", synced, blocked)
    print(f"synced {synced} fixtures, {blocked} blocked on unresolved team names")
    if unsourced:
        print(f"no live source yet for {len(unsourced)} competition(s): {names}")
    if blocked:
        print("check the backlog: python -m gamesenze.jobs.aliases backlog")
    return 0


if __name__ == "__main__":
    run_job(main)
