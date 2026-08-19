"""One-time cleanup for teams written before the encoding fix.

Before jobs/seed.py specified encoding="utf-8" explicitly, every accented
team name read on Windows was silently corrupted (UTF-8 bytes misread as
cp1252 — "Málaga" became "MÃ¡laga"). Re-seeding after the fix does not
repair those rows: `on conflict (sport, canonical_name)` matches on the
literal string, and a corrupted string is not the same string as its correct
form, so the reseed just inserted a second, correct row alongside the first.

This finds teams whose canonical_name contains the 'Ã' signature specific to
that corruption, confirms nothing depends on them, and removes them. Not run
automatically — this is cleanup for damage the bug already did, not
something that recurs once the read-side fix is in place.

No team name in our seed data legitimately contains 'Ã' (verified against
db/seed/teams.json), so a plain substring match is enough — and safer than
a regex character class here: the mangled second byte lands all over the
Unicode map (cp1252 0x80-0x9F hits scattered code points like U+20AC, while
0xA0-0xFF is contiguous Latin-1 supplement), so there's no single contiguous
range that covers it. An earlier attempt at `'Ã[€-ÿ]'` reversed that range
(€ is U+20AC, past ÿ at U+00FF) and Postgres rejects it outright.
"""

from __future__ import annotations

import sys

from ._runtime import JobContext, run_job


async def find_corrupted(ctx: JobContext) -> list[dict]:
    return await ctx.db.fetch(
        r"""
        select id, sport, canonical_name, country
          from teams
         where canonical_name like '%Ã%'
         order by canonical_name
        """
    )


async def references(ctx: JobContext, team_id: str) -> dict[str, int]:
    """Anything that would make deleting this row unsafe."""
    counts = {}
    for label, query in (
        ("fixtures_home", "select count(*) from fixtures where home_team_id = $1"),
        ("fixtures_away", "select count(*) from fixtures where away_team_id = $1"),
        ("team_match_stats", "select count(*) from team_match_stats where team_id = $1"),
        ("player_match_stats", "select count(*) from player_match_stats where team_id = $1"),
        ("lineups", "select count(*) from lineups where team_id = $1"),
    ):
        n = int(await ctx.db.fetchval(query, team_id) or 0)
        if n:
            counts[label] = n
    return counts


async def main(ctx: JobContext) -> int:
    dry_run = "--confirm" not in sys.argv

    corrupted = await find_corrupted(ctx)
    if not corrupted:
        print("no corrupted rows found — nothing to clean up")
        return 0

    print(f"{len(corrupted)} corrupted team row(s) found:\n")
    safe_to_delete = []
    for row in corrupted:
        refs = await references(ctx, str(row["id"]))
        alias_count = int(
            await ctx.db.fetchval(
                "select count(*) from team_aliases where canonical_team_id = $1",
                row["id"],
            )
            or 0
        )
        status = "BLOCKED — has real data attached" if refs else "safe to delete"
        print(f"  {row['canonical_name']!r} ({row['country']}) "
              f"[{alias_count} alias row(s)] — {status}")
        if refs:
            for label, n in refs.items():
                print(f"      {label}: {n}")
        else:
            safe_to_delete.append(row["id"])

    if dry_run:
        print(f"\nDRY RUN — {len(safe_to_delete)} of {len(corrupted)} would be "
              "deleted. Re-run with --confirm to actually delete them.")
        return 0

    deleted = 0
    for team_id in safe_to_delete:
        await ctx.db.execute("delete from teams where id = $1", team_id)
        deleted += 1

    skipped = len(corrupted) - deleted
    print(f"\ndeleted {deleted} corrupted row(s)"
          + (f", {skipped} skipped (had real data — needs a manual look)"
             if skipped else ""))
    return 0


if __name__ == "__main__":
    run_job(main)
