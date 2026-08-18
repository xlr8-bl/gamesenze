"""Layers 4 and 5 — §5.4, §5.5."""

from __future__ import annotations

import dataclasses

import pytest

from gamesenze.qa.gate import (
    MIN_FACTORS,
    PublicationContext,
    PublicationGate,
    failed_checks,
)
from gamesenze.qa.samples import Disposition, evaluate_factor, evaluate_factors
from tests.conftest import FakeDb


@pytest.fixture
def passing() -> PublicationContext:
    return PublicationContext(
        fixture_id="fix-1",
        pick_id="pick-1",
        odds_age_minutes=20,
        home_id="home",
        away_id="away",
        valid_factors=["form", "xg", "rest", "weather"],
        internal_prob=0.55,
        reasoning_full="x" * 250,
        stakes_tags=["run_in"],
        reviewed_by="ash",
    )


# --- Layer 4 ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("factor", "minimum"),
    [
        ("referee_tendency", 20),
        ("player_variance", 10),
        ("opponent_adjusted", 6),
        ("head_to_head", 4),
        ("nba_usage_redistribution", 3),
        ("manager_profile", 5),
    ],
)
def test_every_gate_minimum_matches_the_prd(factor, minimum):
    assert evaluate_factor(factor, minimum).disposition is not Disposition.EXCLUDED
    verdict = evaluate_factor(factor, minimum - 1)
    assert verdict.disposition is not Disposition.INCLUDED


def test_thin_samples_are_excluded_and_say_so_in_words():
    # REQ-QA-2: never silently drop a factor.
    verdict = evaluate_factor("referee_tendency", 11)
    assert verdict.disposition is Disposition.EXCLUDED
    assert verdict.message == (
        "Referee tendency sample too thin (11 matches at this level), "
        "excluded rather than forced."
    )


def test_manager_profile_is_provisional_rather_than_excluded():
    verdict = evaluate_factor("manager_profile", 3)
    assert verdict.disposition is Disposition.PROVISIONAL
    assert verdict.usable  # usable, but the UI carries the caveat


def test_unregistered_factors_cannot_be_used_at_all():
    with pytest.raises(ValueError, match="unknown factor"):
        evaluate_factor("vibes", 100)


def test_factor_set_separates_usable_from_excluded():
    result = evaluate_factors(
        {
            "referee_tendency": 11,
            "player_variance": 14,
            "opponent_adjusted": 6,
            "head_to_head": 2,
            "manager_profile": 3,
        }
    )
    assert result.valid == ["player_variance", "opponent_adjusted", "manager_profile"]
    assert {v.factor for v in result.excluded} == {"referee_tendency", "head_to_head"}
    # Everything not fully included is rendered to the reader.
    assert len(result.ui_blocks()) == 3


# --- Layer 5 ---------------------------------------------------------------

def test_a_complete_context_passes(passing):
    assert failed_checks(passing) == []


@pytest.mark.parametrize(
    ("field", "value", "check"),
    [
        ("blocking_flags", ["unresolved_team_name"], "no_blocking_qa_flags"),
        ("odds_age_minutes", 90, "odds_fresh"),
        ("odds_age_minutes", None, "odds_fresh"),
        ("home_id", None, "teams_resolved"),
        ("away_id", None, "teams_resolved"),
        ("valid_factors", ["a", "b", "c"], "min_factors_present"),
        ("internal_prob", 0.995, "internal_prob_set"),
        ("internal_prob", None, "internal_prob_set"),
        ("reasoning_full", "x" * 200, "reasoning_present"),
        ("stakes_tags", None, "stakes_computed"),
        ("reviewed_by", None, "human_reviewed"),
        ("budget_permits_publication", False, "budget_permits_publication"),
    ],
)
def test_each_check_blocks_on_its_own(passing, field, value, check):
    context = dataclasses.replace(passing, **{field: value})
    assert failed_checks(context) == [check]


def test_min_factors_is_four(passing):
    assert MIN_FACTORS == 4
    assert failed_checks(dataclasses.replace(passing, valid_factors=["a"] * 4)) == []


def test_human_review_is_mandatory(passing):
    # REQ-QA-3: the last line of defence against a plausible-looking pipeline
    # error reaching subscribers.
    unreviewed = dataclasses.replace(passing, reviewed_by=None)
    assert "human_reviewed" in failed_checks(unreviewed)


async def test_blocked_picks_are_recorded_not_silently_dropped(clock, passing):
    db = FakeDb()
    gate = PublicationGate(db, clock)
    context = dataclasses.replace(passing, reviewed_by=None, odds_age_minutes=200)

    assert await gate.publish(context) is False

    blocks = db.writes_matching("insert into publication_blocks")
    assert len(blocks) == 1
    assert sorted(blocks[0][1][2]) == ["human_reviewed", "odds_fresh"]
    assert db.wrote("update picks set status = 'blocked'")
    assert not db.wrote("status = 'published'")


async def test_publishing_requires_passing_the_gate(clock, passing):
    db = FakeDb()
    assert await PublicationGate(db, clock).publish(passing) is True
    assert db.wrote("set status = 'published'")
    assert not db.wrote("insert into publication_blocks")
