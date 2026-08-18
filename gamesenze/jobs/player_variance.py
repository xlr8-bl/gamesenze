"""Weekly player variance refresh — §3.5 (15 min weekly).

Mean and standard deviation per 90 for each player, gated at 10 appearances of
45+ minutes (§5.4). Players below the gate get no row at all rather than a row
with a wide error bar: a factor that exists is a factor someone will use.
"""

from __future__ import annotations

from ..qa.samples import GATES
from ._runtime import JobContext, run_job


async def main(ctx: JobContext) -> int:
    minimum = GATES["player_variance"].minimum

    rows = await ctx.db.fetch(
        """
        select player_id,
               count(*)                                as appearances,
               avg(goals + assists)                    as mean_ga,
               coalesce(stddev_pop(goals + assists), 0) as sd_ga,
               avg(shots)                              as mean_shots
          from player_match_stats
         where minutes >= 45 and kickoff_at < now()
         group by player_id
        having count(*) >= $1
        """,
        minimum,
    )

    for r in rows:
        await ctx.db.execute(
            """
            insert into player_variance (player_id, appearances, mean_ga, sd_ga,
                                         mean_shots, computed_at)
            values ($1, $2, $3, $4, $5, $6)
            on conflict (player_id) do update
                set appearances = excluded.appearances,
                    mean_ga     = excluded.mean_ga,
                    sd_ga       = excluded.sd_ga,
                    mean_shots  = excluded.mean_shots,
                    computed_at = excluded.computed_at
            """,
            r["player_id"],
            r["appearances"],
            r["mean_ga"],
            r["sd_ga"],
            r["mean_shots"],
            ctx.clock.now(),
        )

    print(f"refreshed variance for {len(rows)} player(s) at/above the "
          f"{minimum}-appearance gate")
    return 0


if __name__ == "__main__":
    run_job(main)
