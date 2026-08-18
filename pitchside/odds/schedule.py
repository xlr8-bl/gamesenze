"""Snapshot cadence — §3.4.

Sixteen objects per covered football fixture, front-loaded toward kickoff
because that is where the information is. The windows are data, and the planner
is pure: given a kickoff and a degradation level it returns the exact capture
times, which is what makes the monthly object budget predictable rather than
hopeful.

REQ-BUDGET-1: only fixtures with a published pick get snapshotted. Nothing here
polls the board; the planner is only ever handed covered fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SnapshotWindow:
    label: str
    # Hours before kickoff. `start` is the earlier (larger) offset.
    start_hours: float
    end_hours: float
    interval_minutes: int
    # True for windows the budget ladder is allowed to thin out (§8, 80% rung).
    thinnable: bool

    @property
    def planned_count(self) -> int:
        span_minutes = (self.start_hours - self.end_hours) * 60
        return int(span_minutes // self.interval_minutes)


WINDOWS: tuple[SnapshotWindow, ...] = (
    SnapshotWindow("t48_t12", 48, 12, 360, thinnable=True),   # every 6h  -> 6
    SnapshotWindow("t12_t3", 12, 3, 180, thinnable=True),     # every 3h  -> 3
    SnapshotWindow("t3_t1", 3, 1, 60, thinnable=False),       # hourly    -> 2
    SnapshotWindow("t1_kickoff", 1, 0, 15, thinnable=False),  # 15 min    -> 4
)

LOCK_LABEL = "lock"  # the single at-kickoff capture -> 1

# 6 + 3 + 2 + 4 + 1 = 16, which is what §3.3 budgets per football fixture.
PLANNED_SNAPSHOTS_PER_FIXTURE = sum(w.planned_count for w in WINDOWS) + 1


def plan_snapshots(
    kickoff: datetime,
    *,
    thinning_factor: int = 1,
    closing_only: bool = False,
) -> list[tuple[datetime, str]]:
    """Capture times for one fixture, earliest first.

    `thinning_factor` multiplies the interval of thinnable windows — the 80%
    rung of the ladder passes 2, which halves cadence outside T-3h.

    `closing_only` drops everything but the lock capture. The lock capture is
    never dropped at any rung: REQ-QA-5 measures the backtest against the
    closing line, so losing it does not save budget, it destroys the only
    honest measure of whether we found an edge.
    """
    if thinning_factor < 1:
        raise ValueError("thinning_factor must be >= 1")

    points: list[tuple[datetime, str]] = []
    if not closing_only:
        for window in WINDOWS:
            interval = window.interval_minutes * (
                thinning_factor if window.thinnable else 1
            )
            offset_minutes = window.start_hours * 60
            end_minutes = window.end_hours * 60
            while offset_minutes > end_minutes:
                points.append(
                    (kickoff - timedelta(minutes=offset_minutes), window.label)
                )
                offset_minutes -= interval

    points.append((kickoff, LOCK_LABEL))
    points.sort(key=lambda p: p[0])
    return points


def due_snapshots(
    kickoff: datetime,
    now: datetime,
    *,
    already_captured: int = 0,
    thinning_factor: int = 1,
    closing_only: bool = False,
    grace_minutes: int = 10,
) -> tuple[datetime, str] | None:
    """The single capture point that is due now, if any.

    A Worker tick asks this question per fixture and makes at most one vendor
    call. `grace_minutes` tolerates a late tick without firing a burst of
    catch-up captures: a missed point is a missed point, not a reason to spend
    four objects at once.
    """
    plan = plan_snapshots(
        kickoff, thinning_factor=thinning_factor, closing_only=closing_only
    )
    if already_captured >= len(plan):
        return None

    grace = timedelta(minutes=grace_minutes)
    for at, label in plan:
        if at <= now <= at + grace:
            return (at, label)
    return None


def monthly_object_cost(
    football_fixtures: int,
    nba_games: int,
    *,
    per_football: int = PLANNED_SNAPSHOTS_PER_FIXTURE,
    per_nba: int = 8,
) -> int:
    """Objects a month of coverage will cost (§3.3).

    Used by the coverage admission check: a fixture is only marked covered if
    its full snapshot plan still fits inside the month's remaining objects.
    """
    return football_fixtures * per_football + nba_games * per_nba
