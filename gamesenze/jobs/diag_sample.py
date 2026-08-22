"""Explain why nightly_analysis drafts 0 on the §5.4 sample gate.

Run this after weekly_scrape + odds_sync when nightly_analysis skips every
fixture with "sample below the §5.4 minimum". It answers one question: do the
upcoming fixtures' team IDs actually line up with the historical
team_match_stats rows, or did two sources resolve the same club to two
different canonical teams?

    python -m gamesenze.jobs.diag_sample
"""

from __future__ import annotations

import asyncio

from gamesenze.config import Settings
from gamesenze.db import AsyncpgDb


async def _run() -> int:
    s = Settings.from_env()
    db = await AsyncpgDb.connect(s.database_url)

    total = await db.fetchval("select count(*) from team_match_stats")
    finished = await db.fetchval(
        "select count(*) from team_match_stats where status = 'finished'"
    )
    distinct_teams = await db.fetchval(
        "select count(distinct team_id) from team_match_stats"
    )
    span = await db.fetchrow(
        "select min(kickoff_at) lo, max(kickoff_at) hi from team_match_stats"
    )
    print("team_match_stats")
    print(f"  rows                {total}")
    print(f"  status='finished'   {finished}")
    print(f"  distinct team_id    {distinct_teams}")
    print(f"  kickoff span        {span['lo']}  ->  {span['hi']}")
    print()

    # The exact fixtures nightly_analysis considers: upcoming, both teams set.
    fixtures = await db.fetch(
        """
        select f.id, f.kickoff_at,
               th.canonical_name home_name, f.home_team_id,
               ta.canonical_name away_name, f.away_team_id
          from fixtures f
          join teams th on th.id = f.home_team_id
          join teams ta on ta.id = f.away_team_id
         where f.kickoff_at between now() and now() + interval '48 hours'
         order by f.kickoff_at
         limit 8
        """
    )
    if not fixtures:
        print("No upcoming fixtures in the next 48h. Nothing for nightly to draft.")
        await db.close()
        return 0

    print("Upcoming fixtures — finished stats found for each side (need >= 6):")
    print()
    gate_ok = 0
    for f in fixtures:
        home_n = await db.fetchval(
            "select count(*) from team_match_stats "
            "where team_id = $1 and kickoff_at < $2 and status = 'finished'",
            f["home_team_id"], f["kickoff_at"],
        )
        away_n = await db.fetchval(
            "select count(*) from team_match_stats "
            "where team_id = $1 and kickoff_at < $2 and status = 'finished'",
            f["away_team_id"], f["kickoff_at"],
        )
        ok = home_n >= 6 and away_n >= 6
        gate_ok += ok
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {f['home_name']} ({home_n}) v {f['away_name']} ({away_n})")

    has_stats = await db.fetchval(
        "select count(distinct team_id) from team_match_stats where status='finished'"
    )
    on_fixt = await db.fetchval(
        """select count(distinct t) from (
             select home_team_id t from fixtures
             where kickoff_at between now() and now()+interval '48 hours'
             union select away_team_id from fixtures
             where kickoff_at between now() and now()+interval '48 hours'
           ) x
           where t in (select team_id from team_match_stats where status='finished')"""
    )
    print()
    print(f"teams with finished stats:             {has_stats}")
    print(f"upcoming-fixture teams that have any:   {on_fixt}")

    if gate_ok < len(fixtures):
        print()
        print("Upcoming-fixture team ids with NO finished stats, and whether a")
        print("DIFFERENTLY-NAMED team row holds those stats (the split-canonical bug):")
        print()
        # Every distinct team id on an upcoming fixture.
        up = await db.fetch(
            """
            select distinct t.id, t.canonical_name
              from (
                select home_team_id id from fixtures
                where kickoff_at between now() and now()+interval '48 hours'
                union
                select away_team_id from fixtures
                where kickoff_at between now() and now()+interval '48 hours'
              ) f join teams t on t.id = f.id
             order by 2
            """
        )
        for u in up:
            n = await db.fetchval(
                "select count(*) from team_match_stats "
                "where team_id = $1 and status='finished'",
                u["id"],
            )
            if n >= 6:
                continue
            # Any team that DOES have stats and shares the first word of the name.
            first = (u["canonical_name"].split() or [u["canonical_name"]])[0]
            twin = await db.fetch(
                """
                select t.canonical_name, count(*) n
                  from teams t join team_match_stats s on s.team_id = t.id
                 where s.status = 'finished'
                   and t.id <> $1
                   and lower(t.canonical_name) like lower($2)
                 group by t.canonical_name
                 order by 2 desc
                """,
                u["id"], f"%{first}%",
            )
            twin_str = ", ".join(f"{r['canonical_name']} ({r['n']})" for r in twin) or "none"
            print(f"  '{u['canonical_name']}' has {n} -> stats live under: {twin_str}")

    await db.close()
    return 0


async def _edges() -> int:
    """Replay nightly_analysis's candidate loop and print every edge.

    Answers the follow-up question: for the covered-league fixtures that DO
    pass the sample gate, does the model simply find no value (a legit quiet
    day), or is the pricing off? Prints market, our prob, implied prob and
    edge for each priced selection, and flags the ones that clear the 4%
    threshold nightly needs.
    """
    from gamesenze.analysis.model import MatchModel
    from gamesenze.backtest.features import get_features_as_of
    from gamesenze.odds.math import edge as edge_fn

    s = Settings.from_env()
    db = await AsyncpgDb.connect(s.database_url)
    model = MatchModel()

    rows = await db.fetch(
        """
        select f.id, f.kickoff_at, f.home_team_id, f.away_team_id,
               th.canonical_name home, ta.canonical_name away,
               o.market, o.selection, o.decimal_odds
          from fixtures f
          join teams th on th.id = f.home_team_id
          join teams ta on ta.id = f.away_team_id
          join lateral (
              select market, selection, decimal_odds
                from odds_snapshots
               where fixture_id = f.id
               order by captured_at desc limit 20
          ) o on true
         where f.status = 'scheduled'
           and f.kickoff_at between now() and now() + interval '48 hours'
         order by f.kickoff_at
        """
    )
    by_fix: dict = {}
    for r in rows:
        by_fix.setdefault(str(r["id"]), []).append(r)

    print(f"{len(by_fix)} scheduled fixture(s) with odds in the next 48h")
    priced = drafted = gated = 0
    best_overall = 0.0
    for rs in by_fix.values():
        f0 = rs[0]
        home = await get_features_as_of(db, str(f0["home_team_id"]), f0["kickoff_at"])
        away = await get_features_as_of(db, str(f0["away_team_id"]), f0["kickoff_at"])
        if home is None or away is None:
            gated += 1
            continue
        priced += 1
        prices = model.price(home, away)
        best = None
        for r in rs:
            our = prices.probability(r["market"], r["selection"])
            if our is None:
                continue
            e = edge_fn(our, float(r["decimal_odds"]))
            if best is None or e > best[0]:
                best = (e, r["market"], r["selection"], our, float(r["decimal_odds"]))
        if best is None:
            print(f"  {f0['home']} v {f0['away']}: priced, no market mapped")
            continue
        e, mkt, sel, our, dec = best
        best_overall = max(best_overall, e)
        hit = "  <-- DRAFTS" if e >= 0.04 else ""
        if e >= 0.04:
            drafted += 1
        print(f"  {f0['home']} v {f0['away']}: best {sel} [{mkt}] "
              f"our {our:.0%} vs implied {1/dec:.0%} @ {dec:.2f}  edge {e:+.1%}{hit}")

    print()
    print(f"gated (no stats): {gated}   priced: {priced}   "
          f"would draft (edge>=4%): {drafted}   best edge seen: {best_overall:+.1%}")
    await db.close()
    return 0


import sys

if __name__ == "__main__":
    mode = _edges if "--edges" in sys.argv else _run
    raise SystemExit(asyncio.run(mode()))
