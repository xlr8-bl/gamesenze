"""REQ-BUDGET-3 and the §8 ladder."""

from __future__ import annotations

import pytest

from gamesenze.budget import BudgetExhausted, BudgetMeter, BudgetStatus, period_key
from gamesenze.config import PROVIDER_BUDGETS
from gamesenze.degrade import Rung, policy_from_statuses, rung_for, worst_rung
from tests.conftest import NOW, FakeDb


def test_period_key_is_daily_or_monthly_per_provider():
    assert period_key(PROVIDER_BUDGETS["api_football"], NOW) == "2026-08-18"
    assert period_key(PROVIDER_BUDGETS["sportsgameodds"], NOW) == "2026-08"


async def test_reserve_increments_and_logs_the_call(clock):
    db = FakeDb({"returning calls_used": 5})
    meter = BudgetMeter(db, clock)

    status = await meter.reserve("api_football", "fixtures", job="fixture_sync")

    assert status.used == 5
    assert db.wrote("insert into api_budget")
    assert db.wrote("insert into api_calls")


async def test_reserve_raises_rather_than_breaching_the_ceiling(clock):
    # The conditional upsert returns nothing when the ceiling would be passed.
    db = FakeDb({"returning calls_used": None, "select calls_used from api_budget": 100})
    meter = BudgetMeter(db, clock)

    with pytest.raises(BudgetExhausted) as exc:
        await meter.reserve("api_football", "fixtures")

    assert exc.value.used == 100
    # Nothing was logged as called, because nothing was called.
    assert not db.wrote("insert into api_calls")


async def test_unknown_provider_is_a_configuration_error(clock):
    meter = BudgetMeter(FakeDb(), clock)
    with pytest.raises(ValueError, match="unknown provider"):
        await meter.reserve("mystery_api", "x")


async def test_unlimited_provider_is_metered_but_never_blocks(clock):
    db = FakeDb({"select calls_used from api_budget": 9999})
    meter = BudgetMeter(db, clock)

    status = await meter.reserve("open_meteo", "forecast")

    assert status.unlimited
    assert db.wrote("insert into api_budget")


@pytest.mark.parametrize(
    ("used", "expected"),
    [
        (0, Rung.NORMAL),
        (79, Rung.NORMAL),
        (80, Rung.REDUCED),
        (89, Rung.REDUCED),
        (90, Rung.CLOSING_ONLY),
        (99, Rung.CLOSING_ONLY),
        (100, Rung.EXHAUSTED),
        (120, Rung.EXHAUSTED),
    ],
)
def test_ladder_thresholds_are_exactly_80_90_100(used, expected):
    assert rung_for(BudgetStatus("api_football", "2026-08-18", used, 100)) is expected


def test_pipeline_degrades_to_its_most_constrained_provider():
    statuses = {
        "open_meteo": BudgetStatus("open_meteo", "d", 5000, 0),
        "api_football": BudgetStatus("api_football", "d", 10, 100),
        "sportsgameodds": BudgetStatus("sportsgameodds", "m", 2400, 2500),
    }
    assert worst_rung(statuses) is Rung.CLOSING_ONLY


def test_each_rung_permits_the_right_amount_of_work():
    def policy(used, limit=100):
        return policy_from_statuses({"a": BudgetStatus("a", "p", used, limit)})

    assert policy(10).snapshots_per_fixture == 16
    assert policy(85).snapshots_per_fixture == 12   # halved outside T-3h
    assert policy(95).snapshots_per_fixture == 1    # closing only
    assert policy(100).snapshots_per_fixture == 0

    # §8: at 100% we publish no new picks. Every other rung still may.
    assert policy(10).may_publish
    assert policy(85).may_publish
    assert policy(95).may_publish
    assert not policy(100).may_publish


def test_exhausted_rung_tells_the_reader_what_is_happening():
    p = policy_from_statuses({"a": BudgetStatus("a", "p", 100, 100)})
    assert p.banner is not None
    assert "last-known" in p.banner
