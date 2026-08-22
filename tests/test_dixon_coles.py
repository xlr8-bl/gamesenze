"""Dixon-Coles must recover known strengths and price coherently."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np

from gamesenze.analysis.dixon_coles import fit_dixon_coles

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def _simulate(seed: int = 0, seasons: int = 3):
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(8)]
    att = dict(zip(teams, [0.6, 0.4, 0.2, 0.05, -0.05, -0.2, -0.4, -0.6]))
    dfc = dict(zip(teams, [0.5, 0.3, 0.1, 0.0, -0.05, -0.2, -0.35, -0.5]))
    home = 0.30
    matches = []
    for s in range(seasons):
        for i in teams:
            for j in teams:
                if i == j:
                    continue
                lam = math.exp(att[i] - dfc[j] + home)
                mu = math.exp(att[j] - dfc[i])
                matches.append({
                    "home_id": i, "away_id": j,
                    "home_goals": int(rng.poisson(lam)),
                    "away_goals": int(rng.poisson(mu)),
                    "kickoff_at": NOW - timedelta(days=10 + s * 120),
                })
    return teams, matches


def test_recovers_the_true_strength_ordering():
    teams, matches = _simulate(seed=42)
    m = fit_dixon_coles(matches, as_of=NOW, half_life_days=365)
    ordering = [t for t, _ in sorted(m.attack.items(), key=lambda kv: -kv[1])]
    assert ordering == teams  # strongest attack first, exactly as simulated


def test_estimates_a_positive_home_effect():
    _, matches = _simulate(seed=7)
    m = fit_dixon_coles(matches, as_of=NOW, half_life_days=365)
    assert 0.15 < m.home < 0.45  # true value was 0.30, estimated from data


def test_outcome_probabilities_are_a_distribution_and_favour_the_stronger_side():
    _, matches = _simulate(seed=1)
    m = fit_dixon_coles(matches, as_of=NOW, half_life_days=365)
    h, d, a = m.outcome_probabilities("T0", "T7")  # best at home vs worst
    assert abs(h + d + a - 1.0) < 1e-6
    assert h > 0.7 and h > a
    # Reverse the venue: the strong side, now away, should still be favoured.
    h2, d2, a2 = m.outcome_probabilities("T7", "T0")
    assert a2 > h2


def test_unrated_and_empty_are_safe():
    _, matches = _simulate(seed=2)
    m = fit_dixon_coles(matches, as_of=NOW, half_life_days=365)
    assert m.outcome_probabilities("T0", "NeverSeen") is None
    empty = fit_dixon_coles([], as_of=NOW)
    assert empty.outcome_probabilities("x", "y") is None
    assert not empty.rated("x")


def test_thin_teams_are_dropped_from_the_fit():
    _, matches = _simulate(seed=3)
    matches.append({"home_id": "OneOff", "away_id": "T0", "home_goals": 5,
                    "away_goals": 0, "kickoff_at": NOW - timedelta(days=2)})
    m = fit_dixon_coles(matches, as_of=NOW, min_matches=4)
    assert not m.rated("OneOff")  # a single appearance is not enough to rate
