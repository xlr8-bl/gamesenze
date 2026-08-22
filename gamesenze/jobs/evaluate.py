"""Back-test the Dixon-Coles model — prove it, do not assert it.

Walk-forward evaluation: step through history in date order, and for each match
predict from a model fit ONLY on matches that finished before it (refit every
couple of weeks for speed, always as-of the match date so the time-decay and
the no-lookahead rule both hold). Then score those out-of-sample predictions.

    python -m gamesenze.jobs.evaluate

Reports, over the held-out matches:
  - log loss and multiclass Brier score (lower is better),
  - accuracy of the most-likely outcome,
  - a calibration table (predicted home-win band vs actual home-win rate),
  - the same metrics for a base-rate baseline, so the model has to earn its keep.
"""

from __future__ import annotations

import asyncio
import math
from datetime import timedelta

from gamesenze.analysis.dixon_coles import fit_dixon_coles
from gamesenze.config import Settings
from gamesenze.db import AsyncpgDb

REFIT_EVERY_DAYS = 14
MIN_TRAIN_MATCHES = 200   # do not start scoring until the model has a base


def _outcome(hg: int, ag: int) -> int:
    return 0 if hg > ag else (1 if hg == ag else 2)  # home / draw / away


async def _run() -> int:
    s = Settings.from_env()
    db = await AsyncpgDb.connect(s.database_url)
    rows = await db.fetch(
        """
        select home_team_id as home_id, away_team_id as away_id, kickoff_at,
               home_goals, away_goals
          from fixtures
         where status = 'finished'
           and home_goals is not null and away_goals is not null
           and home_team_id is not null and away_team_id is not null
         order by kickoff_at
        """
    )
    await db.close()
    matches = [
        {"home_id": str(r["home_id"]), "away_id": str(r["away_id"]),
         "home_goals": int(r["home_goals"]), "away_goals": int(r["away_goals"]),
         "kickoff_at": r["kickoff_at"]}
        for r in rows
    ]
    if len(matches) < MIN_TRAIN_MATCHES + 50:
        print(f"only {len(matches)} finished matches — need more history to back-test.")
        return 0

    # Base rates from the first training block, for the baseline model.
    train0 = matches[:MIN_TRAIN_MATCHES]
    base = [0, 0, 0]
    for m in train0:
        base[_outcome(m["home_goals"], m["away_goals"])] += 1
    base_p = [c / len(train0) for c in base]

    model = None
    next_refit = None
    n = m_ll = m_brier = m_hit = 0
    b_ll = b_brier = 0.0
    bins = {i: [0, 0] for i in range(10)}  # predicted-home-band -> [n, home_wins]

    for i, mt in enumerate(matches):
        if i < MIN_TRAIN_MATCHES:
            continue
        date = mt["kickoff_at"]
        if model is None or date >= next_refit:
            history = matches[:i]  # strictly before this match — no lookahead
            model = fit_dixon_coles(history, as_of=date)
            next_refit = date + timedelta(days=REFIT_EVERY_DAYS)

        probs = model.outcome_probabilities(mt["home_id"], mt["away_id"])
        if probs is None:
            continue  # a side not yet rated; not scoreable
        o = _outcome(mt["home_goals"], mt["away_goals"])
        p = [max(min(v, 1 - 1e-9), 1e-9) for v in probs]

        m_ll += -math.log(p[o])
        m_brier += sum((p[c] - (1 if c == o else 0)) ** 2 for c in range(3))
        m_hit += 1 if max(range(3), key=lambda c: p[c]) == o else 0
        b_ll += -math.log(base_p[o] if base_p[o] > 0 else 1e-9)
        b_brier += sum((base_p[c] - (1 if c == o else 0)) ** 2 for c in range(3))
        band = min(int(p[0] * 10), 9)
        bins[band][0] += 1
        bins[band][1] += 1 if o == 0 else 0
        n += 1

    if n == 0:
        print("no scoreable held-out matches.")
        return 0

    print(f"Back-test over {n} held-out matches (walk-forward, refit every "
          f"{REFIT_EVERY_DAYS} days)\n")
    print(f"{'metric':<16}{'Dixon-Coles':>14}{'base rate':>14}")
    print(f"{'log loss':<16}{m_ll / n:>14.4f}{b_ll / n:>14.4f}   (lower better)")
    print(f"{'Brier score':<16}{m_brier / n:>14.4f}{b_brier / n:>14.4f}   (lower better)")
    print(f"{'accuracy':<16}{m_hit / n:>14.1%}{max(base_p):>14.1%}")
    print()
    print("Calibration — when we say home win X%, how often did home win?")
    print(f"  {'predicted':<12}{'matches':>9}{'actual home-win':>18}")
    for b in range(10):
        cnt, wins = bins[b]
        if cnt:
            print(f"  {b*10:>3}-{b*10+10:<7}{cnt:>9}{wins / cnt:>17.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
