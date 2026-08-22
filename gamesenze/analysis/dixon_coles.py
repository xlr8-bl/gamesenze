"""Dixon-Coles: the standard football model, fit by maximum likelihood.

This is the real thing — the model from Dixon & Coles (1997) that sits under
most professional football pricing. It is not hand-tuned formulas: every
parameter is *estimated from the match record* by maximising a likelihood.

For each team it fits an attack strength and a defence strength; globally it
fits a home-field effect and a low-score dependence term (rho) that corrects
the independence assumption where it is worst — the 0-0, 1-0, 0-1 and 1-1
scores. Expected goals for a fixture are

    lambda_home = exp(attack_home - defence_away + home)
    lambda_away = exp(attack_away - defence_home)

and the joint scoreline probability is the Dixon-Coles-corrected product of two
Poissons. Recent matches are weighted more via an exponential time decay, the
same device the original paper uses to track form.

Fitting is a numerical optimisation (L-BFGS-B) over all team parameters at
once. The output is a model that can price any fixture between rated teams and,
crucially, be *back-tested* — see jobs/evaluate.py, which scores its
calibration on held-out matches rather than asserting it is good.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

# Time-decay: a match this many days old carries half the weight of today's.
# 180 days keeps last season's signal alive while letting current form lead.
DEFAULT_HALF_LIFE_DAYS = 180.0

MAX_GOALS = 10  # scoreline grid truncation for pricing


@dataclass(frozen=True)
class DixonColesModel:
    attack: dict[str, float]
    defence: dict[str, float]
    home: float
    rho: float
    log_likelihood: float
    n_matches: int

    def rated(self, team_id: str) -> bool:
        return team_id in self.attack

    def expected_goals(self, home_id: str, away_id: str) -> tuple[float, float] | None:
        if home_id not in self.attack or away_id not in self.attack:
            return None
        lam = math.exp(self.attack[home_id] - self.defence[away_id] + self.home)
        mu = math.exp(self.attack[away_id] - self.defence[home_id])
        return lam, mu

    def scoreline_matrix(self, home_id: str, away_id: str) -> np.ndarray | None:
        """The full Dixon-Coles-corrected P(home_goals, away_goals) grid."""
        eg = self.expected_goals(home_id, away_id)
        if eg is None:
            return None
        lam, mu = eg
        ks = np.arange(MAX_GOALS + 1)
        pois_h = np.exp(ks * math.log(lam) - lam - gammaln(ks + 1))
        pois_a = np.exp(ks * math.log(mu) - mu - gammaln(ks + 1))
        grid = np.outer(pois_h, pois_a)
        # Low-score dependence correction (tau), applied to the four cells.
        grid[0, 0] *= 1 - lam * mu * self.rho
        grid[0, 1] *= 1 + lam * self.rho
        grid[1, 0] *= 1 + mu * self.rho
        grid[1, 1] *= 1 - self.rho
        grid = np.clip(grid, 0.0, None)
        return grid / grid.sum()

    def outcome_probabilities(self, home_id: str, away_id: str):
        """(P(home), P(draw), P(away)) from the corrected scoreline grid."""
        grid = self.scoreline_matrix(home_id, away_id)
        if grid is None:
            return None
        home_p = float(np.tril(grid, -1).sum())
        draw_p = float(np.trace(grid))
        away_p = float(np.triu(grid, 1).sum())
        return home_p, draw_p, away_p

    def match_prices(self, home_id: str, away_id: str):
        """A MatchPrices built from the Dixon-Coles-corrected scoreline grid.

        This is the interface the pick selector and the read consume, so the
        real model drops straight into the existing pipeline. 1X2, totals and
        BTTS all come off the same corrected grid.
        """
        from .model import MatchPrices

        grid = self.scoreline_matrix(home_id, away_id)
        if grid is None:
            return None
        lam, mu = self.expected_goals(home_id, away_id)  # type: ignore[misc]
        totals = np.add.outer(np.arange(grid.shape[0]), np.arange(grid.shape[1]))
        over = float(grid[totals > 2].sum())
        btts = float(grid[1:, 1:].sum())
        return MatchPrices(
            home=float(np.tril(grid, -1).sum()),
            draw=float(np.trace(grid)),
            away=float(np.triu(grid, 1).sum()),
            over_2_5=over,
            under_2_5=1 - over,
            btts_yes=btts,
            btts_no=1 - btts,
            expected_home_goals=lam,
            expected_away_goals=mu,
        )


def _decay_weights(kickoffs: np.ndarray, as_of: datetime, half_life_days: float) -> np.ndarray:
    ages = np.array([(as_of - k).total_seconds() / 86400.0 for k in kickoffs])
    ages = np.clip(ages, 0.0, None)
    return 0.5 ** (ages / half_life_days)


def fit_dixon_coles(
    matches: Sequence[Mapping[str, object]],
    *,
    as_of: datetime,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    min_matches: int = 4,
) -> DixonColesModel:
    """Maximum-likelihood fit over every team at once.

    `matches` are finished games with `home_id`, `away_id`, `home_goals`,
    `away_goals`, `kickoff_at`. Teams with fewer than `min_matches` appearances
    are dropped from the fit (too little to estimate) rather than fit to noise.
    """
    # Count appearances, keep teams with enough evidence.
    appear: dict[str, int] = {}
    for m in matches:
        appear[str(m["home_id"])] = appear.get(str(m["home_id"]), 0) + 1
        appear[str(m["away_id"])] = appear.get(str(m["away_id"]), 0) + 1
    kept = {t for t, n in appear.items() if n >= min_matches}

    rows = [m for m in matches
            if str(m["home_id"]) in kept and str(m["away_id"]) in kept]
    if not rows or len(kept) < 2:
        return DixonColesModel({}, {}, 0.25, 0.0, 0.0, 0)

    teams = sorted(kept)
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    h = np.array([idx[str(m["home_id"])] for m in rows])
    a = np.array([idx[str(m["away_id"])] for m in rows])
    x = np.array([int(m["home_goals"]) for m in rows], dtype=float)
    y = np.array([int(m["away_goals"]) for m in rows], dtype=float)
    w = _decay_weights([m["kickoff_at"] for m in rows], as_of, half_life_days)  # type: ignore[arg-type]
    lgx, lgy = gammaln(x + 1), gammaln(y + 1)

    # Parameters: attack[1..n-1] (attack[0] fixed by sum-to-zero), defence[0..n-1],
    # home, rho. Sum-to-zero on attack removes the joint attack/defence ridge.
    def unpack(p):
        att = np.empty(n)
        att[1:] = p[: n - 1]
        att[0] = -att[1:].sum()
        dfc = p[n - 1 : 2 * n - 1]
        return att, dfc, p[2 * n - 1], p[2 * n]

    def neg_loglik(p):
        att, dfc, home, rho = unpack(p)
        loglam = att[h] - dfc[a] + home
        logmu = att[a] - dfc[h]
        lam, mu = np.exp(loglam), np.exp(logmu)
        ll = x * loglam - lam - lgx + y * logmu - mu - lgy
        # tau correction on the four low-score cells.
        tau = np.ones_like(ll)
        m00 = (x == 0) & (y == 0)
        m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0)
        m11 = (x == 1) & (y == 1)
        tau[m00] = 1 - lam[m00] * mu[m00] * rho
        tau[m01] = 1 + lam[m01] * rho
        tau[m10] = 1 + mu[m10] * rho
        tau[m11] = 1 - rho
        tau = np.clip(tau, 1e-9, None)
        ll = ll + np.log(tau)
        return -np.sum(w * ll)

    p0 = np.concatenate([np.zeros(n - 1), np.zeros(n), [0.25], [0.0]])
    bounds = [(-3, 3)] * (n - 1) + [(-3, 3)] * n + [(-1, 1), (-0.2, 0.2)]
    res = minimize(neg_loglik, p0, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 400})

    att, dfc, home, rho = unpack(res.x)
    return DixonColesModel(
        attack={t: float(att[idx[t]]) for t in teams},
        defence={t: float(dfc[idx[t]]) for t in teams},
        home=float(home),
        rho=float(rho),
        log_likelihood=float(-res.fun),
        n_matches=len(rows),
    )
