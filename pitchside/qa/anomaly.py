"""Layer 3 — anomaly detection (§5.3).

Some values are individually valid but collectively implausible. Every rule
here has an explicit disposition, and the interesting ones are the ambiguous
ones: a 25% odds move might be a data error, or it might be exactly the news
our product exists to catch. So it goes to a human. **Ambiguity does not get
auto-resolved in either direction** — not toward rejecting, not toward trusting.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from .errors import Severity

# Below this implied probability (and above its complement) a price is not a
# real market, it is a typo or a placeholder. Layer 1's wider 1.01-1000.0 range
# is a sanity check on the raw field; this is a usability check on a price we
# would actually price a pick against.
MIN_IMPLIED = 0.01
MAX_IMPLIED = 0.99

ODDS_JUMP_THRESHOLD = 0.20      # relative move between consecutive snapshots
FROZEN_HOURS = 24
COVERAGE_GAP_HOURS = 8
XG_OUTLIER_SD = 3.0


@dataclass(frozen=True)
class Anomaly:
    kind: str
    severity: Severity
    detail: str
    # True when the record must not be stored at all, as opposed to stored and
    # flagged. Only impossible lines and duplicates reach this.
    reject: bool = False


def implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 0:
        raise ValueError("decimal odds must be positive")
    return 1.0 / decimal_odds


def check_impossible_line(decimal_odds: float) -> Anomaly | None:
    """Reject prices implying <1% or >99%."""
    p = implied_probability(decimal_odds)
    if p < MIN_IMPLIED or p > MAX_IMPLIED:
        return Anomaly(
            "impossible_line",
            Severity.BLOCK,
            f"decimal_odds={decimal_odds} implies {p:.4%}",
            reject=True,
        )
    return None


def check_odds_jump(
    previous: float, current: float, *, threshold: float = ODDS_JUMP_THRESHOLD
) -> Anomaly | None:
    """A >20% move between consecutive snapshots. Review, never auto-reject.

    The move is measured on the decimal price (the quantity the rule names);
    the implied-probability shift is reported alongside it, because that is
    what a reviewer actually needs to judge whether the news justifies it.
    """
    if previous <= 0:
        return None
    move = abs(current - previous) / previous
    if move <= threshold:
        return None
    p_before, p_after = implied_probability(previous), implied_probability(current)
    return Anomaly(
        "odds_jump",
        Severity.REVIEW,
        f"{previous:.2f} -> {current:.2f} ({move:.1%} move; implied "
        f"{p_before:.1%} -> {p_after:.1%}) — real news or bad data?",
    )


def check_odds_frozen(
    last_change_at: datetime | None,
    now: datetime,
    *,
    has_breaking_news: bool,
    hours: int = FROZEN_HOURS,
) -> Anomaly | None:
    """No movement in 24h on a fixture with breaking news — possible stale feed.

    Without news, a still price is just a still market, which is unremarkable.
    """
    if not has_breaking_news or last_change_at is None:
        return None
    idle = now - last_change_at
    if idle >= timedelta(hours=hours):
        return Anomaly(
            "odds_frozen",
            Severity.REVIEW,
            f"no price movement for {idle.total_seconds() / 3600:.1f}h despite "
            "breaking news — possible stale feed",
        )
    return None


def check_xg_outlier(
    value: float, season_values: Sequence[float], *, sds: float = XG_OUTLIER_SD
) -> Anomaly | None:
    """>3 SD from that team's season distribution. Flag, do not auto-reject.

    Teams do have 4.5 xG afternoons. Throwing those away would bias the very
    distribution we use to judge the next one.
    """
    if len(season_values) < 5:
        return None  # no distribution worth testing against yet
    mean = statistics.fmean(season_values)
    sd = statistics.pstdev(season_values)
    if sd == 0:
        return None
    z = abs(value - mean) / sd
    if z > sds:
        return Anomaly(
            "xg_outlier",
            Severity.REVIEW,
            f"xG {value:.2f} is {z:.1f} SD from season mean {mean:.2f} "
            f"(sd {sd:.2f})",
        )
    return None


def check_coverage_gap(
    capture_times: Sequence[datetime],
    kickoff: datetime,
    now: datetime,
    *,
    max_gap_hours: int = COVERAGE_GAP_HOURS,
) -> Anomaly | None:
    """A covered fixture with no odds for >8h inside the T-48h window.

    Measured against `now` as well as between captures: a feed that stopped
    four hours ago has a gap that no pair of existing timestamps reveals.
    """
    window_start = kickoff - timedelta(hours=48)
    if now < window_start or now > kickoff:
        return None

    points = sorted(t for t in capture_times if window_start <= t <= now)
    edges = [window_start, *points, now]
    limit = timedelta(hours=max_gap_hours)
    for earlier, later in zip(edges, edges[1:], strict=False):
        gap = later - earlier
        if gap > limit:
            return Anomaly(
                "coverage_gap",
                Severity.REVIEW,
                f"{gap.total_seconds() / 3600:.1f}h without an odds capture "
                f"between {earlier.isoformat()} and {later.isoformat()}",
            )
    return None


@dataclass(frozen=True)
class FixtureKey:
    home_team_id: str
    away_team_id: str
    kickoff_at: datetime


def find_duplicate_fixtures(
    fixtures: Iterable[tuple[str, FixtureKey]],
    *,
    tolerance: timedelta = timedelta(hours=6),
) -> list[tuple[str, str, str]]:
    """The same match ingested twice under different IDs.

    Blocked and deduped rather than flagged: two fixture rows for one match
    means odds, stats and picks split across both, and every downstream count
    is quietly wrong. Kickoff is compared with tolerance because sources
    disagree on the exact time far more often than they invent a match.
    """
    seen: list[tuple[str, FixtureKey]] = []
    duplicates: list[tuple[str, str, str]] = []
    for fixture_id, key in fixtures:
        for other_id, other in seen:
            if (
                key.home_team_id == other.home_team_id
                and key.away_team_id == other.away_team_id
                and abs(key.kickoff_at - other.kickoff_at) <= tolerance
            ):
                duplicates.append(
                    (
                        fixture_id,
                        other_id,
                        f"same teams, kickoffs {key.kickoff_at.isoformat()} and "
                        f"{other.kickoff_at.isoformat()}",
                    )
                )
                break
        seen.append((fixture_id, key))
    return duplicates
