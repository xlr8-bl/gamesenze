"""Turn a model price plus a market into at most one defensible pick.

The model (analysis/model.py) prices a match honestly, but a raw
`argmax(prob * odds - 1)` over every selection is not a betting strategy — it
is an adverse-selection machine. `prob * odds - 1` amplifies a small, noisy
difference on a longshot into a huge number: a model that rates a 10.00 shot
at 12% rather than the market's 9% shows a "+20% edge" built entirely on the
least reliable corner of a ten-match sample. Left alone, the selector backs
those every night and nothing else.

Three corrections, each the standard practice a value desk would recognise:

1.  **De-vig the market.** The book's 1/odds includes its margin; the fair
    probability does not. We compare against the fair number, so the margin is
    a hurdle we must clear, not free edge.

2.  **Shrink toward the market.** The closing line is a strong forecast; a
    ten-match xG Poisson is a weak one. Our published probability is a blend,
    weighted toward our model only as far as a small sample earns. This is the
    §5.4 "early in a season, half the numbers are noise" rule made numeric.

3.  **Refuse what the model cannot support.** No pick below a floor
    probability (our tail estimates are not trustworthy enough to sell a
    longshot), and none whose post-shrink edge is implausibly large (a real
    edge is single digits; a huge one is a model error, not a bet).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..odds.math import devig
from .model import MatchPrices

# Weight on our model when blending with the de-vigged market. The market gets
# the rest. Deliberately no higher than a half: over a ten-match window the
# market is at least as informed as we are, and shrinking toward it is what
# stops a noisy estimate from manufacturing edges.
MODEL_WEIGHT = 0.5

# Below this blended probability we do not draft, whatever the "edge". Our
# sub-third-chance estimates are the noisiest we produce, and a tips product
# that sells 10.00 longshots on model noise is not one we would stand behind.
MIN_SELECTION_PROB = 0.30

# The edge band a pick must land in. The floor is worth acting on; anything
# above the ceiling is not a real market inefficiency, it is our model being
# wrong, so we drop it rather than draft it.
MIN_EDGE = 0.04
MAX_EDGE = 0.20


@dataclass(frozen=True)
class PickChoice:
    """The single selection worth drafting for one fixture, or nothing."""

    market: str
    selection: str
    decimal_odds: float
    bookmaker: str
    model_prob: float
    fair_prob: float
    published_prob: float
    edge: float
    row: dict


def _fair_by_selection(rows: list[dict]) -> dict[tuple[str, str, str], float]:
    """De-vig each (bookmaker, market) group and index the fair probabilities.

    Keyed by (bookmaker, market, selection). A group with fewer than two
    outcomes cannot be de-vigged — its margin is unknowable — so it is left
    out and those selections are simply not evaluated.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["bookmaker"], r["market"]), []).append(r)

    fair: dict[tuple[str, str, str], float] = {}
    for (book, market), group in groups.items():
        if len(group) < 2:
            continue
        probs = devig([float(g["decimal_odds"]) for g in group])
        for g, p in zip(group, probs, strict=True):
            fair[(book, market, g["selection"])] = p
    return fair


def select_pick(prices: MatchPrices, rows: list[dict]) -> PickChoice | None:
    """The best defensible selection across the fixture's odds, or None.

    `rows` are this fixture's odds snapshots — one per
    (bookmaker, market, selection) — each a dict with at least `bookmaker`,
    `market`, `selection`, `decimal_odds`. The returned choice, if any, is the
    highest-edge selection that survives shrinkage and the guards above.
    """
    fair = _fair_by_selection(rows)
    best: PickChoice | None = None

    for r in rows:
        model_prob = prices.probability(r["market"], r["selection"])
        if model_prob is None:
            continue
        fair_prob = fair.get((r["bookmaker"], r["market"], r["selection"]))
        if fair_prob is None:
            continue

        published = MODEL_WEIGHT * model_prob + (1.0 - MODEL_WEIGHT) * fair_prob
        if published < MIN_SELECTION_PROB:
            continue

        odds = float(r["decimal_odds"])
        edge = published * odds - 1.0
        if edge < MIN_EDGE or edge > MAX_EDGE:
            continue

        if best is None or edge > best.edge:
            best = PickChoice(
                market=r["market"],
                selection=r["selection"],
                decimal_odds=odds,
                bookmaker=r["bookmaker"],
                model_prob=model_prob,
                fair_prob=fair_prob,
                published_prob=published,
                edge=edge,
                row=r,
            )
    return best
