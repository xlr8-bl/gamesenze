"""Opponent-adjusted attack/defence ratings, fitted from real matches.

The baseline model (analysis/model.py) multiplies a team's raw average xG by a
hardcoded home advantage and league mean. That does no opponent adjustment: xG
run up against weak defences counts the same as xG against elite ones, so a
flat-track bully and a genuine contender look identical.

This module fits, from the actual match record, each team's attacking and
defensive strength *relative to the opponents they faced*, and estimates the
home-field effect and scoring baseline from the data rather than assuming them.
It is the standard iterative-scaling fit behind a Dixon-Coles-style Poisson
model, with two honesty adjustments:

  * Recent matches count more (an exponential half-life on age), because form
    now matters more than form six months ago.
  * A team's rating is shrunk toward league-average in proportion to how little
    evidence stands behind it, so a hot three-game start does not masquerade as
    an established level.

The fitted ratings feed the same Poisson scoreline grid the baseline used, so
everything downstream (1X2, over/under, BTTS, the read) is unchanged — only the
expected-goals estimate that drives them is now genuinely opponent-adjusted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

# Weight halves every this-many days: a match ~six months old counts about half
# a recent one. Long enough to carry last season's signal, short enough that
# current form leads.
DEFAULT_HALF_LIFE_DAYS = 180.0

# Shrinkage prior, in units of match-weight. A team with this much effective
# evidence is pulled halfway to league-average; more evidence, less pull.
SHRINKAGE_STRENGTH = 4.0

# Ratings are multiplicative and centre on 1.0; clamp keeps a thin-sample team
# from taking an absurd value before shrinkage reins it in.
_MIN_RATING, _MAX_RATING = 0.25, 4.0


@dataclass(frozen=True)
class Ratings:
    attack: dict[str, float]
    defence: dict[str, float]
    home_mean: float   # league mean home-side xG (carries the home edge)
    away_mean: float   # league mean away-side xG
    weight: dict[str, float]  # total match-weight behind each team

    def rated(self, team_id: str) -> bool:
        return team_id in self.attack

    def expected_goals(self, home_id: str, away_id: str) -> tuple[float, float] | None:
        """Opponent-adjusted expected goals for a fixture, or None if unrated."""
        if home_id not in self.attack or away_id not in self.attack:
            return None
        lam_home = self.attack[home_id] * self.defence[away_id] * self.home_mean
        lam_away = self.attack[away_id] * self.defence[home_id] * self.away_mean
        return max(lam_home, 0.15), max(lam_away, 0.15)

    @property
    def home_advantage(self) -> float:
        """How much more the home side scores, as a ratio — estimated, not assumed."""
        return self.home_mean / self.away_mean if self.away_mean else 1.0


def _decay_weight(kickoff: datetime, as_of: datetime, half_life_days: float) -> float:
    age_days = max((as_of - kickoff).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / half_life_days)


def fit_ratings(
    matches: Sequence[Mapping[str, object]],
    *,
    as_of: datetime,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    iterations: int = 60,
    shrinkage: float = SHRINKAGE_STRENGTH,
) -> Ratings:
    """Fit attack/defence ratings by weighted iterative scaling.

    `matches` are finished games, each a mapping with `home_id`, `away_id`,
    `home_xg`, `away_xg`, `kickoff_at`. Teams are rated relative to each other;
    the fit centres attack and defence on 1.0 and folds the overall level into
    the home/away means.
    """
    teams: set[str] = set()
    rows = []
    for m in matches:
        h, a = str(m["home_id"]), str(m["away_id"])
        hx, ax = float(m["home_xg"]), float(m["away_xg"])
        w = _decay_weight(m["kickoff_at"], as_of, half_life_days)  # type: ignore[arg-type]
        if w <= 0:
            continue
        teams.add(h)
        teams.add(a)
        rows.append((h, a, hx, ax, w))

    if not rows:
        return Ratings({}, {}, 1.35, 1.15, {})

    total_w = sum(w for *_, w in rows)
    home_mean = sum(hx * w for _, _, hx, _, w in rows) / total_w
    away_mean = sum(ax * w for _, _, _, ax, w in rows) / total_w
    home_mean = max(home_mean, 0.2)
    away_mean = max(away_mean, 0.2)

    attack = {t: 1.0 for t in teams}
    defence = {t: 1.0 for t in teams}
    team_weight: dict[str, float] = {t: 0.0 for t in teams}
    for h, a, _, _, w in rows:
        team_weight[h] += w
        team_weight[a] += w

    for _ in range(iterations):
        # Attack update: goals a team creates, over the defensive quality faced.
        att_num = {t: 0.0 for t in teams}
        att_den = {t: 0.0 for t in teams}
        def_num = {t: 0.0 for t in teams}
        def_den = {t: 0.0 for t in teams}
        for h, a, hx, ax, w in rows:
            att_num[h] += w * hx
            att_den[h] += w * defence[a] * home_mean
            att_num[a] += w * ax
            att_den[a] += w * defence[h] * away_mean
            def_num[a] += w * hx  # goals a conceded (as away side)
            def_den[a] += w * attack[h] * home_mean
            def_num[h] += w * ax  # goals h conceded (as home side)
            def_den[h] += w * attack[a] * away_mean

        for t in teams:
            if att_den[t] > 0:
                attack[t] = min(max(att_num[t] / att_den[t], _MIN_RATING), _MAX_RATING)
            if def_den[t] > 0:
                defence[t] = min(max(def_num[t] / def_den[t], _MIN_RATING), _MAX_RATING)

        # Re-centre on weighted mean 1.0 so the level lives only in the means.
        a_mean = sum(attack[t] * team_weight[t] for t in teams) / total_w / 2
        d_mean = sum(defence[t] * team_weight[t] for t in teams) / total_w / 2
        if a_mean > 0:
            attack = {t: attack[t] / a_mean for t in teams}
        if d_mean > 0:
            defence = {t: defence[t] / d_mean for t in teams}

        # Re-estimate the home/away scoring level from the current ratings.
        exp_home = sum(w * attack[h] * defence[a] for h, a, _, _, w in rows)
        exp_away = sum(w * attack[a] * defence[h] for h, a, _, _, w in rows)
        if exp_home > 0:
            home_mean = max(sum(hx * w for _, _, hx, _, w in rows) / exp_home, 0.2)
        if exp_away > 0:
            away_mean = max(sum(ax * w for _, _, _, ax, w in rows) / exp_away, 0.2)

    # Shrink each rating toward 1.0 by how little evidence stands behind it.
    for t in teams:
        k = shrinkage
        wt = team_weight[t]
        attack[t] = (wt * attack[t] + k * 1.0) / (wt + k)
        defence[t] = (wt * defence[t] + k * 1.0) / (wt + k)

    return Ratings(attack, defence, home_mean, away_mean, team_weight)
