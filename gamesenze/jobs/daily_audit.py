"""Layer 6, on a schedule — §5.6."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from ..qa.audit import daily_audit
from ._runtime import JobContext, run_job


async def main(ctx: JobContext) -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
    audit_date = (
        date.fromisoformat(arg) if arg else date.today() - timedelta(days=1)
    )

    report = await daily_audit(
        ctx.db, audit_date, alerter=ctx.alerter, meter=ctx.meter
    )
    print(json.dumps(report.to_dict(), indent=2))

    # Unresolved blocking flags are not a "warning" — they mean the next
    # publication cycle must not run until a person has looked. Exit non-zero
    # so the workflow is visibly red rather than green-with-an-alert.
    blocking = int(
        await ctx.db.fetchval(
            "select count(*) from qa_flags where resolved_at is null "
            "and severity = 'block'"
        )
        or 0
    )
    if blocking:
        print(f"{blocking} unresolved BLOCKING flag(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    run_job(main)
