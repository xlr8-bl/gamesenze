"""Populate `fixtures` from API-Football — the piece nothing else was doing.

Every other job in this pipeline reads a fixture that is already there.
Nothing wrote the first one. This runs nightly, before nightly_analysis, so
there is something for that job to find (§3.5).

Only resolved competitions are synced. An unresolved competition_id is not a
fixture list we can trust any more than an unresolved team name is — see
gamesenze.jobs.resolve_competitions for why nothing here guesses an ID.
"""

from __future__ import annotations

import logging

from ..normalize import TeamResolver
from ..providers.api_football import ApiFootball, parse_fixture
from ._runtime import JobContext, run_job

log = logging.getLogger("gamesenze.fixture_sync")


async def resolved_competitions(ctx: JobContext) -> list[dict]:
    return await ctx.db.fetch(
        """
        select c.id as competition_id, c.name, c.needs_standings,
               s.source_id, s.resolved_season
          from competitions c
          join competition_source_ids s
            on s.competition_id = c.id and s.source = 'api_football'
         where s.resolved_season is not null
        """
    )


async def upsert_fixture(
    ctx: JobContext, resolver: TeamResolver, competition_id: str, parsed: dict
) -> str | None:
    """Insert or refresh one fixture. Returns None if a team could not be
    resolved — the fixture is not written at all rather than written with a
    guessed team, matching REQ-DATA-NORM-1.
    """
    existing = await ctx.db.fetchval(
        "select fixture_id from fixture_source_ids "
        "where source = 'api_football' and source_id = $1",
        parsed["source_id"],
    )

    home_id = await resolver.try_resolve("api_football", parsed["home_source_name"])
    away_id = await resolver.try_resolve("api_football", parsed["away_source_name"])
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
            "values ($1, 'api_football', $2)",
            fixture_id,
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
    if not ctx.settings.api_football_key:
        log.warning("API_FOOTBALL_KEY not set; nothing to sync")
        return 0

    competitions = await resolved_competitions(ctx)
    if not competitions:
        log.warning(
            "no competitions resolved yet — run "
            "`python -m gamesenze.jobs.resolve_competitions` first"
        )
        return 0

    client = ApiFootball(
        ctx.settings.api_football_key, db=ctx.db, meter=ctx.meter, clock=ctx.clock
    )
    resolver = TeamResolver(ctx.db, ctx.clock)

    synced = 0
    blocked = 0
    for comp in competitions:
        try:
            response = await client.fixtures(
                int(comp["source_id"]), comp["resolved_season"]
            )
        except Exception as exc:  # noqa: BLE001 - one competition's failure
            # must not stop the other seven from syncing.
            log.error("fixture sync failed for %s: %s", comp["name"], exc)
            continue

        for raw in (response.body or {}).get("response", []):
            parsed = parse_fixture(raw)
            fixture_id = await upsert_fixture(
                ctx, resolver, comp["competition_id"], parsed
            )
            if fixture_id is None:
                blocked += 1
            else:
                synced += 1

    log.info("%d fixture(s) synced, %d blocked on unresolved team names", synced, blocked)
    print(f"synced {synced} fixtures across {len(competitions)} competition(s), "
          f"{blocked} blocked on unresolved team names")
    if blocked:
        print("check the backlog: python -m gamesenze.jobs.aliases backlog")
    return 0


if __name__ == "__main__":
    run_job(main)
