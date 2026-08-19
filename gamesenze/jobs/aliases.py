"""Work the unresolved-team-name backlog — §4.3.

`backlog` lists what sources have sent that we could not resolve, most
frequent first, with suggestions. `add` records a human's decision.

The suggestions are ranked by string similarity and are exactly that:
suggestions. Nothing here resolves a name automatically, however confident the
match looks. A 0.94-similarity guess that is wrong corrupts data precisely as
thoroughly as a 0.4 one, and nothing downstream can tell the difference.
"""

from __future__ import annotations

import sys

from ..normalize import TeamResolver, suggest_aliases
from ._runtime import JobContext, run_job


async def main(ctx: JobContext) -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "backlog"
    resolver = TeamResolver(ctx.db, ctx.clock)

    if command == "backlog":
        cleared = await resolver.sweep_resolved()
        if cleared:
            print(f"auto-cleared {cleared} entr{'y' if cleared == 1 else 'ies'} "
                  "that already resolve (a later reseed made them fixable; "
                  "nothing needed from you for these)\n")

        rows = await resolver.backlog()
        if not rows:
            print("backlog empty — every ingested name resolved")
            return 0

        teams = {
            str(t["id"]): t["canonical_name"]
            for t in await ctx.db.fetch("select id, canonical_name from teams")
        }

        print(f"{len(rows)} unresolved name(s), most-seen first:\n")
        for row in rows:
            print(f"  {row['source']}: {row['source_name']!r} "
                  f"({row['sightings']} sighting(s))")
            for s in suggest_aliases(row["source_name"], teams):
                print(f"      {s.similarity:.2f}  {s.canonical_name}  ({s.canonical_team_id})")
            print(f"      python -m gamesenze.jobs.aliases add "
                  f"{row['source']} {row['source_name']!r} <team-id>\n")
        return 1  # non-zero: a backlog is unfinished work, not a clean state

    if command == "add":
        if len(sys.argv) < 5:
            print("usage: aliases add <source> <source_name> <team_id>",
                  file=sys.stderr)
            return 2
        source, source_name, team_id = sys.argv[2], sys.argv[3], sys.argv[4]
        await resolver.add_alias(source, source_name, team_id)

        # Clear the blocking flags this name raised; the fixtures it blocked can
        # be reconsidered now.
        await ctx.db.execute(
            """
            update qa_flags
               set resolved_at = $1, resolved_by = 'aliases-cli',
                   resolution_note = $2
             where issue = 'unresolved_team_name'
               and resolved_at is null
               and detail like $3
            """,
            ctx.clock.now(),
            f"alias added: {source}/{source_name} -> {team_id}",
            f"%{source_name}%",
        )
        print(f"{source}/{source_name!r} -> {team_id}")
        return 0

    print(f"unknown command {command!r}; try backlog or add", file=sys.stderr)
    return 2


if __name__ == "__main__":
    run_job(main)
