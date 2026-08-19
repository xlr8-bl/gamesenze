"""football-data.org — the free-tier source for live, current-season fixtures.

API-Football's free tier only reaches back to 2022-2024 (discovered live, mid
deployment: "Free plans do not have access to this season"), which makes it
useless for the thing the pipeline actually needs day to day — this season's
fixtures. football-data.org's free tier is the opposite shape: it covers the
current season, for a smaller set of competitions (12 worldwide; 9 overlap
ours). The two are complementary, not competing: this client handles live
fixtures for what it covers, api_football's free tier stays useful for
historical backtest data (§5.7 wants past seasons anyway).

Auth is `X-Auth-Token`, not a query param or bearer token — confirmed against
the vendor's own documentation and public code samples, not assumed.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..budget import BudgetMeter
from ..clock import Clock
from ..db import Db
from .base import MeteredClient, Response, Transport

BASE_URL = "https://api.football-data.org/v4"
PROVIDER = "football_data"


class FootballData:
    def __init__(
        self,
        api_key: str,
        *,
        db: Db,
        meter: BudgetMeter,
        transport: Transport | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._client = MeteredClient(
            PROVIDER,
            BASE_URL,
            db=db,
            meter=meter,
            transport=transport,
            headers={"X-Auth-Token": api_key},
            clock=clock,
        )

    async def list_competitions(self) -> Response:
        """`/competitions` — the full covered list, free and paid tiers alike.

        Called once by the resolver, not on a schedule: this is how a human
        confirms our competition names against the vendor's actual codes,
        the same discipline as resolve_competitions.py for API-Football.
        """
        return await self._client.get(
            "competitions",
            job="resolve_competitions",
            entity_type="competition_lookup",
        )

    async def matches(
        self, code: str, *, days: int = 7, today: date | None = None
    ) -> Response:
        """`/competitions/{code}/matches`, a 7-day window ahead of today."""
        start = today or date.today()
        return await self._client.get(
            f"competitions/{code}/matches",
            params={
                "dateFrom": start.isoformat(),
                "dateTo": (start + timedelta(days=days)).isoformat(),
            },
            job="fixture_sync",
            entity_type="fixture_list",
            entity_ref=f"competition:{code}",
        )


_STATUS_MAP = {
    "SCHEDULED": "scheduled",
    "TIMED": "scheduled",
    "IN_PLAY": "live",
    "PAUSED": "live",
    "FINISHED": "finished",
    "POSTPONED": "postponed",
    "SUSPENDED": "postponed",
    "CANCELLED": "cancelled",
    "AWARDED": "finished",
}


def parse_match(raw: dict[str, Any]) -> dict[str, Any]:
    """Vendor shape -> our shape, matching parse_fixture()'s output exactly
    so fixture_sync.upsert_fixture() does not need to know which vendor a
    fixture came from.
    """
    score = raw.get("score", {}).get("fullTime", {})
    return {
        "source_id": str(raw["id"]),
        "kickoff_at": _parse_kickoff(raw["utcDate"]),
        "status": _STATUS_MAP.get(raw.get("status", ""), "scheduled"),
        "venue": (raw.get("venue") or None),
        "home_source_name": raw["homeTeam"]["name"],
        "away_source_name": raw["awayTeam"]["name"],
        "home_goals": score.get("home"),
        "away_goals": score.get("away"),
    }


def _parse_kickoff(utc_date: str):
    from datetime import datetime

    return datetime.fromisoformat(utc_date.replace("Z", "+00:00"))


def candidates_from_competitions(body: Any) -> list[dict[str, Any]]:
    """`/competitions` response -> flat candidates, mirroring
    resolve_competitions.candidates_from_response() so both resolvers print
    and prompt the same way.
    """
    out = []
    for item in (body or {}).get("competitions", []) or []:
        area = item.get("area", {})
        current = item.get("currentSeason") or {}
        out.append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "type": item.get("type"),
                "country": area.get("name"),
                "current_season": (current.get("startDate") or "")[:4] or None,
            }
        )
    return out
