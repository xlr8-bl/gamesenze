"""Seed canonical teams and their aliases — §11, day 3.

"Team alias table for 3 leagues — before any other ingestion." Running this
after ingestion has started does not undo the damage: rows already stored
against the wrong team are indistinguishable from correct ones.
"""

from __future__ import annotations

import json
from pathlib import Path

from ._runtime import JobContext, run_job

SEED = Path(__file__).resolve().parents[2] / "db" / "seed" / "teams.json"


async def main(ctx: JobContext) -> int:
    data = json.loads(SEED.read_text())

    for comp in data["competitions"]:
        await ctx.db.execute(
            """
            insert into competitions (sport, name, country, tier)
            values ($1, $2, $3, $4)
            on conflict (sport, name, country) do nothing
            """,
            comp["sport"],
            comp["name"],
            comp["country"],
            comp["tier"],
        )

    teams = aliases = 0
    for team in data["teams"]:
        team_id = await ctx.db.fetchval(
            """
            insert into teams (sport, canonical_name, country)
            values ('football', $1, $2)
            on conflict (sport, canonical_name) do update
                set country = excluded.country
            returning id
            """,
            team["canonical"],
            team["country"],
        )
        teams += 1

        # The canonical spelling is itself an alias — sources that happen to
        # agree with us must resolve through the same path as those that do not.
        for name in [team["canonical"], *team["variants"]]:
            for source in data["sources"]:
                await ctx.db.execute(
                    """
                    insert into team_aliases (canonical_team_id, source,
                                              source_name)
                    values ($1, $2, $3)
                    on conflict (source, source_name) do nothing
                    """,
                    team_id,
                    source,
                    name,
                )
                aliases += 1

    print(f"seeded {teams} teams and up to {aliases} alias rows")
    print(
        "Anything a source sends that is not in here lands in "
        "unresolved_team_names and blocks its fixture until a human resolves "
        "it (REQ-DATA-NORM-1). Check the backlog with:\n"
        "  python -m gamesenze.jobs.aliases backlog"
    )
    return 0


if __name__ == "__main__":
    run_job(main)
