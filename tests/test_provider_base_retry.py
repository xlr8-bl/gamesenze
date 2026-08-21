"""providers/base.py's MeteredClient — the provenance-write retry.

Seen live: odds_sync crashed outright with an uncaught TimeoutError from
_store_provenance() — a write path that had no retry at all, unlike the
odds_snapshots insert fixed earlier. Safe to retry here in a way the
odds_snapshots write was not: data_provenance is an append-only audit
archive (REQ-SCRAPE-5), so a duplicate row from a retry is a harmless extra
log entry, not corrupted pricing data — no on-conflict clause needed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg
import pytest

from gamesenze.providers.base import MeteredClient, Response


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


class _FakeMeter:
    async def reserve(self, provider, endpoint, *, cost=1, job=None):
        return None

    async def record_status_code(self, provider, status_code):
        return None


class _FakeClock:
    def now(self):
        return datetime(2026, 8, 19, tzinfo=UTC)


RESPONSE = Response(200, {"ok": True}, "https://example.test/thing")


async def test_a_dropped_connection_on_the_provenance_write_is_retried_once(
    monkeypatch,
):
    monkeypatch.setattr("gamesenze.providers.base.asyncio.sleep", _no_sleep)
    db = _FailOnceDb(asyncpg.exceptions.ConnectionDoesNotExistError("gone"))
    client = MeteredClient(
        "test", "https://example.test", db=db, meter=_FakeMeter(), clock=_FakeClock()
    )

    await client._store_provenance(RESPONSE, "api", None, "ref")

    assert db.calls == 2


async def test_a_second_consecutive_failure_is_a_real_outage_not_swallowed(
    monkeypatch,
):
    monkeypatch.setattr("gamesenze.providers.base.asyncio.sleep", _no_sleep)
    client = MeteredClient(
        "test",
        "https://example.test",
        db=_AlwaysFailDb(),
        meter=_FakeMeter(),
        clock=_FakeClock(),
    )

    with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
        await client._store_provenance(RESPONSE, "api", None, "ref")


async def test_a_timeout_on_the_provenance_write_is_also_retried(monkeypatch):
    """AsyncpgDb's command_timeout turns a hung connection into a prompt
    TimeoutError — this must be caught here too, or the timeout just fails
    fast without actually recovering."""
    monkeypatch.setattr("gamesenze.providers.base.asyncio.sleep", _no_sleep)
    db = _FailOnceDb(TimeoutError("command timed out"))
    client = MeteredClient(
        "test", "https://example.test", db=db, meter=_FakeMeter(), clock=_FakeClock()
    )

    await client._store_provenance(RESPONSE, "api", None, "ref")

    assert db.calls == 2


async def _no_sleep(*args, **kwargs) -> None:
    return None
