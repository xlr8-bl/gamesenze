"""What is waiting for a human — REQ-QA-3.

§9.7: manual review is a real time cost, roughly 20-30 minutes daily, and it is
the binding constraint on volume rather than compute. This prints the queue so
that time is spent reading picks rather than finding them.
"""

from __future__ import annotations

from ..qa.gate import MIN_FACTORS
from ._runtime import JobContext, run_job


async def main(ctx: JobContext) -> int:
    drafts = await ctx.db.fetch(
        """
        select p.id, p.market, p.selection, p.internal_prob, p.capture_odds,
               p.valid_factors, f.kickoff_at,
               ht.canonical_name as home, at.canonical_name as away
          from picks p
          join fixtures f on f.id = p.fixture_id
          left join teams ht on ht.id = f.home_team_id
          left join teams at on at.id = f.away_team_id
         where p.status = 'draft'
         order by f.kickoff_at
        """
    )

    if not drafts:
        print("nothing awaiting review")
        return 0

    print(f"{len(drafts)} pick(s) awaiting review\n")
    for d in drafts:
        factors = d["valid_factors"] or []
        short = " [BELOW FACTOR MINIMUM]" if len(factors) < MIN_FACTORS else ""
        print(
            f"  {d['kickoff_at']:%Y-%m-%d %H:%M}  {d['home']} v {d['away']}\n"
            f"    {d['market']} {d['selection']} @ {d['capture_odds']} "
            f"(our number {float(d['internal_prob']):.1%})\n"
            f"    factors: {', '.join(factors) or 'none'}{short}\n"
        )

    blocked = await ctx.db.fetch(
        "select failed_checks, count(*) as n from publication_blocks "
        "where blocked_at > now() - interval '24 hours' group by 1"
    )
    if blocked:
        print("blocked in the last 24h:")
        for b in blocked:
            print(f"  {b['n']}x {', '.join(b['failed_checks'])}")
    return 0


if __name__ == "__main__":
    run_job(main)
