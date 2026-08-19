"""The Odds API (the-odds-api.com) — replaces SportsGameOdds for live odds.

SportsGameOdds's free "Amateur" tier turned out, discovered live mid
deployment, to cover only MLS and the UEFA Champions League for soccer —
Premier League, La Liga, Serie A, Bundesliga and Ligue 1 all require its
$299/month "Pro" tier. That breaks the zero-cost premise for the leagues this
product actually targets. The Odds API's free tier (500 credits/month) covers
all five, plus Eredivisie, Primeira Liga and the Championship — verified live
against `/v2/leagues` (SportsGameOdds) and `/v4/sports` (this vendor) before
either was trusted, not assumed from either vendor's marketing copy.

Billing here is also structurally different and, for this use case, cheaper:
one credit buys *every* upcoming game for a whole league in one call (cost =
markets x regions, so 1 market x 1 region = 1 credit regardless of how many
games come back), rather than SportsGameOdds's one-object-per-event model.
That is why there is no per-fixture vendor-event resolution step here: a
whole league's board is cheap enough to just pull and match by team name and
kickoff time against fixtures already synced from football-data.org.

Auth is an `apiKey` query parameter, not a header — confirmed against the
vendor's own reference docs and a live call, not assumed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..budget import BudgetMeter
from ..clock import Clock
from ..db import Db
from ..qa.anomaly import check_impossible_line
from ..qa.errors import QAViolation
from ..qa.validation import validate_record_type
from .base import MeteredClient, Response, Transport

BASE_URL = "https://api.the-odds-api.com/v4"
PROVIDER = "odds_api"

# Our competition key -> the-odds-api sport key. Verified live against
# GET /v4/sports?apiKey=... (a free call, does not count against quota) — see
# docs/OPERATIONS.md. Only the leagues actually present in that response are
# listed; anything else (UCL, the domestic cups) has no odds source here and
# stays fixture-only, same as before.
LEAGUE_KEYS: dict[str, str] = {
    "Premier League": "soccer_epl",
    "La Liga": "soccer_spain_la_liga",
    "Serie A": "soccer_italy_serie_a",
    "Bundesliga": "soccer_germany_bundesliga",
    "Ligue 1": "soccer_france_ligue_one",
    "Eredivisie": "soccer_netherlands_eredivisie",
    "Primeira Liga": "soccer_portugal_primeira_liga",
    "Championship": "soccer_efl_champ",
}


class OddsApi:
    def __init__(
        self,
        api_key: str,
        *,
        db: Db,
        meter: BudgetMeter,
        transport: Transport | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = MeteredClient(
            PROVIDER,
            BASE_URL,
            db=db,
            meter=meter,
            transport=transport,
            clock=clock,
        )

    async def odds(
        self, sport_key: str, *, regions: str = "uk", markets: str = "h2h"
    ) -> Response:
        """One credit: every upcoming game for `sport_key`, across every book.

        `regions`/`markets` are pinned to one value each because cost is
        markets x regions — widening either multiplies the credit spend for
        no benefit here, since the pipeline only ever prices the match-result
        market.
        """
        return await self._client.get(
            f"sports/{sport_key}/odds",
            params={
                "apiKey": self._api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": "decimal",
            },
            job="odds_sync",
            entity_type="odds_list",
            entity_ref=f"league:{sport_key}",
        )


def parse_odds(
    raw: dict[str, Any], *, captured_at: datetime, window_label: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Flattens one already-matched game's `bookmakers` into odds rows.

    `raw` is one element of the list GET /sports/{key}/odds returns — see
    odds_sync.py, which matches each game to a fixture before calling this.
    Rejections are returned rather than raised: one nonsense price from one
    book should not cost us the other forty, but it must still be visible to
    the audit.
    """
    rows: list[dict[str, Any]] = []
    rejections: list[str] = []

    for book in raw.get("bookmakers", []) or []:
        book_name = book.get("key") or book.get("title") or "unknown"
        for market in book.get("markets", []) or []:
            market_key = market.get("key") or "unknown"
            for outcome in market.get("outcomes", []) or []:
                selection = outcome.get("name")
                price = outcome.get("price")
                candidate = {"decimal_odds": price}

                try:
                    validate_record_type(candidate, "odds", now=captured_at)
                except QAViolation as exc:
                    rejections.append(f"{book_name}/{market_key}/{selection}: {exc}")
                    continue

                impossible = check_impossible_line(float(price))
                if impossible is not None:
                    rejections.append(
                        f"{book_name}/{market_key}/{selection}: {impossible.detail}"
                    )
                    continue

                rows.append(
                    {
                        "bookmaker": book_name,
                        "market": market_key,
                        "selection": selection,
                        "decimal_odds": float(price),
                        "captured_at": captured_at,
                        "window_label": window_label,
                        "is_closing": window_label == "lock",
                    }
                )

    return rows, rejections
