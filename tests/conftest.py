"""Test fixtures.

Two kinds of database here. `FakeDb` is a scripted stand-in that records what
was written and returns canned reads — enough to test the control flow of the
QA layers without a server. The `pg` fixture is a real Postgres, used for the
things that only exist in SQL: the cadence function, the ingest triggers and
the degradation ladder view.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

import pytest

from gamesenze.clock import FrozenClock

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


class FakeDb:
    """Records writes; answers reads from scripted responses.

    Responses are keyed by a substring of the SQL. The first key that appears
    in the statement wins, so a test can script `"count(*) from qa_flags"`
    without reproducing the whole query.
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def _norm(self, sql: str) -> str:
        return re.sub(r"\s+", " ", sql).strip()

    def _lookup(self, sql: str, default: Any = None) -> Any:
        flat = self._norm(sql)
        for key, value in self.responses.items():
            if self._norm(key) in flat:
                return value
        return default

    async def execute(self, sql: str, *args: Any) -> str:
        self.statements.append((self._norm(sql), args))
        return "OK"

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.statements.append((self._norm(sql), args))
        return self._lookup(sql, []) or []

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        self.statements.append((self._norm(sql), args))
        rows = self._lookup(sql)
        if isinstance(rows, list):
            return rows[0] if rows else None
        return rows

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.statements.append((self._norm(sql), args))
        return self._lookup(sql)

    # --- assertions helpers -------------------------------------------------
    def wrote(self, fragment: str) -> bool:
        needle = self._norm(fragment)
        return any(needle in sql for sql, _ in self.statements)

    def writes_matching(self, fragment: str) -> list[tuple[str, tuple]]:
        needle = self._norm(fragment)
        return [(s, a) for s, a in self.statements if needle in s]


@pytest.fixture
def fake_db() -> FakeDb:
    return FakeDb()


# --- real Postgres ----------------------------------------------------------

def _dsn() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


requires_pg = pytest.mark.skipif(
    _dsn() is None,
    reason="TEST_DATABASE_URL is not set; SQL-level tests need a real Postgres",
)


@pytest.fixture
async def pg():
    """A connection to a migrated test database, rolled back after each test."""
    import asyncpg

    dsn = _dsn()
    if dsn is None:
        pytest.skip("TEST_DATABASE_URL is not set")

    conn = await asyncpg.connect(dsn)
    tx = conn.transaction()
    await tx.start()
    try:
        yield conn
    finally:
        await tx.rollback()
        await conn.close()
