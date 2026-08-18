"""Collection discipline — REQ-SCRAPE-1 and REQ-SCRAPE-4.

Minimum 6 seconds between requests to any single host. `soccerdata` enforces
delays internally and we do not override them; this throttle covers the direct
fetches (Transfermarkt) and acts as a second belt for everything else.

The politeness is not decorative. §4.2 and REQ-SCRAPE-6 both rest on us being a
well-behaved client of sources we depend on and have no contract with.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from ..config import SCRAPE_MIN_INTERVAL_SECONDS, SCRAPE_WINDOW_UTC


class HostThrottle:
    """Per-host minimum interval, safe across concurrent tasks."""

    def __init__(
        self,
        min_interval: float = SCRAPE_MIN_INTERVAL_SECONDS,
        *,
        monotonic=time.monotonic,
        sleep=asyncio.sleep,
    ) -> None:
        if min_interval < SCRAPE_MIN_INTERVAL_SECONDS:
            raise ValueError(
                f"min_interval {min_interval}s is below the {SCRAPE_MIN_INTERVAL_SECONDS}s "
                "floor in REQ-SCRAPE-1"
            )
        self._min_interval = min_interval
        self._monotonic = monotonic
        self._sleep = sleep
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _host(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    async def acquire(self, url: str) -> float:
        """Wait until this host may be called again. Returns seconds waited."""
        host = self._host(url)
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = self._monotonic()
            last = self._last.get(host)
            waited = 0.0
            if last is not None:
                elapsed = now - last
                if elapsed < self._min_interval:
                    waited = self._min_interval - elapsed
                    await self._sleep(waited)
            self._last[host] = self._monotonic()
            return waited


def off_peak_now(now: datetime | None = None) -> bool:
    """REQ-SCRAPE-4: 03:00-06:00 UTC, to minimise load on sources.

    Advisory rather than enforced — a manual re-run after a failed nightly
    should not be blocked at 09:00 — but the scrape jobs log when they run
    outside the window so drift is visible.
    """
    now = now or datetime.now(UTC)
    start, end = SCRAPE_WINDOW_UTC
    return start <= now.hour < end
