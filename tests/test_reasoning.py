"""The read a subscriber sees must be football, long enough, and method-free."""

from __future__ import annotations

from datetime import datetime, timezone

from gamesenze.analysis.reasoning import confidence_from, write_reasoning
from gamesenze.backtest.features import FeatureWindow
from gamesenze.qa.gate import MIN_REASONING_CHARS


def _fw(xgf: float, xga: float, ppg: float) -> FeatureWindow:
    now = datetime.now(timezone.utc)
    return FeatureWindow(
        team_id="t", as_of=now, matches_used=10, xg_for=xgf, xg_against=xga,
        goals_for=1.4, goals_against=1.2, xg_sd=0.3, points_per_game=ppg,
        latest_match_at=now,
    )


def test_reasoning_clears_the_gate_length_and_hides_the_method():
    text = write_reasoning(
        home_name="Torino", away_name="AC Milan",
        home=_fw(1.64, 1.52, 1.5), away=_fw(1.24, 1.55, 1.0),
        market="1x2", selection="home", excluded_labels=["Head-to-head"],
    )
    assert len(text) > MIN_REASONING_CHARS
    lowered = text.lower()
    for banned in ("xg", "poisson", "probability", "%", "expected goals", "lambda"):
        assert banned not in lowered
    # Verdict lead names the backed side and stands as its own sentence.
    assert text.split(".")[0].strip() == "We're with Torino here"


def test_each_market_gets_a_verdict_lead():
    home, away = _fw(1.6, 1.2, 1.7), _fw(1.5, 1.4, 1.3)
    for market, selection in [
        ("1x2", "away"), ("1x2", "draw"), ("ou_2.5", "over"),
        ("ou_2.5", "under"), ("btts", "yes"), ("btts", "no"),
    ]:
        text = write_reasoning(
            home_name="A", away_name="B", home=home, away=away,
            market=market, selection=selection,
        )
        assert len(text) > MIN_REASONING_CHARS
        assert text[0].isupper() and text.rstrip().endswith(".")


def test_confidence_tiers():
    assert confidence_from(0.12, 0.55) == "best_bet"
    assert confidence_from(0.08, 0.40) == "strong_lean"
    assert confidence_from(0.04, 0.35) == "lean"
    # A big edge on a low probability is not a best bet.
    assert confidence_from(0.12, 0.30) == "strong_lean"


def test_reasoning_uses_finishing_pressing_and_the_model_outlook():
    from gamesenze.analysis.model import MatchModel

    home = FeatureWindow(
        team_id="h", as_of=datetime.now(timezone.utc), matches_used=10,
        xg_for=1.7, xg_against=1.2, goals_for=2.2, goals_against=1.0,
        xg_sd=0.3, points_per_game=1.7, latest_match_at=datetime.now(timezone.utc),
        ppda=8.0,  # high press
    )
    away = FeatureWindow(
        team_id="a", as_of=datetime.now(timezone.utc), matches_used=10,
        xg_for=1.4, xg_against=1.6, goals_for=0.9, goals_against=1.7,
        xg_sd=0.3, points_per_game=1.0, latest_match_at=datetime.now(timezone.utc),
        ppda=15.0,  # sits off
    )
    prices = MatchModel().price(home, away)
    text = write_reasoning(
        home_name="Home", away_name="Away", home=home, away=away,
        market="1x2", selection="home", prices=prices,
    )
    low = text.lower()
    assert "clinical" in low          # home over-performing xG
    assert "wasteful" in low          # away under-performing xG
    assert "press high" in low        # home PPDA
    assert "sit off" in low           # away PPDA
    assert "wider read" in low        # model outlook (BTTS + goals)
    # Still no method terms leaked in the richer text.
    for banned in ("xg", "ppda", "poisson", "probability", "%"):
        assert banned not in low


def test_pressing_is_silent_when_ppda_is_absent():
    home = FeatureWindow(
        team_id="h", as_of=datetime.now(timezone.utc), matches_used=10,
        xg_for=1.5, xg_against=1.3, goals_for=1.5, goals_against=1.3,
        xg_sd=0.3, points_per_game=1.4, latest_match_at=datetime.now(timezone.utc),
        ppda=None,
    )
    text = write_reasoning(
        home_name="Home", away_name="Away", home=home, away=home,
        market="1x2", selection="home",
    )
    assert "press" not in text.lower()
