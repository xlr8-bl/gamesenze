"""Shared job wiring: connect, run, close, report."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable

from ..alerts import Alerter
from ..budget import BudgetMeter
from ..clock import SystemClock
from ..config import Settings
from ..db import AsyncpgDb, Db


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )


class JobContext:
    def __init__(self, db: Db, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.clock = SystemClock()
        self.meter = BudgetMeter(db, self.clock)
        self.alerter = Alerter(settings.alert_webhook_url)


def run_job(main: Callable[[JobContext], Awaitable[int | None]]) -> None:
    """Run an async job and exit with its status.

    A job that raises exits non-zero so the workflow goes red. §8 tolerates
    degraded output; it does not tolerate a failure nobody sees.
    """
    configure_logging()
    settings = Settings.from_env()
    if not settings.database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        raise SystemExit(2)

    async def runner() -> int:
        db = await AsyncpgDb.connect(settings.database_url)
        try:
            return int(await main(JobContext(db, settings)) or 0)
        finally:
            await db.close()

    raise SystemExit(asyncio.run(runner()))
