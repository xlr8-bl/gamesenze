"""Resolve club crests and competition artwork against TheSportsDB.

Why this exists
---------------
A football product without crests looks like a spreadsheet, and the crest is a
trademark, so we do not draw our own. TheSportsDB publishes a free, open API
keyed by team *name*, which is exactly the lookup we can verify: we search for
the canonical name we already hold and only accept a result whose own name (or
one of its listed alternates) matches after the same normalisation the rest of
the pipeline uses.

That last part is the point. An ID-keyed source would mean hardcoding 158
numbers nobody can check; a name-keyed source lets the match carry its own
evidence, which lands in the manifest beside every row.

The manifest it writes is static URLs on an image CDN, so the running site
never calls this API. Only this job does, and only when the club list changes.

    python -m gamesenze.jobs.resolve_media            # resolve what is missing
    python -m gamesenze.jobs.resolve_media --refresh  # re-resolve everything
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path
from typing import Any

import httpx

from gamesenze.competitions import COMPETITIONS
from gamesenze.normalize import normalise_name

# The documented free test key. It is rate limited and public; nothing here is
# a secret, and the site never uses it at runtime.
API = "https://www.thesportsdb.com/api/v1/json/3"

SEED = Path(__file__).resolve().parents[2] / "db" / "seed"
TEAMS_FILE = SEED / "teams.json"
MEDIA_FILE = SEED / "media.json"

# Search terms for names TheSportsDB files differently from us. Each one was
# confirmed against the API, not guessed.
TEAM_SEARCH_ALIASES: dict[str, str] = {
    "Internazionale": "Inter Milan",
    "Bayern Munich": "Bayern Munich",
    "Borussia Monchengladbach": "Borussia Monchengladbach",
    "1. FC Köln": "FC Koln",
    "FSV Mainz 05": "Mainz",
    "TSG Hoffenheim": "Hoffenheim",
    "SC Freiburg": "Freiburg",
    "VfB Stuttgart": "Stuttgart",
    "FC Schalke 04": "Schalke 04",
    "SC Paderborn": "Paderborn",
    "Deportivo La Coruña": "Deportivo La Coruna",
    "Deportivo Alavés": "Alaves",
    "Athletic Club": "Athletic Bilbao",
    "Atlético Madrid": "Atletico Madrid",
    "Málaga": "Malaga",
    "Racing Santander": "Racing Santander",
    "Celta Vigo": "Celta Vigo",
    "Sporting CP": "Sporting Lisbon",
    "Vitória SC": "Vitoria Guimaraes",
    "Famalicão": "Famalicao",
    "Académico de Viseu": "Academico Viseu",
    "Queens Park Rangers": "Queens Park Rangers",
    "Wolverhampton Wanderers": "Wolverhampton",
    # Searching "Brighton" returns Brighton WFC, a different club. The spelled
    # out "and" is the term that finds the men's side.
    "Brighton & Hove Albion": "Brighton and Hove",
    "Paris Saint-Germain": "Paris Saint Germain",
    "Lille": "Lille OSC",
    "Nacional": "Nacional Madeira",
    "Hamburger SV": "Hamburg",
    "Nottingham Forest": "Nottingham Forest",
    "Deportivo La Coruña": "RC Deportivo de La Coruna",
    "NEC Nijmegen": "NEC Nijmegen",
    "AZ Alkmaar": "AZ Alkmaar",
    "PSV Eindhoven": "PSV Eindhoven",
    "Hellas Verona": "Hellas Verona",
    "AC Milan": "AC Milan",
}

# The vendor's own name for each competition, taken from the harvested map
# rather than guessed. Six of these missed on the first run because "English FA
# Cup" is our name for it and "FA Cup" is theirs.
COMPETITION_SEARCH: dict[str, str] = {
    "premier_league": "English Premier League",
    "la_liga": "Spanish La Liga",
    "serie_a": "Italian Serie A",
    "bundesliga": "German Bundesliga",
    "ligue_1": "French Ligue 1",
    "ucl": "UEFA Champions League",
    "uel": "UEFA Europa League",
    "uecl": "UEFA Conference League",
    "fa_cup": "FA Cup",
    "efl_cup": "EFL Cup",
    "copa_del_rey": "Copa del Rey",
    "coppa_italia": "Coppa Italia",
    "dfb_pokal": "DFB Pokal",
    "coupe_de_france": "Coupe de France",
    "eredivisie": "Dutch Eredivisie",
    "primeira_liga": "Portuguese Primeira Liga",
    "championship": "English League Championship",
}


def _names_of(row: dict[str, Any]) -> set[str]:
    """Every name the vendor admits to for this row, normalised."""
    names = {row.get("strTeam") or row.get("strLeague") or ""}
    alt = row.get("strTeamAlternate") or row.get("strLeagueAlternate") or ""
    names |= {part.strip() for part in alt.split(",") if part.strip()}
    return {normalise_name(n) for n in names if n}


async def _get(client: httpx.AsyncClient, path: str, **params: str) -> dict[str, Any]:
    for attempt in range(6):
        try:
            r = await client.get(f"{API}/{path}", params=params, timeout=25.0)
            if r.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            # A 404 means the vendor has no such record. That is an answer, not
            # a failure, and it must not end a run that is most of the way
            # through 158 clubs.
            if r.status_code == 404:
                return {}
            r.raise_for_status()
            # A rate-limited response comes back as an HTML error page with a
            # 200, so a body that will not parse is a throttle, not a bug.
            return r.json() or {}
        except (httpx.HTTPError, json.JSONDecodeError):
            if attempt == 5:
                raise
            await asyncio.sleep(2 ** attempt + random.random())
    return {}


def harvest_leagues(row: dict[str, Any], into: dict[str, str]) -> None:
    """Collect league name to league id from a team row.

    The vendor's all_leagues endpoint returns ten soccer leagues and none of
    the domestic cups or UEFA competitions, but every team lists the
    competitions it plays in, with ids. Reading them off the rows we already
    fetch gives a map derived from data rather than from guesswork.
    """
    for suffix in ("", "2", "3", "4", "5", "6", "7"):
        name = row.get(f"strLeague{suffix}")
        ident = row.get(f"idLeague{suffix}")
        if name and ident:
            into.setdefault(normalise_name(name), ident)


async def resolve_team(
    client: httpx.AsyncClient,
    canonical: str,
    variants: list[str],
    leagues: dict[str, str],
) -> dict[str, Any] | None:
    """Search by name and accept only a row that agrees it has that name.

    Falling back to "the first result" is how a resolver quietly puts Real
    Madrid's crest on Real Sociedad, so an unmatched club gets no row and keeps
    its monogram instead.
    """
    wanted = {normalise_name(n) for n in [canonical, *variants]}
    terms = [TEAM_SEARCH_ALIASES.get(canonical, canonical)]
    if terms[0] != canonical:
        terms.append(canonical)

    for term in terms:
        data = await _get(client, "searchteams.php", t=term)
        for row in data.get("teams") or []:
            if row.get("strSport") != "Soccer":
                continue
            harvest_leagues(row, leagues)
            if not (wanted & _names_of(row)):
                continue
            badge = row.get("strBadge")
            if not badge:
                continue
            fanart = [row.get(f"strFanart{i}") for i in (1, 2, 3, 4)]
            return {
                "canonical": canonical,
                "badge": badge,
                "banner": row.get("strBanner"),
                "fanart": [f for f in fanart if f],
                "stadium": row.get("strStadium"),
                # Kept so a human can audit what we matched against.
                "matched": row.get("strTeam"),
                "source_id": row.get("idTeam"),
            }
    return None


async def resolve_competition(
    client: httpx.AsyncClient, key: str, name: str, leagues: dict[str, str]
) -> dict[str, Any] | None:
    """Look the competition up in the harvested map, then fetch its artwork."""
    term = COMPETITION_SEARCH.get(key, name)
    ident = leagues.get(normalise_name(term))
    if not ident:
        return None

    data = await _get(client, "lookupleague.php", id=ident)
    rows = data.get("leagues") or []
    if not rows:
        return None
    row = rows[0]
    fanart = [row.get(f"strFanart{i}") for i in (1, 2, 3, 4)]
    return {
        "key": key,
        "badge": row.get("strBadge"),
        "logo": row.get("strLogo"),
        "banner": row.get("strBanner"),
        "poster": row.get("strPoster"),
        "trophy": row.get("strTrophy"),
        "fanart": [f for f in fanart if f],
        "matched": row.get("strLeague"),
        "source_id": ident,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-resolve everything")
    args = parser.parse_args()

    seed = json.loads(TEAMS_FILE.read_text(encoding="utf-8"))
    existing: dict[str, Any] = {"teams": {}, "competitions": {}}
    if MEDIA_FILE.exists() and not args.refresh:
        existing = json.loads(MEDIA_FILE.read_text(encoding="utf-8"))
        existing.setdefault("teams", {})
        existing.setdefault("competitions", {})

    existing.setdefault("leagues", {})
    leagues: dict[str, str] = dict(existing["leagues"])
    unresolved: list[str] = []

    def checkpoint() -> None:
        """Write what we have so far.

        The first version of this job wrote once, at the end, and lost 158
        resolved clubs to a single 404 in the competition pass. Every phase
        checkpoints now, and a re-run picks up where it stopped.
        """
        existing["leagues"] = leagues
        existing["_note"] = (
            "Generated by gamesenze.jobs.resolve_media. Crest and photography "
            "URLs from TheSportsDB, matched by name, with the name the vendor "
            "returned kept as evidence for every row. Re-run after changing "
            "db/seed/teams.json."
        )
        MEDIA_FILE.write_text(
            json.dumps(existing, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    async with httpx.AsyncClient(headers={"user-agent": "gamesenze/1.0"}) as client:
        todo = [t for t in seed["teams"] if t["canonical"] not in existing["teams"]]
        print(f"teams: {len(seed['teams'])} total, {len(todo)} to resolve", flush=True)
        for i, team in enumerate(todo, 1):
            try:
                hit = await resolve_team(
                    client, team["canonical"], team.get("variants", []), leagues
                )
            except httpx.HTTPError as exc:
                print(f"  {team['canonical']}: {exc}", flush=True)
                hit = None
            if hit:
                existing["teams"][team["canonical"]] = hit
            else:
                unresolved.append(team["canonical"])
            if i % 20 == 0:
                checkpoint()
                print(f"  {i}/{len(todo)} ({len(leagues)} leagues seen)", flush=True)
            await asyncio.sleep(0.6)  # the free key is shared; do not hammer it
        checkpoint()

        comps = [c for c in COMPETITIONS if c.key not in existing["competitions"]]
        print(f"competitions: {len(COMPETITIONS)} total, {len(comps)} to resolve", flush=True)
        for spec in comps:
            try:
                hit = await resolve_competition(client, spec.key, spec.name, leagues)
            except httpx.HTTPError as exc:
                print(f"  {spec.key}: {exc}", flush=True)
                hit = None
            if hit:
                existing["competitions"][spec.key] = hit
            else:
                unresolved.append(f"competition:{spec.key}")
            checkpoint()
            await asyncio.sleep(0.35)

    checkpoint()

    print(f"\nresolved {len(existing['teams'])} teams, {len(existing['competitions'])} competitions")
    if unresolved:
        print(f"unresolved ({len(unresolved)}): {', '.join(unresolved)}")
        print("These keep their monogram badge, which is the correct outcome for")
        print("a club we could not confirm rather than a guessed crest.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
