"""Thin database access layer.

Deliberately thin. §9.3 says keep the data layer portable — plain Postgres, no
vendor extensions — so nothing here knows it is talking to Supabase, and the
rest of the package talks to the `Db` protocol rather than to asyncpg. That is
also what lets the test suite run the whole QA pipeline without a server.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Protocol, runtime_checkable

Row = dict[str, Any]


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

        pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size)
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
