"""The direct-HTTP Understat parser.

Understat cannot be fetched from CI (and its data blocks are stripped by some
proxies), so the network is not exercised here; the parser is, against a page
built to Understat's real shape — JavaScript \\x-escaped UTF-8 literals, an
accented club name, a mix of finished and upcoming fixtures, and PPDA that
lives only in teamsData and has to be joined on by team and date.
"""

from __future__ import annotations

import json

from gamesenze.scrape.understat_http import parse_page, _season_year


def _js_escape(obj) -> str:
    # Reproduce how Understat embeds JSON: a JSON string, then every byte
    # written as a \\xNN escape, exactly what JSON.parse('...') receives.
    text = json.dumps(obj, ensure_ascii=False)
    return "".join(f"\\x{b:02x}" for b in text.encode("utf-8"))


def _page(dates, teams) -> str:
    return (
        "<html><body>"
        f"<script>var datesData = JSON.parse('{_js_escape(dates)}');</script>"
        f"<script>var teamsData = JSON.parse('{_js_escape(teams)}');</script>"
        "</body></html>"
    )


def test_parse_page_flattens_finished_matches_with_joined_ppda():
    dates = [
        {
            "id": "26618",
            "isResult": True,
            "h": {"id": "89", "title": "Atlético Madrid"},
            "a": {"id": "80", "title": "Villarreal"},
            "goals": {"h": "2", "a": "1"},
            "xG": {"h": "1.85", "a": "0.90"},
            "datetime": "2024-08-17 14:00:00",
        },
        {
            "id": "26999",
            "isResult": False,  # upcoming — must be skipped
            "h": {"id": "80", "title": "Villarreal"},
            "a": {"id": "89", "title": "Atlético Madrid"},
            "goals": {"h": None, "a": None},
            "xG": {"h": None, "a": None},
            "datetime": "2025-05-01 19:00:00",
        },
    ]
    teams = {
        "89": {
            "id": "89",
            "title": "Atlético Madrid",
            "history": [
                {"h_a": "h", "date": "2024-08-17 14:00:00", "ppda": {"att": 240, "def": 20}},
            ],
        },
        "80": {
            "id": "80",
            "title": "Villarreal",
            "history": [
                {"h_a": "a", "date": "2024-08-17 14:00:00", "ppda": {"att": 300, "def": 25}},
            ],
        },
    }

    rows = parse_page(_page(dates, teams), "ESP-La Liga")

    assert len(rows) == 1  # the upcoming fixture is dropped
    r = rows[0]
    assert r["league"] == "ESP-La Liga"
    assert r["home_team"] == "Atlético Madrid"  # accents survive the decode
    assert r["away_team"] == "Villarreal"
    assert r["home_goals"] == 2 and r["away_goals"] == 1
    assert r["home_xg"] == 1.85 and r["away_xg"] == 0.90
    # PPDA = att / def, joined from teamsData by team + date.
    assert r["home_ppda"] == 240 / 20
    assert r["away_ppda"] == 300 / 25
    assert r["game_id"] == "26618"


def test_parse_page_survives_a_missing_ppda_entry():
    dates = [
        {
            "id": "1",
            "isResult": True,
            "h": {"id": "1", "title": "Home FC"},
            "a": {"id": "2", "title": "Away FC"},
            "goals": {"h": "0", "a": "0"},
            "xG": {"h": "0.5", "a": "0.4"},
            "datetime": "2024-09-01 12:00:00",
        }
    ]
    rows = parse_page(_page(dates, {}), "ENG-Premier League")
    assert len(rows) == 1
    assert rows[0]["home_ppda"] is None  # no teamsData -> null, not a crash
    assert rows[0]["home_goals"] == 0


def test_parse_page_empty_when_no_data_block():
    assert parse_page("<html>no data here</html>", "ENG-Premier League") == []


def test_season_year_maps_to_understat_start_year():
    assert _season_year("2425") == "2024"
    assert _season_year("2526") == "2025"
