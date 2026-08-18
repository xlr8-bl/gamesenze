"""Coverage admission — §3.3.

A fixture becomes covered only if its *entire* snapshot plan fits in what is
left of the month. Admitting a fixture we can only half-cover is worse than
declining it: we spend twelve objects and still cannot publish, because the
closing line never gets captured and REQ-QA-5 has nothing to measure against.

The 100 football / 50 NBA caps are a product constraint as much as a technical
one — roughly four football picks and two NBA picks a day, which is the curated
volume the product calls for anyway. The budget and the editorial strategy
agree, so enforcing one enforces the other.
"""

from __future__ import annotations

from dataclasses import dataclass

from .budget import BudgetMeter
from .config import (
    MONTHLY_FOOTBALL_FIXTURE_CAP,
    MONTHLY_NBA_GAME_CAP,
    SNAPSHOTS_PER_FIXTURE,
    SNAPSHOTS_PER_NBA_GAME,
)
from .db import Db
from .degrade import Policy


@dataclass(frozen=True)
class CoverageDecision:
    admitted: bool
    reason: str
    objects_required: int
    objects_remaining: int


class CoverageController:
    def __init__(self, db: Db, meter: BudgetMeter) -> None:
        self._db = db
        self._meter = meter

    async def counts_this_month(self, period: str) -> tuple[int, int]:
        football = int(
            await self._db.fetchval(
                "select count(*) from fixtures where covered and sport = 'football' "
                "and to_char(covered_at, 'YYYY-MM') = $1",
                period,
            )
            or 0
        )
        nba = int(
            await self._db.fetchval(
                "select count(*) from fixtures where covered and sport = 'basketball' "
                "and to_char(covered_at, 'YYYY-MM') = $1",
                period,
            )
            or 0
        )
        return football, nba

    async def can_cover(
        self, sport: str, *, policy: Policy | None = None
    ) -> CoverageDecision:
        status = await self._meter.status("sportsgameodds")
        football, nba = await self.counts_this_month(status.period)

        if sport == "football":
            required = SNAPSHOTS_PER_FIXTURE
            used, cap, label = football, MONTHLY_FOOTBALL_FIXTURE_CAP, "football fixture"
        elif sport == "basketball":
            required = SNAPSHOTS_PER_NBA_GAME
            used, cap, label = nba, MONTHLY_NBA_GAME_CAP, "NBA game"
        else:
            return CoverageDecision(False, f"unknown sport {sport!r}", 0, 0)

        # A degraded plan costs fewer objects, so admission uses the plan we
        # would actually run rather than the full-price one.
        if policy is not None:
            required = min(required, policy.snapshots_per_fixture or required)

        remaining = status.remaining
        if used >= cap:
            return CoverageDecision(
                False,
                f"monthly {label} cap reached ({used}/{cap})",
                required,
                remaining,
            )
        if required > remaining:
            return CoverageDecision(
                False,
                f"only {remaining} objects left this month, plan needs {required}",
                required,
                remaining,
            )
        return CoverageDecision(
            True, f"{used + 1}/{cap} {label}s this month", required, remaining
        )

    async def mark_covered(self, fixture_id: str, covered_at) -> None:
        await self._db.execute(
            "update fixtures set covered = true, covered_at = $2, updated_at = $2 "
            "where id = $1 and not covered",
            fixture_id,
            covered_at,
        )
