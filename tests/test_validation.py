"""Layer 1 — §5.1. Fail closed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gamesenze.qa.errors import QAViolation
from gamesenze.qa.validation import (
    RULES,
    validate_batch,
    validate_or_reject,
    validate_record_type,
)

NOW = datetime(2026, 8, 18, tzinfo=UTC)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decimal_odds", 1.01),
        ("decimal_odds", 1000.0),
        ("xg", 0.0),
        ("xg", 10.0),
        ("minutes", 0),
        ("minutes", 120),
        ("ppda", 1.0),
        ("ppda", 60.0),
        ("corners", 0),
        ("corners", 30),
        ("player_age", 15),
        ("player_age", 50),
    ],
)
def test_boundaries_are_inclusive(field, value):
    assert validate_or_reject({field: value}, RULES, now=NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decimal_odds", 1.009),
        ("decimal_odds", 1000.1),
        ("xg", -0.1),
        ("xg", 10.1),
        ("minutes", -1),
        ("minutes", 121),
        ("ppda", 0.99),
        ("ppda", 60.1),
        ("corners", 31),
        ("player_age", 14),
        ("player_age", 51),
    ],
)
def test_out_of_range_is_rejected(field, value):
    with pytest.raises(QAViolation) as exc:
        validate_or_reject({field: value}, RULES, now=NOW)
    assert exc.value.issue == "range_violation"


def test_missing_required_field_is_a_violation_not_a_default():
    # A None xG silently becoming 0.0 is the class of error that produces a
    # confident, wrong number downstream.
    with pytest.raises(QAViolation) as exc:
        validate_record_type({"xg": None, "xga": 1.0}, "team_match_stats", now=NOW)
    assert exc.value.issue == "missing_field"


def test_strings_that_look_numeric_are_rejected():
    with pytest.raises(QAViolation) as exc:
        validate_record_type({"decimal_odds": "2.50"}, "odds", now=NOW)
    assert exc.value.issue == "type_violation"


def test_booleans_are_not_numbers():
    with pytest.raises(QAViolation):
        validate_or_reject({"corners": True}, RULES, now=NOW)


def test_kickoff_must_be_within_180_days_and_aware():
    assert validate_record_type(
        {"kickoff_at": NOW + timedelta(days=179)}, "fixture", now=NOW
    )
    with pytest.raises(QAViolation):
        validate_record_type(
            {"kickoff_at": NOW + timedelta(days=181)}, "fixture", now=NOW
        )
    with pytest.raises(QAViolation) as exc:
        validate_record_type(
            {"kickoff_at": datetime(2026, 8, 19)}, "fixture", now=NOW
        )
    assert exc.value.issue == "type_violation"


def test_batch_keeps_good_rows_and_reports_bad_ones():
    outcome = validate_batch(
        [
            {"xg": 1.2, "xga": 0.8},
            {"xg": 44.0, "xga": 1.0},
            {"xg": 0.4, "xga": 2.2},
        ],
        "team_match_stats",
        now=NOW,
    )
    assert len(outcome.accepted) == 2
    assert len(outcome.rejected) == 1
    assert outcome.reject_rate == pytest.approx(1 / 3)
    _, violation = outcome.rejected[0]
    assert "44.0" in str(violation)
