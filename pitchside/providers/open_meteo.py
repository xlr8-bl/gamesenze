"""Open-Meteo — unlimited and free, still metered.

Metered because the daily audit reporting "we made 40 weather calls" is how we
notice a retry loop, and because an unmetered provider is one the degradation
ladder cannot see.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..budget import BudgetMeter
from ..clock import Clock
from ..db import Db
from .base import MeteredClient, Response, Transport

BASE_URL = "https://api.open-meteo.com/v1"
PROVIDER = "open_meteo"


class OpenMeteo:
    def __init__(
        self,
        *,
        db: Db,
        meter: BudgetMeter,
        transport: Transport | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._client = MeteredClient(
            PROVIDER, BASE_URL, db=db, meter=meter, transport=transport, clock=clock
        )

    async def forecast_at_kickoff(
        self, fixture_id: str, latitude: float, longitude: float, kickoff: datetime
    ) -> Response:
        return await self._client.get(
            "forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": "temperature_2m,precipitation,wind_speed_10m",
                "start_hour": kickoff.strftime("%Y-%m-%dT%H:00"),
                "end_hour": kickoff.strftime("%Y-%m-%dT%H:00"),
                "timezone": "UTC",
            },
            job="weather",
            entity_type="fixture",
            entity_id=fixture_id,
        )


def parse_forecast(raw: dict[str, Any]) -> dict[str, Any] | None:
    hourly = raw.get("hourly") or {}
    temps = hourly.get("temperature_2m") or []
    if not temps:
        return None
    precip = (hourly.get("precipitation") or [None])[0]
    return {
        "temperature_c": temps[0],
        "precip_mm": precip,
        "wind_kph": (hourly.get("wind_speed_10m") or [None])[0],
        "conditions": _describe(temps[0], precip),
    }


def _describe(temp: float | None, precip: float | None) -> str:
    parts = []
    if precip is not None and precip > 0.5:
        parts.append("wet")
    if temp is not None and temp < 5:
        parts.append("cold")
    return ", ".join(parts) or "clear"
