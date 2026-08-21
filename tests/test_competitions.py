"""§3.2 budget math applied to the actual competition list, plus the resolver
and sync logic that keep it honest.
"""

from __future__ import annotations

import pytest

from gamesenze.competitions import COMPETITIONS, by_key, daily_api_football_cost
from gamesenze.config import (
    API_FOOTBALL_DAILY_ALLOCATION,
    PROVIDER_BUDGETS,
    UTILISATION_BAND,
)
from gamesenze.jobs.fixture_sync import upsert_fixtures
from gamesenze.jobs.resolve_competitions import candidates_from_response, prompt_choice
from gamesenze.normalize import TeamResolver
from tests.conftest import NOW, FakeDb


def test_every_key_is_unique():
    keys = [c.key for c in COMPETITIONS]
    assert len(keys) == len(set(keys))


def test_by_key_finds_a_real_competition_and_refuses_a_fake_one():
    assert by_key("premier_league").name == "Premier League"
    with pytest.raises(KeyError):
        by_key("not-a-real-competition")


def test_the_full_plan_stays_inside_the_operating_band():
    # The point of the whole conversation that produced this list: fit inside
    # 70-85% of the API-Football ceiling, not scrape the top of it.
    fixed = sum(
        API_FOOTBALL_DAILY_ALLOCATION[j]
        for j in (
            "injuries",
            "confirmed_lineups",
            "head_to_head",
            "results_settlement",
            "qa_cross_verification",
        )
    )
    ceiling = PROVIDER_BUDGETS["api_football"].ceiling
    total = fixed + daily_api_football_cost()

    low, high = UTILISATION_BAND
    assert low <= total / ceiling <= high


def test_cups_never_cost_a_standings_call():
    cups = [c for c in COMPETITIONS if not c.needs_standings]
    assert len(cups) >= 5  # FA Cup, Copa del Rey, Coppa Italia, DFB Pokal, ...
    for cup in cups:
        assert not cup.needs_standings


# --- resolver -----------------------------------------------------------

def test_candidate_parsing_survives_missing_fields():
    body = {"response": [{"league": {"id": 1, "name": "X"}}]}
    candidates = candidates_from_response(body)
    assert candidates == [
        {"id": 1, "name": "X", "type": None, "country": None, "current_season": None}
    ]


def test_candidate_parsing_picks_the_current_season():
    body = {
        "response": [
            {
                "league": {"id": 39, "name": "Premier League", "type": "League"},
                "country": {"name": "England"},
                "seasons": [
                    {"year": 2024, "current": False},
                    {"year": 2025, "current": True},
                ],
            }
        ]
    }
    assert candidates_from_response(body)[0]["current_season"] == 2025


def test_an_empty_response_yields_no_candidates():
    assert candidates_from_response({"response": []}) == []
    assert candidates_from_response({}) == []


def test_prompt_choice_rejects_out_of_range(monkeypatch):
    candidates = [{"id": 1, "name": "A"}]
    monkeypatch.setattr("builtins.input", lambda _: "5")
    assert prompt_choice(candidates) is None


def test_prompt_choice_skip_is_the_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert prompt_choice([{"id": 1, "name": "A"}]) is None


def test_prompt_choice_selects_by_number(monkeypatch):
    candidates = [{"id": 39, "name": "Premier League"}, {"id": 570, "name": "Decoy"}]
    monkeypatch.setattr("builtins.input", lambda _: "1")
    assert prompt_choice(candidates)["id"] == 39


def test_prompt_choice_q_stops_entirely(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "q")
    with pytest.raises(KeyboardInterrupt):
        prompt_choice([{"id": 1, "name": "A"}])


# --- fixture_sync ---------------------------------------------------------

def _parsed(home="Liverpool", away="Man Utd"):
    return {
        "source_id": "999",
        "kickoff_at": NOW,
        "status": "scheduled",
        "venue": "Anfield",
        "home_source_name": home,
        "away_source_name": away,
        "home_goals": None,
        "away_goals": None,
    }


async def test_a_new_fixture_is_inserted_when_both_teams_resolve():
    db = FakeDb(
        {
            "select source_id, fixture_id from fixture_source_ids": [],
            "select canonical_team_id": "team-uuid",
            "insert into fixtures": [
                {
                    "id": "fixture-uuid",
                    "home_team_id": "team-uuid",
                    "away_team_id": "team-uuid",
                    "kickoff_at": NOW,
                }
            ],
        }
    )
    resolver = TeamResolver(db)

    synced, blocked = await upsert_fixtures(
        type("Ctx", (), {"db": db})(), resolver, "api_football",
        [("comp-uuid", _parsed())],
    )

    assert (synced, blocked) == (1, 0)
    assert db.wrote("insert into fixtures")
    assert db.wrote("insert into fixture_source_ids")


async def test_an_unresolved_team_blocks_the_fixture_entirely():
    # REQ-DATA-NORM-1: no fixture row at all, not one with a guessed team.
    db = FakeDb(
        {
            "select source_id, fixture_id from fixture_source_ids": [],
            "select canonical_team_id": None,
        }
    )
    resolver = TeamResolver(db)

    synced, blocked = await upsert_fixtures(
        type("Ctx", (), {"db": db})(), resolver, "api_football",
        [("comp-uuid", _parsed())],
    )

    assert (synced, blocked) == (0, 1)
    assert not db.wrote("insert into fixtures")


async def test_an_existing_fixture_is_updated_not_duplicated():
    db = FakeDb(
        {
            "select source_id, fixture_id from fixture_source_ids": [
                {"source_id": "999", "fixture_id": "existing-fixture-uuid"}
            ],
            "select canonical_team_id": "team-uuid",
        }
    )
    resolver = TeamResolver(db)

    synced, blocked = await upsert_fixtures(
        type("Ctx", (), {"db": db})(), resolver, "api_football",
        [("comp-uuid", _parsed())],
    )

    assert (synced, blocked) == (1, 0)
    assert db.wrote("update fixtures")
    assert not db.wrote("insert into fixtures")


# --- phone-safe modes -------------------------------------------------------

def test_parse_picks_reads_key_equals_id_pairs():
    from gamesenze.jobs.resolve_competitions import parse_picks

    assert parse_picks("premier_league=39,la_liga=140") == {
        "premier_league": 39,
        "la_liga": 140,
    }


def test_parse_picks_tolerates_whitespace_and_trailing_comma():
    from gamesenze.jobs.resolve_competitions import parse_picks

    assert parse_picks(" premier_league = 39 , la_liga=140, ") == {
        "premier_league": 39,
        "la_liga": 140,
    }


def test_parse_picks_rejects_a_malformed_pair():
    from gamesenze.jobs.resolve_competitions import parse_picks

    with pytest.raises(ValueError, match="not key=id"):
        parse_picks("premier_league=39,garbage")


def test_parse_picks_rejects_a_non_numeric_id():
    from gamesenze.jobs.resolve_competitions import parse_picks

    with pytest.raises(ValueError):
        parse_picks("premier_league=not-a-number")


async def test_confirm_from_picks_rejects_an_id_the_vendor_never_returned():
    # The whole point of --confirm: a typo'd id must not be accepted on
    # faith just because it came through a form field instead of a prompt.
    from gamesenze.jobs.resolve_competitions import confirm_from_picks

    class FakeClient:
        async def search_leagues(self, name):
            class R:
                body = {
                    "response": [
                        {
                            "league": {"id": 39, "name": "Premier League", "type": "League"},
                            "country": {"name": "England"},
                            "seasons": [{"year": 2025, "current": True}],
                        }
                    ]
                }

            return R()

    db = FakeDb()
    ctx = type("Ctx", (), {"db": db, "clock": None})()
    exit_code = await confirm_from_picks(
        ctx, FakeClient(), "premier_league=9999", "test"
    )

    assert exit_code == 1
    assert not db.wrote("insert into competition_source_ids")


async def test_confirm_from_picks_writes_a_vendor_verified_id():
    from gamesenze.jobs.resolve_competitions import confirm_from_picks

    class FakeClient:
        async def search_leagues(self, name):
            class R:
                body = {
                    "response": [
                        {
                            "league": {"id": 39, "name": "Premier League", "type": "League"},
                            "country": {"name": "England"},
                            "seasons": [{"year": 2025, "current": True}],
                        }
                    ]
                }

            return R()

    db = FakeDb({"returning id": "comp-uuid"})
    ctx = type("Ctx", (), {"db": db, "clock": _clock()})()
    exit_code = await confirm_from_picks(
        ctx, FakeClient(), "premier_league=39", "phone-test"
    )

    assert exit_code == 0
    assert db.wrote("insert into competition_source_ids")


def _clock():
    from gamesenze.clock import FrozenClock

    return FrozenClock(NOW)


async def test_confirm_from_picks_rejects_an_unknown_key():
    from gamesenze.jobs.resolve_competitions import confirm_from_picks

    db = FakeDb()
    ctx = type("Ctx", (), {"db": db, "clock": _clock()})()
    exit_code = await confirm_from_picks(
        ctx, object(), "not_a_real_key=39", "test"
    )
    assert exit_code == 1
    assert not db.wrote("insert into competition_source_ids")


async def test_dump_writes_nothing():
    from gamesenze.jobs.resolve_competitions import dump

    class FakeClient:
        async def search_leagues(self, name):
            class R:
                body = {"response": []}

            return R()

    db = FakeDb()
    ctx = type("Ctx", (), {"db": db})()
    await dump(ctx, FakeClient())

    assert not db.wrote("insert into")


# --- surfacing vendor errors (§8: failure must never be silent) -----------

async def test_a_vendor_error_is_logged_not_swallowed(caplog):
    import logging

    from gamesenze.jobs.fixture_sync import main as fixture_sync_main

    class FakeResponse:
        body = {"errors": {"season": "requested season is not available"},
                "matches": []}

    class FakeClient:
        async def matches(self, code, **kwargs):
            return FakeResponse()

    db = FakeDb(
        {
            "join competition_source_ids s\n            on s.competition_id = c.id and s.source = 'football_data'": [
                {
                    "competition_id": "comp-uuid",
                    "name": "Premier League",
                    "source_id": "PL",
                }
            ],
            "join competition_source_ids af": [],
        }
    )
    ctx = type(
        "Ctx",
        (),
        {
            "db": db,
            "settings": type(
                "S", (), {"football_data_key": "x", "api_football_key": ""}
            )(),
            "meter": None,
            "clock": None,
        },
    )()

    import gamesenze.jobs.fixture_sync as mod
    original = mod.FootballData
    mod.FootballData = lambda *a, **k: FakeClient()
    try:
        with caplog.at_level(logging.WARNING):
            await fixture_sync_main(ctx)
    finally:
        mod.FootballData = original

    assert any("API reported" in r.message for r in caplog.records)


# --- football-data.org resolver --------------------------------------------

def test_find_by_code_is_case_insensitive_and_rejects_unknown():
    from gamesenze.jobs.resolve_football_data import find_by_code

    candidates = [{"code": "PL", "name": "Premier League"}]
    assert find_by_code(candidates, "pl")["code"] == "PL"
    assert find_by_code(candidates, "PLX") is None
    assert find_by_code(candidates, "") is None


async def test_confirm_from_picks_rejects_a_code_the_vendor_never_returned():
    from gamesenze.jobs.resolve_football_data import confirm_from_picks

    class FakeClient:
        async def list_competitions(self):
            class R:
                body = {"competitions": [
                    {"code": "PL", "name": "Premier League",
                     "area": {"name": "England"},
                     "currentSeason": {"startDate": "2026-08-15"}}
                ]}
            return R()

    db = FakeDb()
    ctx = type("Ctx", (), {"db": db, "clock": None})()
    exit_code = await confirm_from_picks(
        ctx, FakeClient(), "premier_league=ZZ", "test"
    )

    assert exit_code == 1
    assert not db.wrote("insert into competition_source_ids")


async def test_confirm_from_picks_writes_a_vendor_verified_code():
    from gamesenze.clock import FrozenClock
    from gamesenze.jobs.resolve_football_data import confirm_from_picks

    class FakeClient:
        async def list_competitions(self):
            class R:
                body = {"competitions": [
                    {"code": "PL", "name": "Premier League",
                     "area": {"name": "England"},
                     "currentSeason": {"startDate": "2026-08-15"}}
                ]}
            return R()

    db = FakeDb({"returning id": "comp-uuid"})
    ctx = type("Ctx", (), {"db": db, "clock": FrozenClock(NOW)})()
    exit_code = await confirm_from_picks(
        ctx, FakeClient(), "premier_league=PL", "phone-test"
    )

    assert exit_code == 0
    assert db.wrote("insert into competition_source_ids")


async def test_confirm_from_picks_rejects_an_unknown_competition_key():
    from gamesenze.jobs.resolve_football_data import confirm_from_picks

    class FakeClient:
        async def list_competitions(self):
            class R:
                body = {"competitions": []}
            return R()

    db = FakeDb()
    ctx = type("Ctx", (), {"db": db, "clock": None})()
    exit_code = await confirm_from_picks(
        ctx, FakeClient(), "not_a_real_key=PL", "test"
    )
    assert exit_code == 1
    assert not db.wrote("insert into competition_source_ids")


async def test_dump_writes_nothing_and_lists_unresolved():
    from gamesenze.jobs.resolve_football_data import dump

    class FakeClient:
        async def list_competitions(self):
            class R:
                body = {"competitions": []}
            return R()

    db = FakeDb()
    ctx = type("Ctx", (), {"db": db})()
    await dump(ctx, FakeClient())

    assert not db.wrote("insert into")
