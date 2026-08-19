"""Populate `team_match_stats` from Understat — the piece nothing else did.

weekly_scrape.py archives Understat/FBref data into `data_provenance` (raw-
first storage, REQ-SCRAPE-5) but nothing ever parsed it into the structured
rows the pricing model actually reads: `get_features_as_of()` in
backtest/features.py queries `team_match_stats`, and until this job existed
that table had no writer at all. Found the same way the odds coverage
deadlock was — by tracing the whole chain live, not by inspection: fixtures
synced, odds synced, and nightly_analysis still skipped every candidate on
the §5.4 sample-size gate, because there was no match history to sample.

Understat only, for now. A live check of FBref's real output showed its
`team` column coming back empty (`NaN`) for every row — a bug in soccerdata's
FBref reader, not something to build a fragile guess-the-team-from-context
workaround for. Understat's data is clean and has everything the model
needs: goals, xG, PPDA per team per match. FBref is a tracked follow-up, not
silently dropped — see docs/OPERATIONS.md.

Matches soccerdata's wide-format row (one row per game, `home_`/`away_`
prefixed columns — verified live, not guessed) against fixtures the same way
odds_sync matches vendor games: by team (through the same alias table,
source `understat`) and kickoff time. Unlike odds_sync, a historical result
with no matching fixture gets one created — fixture_sync only ever syncs a
forward-looking window, so last season's matches were never synced when they
were still upcoming.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from ..normalize import TeamResolver
from ..scrape.soccerdata_jobs import SoccerDataScraper
from ._runtime import JobContext, run_job

log = logging.getLogger("gamesenze.stats_sync")

SOURCE = "understat"

# soccerdata's league key -> our competitions.name. Same three leagues
# weekly_scrape.py already fetches (see LEAGUES there) — not all 17, since
# nothing beyond these three has been wired to a stats vendor yet.
LEAGUE_NAMES: dict[str, str] = {
    "ENG-Premier League": "Premier League",
    "ESP-La Liga": "La Liga",
    "ITA-Serie A": "Serie A",
}
SEASONS = ["2526"]

# Same reasoning as odds_sync's KICKOFF_TOLERANCE: matching one vendor's
# clock against another's, not the same source twice.
KICKOFF_TOLERANCE = timedelta(hours=12)


async def competition_ids_by_name(ctx: JobContext) -> dict[str, str]:
    rows = await ctx.db.fetch(
        "select id, name from competitions where name = any($1::text[])",
        list(LEAGUE_NAMES.values()),
    )
    return {r["name"]: r["id"] for r in rows}


async def find_or_create_fixture(
    ctx: JobContext,
    competition_id: str,
    home_id: str,
    away_id: str,
    kickoff_at: datetime,
    home_goals: int | None,
    away_goals: int | None,
    vendor_game_id: str,
) -> str:
    existing = await ctx.db.fetchval(
        """
        select id from fixtures
         where competition_id = $1 and home_team_id = $2 and away_team_id = $3
           and kickoff_at between $4 and $5
         order by abs(extract(epoch from (kickoff_at - $6)))
         limit 1
        """,
        competition_id,
        home_id,
        away_id,
        kickoff_at - KICKOFF_TOLERANCE,
        kickoff_at + KICKOFF_TOLERANCE,
        kickoff_at,
    )
    if existing is not None:
        await ctx.db.execute(
            """
            update fixtures set status = 'finished', home_goals = $2,
                   away_goals = $3, updated_at = now()
             where id = $1
            """,
            existing,
            home_goals,
            away_goals,
        )
        return str(existing)

    fixture_id = await ctx.db.fetchval(
        """
        insert into fixtures (sport, competition_id, home_team_id, away_team_id,
                              kickoff_at, status, home_goals, away_goals)
        values ('football', $1, $2, $3, $4, 'finished', $5, $6)
        returning id
        """,
        competition_id,
        home_id,
        away_id,
        kickoff_at,
        home_goals,
        away_goals,
    )
    await ctx.db.execute(
        """
        insert into fixture_source_ids (fixture_id, source, source_id)
        values ($1, $2, $3)
        on conflict (source, source_id) do nothing
        """,
        fixture_id,
        SOURCE,
        vendor_game_id,
    )
    return str(fixture_id)


def _parse_kickoff(date_str: str) -> datetime:
    from datetime import UTC

    # Understat's `date` has no timezone marker. Treated as UTC: the field is
    # documented and widely used as UTC by consumers of this vendor, and a
    # few hours of drift does not change which matches fall inside the
    # aggregate window get_features_as_of() reads.
    dt = datetime.fromisoformat(date_str)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def parse_understat_rows(rows: list[dict]) -> list[dict]:
    """One vendor row (a game) -> two team_match_stats-shaped dicts.

    Kept separate from the database work below so the mapping itself —
    which field means what — is unit-testable without a server.
    """
    out: list[dict] = []
    for row in rows:
        league = LEAGUE_NAMES.get(row.get("league", ""))
        if league is None:
            continue
        kickoff_at = _parse_kickoff(row["date"])
        game_id = str(row["game_id"])
        common = {
            "league": league,
            "kickoff_at": kickoff_at,
            "game_id": game_id,
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "home_goals": row.get("home_goals"),
            "away_goals": row.get("away_goals"),
        }
        out.append(
            {
                **common,
                "is_home": True,
                "team": row["home_team"],
                "goals_for": row.get("home_goals"),
                "goals_against": row.get("away_goals"),
                "xg": row.get("home_xg"),
                "xga": row.get("away_xg"),
                "ppda": row.get("home_ppda"),
            }
        )
        out.append(
            {
                **common,
                "is_home": False,
                "team": row["away_team"],
                "goals_for": row.get("away_goals"),
                "goals_against": row.get("home_goals"),
                "xg": row.get("away_xg"),
                "xga": row.get("home_xg"),
                "ppda": row.get("away_ppda"),
            }
        )
    return out


async def sync_understat_stats(ctx: JobContext, rows: list[dict]) -> tuple[int, int]:
    """Resolve, match, and write. Returns (matches_written, sides_unresolved)."""
    resolver = TeamResolver(ctx.db, ctx.clock)
    comp_ids = await competition_ids_by_name(ctx)
    parsed = parse_understat_rows(rows)

    # One fixture per game_id, resolved once and reused by both its sides.
    fixture_cache: dict[str, str | None] = {}
    matches_written = 0
    unresolved = 0

    for side in parsed:
        competition_id = comp_ids.get(side["league"])
        if competition_id is None:
            continue

        if side["game_id"] not in fixture_cache:
            home_id = await resolver.try_resolve(SOURCE, side["home_team"])
            away_id = await resolver.try_resolve(SOURCE, side["away_team"])
            if home_id is None or away_id is None:
                fixture_cache[side["game_id"]] = None
            else:
                fixture_cache[side["game_id"]] = await find_or_create_fixture(
                    ctx,
                    competition_id,
                    home_id,
                    away_id,
                    side["kickoff_at"],
                    side["home_goals"],
                    side["away_goals"],
                    side["game_id"],
                )

        fixture_id = fixture_cache[side["game_id"]]
        if fixture_id is None:
            unresolved += 1
            continue

        team_id = await resolver.try_resolve(SOURCE, side["team"])
        if team_id is None:
            unresolved += 1
            continue

        await ctx.db.execute(
            """
            insert into team_match_stats (fixture_id, team_id, kickoff_at, status,
                                          is_home, goals_for, goals_against, xg,
                                          xga, ppda, source)
            values ($1, $2, $3, 'finished', $4, $5, $6, $7, $8, $9, $10)
            on conflict (fixture_id, team_id, source) do update
                set goals_for = excluded.goals_for,
                    goals_against = excluded.goals_against,
                    xg = excluded.xg,
                    xga = excluded.xga,
                    ppda = excluded.ppda
            """,
            fixture_id,
            team_id,
            side["kickoff_at"],
            side["is_home"],
            side["goals_for"],
            side["goals_against"],
            side["xg"],
            side["xga"],
            side["ppda"],
            SOURCE,
        )
        matches_written += 1

    return matches_written, unresolved


async def sync_from_scrape_result(
    ctx: JobContext,
    scraper: SoccerDataScraper,
    result,
    *,
    leagues: list[str],
    seasons: list[str],
) -> tuple[int, int]:
    """Parse a ScrapeResult already fetched elsewhere (e.g. weekly_scrape.py),
    falling back to the archived payload when it came back
    `skipped_unchanged=True` — REQ-SCRAPE-3 skips re-fetching identical data,
    but that is not the same fact as "already parsed into team_match_stats",
    and the caller's destination table may still be empty.
    """
    rows = result.rows
    if result.skipped_unchanged:
        entity_ref = f"{SOURCE}:{','.join(leagues)}:{','.join(seasons)}"
        cached = await scraper.latest_archived(SOURCE, entity_ref)
        if cached is None:
            return 0, 0
        rows = cached
    return await sync_understat_stats(ctx, rows)


async def main(ctx: JobContext) -> int:
    scraper = SoccerDataScraper(
        ctx.db, contact=ctx.settings.scraper_contact, clock=ctx.clock
    )
    leagues = list(LEAGUE_NAMES.keys())
    result = await scraper.understat(leagues, SEASONS)

    written, unresolved = await sync_from_scrape_result(
        ctx, scraper, result, leagues=leagues, seasons=SEASONS
    )
    print(f"team_match_stats: {written} row(s) written, {unresolved} side(s) unresolved")
    return 0


if __name__ == "__main__":
    run_job(main)
