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


async def find_or_create_fixtures(
    ctx: JobContext, games: list[dict]
) -> dict[str, str]:
    """Batch version of "find or create one fixture per game".

    A full season across 3 leagues is ~1,100 games — doing this one game at a
    time (a SELECT plus an UPDATE-or-INSERT each) was the exact same
    one-row-per-round-trip mistake already fixed twice today in seed.py and
    odds_sync.py, just not caught before this job shipped: ~3,000+ sequential
    round trips, seen live as the command appearing to hang for 15+ minutes.
    Three round trips total instead: one to match every game against
    existing fixtures at once (a LATERAL join against the whole batch), one
    to bulk-update the matches found, one to bulk-insert the rest.

    Returns {game_id: fixture_id} for every game that had both teams
    resolved (the caller filters unresolved ones out before calling this).
    """
    if not games:
        return {}

    matches = await ctx.db.fetch(
        """
        select input.game_id, f.id as fixture_id
          from unnest($1::text[], $2::uuid[], $3::uuid[], $4::uuid[],
                      $5::timestamptz[]) as input(game_id, competition_id,
                                                   home_id, away_id, kickoff_at)
          left join lateral (
              select id from fixtures
               where competition_id = input.competition_id
                 and home_team_id = input.home_id
                 and away_team_id = input.away_id
                 and kickoff_at between input.kickoff_at - $6::interval
                                     and input.kickoff_at + $6::interval
               order by abs(extract(epoch from (kickoff_at - input.kickoff_at)))
               limit 1
          ) f on true
        """,
        [g["game_id"] for g in games],
        [g["competition_id"] for g in games],
        [g["home_id"] for g in games],
        [g["away_id"] for g in games],
        [g["kickoff_at"] for g in games],
        KICKOFF_TOLERANCE,
    )
    fixture_by_game = {
        m["game_id"]: str(m["fixture_id"]) for m in matches if m["fixture_id"]
    }

    to_update = [g for g in games if g["game_id"] in fixture_by_game]
    if to_update:
        await ctx.db.execute(
            """
            update fixtures set status = 'finished', home_goals = u.home_goals,
                   away_goals = u.away_goals, updated_at = now()
              from unnest($1::uuid[], $2::int[], $3::int[])
                   as u(id, home_goals, away_goals)
             where fixtures.id = u.id
            """,
            [fixture_by_game[g["game_id"]] for g in to_update],
            [g["home_goals"] for g in to_update],
            [g["away_goals"] for g in to_update],
        )

    to_create = [g for g in games if g["game_id"] not in fixture_by_game]
    if to_create:
        created = await ctx.db.fetch(
            """
            insert into fixtures (sport, competition_id, home_team_id,
                                  away_team_id, kickoff_at, status, home_goals,
                                  away_goals)
            select 'football', u.competition_id, u.home_team_id, u.away_team_id,
                   u.kickoff_at, 'finished', u.home_goals, u.away_goals
              from unnest(
                  $1::uuid[], $2::uuid[], $3::uuid[], $4::timestamptz[],
                  $5::int[], $6::int[]
              ) as u(competition_id, home_team_id, away_team_id, kickoff_at,
                     home_goals, away_goals)
            returning id, home_team_id, away_team_id, kickoff_at
            """,
            [g["competition_id"] for g in to_create],
            [g["home_id"] for g in to_create],
            [g["away_id"] for g in to_create],
            [g["kickoff_at"] for g in to_create],
            [g["home_goals"] for g in to_create],
            [g["away_goals"] for g in to_create],
        )
        # Matched back by (home, away, kickoff_at) rather than by position:
        # correct regardless of whether Postgres preserves unnest() order,
        # and that triple is unique within one batch (the same two teams do
        # not play twice at the same kickoff time in one season).
        by_triple = {
            (str(r["home_team_id"]), str(r["away_team_id"]), r["kickoff_at"]): str(
                r["id"]
            )
            for r in created
        }
        for g in to_create:
            key = (str(g["home_id"]), str(g["away_id"]), g["kickoff_at"])
            fixture_id = by_triple.get(key)
            if fixture_id is not None:
                fixture_by_game[g["game_id"]] = fixture_id

        created_game_ids = [g["game_id"] for g in to_create if g["game_id"] in fixture_by_game]
        if created_game_ids:
            await ctx.db.execute(
                """
                insert into fixture_source_ids (fixture_id, source, source_id)
                select * from unnest($1::uuid[], $2::text[], $3::text[])
                on conflict (source, source_id) do nothing
                """,
                [fixture_by_game[game_id] for game_id in created_game_ids],
                [SOURCE] * len(created_game_ids),
                created_game_ids,
            )

    return fixture_by_game


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
    """Resolve, match, and write — batched throughout. Returns
    (matches_written, sides_unresolved).
    """
    resolver = TeamResolver(ctx.db, ctx.clock)
    comp_ids = await competition_ids_by_name(ctx)
    parsed = parse_understat_rows(rows)

    for side in parsed:
        side["competition_id"] = comp_ids.get(side["league"])
        # try_resolve() caches in-process, so a team appearing in dozens of
        # matches this season still costs one round trip, not one per row.
        side["team_id"] = await resolver.try_resolve(SOURCE, side["team"])

    by_game: dict[str, list[dict]] = {}
    for side in parsed:
        by_game.setdefault(side["game_id"], []).append(side)

    games: dict[str, dict] = {}
    for game_id, sides in by_game.items():
        home = next((s for s in sides if s["is_home"]), None)
        away = next((s for s in sides if not s["is_home"]), None)
        if home is None or away is None:
            continue
        if home["competition_id"] is None:
            continue
        if home["team_id"] is None or away["team_id"] is None:
            continue
        games[game_id] = {
            "game_id": game_id,
            "competition_id": home["competition_id"],
            "home_id": home["team_id"],
            "away_id": away["team_id"],
            "kickoff_at": home["kickoff_at"],
            "home_goals": home["home_goals"],
            "away_goals": home["away_goals"],
        }

    fixture_by_game = await find_or_create_fixtures(ctx, list(games.values()))

    # Keyed by (fixture_id, team_id) so a within-batch collision overwrites
    # rather than appends: Postgres flatly rejects an ON CONFLICT DO UPDATE
    # that would affect the same row twice in one statement
    # (CardinalityViolationError), and two vendor rows resolving to the same
    # fixture+team is the same fact arriving twice, not two facts.
    resolved_sides: dict[tuple[str, str], dict] = {}
    unresolved = 0

    for side in parsed:
        if side["competition_id"] is None:
            continue
        fixture_id = fixture_by_game.get(side["game_id"])
        if fixture_id is None or side["team_id"] is None:
            unresolved += 1
            continue
        resolved_sides[(fixture_id, side["team_id"])] = {**side, "fixture_id": fixture_id}

    tms: dict[str, list] = {
        "fixture_id": [], "team_id": [], "kickoff_at": [], "is_home": [],
        "goals_for": [], "goals_against": [], "xg": [], "xga": [], "ppda": [],
    }
    for side in resolved_sides.values():
        tms["fixture_id"].append(side["fixture_id"])
        tms["team_id"].append(side["team_id"])
        tms["kickoff_at"].append(side["kickoff_at"])
        tms["is_home"].append(side["is_home"])
        tms["goals_for"].append(side["goals_for"])
        tms["goals_against"].append(side["goals_against"])
        tms["xg"].append(side["xg"])
        tms["xga"].append(side["xga"])
        tms["ppda"].append(side["ppda"])

    if tms["fixture_id"]:
        await ctx.db.execute(
            """
            insert into team_match_stats (fixture_id, team_id, kickoff_at, status,
                                          is_home, goals_for, goals_against, xg,
                                          xga, ppda, source)
            select f.fixture_id, f.team_id, f.kickoff_at, 'finished', f.is_home,
                   f.goals_for, f.goals_against, f.xg, f.xga, f.ppda, $10
              from unnest(
                  $1::uuid[], $2::uuid[], $3::timestamptz[], $4::bool[],
                  $5::int[], $6::int[], $7::numeric[], $8::numeric[], $9::numeric[]
              ) as f(fixture_id, team_id, kickoff_at, is_home, goals_for,
                     goals_against, xg, xga, ppda)
            on conflict (fixture_id, team_id, source) do update
                set goals_for = excluded.goals_for,
                    goals_against = excluded.goals_against,
                    xg = excluded.xg,
                    xga = excluded.xga,
                    ppda = excluded.ppda
            """,
            tms["fixture_id"],
            tms["team_id"],
            tms["kickoff_at"],
            tms["is_home"],
            tms["goals_for"],
            tms["goals_against"],
            tms["xg"],
            tms["xga"],
            tms["ppda"],
            SOURCE,
        )

    return len(tms["fixture_id"]), unresolved


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
