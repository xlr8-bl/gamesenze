"""QA exception types."""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    BLOCK = "block"    # nothing downstream may proceed
    REVIEW = "review"  # a human decides; ambiguity is never auto-resolved
    INFO = "info"      # recorded for the audit, no action


class QAViolation(Exception):
    """A rule was broken. Carries enough detail to act without re-deriving it."""

    def __init__(
        self,
        message: str,
        *,
        severity: Severity | str = Severity.BLOCK,
        field: str | None = None,
        issue: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.severity = Severity(severity)
        self.field = field
        self.issue = issue or "validation_failed"
