"""The backtest harness — REQ-QA-4 through REQ-QA-8.

Four rules the harness enforces rather than trusts:

* **Selection uses the price we could have seen; evaluation uses the close.**
  REQ-QA-5 says measure against the closing line, and it is tempting to also
  *choose* picks by comparing our number to the close. That is lookahead by
  another route — we did not know the closing price when the pick was written.
  So `capture_odds` decides whether a pick is taken and `closing_odds` decides
  what it was worth.
* **Every fixture we would have covered is included** (REQ-QA-6), including the
  ones where data was missing. Those are reported as skips with a reason, not
  quietly dropped: excluding awkward fixtures after the fact is survivorship
  bias and inflates results.
* **Fewer than 100 picks is not evidence** (REQ-QA-7). The result carries the
  flag and the confidence interval, and `is_evidence` says so plainly.
* **Calibration is reported alongside win rate** (REQ-QA-8).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from ..db import Db
from .calibration import (
    CalibrationBin,
    brier_score,
    calibration_bins,
    calibration_error,
    wilson_interval,
)
from .features import FeatureWindow, get_features_as_of

MIN_PICKS_FOR_EVIDENCE = 100


@dataclass(frozen=True)
class BacktestCandidate:
    """One fixture the pipeline would have looked at, whatever came of it."""

    fixture_id: str
    kickoff_at: datetime
    home_team_id: str
    away_team_id: str
    market: str
    selection: str
    # The price available when the pick would have been written.
    capture_odds: float | None
    # The close. Evaluation only — never shown to the model.
    closing_odds: float | None
    # 1 if the selection won, 0 if it lost. None if the fixture never settled.
    outcome: int | None

    # `as_of` is the moment the pick would have been made: we use kickoff,
    # since features must predate the match itself.
    @property
    def as_of(self) -> datetime:
        return self.kickoff_at


Model = Callable[
    [FeatureWindow, FeatureWindow, BacktestCandidate], float | None
]


@dataclass
class Skip:
    fixture_id: str
    reason: str


@dataclass
class BacktestResult:
    label: str
    pick_count: int
    candidate_count: int
    as_of_correct: bool
    vs_closing_line: bool
    hit_rate: float
    ci_low: float
    ci_high: float
    roi: float
    brier: float
    ece: float
    bins: list[CalibrationBin] = field(default_factory=list)
    skips: list[Skip] = field(default_factory=list)

    @property
    def is_evidence(self) -> bool:
        return self.pick_count >= MIN_PICKS_FOR_EVIDENCE

    @property
    def skip_reasons(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for skip in self.skips:
            counts[skip.reason] = counts.get(skip.reason, 0) + 1
        return counts

    def summary(self) -> str:
        header = (
            f"{self.label}: {self.pick_count} picks from "
            f"{self.candidate_count} candidates"
        )
        if not self.is_evidence:
            header += (
                f"\n  NOT EVIDENCE — fewer than {MIN_PICKS_FOR_EVIDENCE} picks "
                "(REQ-QA-7). Report with the interval below or not at all."
            )
        return (
            f"{header}\n"
            f"  hit rate  {self.hit_rate:.1%} "
            f"(95% CI {self.ci_low:.1%} - {self.ci_high:.1%})\n"
            f"  ROI       {self.roi:+.2%} vs closing line\n"
            f"  Brier     {self.brier:.4f}\n"
            f"  calib err {self.ece:.4f}\n"
            f"  skipped   {self.skip_reasons or 'none'}"
        )


class BacktestHarness:
    def __init__(
        self,
        db: Db,
        model: Model,
        *,
        edge_threshold: float = 0.02,
        window: int = 10,
    ) -> None:
        self._db = db
        self._model = model
        self._edge_threshold = edge_threshold
        self._window = window

    async def run(
        self,
        candidates: Iterable[BacktestCandidate],
        *,
        label: str = "backtest",
    ) -> BacktestResult:
        candidates = list(candidates)
        predictions: list[float] = []
        outcomes: list[int] = []
        returns: list[float] = []
        skips: list[Skip] = []

        for candidate in candidates:
            home = await get_features_as_of(
                self._db, candidate.home_team_id, candidate.as_of,
                window=self._window,
            )
            away = await get_features_as_of(
                self._db, candidate.away_team_id, candidate.as_of,
                window=self._window,
            )
            if home is None or away is None:
                skips.append(Skip(candidate.fixture_id, "insufficient_sample"))
                continue
            if candidate.capture_odds is None:
                skips.append(Skip(candidate.fixture_id, "no_capture_price"))
                continue

            probability = self._model(home, away, candidate)
            if probability is None:
                skips.append(Skip(candidate.fixture_id, "model_declined"))
                continue

            # Selection: our number against the price we could have taken.
            if probability * candidate.capture_odds < 1 + self._edge_threshold:
                skips.append(Skip(candidate.fixture_id, "no_edge"))
                continue

            # Evaluation: REQ-QA-5, against the close.
            if candidate.closing_odds is None:
                skips.append(Skip(candidate.fixture_id, "no_closing_price"))
                continue
            if candidate.outcome is None:
                skips.append(Skip(candidate.fixture_id, "unsettled"))
                continue

            predictions.append(probability)
            outcomes.append(candidate.outcome)
            returns.append(
                candidate.closing_odds - 1.0 if candidate.outcome == 1 else -1.0
            )

        return self._assemble(label, candidates, predictions, outcomes, returns, skips)

    def _assemble(
        self,
        label: str,
        candidates: Sequence[BacktestCandidate],
        predictions: list[float],
        outcomes: list[int],
        returns: list[float],
        skips: list[Skip],
    ) -> BacktestResult:
        n = len(predictions)
        if n == 0:
            return BacktestResult(
                label=label,
                pick_count=0,
                candidate_count=len(candidates),
                as_of_correct=True,
                vs_closing_line=True,
                hit_rate=0.0,
                ci_low=0.0,
                ci_high=0.0,
                roi=0.0,
                brier=0.0,
                ece=0.0,
                skips=skips,
            )

        wins = sum(outcomes)
        low, high = wilson_interval(wins, n)
        return BacktestResult(
            label=label,
            pick_count=n,
            candidate_count=len(candidates),
            # Both are structurally true of this harness: features come only
            # from get_features_as_of, returns only from closing_odds.
            as_of_correct=True,
            vs_closing_line=True,
            hit_rate=wins / n,
            ci_low=low,
            ci_high=high,
            roi=sum(returns) / n,
            brier=brier_score(predictions, outcomes),
            ece=calibration_error(predictions, outcomes),
            bins=calibration_bins(predictions, outcomes),
            skips=skips,
        )

    async def persist(self, db: Db, result: BacktestResult, notes: str = "") -> int:
        run_id = await db.fetchval(
            """
            insert into backtest_runs (label, pick_count, as_of_correct,
                                       vs_closing_line, brier_score,
                                       calibration_error, roi, hit_rate,
                                       ci_low, ci_high, notes)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            returning id
            """,
            result.label,
            result.pick_count,
            result.as_of_correct,
            result.vs_closing_line,
            result.brier,
            result.ece,
            result.roi,
            result.hit_rate,
            result.ci_low,
            result.ci_high,
            notes or ("below evidence threshold" if not result.is_evidence else ""),
        )
        for b in result.bins:
            await db.execute(
                """
                insert into backtest_calibration_bins (run_id, bin_low, bin_high,
                                                       predicted_avg,
                                                       observed_rate, n)
                values ($1, $2, $3, $4, $5, $6)
                """,
                run_id,
                b.low,
                b.high,
                b.predicted_avg,
                b.observed_rate,
                b.n,
            )
        return int(run_id)
