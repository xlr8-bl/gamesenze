"""Layer 5 — the pre-publication gate (§5.5).

No pick publishes without passing every check. The gate returns nothing on
failure and writes the reason to `publication_blocks`: silence is the safe
state, but it is never a silent one — a blocked pick that nobody can explain
tomorrow morning is its own failure.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..clock import Clock, SystemClock
from ..db import Db


@dataclass
class PublicationContext:
    """Everything the gate needs, assembled by the caller before it runs."""

    fixture_id: str
    pick_id: str | None = None
    blocking_flags: Sequence[object] = field(default_factory=list)
    odds_age_minutes: float | None = None
    home_id: str | None = None
    away_id: str | None = None
    valid_factors: Sequence[str] = field(default_factory=list)
    internal_prob: float | None = None
    reasoning_full: str = ""
    stakes_tags: Sequence[str] | None = None
    reviewed_by: str | None = None
    # §8: at 100% of any provider ceiling we publish no new picks. The gate is
    # where that becomes enforceable rather than advisory.
    budget_permits_publication: bool = True


Check = Callable[[PublicationContext], bool]

MIN_FACTORS = 4
MAX_ODDS_AGE_MINUTES = 90
MIN_REASONING_CHARS = 200

PUBLICATION_GATE: list[tuple[str, Check]] = [
    ("no_blocking_qa_flags", lambda c: len(c.blocking_flags) == 0),
    (
        "odds_fresh",
        lambda c: c.odds_age_minutes is not None
        and c.odds_age_minutes < MAX_ODDS_AGE_MINUTES,
    ),
    ("teams_resolved", lambda c: bool(c.home_id) and bool(c.away_id)),
    ("min_factors_present", lambda c: len(c.valid_factors) >= MIN_FACTORS),
    (
        "internal_prob_set",
        lambda c: c.internal_prob is not None and 0.01 < c.internal_prob < 0.99,
    ),
    ("reasoning_present", lambda c: len(c.reasoning_full) > MIN_REASONING_CHARS),
    ("stakes_computed", lambda c: c.stakes_tags is not None),
    # REQ-QA-3: every pick is read by a person before it goes out. At 4-6 picks
    # a day this is feasible, and it is the last line of defence against a
    # plausible-looking pipeline error reaching subscribers.
    ("human_reviewed", lambda c: c.reviewed_by is not None),
    ("budget_permits_publication", lambda c: c.budget_permits_publication),
]


def failed_checks(context: PublicationContext) -> list[str]:
    """Every failure, not just the first — one round trip for the human."""
    return [name for name, check in PUBLICATION_GATE if not check(context)]


class PublicationGate:
    def __init__(self, db: Db, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()

    async def gate(self, context: PublicationContext) -> bool:
        failed = failed_checks(context)
        if failed:
            await self._log_blocked(context, failed)
            return False
        return True

    async def _log_blocked(
        self, context: PublicationContext, failed: list[str]
    ) -> None:
        await self._db.execute(
            """
            insert into publication_blocks (fixture_id, pick_id, failed_checks,
                                            blocked_at)
            values ($1, $2, $3, $4)
            """,
            context.fixture_id,
            context.pick_id,
            failed,
            self._clock.now(),
        )

    async def publish(self, context: PublicationContext) -> bool:
        """Gate, then mark the pick published. Never one without the other."""
        if not await self.gate(context):
            if context.pick_id:
                await self._db.execute(
                    "update picks set status = 'blocked', updated_at = $2 "
                    "where id = $1",
                    context.pick_id,
                    self._clock.now(),
                )
            return False

        now = self._clock.now()
        await self._db.execute(
            """
            update picks
               set status = 'published', published_at = $2, updated_at = $2
             where id = $1
            """,
            context.pick_id,
            now,
        )
        return True
