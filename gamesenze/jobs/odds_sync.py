"""Populate `odds_snapshots` from The Odds API — §3.5, runs before analysis.

This is the piece that closed the last gap in the pipeline: nightly_analysis
only drafts a pick for a fixture that already has an odds snapshot, and
nothing wrote the first one. The `fixtures.covered` flag looked like the
missing link, but it is set by nightly_analysis itself *after* a fixture is
priced — a fixture could never become covered, so nothing could ever poll it,
so nothing could ever be priced. Circular, and only visible once the whole
pipeline ran live end to end.

The Odds API sidesteps that: one call returns an entire league's board (see
providers/odds_api.py for why that made it the better vendor here), so there
is no per-fixture admission step to gate on. Every scheduled, resolved
fixture in a covered league gets matched against that board by team names —
already resolved through the same alias table as everything else, so a name
this vendor sends that we do not recognise blocks that one match rather than
being guessed (REQ-DATA-NORM-1) — and by proximity of kickoff time.

Runs once/day (8 credits — one per covered league) as a step before
nightly_analysis. That means every snapshot in the current setup carries the
same window_label; there is no separate closing-line pass yet. Tracked as a
follow-up, not silently pretended away — see docs/OPERATIONS.md. Increasing
the frequency later is a config change (ODDS_API budget has headroom for
it), not a rewrite.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from ..normalize import TeamResolver
from ..providers.base import ProviderError
from ..providers.odds_api import LEAGUE_KEYS, OddsApi, parse_odds
from ._runtime import JobContext, run_job

log = logging.getLogger("gamesenze.odds_sync")

# How far a vendor's commence_time may drift from our stored kickoff_at and
# still count as the same fixture. Generous on purpose: this is matching two
# independent vendors' clocks, not the same source twice.
KICKOFF_TOLERANCE = timedelta(hours=6)


async def covered_competitions(ctx: JobContext) -> list[dict]:
    """Resolved-and-synced competitions this vendor actually has a board for."""
    rows = await ctx.db.fetch(
        """
        select c.id as competition_id, c.name
          from competitions c
          join competition_source_ids s
            on s.competition_id = c.id and s.source = 'football_data'
        """
    )
    return [r for r in rows if r["name"] in LEAGUE_KEYS]


async def match_fixture(
    ctx: JobContext, competition_id: str, home_id: str, away_id: str, commence_at
) -> str | None:
    """Single-game lookup. Prefer `match_fixtures` for a whole board."""
    found = await match_fixtures(
        ctx, [(competition_id, home_id, away_id, commence_at)]
    )
    return found.get((str(competition_id), str(home_id), str(away_id), commence_at))


async def match_fixtures(ctx: JobContext, games: list[tuple]) -> dict[tuple, str]:
    """Match a whole league board to fixtures in one query.

    One round trip for the batch instead of one per game: a league board is
    up to ~80 games and there are 8 leagues, so per-game lookups are ~500
    sequential round trips to Supabase on top of the vendor calls. Keyed by
    (competition_id, home_id, away_id, commence_at) so callers can look
    their own game back up.
    """
    if not games:
        return {}

    rows = await ctx.db.fetch(
        """
        select input.idx, f.id as fixture_id
          from unnest($1::int[], $2::uuid[], $3::uuid[], $4::uuid[],
                      $5::timestamptz[])
               as input(idx, competition_id, home_id, away_id, commence_at)
          left join lateral (
              select id from fixtures
               where competition_id = input.competition_id
                 and home_team_id = input.home_id
                 and away_team_id = input.away_id
                 and status = 'scheduled'
                 and kickoff_at between input.commence_at - $6::interval
                                     and input.commence_at + $6::interval
               order by abs(extract(epoch from (kickoff_at - input.commence_at)))
               limit 1
          ) f on true
        """,
        list(range(len(games))),
        [g[0] for g in games],
        [g[1] for g in games],
        [g[2] for g in games],
        [g[3] for g in games],
        KICKOFF_TOLERANCE,
    )

    out: dict[tuple, str] = {}
    for r in rows:
        if r["fixture_id"] is None:
            continue
        comp, home, away, commence = games[r["idx"]]
        out[(str(comp), str(home), str(away), commence)] = str(r["fixture_id"])
    return out


async def main(ctx: JobContext) -> int:
    if not ctx.settings.odds_api_key:
        log.warning("ODDS_API_KEY not set; skipping odds_sync")
        return 0

    resolver = TeamResolver(ctx.db, ctx.clock)
    client = OddsApi(
        ctx.settings.odds_api_key, db=ctx.db, meter=ctx.meter, clock=ctx.clock
    )

    competitions = await covered_competitions(ctx)
    if not competitions:
        log.warning(
            "no odds_api-covered competition is resolved against "
            "football_data yet — run fixture_sync first"
        )
        return 0

    # Collected across the whole run and written in one batched insert at the
    # end (see below) instead of one execute() per row — a single game can
    # carry 50+ rows (bookmakers x markets x outcomes), and ~80 games' worth
    # of one-row-per-round-trip inserts is what made this slow the first
    # time it ran for real. Same fix as jobs/seed.py's original slowness.
    snap_fixture_ids: list[str] = []
    snap_captured_ats: list = []
    snap_bookmakers: list[str] = []
    snap_markets: list[str] = []
    snap_selections: list[str] = []
    snap_odds: list[float] = []
    snap_window_labels: list[str] = []
    snap_is_closing: list[bool] = []

    # One HTTP call per league, ~20-30s each for a big payload (many games x
    # many bookmakers). Nothing here needs to be sequential — each league is
    # an independent vendor call, and budget.reserve() is a single atomic
    # upsert safe under concurrency (see budget.py) — so fetch them all at
    # once instead of paying that latency eight times in a row.
    async def _fetch(comp):
        import asyncpg

        sport_key = LEAGUE_KEYS[comp["name"]]
        try:
            # h2h + totals are both core markets on this endpoint, so the two
            # come back in one call (cost = markets x regions = 2 credits per
            # league). BTTS and double-chance are additional markets The Odds
            # API only serves per-event, so they are not requested here.
            response = await client.odds(sport_key, markets="h2h,totals")
        except ProviderError as exc:
            log.error("odds_api %s: %s", sport_key, exc)
            return comp, []
        except (
            asyncpg.exceptions.ConnectionDoesNotExistError,
            asyncpg.exceptions.InterfaceError,
            TimeoutError,
            OSError,
        ) as exc:
            # A dropped connection here (already retried once inside
            # _store_provenance) is this one league's problem, not the
            # batch's — asyncio.gather() would otherwise let one flaky
            # league's persistent failure discard every other league's
            # already-successful fetch. Seen live.
            log.error("odds_api %s: connection issue, skipping this league: %s", sport_key, exc)
            return comp, []
        games = response.body if isinstance(response.body, list) else []
        return comp, games

    fetched = await asyncio.gather(*(_fetch(comp) for comp in competitions))

    matched = unmatched = rejected = 0

    # Pre-resolve every team name across every board in one query, so the
    # per-game try_resolve calls below are all cache reads rather than one
    # Supabase round trip per distinct name on a cold cache (a full board is
    # ~160 names — that is ~160 sequential round trips of pure latency saved).
    await resolver.warm(
        "odds_api",
        [
            name
            for _, games in fetched
            for game in games
            for name in (game.get("home_team", ""), game.get("away_team", ""))
        ],
    )

    # Resolve every game's teams first (the resolver caches, so a repeated
    # name costs nothing), then look every game's fixture up in one query
    # rather than one round trip per game across ~8 boards.
    candidates = []
    for comp, games in fetched:
        for game in games:
            home_id = await resolver.try_resolve("odds_api", game.get("home_team", ""))
            away_id = await resolver.try_resolve("odds_api", game.get("away_team", ""))
            if home_id is None or away_id is None:
                unmatched += 1
                continue
            commence_at = _parse_commence(game.get("commence_time"))
            candidates.append((comp["competition_id"], home_id, away_id, commence_at, game))

    fixture_by_key = await match_fixtures(ctx, [c[:4] for c in candidates])

    for competition_id, home_id, away_id, commence_at, game in candidates:
        key = (str(competition_id), str(home_id), str(away_id), commence_at)
        fixture_id = fixture_by_key.get(key)
        if fixture_id is None:
            unmatched += 1
            continue

        rows, rejections = parse_odds(
            game, captured_at=ctx.clock.now(), window_label="daily"
        )
        rejected += len(rejections)
        for r in rejections:
            log.warning("fixture %s: rejected odds row: %s", fixture_id, r)

        for row in rows:
            snap_fixture_ids.append(fixture_id)
            snap_captured_ats.append(row["captured_at"])
            snap_bookmakers.append(row["bookmaker"])
            snap_markets.append(row["market"])
            snap_selections.append(row["selection"])
            snap_odds.append(row["decimal_odds"])
            snap_window_labels.append(row["window_label"])
            snap_is_closing.append(row["is_closing"])
        if rows:
            matched += 1

    if snap_fixture_ids:
        await _insert_odds_snapshots(
            ctx,
            snap_fixture_ids,
            snap_captured_ats,
            snap_bookmakers,
            snap_markets,
            snap_selections,
            snap_odds,
            snap_window_labels,
            snap_is_closing,
        )

    print(
        f"odds captured for {matched} fixture(s), {unmatched} game(s) not "
        f"matched to a fixture, {rejected} odds row(s) rejected by QA"
    )
    return 0


_INSERT_ODDS_SQL = """
    insert into odds_snapshots (fixture_id, captured_at, bookmaker,
                                market, selection, decimal_odds,
                                window_label, is_closing)
    select * from unnest(
        $1::uuid[], $2::timestamptz[], $3::text[], $4::text[],
        $5::text[], $6::numeric[], $7::text[], $8::bool[]
    )
    -- Same (fixture, bookmaker, market, selection, captured_at) twice is
    -- the same fact twice, not new information — this is what makes the
    -- retry below safe rather than a silent double-write if the first
    -- attempt actually committed before a dropped-connection error
    -- reached us.
    on conflict (fixture_id, bookmaker, market, selection, captured_at)
        do nothing
"""


async def _insert_odds_snapshots(ctx: JobContext, *columns) -> None:
    """Write the batch, retrying once if a pooled connection drops mid-write.

    Safe to retry because of the on-conflict clause in _INSERT_ODDS_SQL: a
    duplicate of the same insert is a no-op, not a double-write. Seen live
    on a flaky client connection: `ConnectionDoesNotExistError` raised from
    inside the query itself, after several successful vendor calls already
    did the expensive part of the job — losing all of that to one dropped
    connection is worse than one retry.
    """
    import asyncpg

    try:
        await ctx.db.execute(_INSERT_ODDS_SQL, *columns)
    except (
        asyncpg.exceptions.ConnectionDoesNotExistError,
        asyncpg.exceptions.InterfaceError,
        TimeoutError,
        OSError,
    ):
        log.warning("odds_snapshots write hit a dropped connection; retrying once")
        await asyncio.sleep(1.0)
        await ctx.db.execute(_INSERT_ODDS_SQL, *columns)


def _parse_commence(value: str | None):
    from datetime import datetime

    if not value:
        raise ValueError("odds_api game missing commence_time")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


if __name__ == "__main__":
    run_job(main)
