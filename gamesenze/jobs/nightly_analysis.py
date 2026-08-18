"""Nightly analysis — §3.5, 4 minutes daily.

Drafts picks. Publishes nothing: REQ-QA-3 means a person reads every pick
before it goes out, so this job's output is a review queue, not a board.
"""

from __future__ import annotations

import json
import logging

from ..analysis.model import MatchModel
from ..backtest.features import get_features_as_of
from ..coverage import CoverageController
from ..degrade import policy_from_statuses
from ..odds.math import edge
from ..qa.samples import evaluate_factors
from ._runtime import JobContext, run_job

log = logging.getLogger("gamesenze.nightly")

EDGE_THRESHOLD = 0.04  # 4% over the price before a pick is worth drafting


async def main(ctx: JobContext) -> int:
    policy = policy_from_statuses(await ctx.meter.all_statuses())
    log.info("degradation rung: %s", policy.rung.value)

    if not policy.may_publish:
        # §8 at 100%: serve last-known with a visible timestamp, publish no new
        # picks. Drafting them anyway would only build a queue we cannot price.
        ctx.alerter.alert(
            "Request budget exhausted — no picks drafted tonight (§8)."
        )
        return 0

    coverage = CoverageController(ctx.db, ctx.meter)
    model = MatchModel()
    drafted = 0

    candidates = await ctx.db.fetch(
        """
        select f.id, f.sport, f.kickoff_at, f.home_team_id, f.away_team_id,
               o.market, o.selection, o.decimal_odds, o.bookmaker, o.captured_at
          from fixtures f
          join lateral (
              select market, selection, decimal_odds, bookmaker, captured_at
                from odds_snapshots
               where fixture_id = f.id
               order by captured_at desc
               limit 20
          ) o on true
         where f.status = 'scheduled'
           and f.kickoff_at between now() and now() + interval '48 hours'
           and f.home_team_id is not null
           and f.away_team_id is not null
           and not exists (
               select 1 from qa_flags q
                where q.entity_type = 'fixture' and q.entity_id = f.id
                  and q.severity = 'block' and q.resolved_at is null
           )
        """
    )

    for row in candidates:
        as_of = row["kickoff_at"]
        home = await get_features_as_of(ctx.db, str(row["home_team_id"]), as_of)
        away = await get_features_as_of(ctx.db, str(row["away_team_id"]), as_of)
        if home is None or away is None:
            log.info("fixture %s: sample below the §5.4 minimum, skipping", row["id"])
            continue

        prices = model.price(home, away)
        our_prob = prices.probability(row["market"], row["selection"])
        if our_prob is None:
            continue

        our_edge = edge(our_prob, float(row["decimal_odds"]))
        if our_edge < EDGE_THRESHOLD:
            continue

        decision = await coverage.can_cover(row["sport"], policy=policy)
        if not decision.admitted:
            log.info("fixture %s not admitted: %s", row["id"], decision.reason)
            continue

        factors = await _factor_counts(ctx, row)
        factor_set = evaluate_factors(factors)

        await ctx.db.execute(
            """
            insert into picks (fixture_id, market, selection, internal_prob,
                               capture_odds, capture_bookmaker, captured_at,
                               valid_factors, excluded_factors, status)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft')
            """,
            row["id"],
            row["market"],
            row["selection"],
            our_prob,
            row["decimal_odds"],
            row["bookmaker"],
            row["captured_at"],
            factor_set.valid,
            json.dumps(factor_set.ui_blocks()),
        )
        await coverage.mark_covered(str(row["id"]), ctx.clock.now())
        drafted += 1

    print(f"drafted {drafted} pick(s) awaiting human review")
    return 0


async def _factor_counts(ctx: JobContext, row) -> dict[str, int]:
    """Sample sizes behind each factor, for the §5.4 gates."""
    h2h = int(
        await ctx.db.fetchval(
            """
            select count(*) from fixtures
             where status = 'finished' and kickoff_at > now() - interval '5 years'
               and ((home_team_id = $1 and away_team_id = $2)
                 or (home_team_id = $2 and away_team_id = $1))
            """,
            row["home_team_id"],
            row["away_team_id"],
        )
        or 0
    )
    season = int(
        await ctx.db.fetchval(
            "select count(*) from team_match_stats where team_id = $1 "
            "and status = 'finished' and kickoff_at < $2",
            row["home_team_id"],
            row["kickoff_at"],
        )
        or 0
    )
    return {"head_to_head": h2h, "opponent_adjusted": min(season, 38)}


if __name__ == "__main__":
    run_job(main)
