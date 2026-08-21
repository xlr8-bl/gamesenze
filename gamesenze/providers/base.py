"""Metered HTTP client.

Two things happen around every vendor request, and the client owns both so a
caller cannot forget either:

1. Budget is reserved *before* the call (REQ-BUDGET-3). A call made and then
   counted is a call that vanishes if the process dies mid-request, leaving us
   believing we have room we do not.
2. The raw response is stored *before* parsing (REQ-SCRAPE-5). When a vendor
   changes its shape, the archive is what lets us re-parse history instead of
   losing it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..budget import BudgetMeter
from ..clock import Clock, SystemClock
from ..db import Db


@dataclass(frozen=True)
class Response:
    status_code: int
    body: Any
    url: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class Transport(Protocol):
    async def get(
        self, url: str, *, params: dict[str, Any] | None, headers: dict[str, str]
    ) -> Response: ...


class HttpxTransport:
    """Default transport. httpx is imported lazily so tests need no network stack."""

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    async def get(
        self, url: str, *, params: dict[str, Any] | None, headers: dict[str, str]
    ) -> Response:
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url, params=params, headers=headers)
        try:
            body = r.json()
        except ValueError:
            body = r.text
        return Response(r.status_code, body, str(r.url), dict(r.headers))


class ProviderError(RuntimeError):
    def __init__(self, provider: str, response: Response) -> None:
        super().__init__(
            f"{provider} returned {response.status_code} for {response.url}"
        )
        self.provider = provider
        self.response = response


class MeteredClient:
    def __init__(
        self,
        provider: str,
        base_url: str,
        *,
        db: Db,
        meter: BudgetMeter,
        transport: Transport | None = None,
        headers: dict[str, str] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.provider = provider
        self._base_url = base_url.rstrip("/")
        self._db = db
        self._meter = meter
        self._transport = transport or HttpxTransport()
        self._headers = headers or {}
        self._clock = clock or SystemClock()

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        cost: int = 1,
        job: str | None = None,
        entity_type: str = "api",
        entity_id: str | None = None,
        entity_ref: str | None = None,
        store_raw: bool = True,
    ) -> Response:
        """Reserve budget, call, archive. Raises `BudgetExhausted` before calling."""
        endpoint = path.lstrip("/")
        await self._meter.reserve(self.provider, endpoint, cost=cost, job=job)

        url = f"{self._base_url}/{endpoint}"
        response = await self._transport.get(
            url, params=params, headers=self._headers
        )
        await self._meter.record_status_code(self.provider, response.status_code)

        if store_raw:
            await self._store_provenance(
                response, entity_type, entity_id, entity_ref or endpoint
            )

        if not response.ok:
            raise ProviderError(self.provider, response)
        return response

    async def _store_provenance(
        self,
        response: Response,
        entity_type: str,
        entity_id: str | None,
        entity_ref: str,
    ) -> None:
        payload = json.dumps(response.body, default=str)
        args = (
            entity_type,
            entity_id,
            entity_ref,
            self.provider,
            self._clock.now(),
            response.url,
            payload,
            "v1",
            hashlib.sha256(payload.encode()).hexdigest(),
        )
        sql = """
            insert into data_provenance (entity_type, entity_id, entity_ref,
                                         source, fetched_at, request_url,
                                         raw_response, parser_version,
                                         content_hash)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """
        # Retried once on a dropped connection — seen live, and safe here
        # unlike a pricing write: data_provenance is an append-only audit
        # archive (REQ-SCRAPE-5), so a duplicate row from a retry is a
        # harmless extra log entry, not corrupted decision data.
        import asyncpg  # imported lazily so tests need no driver

        try:
            await self._db.execute(sql, *args)
        except (
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            TimeoutError,
            OSError,
        ):
            await asyncio.sleep(1.0)
            await self._db.execute(sql, *args)
