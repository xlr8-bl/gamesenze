"""The pick selector must refuse the longshots a raw edge maximiser loves."""

from __future__ import annotations

from gamesenze.analysis.model import MatchPrices
from gamesenze.analysis.selection import (
    MAX_EDGE,
    MIN_SELECTION_PROB,
    select_pick,
)


def _prices(home: float, draw: float, away: float) -> MatchPrices:
    return MatchPrices(
        home=home,
        draw=draw,
        away=away,
        over_2_5=0.5,
        under_2_5=0.5,
        btts_yes=0.5,
        btts_no=0.5,
        expected_home_goals=1.4,
        expected_away_goals=1.2,
    )


def _h2h(book: str, home_odds: float, draw_odds: float, away_odds: float) -> list[dict]:
    return [
        {"bookmaker": book, "market": "1x2", "selection": "home", "decimal_odds": home_odds},
        {"bookmaker": book, "market": "1x2", "selection": "draw", "decimal_odds": draw_odds},
        {"bookmaker": book, "market": "1x2", "selection": "away", "decimal_odds": away_odds},
    ]


def test_the_elche_case_is_not_drafted():
    # Model rates the home longshot at 24% where the market has it near 10%.
    # A raw prob*odds-1 sees +140%; the selector must throw it out because the
    # blended probability sits below the floor.
    prices = _prices(home=0.24, draw=0.23, away=0.53)
    rows = _h2h("pinnacle", home_odds=10.0, draw_odds=6.5, away_odds=1.35)
    assert select_pick(prices, rows) is None


def test_a_modest_favourite_edge_is_drafted():
    # Model 55% home; market fair ~50% at 1.90. Blended ~52.5%, edge ~ +0.5?..
    # priced so the blended edge lands inside the band.
    prices = _prices(home=0.60, draw=0.24, away=0.16)
    rows = _h2h("bet365", home_odds=2.00, draw_odds=3.6, away_odds=4.5)
    choice = select_pick(prices, rows)
    assert choice is not None
    assert choice.selection == "home"
    assert choice.market == "1x2"
    assert MIN_SELECTION_PROB <= choice.published_prob
    assert choice.edge <= MAX_EDGE


def test_an_implausible_edge_is_capped_out():
    # A near-even selection the model rates far above the market: blended edge
    # exceeds the ceiling, so it is a model error, not a bet.
    prices = _prices(home=0.95, draw=0.03, away=0.02)
    rows = _h2h("book", home_odds=2.20, draw_odds=3.4, away_odds=3.2)
    assert select_pick(prices, rows) is None


def test_a_one_sided_market_cannot_be_devigged_and_is_skipped():
    prices = _prices(home=0.6, draw=0.24, away=0.16)
    rows = [
        {"bookmaker": "b", "market": "1x2", "selection": "home", "decimal_odds": 2.0},
    ]
    assert select_pick(prices, rows) is None


def test_the_best_edge_wins_when_several_qualify():
    prices = _prices(home=0.55, draw=0.27, away=0.18)
    rows = _h2h("a", home_odds=2.10, draw_odds=3.3, away_odds=4.6)
    choice = select_pick(prices, rows)
    assert choice is not None
    # Home and draw may both clear; the selector returns the larger edge.
    all_edges = []
    from gamesenze.analysis.selection import MODEL_WEIGHT
    from gamesenze.odds.math import devig

    fair = devig([2.10, 3.3, 4.6])
    for sel, mp, odds, fp in [
        ("home", 0.55, 2.10, fair[0]),
        ("draw", 0.27, 3.30, fair[1]),
        ("away", 0.18, 4.60, fair[2]),
    ]:
        pub = MODEL_WEIGHT * mp + (1 - MODEL_WEIGHT) * fp
        all_edges.append(pub * odds - 1)
    assert choice.edge == max(e for e in all_edges if e <= MAX_EDGE)
