"""Stakes tags — the "why this match matters" layer from §6 Tier 1.

Free to compute: it is all derivable from the fixture, the table and the
calendar. The publication gate requires `stakes_computed`, so an empty list is
a valid answer and `None` is not — "we looked and there is nothing at stake" is
information, "we never looked" is a gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class StakesInput:
    matchday: int
    total_matchdays: int
    home_position: int | None
    away_position: int | None
    home_points: int | None
    away_points: int | None
    points_available: int
    is_derby: bool = False
    is_relegation_six_pointer: bool = False
    days_since_last_home: int | None = None
    days_since_last_away: int | None = None
    reverse_fixture_result: str | None = None  # 'won' | 'lost' | 'drew'


def stakes_tags(s: StakesInput) -> list[str]:
    tags: list[str] = []

    season_progress = s.matchday / max(s.total_matchdays, 1)
    if season_progress >= 0.85:
        tags.append("run_in")

    if s.home_position is not None and s.away_position is not None:
        if s.home_position <= 4 and s.away_position <= 4:
            tags.append("top_four_clash")
        if s.home_position >= 18 or s.away_position >= 18:
            tags.append("relegation_battle")
        if abs(s.home_position - s.away_position) <= 2:
            tags.append("neighbours_in_table")

    if s.is_derby:
        tags.append("derby")
    if s.is_relegation_six_pointer:
        tags.append("six_pointer")

    # Mathematical relevance: with few points left, a gap can be uncatchable
    # and the fixture stops mattering to one side regardless of the table.
    if (
        s.home_points is not None
        and s.away_points is not None
        and s.points_available > 0
        and abs(s.home_points - s.away_points) > s.points_available
    ):
        tags.append("dead_rubber_for_one_side")

    for days, side in ((s.days_since_last_home, "home"), (s.days_since_last_away, "away")):
        if days is not None and days <= 3:
            tags.append(f"{side}_short_rest")

    if s.reverse_fixture_result in ("lost",):
        tags.append("revenge_fixture")

    return tags


def congestion_flag(fixtures_in_window: int, window: timedelta) -> str | None:
    """Fixture congestion — Tier 1, and one of the more reliable free edges."""
    if window <= timedelta(0):
        return None
    per_week = fixtures_in_window / (window.days / 7 or 1)
    if per_week >= 2.5:
        return "severe_congestion"
    if per_week >= 2.0:
        return "congested"
    return None
