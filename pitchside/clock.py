"""Time, injectable.

Every point-in-time guarantee in §5.7 depends on "now" being something a test
can control. Modules take a `Clock` rather than calling `datetime.now()`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Fixed clock for tests and for backtests, where "now" is a past moment."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FrozenClock requires an aware datetime")
        self._at = at

    def now(self) -> datetime:
        return self._at

    def advance(self, **kwargs) -> None:
        from datetime import timedelta

        self._at = self._at + timedelta(**kwargs)


def utcnow() -> datetime:
    return datetime.now(UTC)
