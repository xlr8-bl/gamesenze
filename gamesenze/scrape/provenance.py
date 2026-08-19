"""Raw-first storage — REQ-SCRAPE-5, and the run ledger behind §8.

Store raw responses before parsing. When a site changes its HTML, the raw
archive is what lets you re-parse history instead of losing it — and §9.5 is
explicit that this is the thing that makes recovery possible at all.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from typing import Any

from ..clock import Clock, SystemClock
from ..db import Db


class RawStore:
    def __init__(self, db: Db, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def store(
        self,
        source: str,
        entity_type: str,
        payload: Any,
        *,
        entity_id: str | None = None,
        entity_ref: str | None = None,
        url: str | None = None,
        parser_version: str = "v1",
    ) -> str:
        """Archive a payload and return its content hash.

        The hash is what makes REQ-SCRAPE-3 cheap: an unchanged page has an
        unchanged hash, and season-level statistics change once a week at most.
        """
        body = json.dumps(payload, default=str, sort_keys=True)
        digest = hashlib.sha256(body.encode()).hexdigest()
        await self._db.execute(
            """
            insert into data_provenance (entity_type, entity_id, entity_ref,
                                         source, fetched_at, request_url,
                                         raw_response, parser_version,
                                         content_hash)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            entity_type,
            entity_id,
            entity_ref,
            source,
            self._clock.now(),
            url,
            body,
            parser_version,
            digest,
        )
        return digest

    async def latest(self, source: str, entity_ref: str) -> Any | None:
        """The most recently archived payload for (source, entity_ref).

        For a parser that needs to run every time a scrape job runs, not just
        when new data was fetched: REQ-SCRAPE-3 skips re-parsing on an
        unchanged fetch to save the work of re-processing identical data, but
        "identical to last time" and "already parsed into its destination
        table" are different facts. A caller whose destination table might
        still be empty (a first-ever run, or one that failed after the fetch
        but before the write) uses this to parse the archived copy instead of
        needing a fresh network call.
        """
        raw = await self._db.fetchval(
            """
            select raw_response from data_provenance
             where source = $1 and entity_ref = $2 and raw_response is not null
             order by fetched_at desc limit 1
            """,
            source,
            entity_ref,
        )
        if raw is None:
            return None
        return json.loads(raw) if isinstance(raw, str) else raw

    async def unchanged_since_last(
        self, source: str, entity_ref: str, digest: str
    ) -> bool:
        """REQ-SCRAPE-3: never re-parse what has not changed."""
        previous = await self._db.fetchval(
            """
            select content_hash from data_provenance
             where source = $1 and entity_ref = $2
             order by fetched_at desc limit 1
            """,
            source,
            entity_ref,
        )
        return previous == digest

    async def prune(self, older_than_days: int) -> int:
        """Drop raw bodies past retention, keeping the metadata row (§7).

        The row stays because "we fetched this on the 3rd and the hash was X"
        is still worth having after the body is gone, and it costs almost
        nothing against the 500MB ceiling.
        """
        return int(
            await self._db.fetchval(
                """
                with pruned as (
                    update data_provenance
                       set raw_response = null
                     where raw_response is not null
                       and fetched_at < now() - ($1 || ' days')::interval
                    returning 1
                )
                select count(*) from pruned
                """,
                str(older_than_days),
            )
            or 0
        )


class ScrapeRun:
    """Records a scrape attempt so a silent failure shows up in the audit."""

    def __init__(self, db: Db, source: str, job: str, clock: Clock | None = None):
        self._db = db
        self._source = source
        self._job = job
        self._clock = clock or SystemClock()
        self.run_id: int | None = None
        self.rows_written = 0

    async def __aenter__(self) -> ScrapeRun:
        self.run_id = int(
            await self._db.fetchval(
                "insert into scrape_runs (source, job, started_at, status) "
                "values ($1, $2, $3, 'running') returning id",
                self._source,
                self._job,
                self._clock.now(),
            )
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        status = "ok" if exc_type is None else "failed"
        await self._db.execute(
            "update scrape_runs set finished_at = $2, status = $3, "
            "rows_written = $4, error = $5 where id = $1",
            self.run_id,
            self._clock.now(),
            status,
            self.rows_written,
            None if exc is None else str(exc)[:500],
        )
        # Do not swallow: §8 says a scrape failure falls back to cached data,
        # and that decision belongs to the caller, not to this context manager.
        return False


@asynccontextmanager
async def scrape_run(db: Db, source: str, job: str, clock: Clock | None = None):
    run = ScrapeRun(db, source, job, clock)
    await run.__aenter__()
    try:
        yield run
    except BaseException as exc:
        await run.__aexit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        await run.__aexit__(None, None, None)
