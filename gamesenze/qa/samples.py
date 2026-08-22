"""Layer 4 — sample adequacy gates (§5.4).

Thin samples produce confident-looking nonsense. The minimums below are hard
and enforced in code, not conventions someone remembers to apply.

REQ-QA-2: an excluded factor renders as an explicit data-limit block in the UI.
We never silently drop a factor. Stating the limit is a trust asset; hiding it
is the beginning of a track record we cannot defend — and a reader who sees us
exclude a thin referee sample has a reason to believe the factors we did use.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class Disposition(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    PROVISIONAL = "provisional"


@dataclass(frozen=True)
class SampleGate:
    factor: str
    minimum: int
    unit: str          # what is being counted, for the UI message
    label: str         # human name of the factor
    # Manager profile is flagged rather than dropped: five matches says
    # something, just not enough to lean on.
    provisional_below_minimum: bool = False


GATES: dict[str, SampleGate] = {
    "referee_tendency": SampleGate(
        "referee_tendency", 20, "matches at this level", "Referee tendency"
    ),
    "player_variance": SampleGate(
        "player_variance", 10, "appearances of 45+ minutes", "Player variance"
    ),
    "opponent_adjusted": SampleGate(
        "opponent_adjusted", 6, "matches this season", "Opponent-adjusted metrics"
    ),
    "head_to_head": SampleGate(
        "head_to_head", 4, "meetings in five years", "Head-to-head"
    ),
    "recent_form": SampleGate(
        "recent_form", 6, "recent matches", "Recent form"
    ),
    "scoring_trend": SampleGate(
        "scoring_trend", 6, "recent matches", "Attacking output"
    ),
    "defensive_record": SampleGate(
        "defensive_record", 6, "recent matches", "Defensive record"
    ),
    "nba_usage_redistribution": SampleGate(
        "nba_usage_redistribution", 3, "games without the player",
        "NBA usage redistribution",
    ),
    "manager_profile": SampleGate(
        "manager_profile", 5, "matches at this club", "Manager tactical profile",
        provisional_below_minimum=True,
    ),
}


@dataclass(frozen=True)
class FactorVerdict:
    factor: str
    disposition: Disposition
    n: int
    minimum: int
    message: str

    @property
    def usable(self) -> bool:
        """Provisional factors may be used; they carry a caveat in the UI."""
        return self.disposition is not Disposition.EXCLUDED


def evaluate_factor(factor: str, n: int) -> FactorVerdict:
    try:
        gate = GATES[factor]
    except KeyError:
        raise ValueError(
            f"unknown factor {factor!r}: register a SampleGate before using it "
            "in a pick"
        ) from None

    if n >= gate.minimum:
        return FactorVerdict(
            factor,
            Disposition.INCLUDED,
            n,
            gate.minimum,
            f"{gate.label}: {n} {gate.unit}.",
        )

    if gate.provisional_below_minimum:
        return FactorVerdict(
            factor,
            Disposition.PROVISIONAL,
            n,
            gate.minimum,
            f"{gate.label} is provisional — only {n} {gate.unit} "
            f"(we prefer {gate.minimum}).",
        )

    return FactorVerdict(
        factor,
        Disposition.EXCLUDED,
        n,
        gate.minimum,
        f"{gate.label} sample too thin ({n} {gate.unit}), excluded rather "
        "than forced.",
    )


@dataclass
class FactorSet:
    """The outcome of gating every factor a pick wanted to use."""

    verdicts: list[FactorVerdict] = field(default_factory=list)

    @property
    def valid(self) -> list[str]:
        return [v.factor for v in self.verdicts if v.usable]

    @property
    def excluded(self) -> list[FactorVerdict]:
        return [v for v in self.verdicts if v.disposition is Disposition.EXCLUDED]

    @property
    def provisional(self) -> list[FactorVerdict]:
        return [
            v for v in self.verdicts if v.disposition is Disposition.PROVISIONAL
        ]

    def ui_blocks(self) -> list[dict[str, object]]:
        """Serialised for `picks.excluded_factors` and the UI (REQ-QA-2)."""
        return [
            {
                "factor": v.factor,
                "disposition": v.disposition.value,
                "n": v.n,
                "minimum": v.minimum,
                "message": v.message,
            }
            for v in self.verdicts
            if v.disposition is not Disposition.INCLUDED
        ]


def evaluate_factors(sample_counts: Mapping[str, int]) -> FactorSet:
    """Gate every factor at once. Order follows the §5.4 table for stable UI."""
    ordered = [f for f in GATES if f in sample_counts]
    return FactorSet([evaluate_factor(f, sample_counts[f]) for f in ordered])
