"""§10 track record read models (migration 0011).

The gate these views enforce is the whole point of the record page: below the
sample floor the percentages are withheld, not zeroed. That rule lives in SQL
rather than in the browser, because a rule enforced in the browser is a rule
someone can turn off, so it is tested against a real server.
"""

from __future__ import annotations

from tests.conftest import requires_pg


async def _fixture(pg) -> str:
    comp = await pg.fetchval(
        "insert into competitions (sport, name) values ('football', 'Test League') "
        "returning id"
    )
    home = await pg.fetchval(
        "insert into teams (sport, canonical_name) values ('football', 'Home FC') "
        "returning id"
    )
    away = await pg.fetchval(
        "insert into teams (sport, canonical_name) values ('football', 'Away FC') "
        "returning id"
    )
    return await pg.fetchval(
        "insert into fixtures (sport, competition_id, home_team_id, away_team_id, "
        "kickoff_at, status) values ('football', $1, $2, $3, now() - interval '2 days', "
        "'finished') returning id",
        comp,
        home,
        away,
    )


async def _settle(pg, fixture, n, *, capture=2.0, closing=2.0, result="won"):
    await pg.execute(
        """
        insert into picks (fixture_id, market, selection, capture_odds, closing_odds,
                           status, result, settled_at)
        select $1, 'h2h', 'sel' || g, $2, $3, 'settled', $4, now()
          from generate_series(1, $5) g
        """,
        fixture,
        capture,
        closing,
        result,
        n,
    )


@requires_pg
async def test_an_open_pick_is_not_a_result(pg):
    fixture = await _fixture(pg)
    await pg.execute(
        "insert into picks (fixture_id, market, selection, capture_odds, status) "
        "values ($1, 'h2h', 'home', 2.0, 'published')",
        fixture,
    )
    assert await pg.fetchval("select count(*) from v_pick_record") == 0


@requires_pg
async def test_clv_is_positive_when_we_beat_the_close(pg):
    fixture = await _fixture(pg)
    # Published at 2.50, market closed at 2.20: the market moved toward us.
    await _settle(pg, fixture, 1, capture=2.50, closing=2.20)
    row = await pg.fetchrow("select clv_pct, unit_return from v_pick_record")
    assert float(row["clv_pct"]) == 13.64
    assert float(row["unit_return"]) == 1.5


@requires_pg
async def test_clv_is_null_rather_than_zero_without_a_closing_line(pg):
    """A missing closing line is a gap in what we know. Reporting it as 0.00
    would put it in the average as a neutral observation, which is a claim we
    have no evidence for."""
    fixture = await _fixture(pg)
    await pg.execute(
        "insert into picks (fixture_id, market, selection, capture_odds, status, "
        "result, settled_at) values ($1, 'h2h', 'home', 2.0, 'settled', 'won', now())",
        fixture,
    )
    assert await pg.fetchval("select clv_pct from v_pick_record") is None


@requires_pg
async def test_a_push_costs_and_returns_nothing(pg):
    fixture = await _fixture(pg)
    await _settle(pg, fixture, 1, result="push")
    assert float(await pg.fetchval("select unit_return from v_pick_record")) == 0.0


@requires_pg
async def test_rates_are_withheld_below_the_sample_floor(pg):
    fixture = await _fixture(pg)
    floor = await pg.fetchval("select record_sample_floor()")
    await _settle(pg, fixture, floor - 1)

    row = await pg.fetchrow("select * from v_record_summary where sport = 'all'")

    assert row["settled"] == floor - 1
    assert row["rates_published"] is False
    # Counts are real and complete; every rate is withheld, not zeroed.
    assert row["hit_rate_pct"] is None
    assert row["roi_pct"] is None
    assert row["avg_clv_pct"] is None
    assert float(row["units"]) > 0


@requires_pg
async def test_rates_appear_once_the_sample_reaches_the_floor(pg):
    fixture = await _fixture(pg)
    floor = await pg.fetchval("select record_sample_floor()")
    await _settle(pg, fixture, floor)

    row = await pg.fetchrow("select * from v_record_summary where sport = 'all'")

    assert row["rates_published"] is True
    assert float(row["hit_rate_pct"]) == 100.0


@requires_pg
async def test_pushes_leave_the_hit_rate_denominator(pg):
    """A void bet is not a loss. Counting it against the hit rate would make a
    postponed fixture look like a bad call."""
    fixture = await _fixture(pg)
    floor = await pg.fetchval("select record_sample_floor()")
    await _settle(pg, fixture, floor, result="won")
    await _settle(pg, fixture, 10, result="push")

    row = await pg.fetchrow("select * from v_record_summary where sport = 'all'")

    assert row["settled"] == floor + 10
    assert row["pushed"] == 10
    assert float(row["hit_rate_pct"]) == 100.0


@requires_pg
async def test_clv_keeps_its_own_sample_gate(pg):
    """A pick can settle without a closing line ever being captured, so the CLV
    average reaches the floor later than the win rate does. It is gated on its
    own count rather than riding on the settled count."""
    fixture = await _fixture(pg)
    floor = await pg.fetchval("select record_sample_floor()")
    await pg.execute(
        """
        insert into picks (fixture_id, market, selection, capture_odds,
                           status, result, settled_at)
        select $1, 'h2h', 'sel' || g, 2.0, 'settled', 'won', now()
          from generate_series(1, $2) g
        """,
        fixture,
        floor,
    )

    row = await pg.fetchrow("select * from v_record_summary where sport = 'all'")

    assert row["rates_published"] is True
    assert float(row["hit_rate_pct"]) == 100.0
    assert row["clv_sample"] == 0
    assert row["avg_clv_pct"] is None


@requires_pg
async def test_the_summary_carries_an_all_row_beside_each_sport(pg):
    fixture = await _fixture(pg)
    await _settle(pg, fixture, 3)
    sports = [r["sport"] for r in await pg.fetch("select sport from v_record_summary")]
    assert sorted(sports) == ["all", "football"]
