"""Weekly and monthly scrapes — §4.1.

`soccerdata` is imported lazily and its internal rate limiting is left alone
(REQ-SCRAPE-1 says do not override it). Each job stores raw before it parses,
skips work when the content hash is unchanged (REQ-SCRAPE-3), and records a
`scrape_runs` row either way so the daily audit can see a failure that produced
no exception anyone was watching.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..clock import Clock, SystemClock
from ..config import user_agent
from ..db import Db
from .provenance import RawStore, scrape_run
from .throttle import off_peak_now

log = logging.getLogger("gamesenze.scrape")


@dataclass
class ScrapeResult:
    source: str
    job: str
    rows: list[dict[str, Any]]
    skipped_unchanged: bool = False


class SoccerDataScraper:
    """Thin wrapper so jobs stay testable without the library installed."""

    def __init__(
        self,
        db: Db,
        *,
        contact: str,
        clock: Clock | None = None,
        loader: Callable[..., Any] | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._raw = RawStore(db, clock)
        self._contact = contact
        self._user_agent = user_agent(contact)
        self._loader = loader

    def _soccerdata(self):
        if self._loader is not None:
            return self._loader
        import soccerdata  # noqa: PLC0415 - lazy by design

        return soccerdata

    def _warn_if_on_peak(self, job: str) -> None:
        if not off_peak_now(self._clock.now()):
            log.warning(
                "%s running outside the 03:00-06:00 UTC window (REQ-SCRAPE-4)", job
            )

    async def understat(self, leagues: list[str], seasons: list[str]) -> ScrapeResult:
        """xG, xGA, PPDA, game-state and formation splits, shot coordinates."""
        return await self._run("understat", "team_match_stats", leagues, seasons)

    async def fbref(self, leagues: list[str], seasons: list[str]) -> ScrapeResult:
        """Progressive passes/carries, defensive actions, per-90 match logs."""
        return await self._run("fbref", "team_match_stats", leagues, seasons)

    async def sofifa(self, leagues: list[str], seasons: list[str]) -> ScrapeResult:
        """Player quality ratings and attribute sub-ratings. Monthly."""
        return await self._run("sofifa", "player_ratings", leagues, seasons)

    async def _run(
        self, source: str, job: str, leagues: list[str], seasons: list[str]
    ) -> ScrapeResult:
        self._warn_if_on_peak(job)
        async with scrape_run(self._db, source, job, self._clock) as run:
            sd = self._soccerdata()
            reader = _reader_for(sd, source, leagues, seasons)
            frame = reader.read_team_match_stats() if hasattr(
                reader, "read_team_match_stats"
            ) else reader.read_player_season_stats()

            payload = _frame_to_records(frame)
            entity_ref = f"{source}:{','.join(leagues)}:{','.join(seasons)}"
            digest = await self._raw.store(
                source, job, payload, entity_ref=entity_ref
            )

            if await self._raw.unchanged_since_last(source, entity_ref, digest):
                log.info("%s unchanged since last fetch, skipping parse", entity_ref)
                return ScrapeResult(source, job, [], skipped_unchanged=True)

            run.rows_written = len(payload)
            return ScrapeResult(source, job, payload)


def _reader_for(sd: Any, source: str, leagues: list[str], seasons: list[str]) -> Any:
    readers = {
        "understat": lambda: sd.Understat(leagues=leagues, seasons=seasons),
        "fbref": lambda: sd.FBref(leagues=leagues, seasons=seasons),
        "sofifa": lambda: sd.SoFIFA(leagues=leagues, seasons=seasons),
    }
    try:
        return readers[source]()
    except KeyError:
        raise ValueError(f"no soccerdata reader for {source!r}") from None


def _frame_to_records(frame: Any) -> list[dict[str, Any]]:
    """DataFrame -> plain records, so nothing downstream needs pandas."""
    if hasattr(frame, "reset_index"):
        frame = frame.reset_index()
    if hasattr(frame, "to_dict"):
        return frame.to_dict(orient="records")
    return list(frame)
