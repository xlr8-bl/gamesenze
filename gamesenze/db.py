"""Thin database access layer.

Deliberately thin. §9.3 says keep the data layer portable — plain Postgres, no
vendor extensions — so nothing here knows it is talking to Supabase, and the
rest of the package talks to the `Db` protocol rather than to asyncpg. That is
also what lets the test suite run the whole QA pipeline without a server.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

Row = dict[str, Any]

# Supabase's transaction-mode pooler listens here; session mode uses 5432 and
# holds a connection for the whole session, so prepared statements are safe.
TRANSACTION_POOLER_PORT = 6543


def uses_transaction_pooler(dsn: str) -> bool:
    """True when the DSN points at a connection pooler in transaction mode."""
    try:
        parsed = urlparse(dsn)
    except ValueError:
        return False
    if parsed.port == TRANSACTION_POOLER_PORT:
        return True
    host = (parsed.hostname or "").lower()
    return "pgbouncer" in host or "pooler" in host


@runtime_checkable
class Db(Protocol):
    async def execute(self, sql: str, *args: Any) -> str: ...

    async def fetch(self, sql: str, *args: Any) -> list[Row]: ...

    async def fetchrow(self, sql: str, *args: Any) -> Row | None: ...

    async def fetchval(self, sql: str, *args: Any) -> Any: ...


class AsyncpgDb:
    """`Db` backed by an asyncpg pool.

    asyncpg speaks `$1` placeholders and returns `Record`; both are normalised
    here so callers see plain dicts and one placeholder style.
    """

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, dsn: str, *, min_size: int = 1, max_size: int = 4):
        import asyncpg  # imported lazily so tests need no driver

        # GitHub Actions runners are IPv4-only and Supabase's direct database
        # host is IPv6-only, so in practice every connection from CI goes
        # through the pooler. Its transaction mode multiplexes one server
        # connection across clients, which breaks asyncpg's prepared-statement
        # cache with a "prepared statement already exists" error partway
        # through a job — the worst kind of failure, because it works in
        # testing and fails under concurrency.
        kwargs: dict[str, Any] = {"min_size": min_size, "max_size": max_size}
        if uses_transaction_pooler(dsn):
            kwargs["statement_cache_size"] = 0

        pool = await asyncpg.create_pool(dsn, **kwargs)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def execute(self, sql: str, *args: Any) -> str:
        async with self._pool.acquire() as conn:
            return await conn.execute(sql, *args)

    async def fetch(self, sql: str, *args: Any) -> list[Row]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, *args: Any) -> Row | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        return dict(row) if row is not None else None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, *args)


async def executemany(db: Db, sql: str, rows: Iterable[Sequence[Any]]) -> int:
    """Portable fallback for bulk insert: one statement per row.

    Our write volume is small enough (a few hundred rows a night) that the
    round trips do not matter, and this keeps `Db` to four methods.
    """
    n = 0
    for row in rows:
        await db.execute(sql, *row)
        n += 1
    return n
