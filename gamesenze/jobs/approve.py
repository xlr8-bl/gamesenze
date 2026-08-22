"""Human review and publish — the last step before a pick reaches the board.

REQ-QA-3: nothing auto-publishes. nightly_analysis drafts; a person reads each
draft and signs it off here. This job is that signature. It assembles the full
publication context for each draft, runs the same gate the system enforces
(fresh odds, resolved teams, enough factors, real reasoning, budget headroom,
and a named reviewer), and only then flips the pick to 'published'.

    # See what is waiting and whether each draft would pass the gate:
    python -m gamesenze.jobs.approve

    # Sign off and publish everything that passes, under your name:
    python -m gamesenze.jobs.approve --all --reviewer "Ashley"

    # Or one pick:
    python -m gamesenze.jobs.approve --id <pick-id> --reviewer "Ashley"

A draft that fails a check is reported with the reasons and left as a draft
(not blocked) so it can be fixed and re-tried — except when you name a reviewer
and it still fails a *content* check, in which case the gate records the block.
"""

from __future__ import annotations

import sys

from ..degrade import policy_from_statuses
from ..qa.gate import PublicationContext, PublicationGate, failed_checks
from ._runtime import JobContext, run_job


def _arg(flag: str) -> str | None:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


async def _context_for(ctx: JobContext, pick, *, reviewer: str | None,
                       budget_ok: bool) -> PublicationContext:
    flags = await ctx.db.fetch(
        "select id from qa_flags where entity_type = 'fixture' "
        "and entity_id = $1 and severity = 'block' and resolved_at is null",
        pick["fixture_id"],
    )
    age_min = None
    if pick["captured_at"] is not None:
        age_min = (ctx.clock.now() - pick["captured_at"]).total_seconds() / 60.0

    return PublicationContext(
        fixture_id=str(pick["fixture_id"]),
        pick_id=str(pick["id"]),
        blocking_flags=list(flags),
        odds_age_minutes=age_min,
        home_id=str(pick["home_team_id"]) if pick["home_team_id"] else None,
        away_id=str(pick["away_team_id"]) if pick["away_team_id"] else None,
        valid_factors=pick["valid_factors"] or [],
        internal_prob=float(pick["internal_prob"]) if pick["internal_prob"] is not None else None,
        reasoning_full=pick["reasoning_full"] or "",
        stakes_tags=pick["stakes_tags"],
        reviewed_by=reviewer,
        budget_permits_publication=budget_ok,
    )


async def main(ctx: JobContext) -> int:
    reviewer = _arg("--reviewer")
    one_id = _arg("--id")
    publish_all = "--all" in sys.argv

    policy = policy_from_statuses(await ctx.meter.all_statuses())
    budget_ok = policy.may_publish

    where = "p.status = 'draft'"
    args: list = []
    if one_id:
        where += " and p.id = $1"
        args = [one_id]

    drafts = await ctx.db.fetch(
        f"""
        select p.id, p.fixture_id, p.market, p.selection, p.internal_prob,
               p.capture_odds, p.captured_at, p.reasoning_full, p.valid_factors,
               p.stakes_tags, f.home_team_id, f.away_team_id, f.kickoff_at,
               ht.canonical_name as home, at.canonical_name as away
          from picks p
          join fixtures f on f.id = p.fixture_id
          left join teams ht on ht.id = f.home_team_id
          left join teams at on at.id = f.away_team_id
         where {where}
         order by f.kickoff_at
        """,
        *args,
    )

    if not drafts:
        print("nothing awaiting review")
        return 0

    gate = PublicationGate(ctx.db, ctx.clock)
    published = 0

    # Preview mode: no reviewer named, so we only report the gate status.
    if not reviewer:
        print(f"{len(drafts)} draft(s). Gate status (run with --reviewer to publish):\n")
        for d in drafts:
            ctx_obj = await _context_for(ctx, d, reviewer="preview", budget_ok=budget_ok)
            failed = failed_checks(ctx_obj)
            mark = "READY" if not failed else "blocked: " + ", ".join(failed)
            print(f"  {d['kickoff_at']:%m-%d %H:%M}  {d['home']} v {d['away']}  "
                  f"— {d['selection']} @ {d['capture_odds']}  [{mark}]")
        print("\nName a reviewer to sign these off, e.g. --all --reviewer \"Your Name\"")
        return 0

    if not (publish_all or one_id):
        print("Refusing to publish without --all or --id. "
              "Run with no flags to preview the queue first.")
        return 1

    for d in drafts:
        ctx_obj = await _context_for(ctx, d, reviewer=reviewer, budget_ok=budget_ok)
        failed = failed_checks(ctx_obj)
        if failed:
            # Leave it a draft, not blocked: a stale-odds or thin-factor miss
            # is fixable (re-run odds_sync, wait for the sample) and should be
            # retryable rather than struck off.
            print(f"  held       {d['home']} v {d['away']} — {', '.join(failed)}")
            continue

        await gate.publish(ctx_obj)  # passes the gate; flips to 'published'
        await ctx.db.execute(
            "update picks set reviewed_by = $2, reviewed_at = $3 where id = $1",
            d["id"], reviewer, ctx.clock.now(),
        )
        published += 1
        print(f"  published  {d['home']} v {d['away']} — {d['selection']} @ {d['capture_odds']}")

    print(f"\n{published} pick(s) published, {len(drafts) - published} held")
    return 0


if __name__ == "__main__":
    run_job(main)
