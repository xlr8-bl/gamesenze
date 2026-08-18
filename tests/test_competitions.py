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
from gamesenze.jobs.fixture_sync import upsert_fixture
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
            "select fixture_id from fixture_source_ids": None,
            "select canonical_team_id": "team-uuid",
            "returning id": "fixture-uuid",
        }
    )
    resolver = TeamResolver(db)

    fixture_id = await upsert_fixture(
        type("Ctx", (), {"db": db})(), resolver, "comp-uuid", _parsed()
    )

    assert fixture_id == "fixture-uuid"
    assert db.wrote("insert into fixtures")
    assert db.wrote("insert into fixture_source_ids")


async def test_an_unresolved_team_blocks_the_fixture_entirely():
    # REQ-DATA-NORM-1: no fixture row at all, not one with a guessed team.
    db = FakeDb(
        {
            "select fixture_id from fixture_source_ids": None,
            "select canonical_team_id": None,
        }
    )
    resolver = TeamResolver(db)

    fixture_id = await upsert_fixture(
        type("Ctx", (), {"db": db})(), resolver, "comp-uuid", _parsed()
    )

    assert fixture_id is None
    assert not db.wrote("insert into fixtures")


async def test_an_existing_fixture_is_updated_not_duplicated():
    db = FakeDb(
        {
            "select fixture_id from fixture_source_ids": "existing-fixture-uuid",
            "select canonical_team_id": "team-uuid",
        }
    )
    resolver = TeamResolver(db)

    fixture_id = await upsert_fixture(
        type("Ctx", (), {"db": db})(), resolver, "comp-uuid", _parsed()
    )

    assert fixture_id == "existing-fixture-uuid"
    assert db.wrote("update fixtures")
    assert not db.wrote("insert into fixtures")
