"""providers/odds_api.py — parsing and the real vendor shape.

The exact fixture used for PAYLOAD mirrors what a live call to
GET /v4/sports/soccer_epl/odds/?...&markets=h2h actually returned during
development (one bookmaker, trimmed to the fields parse_odds reads), not a
guess at the shape — see gamesenze/providers/odds_api.py's module docstring
for why that mattered here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from gamesenze.providers.odds_api import LEAGUE_KEYS, parse_odds

CAPTURED_AT = datetime(2026, 8, 19, 14, 49, tzinfo=UTC)

GAME = {
    "id": "eb2553d10d63dc912b99f8fd0d675721",
    "sport_key": "soccer_epl",
    "commence_time": "2026-08-21T19:00:00Z",
    "home_team": "Arsenal",
    "away_team": "Coventry City",
    "bookmakers": [
        {
            "key": "betfair_sb_uk",
            "title": "Betfair Sportsbook",
            "last_update": "2026-08-19T14:48:18Z",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Arsenal", "price": 1.17},
                        {"name": "Coventry City", "price": 17.0},
                        {"name": "Draw", "price": 7.5},
                    ],
                }
            ],
        }
    ],
}


def test_the_five_target_leagues_have_a_real_sport_key():
    for league in (
        "Premier League",
        "La Liga",
        "Serie A",
        "Bundesliga",
        "Ligue 1",
    ):
        assert league in LEAGUE_KEYS


def test_parses_every_outcome_from_the_real_response_shape():
    rows, rejections = parse_odds(GAME, captured_at=CAPTURED_AT, window_label="daily")

    assert rejections == []
    assert len(rows) == 3
    by_selection = {r["selection"]: r for r in rows}
    assert by_selection["Arsenal"]["decimal_odds"] == 1.17
    assert by_selection["Coventry City"]["decimal_odds"] == 17.0
    assert by_selection["Draw"]["decimal_odds"] == 7.5
    assert all(r["bookmaker"] == "betfair_sb_uk" for r in rows)
    assert all(r["market"] == "h2h" for r in rows)
    assert all(r["captured_at"] == CAPTURED_AT for r in rows)
    assert all(r["is_closing"] is False for r in rows)


def test_a_lock_window_is_recorded_as_the_closing_line():
    rows, _ = parse_odds(GAME, captured_at=CAPTURED_AT, window_label="lock")
    assert all(r["is_closing"] for r in rows)


def test_an_impossible_price_is_rejected_not_stored():
    game = {
        **GAME,
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "home", "price": 1.001},
                            {"name": "away", "price": 500},
                            {"name": "draw", "price": 3.4},
                        ],
                    }
                ],
            }
        ],
    }
    rows, rejections = parse_odds(game, captured_at=CAPTURED_AT, window_label="daily")
    assert len(rows) == 1
    assert len(rejections) == 2


def test_a_missing_price_is_rejected_not_crashed_on():
    game = {
        **GAME,
        "bookmakers": [
            {
                "key": "pinnacle",
                "markets": [
                    {"key": "h2h", "outcomes": [{"name": "home", "price": None}]}
                ],
            }
        ],
    }
    rows, rejections = parse_odds(game, captured_at=CAPTURED_AT, window_label="daily")
    assert rows == []
    assert len(rejections) == 1


def test_no_bookmakers_is_an_empty_result_not_an_error():
    rows, rejections = parse_odds(
        {**GAME, "bookmakers": []}, captured_at=CAPTURED_AT, window_label="daily"
    )
    assert rows == []
    assert rejections == []
