"""Thin database access layer.

Deliberately thin. §9.3 says keep the data layer portable — plain Postgres, no
vendor extensions — so nothing here knows it is talking to Supabase, and the
rest of the package talks to the `Db` protocol rather than to asyncpg. That is
also what lets the test suite run the whole QA pipeline without a server.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any, Protocol, TypeVar, runtime_checkable
from urllib.parse import urlparse

T = TypeVar("T")

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
    async def connect(
        cls,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 4,
        command_timeout: float = 30.0,
    ):
        import asyncpg  # imported lazily so tests need no driver
        import socket
        from urllib.parse import urlsplit

        # Fail early and legibly on the two mistakes that otherwise surface as
        # a 40-line asyncpg traceback ending in "getaddrinfo failed": a
        # DATABASE_URL still holding the .env placeholders, or the direct
        # (IPv6-only) host in place of the pooler.
        if not dsn or "<" in dsn or ">" in dsn:
            raise SystemExit(
                "DATABASE_URL is empty or still has the .env placeholders "
                "(the <...> parts).\n"
                "Edit your .env and paste the Supabase SESSION POOLER URI:\n"
                "  postgresql://postgres.<ref>:<password>"
                "@aws-0-<region>.pooler.supabase.com:5432/postgres\n"
                "The username is postgres.<ref>, not plain postgres. "
                "See docs/SETUP.md section 1."
            )

        # GitHub Actions runners are IPv4-only and Supabase's direct database
        # host is IPv6-only, so in practice every connection from CI goes
        # through the pooler. Its transaction mode multiplexes one server
        # connection across clients, which breaks asyncpg's prepared-statement
        # cache with a "prepared statement already exists" error partway
        # through a job — the worst kind of failure, because it works in
        # testing and fails under concurrency.
        kwargs: dict[str, Any] = {
            "min_size": min_size,
            "max_size": max_size,
            # Without this, a connection that dies silently on the client
            # side (network drop, laptop sleep) leaves a query waiting on
            # the OS to eventually notice, which can take minutes — seen
            # live as a job appearing to hang before finally erroring. This
            # caps that wait so the retry in execute()/_read() kicks in
            # quickly instead of the whole job looking frozen.
            "command_timeout": command_timeout,
        }
        if uses_transaction_pooler(dsn):
            kwargs["statement_cache_size"] = 0

        try:
            pool = await asyncpg.create_pool(dsn, **kwargs)
        except (socket.gaierror, OSError) as exc:
            host = urlsplit(dsn).hostname or "?"
            hint = ""
            if host.startswith("db.") and host.endswith(".supabase.co"):
                hint = (
                    "\nThat host is the DIRECT connection, which is IPv6-only "
                    "and usually cannot be resolved. Use the Session pooler URI "
                    "instead (host aws-0-<region>.pooler.supabase.com, user "
                    "postgres.<ref>, port 5432)."
                )
            raise SystemExit(
                f"Could not reach the database host '{host}': {exc}."
                f"{hint}\n"
                "Check DATABASE_URL in .env, then test it directly:\n"
                '  psql "$DATABASE_URL" -c "select version();"\n'
                "See docs/SETUP.md section 1."
            ) from None
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def _read(self, fn: Callable[[Any], Awaitable[T]]) -> T:
        """Acquire a connection, run a read, retry once on a dropped one.

        A pooled connection can go stale between the pool handing it out and
        the query actually running — a network blip on the client side, or
        Supabase's pooler recycling it — and asyncpg surfaces that as a
        connection error on the query itself, not on acquire(). Seen live on
        a flaky Windows connection: a dead connection that hung for minutes
        before the OS finally noticed, which `command_timeout` above turns
        into a prompt `TimeoutError` instead — caught here for the same
        reason. Reads are always safe to retry: there is no side effect to
        duplicate. Writes are not (see execute() below), so this retry
        deliberately does not cover them.
        """
        import asyncpg

        try:
            async with self._pool.acquire() as conn:
                return await fn(conn)
        except (
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            TimeoutError,
            OSError,
        ):
            await asyncio.sleep(1.0)
            async with self._pool.acquire() as conn:
                return await fn(conn)

    async def execute(self, sql: str, *args: Any) -> str:
        # No automatic retry here: if the connection drops after the command
        # reached the server but before its acknowledgement reached us, the
        # write may already be committed, and blindly resending it would
        # silently duplicate data — exactly what this codebase's alias and
        # fixture-resolution discipline exists to prevent elsewhere. A
        # write-side retry is safe only where the statement itself is
        # idempotent (an upsert, an `on conflict do nothing`); that is a
        # decision for the caller to make, not this generic layer.
        async with self._pool.acquire() as conn:
            return await conn.execute(sql, *args)

    async def fetch(self, sql: str, *args: Any) -> list[Row]:
        rows = await self._read(lambda conn: conn.fetch(sql, *args))
        return [dict(r) for r in rows]

    async def fetchrow(self, sql: str, *args: Any) -> Row | None:
        row = await self._read(lambda conn: conn.fetchrow(sql, *args))
        return dict(row) if row is not None else None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return await self._read(lambda conn: conn.fetchval(sql, *args))


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
