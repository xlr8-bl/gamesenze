"""Layer 7 — §5.7. The layer that separates a real edge from a fictional one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pitchside.backtest.calibration import (
    brier_score,
    calibration_bins,
    calibration_error,
    wilson_interval,
)
from pitchside.backtest.features import (
    MIN_MATCHES,
    LookaheadError,
    compute_features,
    get_features_as_of,
)
from pitchside.backtest.harness import (
    MIN_PICKS_FOR_EVIDENCE,
    BacktestCandidate,
    BacktestHarness,
)
from tests.conftest import FakeDb

AS_OF = datetime(2026, 8, 20, 19, 0, tzinfo=UTC)


def match(days_before: int, *, xg=1.4, xga=1.0, gf=2, ga=1, status="finished"):
    return {
        "fixture_id": f"f{days_before}",
        "team_id": "team-1",
        "kickoff_at": AS_OF - timedelta(days=days_before),
        "status": status,
        "xg": xg,
        "xga": xga,
        "goals_for": gf,
        "goals_against": ga,
    }


# --- REQ-QA-4 --------------------------------------------------------------

def test_features_are_computed_only_from_the_past():
    rows = [match(d) for d in range(1, 11)]
    window = compute_features("team-1", rows, AS_OF)
    assert window.matches_used == 10
    assert window.latest_match_at < AS_OF


def test_a_future_row_raises_rather_than_being_filtered():
    # If a row got this far the query is wrong; dropping it silently would hide
    # the bug in every future run.
    rows = [match(d) for d in range(1, 10)] + [match(-1)]
    with pytest.raises(LookaheadError, match="lookahead bias"):
        compute_features("team-1", rows, AS_OF)


def test_a_row_dated_exactly_as_of_is_lookahead():
    rows = [match(d) for d in range(1, 10)] + [match(0)]
    with pytest.raises(LookaheadError):
        compute_features("team-1", rows, AS_OF)


def test_unfinished_matches_have_no_result_to_learn_from():
    rows = [match(d) for d in range(1, 10)] + [match(2, status="live")]
    with pytest.raises(LookaheadError, match="unfinished"):
        compute_features("team-1", rows, AS_OF)


def test_sample_gate_applies_in_backtest_too():
    with pytest.raises(ValueError, match=f"below the {MIN_MATCHES}-match minimum"):
        compute_features("team-1", [match(d) for d in range(1, MIN_MATCHES)], AS_OF)


async def test_query_filters_on_kickoff_not_season():
    db = FakeDb({"from team_match_stats": [match(d) for d in range(1, 11)]})
    await get_features_as_of(db, "team-1", AS_OF)

    sql, args = db.statements[0]
    assert "kickoff_at < $2" in sql
    assert "season" not in sql
    assert args[1] == AS_OF


async def test_thin_sample_returns_none_rather_than_a_guess():
    db = FakeDb({"from team_match_stats": [match(1), match(2)]})
    assert await get_features_as_of(db, "team-1", AS_OF) is None


async def test_naive_datetimes_are_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        await get_features_as_of(FakeDb(), "team-1", datetime(2026, 8, 20))


# --- REQ-QA-5, 6, 7, 8 -----------------------------------------------------

def _db_with_history():
    return FakeDb({"from team_match_stats": [match(d) for d in range(1, 11)]})


def _candidate(i: int, *, capture=2.10, closing=2.05, outcome=1):
    return BacktestCandidate(
        fixture_id=f"fix-{i}",
        kickoff_at=AS_OF,
        home_team_id="team-1",
        away_team_id="team-2",
        market="1x2",
        selection="home",
        capture_odds=capture,
        closing_odds=closing,
        outcome=outcome,
    )


async def test_returns_are_measured_against_the_closing_line():
    # REQ-QA-5: beating a stale line proves nothing.
    harness = BacktestHarness(_db_with_history(), lambda h, a, c: 0.60)
    result = await harness.run([_candidate(0, capture=2.10, closing=1.50)])

    assert result.vs_closing_line
    # One win at closing 1.50 returns +0.50, not the +1.10 the capture implies.
    assert result.roi == pytest.approx(0.50)


async def test_selection_uses_the_capture_price_not_the_close():
    # Choosing picks by the closing price is lookahead by another route.
    harness = BacktestHarness(_db_with_history(), lambda h, a, c: 0.50)
    # No edge at capture (0.50 * 1.90 = 0.95), plenty at the close.
    result = await harness.run([_candidate(0, capture=1.90, closing=3.00)])

    assert result.pick_count == 0
    assert result.skip_reasons == {"no_edge": 1}


async def test_awkward_fixtures_are_skipped_with_a_reason_never_dropped():
    # REQ-QA-6: excluding them after the fact is survivorship bias.
    harness = BacktestHarness(_db_with_history(), lambda h, a, c: 0.60)
    result = await harness.run(
        [
            _candidate(0),
            _candidate(1, capture=None),
            _candidate(2, closing=None),
            _candidate(3, outcome=None),
        ]
    )

    assert result.candidate_count == 4
    assert result.pick_count == 1
    assert result.skip_reasons == {
        "no_capture_price": 1,
        "no_closing_price": 1,
        "unsettled": 1,
    }


async def test_insufficient_sample_is_a_skip_not_an_omission():
    db = FakeDb({"from team_match_stats": [match(1)]})
    harness = BacktestHarness(db, lambda h, a, c: 0.60)
    result = await harness.run([_candidate(0)])

    assert result.candidate_count == 1
    assert result.skip_reasons == {"insufficient_sample": 1}


async def test_under_a_hundred_picks_is_not_evidence():
    harness = BacktestHarness(_db_with_history(), lambda h, a, c: 0.60)
    small = await harness.run([_candidate(i) for i in range(99)])
    assert not small.is_evidence
    assert "NOT EVIDENCE" in small.summary()

    big = await harness.run([_candidate(i) for i in range(MIN_PICKS_FOR_EVIDENCE)])
    assert big.is_evidence
    assert "NOT EVIDENCE" not in big.summary()


async def test_result_always_carries_an_interval():
    harness = BacktestHarness(_db_with_history(), lambda h, a, c: 0.60)
    # Mixed outcomes: an all-wins run pins the interval to 1.0 and tests nothing.
    result = await harness.run(
        [_candidate(i, outcome=i % 2) for i in range(20)]
    )
    assert result.hit_rate == pytest.approx(0.5)
    assert result.ci_low < result.hit_rate < result.ci_high
    assert 0.0 < result.ci_low and result.ci_high < 1.0


# --- Calibration, REQ-QA-8 -------------------------------------------------

def test_a_calibrated_forecaster_scores_zero_error():
    predictions = [0.70] * 100
    outcomes = [1] * 70 + [0] * 30
    assert calibration_error(predictions, outcomes) == pytest.approx(0.0, abs=1e-9)


def test_the_prd_miscalibration_example_is_caught():
    # "strong lean" priced at 70%, landing at 55%.
    predictions = [0.70] * 100
    outcomes = [1] * 55 + [0] * 45
    assert calibration_error(predictions, outcomes) == pytest.approx(0.15)
    # Worse than the 0.25 a coin-flip baseline scores, despite being profitable
    # at any price above 1.82.
    assert brier_score(predictions, outcomes) > 0.25


def test_brier_rewards_confident_correctness():
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert brier_score([0.0, 1.0], [1, 0]) == 1.0


def test_calibration_bins_partition_the_predictions():
    bins = calibration_bins([0.05, 0.15, 0.95], [0, 0, 1], n_bins=10)
    assert sum(b.n for b in bins) == 3
    assert [b.n for b in bins] == [1, 1, 1]


def test_certainty_at_one_is_binned_not_dropped():
    bins = calibration_bins([1.0], [1], n_bins=10)
    assert len(bins) == 1 and bins[0].n == 1


def test_probabilities_outside_zero_to_one_are_refused():
    with pytest.raises(ValueError, match="not a probability"):
        calibration_bins([1.4], [1])


def test_wilson_interval_is_honest_about_small_samples():
    low_20, high_20 = wilson_interval(11, 20)
    low_500, high_500 = wilson_interval(275, 500)
    # Same hit rate, far wider interval on the smaller sample.
    assert (high_20 - low_20) > 3 * (high_500 - low_500)
    assert 0.0 <= low_20 < high_20 <= 1.0


def test_mismatched_lengths_are_an_error_not_a_zip_truncation():
    with pytest.raises(ValueError, match="same length"):
        brier_score([0.5, 0.5], [1])
