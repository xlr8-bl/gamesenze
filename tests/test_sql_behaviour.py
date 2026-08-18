"""Behaviour that only exists in SQL: the ladder view, the two `due_*`
functions and the lineup ingest path.

These matter because the Worker has no logic of its own (§2.3 CPU limit) — it
does what these functions tell it. A mistake here is a mistake in production
that no Python test would catch.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from tests.conftest import requires_pg

pytestmark = requires_pg


async def make_fixture(pg, *, kickoff_in: timedelta, covered=True, sport="football"):
    home = await pg.fetchval(
        "insert into teams (sport, canonical_name) values ($1, $2) returning id",
        sport,
        f"Home {kickoff_in}",
    )
    away = await pg.fetchval(
        "insert into teams (sport, canonical_name) values ($1, $2) returning id",
        sport,
        f"Away {kickoff_in}",
    )
    fixture_id = await pg.fetchval(
        """
        insert into fixtures (sport, home_team_id, away_team_id, kickoff_at,
                              covered, covered_at)
        values ($1, $2, $3, now() + $4, $5, now())
        returning id
        """,
        sport,
        home,
        away,
        kickoff_in,
        covered,
    )
    await pg.execute(
        "insert into fixture_source_ids values ($1, 'sportsgameodds', $2)",
        fixture_id,
        f"evt_{fixture_id}",
    )
    await pg.execute(
        "insert into fixture_source_ids values ($1, 'api_football', $2)",
        fixture_id,
        f"af_{fixture_id}",
    )
    return fixture_id, home, away


async def set_budget(pg, used, limit=2500):
    await pg.execute(
        """
        insert into api_budget (provider, period, calls_used, calls_limit)
        values ('sportsgameodds', to_char(now(), 'YYYY-MM'), $1, $2)
        on conflict (provider, period) do update
            set calls_used = excluded.calls_used, calls_limit = excluded.calls_limit
        """,
        used,
        limit,
    )


@pytest.mark.parametrize(
    ("used", "expected"),
    [(0, "normal"), (2000, "reduced"), (2250, "closing_only"), (2500, "exhausted")],
)
async def test_budget_view_reports_the_right_rung(pg, used, expected):
    await set_budget(pg, used)
    rung = await pg.fetchval(
        "select ladder_rung from v_budget_status where provider = 'sportsgameodds'"
    )
    assert rung == expected


async def test_a_covered_fixture_inside_a_window_is_due(pg):
    fixture_id, _, _ = await make_fixture(pg, kickoff_in=timedelta(hours=2))
    await set_budget(pg, 0)

    rows = await pg.fetch("select * from due_odds_snapshots(now(), 10, 20)")

    assert [r["fixture_id"] for r in rows] == [fixture_id]
    assert rows[0]["window_label"] == "t3_t1"


async def test_an_uncovered_fixture_is_never_polled(pg):
    # REQ-BUDGET-1: only fixtures with a published pick get snapshotted.
    await make_fixture(pg, kickoff_in=timedelta(hours=2), covered=False)
    await set_budget(pg, 0)

    rows = await pg.fetch("select * from due_odds_snapshots(now(), 10, 20)")

    assert rows == []


async def test_closing_only_drops_intermediate_captures_but_keeps_the_lock(pg):
    fixture_id, _, _ = await make_fixture(pg, kickoff_in=timedelta(hours=2))
    await set_budget(pg, 2250)  # 90%

    intermediate = await pg.fetch("select * from due_odds_snapshots(now(), 10, 20)")
    at_kickoff = await pg.fetch(
        "select * from due_odds_snapshots(now() + interval '2 hours', 10, 20)"
    )

    assert intermediate == []
    assert [r["window_label"] for r in at_kickoff] == ["lock"]


async def test_exhausted_stops_everything_including_the_lock(pg):
    await make_fixture(pg, kickoff_in=timedelta(hours=2))
    await set_budget(pg, 2500)

    rows = await pg.fetch(
        "select * from due_odds_snapshots(now() + interval '2 hours', 10, 20)"
    )

    assert rows == []


async def test_an_existing_capture_stops_the_fixture_being_asked_again(pg):
    fixture_id, _, _ = await make_fixture(pg, kickoff_in=timedelta(hours=2))
    await set_budget(pg, 0)
    await pg.execute(
        """
        insert into odds_snapshots (fixture_id, captured_at, bookmaker, market,
                                    selection, decimal_odds, window_label)
        values ($1, now(), 'pinnacle', '1x2', 'home', 2.0, 't3_t1')
        """,
        fixture_id,
    )

    rows = await pg.fetch("select * from due_odds_snapshots(now(), 10, 20)")

    assert rows == []


async def test_max_fixtures_caps_a_runaway_tick(pg):
    # Stagger backwards, not forwards: a kickoff further in the future moves
    # its T-2h capture point past `now` and out of the window entirely.
    for i in range(4):
        await make_fixture(pg, kickoff_in=timedelta(hours=2, minutes=-i))
    await set_budget(pg, 0)

    rows = await pg.fetch("select * from due_odds_snapshots(now(), 10, 2)")

    assert len(rows) == 2


# --- Lineup watch ----------------------------------------------------------

async def test_the_t1h_window_is_what_triggers_a_lineup_check(pg):
    inside, _, _ = await make_fixture(pg, kickoff_in=timedelta(minutes=60))
    await make_fixture(pg, kickoff_in=timedelta(hours=6))

    rows = await pg.fetch("select * from due_lineup_checks(now(), 20)")

    assert [r["fixture_id"] for r in rows] == [inside]


async def test_an_unresolved_team_name_blocks_and_does_not_guess(pg):
    # REQ-DATA-NORM-1, enforced on the Worker's write path too.
    fixture_id, _, _ = await make_fixture(pg, kickoff_in=timedelta(minutes=60))

    await pg.execute(
        "insert into lineup_ingest_queue (fixture_id, payload) values ($1, $2)",
        fixture_id,
        json.dumps(
            {"response": [{"team": {"name": "Nott'ham Forest"},
                           "startXI": [{"player": {"id": "1"}}]}]}
        ),
    )

    written = await pg.fetchval(
        "select rows_written from lineup_ingest_queue where fixture_id = $1",
        fixture_id,
    )
    flag = await pg.fetchrow(
        "select issue, severity from qa_flags where entity_id = $1 "
        "and issue = 'unresolved_team_name'",
        fixture_id,
    )
    backlog = await pg.fetchval(
        "select sightings from unresolved_team_names where source_name = $1",
        "Nott'ham Forest",
    )

    assert written == 0
    assert flag["severity"] == "block"
    assert backlog == 1
    assert await pg.fetchval(
        "select count(*) from lineups where fixture_id = $1", fixture_id
    ) == 0


async def test_a_resolved_name_stores_the_confirmed_xi(pg):
    fixture_id, home, _ = await make_fixture(pg, kickoff_in=timedelta(minutes=60))
    await pg.execute(
        "insert into team_aliases (canonical_team_id, source, source_name) "
        "values ($1, 'api_football', 'Nott''ham Forest')",
        home,
    )

    await pg.execute(
        "insert into lineup_ingest_queue (fixture_id, payload) values ($1, $2)",
        fixture_id,
        json.dumps(
            {"response": [{"team": {"name": "Nott'ham Forest"},
                           "startXI": [{"player": {"id": str(i)}} for i in range(11)]}]}
        ),
    )

    row = await pg.fetchrow(
        "select team_id, confirmed, player_ids from lineups where fixture_id = $1",
        fixture_id,
    )
    assert row["team_id"] == home
    assert row["confirmed"] is True
    assert len(row["player_ids"]) == 11

    # And the fixture stops consuming the 12-call/day lineup allocation.
    assert await pg.fetch("select * from due_lineup_checks(now(), 20)") == []


async def test_closing_lines_are_captured_for_every_settled_pick(pg):
    # §10: "Closing line captured for every pick."
    fixture_id, _, _ = await make_fixture(pg, kickoff_in=timedelta(hours=-3))
    await pg.execute(
        """
        insert into odds_snapshots (fixture_id, captured_at, bookmaker, market,
                                    selection, decimal_odds, window_label,
                                    is_closing)
        values ($1, now() - interval '3 hours', 'pinnacle', '1x2', 'home',
                2.05, 'lock', true)
        """,
        fixture_id,
    )
    pick_id = await pg.fetchval(
        """
        insert into picks (fixture_id, market, selection, internal_prob,
                           capture_odds, status, published_at)
        values ($1, '1x2', 'home', 0.55, 2.20, 'published', now())
        returning id
        """,
        fixture_id,
    )

    assert await pg.fetchval("select count(*) from v_missing_closing_lines") == 1
    updated = await pg.fetchval("select capture_closing_lines()")
    assert updated == 1
    assert await pg.fetchval("select count(*) from v_missing_closing_lines") == 0
    assert float(
        await pg.fetchval("select closing_odds from picks where id = $1", pick_id)
    ) == pytest.approx(2.05)


async def test_a_qa_flag_cannot_be_raised_twice_while_it_is_open(pg):
    # An unresolved-flag count that inflates with retries stops being a number
    # anyone acts on.
    fixture_id, _, _ = await make_fixture(pg, kickoff_in=timedelta(hours=2))
    for _ in range(3):
        await pg.execute(
            """
            insert into qa_flags (entity_type, entity_id, issue, detail, severity)
            values ('fixture', $1, 'score_mismatch', 'a', 'block')
            on conflict (entity_type, coalesce(entity_id::text, entity_ref), issue)
                where resolved_at is null
            do update set detail = excluded.detail
            """,
            fixture_id,
        )

    assert await pg.fetchval(
        "select count(*) from qa_flags where entity_id = $1", fixture_id
    ) == 1
