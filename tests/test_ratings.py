"""The ratings fit must actually adjust for opponent strength."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gamesenze.analysis.ratings import fit_ratings

NOW = datetime(2026, 8, 22, tzinfo=timezone.utc)


def _d(days: int) -> datetime:
    return NOW - timedelta(days=days)


def _league_with_two_scorers():
    """Two teams score the same, against a strong vs a weak defence."""
    m = []
    for i in range(6):
        m.append({"home_id": "Elite", "away_id": "Filler",
                  "home_xg": 1.5, "away_xg": 0.4, "kickoff_at": _d(20 + i)})
        m.append({"home_id": "Filler", "away_id": "Minnow",
                  "home_xg": 2.4, "away_xg": 1.0, "kickoff_at": _d(20 + i)})
    for i in range(6):
        m.append({"home_id": "A", "away_id": "Elite",
                  "home_xg": 2.0, "away_xg": 1.0, "kickoff_at": _d(5 + i)})
        m.append({"home_id": "B", "away_id": "Minnow",
                  "home_xg": 2.0, "away_xg": 1.0, "kickoff_at": _d(5 + i)})
    return m


def test_scoring_against_a_stronger_defence_earns_a_higher_attack_rating():
    r = fit_ratings(_league_with_two_scorers(), as_of=NOW)
    assert r.attack["A"] > r.attack["B"]           # same goals, tougher opponents
    assert r.defence["Elite"] < r.defence["Minnow"]  # elite concedes less


def test_ratings_centre_on_about_one():
    r = fit_ratings(_league_with_two_scorers(), as_of=NOW)
    vals = list(r.attack.values())
    assert 0.7 < sum(vals) / len(vals) < 1.4  # centred near average


def test_recent_matches_outweigh_old_ones():
    # A team awful long ago but excellent lately should rate above average.
    m = []
    for i in range(8):
        m.append({"home_id": "Rise", "away_id": "Mid",
                  "home_xg": 0.5, "away_xg": 1.8, "kickoff_at": _d(300 + i)})
        m.append({"home_id": "Mid", "away_id": "Other",
                  "home_xg": 1.3, "away_xg": 1.3, "kickoff_at": _d(150 + i)})
    for i in range(8):
        m.append({"home_id": "Rise", "away_id": "Mid",
                  "home_xg": 2.6, "away_xg": 0.6, "kickoff_at": _d(3 + i)})
    r = fit_ratings(m, as_of=NOW, half_life_days=90)
    # Recent excellence should have pulled Rise's attack above its ancient slump.
    assert r.attack["Rise"] > 1.0


def test_shrinkage_pulls_thin_samples_toward_average():
    # A one-game wonder should not get an extreme rating.
    strong_history = []
    for i in range(20):
        strong_history.append({"home_id": "Reg", "away_id": "Foe",
                               "home_xg": 1.4, "away_xg": 1.3, "kickoff_at": _d(10 + i)})
    one_game = [{"home_id": "Flash", "away_id": "Foe",
                 "home_xg": 5.0, "away_xg": 0.2, "kickoff_at": _d(2)}]
    r = fit_ratings(strong_history + one_game, as_of=NOW)
    # Flash blitzed one game; shrinkage keeps its attack well below the raw ratio.
    assert r.attack["Flash"] < 2.0


def test_unrated_teams_return_no_prediction():
    r = fit_ratings(_league_with_two_scorers(), as_of=NOW)
    assert r.expected_goals("A", "B") is not None
    assert r.expected_goals("A", "NeverSeen") is None


def test_empty_history_is_safe():
    r = fit_ratings([], as_of=NOW)
    assert r.expected_goals("x", "y") is None
