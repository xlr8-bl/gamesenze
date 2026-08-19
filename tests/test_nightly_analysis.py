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

from datetime import timedelta

from gamesenze.jobs import nightly_analysis
from gamesenze.jobs._runtime import JobContext
from tests.conftest import NOW, FakeDb

KICKOFF = NOW + timedelta(hours=24)


def _candidate_row(fixture_id, *, market="1x2", selection="home", decimal_odds=2.0):
    return {
        "id": fixture_id,
        "sport": "football",
        "kickoff_at": KICKOFF,
        "home_team_id": "home-team",
        "away_team_id": "away-team",
        "market": market,
        "selection": selection,
        "decimal_odds": decimal_odds,
        "bookmaker": "test-book",
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
    """Three odds rows for one fixture: one far below threshold (skipped),
    two that both clear it at different edges. Exactly one pick must be
    drafted, using the higher-edge row.
    """
    rows = [
        _candidate_row("fixture-1", selection="home", decimal_odds=1.5),  # no edge
        _candidate_row("fixture-1", selection="home", decimal_odds=2.5),  # some edge
        _candidate_row("fixture-1", selection="home", decimal_odds=3.5),  # best edge
    ]
    db = FakeDb({"select f.id": rows})
    ctx = JobContext(db, _Settings())

    async def fake_features(db_arg, team_id, as_of, **kwargs):
        return object()  # any non-None sentinel; price() is patched below

    class _FakePrices:
        def probability(self, market, selection):
            return 0.55  # our model's fixed view of "home" for this test

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
    assert args[4] == 3.5  # capture_odds — the best-edge row's price
