"""Apply SQL migrations in filename order.

Migrations are written to be idempotent, so this re-runs the whole directory
rather than tracking state in a table. At six files that is simpler and has one
fewer thing to get out of sync.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from ..config import Settings
from ..db import AsyncpgDb

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


async def apply(dsn: str, *, dry_run: bool) -> int:
    files = sorted(MIGRATIONS.glob("0*.sql"))
    if dry_run:
        for f in files:
            print(f"would apply {f.name}")
        return 0

    db = await AsyncpgDb.connect(dsn)
    try:
        for f in files:
            print(f"applying {f.name}")
            await db.execute(f.read_text())
    finally:
        await db.close()
    print(f"{len(files)} migrations applied")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.database_url and not args.dry_run:
        print("DATABASE_URL is not set", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(apply(settings.database_url, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
