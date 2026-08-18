"""Point-in-time features — REQ-QA-4.

The dominant failure in betting model development is lookahead bias: computing
a feature using data that did not exist at the time of the fixture. A model
that uses full-season xG to "predict" an October match has seen the future. It
will look excellent in backtest and lose money live. This is not a rare edge
case; it is the normal outcome of careless backtesting.

So there is exactly one way to read match history in this codebase, and it
takes an `as_of` argument. Never `WHERE season = X` — always
`WHERE kickoff_at < as_of`.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..db import Db

# The §5.4 minimum for opponent-adjusted metrics. The sample gate applies in
# backtest exactly as it does live — a backtest that quietly uses thinner
# samples than production is measuring a model we do not ship.
MIN_MATCHES = 6
DEFAULT_WINDOW = 10


class LookaheadError(AssertionError):
    """A row dated at or after `as_of` reached feature computation.

    Raised rather than filtered. If a row got this far, the query that fetched
    it is wrong, and silently dropping it would hide the bug in every future
    run.
    """


@dataclass(frozen=True)
class FeatureWindow:
    """Features for one team, computed only from matches finished before `as_of`."""

    team_id: str
    as_of: datetime
    matches_used: int
    xg_for: float
    xg_against: float
    goals_for: float
    goals_against: float
    xg_sd: float
    points_per_game: float
    latest_match_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "as_of": self.as_of.isoformat(),
            "matches_used": self.matches_used,
            "xg_for": round(self.xg_for, 4),
            "xg_against": round(self.xg_against, 4),
            "goals_for": round(self.goals_for, 4),
            "goals_against": round(self.goals_against, 4),
            "xg_sd": round(self.xg_sd, 4),
            "points_per_game": round(self.points_per_game, 4),
        }


def assert_point_in_time(rows: Sequence[dict[str, Any]], as_of: datetime) -> None:
    """Guard that runs in production too, not only in tests."""
    for row in rows:
        kickoff = row.get("kickoff_at")
        if kickoff is None:
            raise LookaheadError("row has no kickoff_at; cannot prove it is past")
        if kickoff >= as_of:
            raise LookaheadError(
                f"row dated {kickoff.isoformat()} is not before as_of "
                f"{as_of.isoformat()} — the feature query has lookahead bias"
            )
        if row.get("status") != "finished":
            raise LookaheadError(
                f"row dated {kickoff.isoformat()} has status "
                f"{row.get('status')!r}; an unfinished match has no result to "
                "learn from"
            )


def compute_features(
    team_id: str, rows: Sequence[dict[str, Any]], as_of: datetime
) -> FeatureWindow:
    """Pure aggregation over already-fetched, already-verified rows."""
    assert_point_in_time(rows, as_of)
    if len(rows) < MIN_MATCHES:
        raise ValueError(
            f"{len(rows)} matches is below the {MIN_MATCHES}-match minimum"
        )

    xgs = [float(r["xg"]) for r in rows]
    xgas = [float(r["xga"]) for r in rows]
    gf = [int(r["goals_for"]) for r in rows]
    ga = [int(r["goals_against"]) for r in rows]
    points = [
        3 if f > a else (1 if f == a else 0)
        for f, a in zip(gf, ga, strict=True)
    ]

    return FeatureWindow(
        team_id=team_id,
        as_of=as_of,
        matches_used=len(rows),
        xg_for=statistics.fmean(xgs),
        xg_against=statistics.fmean(xgas),
        goals_for=statistics.fmean(gf),
        goals_against=statistics.fmean(ga),
        xg_sd=statistics.pstdev(xgs) if len(xgs) > 1 else 0.0,
        points_per_game=statistics.fmean(points),
        latest_match_at=max(r["kickoff_at"] for r in rows),
    )


async def get_features_as_of(
    db: Db,
    team_id: str,
    as_of: datetime,
    *,
    window: int = DEFAULT_WINDOW,
) -> FeatureWindow | None:
    """Only matches that had FINISHED before `as_of`.

    Returns None when the sample is too thin — the §5.4 gate applies in
    backtest too, and a None here is what stops a thin-sample pick from being
    counted as evidence later.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")

    rows = await db.fetch(
        """
        select fixture_id, team_id, kickoff_at, status, xg, xga,
               goals_for, goals_against
          from team_match_stats
         where team_id = $1
           and kickoff_at < $2
           and status = 'finished'
         order by kickoff_at desc
         limit $3
        """,
        team_id,
        as_of,
        window,
    )

    if len(rows) < MIN_MATCHES:
        return None

    return compute_features(team_id, rows, as_of)
