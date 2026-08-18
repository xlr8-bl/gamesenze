"""Layer 2 — cross-source verification (§5.2).

Where two sources cover the same fact, we check them against each other.
Disagreement is a signal that one of them is wrong, and we do not get to know
which — so the answer is never "pick the one we like". It is: stop, flag, and
have a person resolve it.

REQ-QA-1: settlement never proceeds on a single source. A pick's outcome needs
two sources agreeing, or explicit human resolution.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..clock import Clock, SystemClock
from ..db import Db
from .errors import Severity
from .flags import FlagStore


@dataclass(frozen=True)
class Agreement:
    fact: str
    agree: bool
    source_a: str
    source_b: str
    detail: str = ""
    severity: Severity = Severity.BLOCK

    def __bool__(self) -> bool:
        return self.agree


# --- Pure comparisons -------------------------------------------------------

def compare_score(
    a: tuple[int, int] | None,
    b: tuple[int, int] | None,
    *,
    source_a: str = "api_football",
    source_b: str = "fbref",
) -> Agreement:
    """Exact match required. A settled pick rests on this number."""
    if a is None or b is None:
        return Agreement(
            "final_score",
            False,
            source_a,
            source_b,
            detail=f"missing score from {source_a if a is None else source_b}",
        )
    if a != b:
        return Agreement(
            "final_score",
            False,
            source_a,
            source_b,
            detail=f"{source_a} {a[0]}-{a[1]} vs {source_b} {b[0]}-{b[1]}",
        )
    return Agreement("final_score", True, source_a, source_b)


def compare_kickoff(
    a: datetime | None,
    b: datetime | None,
    *,
    tolerance: timedelta = timedelta(minutes=15),
    source_a: str = "api_football",
    source_b: str = "understat",
) -> Agreement:
    if a is None or b is None:
        return Agreement(
            "kickoff_time", False, source_a, source_b, detail="missing kickoff"
        )
    drift = abs(a - b)
    if drift > tolerance:
        return Agreement(
            "kickoff_time",
            False,
            source_a,
            source_b,
            detail=f"{a.isoformat()} vs {b.isoformat()} "
                   f"({int(drift.total_seconds() // 60)} min apart)",
        )
    return Agreement("kickoff_time", True, source_a, source_b)


def compare_starting_xi(
    a: Sequence[str],
    b: Sequence[str],
    *,
    min_overlap: int = 9,
    source_a: str = "api_football",
    source_b: str = "fbref",
) -> Agreement:
    """At least 9 of 11 must match.

    Two disagreements is a late substitution or a naming difference; three is a
    different match, or an alias table that has not caught up.
    """
    overlap = len(set(a) & set(b))
    if overlap < min_overlap:
        return Agreement(
            "starting_xi",
            False,
            source_a,
            source_b,
            detail=f"only {overlap}/11 players match (need {min_overlap})",
        )
    return Agreement("starting_xi", True, source_a, source_b)


def compare_team_xg(
    a: float | None,
    b: float | None,
    *,
    tolerance: float = 0.30,
    source_a: str = "understat",
    source_b: str = "fbref",
) -> Agreement:
    """xG models differ by construction, so this is a drift check, not equality.

    Beyond 0.30 the two are not modelling the same match — usually a fixture
    mismatch rather than a modelling difference.
    """
    if a is None or b is None:
        return Agreement(
            "team_xg",
            False,
            source_a,
            source_b,
            detail="missing xG",
            severity=Severity.REVIEW,
        )
    # `> tolerance` alone flags a difference of exactly 0.30, because
    # 1.40 + 0.30 is 1.7000000000000002. A source landing precisely on the
    # tolerance should pass, so absorb the representation error.
    if abs(a - b) > tolerance and not math.isclose(
        abs(a - b), tolerance, rel_tol=1e-9, abs_tol=1e-9
    ):
        return Agreement(
            "team_xg",
            False,
            source_a,
            source_b,
            detail=f"{a:.2f} vs {b:.2f} (tolerance {tolerance:.2f})",
            severity=Severity.REVIEW,
        )
    return Agreement("team_xg", True, source_a, source_b)


def compare_player_minutes(
    a: int | None,
    b: int | None,
    *,
    tolerance: int = 5,
    source_a: str = "api_football",
    source_b: str = "fbref",
) -> Agreement:
    if a is None or b is None:
        return Agreement(
            "player_minutes",
            False,
            source_a,
            source_b,
            detail="missing minutes",
            severity=Severity.REVIEW,
        )
    if abs(a - b) > tolerance:
        return Agreement(
            "player_minutes",
            False,
            source_a,
            source_b,
            detail=f"{a} vs {b} (tolerance {tolerance})",
            severity=Severity.REVIEW,
        )
    return Agreement("player_minutes", True, source_a, source_b)


@dataclass
class VerificationReport:
    fixture_id: str
    results: list[Agreement] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.agree for r in self.results)

    @property
    def blocking(self) -> list[Agreement]:
        return [
            r for r in self.results
            if not r.agree and r.severity is Severity.BLOCK
        ]

    @property
    def settlement_allowed(self) -> bool:
        """REQ-QA-1: the score check must have run and must have passed."""
        score = [r for r in self.results if r.fact == "final_score"]
        return bool(score) and all(r.agree for r in score)


class CrossVerifier:
    """Runs the §5.2 table against a fixture and records what it finds."""

    def __init__(self, db: Db, clock: Clock | None = None) -> None:
        self._db = db
        self._flags = FlagStore(db, clock)
        self._clock = clock or SystemClock()

    async def verify_fixture(
        self,
        fixture_id: str,
        a: dict[str, Any],
        b: dict[str, Any],
    ) -> VerificationReport:
        """Compare two source views of the same fixture.

        Each dict may carry `score`, `kickoff_at`, `starting_xi`, `xg`. Facts
        absent from both sides are skipped; a fact present on one side only is
        a disagreement, because a source that should have covered it and did
        not is itself a signal.
        """
        report = VerificationReport(fixture_id)

        if "score" in a or "score" in b:
            report.results.append(compare_score(a.get("score"), b.get("score")))
        if "kickoff_at" in a or "kickoff_at" in b:
            report.results.append(
                compare_kickoff(a.get("kickoff_at"), b.get("kickoff_at"))
            )
        if "starting_xi" in a or "starting_xi" in b:
            report.results.append(
                compare_starting_xi(
                    a.get("starting_xi") or [], b.get("starting_xi") or []
                )
            )
        if "xg" in a or "xg" in b:
            report.results.append(compare_team_xg(a.get("xg"), b.get("xg")))

        for result in report.results:
            if not result.agree:
                await self._flags.raise_flag(
                    "fixture",
                    fixture_id,
                    issue=f"{result.fact}_mismatch",
                    detail=result.detail,
                    severity=result.severity,
                )
        return report

    async def settle_if_verified(
        self, fixture_id: str, report: VerificationReport
    ) -> bool:
        """Gate on REQ-QA-1 before any settlement writes.

        Returns False and leaves settlement pending rather than guessing.
        """
        if not report.settlement_allowed:
            await self._flags.raise_flag(
                "fixture",
                fixture_id,
                issue="settlement_blocked",
                detail="settlement requires two agreeing sources on the score",
                severity=Severity.BLOCK,
            )
            return False
        return True
