"""§4.3 name resolution and §3.3 coverage admission."""

from __future__ import annotations

import pytest

from gamesenze.budget import BudgetMeter
from gamesenze.coverage import CoverageController
from gamesenze.degrade import Rung, policy_for
from gamesenze.normalize import (
    TeamResolver,
    UnresolvedTeamName,
    normalise_name,
    suggest_aliases,
)
from gamesenze.odds.schedule import monthly_object_cost
from tests.conftest import FakeDb, requires_pg


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


async def test_an_unresolved_name_is_also_cached_within_a_job(clock):
    """A team can appear in ~38 matches a season; without this, a single
    unresolvable name cost 3 round trips (a lookup, an unresolved_team_names
    upsert, a QA flag upsert) *per occurrence* instead of once per job run.
    Seen live: a real season's worth of Understat data with several
    genuinely unresolved names turned a batched job into one that hung for
    10+ minutes and had to be killed.
    """
    db = FakeDb({"select canonical_team_id": None})
    resolver = TeamResolver(db, clock)

    with pytest.raises(UnresolvedTeamName):
        await resolver.resolve("fbref", "Who FC")
    with pytest.raises(UnresolvedTeamName):
        await resolver.resolve("fbref", "Who FC")

    assert len(db.writes_matching("select canonical_team_id")) == 1
    assert len(db.writes_matching("insert into unresolved_team_names")) == 1
    assert len(db.writes_matching("insert into qa_flags")) == 1


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


async def test_adding_an_alias_overrides_an_earlier_failure_in_the_same_job(clock):
    """A name that failed earlier in a run (and is now negatively cached)
    must resolve immediately once add_alias makes it valid — not keep
    raising from the stale failure cache for the rest of the run.
    """
    db = FakeDb({"select canonical_team_id": None})
    resolver = TeamResolver(db, clock)

    with pytest.raises(UnresolvedTeamName):
        await resolver.resolve("fbref", "Man Utd")

    await resolver.add_alias("fbref", "Man Utd", "team-uuid")

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


async def test_sweep_resolved_clears_stale_backlog_entries(clock):
    # The exact scenario this fixes: a name failed once, an alias was added
    # later (e.g. by reseeding), and nothing ever told unresolved_team_names.
    db = FakeDb({"update unresolved_team_names": [{"id": 1}]})
    resolver = TeamResolver(db, clock)

    cleared = await resolver.sweep_resolved()

    assert cleared == 1
    assert db.wrote("update unresolved_team_names")


async def test_sweep_resolved_leaves_genuinely_unresolved_entries(clock):
    # No alias exists, so the join matches nothing and nothing is cleared.
    db = FakeDb({"update unresolved_team_names": []})
    resolver = TeamResolver(db, clock)

    cleared = await resolver.sweep_resolved()

    assert cleared == 0


async def test_sweep_resolved_does_not_inflate_sightings_or_reraise_flags(clock):
    """Reading the queue must not mutate it.

    sweep_resolved used to call try_resolve() per row, which for a name that
    still does not resolve bumps unresolved_team_names.sightings and re-raises
    a QA flag — so merely running `aliases backlog` corrupted the very counter
    the backlog is sorted by.
    """
    db = FakeDb({"update unresolved_team_names": []})
    resolver = TeamResolver(db, clock)

    await resolver.sweep_resolved()

    assert not db.wrote("insert into unresolved_team_names")
    assert not db.wrote("insert into qa_flags")


async def test_sweep_resolved_on_an_empty_backlog_is_a_no_op(clock):
    db = FakeDb({"select * from unresolved_team_names": []})
    resolver = TeamResolver(db, clock)
    assert await resolver.sweep_resolved() == 0


# --- sweep_resolved against a real server -----------------------------------
# It is a single set-based UPDATE ... FROM now, so the thing worth testing is
# the SQL itself, which FakeDb cannot exercise.

@requires_pg
async def test_sweep_resolved_clears_only_aliased_names_against_real_sql(job_ctx, pg):
    team = await pg.fetchval(
        "insert into teams (sport, canonical_name) values ('football', $1) "
        "returning id",
        "Liverpool",
    )
    await pg.execute(
        "insert into team_aliases (canonical_team_id, source, source_name) "
        "values ($1, 'football_data', 'Liverpool FC')",
        team,
    )
    await pg.execute(
        "insert into unresolved_team_names (source, source_name, sightings) "
        "values ('football_data', 'Liverpool FC', 3), "
        "       ('football_data', 'Some New Club', 5)"
    )

    resolver = TeamResolver(job_ctx.db, job_ctx.clock)
    cleared = await resolver.sweep_resolved()

    assert cleared == 1
    still_open = await pg.fetch(
        "select source_name from unresolved_team_names where resolved_at is null"
    )
    assert [r["source_name"] for r in still_open] == ["Some New Club"]


@requires_pg
async def test_sweeping_does_not_mutate_the_queue_it_reads(job_ctx, pg):
    """Reading the backlog must not bump sightings or re-raise flags.

    sweep_resolved used to call try_resolve() per row; for a name that still
    does not resolve that records a sighting and raises a QA flag, so simply
    running `aliases backlog` corrupted the counter the backlog sorts by.
    """
    await pg.execute(
        "insert into unresolved_team_names (source, source_name, sightings) "
        "values ('football_data', 'Some New Club', 5)"
    )
    flags_before = await pg.fetchval("select count(*) from qa_flags")

    resolver = TeamResolver(job_ctx.db, job_ctx.clock)
    assert await resolver.sweep_resolved() == 0

    assert await pg.fetchval(
        "select sightings from unresolved_team_names where source_name = $1",
        "Some New Club",
    ) == 5
    assert await pg.fetchval("select count(*) from qa_flags") == flags_before


async def test_warm_prefills_the_cache_in_one_query(clock):
    """A batch ingest resolves every name in one round trip, not one each.

    Before warm(), matching an odds board resolved each team the first time it
    was seen — on a cold cache that is one Supabase round trip per distinct
    name, dozens to hundreds of them in a row, all pure latency. warm() folds
    them into a single query; the per-row resolve() calls that follow must then
    make no further database reads.
    """
    db = FakeDb(
        {
            "select source_name, canonical_team_id from team_aliases": [
                {"source_name": "Manchester United", "canonical_team_id": "t1"},
                {"source_name": "Arsenal", "canonical_team_id": "t2"},
            ]
        }
    )
    resolver = TeamResolver(db, clock)

    # Duplicates and blanks collapse; one query goes out.
    await resolver.warm("odds_api", ["Manchester United", "Arsenal", "Manchester United", ""])
    assert len(db.writes_matching("select source_name, canonical_team_id")) == 1

    # Both names now resolve straight from the cache.
    assert await resolver.resolve("odds_api", "Manchester United") == "t1"
    assert await resolver.resolve("odds_api", "Arsenal") == "t2"
    assert db.writes_matching("select canonical_team_id from team_aliases") == []


async def test_warm_leaves_unknown_names_to_the_normal_path(clock):
    """A name with no alias is not cached by warm(), so it still blocks and is
    recorded as unresolved exactly as before — warming changes speed, nothing
    else."""
    db = FakeDb({"select source_name, canonical_team_id from team_aliases": []})
    resolver = TeamResolver(db, clock)

    await resolver.warm("odds_api", ["Who FC"])
    assert await resolver.try_resolve("odds_api", "Who FC") is None
    assert db.wrote("insert into unresolved_team_names")
