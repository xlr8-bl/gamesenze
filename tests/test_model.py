

from datetime import datetime, timezone

from gamesenze.analysis.model import MatchModel
from gamesenze.backtest.features import FeatureWindow


def _fw(xgf: float, xga: float) -> FeatureWindow:
    now = datetime.now(timezone.utc)
    return FeatureWindow("t", now, 10, xgf, xga, 1.4, 1.2, 0.3, 1.5, now)


def test_prices_any_total_line_not_just_2_5():
    p = MatchModel().price(_fw(1.6, 1.2), _fw(1.3, 1.4))
    # A lower line is easier to go over; a higher line harder — monotonic.
    assert p.probability("ou_1.5", "over") > p.probability("ou_2.5", "over")
    assert p.probability("ou_2.5", "over") > p.probability("ou_3.5", "over")
    # Over and under of the same line are complementary.
    for line in ("ou_1.5", "ou_2.5", "ou_3.5"):
        assert abs(p.probability(line, "over") + p.probability(line, "under") - 1.0) < 1e-9


def test_double_chance_is_the_union_of_two_1x2_outcomes():
    p = MatchModel().price(_fw(1.6, 1.2), _fw(1.3, 1.4))
    assert abs(p.probability("double_chance", "1x") - (p.home + p.draw)) < 1e-9
    assert abs(p.probability("double_chance", "12") - (p.home + p.away)) < 1e-9
    assert abs(p.probability("double_chance", "x2") - (p.draw + p.away)) < 1e-9


def test_btts_and_unknown_markets():
    p = MatchModel().price(_fw(1.6, 1.2), _fw(1.3, 1.4))
    assert 0.0 < p.probability("btts", "yes") < 1.0
    assert p.probability("corners", "over") is None
    assert p.probability("ou_bad", "over") is None
