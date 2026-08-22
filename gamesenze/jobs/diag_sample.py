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
               th.name home_name, f.home_team_id,
               ta.name away_name, f.away_team_id
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

    print()
    if gate_ok == 0:
        print("Every fixture FAILS. The stats exist but don't match these team IDs.")
        print("Checking whether the same club exists under two team rows...")
        print()
        # Clubs that have stats but whose id never appears on an upcoming fixture,
        # yet a same-named team row does — the duplicate-canonical smell.
        dupes = await db.fetch(
            """
            select name, count(*) n, array_agg(id::text) ids
              from teams
             group by name
            having count(*) > 1
             order by name
            """
        )
        if dupes:
            print("Duplicate team rows (same name, different id) — this is the bug:")
            for d in dupes:
                print(f"  {d['name']}: {d['n']} rows  {d['ids']}")
        else:
            print("No duplicate team names. The mismatch is elsewhere:")
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
            print(f"  teams with finished stats:            {has_stats}")
            print(f"  upcoming-fixture teams that have any:  {on_fixt}")

    await db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
