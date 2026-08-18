"""Calibration — REQ-QA-8.

Track calibration, not just win rate. If "strong lean" picks land at 55% while
we internally priced them at 70%, we are miscalibrated regardless of whether we
are profitable — and miscalibration is a leading indicator of future losses,
because the profit came from prices rather than from knowing something.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationBin:
    low: float
    high: float
    n: int
    predicted_avg: float
    observed_rate: float

    @property
    def gap(self) -> float:
        return self.observed_rate - self.predicted_avg


def brier_score(predictions: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean squared error of probabilistic forecasts. Lower is better.

    Always-predicting the base rate scores about 0.25 on a coin flip, so a
    Brier above that on near-even markets means the model is worse than saying
    nothing.
    """
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must be the same length")
    if not predictions:
        raise ValueError("no predictions to score")
    return sum(
        (p - o) ** 2 for p, o in zip(predictions, outcomes, strict=True)
    ) / len(predictions)


def calibration_bins(
    predictions: Sequence[float],
    outcomes: Sequence[int],
    *,
    n_bins: int = 10,
) -> list[CalibrationBin]:
    """Bucket predictions and compare each bucket's forecast with what happened."""
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must be the same length")

    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, o in zip(predictions, outcomes, strict=True):
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"prediction {p} is not a probability")
        index = min(int(p * n_bins), n_bins - 1)
        buckets[index].append((p, o))

    bins: list[CalibrationBin] = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        ps = [p for p, _ in bucket]
        os_ = [o for _, o in bucket]
        bins.append(
            CalibrationBin(
                low=i / n_bins,
                high=(i + 1) / n_bins,
                n=len(bucket),
                predicted_avg=sum(ps) / len(ps),
                observed_rate=sum(os_) / len(os_),
            )
        )
    return bins


def calibration_error(
    predictions: Sequence[float],
    outcomes: Sequence[int],
    *,
    n_bins: int = 10,
) -> float:
    """Expected calibration error: bin gaps weighted by bin population."""
    bins = calibration_bins(predictions, outcomes, n_bins=n_bins)
    total = sum(b.n for b in bins)
    if total == 0:
        return 0.0
    return sum(b.n * abs(b.gap) for b in bins) / total


def wilson_interval(
    successes: int, trials: int, *, z: float = 1.96
) -> tuple[float, float]:
    """Confidence interval for a hit rate — REQ-QA-7.

    Wilson rather than normal-approximation: at the sample sizes a betting
    record actually reaches, the normal interval is visibly wrong near 0 and 1,
    and an interval that overstates our certainty is worse than none.
    """
    if trials <= 0:
        return (0.0, 0.0)
    p = successes / trials
    denominator = 1 + z**2 / trials
    centre = p + z**2 / (2 * trials)
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * trials)) / trials)
    return (
        max(0.0, (centre - margin) / denominator),
        min(1.0, (centre + margin) / denominator),
    )
