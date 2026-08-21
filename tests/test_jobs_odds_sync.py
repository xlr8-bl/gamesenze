"""Real-Postgres tests for jobs/odds_sync.py's matching logic.

The provider-parsing side is covered by tests/test_odds_api.py with FakeDb;
what actually needs a real server is the SQL that decides which competitions
this vendor can serve odds for, and which fixture a vendor's game matches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg

from gamesenze.config import Settings
from gamesenze.jobs import odds_sync
from gamesenze.jobs.odds_sync import covered_competitions, match_fixture
from gamesenze.providers.base import Response
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


class _FakeTransport:
    """Stands in for the vendor: returns one matchable game, one that
    resolves no team on either side, in the real /odds response shape."""

    def __init__(self, kickoff):
        self._kickoff = kickoff

    async def get(self, url, *, params, headers):
        commence = self._kickoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        body = [
            {
                "id": "matchable",
                "sport_key": "soccer_epl",
                "commence_time": commence,
                "home_team": "Arsenal",
                "away_team": "Coventry City",
                "bookmakers": [
                    {
                        "key": "pinnacle",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Arsenal", "price": 1.5},
                                    {"name": "Coventry City", "price": 6.0},
                                    {"name": "Draw", "price": 4.0},
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": "unmatchable",
                "sport_key": "soccer_epl",
                "commence_time": commence,
                "home_team": "Nobody FC",
                "away_team": "Nowhere United",
                "bookmakers": [],
            },
        ]
        return Response(200, body, url)


async def test_main_matches_a_fixture_and_backlogs_an_unresolved_one(
    job_ctx, pg, monkeypatch, capsys
):
    comp = await _competition(pg, "Premier League")
    home = await _team(pg, "Arsenal")
    away = await _team(pg, "Coventry City")
    await pg.execute(
        "insert into team_aliases (canonical_team_id, source, source_name) "
        "values ($1, 'odds_api', 'Arsenal')",
        home,
    )
    await pg.execute(
        "insert into team_aliases (canonical_team_id, source, source_name) "
        "values ($1, 'odds_api', 'Coventry City')",
        away,
    )
    fixture_id = await pg.fetchval(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, $4, 'scheduled') "
        "returning id",
        comp,
        home,
        away,
        KICKOFF,
    )
    await _resolve_against_football_data(pg, comp, "PL")

    real_init = odds_sync.OddsApi.__init__

    def fake_init(self, api_key, *, db, meter, transport=None, clock=None):
        real_init(self, api_key, db=db, meter=meter, transport=_FakeTransport(KICKOFF), clock=clock)

    monkeypatch.setattr(odds_sync.OddsApi, "__init__", fake_init)
    from gamesenze.config import Settings

    job_ctx.settings = Settings(odds_api_key="test-key")

    result = await odds_sync.main(job_ctx)

    assert result == 0
    out = capsys.readouterr().out
    assert "odds captured for 1 fixture(s), 1 game(s) not matched" in out

    stored = await pg.fetch(
        "select bookmaker, market, selection, decimal_odds from odds_snapshots "
        "where fixture_id = $1 order by selection",
        fixture_id,
    )
    assert len(stored) == 3
    assert {r["selection"] for r in stored} == {"Arsenal", "Coventry City", "Draw"}

    backlog = await pg.fetch(
        "select source_name from unresolved_team_names where source = 'odds_api' "
        "order by source_name"
    )
    assert [r["source_name"] for r in backlog] == ["Nobody FC", "Nowhere United"]


async def test_resubmitting_the_same_batch_does_not_duplicate_rows(job_ctx, pg):
    """Pins the correctness half of the write-retry story.

    tests/test_odds_sync_retry.py pins that _insert_odds_snapshots actually
    retries on a dropped connection; this pins that doing so is safe — the
    same batch submitted twice (what a retry after an ambiguous connection
    drop looks like from the database's side) must not double the rows.
    """
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

    from gamesenze.jobs.odds_sync import _insert_odds_snapshots

    captured_at = KICKOFF - timedelta(days=1)
    columns = (
        [fixture_id],
        [captured_at],
        ["pinnacle"],
        ["h2h"],
        ["home"],
        [1.5],
        ["daily"],
        [False],
    )

    await _insert_odds_snapshots(job_ctx, *columns)
    await _insert_odds_snapshots(job_ctx, *columns)  # the "retry"

    count = await pg.fetchval(
        "select count(*) from odds_snapshots where fixture_id = $1", fixture_id
    )
    assert count == 1


async def test_one_leagues_persistent_connection_failure_does_not_sink_the_others(
    job_ctx, pg, monkeypatch, capsys
):
    """Seen live: odds_sync crashed outright — an uncaught TimeoutError from
    one league's provenance write took down asyncio.gather() for all 8
    leagues, discarding 7 already-successful fetches. _fetch() must catch a
    persistent connection failure on one league and continue with the rest.
    """
    working_comp = await _competition(pg, "Premier League")
    await _resolve_against_football_data(pg, working_comp, "PL")
    broken_comp = await _competition(pg, "La Liga")
    await _resolve_against_football_data(pg, broken_comp, "PD")

    async def fake_odds(self, sport_key, *, regions="uk", markets="h2h"):
        if sport_key == "soccer_spain_la_liga":
            raise asyncpg.exceptions.ConnectionDoesNotExistError("still gone")
        return Response(200, [], "https://example.test")

    monkeypatch.setattr(odds_sync.OddsApi, "odds", fake_odds)
    job_ctx.settings = Settings(odds_api_key="test-key")

    result = await odds_sync.main(job_ctx)

    assert result == 0
    out = capsys.readouterr().out
    assert "odds captured for 0 fixture(s), 0 game(s) not matched" in out
