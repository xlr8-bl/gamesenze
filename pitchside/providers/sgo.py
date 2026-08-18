"""SportsGameOdds — 2,500 objects/month, 2,000 planned (§3.3).

One object = one full event across all books and markets, which is why the
cadence in §3.4 is a per-fixture plan rather than a per-market one: fetching
five markets for a fixture costs the same one object as fetching one.

REQ-BUDGET-1: only fixtures with a published pick get snapshotted. There is
deliberately no "list events" method on this client. A board poll is how a
2,000-object month becomes a 2,500-object month.
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

BASE_URL = "https://api.sportsgameodds.com/v2"
PROVIDER = "sportsgameodds"


class SportsGameOdds:
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
            headers={"X-Api-Key": api_key},
            clock=clock,
        )

    async def event_odds(
        self, fixture_id: str, vendor_event_id: str, *, window_label: str
    ) -> Response:
        """One object: the whole event across every book and market."""
        return await self._client.get(
            f"events/{vendor_event_id}/odds",
            job=f"snapshot:{window_label}",
            entity_type="fixture",
            entity_id=fixture_id,
        )


def parse_odds(
    raw: dict[str, Any], *, captured_at: datetime, window_label: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Flatten an event object into odds rows, dropping what fails §5.1/§5.3.

    Returns (rows, rejections). Rejections are returned rather than raised: one
    nonsense price from one book should not cost us the other forty, but it
    must still be visible to the audit.
    """
    rows: list[dict[str, Any]] = []
    rejections: list[str] = []

    for book in raw.get("bookmakers", []) or []:
        book_name = book.get("key") or book.get("name") or "unknown"
        for market in book.get("markets", []) or []:
            market_key = market.get("key") or market.get("name") or "unknown"
            for outcome in market.get("outcomes", []) or []:
                selection = outcome.get("name") or outcome.get("key")
                price = outcome.get("price") or outcome.get("decimal")
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
