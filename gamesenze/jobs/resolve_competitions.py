"""Resolve competition IDs against API-Football's own /leagues endpoint.

Never guesses. Two independent lookups for the same competition produced
different numbers during this build — that is the whole reason this exists
rather than a hardcoded table. It searches by name, shows every candidate the
vendor actually returned, and a human picks. Nothing is written on a match
found by string similarity alone; REQ-DATA-NORM-1 draws the same line for
team names, and a wrong competition ID is the same failure mode: it would
silently sync fixtures for the wrong tournament, forever, with nothing
downstream able to tell.

Run it once per competition. It skips anything already resolved, so re-running
after adding a competition to gamesenze/competitions.py only prompts for the
new one.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from ..competitions import COMPETITIONS, CompetitionSpec, by_key
from ..providers.api_football import ApiFootball
from ._runtime import JobContext, run_job


async def already_resolved(ctx: JobContext, key: str) -> bool:
    row = await ctx.db.fetchrow(
        """
        select 1 from competition_source_ids s
        join competitions c on c.id = s.competition_id
        where s.source = 'api_football' and c.name = $1
        """,
        by_key_name(key),
    )
    return row is not None


def by_key_name(key: str) -> str:
    for c in COMPETITIONS:
        if c.key == key:
            return c.name
    raise KeyError(key)


def candidates_from_response(body: Any) -> list[dict[str, Any]]:
    """API-Football's /leagues shape -> flat candidate dicts."""
    out = []
    for item in (body or {}).get("response", []) or []:
        league = item.get("league", {})
        country = item.get("country", {})
        seasons = item.get("seasons", [])
        current = next((s for s in seasons if s.get("current")), None)
        out.append(
            {
                "id": league.get("id"),
                "name": league.get("name"),
                "type": league.get("type"),
                "country": country.get("name"),
                "current_season": current.get("year") if current else None,
            }
        )
    return out


def print_candidates(spec: CompetitionSpec, candidates: list[dict[str, Any]]) -> None:
    print(f"\n{spec.name} ({spec.country}) — searching API-Football for {spec.name!r}")
    if not candidates:
        print("  no results returned")
        return
    for i, c in enumerate(candidates, 1):
        season = c["current_season"] or "?"
        print(
            f"  [{i}] id={c['id']:<5} {c['name']!r:30s} {c['country']:15s} "
            f"{c['type'] or '':7s} season {season}"
        )


def prompt_choice(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Blocking on purpose — a human is meant to be at the keyboard.

    A skip is always safe: fixture_sync refuses to run for a competition with
    no resolved ID (fail closed), so leaving one unresolved costs nothing but
    that competition's coverage until it is resolved.
    """
    raw = input(
        "  pick a number, or 's' to skip, or 'q' to stop entirely: "
    ).strip().lower()
    if raw == "q":
        raise KeyboardInterrupt
    if raw == "s" or raw == "":
        return None
    try:
        index = int(raw)
    except ValueError:
        print("  not a number, skipping")
        return None
    if not 1 <= index <= len(candidates):
        print("  out of range, skipping")
        return None
    return candidates[index - 1]


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
        values ($1, 'api_football', $2, $3, $4, $5, $6, $7)
        on conflict (source, source_id) do update
            set competition_id = excluded.competition_id,
                resolved_name = excluded.resolved_name,
                resolved_country = excluded.resolved_country,
                resolved_season = excluded.resolved_season,
                resolved_at = excluded.resolved_at,
                resolved_by = excluded.resolved_by
        """,
        competition_id,
        str(choice["id"]),
        choice["name"],
        choice["country"],
        choice["current_season"],
        ctx.clock.now(),
        resolved_by,
    )
    print(f"  confirmed: {spec.name} -> api_football id={choice['id']}")


async def dump(ctx: JobContext, client: ApiFootball) -> int:
    """Non-interactive: print every candidate, decide nothing.

    For running from a phone via GitHub Actions' "Run workflow" button, where
    there is no keyboard for prompt_choice() to read. The human reads the
    printed candidates in the workflow log and comes back with their picks for
    the `--confirm` mode below — the decision is still made by a person
    reading real vendor data, just relayed through a log instead of a
    terminal prompt.
    """
    print("Reading each competition's real candidates from API-Football.\n"
          "Nothing is written by this run. Note the [id] you want for each "
          "line below, then trigger 'Confirm competitions' with e.g.\n"
          "  premier_league=39,la_liga=140,serie_a=135\n")
    unresolved = [c for c in COMPETITIONS if not await already_resolved(ctx, c.key)]
    if not unresolved:
        print("nothing unresolved — every competition already has an ID")
        return 0
    for spec in unresolved:
        response = await client.search_leagues(spec.name)
        print(f"key: {spec.key}")
        print_candidates(spec, candidates_from_response(response.body))
    return 0


def parse_picks(raw: str) -> dict[str, int]:
    """'premier_league=39,la_liga=140' -> {'premier_league': 39, ...}

    Rejects the whole batch on a malformed entry rather than silently
    dropping it — a typo'd pair should stop the run, not vanish.
    """
    picks: dict[str, int] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"{pair!r} is not key=id")
        key, _, value = pair.partition("=")
        picks[key.strip()] = int(value.strip())
    return picks


async def confirm_from_picks(
    ctx: JobContext, client: ApiFootball, raw_picks: str, resolved_by: str
) -> int:
    """Phone-mode confirmation. Still verifies against the live vendor
    response rather than trusting a bare number: the id must appear among
    what /leagues actually returns for that competition's name, or it is
    rejected rather than accepted on faith. A typo'd id is exactly the kind
    of unverified match REQ-DATA-NORM-1 exists to catch.
    """
    picks = parse_picks(raw_picks)
    confirmed = rejected = 0

    for key, chosen_id in picks.items():
        try:
            spec = by_key(key)
        except KeyError:
            print(f"  {key}: not a known competition key, skipping")
            rejected += 1
            continue

        response = await client.search_leagues(spec.name)
        candidates = candidates_from_response(response.body)
        match = next((c for c in candidates if c["id"] == chosen_id), None)
        if match is None:
            print(f"  {key}: id {chosen_id} was not in API-Football's own "
                  f"results for {spec.name!r} — not confirming an unverified "
                  "number, skipping")
            rejected += 1
            continue

        await confirm(ctx, spec, match, resolved_by)
        confirmed += 1

    print(f"\n{confirmed} confirmed, {rejected} rejected")
    return 0 if rejected == 0 else 1


async def main(ctx: JobContext) -> int:
    if not ctx.settings.api_football_key:
        print("API_FOOTBALL_KEY is not set", file=sys.stderr)
        return 2

    client = ApiFootball(
        ctx.settings.api_football_key, db=ctx.db, meter=ctx.meter, clock=ctx.clock
    )
    args = sys.argv[1:]

    if args and args[0] == "--dump":
        return await dump(ctx, client)

    if args and args[0] == "--confirm":
        if len(args) < 2:
            print("usage: --confirm 'key=id,key=id,...'", file=sys.stderr)
            return 2
        resolved_by = os.environ.get("GITHUB_ACTOR", "phone-confirm")
        return await confirm_from_picks(ctx, client, args[1], resolved_by)

    # Interactive terminal mode, unchanged.
    resolved_by = args[0] if args else "terminal"
    resolved = 0
    skipped = 0
    try:
        for spec in COMPETITIONS:
            if await already_resolved(ctx, spec.key):
                continue
            response = await client.search_leagues(spec.name)
            candidates = candidates_from_response(response.body)
            print_candidates(spec, candidates)
            if not candidates:
                skipped += 1
                continue
            choice = prompt_choice(candidates)
            if choice is None:
                skipped += 1
                continue
            await confirm(ctx, spec, choice, resolved_by)
            resolved += 1
    except KeyboardInterrupt:
        print("\nstopped early")

    print(f"\n{resolved} resolved, {skipped} skipped this run")
    still_unresolved = [
        c.key for c in COMPETITIONS if not await already_resolved(ctx, c.key)
    ]
    if still_unresolved:
        print(f"still unresolved: {', '.join(still_unresolved)}")
        print("fixture_sync will skip these until resolved. Re-run this command "
              "any time to pick up where you left off.")
    return 0


if __name__ == "__main__":
    run_job(main)
