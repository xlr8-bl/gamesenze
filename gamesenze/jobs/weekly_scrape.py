"""Weekly Understat + FBref scrape — §4.1, §3.5 (25 min weekly)."""

from __future__ import annotations

import logging

from ..scrape.soccerdata_jobs import SoccerDataScraper
from . import stats_sync
from ._runtime import JobContext, run_job

log = logging.getLogger("gamesenze.scrape")

LEAGUES = list(stats_sync.LEAGUE_NAMES.keys())
SEASONS = stats_sync.SEASONS


async def main(ctx: JobContext) -> int:
    scraper = SoccerDataScraper(
        ctx.db, contact=ctx.settings.scraper_contact, clock=ctx.clock
    )

    failures = 0
    for name, fetch in (
        ("understat", scraper.understat),
        ("fbref", scraper.fbref),
    ):
        try:
            result = await fetch(LEAGUES, SEASONS)
            if result.skipped_unchanged:
                log.info("%s unchanged since last week (REQ-SCRAPE-3)", name)
            else:
                log.info("%s: %d rows", name, len(result.rows))

            # FBref has no team_match_stats parser yet — a live check found
            # its `team` column coming back empty for every row, a bug in
            # soccerdata's FBref reader. See jobs/stats_sync.py's module
            # docstring.
            if name == "understat":
                written, unresolved = await stats_sync.sync_from_scrape_result(
                    ctx, scraper, result, leagues=LEAGUES, seasons=SEASONS
                )
                log.info(
                    "team_match_stats: %d row(s) written, %d side(s) unresolved",
                    written,
                    unresolved,
                )
        except Exception as exc:  # noqa: BLE001
            # §8: a scrape failure falls back to cached data with its age shown
            # in the UI. It does not stop the other source from running.
            failures += 1
            log.error("%s scrape failed: %s", name, exc)
            ctx.alerter.alert(f"{name} scrape failed: {exc}", source=name)

    return 1 if failures else 0


if __name__ == "__main__":
    run_job(main)
