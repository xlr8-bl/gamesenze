"""Layer 1 — ingestion validation (§5.1).

Every record is validated on arrival against range and type rules. Fail closed:
a rejected record never reaches analysis. Rejecting a row costs us one row;
accepting a corrupt one costs us a pick, and eventually the track record.

Missing is a violation, not a default. A `None` xG silently becoming 0.0 is
exactly the class of error that produces a confident, wrong number downstream.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..clock import utcnow
from .errors import QAViolation, Severity


class Rule:
    field: str

    def check(self, value: Any, now: datetime) -> None:  # pragma: no cover
        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover
        raise NotImplementedError


@dataclass(frozen=True)
class NumericRange(Rule):
    field: str
    lo: float
    hi: float

    def check(self, value: Any, now: datetime) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise QAViolation(
                f"{self.field}={value!r} is not numeric",
                field=self.field,
                issue="type_violation",
            )
        if not (self.lo <= value <= self.hi):
            raise QAViolation(
                f"{self.field}={value} outside [{self.lo}, {self.hi}]",
                field=self.field,
                issue="range_violation",
            )

    def describe(self) -> str:
        return f"{self.lo} - {self.hi}"


@dataclass(frozen=True)
class TemporalWindow(Rule):
    """Bounds relative to now — a kickoff two years out is a parsing error."""

    field: str
    days: int

    def check(self, value: Any, now: datetime) -> None:
        if not isinstance(value, datetime):
            raise QAViolation(
                f"{self.field}={value!r} is not a datetime",
                field=self.field,
                issue="type_violation",
            )
        if value.tzinfo is None:
            raise QAViolation(
                f"{self.field} is naive; all timestamps must be UTC-aware",
                field=self.field,
                issue="type_violation",
            )
        delta = abs(value - now)
        if delta > timedelta(days=self.days):
            raise QAViolation(
                f"{self.field}={value.isoformat()} is more than {self.days} "
                f"days from now",
                field=self.field,
                issue="range_violation",
            )

    def describe(self) -> str:
        return f"within +/-{self.days} days"


# The table from §5.1, verbatim.
RULES: dict[str, Rule] = {
    "decimal_odds": NumericRange("decimal_odds", 1.01, 1000.0),
    "xg": NumericRange("xg", 0.0, 10.0),
    "xga": NumericRange("xga", 0.0, 10.0),
    "minutes": NumericRange("minutes", 0, 120),
    "ppda": NumericRange("ppda", 1.0, 60.0),
    "corners": NumericRange("corners", 0, 30),
    "kickoff_at": TemporalWindow("kickoff_at", 180),
    "player_age": NumericRange("player_age", 15, 50),
}

# Which fields each record type must carry. A field absent from the record is
# a violation when it is listed here, and ignored when it is not — that keeps
# partial records (an odds row has no xG) from failing for the wrong reason.
RECORD_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "odds": ("decimal_odds",),
    "fixture": ("kickoff_at",),
    "team_match_stats": ("xg", "xga"),
    "player_match_stats": ("minutes",),
}


def validate_or_reject(
    record: Mapping[str, Any],
    rules: Mapping[str, Rule] | Iterable[str] | None = None,
    *,
    required: Iterable[str] = (),
    now: datetime | None = None,
) -> Mapping[str, Any]:
    """Fail closed. A rejected record never reaches analysis.

    Fields present in `record` and known to `rules` are range-checked. Fields
    in `required` must additionally be present and non-null.
    """
    now = now or utcnow()

    if rules is None:
        active: Mapping[str, Rule] = RULES
    elif isinstance(rules, Mapping):
        active = rules
    else:  # an iterable of field names
        active = {name: RULES[name] for name in rules}

    for field in required:
        if record.get(field) is None:
            raise QAViolation(
                f"{field} missing",
                severity=Severity.BLOCK,
                field=field,
                issue="missing_field",
            )

    for field, rule in active.items():
        if field not in record:
            continue
        value = record[field]
        if value is None:
            if field in required:
                raise QAViolation(
                    f"{field} missing",
                    field=field,
                    issue="missing_field",
                )
            continue
        rule.check(value, now)

    return record


def validate_record_type(
    record: Mapping[str, Any], record_type: str, *, now: datetime | None = None
) -> Mapping[str, Any]:
    """Validate against the requirements registered for a record type."""
    required = RECORD_REQUIREMENTS.get(record_type, ())
    return validate_or_reject(record, RULES, required=required, now=now)


@dataclass
class ValidationOutcome:
    accepted: list[Mapping[str, Any]]
    rejected: list[tuple[Mapping[str, Any], QAViolation]]

    @property
    def reject_rate(self) -> float:
        total = len(self.accepted) + len(self.rejected)
        return 0.0 if total == 0 else len(self.rejected) / total


def validate_batch(
    records: Iterable[Mapping[str, Any]],
    record_type: str,
    *,
    now: datetime | None = None,
) -> ValidationOutcome:
    """Validate a batch, keeping rejects with their reason for the audit.

    Batch validation does not abort on the first bad row: one malformed record
    in a fixture list should not cost us the other nineteen. The rejects are
    returned rather than logged and forgotten, so the caller can flag them.
    """
    accepted: list[Mapping[str, Any]] = []
    rejected: list[tuple[Mapping[str, Any], QAViolation]] = []
    for record in records:
        try:
            accepted.append(validate_record_type(record, record_type, now=now))
        except QAViolation as exc:
            rejected.append((record, exc))
    return ValidationOutcome(accepted, rejected)
