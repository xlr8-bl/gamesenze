"""Combo builder — §12.

An analytics and visualisation tool, not a betting service. We show the maths;
the subscriber places the bet at their own book. Three constraints from the
compliance notes shape this module more than anything else:

* no pre-filled bet slips are generated, and nothing here can post to a book;
* no affiliate links or commission tracking exist anywhere in the payload;
* every price carries the timestamp of the snapshot it came from, so the UI
  says "as of 14:23 UTC" rather than implying a live quote.

The one piece of maths worth arguing about is the risk warning. Multiplying leg
probabilities assumes the legs are independent. Two picks on the same fixture
are not, and telling a subscriber their same-match parlay has a 12% chance when
the true number is different would be exactly the kind of confident-looking
nonsense §5.4 exists to prevent. So correlated legs are detected and stated,
and the independence estimate is labelled as one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from math import prod
from typing import Any

from .db import Db
from .odds.math import implied_probability

MIN_LEGS = 2
MAX_LEGS = 5

DISCLAIMER = (
    "We don't hold funds or execute wagers; you place bets at your sportsbook."
)


@dataclass(frozen=True)
class ComboLeg:
    pick_id: str
    fixture_id: str
    label: str            # "Liverpool vs Man Utd — over 2.5"
    market: str
    selection: str
    decimal_odds: float
    bookmaker: str
    odds_as_of: datetime
    # Our number for this leg, when the pick has one.
    internal_prob: float | None = None
    sport: str = "football"

    @property
    def implied_prob(self) -> float:
        return implied_probability(self.decimal_odds)


@dataclass
class ComboQuote:
    legs: list[ComboLeg]
    total_odds: float
    stake: float
    expected_payout: float
    profit: float
    implied_prob: float
    model_prob_independent: float | None
    correlation_warnings: list[str] = field(default_factory=list)
    track_record_note: str | None = None
    odds_as_of: datetime | None = None
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "legs": [
                {
                    "pick_id": leg.pick_id,
                    "fixture_id": leg.fixture_id,
                    "label": leg.label,
                    "market": leg.market,
                    "selection": leg.selection,
                    "odds": round(leg.decimal_odds, 3),
                    "bookmaker": leg.bookmaker,
                    "odds_as_of": leg.odds_as_of.isoformat(),
                }
                for leg in self.legs
            ],
            "leg_count": len(self.legs),
            "total_odds": round(self.total_odds, 4),
            "stake": round(self.stake, 2),
            "expected_payout": round(self.expected_payout, 2),
            "profit": round(self.profit, 2),
            "implied_prob": round(self.implied_prob, 5),
            "model_prob_independent": (
                None
                if self.model_prob_independent is None
                else round(self.model_prob_independent, 5)
            ),
            "correlation_warnings": self.correlation_warnings,
            "track_record_note": self.track_record_note,
            "odds_as_of": self.odds_as_of.isoformat() if self.odds_as_of else None,
            "disclaimer": self.disclaimer,
        }


class ComboError(ValueError):
    pass


def build_quote(
    legs: Sequence[ComboLeg],
    *,
    stake: float = 100.0,
    track_record: ComboTrackRecord | None = None,
) -> ComboQuote:
    """Price a combo. Pure — no database, no network, no book contact."""
    if not MIN_LEGS <= len(legs) <= MAX_LEGS:
        raise ComboError(
            f"a combo takes {MIN_LEGS}-{MAX_LEGS} legs, got {len(legs)}"
        )
    if len({leg.pick_id for leg in legs}) != len(legs):
        raise ComboError("the same pick cannot appear twice in one combo")
    if stake <= 0:
        raise ComboError("stake must be positive")

    total_odds = prod(leg.decimal_odds for leg in legs)
    payout = stake * total_odds

    model_prob = None
    if all(leg.internal_prob is not None for leg in legs):
        model_prob = prod(float(leg.internal_prob) for leg in legs)

    quote = ComboQuote(
        legs=list(legs),
        total_odds=total_odds,
        stake=stake,
        expected_payout=payout,
        profit=payout - stake,
        implied_prob=1.0 / total_odds,
        model_prob_independent=model_prob,
        correlation_warnings=correlation_warnings(legs),
        odds_as_of=min(leg.odds_as_of for leg in legs),
    )

    if track_record is not None:
        quote.track_record_note = track_record.note_for(len(legs), quote)
    return quote


def correlation_warnings(legs: Sequence[ComboLeg]) -> list[str]:
    """Say plainly where the independence assumption does not hold.

    Same-fixture legs are the clear case; most books will not accept them in
    one parlay anyway, and where they do the price is not the product of the
    singles. Stating the limit beats a number we cannot defend (REQ-QA-2 in
    spirit).
    """
    warnings: list[str] = []

    by_fixture: dict[str, list[ComboLeg]] = {}
    for leg in legs:
        by_fixture.setdefault(leg.fixture_id, []).append(leg)

    for group in by_fixture.values():
        if len(group) > 1:
            markets = ", ".join(sorted(f"{g.market} {g.selection}" for g in group))
            warnings.append(
                f"{len(group)} legs on the same fixture ({markets}). These "
                "outcomes are correlated, so the combined probability shown is "
                "an independence estimate and the true chance differs. Many "
                "books will not accept these in one parlay."
            )

    if len({leg.sport for leg in legs}) > 1:
        warnings.append(
            "Mixed-sport combo — check your book accepts cross-sport parlays "
            "before relying on the price shown."
        )
    return warnings


@dataclass(frozen=True)
class ComboTrackRecord:
    """Observed combo performance, for the §12 risk warning."""

    leg_count: int
    settled: int
    won: int

    @property
    def hit_rate(self) -> float | None:
        return None if self.settled == 0 else self.won / self.settled

    def note_for(self, leg_count: int, quote: ComboQuote) -> str:
        implied = quote.implied_prob
        if self.settled < 20:
            return (
                f"{leg_count}-leg combos: only {self.settled} settled in our "
                "record so far — too few to quote a hit rate. The price implies "
                f"{implied:.1%}."
            )
        return (
            f"{leg_count}-leg combos have landed {self.hit_rate:.1%} of the time "
            f"in our record ({self.won}/{self.settled}); this one's price implies "
            f"{implied:.1%}."
        )


# --- Persistence ------------------------------------------------------------

class ComboStore:
    def __init__(self, db: Db) -> None:
        self._db = db

    async def save(
        self,
        user_id: str,
        quote: ComboQuote,
        *,
        region: str | None,
        created_at: datetime,
    ) -> str:
        import json

        combo_id = await self._db.fetchval(
            """
            insert into combo_sessions (user_id, created_at, pick_ids,
                                        bookmaker_selections, total_odds,
                                        expected_payout, region, odds_as_of)
            values ($1, $2, $3, $4, $5, $6, $7, $8)
            returning id
            """,
            user_id,
            created_at,
            json.dumps([leg.pick_id for leg in quote.legs]),
            json.dumps({leg.pick_id: leg.bookmaker for leg in quote.legs}),
            quote.total_odds,
            quote.expected_payout,
            region,
            quote.odds_as_of,
        )
        for index, leg in enumerate(quote.legs):
            await self._db.execute(
                """
                insert into combo_legs (combo_id, pick_id, leg_index, bookmaker,
                                        odds)
                values ($1, $2, $3, $4, $5)
                on conflict (combo_id, pick_id) do nothing
                """,
                combo_id,
                leg.pick_id,
                index,
                leg.bookmaker,
                leg.decimal_odds,
            )
        return str(combo_id)

    async def log_bet(
        self,
        combo_id: str,
        user_id: str,
        *,
        bookmaker: str,
        odds_received: float,
        stake_amount: float,
        placed_at: datetime,
    ) -> str:
        """Optional self-reported log. We record what the user tells us."""
        bet_id = await self._db.fetchval(
            """
            insert into combo_bets (combo_id, user_id, bookmaker, odds_received,
                                    stake_amount, placed_at)
            values ($1, $2, $3, $4, $5, $6)
            returning id
            """,
            combo_id,
            user_id,
            bookmaker,
            odds_received,
            stake_amount,
            placed_at,
        )
        return str(bet_id)

    async def track_record(self, leg_count: int) -> ComboTrackRecord:
        row = await self._db.fetchrow(
            """
            select count(*) filter (where cb.result is not null) as settled,
                   count(*) filter (where cb.result = 'won')     as won
              from combo_sessions cs
              join combo_bets cb on cb.combo_id = cs.id
             where jsonb_array_length(cs.pick_ids) = $1
            """,
            leg_count,
        )
        row = row or {}
        return ComboTrackRecord(
            leg_count, int(row.get("settled") or 0), int(row.get("won") or 0)
        )

    async def popularity(self, limit: int = 10) -> list[dict[str, Any]]:
        """Which picks get stacked together most (§12 analytics)."""
        return await self._db.fetch(
            "select * from v_combo_pick_popularity order by combo_count desc "
            "limit $1",
            limit,
        )

    async def payout_vs_expected(self) -> list[dict[str, Any]]:
        """Actual payout against expected — are users beating parlays?"""
        return await self._db.fetch("select * from v_combo_performance order by 1")
