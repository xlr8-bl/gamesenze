"""§4.3 name resolution and §3.3 coverage admission."""

from __future__ import annotations

import pytest

from pitchside.budget import BudgetMeter
from pitchside.coverage import CoverageController
from pitchside.degrade import Rung, policy_for
from pitchside.normalize import (
    TeamResolver,
    UnresolvedTeamName,
    normalise_name,
    suggest_aliases,
)
from pitchside.odds.schedule import monthly_object_cost
from tests.conftest import FakeDb


def test_the_four_spellings_from_the_prd_collapse_to_one_key():
    keys = {
        normalise_name(n)
        for n in ("Man Utd", "Manchester Utd", "Manchester United", "Man United")
    }
    assert keys == {"manchester united"}


def test_accents_and_club_boilerplate_are_stripped():
    assert normalise_name("Atlético Madrid") == normalise_name("Club Atletico de Madrid")
    assert normalise_name("Bayern München") == normalise_name("FC Bayern Munchen")


def test_a_name_of_pure_boilerplate_does_not_become_empty():
    assert normalise_name("FC") != ""


def test_suggestions_are_ranked_but_never_applied():
    suggestions = suggest_aliases(
        "Man Utd",
        {"1": "Manchester United", "2": "Manchester City", "3": "Newcastle United"},
    )
    assert suggestions[0].canonical_name == "Manchester United"
    assert suggestions[0].similarity > suggestions[1].similarity


async def test_a_known_alias_resolves(clock):
    db = FakeDb({"select canonical_team_id": "team-uuid"})
    resolver = TeamResolver(db, clock)
    assert await resolver.resolve("fbref", "Man Utd") == "team-uuid"


async def test_an_unknown_name_blocks_and_never_guesses(clock):
    # REQ-DATA-NORM-1. "Manchester Utd" is one edit from a team we know, and it
    # still does not get resolved.
    db = FakeDb({"select canonical_team_id": None})
    resolver = TeamResolver(db, clock)

    with pytest.raises(UnresolvedTeamName):
        await resolver.resolve("fbref", "Manchester Utd", fixture_id="fix-1")

    assert db.wrote("insert into unresolved_team_names")
    flags = db.writes_matching("insert into qa_flags")
    assert len(flags) == 1
    assert flags[0][1][5] == "block"  # severity


async def test_resolution_is_cached_within_a_job(clock):
    db = FakeDb({"select canonical_team_id": "team-uuid"})
    resolver = TeamResolver(db, clock)

    await resolver.resolve("fbref", "Man Utd")
    await resolver.resolve("fbref", "Man Utd")

    assert len(db.writes_matching("select canonical_team_id")) == 1


async def test_try_resolve_lets_a_batch_continue(clock):
    db = FakeDb({"select canonical_team_id": None})
    resolver = TeamResolver(db, clock)
    assert await resolver.try_resolve("fbref", "Who FC") is None


async def test_adding_an_alias_clears_the_backlog_entry(clock):
    db = FakeDb()
    resolver = TeamResolver(db, clock)
    await resolver.add_alias("fbref", "Man Utd", "team-uuid")

    assert db.wrote("insert into team_aliases")
    assert db.wrote("update unresolved_team_names set resolved_at")
    # And it is cached, so the next lookup does not hit the database.
    assert await resolver.resolve("fbref", "Man Utd") == "team-uuid"


# --- Coverage admission ----------------------------------------------------

def test_the_monthly_plan_costs_exactly_the_budgeted_objects():
    # §3.3: 100 x 16 + 50 x 8 = 2,000, the planned spend of a 2,500 ceiling.
    assert monthly_object_cost(100, 50) == 2000


async def test_a_fixture_is_refused_when_its_whole_plan_will_not_fit(clock):
    # Half-covering a fixture spends objects and still cannot publish, because
    # the closing line never gets captured.
    db = FakeDb({"select calls_used from api_budget": 2492, "count(*) from fixtures": 10})
    controller = CoverageController(db, BudgetMeter(db, clock))

    decision = await controller.can_cover("football")

    assert not decision.admitted
    assert "8 objects left" in decision.reason


async def test_the_monthly_fixture_cap_is_enforced(clock):
    db = FakeDb({"select calls_used from api_budget": 0, "count(*) from fixtures": 100})
    controller = CoverageController(db, BudgetMeter(db, clock))

    decision = await controller.can_cover("football")

    assert not decision.admitted
    assert "cap reached (100/100)" in decision.reason


async def test_a_degraded_plan_costs_less_and_can_still_be_admitted(clock):
    db = FakeDb({"select calls_used from api_budget": 2492, "count(*) from fixtures": 10})
    controller = CoverageController(db, BudgetMeter(db, clock))

    decision = await controller.can_cover(
        "football", policy=policy_for(Rung.CLOSING_ONLY)
    )

    assert decision.admitted
    assert decision.objects_required == 1


async def test_room_and_headroom_means_admitted(clock):
    db = FakeDb({"select calls_used from api_budget": 100, "count(*) from fixtures": 5})
    controller = CoverageController(db, BudgetMeter(db, clock))

    decision = await controller.can_cover("football")

    assert decision.admitted
    assert decision.objects_required == 16
