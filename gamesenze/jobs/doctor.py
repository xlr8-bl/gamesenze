"""Check the environment before anything tries to connect.

Run this first when a job fails with a connection error. It reports what your
.env actually loaded — with the password masked — and tries the database once,
turning the usual 40-line asyncpg traceback into a single clear line.

    python -m gamesenze.jobs.doctor
"""

from __future__ import annotations

import asyncio
import re
import sys
from urllib.parse import urlsplit

from gamesenze.config import Settings


def _mask(dsn: str) -> str:
    # Hide the password but keep everything else visible for eyeballing.
    return re.sub(r"(:)([^:@/]+)(@)", r"\1***\3", dsn) if dsn else "(empty)"


async def _check_db(dsn: str) -> tuple[bool, str]:
    if not dsn or "<" in dsn or ">" in dsn:
        return False, "DATABASE_URL is empty or still has the .env placeholders (<...>)."
    try:
        from gamesenze.db import AsyncpgDb

        db = await AsyncpgDb.connect(dsn)
        val = await db.fetchval("select version()")
        await db.close()
        return True, str(val).split(" on ")[0]
    except SystemExit as exc:  # our own clear message from db.connect
        return False, str(exc).splitlines()[0]
    except Exception as exc:  # noqa: BLE001 - report whatever it is, don't crash
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    s = Settings.from_env()
    host = urlsplit(s.database_url).hostname if s.database_url else None

    print("Environment check")
    print("-----------------")
    print(f"DATABASE_URL      {_mask(s.database_url)}")
    if host:
        pooler = "pooler.supabase.com" in host
        print(f"  host            {host}  ({'pooler, good' if pooler else 'not the pooler'})")
        if host.startswith("db.") and host.endswith(".supabase.co"):
            print("  WARNING         this is the DIRECT host (IPv6-only). Use the Session pooler URI.")
    print(f"FOOTBALL_DATA_KEY {'set' if s.football_data_key else 'MISSING (fixtures need it)'}")
    print(f"ODDS_API_KEY      {'set' if s.odds_api_key else 'MISSING (no odds = no publishable picks)'}")
    print(f"SCRAPER_CONTACT   {s.scraper_contact or '(unset)'}")
    print()

    ok, detail = asyncio.run(_check_db(s.database_url))
    print(f"Database          {'OK — ' + detail if ok else 'FAILED — ' + detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
