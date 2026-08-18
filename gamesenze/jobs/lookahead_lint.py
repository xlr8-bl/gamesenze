"""Static guard against lookahead bias — REQ-QA-4, §10.

"`get_features_as_of()` used everywhere — zero full-season lookups in feature
code" is a checklist item, and a checklist item that nothing enforces is a
checklist item that stops being true in about three weeks.

So this walks the AST of the analysis modules and fails on the patterns that
let future data into a feature:

  * a SQL string that filters on `season` without an `as_of`-style bound;
  * a query against a match-history table with no upper time bound at all;
  * a call to `datetime.now()` inside feature code, which silently makes a
    backtest evaluate "as of today" rather than as of the fixture.

It is deliberately narrow. A lint that cries wolf gets suppressed, and a
suppressed lint is worse than none.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Where features are computed. Ingestion and jobs legitimately read whole
# seasons; feature code never may.
FEATURE_PATHS = ("gamesenze/backtest", "gamesenze/analysis")

HISTORY_TABLES = ("team_match_stats", "player_match_stats", "matches", "fixtures")
# Prose mentioning "selection" and "fixtures" is not a query. Requiring an
# actual SELECT ... FROM keeps the lint quiet enough to stay switched on.
SQL_SHAPE = re.compile(r"\bselect\b[\s\S]*\bfrom\b", re.IGNORECASE)
SEASON_FILTER = re.compile(r"\bseason\s*=", re.IGNORECASE)
TIME_BOUND = re.compile(
    r"kickoff_at\s*<|kickoff_at\s*<=|as_of|before\s*\$|<\s*\$\d", re.IGNORECASE
)


@dataclass
class Finding:
    path: Path
    line: int
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.detail}"


class LookaheadVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[Finding] = []
        self.docstrings: set[int] = set()

    def visit_Module(self, node: ast.Module) -> None:
        self._note_docstring(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._note_docstring(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._note_docstring(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._note_docstring(node)
        self.generic_visit(node)

    def _note_docstring(self, node: ast.AST) -> None:
        # `body` is a statement list on modules, functions and classes, but a
        # bare expression on nodes like IfExp — only the former can hold a
        # docstring.
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            return
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            if isinstance(first.value.value, str):
                self.docstrings.add(id(first.value))

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, str) or id(node) in self.docstrings:
            return
        sql = node.value
        lowered = sql.lower()
        if not SQL_SHAPE.search(sql):
            return

        if SEASON_FILTER.search(sql) and not TIME_BOUND.search(sql):
            self.findings.append(
                Finding(
                    self.path,
                    node.lineno,
                    "season-filter",
                    "query filters on `season` with no as-of bound. Never "
                    "`WHERE season = X` — always `WHERE kickoff_at < as_of`.",
                )
            )

        if any(t in lowered for t in HISTORY_TABLES) and not TIME_BOUND.search(sql):
            self.findings.append(
                Finding(
                    self.path,
                    node.lineno,
                    "unbounded-history",
                    "query reads match history with no upper time bound; it "
                    "can see matches that had not happened yet.",
                )
            )

    def visit_Call(self, node: ast.Call) -> None:
        target = node.func
        name = getattr(target, "attr", None) or getattr(target, "id", None)
        if name in ("now", "utcnow", "today"):
            self.findings.append(
                Finding(
                    self.path,
                    node.lineno,
                    "wall-clock",
                    f"`{name}()` in feature code makes a backtest evaluate as "
                    "of today rather than as of the fixture. Take `as_of` as "
                    "an argument.",
                )
            )
        self.generic_visit(node)


def scan(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for directory in FEATURE_PATHS:
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=str(path))
            visitor = LookaheadVisitor(path.relative_to(root))
            # Two passes: docstrings are registered by their parent node, which
            # a single walk would reach only after visiting the string itself.
            for node in ast.walk(tree):
                visitor._note_docstring(node)
            visitor.visit(tree)
            findings.extend(visitor.findings)
    return findings


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    findings = scan(root)
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(
            f"\n{len(findings)} lookahead risk(s). A model that has seen the "
            "future backtests beautifully and loses money live (§5.7).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print("no lookahead risks found in feature code")
    raise SystemExit(0)


if __name__ == "__main__":
    main()
