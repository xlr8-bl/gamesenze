"""Real-Postgres tests for jobs/seed.py's batching and
jobs/cleanup_corrupted_encoding.py.

Both bugs here were only visible against a real server: the seed job's
row-at-a-time loop is indistinguishable from a batched one against `FakeDb`
(both just record statements), and the cleanup job's original regex
(`'Ã[€-ÿ]'`) is syntactically valid Python but an invalid Postgres regular
expression — `€` is U+20AC, past `ÿ` at U+00FF, so the character range is
reversed and Postgres rejects it outright.
"""

from __future__ import annotations

from gamesenze.jobs import cleanup_corrupted_encoding, seed
from tests.conftest import requires_pg

pytestmark = requires_pg


async def test_seed_batches_into_a_handful_of_statements_not_one_per_row(job_ctx, pg):
    await seed.main(job_ctx)

    teams = await pg.fetchval("select count(*) from teams")
    aliases = await pg.fetchval("select count(*) from team_aliases")
    assert teams > 100
    assert aliases > 1000

    # The specific bug: a name misread on Windows would have landed as
    # "MÃ¡laga" instead of "Málaga". Confirms the batched insert round-trips
    # accented characters correctly through unnest().
    malaga = await pg.fetchval(
        "select canonical_name from teams where canonical_name = 'Málaga'"
    )
    assert malaga == "Málaga"


async def test_seed_is_idempotent(job_ctx, pg):
    await seed.main(job_ctx)
    first_teams = await pg.fetchval("select count(*) from teams")
    first_aliases = await pg.fetchval("select count(*) from team_aliases")

    await seed.main(job_ctx)
    second_teams = await pg.fetchval("select count(*) from teams")
    second_aliases = await pg.fetchval("select count(*) from team_aliases")

    assert second_teams == first_teams
    assert second_aliases == first_aliases


async def test_cleanup_finds_nothing_when_nothing_is_corrupted(job_ctx, capsys):
    result = await cleanup_corrupted_encoding.main(job_ctx)
    assert result == 0
    assert "nothing to clean up" in capsys.readouterr().out


async def test_cleanup_dry_run_reports_but_does_not_delete(job_ctx, pg, capsys):
    await pg.execute(
        "insert into teams (sport, canonical_name, country) "
        "values ('football', 'FamalicÃ£o', 'Portugal')"
    )

    result = await cleanup_corrupted_encoding.main(job_ctx)

    assert result == 0
    out = capsys.readouterr().out
    assert "safe to delete" in out
    assert "DRY RUN" in out
    still_there = await pg.fetchval(
        "select count(*) from teams where canonical_name = 'FamalicÃ£o'"
    )
    assert still_there == 1


async def test_cleanup_confirm_deletes_safe_rows_but_blocks_referenced_ones(
    job_ctx, pg, capsys, monkeypatch
):
    monkeypatch.setattr("sys.argv", ["cleanup_corrupted_encoding", "--confirm"])

    safe_id = await pg.fetchval(
        "insert into teams (sport, canonical_name, country) "
        "values ('football', 'FamalicÃ£o', 'Portugal') returning id"
    )
    blocked_id = await pg.fetchval(
        "insert into teams (sport, canonical_name, country) "
        "values ('football', 'MÃ¡laga', 'Spain') returning id"
    )
    await pg.execute(
        "insert into fixtures (sport, home_team_id, kickoff_at) "
        "values ('football', $1, now())",
        blocked_id,
    )

    result = await cleanup_corrupted_encoding.main(job_ctx)

    assert result == 0
    out = capsys.readouterr().out
    assert "deleted 1 corrupted row(s), 1 skipped" in out

    remaining = await pg.fetch(
        "select id, canonical_name from teams where canonical_name like '%Ã%'"
    )
    assert [r["id"] for r in remaining] == [blocked_id]
    assert await pg.fetchval("select count(*) from teams where id = $1", safe_id) == 0


async def test_cleanup_never_flags_a_legitimate_accented_name(job_ctx, pg):
    await pg.execute(
        "insert into teams (sport, canonical_name, country) "
        "values ('football', 'Águia Real', 'Spain')"
    )

    corrupted = await cleanup_corrupted_encoding.find_corrupted(job_ctx)

    assert corrupted == []
