"""nightly_analysis.py's candidate loop — grouping by fixture.

The LATERAL join in main()'s candidate query returns up to 20 odds rows per
fixture (one per bookmaker/market/selection), not one row per fixture. Seen
live: with real odds data, the same fixture logged "sample below the §5.4
minimum, skipping" 20 times in a row — get_features_as_of() was rerun once
per odds row instead of once per fixture. Fixing that also closed a latent
correctness gap the redundancy had been masking: nothing stopped a second
qualifying bookmaker row for the same fixture from drafting a second pick.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from gamesenze.backtest.features import FeatureWindow
from gamesenze.jobs import nightly_analysis
from gamesenze.jobs._runtime import JobContext
from tests.conftest import NOW, FakeDb

KICKOFF = NOW + timedelta(hours=24)


def _candidate_row(
    fixture_id, *, market="1x2", selection="home", decimal_odds=2.0, bookmaker="test-book"
):
    return {
        "id": fixture_id,
        "sport": "football",
        "kickoff_at": KICKOFF,
        "home_team_id": "home-team",
        "away_team_id": "away-team",
        "home_name": "Home FC",
        "away_name": "Away FC",
        "market": market,
        "selection": selection,
        "decimal_odds": decimal_odds,
        "bookmaker": bookmaker,
        "captured_at": NOW,
    }


class _Settings:
    alert_webhook_url = ""


async def test_get_features_is_called_once_per_fixture_not_once_per_odds_row(
    monkeypatch,
):
    # 5 odds rows (different bookmakers), all for the same fixture — a
    # realistic count once a league has several books quoting a match.
    rows = [_candidate_row("fixture-1", decimal_odds=1.5 + i * 0.1) for i in range(5)]
    db = FakeDb({"select f.id": rows})
    ctx = JobContext(db, _Settings())

    calls = []

    async def fake_features(db_arg, team_id, as_of, **kwargs):
        calls.append(team_id)
        return None  # forces the "sample below minimum" branch — the point

    monkeypatch.setattr(nightly_analysis, "get_features_as_of", fake_features)

    result = await nightly_analysis.main(ctx)

    assert result == 0
    # 2 calls (home + away) for ONE fixture, not 2 x 5 for five odds rows.
    assert calls == ["home-team", "away-team"]


async def test_get_features_is_called_once_per_distinct_fixture_with_several(
    monkeypatch,
):
    rows = [
        *[_candidate_row("fixture-1", decimal_odds=1.5 + i * 0.1) for i in range(3)],
        *[_candidate_row("fixture-2", decimal_odds=2.0 + i * 0.1) for i in range(4)],
    ]
    db = FakeDb({"select f.id": rows})
    ctx = JobContext(db, _Settings())

    calls = []

    async def fake_features(db_arg, team_id, as_of, **kwargs):
        calls.append(team_id)
        return None

    monkeypatch.setattr(nightly_analysis, "get_features_as_of", fake_features)

    await nightly_analysis.main(ctx)

    # 2 fixtures x 2 sides = 4 calls, regardless of 7 total odds rows.
    assert len(calls) == 4


async def test_only_the_best_edge_row_drafts_and_only_once_per_fixture(monkeypatch):
    """Two books quote a full 1X2 market for one fixture; the model rates the
    home side as value. Exactly one pick must be drafted, at the better of the
    two home prices — and the selector must de-vig each book, so it needs the
    complete market, not a lone selection.
    """
    rows = [
        # Book A: a fair-ish market, home a touch of value.
        _candidate_row("fixture-1", selection="home", decimal_odds=2.0, bookmaker="a"),
        _candidate_row("fixture-1", selection="draw", decimal_odds=3.6, bookmaker="a"),
        _candidate_row("fixture-1", selection="away", decimal_odds=4.5, bookmaker="a"),
        # Book B: a better home price, so the larger edge.
        _candidate_row("fixture-1", selection="home", decimal_odds=2.2, bookmaker="b"),
        _candidate_row("fixture-1", selection="draw", decimal_odds=3.5, bookmaker="b"),
        _candidate_row("fixture-1", selection="away", decimal_odds=4.3, bookmaker="b"),
    ]
    db = FakeDb({"select f.id": rows})
    ctx = JobContext(db, _Settings())

    def _window():
        now = datetime.now(timezone.utc)
        return FeatureWindow(
            team_id="t", as_of=now, matches_used=10, xg_for=1.5, xg_against=1.3,
            goals_for=1.4, goals_against=1.2, xg_sd=0.3, points_per_game=1.5,
            latest_match_at=now,
        )

    async def fake_features(db_arg, team_id, as_of, **kwargs):
        return _window()  # real window; price() is patched below

    class _FakePrices:
        expected_home_goals = 1.5
        expected_away_goals = 1.1
        btts_yes = 0.5

        def probability(self, market, selection):
            # Home is the value side; draw and away sit at/below the market.
            return {"home": 0.60, "draw": 0.24, "away": 0.16}.get(selection)

    monkeypatch.setattr(nightly_analysis, "get_features_as_of", fake_features)
    monkeypatch.setattr(
        nightly_analysis.MatchModel, "price", lambda self, home, away: _FakePrices()
    )

    admitted = []

    async def fake_can_cover(self, sport, *, policy=None):
        from gamesenze.coverage import CoverageDecision

        admitted.append(sport)
        return CoverageDecision(True, "ok", 16, 1000)

    async def fake_mark_covered(self, fixture_id, covered_at):
        return None

    monkeypatch.setattr(
        nightly_analysis.CoverageController, "can_cover", fake_can_cover
    )
    monkeypatch.setattr(
        nightly_analysis.CoverageController, "mark_covered", fake_mark_covered
    )

    result = await nightly_analysis.main(ctx)

    assert result == 0
    assert len(admitted) == 1  # can_cover() called once, not once per row
    picks = db.writes_matching("insert into picks")
    assert len(picks) == 1
    args = picks[0][1]
    # args order: fixture_id, market, selection, internal_prob, capture_odds, ...
    assert args[2] == "home"  # selection — the value side
    assert args[4] == 2.2  # capture_odds — the better of the two home prices
