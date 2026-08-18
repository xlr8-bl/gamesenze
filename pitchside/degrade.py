"""Degradation ladder — §8.

Failure is expected. It must never be silent, and it must never produce a wrong
pick. Every rung below trades away freshness or coverage; none of them trades
away correctness, because REQ-DEGRADE-1 says silence beats error.

The ladder is a pure function of budget state so it can be unit-tested and so
the Worker, the Actions jobs and the frontend all reach the same conclusion
from the same counters rather than each guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from enum import StrEnum

from .budget import BudgetStatus


class Rung(StrEnum):
    NORMAL = "normal"
    REDUCED = "reduced"            # >= 80%: halve cadence outside T-3h
    CLOSING_ONLY = "closing_only"  # >= 90%: closing snapshots only
    EXHAUSTED = "exhausted"        # 100%: last-known only, publish nothing


REDUCED_AT = 0.80
CLOSING_ONLY_AT = 0.90


def rung_for(status: BudgetStatus) -> Rung:
    if status.unlimited:
        return Rung.NORMAL
    if status.used >= status.limit:
        return Rung.EXHAUSTED
    if status.used >= CLOSING_ONLY_AT * status.limit:
        return Rung.CLOSING_ONLY
    if status.used >= REDUCED_AT * status.limit:
        return Rung.REDUCED
    return Rung.NORMAL


def worst_rung(statuses: dict[str, BudgetStatus]) -> Rung:
    """The pipeline degrades to its most constrained provider.

    Being comfortable on Open-Meteo does not buy room on API-Football, and a
    pick assembled from a half-exhausted provider is the failure mode this
    whole section exists to prevent.
    """
    order = [Rung.NORMAL, Rung.REDUCED, Rung.CLOSING_ONLY, Rung.EXHAUSTED]
    worst = Rung.NORMAL
    for status in statuses.values():
        rung = rung_for(status)
        if order.index(rung) > order.index(worst):
            worst = rung
    return worst


@dataclass(frozen=True)
class Policy:
    """What a rung permits. Consumed by the Worker and the nightly job."""

    rung: Rung
    thinning_factor: int
    closing_only: bool
    may_snapshot: bool
    may_publish: bool
    banner: str | None

    @property
    def snapshots_per_fixture(self) -> int:
        from datetime import datetime

        from .odds.schedule import plan_snapshots

        if not self.may_snapshot:
            return 0
        anchor = datetime(2000, 1, 1, tzinfo=UTC)
        return len(
            plan_snapshots(
                anchor,
                thinning_factor=self.thinning_factor,
                closing_only=self.closing_only,
            )
        )


_POLICIES: dict[Rung, Policy] = {
    Rung.NORMAL: Policy(
        rung=Rung.NORMAL,
        thinning_factor=1,
        closing_only=False,
        may_snapshot=True,
        may_publish=True,
        banner=None,
    ),
    Rung.REDUCED: Policy(
        rung=Rung.REDUCED,
        thinning_factor=2,
        closing_only=False,
        may_snapshot=True,
        may_publish=True,
        banner="Reduced odds cadence — prices outside the final three hours "
               "update half as often today.",
    ),
    Rung.CLOSING_ONLY: Policy(
        rung=Rung.CLOSING_ONLY,
        thinning_factor=2,
        closing_only=True,
        may_snapshot=True,
        may_publish=True,
        banner="Closing prices only — intermediate odds updates are paused "
               "for the rest of this period.",
    ),
    Rung.EXHAUSTED: Policy(
        rung=Rung.EXHAUSTED,
        thinning_factor=2,
        closing_only=True,
        may_snapshot=False,
        may_publish=False,
        banner="Request budget reached. Showing last-known prices with their "
               "capture time; no new picks are being published.",
    ),
}


def policy_for(rung: Rung) -> Policy:
    return _POLICIES[rung]


def policy_from_statuses(statuses: dict[str, BudgetStatus]) -> Policy:
    return policy_for(worst_rung(statuses))


# --- Non-budget rungs -------------------------------------------------------
# The rest of the §8 table is not about request counts, so it does not belong
# on the same axis. These are the responses the calling code implements.

@dataclass(frozen=True)
class Fallback:
    condition: str
    response: str
    blocks_publication: bool


FALLBACKS: tuple[Fallback, ...] = (
    Fallback(
        "scrape_failed",
        "Use cached data and render its age in the UI.",
        blocks_publication=False,
    ),
    Fallback(
        "cross_source_mismatch",
        "Block settlement, raise a blocking QA flag, alert.",
        blocks_publication=True,
    ),
    Fallback(
        "worker_failed",
        "The hourly GitHub Actions fallback catches it within an hour.",
        blocks_publication=False,
    ),
    Fallback(
        "actions_delayed",
        "Accept. No time-critical work runs on Actions (§2.1).",
        blocks_publication=False,
    ),
    Fallback(
        "storage_near_limit",
        "Emergency prune of data_provenance.raw_response; alert at 400MB.",
        blocks_publication=False,
    ),
    Fallback(
        "blocking_qa_flag",
        "The pick does not publish.",
        blocks_publication=True,
    ),
)
