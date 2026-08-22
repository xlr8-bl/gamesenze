"""A baseline match model.

Bivariate-independent Poisson over expected goals, with expected goals taken
from point-in-time xG rather than actual goals: xG is the more stable estimator
over the 6-10 match windows §5.4 permits, and over those samples actual goals
are mostly noise about it.

Deliberately simple and legible. A model we can explain is one we can debug
when calibration drifts (REQ-QA-8), and §5.7 is clear that the hard part of
this problem is not model sophistication — it is not lying to yourself about
what the model saw.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..backtest.features import FeatureWindow

# League-average goals per team per match, used to convert a team's attacking
# and defensive rates into an expectation against a specific opponent.
LEAGUE_MEAN_GOALS = 1.35

# Home advantage as a multiplier on expected goals. Modest by historical
# standards because it has been shrinking, and because overstating it is the
# most common way a simple model becomes systematically miscalibrated.
HOME_ADVANTAGE = 1.10

MAX_GOALS = 8  # truncation point for the scoreline grid


@dataclass(frozen=True)
class MatchPrices:
    home: float
    draw: float
    away: float
    over_2_5: float
    under_2_5: float
    btts_yes: float
    btts_no: float
    expected_home_goals: float
    expected_away_goals: float

    def probability(self, market: str, selection: str) -> float | None:
        m, s = market.lower(), selection.lower()

        if m == "1x2":
            return {"home": self.home, "draw": self.draw, "away": self.away}.get(s)

        if m == "btts":
            return {"yes": self.btts_yes, "no": self.btts_no}.get(s)

        # Double chance: two of the three 1X2 outcomes. Its selections cover the
        # space twice over, which de-vigging has to account for downstream.
        if m == "double_chance":
            return {
                "1x": self.home + self.draw,
                "12": self.home + self.away,
                "x2": self.draw + self.away,
            }.get(s)

        # Over/under any goal line, not just 2.5. Total goals are the sum of two
        # independent Poisson scorelines, so the total is itself Poisson with
        # the combined mean — priced on demand for whatever line the book hangs.
        if m.startswith("ou_"):
            try:
                line = float(m[3:])
            except ValueError:
                return None
            if s not in ("over", "under"):
                return None
            lam = self.expected_home_goals + self.expected_away_goals
            under = sum(_poisson(k, lam) for k in range(0, math.floor(line) + 1))
            under = min(under, 1.0)
            return under if s == "under" else 1.0 - under

        return None


def _poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


class MatchModel:
    def __init__(
        self,
        *,
        league_mean: float = LEAGUE_MEAN_GOALS,
        home_advantage: float = HOME_ADVANTAGE,
    ) -> None:
        self._league_mean = league_mean
        self._home_advantage = home_advantage

    def expected_goals(
        self, home: FeatureWindow, away: FeatureWindow
    ) -> tuple[float, float]:
        """Attack strength x opponent weakness x league mean."""
        home_attack = home.xg_for / self._league_mean
        home_defence = home.xg_against / self._league_mean
        away_attack = away.xg_for / self._league_mean
        away_defence = away.xg_against / self._league_mean

        lam_home = home_attack * away_defence * self._league_mean * self._home_advantage
        lam_away = away_attack * home_defence * self._league_mean
        # Floor rather than clamp: a zero expectation makes every downstream
        # probability degenerate, and a team really averaging 0.0 xG over ten
        # matches is a data problem, not a football one.
        return max(lam_home, 0.15), max(lam_away, 0.15)

    def price(self, home: FeatureWindow, away: FeatureWindow) -> MatchPrices:
        """Price from each team's own averages — the un-adjusted baseline."""
        return self.price_from_goals(*self.expected_goals(home, away))

    def price_from_goals(self, lam_home: float, lam_away: float) -> MatchPrices:
        """Build the full market from a pair of expected-goals figures.

        Split out so an opponent-adjusted estimate (analysis/ratings.py) can be
        priced through exactly the same scoreline grid as the baseline — only
        the two lambdas differ, everything downstream is identical.
        """
        lam_home, lam_away = max(lam_home, 0.15), max(lam_away, 0.15)

        home_p = draw_p = away_p = 0.0
        over_p = btts_p = 0.0

        for h in range(MAX_GOALS + 1):
            ph = _poisson(h, lam_home)
            for a in range(MAX_GOALS + 1):
                p = ph * _poisson(a, lam_away)
                if h > a:
                    home_p += p
                elif h == a:
                    draw_p += p
                else:
                    away_p += p
                if h + a > 2:
                    over_p += p
                if h > 0 and a > 0:
                    btts_p += p

        # Truncating the grid at 8 goals loses a little mass; renormalise so
        # the 1X2 market sums to exactly 1 rather than 0.9997.
        total = home_p + draw_p + away_p
        home_p, draw_p, away_p = home_p / total, draw_p / total, away_p / total
        over_p /= total
        btts_p /= total

        return MatchPrices(
            home=home_p,
            draw=draw_p,
            away=away_p,
            over_2_5=over_p,
            under_2_5=1 - over_p,
            btts_yes=btts_p,
            btts_no=1 - btts_p,
            expected_home_goals=lam_home,
            expected_away_goals=lam_away,
        )
