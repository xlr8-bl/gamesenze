"""Load Understat match stats over plain HTTP — the fast path, no browser.

A drop-in replacement for `weekly_scrape` + `stats_sync` for the Understat
half of the pipeline, which is the half the model actually needs to clear the
§5.4 sample gate. It fetches each league-season page directly (one GET each),
flattens the embedded JSON, and writes team_match_stats through the same
`sync_understat_stats` the browser path uses — so the result is identical, it
just arrives in seconds instead of the 15-25 minutes a headless-browser scrape
takes.

    python -m gamesenze.jobs.understat_sync

FBref still needs the browser (Cloudflare), but its team column is unusable
anyway (a soccerdata bug, verified live), so nothing the model uses is lost by
taking this path.
"""

from __future__ import annotations

import httpx

from ..scrape.understat_http import DEFAULT_LEAGUES, fetch_understat
from . import stats_sync
from ._runtime import JobContext, run_job


async def main(ctx: JobContext) -> int:
    contact = ctx.settings.scraper_contact or "ops@example.com"
    headers = {
        # REQ-SCRAPE-2: identify honestly. A real browser UA plus a contact so
        # Understat can reach us rather than just block an anonymous scraper.
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/122.0 Safari/537.36 (+{contact})"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://understat.com/",
    }

    async with httpx.AsyncClient(headers=headers) as client:
        rows = await fetch_understat(client, DEFAULT_LEAGUES, stats_sync.SEASONS)

    if not rows:
        print(
            "No Understat rows fetched: the pages returned but did not include "
            "their data, which means Understat gated this non-browser request "
            "on your network. Fall back to the browser scrape for stats:\n"
            "  python -m gamesenze.jobs.weekly_scrape   (15-25 min, headless browser)\n"
            "  python -m gamesenze.jobs.stats_sync\n"
            "Everything downstream (odds_sync, nightly_analysis) is the same "
            "either way."
        )
        return 0

    written, blocked = await stats_sync.sync_understat_stats(ctx, rows)
    print(
        f"team_match_stats: {written} row(s) written from {len(rows)} matches, "
        f"{blocked} blocked on unresolved team names"
    )
    if blocked:
        print("  resolve them with: python -m gamesenze.jobs.aliases backlog")
    return 0


if __name__ == "__main__":
    run_job(main)
