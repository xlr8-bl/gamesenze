"""Guard against the N+1 round-trip pattern in bulk-ingest jobs.

The same bug shipped three times in this codebase — seed.py, odds_sync.py and
stats_sync.py each did one database round trip per row inside a loop, and each
time it was caught only when a real run against Supabase hung for minutes.
Unit tests never caught it because a fake database answers instantly: the cost
is network latency per statement, which is invisible without a real server and
realistic row counts.

So this is a static check instead. For the jobs that process whole vendor
payloads (hundreds to thousands of rows), an awaited database call inside a
loop is a bug by construction, regardless of how fast the tests run.

Deliberately *not* enforced everywhere. Plenty of loops legitimately do one
call per iteration — migrations must be sequential, the Worker fallback is
rate-limit paced on purpose, interactive resolvers wait on a human between
prompts, and one-time cleanup tools handle a handful of rows. Those modules
are simply out of scope rather than allowlisted line by line, which would rot
the moment anything moved.
"""

from __future__ import annotations

import ast
import pathlib

# Jobs that ingest a whole vendor payload in one run. N here is "every match
# this week" or "every team-season", not "a handful".
BULK_INGEST_MODULES = [
    "gamesenze/jobs/seed.py",
    "gamesenze/jobs/fixture_sync.py",
    "gamesenze/jobs/odds_sync.py",
    "gamesenze/jobs/stats_sync.py",
]

DB_METHODS = {"execute", "fetch", "fetchrow", "fetchval"}

# TeamResolver caches both hits and misses in-process, so calling it per row
# costs one round trip per *distinct name*, not per row — the whole reason
# that cache exists. See TeamResolver's docstring.
CACHED_CALLS = {"try_resolve", "resolve"}


def _db_touching_functions(tree: ast.Module) -> set[str]:
    """Functions in this module whose body reaches the database."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr in DB_METHODS
                ):
                    found.add(node.name)
                    break
    return found


class _LoopDbFinder(ast.NodeVisitor):
    def __init__(self, helpers: set[str]) -> None:
        self.helpers = helpers
        self.depth = 0
        self.hits: list[tuple[int, str]] = []

    def visit_For(self, node):  # noqa: N802
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    visit_AsyncFor = visit_For

    def visit_While(self, node):  # noqa: N802
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_Await(self, node):  # noqa: N802
        if self.depth > 0 and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            else:
                name = None

            if name in CACHED_CALLS:
                pass  # cached in-process; one trip per distinct value
            elif name in DB_METHODS or name in self.helpers:
                self.hits.append((node.lineno, name))
        self.generic_visit(node)


def test_bulk_ingest_jobs_make_no_database_call_inside_a_loop():
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for rel in BULK_INGEST_MODULES:
        path = root / rel
        assert path.exists(), f"{rel} moved or was renamed — update this guard"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        finder = _LoopDbFinder(_db_touching_functions(tree))
        finder.visit(tree)
        for lineno, name in finder.hits:
            offenders.append(f"{rel}:{lineno} awaits {name}() inside a loop")

    assert offenders == [], (
        "Database round trip inside a loop in a bulk-ingest job — this is the "
        "bug that hung seed.py, odds_sync.py and stats_sync.py in production. "
        "Collect the rows and write them in one batched statement (see "
        "upsert_fixtures() or _insert_odds_snapshots() for the pattern):\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_actually_detects_the_pattern_it_claims_to():
    """A guard that cannot fail is not a guard.

    Feeds the finder a module shaped exactly like the bug it exists to catch,
    and asserts it fires — so a refactor that silently breaks the detection
    (say, a new loop node type) fails here rather than going quiet.
    """
    source = """
async def sync(ctx, rows):
    for row in rows:
        await ctx.db.execute("insert into t values ($1)", row)
"""
    tree = ast.parse(source)
    finder = _LoopDbFinder(_db_touching_functions(tree))
    finder.visit(tree)
    assert [name for _, name in finder.hits] == ["execute"]


def test_the_guard_does_not_fire_on_a_correctly_batched_job():
    source = """
async def sync(ctx, rows):
    values = []
    for row in rows:
        values.append(row)
    await ctx.db.execute("insert into t select * from unnest($1::text[])", values)
"""
    tree = ast.parse(source)
    finder = _LoopDbFinder(_db_touching_functions(tree))
    finder.visit(tree)
    assert finder.hits == []


def test_the_guard_treats_the_cached_resolver_as_free():
    source = """
async def sync(ctx, resolver, rows):
    for row in rows:
        await resolver.try_resolve("src", row)
"""
    tree = ast.parse(source)
    finder = _LoopDbFinder(_db_touching_functions(tree))
    finder.visit(tree)
    assert finder.hits == []
