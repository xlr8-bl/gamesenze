"""jobs/stats_sync.py — the parser that closes the last gap in the pipeline.

Before this, weekly_scrape.py archived Understat data but nothing ever
parsed it into team_match_stats, so nightly_analysis could never clear the
§5.4 sample-size gate no matter how much fixture/odds data accumulated. The
row shape below is copied verbatim from a real live call (see
gamesenze/jobs/stats_sync.py's module docstring) — not guessed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from gamesenze.jobs.stats_sync import (
    LEAGUE_NAMES,
    find_or_create_fixtures,
    parse_understat_rows,
    sync_from_scrape_result,
    sync_understat_stats,
)
from tests.conftest import requires_pg

pytestmark = requires_pg

REAL_ROW = {
    "league": "ENG-Premier League",
    "season": "2526",
    "game": "2025-08-15 Liverpool-Bournemouth",
    "league_id": "1",
    "season_id": 2025,
    "game_id": 28778,
    "date": "2025-08-15 19:00:00",
    "home_team_id": 87,
    "away_team_id": 73,
    "home_team": "Liverpool",
    "away_team": "Bournemouth",
    "away_team_code": "BOU",
    "home_team_code": "LIV",
    "home_points": 3,
    "home_expected_points": 1.877,
    "home_goals": 4,
    "home_xg": 2.33007,
    "home_np_xg": 2.33007,
    "home_np_xg_difference": 0.75704,
    "home_ppda": 8.764706,
    "home_deep_completions": 9,
    "away_points": 0,
    "away_expected_points": 0.8954,
    "away_goals": 2,
    "away_xg": 1.57303,
    "away_np_xg": 1.57303,
    "away_np_xg_difference": -0.75704,
    "away_ppda": 11.583333,
    "away_deep_completions": 8,
}


def test_league_names_cover_the_three_leagues_weekly_scrape_fetches():
    assert set(LEAGUE_NAMES.values()) == {"Premier League", "La Liga", "Serie A"}


def test_one_vendor_row_becomes_two_team_perspectives():
    sides = parse_understat_rows([REAL_ROW])

    assert len(sides) == 2
    home, away = sides
    assert home["is_home"] is True
    assert home["team"] == "Liverpool"
    assert home["goals_for"] == 4
    assert home["goals_against"] == 2
    assert home["xg"] == 2.33007
    assert home["xga"] == 1.57303
    assert home["ppda"] == 8.764706

    assert away["is_home"] is False
    assert away["team"] == "Bournemouth"
    assert away["goals_for"] == 2
    assert away["goals_against"] == 4
    assert away["xg"] == 1.57303
    assert away["xga"] == 2.33007


def test_an_unrecognised_league_is_skipped_not_guessed():
    row = {**REAL_ROW, "league": "SCO-Premiership"}
    assert parse_understat_rows([row]) == []


def test_kickoff_is_parsed_and_treated_as_utc():
    sides = parse_understat_rows([REAL_ROW])
    assert sides[0]["kickoff_at"] == datetime(2025, 8, 15, 19, 0, tzinfo=UTC)


async def _team(pg, name: str) -> str:
    return await pg.fetchval(
        "insert into teams (sport, canonical_name) values ('football', $1) "
        "returning id",
        name,
    )


async def _alias(pg, team_id: str, name: str) -> None:
    await pg.execute(
        "insert into team_aliases (canonical_team_id, source, source_name) "
        "values ($1, 'understat', $2)",
        team_id,
        name,
    )


async def _competition(pg, name: str) -> str:
    return await pg.fetchval(
        "insert into competitions (sport, name, country) "
        "values ('football', $1, 'England') returning id",
        name,
    )


def _game(comp, home, away, kickoff, home_goals=4, away_goals=2, game_id="28778"):
    return {
        "game_id": game_id,
        "competition_id": comp,
        "home_id": home,
        "away_id": away,
        "kickoff_at": kickoff,
        "home_goals": home_goals,
        "away_goals": away_goals,
    }


async def test_find_or_create_fixtures_creates_a_finished_historical_fixture(
    job_ctx, pg
):
    comp = await _competition(pg, "Premier League")
    home = await _team(pg, "Liverpool")
    away = await _team(pg, "Bournemouth")
    kickoff = datetime(2025, 8, 15, 19, 0, tzinfo=UTC)

    by_game = await find_or_create_fixtures(job_ctx, [_game(comp, home, away, kickoff)])

    fixture_id = by_game["28778"]
    row = await pg.fetchrow(
        "select status, home_goals, away_goals from fixtures where id = $1",
        fixture_id,
    )
    assert row["status"] == "finished"
    assert row["home_goals"] == 4
    assert row["away_goals"] == 2
    source_id = await pg.fetchval(
        "select source_id from fixture_source_ids where fixture_id = $1 "
        "and source = 'understat'",
        fixture_id,
    )
    assert source_id == "28778"


async def test_find_or_create_fixtures_reuses_an_already_synced_fixture(job_ctx, pg):
    comp = await _competition(pg, "Premier League")
    home = await _team(pg, "Liverpool")
    away = await _team(pg, "Bournemouth")
    kickoff = datetime(2025, 8, 15, 19, 0, tzinfo=UTC)
    existing_id = await pg.fetchval(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, $4, 'scheduled') "
        "returning id",
        comp,
        home,
        away,
        kickoff,
    )

    by_game = await find_or_create_fixtures(
        job_ctx, [_game(comp, home, away, kickoff + timedelta(minutes=5))]
    )

    found = by_game["28778"]
    assert found == str(existing_id)
    status = await pg.fetchval("select status from fixtures where id = $1", found)
    assert status == "finished"


async def test_find_or_create_fixtures_handles_a_mixed_batch(job_ctx, pg):
    """One game already synced (must be reused, not duplicated), one entirely
    new (must be created) — in the same batch, exercising both the matched
    and unmatched paths of the single combined query."""
    comp = await _competition(pg, "Premier League")
    liverpool = await _team(pg, "Liverpool")
    bournemouth = await _team(pg, "Bournemouth")
    villa = await _team(pg, "Aston Villa")
    newcastle = await _team(pg, "Newcastle United")
    kickoff_a = datetime(2025, 8, 15, 19, 0, tzinfo=UTC)
    kickoff_b = datetime(2025, 8, 16, 11, 30, tzinfo=UTC)

    existing_id = await pg.fetchval(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, $4, 'scheduled') "
        "returning id",
        comp,
        liverpool,
        bournemouth,
        kickoff_a,
    )

    by_game = await find_or_create_fixtures(
        job_ctx,
        [
            _game(comp, liverpool, bournemouth, kickoff_a, game_id="28778"),
            _game(comp, villa, newcastle, kickoff_b, home_goals=1, away_goals=0, game_id="28779"),
        ],
    )

    assert by_game["28778"] == str(existing_id)
    assert by_game["28779"] != str(existing_id)
    new_row = await pg.fetchrow(
        "select status, home_goals, away_goals from fixtures where id = $1",
        by_game["28779"],
    )
    assert dict(new_row) == {"status": "finished", "home_goals": 1, "away_goals": 0}


async def test_sync_understat_stats_writes_both_sides_and_is_idempotent(job_ctx, pg):
    await _competition(pg, "Premier League")
    home = await _team(pg, "Liverpool")
    away = await _team(pg, "Bournemouth")
    await _alias(pg, home, "Liverpool")
    await _alias(pg, away, "Bournemouth")

    written, unresolved = await sync_understat_stats(job_ctx, [REAL_ROW])
    assert (written, unresolved) == (2, 0)

    # Idempotent: running again on the same data must not duplicate rows or
    # error against the (fixture_id, team_id, source) uniqueness.
    written_again, _ = await sync_understat_stats(job_ctx, [REAL_ROW])
    assert written_again == 2

    rows = await pg.fetch(
        "select team_id, goals_for, xg from team_match_stats "
        "where team_id = any($1::uuid[]) order by is_home desc",
        [home, away],
    )
    assert len(rows) == 2
    assert rows[0]["team_id"] == home
    assert rows[0]["goals_for"] == 4
    assert rows[1]["team_id"] == away
    assert rows[1]["goals_for"] == 2


async def test_two_vendor_rows_resolving_to_the_same_fixture_do_not_collide(job_ctx, pg):
    """Postgres flatly rejects an ON CONFLICT DO UPDATE that would affect the
    same row twice in one statement (CardinalityViolationError) — caught by
    a large-batch benchmark, not by inspection. Two different game_ids that
    both match the same already-synced fixture (a real possibility: a
    rescheduled or duplicate vendor entry) must not crash the whole batch.
    """
    await _competition(pg, "Premier League")
    home = await _team(pg, "Liverpool")
    away = await _team(pg, "Bournemouth")
    await _alias(pg, home, "Liverpool")
    await _alias(pg, away, "Bournemouth")

    duplicate_row = {**REAL_ROW, "game_id": 99999}

    written, unresolved = await sync_understat_stats(job_ctx, [REAL_ROW, duplicate_row])

    assert unresolved == 0
    assert written == 2  # collapsed to one fixture's worth, not four rows
    count = await pg.fetchval(
        "select count(*) from team_match_stats where team_id = any($1::uuid[])",
        [home, away],
    )
    assert count == 2


async def test_an_unresolvable_team_blocks_that_sides_row_not_the_other(job_ctx, pg):
    await _competition(pg, "Premier League")
    home = await _team(pg, "Liverpool")
    await _alias(pg, home, "Liverpool")
    # Bournemouth deliberately not aliased.

    written, unresolved = await sync_understat_stats(job_ctx, [REAL_ROW])

    # Neither side writes: find_or_create_fixture needs both teams resolved
    # before a fixture can even exist to attach stats to.
    assert written == 0
    assert unresolved == 2
    backlog = await pg.fetchval(
        "select source_name from unresolved_team_names where source = 'understat'"
    )
    assert backlog == "Bournemouth"


class _FakeScraper:
    def __init__(self, cached) -> None:
        self._cached = cached

    async def latest_archived(self, source: str, entity_ref: str):
        return self._cached


class _SkippedResult:
    skipped_unchanged = True
    rows: list = []


async def test_a_skipped_unchanged_fetch_still_parses_the_archived_copy(job_ctx, pg):
    await _competition(pg, "Premier League")
    home = await _team(pg, "Liverpool")
    away = await _team(pg, "Bournemouth")
    await _alias(pg, home, "Liverpool")
    await _alias(pg, away, "Bournemouth")

    written, unresolved = await sync_from_scrape_result(
        job_ctx,
        _FakeScraper([REAL_ROW]),
        _SkippedResult(),
        leagues=list(LEAGUE_NAMES.keys()),
        seasons=["2526"],
    )

    assert (written, unresolved) == (2, 0)


async def test_a_skipped_fetch_with_nothing_archived_yet_is_a_quiet_no_op(job_ctx):
    written, unresolved = await sync_from_scrape_result(
        job_ctx,
        _FakeScraper(None),
        _SkippedResult(),
        leagues=list(LEAGUE_NAMES.keys()),
        seasons=["2526"],
    )

    assert (written, unresolved) == (0, 0)
