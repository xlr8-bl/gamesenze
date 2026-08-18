"""API-Football — 100 calls/day, 80 planned (§3.2).

Every method here corresponds to a line in the daily allocation table, and each
one declares which line it spends from. That is what makes the allocation
auditable rather than aspirational: `api_calls.job` carries the label, so the
daily audit can show where the day's 70 went.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..budget import BudgetMeter
from ..clock import Clock
from ..db import Db
from .base import MeteredClient, Response, Transport

BASE_URL = "https://v3.football.api-sports.io"
PROVIDER = "api_football"


class ApiFootball:
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
            headers={"x-apisports-key": api_key},
            clock=clock,
        )

    # --- competition resolution: one-time, not part of any daily budget line -
    async def search_leagues(self, name: str) -> Response:
        """`/leagues?search=<name>`, for resolving a competition's numeric ID.

        Deliberately outside the daily allocation: this runs once per
        competition, ever, driven by a human confirming a match — not on a
        schedule, so it does not compete with fixture_sync etc. for budget.
        """
        return await self._client.get(
            "leagues",
            params={"search": name},
            job="resolve_competitions",
            entity_type="competition_lookup",
            entity_ref=name,
        )

    # --- fixture_sync: 8 calls/day, one per league ------------------------
    async def fixtures(
        self, league_id: int, season: int, *, days: int = 7, today: date | None = None
    ) -> Response:
        """A 7-day window for one league. One call covers the whole window."""
        start = today or date.today()
        return await self._client.get(
            "fixtures",
            params={
                "league": league_id,
                "season": season,
                "from": start.isoformat(),
                "to": (start + timedelta(days=days)).isoformat(),
            },
            job="fixture_sync",
            entity_type="fixture_list",
            entity_ref=f"league:{league_id}",
        )

    # --- standings_refresh: 8 calls/day -----------------------------------
    async def standings(self, league_id: int, season: int) -> Response:
        return await self._client.get(
            "standings",
            params={"league": league_id, "season": season},
            job="standings_refresh",
            entity_type="standings",
            entity_ref=f"league:{league_id}",
        )

    # --- injuries: 10 calls/day, covered fixtures only --------------------
    async def injuries(self, fixture_id: str, vendor_fixture_id: int) -> Response:
        return await self._client.get(
            "injuries",
            params={"fixture": vendor_fixture_id},
            job="injuries",
            entity_type="fixture",
            entity_id=fixture_id,
        )

    # --- confirmed_lineups: 12 calls/day, T-1h ----------------------------
    async def lineups(self, fixture_id: str, vendor_fixture_id: int) -> Response:
        """Confirmed XI at T-1h.

        This is the call that cannot live on GitHub Actions (§2.1): a lineup
        fetched 30 minutes late is a lineup fetched after the market moved.
        """
        return await self._client.get(
            "fixtures/lineups",
            params={"fixture": vendor_fixture_id},
            job="confirmed_lineups",
            entity_type="fixture",
            entity_id=fixture_id,
        )

    # --- head_to_head: 5 calls/day, new coverage only ---------------------
    async def head_to_head(self, home_vendor_id: int, away_vendor_id: int) -> Response:
        return await self._client.get(
            "fixtures/headtohead",
            params={"h2h": f"{home_vendor_id}-{away_vendor_id}", "last": 10},
            job="head_to_head",
            entity_type="h2h",
            entity_ref=f"{home_vendor_id}-{away_vendor_id}",
        )

    # --- results_settlement: 12 calls/day ---------------------------------
    async def result(self, fixture_id: str, vendor_fixture_id: int) -> Response:
        return await self._client.get(
            "fixtures",
            params={"id": vendor_fixture_id},
            job="results_settlement",
            entity_type="fixture",
            entity_id=fixture_id,
        )

    # --- qa_cross_verification: 15 calls/day ------------------------------
    async def verify(self, fixture_id: str, vendor_fixture_id: int) -> Response:
        """Deliberately its own budget line (§3.2).

        Cross-verification competing with settlement for the same allocation is
        how verification quietly stops happening on a busy day.
        """
        return await self._client.get(
            "fixtures",
            params={"id": vendor_fixture_id},
            job="qa_cross_verification",
            entity_type="fixture",
            entity_id=fixture_id,
        )


def parse_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    """Vendor shape -> our shape. No team resolution here.

    Names are carried through as source names; `TeamResolver` turns them into
    canonical ids, and it is allowed to refuse (REQ-DATA-NORM-1).
    """
    from datetime import datetime

    fixture = raw["fixture"]
    teams = raw["teams"]
    goals = raw.get("goals") or {}
    status = (fixture.get("status") or {}).get("short", "")

    return {
        "source_id": str(fixture["id"]),
        "kickoff_at": datetime.fromisoformat(
            fixture["date"].replace("Z", "+00:00")
        ),
        "status": _STATUS_MAP.get(status, "scheduled"),
        "venue": (fixture.get("venue") or {}).get("name"),
        "home_source_name": teams["home"]["name"],
        "away_source_name": teams["away"]["name"],
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
    }


_STATUS_MAP = {
    "TBD": "scheduled",
    "NS": "scheduled",
    "1H": "live",
    "HT": "live",
    "2H": "live",
    "ET": "live",
    "P": "live",
    "FT": "finished",
    "AET": "finished",
    "PEN": "finished",
    "PST": "postponed",
    "CANC": "cancelled",
    "ABD": "cancelled",
    "AWD": "finished",
    "WO": "finished",
}
