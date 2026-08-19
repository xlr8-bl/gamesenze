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


async def upsert_fixture(
    ctx: JobContext, resolver: TeamResolver, source: str, competition_id: str,
    parsed: dict,
) -> str | None:
    """Insert or refresh one fixture. Returns None if a team could not be
    resolved — the fixture is not written at all rather than written with a
    guessed team, matching REQ-DATA-NORM-1.
    """
    existing = await ctx.db.fetchval(
        "select fixture_id from fixture_source_ids "
        "where source = $1 and source_id = $2",
        source,
        parsed["source_id"],
    )

    home_id = await resolver.try_resolve(source, parsed["home_source_name"])
    away_id = await resolver.try_resolve(source, parsed["away_source_name"])
    if home_id is None or away_id is None:
        return None

    if existing is None:
        fixture_id = await ctx.db.fetchval(
            """
            insert into fixtures (sport, competition_id, home_team_id,
                                  away_team_id, kickoff_at, status,
                                  home_goals, away_goals, venue)
            values ('football', $1, $2, $3, $4, $5, $6, $7, $8)
            returning id
            """,
            competition_id,
            home_id,
            away_id,
            parsed["kickoff_at"],
            parsed["status"],
            parsed["home_goals"],
            parsed["away_goals"],
            parsed["venue"],
        )
        await ctx.db.execute(
            "insert into fixture_source_ids (fixture_id, source, source_id) "
            "values ($1, $2, $3)",
            fixture_id,
            source,
            parsed["source_id"],
        )
        return fixture_id

    await ctx.db.execute(
        """
        update fixtures
           set status = $2, home_goals = $3, away_goals = $4, updated_at = now()
         where id = $1
        """,
        existing,
        parsed["status"],
        parsed["home_goals"],
        parsed["away_goals"],
    )
    return existing


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
        for comp in competitions:
            try:
                response = await client.matches(comp["source_id"])
            except Exception as exc:  # noqa: BLE001 - one competition's
                # failure must not stop the other eight from syncing.
                log.error("fixture sync failed for %s: %s", comp["name"], exc)
                continue

            errors = (response.body or {}).get("errors")
            if errors:
                log.warning("%s (code=%s): API reported %s",
                            comp["name"], comp["source_id"], errors)

            body_matches = (response.body or {}).get("matches", [])
            for raw in body_matches:
                parsed = parse_match(raw)
                fixture_id = await upsert_fixture(
                    ctx, resolver, "football_data", comp["competition_id"], parsed
                )
                if fixture_id is None:
                    blocked += 1
                else:
                    synced += 1
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
