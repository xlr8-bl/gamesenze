"""Odds arithmetic.

Small, pure, and heavily used — every number the frontend shows a subscriber
comes through here, so it is worth being exact about the difference between a
book's implied probability (which includes its margin) and a fair one (which
does not).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


def implied_probability(decimal_odds: float) -> float:
    """The book's number, margin included. Not a forecast."""
    if decimal_odds < 1.01:
        raise ValueError(f"decimal odds {decimal_odds} below the 1.01 floor")
    return 1.0 / decimal_odds


def decimal_from_probability(probability: float) -> float:
    if not 0.0 < probability < 1.0:
        raise ValueError(f"{probability} is not a probability strictly in (0, 1)")
    return 1.0 / probability


def overround(decimal_odds: Sequence[float]) -> float:
    """Sum of implied probabilities across a complete market, minus 1."""
    return sum(implied_probability(o) for o in decimal_odds) - 1.0


def devig(decimal_odds: Sequence[float]) -> list[float]:
    """Fair probabilities by proportional (multiplicative) de-vigging.

    Proportional is the simple choice and it slightly under-corrects favourites
    relative to more elaborate methods. We use it because it is transparent:
    a subscriber can reproduce our fair price with a calculator, which matters
    more here than the last decimal of accuracy.
    """
    raw = [implied_probability(o) for o in decimal_odds]
    total = sum(raw)
    if total <= 0:
        raise ValueError("cannot de-vig an empty or zero market")
    return [p / total for p in raw]


def expected_value(probability: float, decimal_odds: float, stake: float = 1.0) -> float:
    """EV of a stake at these odds, given our probability."""
    return stake * (probability * (decimal_odds - 1.0) - (1.0 - probability))


def edge(probability: float, decimal_odds: float) -> float:
    """Fractional edge: >0 means our number beats the price."""
    return probability * decimal_odds - 1.0


def kelly_fraction(
    probability: float, decimal_odds: float, *, cap: float = 0.25
) -> float:
    """Kelly stake as a fraction of bankroll, capped.

    Capped because full Kelly on a probability we estimated is a bet on our
    calibration being perfect, and REQ-QA-8 exists precisely because it is not.
    """
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    f = (probability * b - (1.0 - probability)) / b
    return max(0.0, min(f, cap))


@dataclass(frozen=True)
class Move:
    from_odds: float
    to_odds: float

    @property
    def relative(self) -> float:
        return (self.to_odds - self.from_odds) / self.from_odds

    @property
    def probability_shift(self) -> float:
        return implied_probability(self.to_odds) - implied_probability(self.from_odds)

    @property
    def direction(self) -> str:
        if self.to_odds > self.from_odds:
            return "drifting"   # price lengthening, money going elsewhere
        if self.to_odds < self.from_odds:
            return "shortening"  # money coming in
        return "static"
