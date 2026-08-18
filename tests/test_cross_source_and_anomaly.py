"""Layers 2 and 3 — §5.2, §5.3."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gamesenze.qa.anomaly import (
    FixtureKey,
    check_coverage_gap,
    check_impossible_line,
    check_odds_frozen,
    check_odds_jump,
    check_xg_outlier,
    find_duplicate_fixtures,
)
from gamesenze.qa.cross_source import (
    CrossVerifier,
    VerificationReport,
    compare_kickoff,
    compare_player_minutes,
    compare_score,
    compare_starting_xi,
    compare_team_xg,
)
from gamesenze.qa.errors import Severity
from tests.conftest import FakeDb

KICKOFF = datetime(2026, 8, 20, 19, 0, tzinfo=UTC)


# --- Layer 2 ---------------------------------------------------------------

def test_score_requires_exact_agreement():
    assert compare_score((2, 1), (2, 1))
    disagreement = compare_score((2, 1), (2, 0))
    assert not disagreement
    assert "2-1" in disagreement.detail and "2-0" in disagreement.detail


def test_a_missing_source_is_a_disagreement_not_a_pass():
    # A source that should have covered a fact and did not is itself a signal.
    assert not compare_score((2, 1), None)
    assert not compare_kickoff(KICKOFF, None)


@pytest.mark.parametrize(
    ("minutes", "agree"), [(0, True), (15, True), (16, False), (120, False)]
)
def test_kickoff_tolerance_is_15_minutes(minutes, agree):
    assert bool(compare_kickoff(KICKOFF, KICKOFF + timedelta(minutes=minutes))) is agree


@pytest.mark.parametrize(("overlap", "agree"), [(11, True), (10, True), (9, True), (8, False)])
def test_starting_xi_needs_nine_of_eleven(overlap, agree):
    a = [str(i) for i in range(11)]
    b = a[:overlap] + [f"x{i}" for i in range(11 - overlap)]
    assert bool(compare_starting_xi(a, b)) is agree


@pytest.mark.parametrize(("delta", "agree"), [(0.0, True), (0.30, True), (0.31, False)])
def test_team_xg_tolerance_is_0_30(delta, agree):
    assert bool(compare_team_xg(1.40, 1.40 + delta)) is agree


@pytest.mark.parametrize(("delta", "agree"), [(0, True), (5, True), (6, False)])
def test_player_minutes_tolerance_is_5(delta, agree):
    assert bool(compare_player_minutes(78, 78 + delta)) is agree


def test_xg_disagreement_is_review_but_score_disagreement_blocks():
    # xG models differ by construction; scores do not.
    assert compare_team_xg(1.0, 2.0).severity is Severity.REVIEW
    assert compare_score((1, 0), (2, 0)).severity is Severity.BLOCK


async def test_mismatch_raises_a_flag_and_halts_settlement(clock):
    db = FakeDb()
    verifier = CrossVerifier(db, clock)

    report = await verifier.verify_fixture(
        "fix-1", {"score": (2, 1)}, {"score": (2, 0)}
    )

    assert not report.ok
    assert not report.settlement_allowed
    assert db.wrote("insert into qa_flags")
    assert await verifier.settle_if_verified("fix-1", report) is False


async def test_settlement_never_proceeds_on_a_single_source(clock):
    # REQ-QA-1. A report with no score check at all must not settle.
    verifier = CrossVerifier(FakeDb(), clock)
    empty = VerificationReport("fix-1")
    assert empty.settlement_allowed is False
    assert await verifier.settle_if_verified("fix-1", empty) is False


async def test_agreement_permits_settlement(clock):
    verifier = CrossVerifier(FakeDb(), clock)
    report = await verifier.verify_fixture(
        "fix-1", {"score": (2, 1)}, {"score": (2, 1)}
    )
    assert report.ok
    assert await verifier.settle_if_verified("fix-1", report) is True


# --- Layer 3 ---------------------------------------------------------------

def test_impossible_lines_are_rejected_outright():
    assert check_impossible_line(150).reject is True     # implies 0.67%
    assert check_impossible_line(1.005).reject is True   # implies 99.5%
    assert check_impossible_line(2.0) is None


def test_odds_jump_goes_to_review_never_auto_reject():
    # A 25% move might be a data error or the news the product exists to catch.
    anomaly = check_odds_jump(2.00, 2.50)
    assert anomaly.severity is Severity.REVIEW
    assert anomaly.reject is False
    assert check_odds_jump(2.00, 2.30) is None  # 15%, under the threshold


def test_frozen_odds_only_matter_when_there_is_news():
    now = datetime(2026, 8, 18, 12, tzinfo=UTC)
    stale = now - timedelta(hours=30)
    assert check_odds_frozen(stale, now, has_breaking_news=True) is not None
    assert check_odds_frozen(stale, now, has_breaking_news=False) is None


def test_xg_outliers_are_flagged_but_never_dropped():
    season = [1.1, 1.3, 0.9, 1.4, 1.2, 1.0]
    anomaly = check_xg_outlier(6.0, season)
    assert anomaly is not None
    assert anomaly.reject is False  # teams do have 4.5 xG afternoons
    assert check_xg_outlier(1.5, season) is None
    # Too few observations to have a distribution worth testing against.
    assert check_xg_outlier(9.0, [1.0, 1.2]) is None


def test_coverage_gap_measures_against_now_not_just_between_captures():
    # A feed that stopped four hours ago leaves a gap no pair of existing
    # timestamps reveals.
    captures = [KICKOFF - timedelta(hours=h) for h in (47, 42, 36, 30, 24, 20)]
    assert check_coverage_gap(captures, KICKOFF, KICKOFF - timedelta(hours=19)) is None
    assert (
        check_coverage_gap(captures, KICKOFF, KICKOFF - timedelta(hours=10))
        is not None
    )


def test_duplicate_fixtures_are_found_across_kickoff_drift():
    key = FixtureKey("home", "away", KICKOFF)
    drifted = FixtureKey("home", "away", KICKOFF + timedelta(hours=2))
    other = FixtureKey("home", "third", KICKOFF)

    duplicates = find_duplicate_fixtures([("1", key), ("2", drifted), ("3", other)])

    assert len(duplicates) == 1
    assert duplicates[0][:2] == ("2", "1")
