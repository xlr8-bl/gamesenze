"""Weekly backtest integrity check — §5.7, §3.5 (12 min weekly).

Reports whether we have evidence, not whether we made money. A profitable run
of 40 picks is not evidence (REQ-QA-7) and this job says so out loud.
"""

from __future__ import annotations

from datetime import timedelta

from ..analysis.model import MatchModel
from ..backtest.harness import BacktestCandidate, BacktestHarness
from ._runtime import JobContext, run_job


async def main(ctx: JobContext) -> int:
    model = MatchModel()

    def predict(home, away, candidate):
        return model.price(home, away).probability(
            candidate.market, candidate.selection
        )

    since = ctx.clock.now() - timedelta(days=365)
    rows = await ctx.db.fetch(
        """
        select p.id, p.fixture_id, p.market, p.selection, p.capture_odds,
               p.closing_odds, p.result, f.kickoff_at, f.home_team_id,
               f.away_team_id
          from picks p
          join fixtures f on f.id = p.fixture_id
         where f.kickoff_at >= $1 and f.kickoff_at < now()
         order by f.kickoff_at
        """,
        since,
    )

    # REQ-QA-6: every fixture we would have covered goes in, including the ones
    # missing data. They become skips with a reason rather than disappearing.
    candidates = [
        BacktestCandidate(
            fixture_id=str(r["fixture_id"]),
            kickoff_at=r["kickoff_at"],
            home_team_id=str(r["home_team_id"]),
            away_team_id=str(r["away_team_id"]),
            market=r["market"],
            selection=r["selection"],
            capture_odds=float(r["capture_odds"]) if r["capture_odds"] else None,
            closing_odds=float(r["closing_odds"]) if r["closing_odds"] else None,
            outcome=None if r["result"] is None else int(r["result"] == "won"),
        )
        for r in rows
    ]

    harness = BacktestHarness(ctx.db, predict)
    result = await harness.run(candidates, label="weekly")
    print(result.summary())
    await harness.persist(ctx.db, result)

    if not result.is_evidence:
        print(
            "\nReported, not acted on: below the 100-pick threshold in "
            "REQ-QA-7."
        )

    # A high calibration error is the leading indicator §5.7 warns about, so it
    # alerts even when the ROI looks fine.
    if result.is_evidence and result.ece > 0.10:
        ctx.alerter.alert(
            f"Calibration error {result.ece:.3f} over {result.pick_count} picks "
            "— miscalibrated regardless of profitability (REQ-QA-8)",
            ece=round(result.ece, 4),
        )
        return 1
    return 0


if __name__ == "__main__":
    run_job(main)
