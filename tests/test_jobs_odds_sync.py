"""Real-Postgres tests for jobs/odds_sync.py's matching logic.

The provider-parsing side is covered by tests/test_odds_api.py with FakeDb;
what actually needs a real server is the SQL that decides which competitions
this vendor can serve odds for, and which fixture a vendor's game matches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from gamesenze.jobs.odds_sync import covered_competitions, match_fixture
from tests.conftest import requires_pg

pytestmark = requires_pg

KICKOFF = datetime(2026, 8, 21, 19, 0, tzinfo=UTC)


async def _team(pg, name: str) -> str:
    return await pg.fetchval(
        "insert into teams (sport, canonical_name) values ('football', $1) "
        "returning id",
        name,
    )


async def _competition(pg, name: str) -> str:
    return await pg.fetchval(
        "insert into competitions (sport, name, country) "
        "values ('football', $1, 'England') returning id",
        name,
    )


async def _resolve_against_football_data(pg, competition_id: str, code: str) -> None:
    await pg.execute(
        "insert into competition_source_ids (competition_id, source, source_id, "
        "resolved_name, resolved_at, resolved_by) "
        "values ($1, 'football_data', $2, $3, now(), 'test')",
        competition_id,
        code,
        code,
    )


async def test_only_leagues_the_odds_api_actually_covers_are_returned(job_ctx, pg):
    epl = await _competition(pg, "Premier League")
    await _resolve_against_football_data(pg, epl, "PL")

    # Resolved against football_data, but not a league the-odds-api has —
    # must not appear, or odds_sync would spend a credit calling a sport_key
    # that does not exist.
    ucl = await _competition(pg, "UEFA Champions League")
    await _resolve_against_football_data(pg, ucl, "CL")

    covered = await covered_competitions(job_ctx)

    names = {c["name"] for c in covered}
    assert names == {"Premier League"}


async def test_a_competition_never_resolved_against_football_data_is_excluded(
    job_ctx, pg
):
    await _competition(pg, "Premier League")  # no competition_source_ids row

    covered = await covered_competitions(job_ctx)

    assert covered == []


async def test_match_fixture_finds_the_right_teams_within_tolerance(job_ctx, pg):
    comp = await _competition(pg, "Premier League")
    home = await _team(pg, "Arsenal")
    away = await _team(pg, "Coventry City")
    fixture_id = await pg.fetchval(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, $4, 'scheduled') "
        "returning id",
        comp,
        home,
        away,
        KICKOFF,
    )

    found = await match_fixture(job_ctx, comp, home, away, KICKOFF + timedelta(minutes=5))

    assert found == fixture_id


async def test_match_fixture_returns_none_outside_the_tolerance_window(job_ctx, pg):
    comp = await _competition(pg, "Premier League")
    home = await _team(pg, "Arsenal")
    away = await _team(pg, "Coventry City")
    await pg.execute(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, $4, 'scheduled')",
        comp,
        home,
        away,
        KICKOFF,
    )

    found = await match_fixture(job_ctx, comp, home, away, KICKOFF + timedelta(days=3))

    assert found is None


async def test_match_fixture_ignores_a_fixture_already_kicked_off(job_ctx, pg):
    comp = await _competition(pg, "Premier League")
    home = await _team(pg, "Arsenal")
    away = await _team(pg, "Coventry City")
    await pg.execute(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, $4, 'finished')",
        comp,
        home,
        away,
        KICKOFF,
    )

    found = await match_fixture(job_ctx, comp, home, away, KICKOFF)

    assert found is None


async def test_match_fixture_picks_the_closer_of_two_candidates(job_ctx, pg):
    comp = await _competition(pg, "Premier League")
    home = await _team(pg, "Arsenal")
    away = await _team(pg, "Coventry City")
    far_id = await pg.fetchval(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, $4, 'scheduled') "
        "returning id",
        comp,
        home,
        away,
        KICKOFF - timedelta(hours=5),
    )
    near_id = await pg.fetchval(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, $4, 'scheduled') "
        "returning id",
        comp,
        home,
        away,
        KICKOFF,
    )

    found = await match_fixture(job_ctx, comp, home, away, KICKOFF + timedelta(minutes=1))

    assert found == near_id
    assert found != far_id
