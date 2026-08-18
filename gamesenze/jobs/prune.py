"""Storage hygiene — §7 and §9.4.

Pruning is mandatory, not housekeeping: 500MB fills, and it fills fastest
through `data_provenance.raw_response`. The metadata row survives the prune —
"we fetched this on the 3rd and the hash was X" stays useful after the body is
gone and costs almost nothing.
"""

from __future__ import annotations

from ..config import PROVENANCE_RETENTION_DAYS, SUPABASE_ALERT_MB, SUPABASE_LIMIT_MB
from ..scrape.provenance import RawStore
from ._runtime import JobContext, run_job


async def main(ctx: JobContext) -> int:
    pruned = await RawStore(ctx.db, ctx.clock).prune(PROVENANCE_RETENTION_DAYS)
    print(f"pruned {pruned} raw responses older than {PROVENANCE_RETENTION_DAYS} days")

    size_mb = float(
        await ctx.db.fetchval(
            "select pg_database_size(current_database()) / 1024.0 / 1024.0"
        )
        or 0
    )
    print(f"database size: {size_mb:.1f}MB of {SUPABASE_LIMIT_MB}MB")

    if size_mb >= SUPABASE_ALERT_MB:
        ctx.alerter.alert(
            f"Supabase at {size_mb:.0f}MB of {SUPABASE_LIMIT_MB}MB — "
            "emergency prune territory",
            size_mb=round(size_mb, 1),
        )
        return 1
    return 0


if __name__ == "__main__":
    run_job(main)
