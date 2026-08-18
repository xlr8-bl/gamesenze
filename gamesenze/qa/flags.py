"""Raising and resolving QA flags.

One open flag per (entity, issue) — the unique index in 0002_qa.sql enforces
it. Re-raising an existing problem bumps its detail rather than adding a row,
because an unresolved-flag count that inflates with retries stops being a
number anyone acts on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..clock import Clock, SystemClock
from ..db import Db
from .errors import Severity


@dataclass(frozen=True)
class QAFlag:
    entity_type: str
    entity_id: str | None
    entity_ref: str | None
    issue: str
    detail: str
    severity: Severity
    raised_at: datetime


class FlagStore:
    def __init__(self, db: Db, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def raise_flag(
        self,
        entity_type: str,
        entity_id: str | None,
        issue: str,
        detail: str = "",
        severity: Severity | str = Severity.BLOCK,
        *,
        entity_ref: str | None = None,
    ) -> QAFlag:
        now = self._clock.now()
        sev = Severity(severity)
        await self._db.execute(
            """
            insert into qa_flags (entity_type, entity_id, entity_ref, issue,
                                  detail, severity, raised_at)
            values ($1, $2, $3, $4, $5, $6, $7)
            on conflict (entity_type, coalesce(entity_id::text, entity_ref), issue)
                where resolved_at is null
            do update set detail = excluded.detail,
                          severity = excluded.severity
            """,
            entity_type,
            entity_id,
            entity_ref,
            issue,
            detail,
            sev.value,
            now,
        )
        return QAFlag(entity_type, entity_id, entity_ref, issue, detail, sev, now)

    async def resolve(
        self, flag_id: int, resolved_by: str, note: str = ""
    ) -> None:
        await self._db.execute(
            """
            update qa_flags
               set resolved_at = $2, resolved_by = $3, resolution_note = $4
             where id = $1 and resolved_at is null
            """,
            flag_id,
            self._clock.now(),
            resolved_by,
            note,
        )

    async def open_flags(
        self, entity_type: str, entity_id: str, severity: str | None = None
    ) -> list[dict[str, Any]]:
        if severity:
            return await self._db.fetch(
                """
                select * from qa_flags
                 where entity_type = $1 and entity_id = $2
                   and severity = $3 and resolved_at is null
                """,
                entity_type,
                entity_id,
                severity,
            )
        return await self._db.fetch(
            """
            select * from qa_flags
             where entity_type = $1 and entity_id = $2 and resolved_at is null
            """,
            entity_type,
            entity_id,
        )

    async def blocking_flags(self, entity_type: str, entity_id: str) -> list[dict]:
        return await self.open_flags(entity_type, entity_id, Severity.BLOCK.value)

    async def unresolved_count(self, severity: str | None = None) -> int:
        if severity:
            return int(
                await self._db.fetchval(
                    "select count(*) from qa_flags "
                    "where resolved_at is null and severity = $1",
                    severity,
                )
                or 0
            )
        return int(
            await self._db.fetchval(
                "select count(*) from qa_flags where resolved_at is null"
            )
            or 0
        )
