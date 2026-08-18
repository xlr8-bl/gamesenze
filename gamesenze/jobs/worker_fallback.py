"""GitHub Actions fallback for the Cloudflare Worker — §8.

The Worker fires this when a tick errors, and it also runs hourly as a backstop
for the case where the Worker is not running at all.

It does not pretend to be on time. A capture whose window has closed is
recorded as missed rather than backfilled with a late price wearing an on-time
timestamp — a snapshot series with a lie in it is worse than one with a gap,
because the gap is visible to §5.3's coverage-gap check and the lie is not.
"""

from __future__ import annotations

import asyncio
import logging

from ..budget import BudgetExhausted
from ..config import FALLBACK_MAX_CATCHUP, min_seconds_between_calls
from ..degrade import policy_from_statuses
from ..providers.sgo import SportsGameOdds
from ._runtime import JobContext, run_job

log = logging.getLogger("gamesenze.fallback")

# The Worker may be mid-tick while this runs, and both draw on the same
# 10 requests/minute. The split lives in config so the two halves cannot drift
# apart into a combined burst that earns a 429 — which would cost us objects
# and return no prices.
MAX_CATCHUP = FALLBACK_MAX_CATCHUP


async def main(ctx: JobContext) -> int:
    policy = policy_from_statuses(await ctx.meter.all_statuses())
    if not policy.may_snapshot:
        log.info("budget exhausted; no catch-up captures (§8)")
        return 0

    due = await ctx.db.fetch(
        "select * from due_odds_snapshots(now(), 60, $1)", MAX_CATCHUP
    )
    if not due:
        print("nothing due; Worker is keeping up")
        return 0

    log.warning(
        "%d capture(s) still due at fallback time — the Worker missed them", len(due)
    )

    client = SportsGameOdds(
        ctx.settings.sportsgameodds_key, db=ctx.db, meter=ctx.meter, clock=ctx.clock
    )
    captured = 0
    pace = min_seconds_between_calls("sportsgameodds")
    for index, row in enumerate(due):
        if index and pace:
            await asyncio.sleep(pace)
        try:
            response = await client.event_odds(
                str(row["fixture_id"]),
                row["vendor_event_id"],
                window_label=row["window_label"],
            )
        except BudgetExhausted:
            log.warning("budget exhausted mid-catch-up; stopping")
            break
        except Exception as exc:  # noqa: BLE001
            log.error("fixture %s: %s", row["fixture_id"], exc)
            continue

        import json

        await ctx.db.execute(
            """
            insert into odds_ingest_queue (fixture_id, window_label, payload)
            values ($1, $2, $3)
            """,
            row["fixture_id"],
            row["window_label"],
            json.dumps(response.body),
        )
        captured += 1

    ctx.alerter.alert(
        f"Worker fallback captured {captured} of {len(due)} missed snapshot(s)",
        due=len(due),
    )
    print(f"captured {captured} of {len(due)}")
    return 0


if __name__ == "__main__":
    run_job(main)
