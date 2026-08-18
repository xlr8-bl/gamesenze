"""Combo builder — §12."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pitchside.combo import (
    DISCLAIMER,
    ComboError,
    ComboLeg,
    ComboStore,
    ComboTrackRecord,
    build_quote,
    correlation_warnings,
)
from tests.conftest import FakeDb

AS_OF = datetime(2026, 8, 20, 14, 23, tzinfo=UTC)


def leg(pick_id="p1", fixture="f1", odds=2.0, prob=None, sport="football", market="1x2"):
    return ComboLeg(
        pick_id=pick_id,
        fixture_id=fixture,
        label=f"{fixture} {market}",
        market=market,
        selection="home",
        decimal_odds=odds,
        bookmaker="pinnacle",
        odds_as_of=AS_OF,
        internal_prob=prob,
        sport=sport,
    )


def test_parlay_odds_are_the_product_of_the_legs():
    quote = build_quote([leg("p1", odds=2.0), leg("p2", "f2", odds=3.0)])
    assert quote.total_odds == pytest.approx(6.0)


def test_a_hundred_pound_stake_reports_payout_and_profit():
    quote = build_quote([leg("p1", odds=1.90), leg("p2", "f2", odds=2.20)], stake=100)
    assert quote.expected_payout == pytest.approx(418.0)
    assert quote.profit == pytest.approx(318.0)


def test_implied_probability_is_the_reciprocal_of_the_price():
    quote = build_quote([leg("p1", odds=2.0), leg("p2", "f2", odds=2.0)])
    assert quote.implied_prob == pytest.approx(0.25)


def test_our_own_number_is_reported_separately_from_the_price():
    quote = build_quote(
        [leg("p1", odds=2.0, prob=0.55), leg("p2", "f2", odds=2.0, prob=0.60)]
    )
    assert quote.model_prob_independent == pytest.approx(0.33)
    assert quote.implied_prob == pytest.approx(0.25)


def test_no_model_number_when_a_leg_lacks_one():
    quote = build_quote([leg("p1", odds=2.0, prob=0.55), leg("p2", "f2", odds=2.0)])
    assert quote.model_prob_independent is None


@pytest.mark.parametrize("count", [1, 6])
def test_leg_count_is_bounded_at_two_to_five(count):
    legs = [leg(f"p{i}", f"f{i}") for i in range(count)]
    with pytest.raises(ComboError, match="2-5 legs"):
        build_quote(legs)


def test_the_same_pick_cannot_be_stacked_on_itself():
    with pytest.raises(ComboError, match="cannot appear twice"):
        build_quote([leg("p1"), leg("p1")])


def test_a_zero_stake_is_refused():
    with pytest.raises(ComboError, match="stake must be positive"):
        build_quote([leg("p1"), leg("p2", "f2")], stake=0)


def test_same_fixture_legs_are_flagged_as_correlated():
    # Multiplying leg probabilities assumes independence. Two markets on one
    # match are not independent, and quoting a confident number for them is
    # exactly the nonsense §5.4 exists to prevent.
    warnings = correlation_warnings(
        [leg("p1", "f1", market="ou_2.5"), leg("p2", "f1", market="1x2")]
    )
    assert len(warnings) == 1
    assert "correlated" in warnings[0]
    assert "independence estimate" in warnings[0]


def test_independent_fixtures_produce_no_correlation_warning():
    assert correlation_warnings([leg("p1", "f1"), leg("p2", "f2")]) == []


def test_mixed_sport_combos_are_flagged_for_book_acceptance():
    warnings = correlation_warnings(
        [leg("p1", "f1"), leg("p2", "f2", sport="basketball")]
    )
    assert any("Mixed-sport" in w for w in warnings)


def test_the_quote_carries_the_oldest_price_timestamp():
    # "as of 14:23 UTC" must be honest: the combo is only as fresh as its
    # stalest leg.
    older = ComboLeg(
        "p2", "f2", "x", "1x2", "home", 2.0, "fanduel",
        datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )
    quote = build_quote([leg("p1"), older])
    assert quote.odds_as_of == datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def test_every_quote_carries_the_disclaimer():
    quote = build_quote([leg("p1"), leg("p2", "f2")])
    assert quote.disclaimer == DISCLAIMER
    assert "don't hold funds" in quote.to_dict()["disclaimer"]


def test_the_payload_contains_no_affiliate_or_slip_fields():
    payload = build_quote([leg("p1"), leg("p2", "f2")]).to_dict()
    flat = str(payload).lower()
    for forbidden in ("affiliate", "betslip", "bet_slip", "deeplink", "commission"):
        assert forbidden not in flat


def test_track_record_note_declines_to_quote_a_thin_record():
    quote = build_quote(
        [leg("p1"), leg("p2", "f2")], track_record=ComboTrackRecord(2, 7, 3)
    )
    assert "too few" in quote.track_record_note


def test_track_record_note_compares_observed_with_implied():
    quote = build_quote(
        [leg("p1", odds=2.0), leg("p2", "f2", odds=2.0)],
        track_record=ComboTrackRecord(2, 80, 18),
    )
    assert "22.5%" in quote.track_record_note   # observed
    assert "25.0%" in quote.track_record_note   # implied by the price


async def test_saving_a_combo_writes_the_session_and_its_legs():
    db = FakeDb({"returning id": "combo-uuid"})
    quote = build_quote([leg("p1"), leg("p2", "f2")])

    combo_id = await ComboStore(db).save(
        "user-1", quote, region="UK", created_at=AS_OF
    )

    assert combo_id == "combo-uuid"
    assert db.wrote("insert into combo_sessions")
    assert len(db.writes_matching("insert into combo_legs")) == 2


async def test_logging_a_placed_bet_records_what_the_user_reports():
    db = FakeDb({"returning id": "bet-uuid"})
    bet_id = await ComboStore(db).log_bet(
        "combo-1",
        "user-1",
        bookmaker="bet365",
        odds_received=5.8,
        stake_amount=25.0,
        placed_at=AS_OF,
    )
    assert bet_id == "bet-uuid"
    assert db.wrote("insert into combo_bets")
