"""The competition list — §3.2 budget math applied to a concrete plan.

Every row here is a name and a country, never a vendor ID. IDs are resolved
against API-Football's own `/leagues` endpoint by `jobs.resolve_competitions`
and stored in `competition_source_ids`, with the name/country the vendor
returned kept as evidence for the match. Two independent lookups for the same
competition during this build produced different numbers — that is the whole
reason this module holds no IDs at all.

`needs_standings` decides whether standings_refresh runs for a competition.
Knockout cups have no table; calling standings on one wastes a request and
gets an error back rather than data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompetitionSpec:
    key: str            # stable slug, used in code and logs
    name: str            # canonical display/search name
    country: str
    needs_standings: bool = True


# 17 competitions, sized against the actual API-Football budget (§3.2):
# top-5 leagues + 3 UEFA club competitions need a table (16 calls: 8 fixture
# sync + 8 standings); the six domestic cups are knockout, fixture sync only
# (6 calls); three further leagues add another 6. Total 28 of the 31 calls
# available at the top of the 70-85% operating band — see
# docs/OPERATIONS.md for the full arithmetic and tests/test_competitions.py
# for the assertion that keeps this comment honest as the list changes.
COMPETITIONS: tuple[CompetitionSpec, ...] = (
    # --- Top 5 domestic leagues ---------------------------------------------
    CompetitionSpec("premier_league", "Premier League", "England"),
    CompetitionSpec("la_liga", "La Liga", "Spain"),
    CompetitionSpec("serie_a", "Serie A", "Italy"),
    CompetitionSpec("bundesliga", "Bundesliga", "Germany"),
    CompetitionSpec("ligue_1", "Ligue 1", "France"),
    # --- UEFA club competitions ----------------------------------------------
    CompetitionSpec("ucl", "UEFA Champions League", "World"),
    CompetitionSpec("uel", "UEFA Europa League", "World"),
    CompetitionSpec("uecl", "UEFA Europa Conference League", "World"),
    # --- Major domestic cups (knockout — no standings table) -----------------
    CompetitionSpec("fa_cup", "FA Cup", "England", needs_standings=False),
    CompetitionSpec("efl_cup", "EFL Cup", "England", needs_standings=False),
    CompetitionSpec("copa_del_rey", "Copa del Rey", "Spain", needs_standings=False),
    CompetitionSpec("coppa_italia", "Coppa Italia", "Italy", needs_standings=False),
    CompetitionSpec("dfb_pokal", "DFB Pokal", "Germany", needs_standings=False),
    CompetitionSpec("coupe_de_france", "Coupe de France", "France", needs_standings=False),
    # --- Additional leagues ---------------------------------------------------
    CompetitionSpec("eredivisie", "Eredivisie", "Netherlands"),
    CompetitionSpec("primeira_liga", "Primeira Liga", "Portugal"),
    CompetitionSpec("championship", "Championship", "England"),
)


def by_key(key: str) -> CompetitionSpec:
    for c in COMPETITIONS:
        if c.key == key:
            return c
    raise KeyError(f"no competition registered with key {key!r}")


def daily_api_football_cost() -> int:
    """fixture_sync (1/competition) + standings_refresh (1/competition, only
    where needs_standings). Kept as a function rather than a constant so a
    change to COMPETITIONS is reflected immediately, not stale in a comment.
    """
    fixture_sync = len(COMPETITIONS)
    standings = sum(1 for c in COMPETITIONS if c.needs_standings)
    return fixture_sync + standings
