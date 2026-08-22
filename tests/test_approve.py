"""approve.py — the human sign-off that flips a draft to published."""

from __future__ import annotations

from datetime import datetime, timezone

from gamesenze.jobs import approve
from gamesenze.jobs._runtime import JobContext
from tests.conftest import FakeDb


class _Settings:
    alert_webhook_url = ""


class _Policy:
    may_publish = True


def _draft(**over):
    now = datetime.now(timezone.utc)
    base = {
        "id": "pick-1",
        "fixture_id": "fix-1",
        "market": "1x2",
        "selection": "home",
        "internal_prob": 0.52,
        "capture_odds": 2.10,
        "captured_at": now,  # fresh
        "reasoning_full": "x" * 240,  # over the 200-char floor
        "valid_factors": ["opponent_adjusted", "recent_form", "scoring_trend", "defensive_record"],
        "stakes_tags": [],
        "home_team_id": "h",
        "away_team_id": "a",
        "kickoff_at": now,
        "home": "Home FC",
        "away": "Away FC",
    }
    base.update(over)
    return base


def _ctx(rows):
    db = FakeDb({"from picks p": rows, "from qa_flags": []})
    return db, JobContext(db, _Settings())


async def test_a_clean_draft_publishes_under_a_reviewer(monkeypatch):
    db, ctx = _ctx([_draft()])
    monkeypatch.setattr(approve, "policy_from_statuses", lambda s: _Policy())
    monkeypatch.setattr(approve.sys, "argv",
                        ["approve", "--all", "--reviewer", "Ashley"])

    rc = await approve.main(ctx)
    assert rc == 0
    assert db.wrote("set status = 'published'")
    assert db.wrote("set reviewed_by")


async def test_preview_without_reviewer_publishes_nothing(monkeypatch):
    db, ctx = _ctx([_draft()])
    monkeypatch.setattr(approve, "policy_from_statuses", lambda s: _Policy())
    monkeypatch.setattr(approve.sys, "argv", ["approve"])

    rc = await approve.main(ctx)
    assert rc == 0
    assert not db.wrote("set status = 'published'")


async def test_thin_reasoning_is_held_not_published(monkeypatch):
    db, ctx = _ctx([_draft(reasoning_full="too short")])
    monkeypatch.setattr(approve, "policy_from_statuses", lambda s: _Policy())
    monkeypatch.setattr(approve.sys, "argv",
                        ["approve", "--all", "--reviewer", "Ashley"])

    rc = await approve.main(ctx)
    assert rc == 0
    assert not db.wrote("set status = 'published'")


async def test_stale_odds_is_held(monkeypatch):
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db, ctx = _ctx([_draft(captured_at=old)])
    monkeypatch.setattr(approve, "policy_from_statuses", lambda s: _Policy())
    monkeypatch.setattr(approve.sys, "argv",
                        ["approve", "--all", "--reviewer", "Ashley"])

    rc = await approve.main(ctx)
    assert rc == 0
    assert not db.wrote("set status = 'published'")


async def test_too_few_factors_is_held(monkeypatch):
    db, ctx = _ctx([_draft(valid_factors=["opponent_adjusted", "recent_form"])])
    monkeypatch.setattr(approve, "policy_from_statuses", lambda s: _Policy())
    monkeypatch.setattr(approve.sys, "argv",
                        ["approve", "--all", "--reviewer", "Ashley"])

    rc = await approve.main(ctx)
    assert rc == 0
    assert not db.wrote("set status = 'published'")
