"""The database and the Python must agree.

Two pieces of logic exist twice: the §3.4 snapshot cadence (Python for the
planner and the fallback job, SQL for what the Worker asks) and the §5.1/§5.3
odds rules (Python for the fallback path, SQL for the Worker's ingest trigger).

Duplication is deliberate — the Worker cannot run Python, and the fallback job
cannot run inside Postgres — so these tests are what keep the copies honest. If
one is changed without the other, this file fails.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from pitchside.odds.schedule import PLANNED_SNAPSHOTS_PER_FIXTURE, plan_snapshots
from pitchside.providers.sgo import parse_odds
from tests.conftest import requires_pg

pytestmark = requires_pg

KICKOFF = datetime(2026, 8, 20, 19, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("thinning", "closing_only"),
    [(1, False), (2, False), (1, True), (2, True)],
)
async def test_cadence_matches_between_sql_and_python(pg, thinning, closing_only):
    rows = await pg.fetch(
        "select at, label from snapshot_plan($1, $2, $3) order by at",
        KICKOFF,
        thinning,
        closing_only,
    )
    sql_plan = [(r["at"], r["label"]) for r in rows]
    python_plan = plan_snapshots(
        KICKOFF, thinning_factor=thinning, closing_only=closing_only
    )
    assert sql_plan == python_plan


async def test_the_full_plan_is_the_sixteen_objects_budgeted(pg):
    n = await pg.fetchval(
        "select count(*) from snapshot_plan($1, 1, false)", KICKOFF
    )
    assert n == PLANNED_SNAPSHOTS_PER_FIXTURE == 16


async def test_the_lock_capture_survives_every_degradation_rung(pg):
    # REQ-QA-5 has nothing to measure against without it.
    for thinning, closing_only in [(1, False), (2, False), (2, True)]:
        labels = await pg.fetch(
            "select label from snapshot_plan($1, $2, $3)",
            KICKOFF,
            thinning,
            closing_only,
        )
        assert "lock" in {r["label"] for r in labels}


PAYLOAD = {
    "bookmakers": [
        {
            "key": "pinnacle",
            "markets": [
                {
                    "key": "1x2",
                    "outcomes": [
                        {"name": "home", "price": 2.10},
                        {"name": "draw", "price": 3.40},
                        {"name": "away", "price": 3.60},
                        {"name": "too_short", "price": 1.001},
                        {"name": "missing", "price": None},
                        {"name": "too_long", "price": 500},
                    ],
                }
            ],
        }
    ]
}


async def _fixture_id(pg) -> str:
    home = await pg.fetchval(
        "insert into teams (sport, canonical_name) values ('football', $1) "
        "returning id",
        "Parity Home",
    )
    away = await pg.fetchval(
        "insert into teams (sport, canonical_name) values ('football', $1) "
        "returning id",
        "Parity Away",
    )
    return await pg.fetchval(
        """
        insert into fixtures (sport, home_team_id, away_team_id, kickoff_at,
                              covered, covered_at)
        values ('football', $1, $2, now() + interval '2 hours', true, now())
        returning id
        """,
        home,
        away,
    )


async def test_ingest_trigger_accepts_and_rejects_exactly_what_python_does(pg):
    fixture_id = await _fixture_id(pg)

    await pg.execute(
        "insert into odds_ingest_queue (fixture_id, window_label, payload) "
        "values ($1, 'lock', $2)",
        fixture_id,
        json.dumps(PAYLOAD),
    )

    queued = await pg.fetchrow(
        "select rows_written, rejections from odds_ingest_queue "
        "where fixture_id = $1",
        fixture_id,
    )
    stored = await pg.fetch(
        "select selection, decimal_odds, is_closing from odds_snapshots "
        "where fixture_id = $1 order by selection",
        fixture_id,
    )

    python_rows, python_rejections = parse_odds(
        PAYLOAD, captured_at=datetime.now(UTC), window_label="lock"
    )

    assert queued["rows_written"] == len(python_rows) == 3
    assert len(queued["rejections"]) == len(python_rejections) == 3

    assert [r["selection"] for r in stored] == sorted(
        r["selection"] for r in python_rows
    )
    # A lock capture is the closing line on both paths.
    assert all(r["is_closing"] for r in stored)
    assert all(r["is_closing"] for r in python_rows)


async def test_both_paths_reject_the_same_three_prices(pg):
    fixture_id = await _fixture_id(pg)
    await pg.execute(
        "insert into odds_ingest_queue (fixture_id, window_label, payload) "
        "values ($1, 'lock', $2)",
        fixture_id,
        json.dumps(PAYLOAD),
    )
    rejections = await pg.fetchval(
        "select rejections from odds_ingest_queue where fixture_id = $1", fixture_id
    )
    _, python_rejections = parse_odds(
        PAYLOAD, captured_at=datetime.now(UTC), window_label="lock"
    )

    def selections(items):
        return sorted(item.split("/")[2].split(":")[0] for item in items)

    assert selections(rejections) == selections(python_rejections)
    assert selections(rejections) == ["missing", "too_long", "too_short"]


async def test_an_empty_payload_raises_a_flag_rather_than_passing_quietly(pg):
    fixture_id = await _fixture_id(pg)
    await pg.execute(
        "insert into odds_ingest_queue (fixture_id, window_label, payload) "
        "values ($1, 't3_t1', '{\"bookmakers\": []}'::jsonb)",
        fixture_id,
    )
    flag = await pg.fetchrow(
        "select issue, severity from qa_flags where entity_id = $1", fixture_id
    )
    assert flag["issue"] == "empty_odds_payload"
    assert flag["severity"] == "review"
