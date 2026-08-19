"""odds_sync's write-side retry — no real Postgres needed.

This exercises the actual failure seen live: a pooled connection dropping
mid-write (asyncpg.ConnectionDoesNotExistError) after several successful
vendor calls already did the expensive part of the job. The retry in
gamesenze/jobs/odds_sync.py's _insert_odds_snapshots is only safe because the
insert carries `on conflict ... do nothing` (see db/migrations/
0010_odds_snapshots_unique.sql) — this test pins that it actually retries,
and a companion in test_jobs_odds_sync.py (real Postgres) pins that a
resubmitted batch does not duplicate rows.
"""

from __future__ import annotations

from types import SimpleNamespace

import asyncpg
import pytest

from gamesenze.jobs.odds_sync import _insert_odds_snapshots

EMPTY_COLUMNS = ([], [], [], [], [], [], [], [])


class _FailOnceDb:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    async def execute(self, sql: str, *args):
        self.calls += 1
        if self.calls == 1:
            raise self._error
        return "OK"


class _AlwaysFailDb:
    async def execute(self, sql: str, *args):
        raise asyncpg.exceptions.ConnectionDoesNotExistError("still gone")


async def test_a_dropped_connection_on_first_attempt_is_retried_once(monkeypatch):
    monkeypatch.setattr("gamesenze.jobs.odds_sync.asyncio.sleep", _no_sleep)
    db = _FailOnceDb(asyncpg.exceptions.ConnectionDoesNotExistError("gone"))
    ctx = SimpleNamespace(db=db)

    await _insert_odds_snapshots(ctx, *EMPTY_COLUMNS)

    assert db.calls == 2


async def test_a_second_consecutive_failure_is_a_real_outage_not_swallowed(monkeypatch):
    monkeypatch.setattr("gamesenze.jobs.odds_sync.asyncio.sleep", _no_sleep)
    ctx = SimpleNamespace(db=_AlwaysFailDb())

    with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
        await _insert_odds_snapshots(ctx, *EMPTY_COLUMNS)


async def _no_sleep(*args, **kwargs) -> None:
    return None
