"""Understat over plain HTTP — no browser, no soccerdata, seconds not minutes.

soccerdata drives a headless browser for Understat, which is slow and, on
Windows, fragile. It does not need to: Understat embeds every match and every
team's per-match history as JSON literals inside the page, so one ordinary GET
per league-season returns everything team_match_stats wants. FBref genuinely
needs a browser (Cloudflare); Understat never did.

This produces rows in exactly the shape `stats_sync.parse_understat_rows`
already consumes, so nothing downstream changes — only how the bytes arrive.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

log = logging.getLogger("gamesenze.understat_http")

BASE = "https://understat.com/league"

# Understat's own league slug -> the soccerdata-style key parse_understat_rows
# maps through LEAGUE_NAMES. Emitting that key means the existing parser needs
# no change. Only the three leagues the stats layer is wired for.
UNDERSTAT_TO_SD: dict[str, str] = {
    "EPL": "ENG-Premier League",
    "La_liga": "ESP-La Liga",
    "Serie_A": "ITA-Serie A",
}
DEFAULT_LEAGUES = list(UNDERSTAT_TO_SD)


def _season_year(season: str) -> str:
    """"2425" -> "2024": Understat keys a season by its starting year."""
    return str(2000 + int(season[:2]))


def _extract_var(html: str, name: str) -> Any:
    """Pull one `var <name> = JSON.parse('...')` blob out of the page.

    The literal is JavaScript-escaped UTF-8 (\\xNN sequences), so it is decoded
    the standard Understat way: unescape to bytes, then read those bytes as
    UTF-8, which is what keeps accented club names ("Atletico") intact.
    """
    m = re.search(name + r"\s*=\s*JSON\.parse\('(.*?)'\)", html, re.S)
    if not m:
        return None
    raw = m.group(1)
    decoded = raw.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")
    return json.loads(decoded)


def _ppda_by_team_date(teams_data: dict) -> dict[tuple[str, str], float | None]:
    """(team title, match date) -> PPDA for that team that day.

    PPDA is passes allowed per defensive action: the `att`/`def` pair Understat
    stores in each team's match history. It lives only in teamsData, not in the
    match list, so it is looked up and joined onto each fixture by team + date.
    """
    out: dict[tuple[str, str], float | None] = {}
    for team in (teams_data or {}).values():
        title = team.get("title")
        for h in team.get("history", []):
            date = str(h.get("date", ""))[:10]
            ppda = h.get("ppda") or {}
            att, dfn = ppda.get("att"), ppda.get("def")
            value = (att / dfn) if att is not None and dfn else None
            if title and date:
                out[(title, date)] = value
    return out


def parse_page(html: str, sd_league: str) -> list[dict]:
    """One league-season page -> finished-match rows for parse_understat_rows."""
    dates_data = _extract_var(html, "datesData")
    teams_data = _extract_var(html, "teamsData")
    if not dates_data:
        return []
    ppda = _ppda_by_team_date(teams_data or {})

    rows: list[dict] = []
    for m in dates_data:
        if not m.get("isResult"):
            continue  # upcoming fixture, no result yet
        home, away = m["h"]["title"], m["a"]["title"]
        date = str(m.get("datetime", ""))
        day = date[:10]
        rows.append(
            {
                "league": sd_league,
                "date": date,
                "game_id": str(m.get("id")),
                "home_team": home,
                "away_team": away,
                "home_goals": _int(m.get("goals", {}).get("h")),
                "away_goals": _int(m.get("goals", {}).get("a")),
                "home_xg": _float(m.get("xG", {}).get("h")),
                "away_xg": _float(m.get("xG", {}).get("a")),
                "home_ppda": ppda.get((home, day)),
                "away_ppda": ppda.get((away, day)),
            }
        )
    return rows


async def fetch_understat(
    client: httpx.AsyncClient,
    leagues: list[str] | None = None,
    seasons: list[str] | None = None,
) -> list[dict]:
    """GET each league-season page and flatten every finished match."""
    leagues = leagues or DEFAULT_LEAGUES
    seasons = seasons or ["2526"]
    rows: list[dict] = []
    for league in leagues:
        sd_league = UNDERSTAT_TO_SD.get(league)
        if sd_league is None:
            log.warning("no soccerdata mapping for Understat league %s, skipping", league)
            continue
        for season in seasons:
            url = f"{BASE}/{league}/{_season_year(season)}"
            try:
                resp = await client.get(url, timeout=30.0)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.error("understat %s %s: %s", league, season, exc)
                continue
            page_rows = parse_page(resp.text, sd_league)
            log.info("understat %s %s: %d finished matches", league, season, len(page_rows))
            rows.extend(page_rows)
    return rows


def _int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
