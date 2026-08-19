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
    data = json.loads(SEED.read_text(encoding="utf-8"))

    # Batched as one round trip per table instead of one per row. At ~130
    # teams x ~7 sources x ~3 names each, the old row-at-a-time loop was
    # ~2000+ sequential network round trips to Supabase — seconds of network
    # latency each, minutes in total on a home connection. unnest() turns
    # that into 3 statements.
    comps = data["competitions"]
    await ctx.db.execute(
        """
        insert into competitions (sport, name, country, tier)
        select * from unnest($1::text[], $2::text[], $3::text[], $4::int[])
        on conflict (sport, name, country) do nothing
        """,
        [c["sport"] for c in comps],
        [c["name"] for c in comps],
        [c["country"] for c in comps],
        [c["tier"] for c in comps],
    )

    teams = data["teams"]
    rows = await ctx.db.fetch(
        """
        insert into teams (sport, canonical_name, country)
        select 'football', * from unnest($1::text[], $2::text[])
        on conflict (sport, canonical_name) do update
            set country = excluded.country
        returning id, canonical_name
        """,
        [t["canonical"] for t in teams],
        [t["country"] for t in teams],
    )
    team_id_by_name = {r["canonical_name"]: r["id"] for r in rows}

    # The canonical spelling is itself an alias — sources that happen to
    # agree with us must resolve through the same path as those that do not.
    alias_team_ids: list[str] = []
    alias_sources: list[str] = []
    alias_names: list[str] = []
    for team in teams:
        team_id = team_id_by_name[team["canonical"]]
        for name in [team["canonical"], *team["variants"]]:
            for source in data["sources"]:
                alias_team_ids.append(team_id)
                alias_sources.append(source)
                alias_names.append(name)

    await ctx.db.execute(
        """
        insert into team_aliases (canonical_team_id, source, source_name)
        select * from unnest($1::uuid[], $2::text[], $3::text[])
        on conflict (source, source_name) do nothing
        """,
        alias_team_ids,
        alias_sources,
        alias_names,
    )

    print(f"seeded {len(teams)} teams and up to {len(alias_names)} alias rows")
    print(
        "Anything a source sends that is not in here lands in "
        "unresolved_team_names and blocks its fixture until a human resolves "
        "it (REQ-DATA-NORM-1). Check the backlog with:\n"
        "  python -m gamesenze.jobs.aliases backlog"
    )
    return 0


if __name__ == "__main__":
    run_job(main)
