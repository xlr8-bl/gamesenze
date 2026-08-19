"""Resolve football-data.org competition codes — same discipline, different
shape of lookup than resolve_competitions.py.

API-Football is searched by name, one call per competition, often returning
dozens of decoys (amateur leagues worldwide sharing a name). football-data.org
covers a small, curated set — one call lists everything it has, in full. So
instead of narrowing per competition (a substring heuristic tried here first
and was dropped: "la_liga" matched Bundesliga and Primeira Liga, because
"liga" is a substring of both), the whole list is shown once and a human types
the short code for each of ours. The typed code is still checked against what
the vendor actually returned before anything is confirmed — a typo must be
rejected, not accepted on faith, the same rule resolve_competitions.py's
--confirm mode applies.

Only the 9 of our 17 competitions football-data.org's free tier actually
covers are asked for here. The other 8 (UEL, UECL, and the six domestic cups)
have no free current-season source yet — see docs/OPERATIONS.md.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from ..competitions import CompetitionSpec, by_key
from ..providers.football_data import FootballData, candidates_from_competitions
from ._runtime import JobContext, run_job

COVERED_KEYS = (
    "premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1",
    "ucl", "eredivisie", "primeira_liga", "championship",
)


async def already_resolved(ctx: JobContext, key: str) -> bool:
    row = await ctx.db.fetchrow(
        """
        select 1 from competition_source_ids s
        join competitions c on c.id = s.competition_id
        where s.source = 'football_data' and c.name = $1
        """,
        by_key(key).name,
    )
    return row is not None


def print_full_list(candidates: list[dict[str, Any]]) -> None:
    print(f"\nfootball-data.org covers {len(candidates)} competition(s):\n")
    for c in sorted(candidates, key=lambda c: (c["country"] or "", c["name"] or "")):
        season = c["current_season"] or "?"
        print(f"  {c['code']:5s} {c['name']!r:35s} {c['country']:15s} "
              f"{c['type'] or '':7s} season {season}")


async def confirm(
    ctx: JobContext, spec: CompetitionSpec, choice: dict[str, Any], resolved_by: str
) -> None:
    competition_id = await ctx.db.fetchval(
        """
        insert into competitions (sport, name, country, needs_standings)
        values ('football', $1, $2, $3)
        on conflict (sport, name, country) do update
            set needs_standings = excluded.needs_standings
        returning id
        """,
        spec.name,
        spec.country,
        spec.needs_standings,
    )
    await ctx.db.execute(
        """
        insert into competition_source_ids (competition_id, source, source_id,
                                            resolved_name, resolved_country,
                                            resolved_season, resolved_at,
                                            resolved_by)
        values ($1, 'football_data', $2, $3, $4, $5, $6, $7)
        on conflict (source, source_id) do update
            set competition_id = excluded.competition_id,
                resolved_name = excluded.resolved_name,
                resolved_country = excluded.resolved_country,
                resolved_season = excluded.resolved_season,
                resolved_at = excluded.resolved_at,
                resolved_by = excluded.resolved_by
        """,
        competition_id,
        choice["code"],
        choice["name"],
        choice["country"],
        int(choice["current_season"]) if choice["current_season"] else None,
        ctx.clock.now(),
        resolved_by,
    )
    print(f"  confirmed: {spec.name} -> football_data code={choice['code']}")


def find_by_code(candidates: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
    code = code.strip().upper()
    return next((c for c in candidates if (c["code"] or "").upper() == code), None)


async def dump(ctx: JobContext, client: FootballData) -> int:
    """Non-interactive: print the full list and which of our 9 still need a
    code, write nothing. For reading in a GitHub Actions run's log from a
    phone — see resolve_competitions.py's --dump for the same idea.
    """
    response = await client.list_competitions()
    all_candidates = candidates_from_competitions(response.body)
    print_full_list(all_candidates)

    specs = [by_key(k) for k in COVERED_KEYS if not await already_resolved(ctx, k)]
    if not specs:
        print("\nall 9 already resolved")
        return 0
    print("\nstill need a code:")
    for spec in specs:
        print(f"  {spec.key}: {spec.name} ({spec.country})")
    print("\nTrigger 'Resolve football-data.org — 2. confirm picks' with e.g.\n"
          "  premier_league=PL,la_liga=PD,serie_a=SA")
    return 0


async def confirm_from_picks(
    ctx: JobContext, client: FootballData, raw_picks: str, resolved_by: str
) -> int:
    """Phone-mode confirmation. Re-fetches the full list and only confirms a
    code that actually appears in it — a typo'd code is rejected, not
    accepted on faith, same as resolve_competitions.py's --confirm.
    """

    picks: dict[str, str] = {}
    for pair in raw_picks.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            print(f"  {pair!r} is not key=code, skipping", file=sys.stderr)
            continue
        key, _, code = pair.partition("=")
        picks[key.strip()] = code.strip()

    response = await client.list_competitions()
    all_candidates = candidates_from_competitions(response.body)

    confirmed = rejected = 0
    for key, code in picks.items():
        try:
            spec = by_key(key)
        except KeyError:
            print(f"  {key}: not a known competition key, skipping")
            rejected += 1
            continue
        match = find_by_code(all_candidates, code)
        if match is None:
            print(f"  {key}: code {code!r} was not in football-data.org's own "
                  "list — not confirming an unverified code, skipping")
            rejected += 1
            continue
        await confirm(ctx, spec, match, resolved_by)
        confirmed += 1

    print(f"\n{confirmed} confirmed, {rejected} rejected")
    return 0 if rejected == 0 else 1


async def main(ctx: JobContext) -> int:
    if not ctx.settings.football_data_key:
        print("FOOTBALL_DATA_KEY is not set", file=sys.stderr)
        return 2

    client = FootballData(
        ctx.settings.football_data_key, db=ctx.db, meter=ctx.meter, clock=ctx.clock
    )
    args = sys.argv[1:]

    if args and args[0] == "--dump":
        return await dump(ctx, client)

    if args and args[0] == "--confirm":
        if len(args) < 2:
            print("usage: --confirm 'key=code,key=code,...'", file=sys.stderr)
            return 2
        resolved_by = os.environ.get("GITHUB_ACTOR", "phone-confirm")
        return await confirm_from_picks(ctx, client, args[1], resolved_by)

    response = await client.list_competitions()
    all_candidates = candidates_from_competitions(response.body)

    specs = [by_key(k) for k in COVERED_KEYS if not await already_resolved(ctx, k)]
    if not specs:
        print("all 9 already resolved")
        return 0

    print_full_list(all_candidates)

    resolved_by = args[0] if args else "terminal"
    resolved = skipped = 0
    try:
        for spec in specs:
            raw = input(
                f"\n{spec.name} ({spec.country}) — type the code, or 's' to skip: "
            ).strip()
            if raw.lower() in ("", "s"):
                skipped += 1
                continue
            match = find_by_code(all_candidates, raw)
            if match is None:
                print(f"  {raw!r} is not in the list above — not confirming an "
                      "unverified code, skipping")
                skipped += 1
                continue
            await confirm(ctx, spec, match, resolved_by)
            resolved += 1
    except KeyboardInterrupt:
        print("\nstopped early")

    print(f"\n{resolved} resolved, {skipped} skipped this run")
    return 0


if __name__ == "__main__":
    run_job(main)
