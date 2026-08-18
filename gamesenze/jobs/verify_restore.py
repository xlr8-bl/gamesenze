"""Prove the backup restores — §9.2, §10.

"Test the restore, not just the dump — an untested backup is a guess." This
compares row counts table by table between the live database and a restore of
the dump, and fails loudly on any table that came back short.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ..db import AsyncpgDb

# Tables whose loss would be unrecoverable, in the sense that we cannot re-fetch
# them from a vendor: our own judgements and the archive behind them.
CRITICAL = (
    "picks",
    "qa_flags",
    "team_aliases",
    "odds_snapshots",
    "data_provenance",
    "backtest_runs",
    "combo_sessions",
)


async def counts(dsn: str) -> dict[str, int]:
    db = await AsyncpgDb.connect(dsn)
    try:
        rows = await db.fetch(
            "select tablename from pg_tables where schemaname = 'public' "
            "order by tablename"
        )
        result: dict[str, int] = {}
        for row in rows:
            table = row["tablename"]
            result[table] = int(
                await db.fetchval(f'select count(*) from "{table}"') or 0
            )
        return result
    finally:
        await db.close()


async def verify(source_dsn: str, restored_dsn: str) -> int:
    source = await counts(source_dsn)
    restored = await counts(restored_dsn)

    missing_tables = sorted(set(source) - set(restored))
    problems: list[str] = [f"table {t} missing from restore" for t in missing_tables]

    for table, n in sorted(source.items()):
        if table in restored and restored[table] < n:
            problems.append(
                f"{table}: {restored[table]} rows restored vs {n} in source"
            )

    for table in CRITICAL:
        if source.get(table, 0) > 0 and restored.get(table, 0) == 0:
            problems.append(f"{table} is CRITICAL and restored empty")

    width = max((len(t) for t in source), default=10)
    for table, n in sorted(source.items()):
        print(f"  {table:<{width}}  source {n:>8}  restored {restored.get(table, 0):>8}")

    if problems:
        print("\nRESTORE VERIFICATION FAILED", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"\nrestore verified: {len(source)} tables, row counts match or exceed")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--restored", required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(verify(args.source, args.restored)))


if __name__ == "__main__":
    main()
