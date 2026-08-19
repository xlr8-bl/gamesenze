"""Team name normalisation — §4.3. Do this first.

Every source spells team names differently. "Man Utd" / "Manchester Utd" /
"Manchester United" / "Man United" are one team across four sources.
Unresolved name mismatches are the single largest source of silent data
corruption in multi-source sports pipelines — they do not error, they quietly
join the wrong rows, and the first symptom is a pick built on another team's
form.

REQ-DATA-NORM-1: every ingested record resolves to a canonical team ID before
it is stored. An unresolved name raises a QA flag and blocks the fixture from
publication. It does not get a best guess.

The fuzzy matcher below exists only to *suggest* aliases to a human reviewing
the backlog. It never resolves an ingestion. That distinction is the whole
point: a 0.94-similarity guess that is wrong corrupts data exactly as
thoroughly as a 0.4 one, and nothing downstream can tell.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

from .clock import Clock, SystemClock
from .db import Db
from .qa.errors import QAViolation, Severity
from .qa.flags import FlagStore

# Tokens that carry no identity: every source drops or keeps them arbitrarily.
_NOISE_TOKENS = {
    "fc", "afc", "cf", "sc", "ac", "as", "ss", "ssc", "cd", "ud", "sv", "vfl",
    "vfb", "tsg", "fsv", "bsc", "rc", "sd", "club", "de", "futbol", "football",
}

_ABBREVIATIONS = {
    "utd": "united",
    "man": "manchester",
    "wolves": "wolverhampton",
    "spurs": "tottenham",
    "st": "saint",
    "int": "internazionale",
    "atl": "atletico",
    "borussia": "borussia",
}


def normalise_name(name: str) -> str:
    """A comparison key, not a display name.

    Strips accents, punctuation, boilerplate club suffixes and expands the
    abbreviations sources actually use. Deterministic and side-effect free so
    the same input always produces the same key across runs.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    lowered = ascii_name.lower()
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    tokens = [t for t in cleaned.split() if t]
    expanded = [_ABBREVIATIONS.get(t, t) for t in tokens]
    meaningful = [t for t in expanded if t not in _NOISE_TOKENS]
    # If a name is nothing but noise tokens, keep them rather than return "".
    return " ".join(meaningful or expanded)


@dataclass(frozen=True)
class AliasSuggestion:
    source_name: str
    canonical_team_id: str
    canonical_name: str
    similarity: float


def suggest_aliases(
    source_name: str,
    candidates: dict[str, str],
    *,
    limit: int = 3,
    floor: float = 0.6,
) -> list[AliasSuggestion]:
    """Rank canonical teams by similarity, for a human to accept or reject.

    `candidates` maps canonical_team_id -> canonical_name.
    """
    key = normalise_name(source_name)
    scored = [
        AliasSuggestion(
            source_name,
            team_id,
            name,
            difflib.SequenceMatcher(None, key, normalise_name(name)).ratio(),
        )
        for team_id, name in candidates.items()
    ]
    scored = [s for s in scored if s.similarity >= floor]
    scored.sort(key=lambda s: s.similarity, reverse=True)
    return scored[:limit]


class UnresolvedTeamName(QAViolation):
    def __init__(self, source: str, source_name: str) -> None:
        super().__init__(
            f"unresolved team name {source_name!r} from {source}",
            severity=Severity.BLOCK,
            issue="unresolved_team_name",
        )
        self.source = source
        self.source_name = source_name


class TeamResolver:
    """Exact alias lookup with an in-process cache.

    The cache matters: fixture sync resolves the same twenty names repeatedly
    within one job, and each miss would otherwise be a round trip. It caches
    failures too — an unresolved name recurs once per match a team plays (up
    to ~38 times a season), and without this a single unresolvable team name
    cost 3 round trips (a lookup, an unresolved_team_names upsert, a QA flag
    upsert) *per occurrence* rather than once per job run. Seen live: with a
    real season's worth of Understat data and several genuinely unresolved
    names, that turned a batched job that should run in seconds into one
    that hung for 10+ minutes and had to be killed.

    The one behavioural cost: `unresolved_team_names.sightings` now counts
    roughly "distinct job runs this name was seen in" rather than "every
    individual row it appeared in" — arguably the more useful number for a
    human deciding whether a backlog entry is worth resolving, and a
    reasonable trade for not redoing the same two writes hundreds of times.
    """

    def __init__(self, db: Db, clock: Clock | None = None) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._flags = FlagStore(db, clock)
        self._cache: dict[tuple[str, str], str] = {}
        self._unresolved_cache: set[tuple[str, str]] = set()

    async def resolve(
        self, source: str, source_name: str, *, fixture_id: str | None = None
    ) -> str:
        """Canonical team id, or raise. Never guesses (REQ-DATA-NORM-1)."""
        cache_key = (source, source_name)
        if cache_key in self._cache:
            return self._cache[cache_key]
        if cache_key in self._unresolved_cache:
            raise UnresolvedTeamName(source, source_name)

        team_id = await self._db.fetchval(
            "select canonical_team_id from team_aliases "
            "where source = $1 and source_name = $2",
            source,
            source_name,
        )

        if team_id is None:
            self._unresolved_cache.add(cache_key)
            await self._record_unresolved(source, source_name)
            await self._flags.raise_flag(
                "fixture" if fixture_id else "team",
                fixture_id,
                issue="unresolved_team_name",
                detail=f"{source} sent {source_name!r}, which is not in "
                       "team_aliases; fixture blocked from publication",
                severity=Severity.BLOCK,
                entity_ref=None if fixture_id else f"{source}:{source_name}",
            )
            raise UnresolvedTeamName(source, source_name)

        team_id = str(team_id)
        self._cache[cache_key] = team_id
        return team_id

    async def try_resolve(
        self, source: str, source_name: str, *, fixture_id: str | None = None
    ) -> str | None:
        """`resolve` for callers that want to keep processing the batch."""
        try:
            return await self.resolve(source, source_name, fixture_id=fixture_id)
        except UnresolvedTeamName:
            return None

    async def _record_unresolved(self, source: str, source_name: str) -> None:
        await self._db.execute(
            """
            insert into unresolved_team_names (source, source_name, first_seen,
                                               last_seen, sightings)
            values ($1, $2, $3, $3, 1)
            on conflict (source, source_name) do update
                set last_seen = $3,
                    sightings = unresolved_team_names.sightings + 1
            """,
            source,
            source_name,
            self._clock.now(),
        )

    async def add_alias(
        self,
        source: str,
        source_name: str,
        canonical_team_id: str,
        source_id: str | None = None,
    ) -> None:
        """Record a human-accepted alias and clear its backlog entry."""
        await self._db.execute(
            """
            insert into team_aliases (canonical_team_id, source, source_name,
                                      source_id)
            values ($1, $2, $3, $4)
            on conflict (source, source_name) do update
                set canonical_team_id = excluded.canonical_team_id,
                    source_id = excluded.source_id
            """,
            canonical_team_id,
            source,
            source_name,
            source_id,
        )
        await self._db.execute(
            "update unresolved_team_names set resolved_at = $3 "
            "where source = $1 and source_name = $2",
            source,
            source_name,
            self._clock.now(),
        )
        self._cache[(source, source_name)] = canonical_team_id
        self._unresolved_cache.discard((source, source_name))

    async def backlog(self) -> list[dict]:
        return await self._db.fetch(
            "select * from unresolved_team_names where resolved_at is null "
            "order by sightings desc, last_seen desc"
        )

    async def sweep_resolved(self) -> int:
        """Auto-clear backlog entries a later alias made resolvable.

        `unresolved_team_names` is written on every failed lookup but only
        ever cleared by an explicit `add_alias` call — reseeding with a
        correct variant does not touch it. Left alone, the backlog shows
        every name that has *ever* failed, including ones that resolve fine
        right now, which is exactly the confusion this method exists to
        remove: a human reading a 130-line backlog where most entries already
        have a 1.00 match has no way to tell "still broken" from "already
        fixed, nobody told this table."

        Calling `try_resolve` on an already-resolvable name is side-effect
        free — it hits the cache path in `resolve()` and returns, no re-flag,
        no re-record. Only genuinely unresolved names touch those paths.
        """
        cleared = 0
        for row in await self.backlog():
            team_id = await self.try_resolve(row["source"], row["source_name"])
            if team_id is not None:
                await self._db.execute(
                    "update unresolved_team_names set resolved_at = $3 "
                    "where source = $1 and source_name = $2",
                    row["source"],
                    row["source_name"],
                    self._clock.now(),
                )
                cleared += 1
        return cleared
