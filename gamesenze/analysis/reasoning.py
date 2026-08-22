"""Write the read a subscriber sees under a pick — in football, not maths.

Everything upstream of here speaks in expected goals, probabilities and
shrinkage. None of that reaches the page. §"we are not here to tell them
statistic terms": the card carries a plain-language verdict and the argument
behind it, the way a tipsheet is written, and the model stays our business.

The generator is deterministic and template-free of numbers: it turns each
team's level into a qualitative band (how they attack, how they defend, what
form they are in), compares the two sides, and states the call. It is not an
LLM — this runs on a schedule at zero cost — so the craft is in the banding
and the sentence assembly, not in generation.
"""

from __future__ import annotations

from ..backtest.features import FeatureWindow


def _band(value: float, edges: tuple[float, float, float], words: tuple[str, str, str, str]) -> str:
    lo, mid, hi = edges
    if value < lo:
        return words[0]
    if value < mid:
        return words[1]
    if value < hi:
        return words[2]
    return words[3]


def _attack(xg_for: float) -> str:
    return _band(xg_for, (1.0, 1.35, 1.75), ("blunt", "steady", "dangerous", "prolific"))


def _defence(xg_against: float) -> str:
    # Lower is better, so the words run strong -> weak.
    return _band(xg_against, (1.05, 1.35, 1.7), ("miserly", "solid", "shaky", "leaky"))


def _form(ppg: float) -> str:
    return _band(ppg, (0.9, 1.4, 1.9), ("out of sorts", "patchy", "in good order", "flying"))


def _venue_form(f: FeatureWindow, home: bool) -> str:
    where = "at home" if home else "on the road"
    return f"{_form(f.points_per_game)} {where}"


def _finishing(f: FeatureWindow) -> str | None:
    """Goals scored against the chances created — clinical, or wasteful.

    A team scoring well above the quality of its chances has been riding its
    finishing, which tends not to last; well below, and better output is due.
    Returns None when the two are close enough not to be worth a line.
    """
    if f.xg_for <= 0:
        return None
    ratio = f.goals_for / f.xg_for
    if ratio >= 1.2:
        return "have been clinical, scoring more than their chances have merited"
    if ratio <= 0.8:
        return "have been wasteful in front of goal, with more goals in them than the table shows"
    return None


def _pressing(f: FeatureWindow) -> str | None:
    """Pressing intensity from PPDA, when the data carries it (lower = higher press)."""
    if f.ppda is None:
        return None
    if f.ppda < 9:
        return "press high and hunt the ball back quickly"
    if f.ppda > 14:
        return "sit off and stay compact rather than press"
    return None


def _model_outlook(prices) -> str | None:
    """The model's wider read on the game, in plain terms — no numbers shown.

    Uses the same price object the pick came from to speak to both-teams-to-
    score and the likely goal count, so the card carries a view on the shape
    of the match beyond the one selection being backed.
    """
    if prices is None:
        return None
    total = prices.expected_home_goals + prices.expected_away_goals
    btts = prices.btts_yes

    goals = (
        "shapes up as an open, high-scoring game"
        if total >= 2.9
        else "points to a cagey, low-scoring night"
        if total <= 2.15
        else "looks like a middling one for goals"
    )
    both = (
        "with both ends likely to find the net"
        if btts >= 0.58
        else "and one side looks the likelier to keep it tight"
        if btts <= 0.45
        else "with a goal in both sides as likely as not"
    )
    return f"Our wider read is that it {goals}, {both}."


def confidence_from(edge: float, published_prob: float) -> str:
    """Map the edge and our conviction to the three published tiers."""
    if edge >= 0.10 and published_prob >= 0.5:
        return "best_bet"
    if edge >= 0.07:
        return "strong_lean"
    return "lean"


def _subject(market: str, selection: str, home: str, away: str) -> str:
    m, s = market.lower(), selection.lower()
    if m == "1x2":
        return {"home": home, "away": away, "draw": "a draw"}.get(s, selection)
    if m.startswith("ou_"):
        return "goals" if s == "over" else "a tight, low-scoring game"
    if m == "btts":
        return "both teams to score" if s == "yes" else "a clean sheet at one end"
    return selection


def write_reasoning(
    *,
    home_name: str,
    away_name: str,
    home: FeatureWindow,
    away: FeatureWindow,
    market: str,
    selection: str,
    excluded_labels: list[str] | None = None,
    prices=None,
) -> str:
    """Assemble the verdict lead plus the argument, in plain football terms.

    The first sentence is the call; splitRead() on the frontend renders it
    louder than the rest, so it must stand alone as the verdict. When the
    model's `prices` are passed, the read also carries finishing quality,
    pressing and the model's wider outlook (both-teams and goal count) — using
    the fuller signal set, not just attack/defence/form.
    """
    subject = _subject(market, selection, home_name, away_name)
    sel = selection.lower()
    mk = market.lower()

    # 1) The verdict lead.
    if mk == "1x2" and sel in ("home", "away"):
        backed = home_name if sel == "home" else away_name
        lead = f"We're with {backed} here."
    elif mk == "1x2" and sel == "draw":
        lead = "This one has stalemate written on it."
    elif mk.startswith("ou_"):
        lead = "We're on the goals." if sel == "over" else "We're taking the unders."
    elif mk == "btts":
        lead = (
            "Both ends look like scoring."
            if sel == "yes"
            else "We fancy one side to keep it tight."
        )
    else:
        lead = f"Our call is {subject}."

    # 2) The two-team read, in football language.
    h_attack, h_def, h_form = _attack(home.xg_for), _defence(home.xg_against), _venue_form(home, True)
    a_attack, a_def, a_form = _attack(away.xg_for), _defence(away.xg_against), _venue_form(away, False)

    body = [
        f"{home_name} have looked {h_attack} going forward and {h_def} at the back, "
        f"and come in {h_form}.",
        f"{away_name} have been {a_attack} in attack and {a_def} defensively, "
        f"{a_form}.",
    ]

    # 2b) The fuller signal set: finishing quality, pressing, and — for the more
    # notable side of each — weave a line in rather than listing every metric.
    for name, f in ((home_name, home), (away_name, away)):
        finish, press = _finishing(f), _pressing(f)
        if finish and press:
            body.append(f"{name} {finish}, and they {press}.")
        elif finish:
            body.append(f"{name} {finish}.")
        elif press:
            body.append(f"{name} {press}.")

    # 3) Tie it to the actual call so the argument matches the pick.
    if mk == "1x2" and sel == "home":
        body.append(
            f"On the balance of the two, {home_name} are the side better set up to "
            "take this, and the price is longer than that edge deserves."
        )
    elif mk == "1x2" and sel == "away":
        body.append(
            f"{away_name} carry enough to trouble this hosts, and the market has been "
            "slow to give them their due."
        )
    elif mk == "1x2" and sel == "draw":
        body.append(
            "Two sides this evenly matched, with neither defence giving much away, "
            "is exactly the shape a draw comes from — and it pays handsomely."
        )
    elif mk.startswith("ou_") and sel == "over":
        body.append(
            "With this much attacking intent and defences that can be got at, the "
            "goals should come, and the line looks beatable."
        )
    elif mk.startswith("ou_") and sel == "under":
        body.append(
            "Two careful sides who keep things tight point to a low count, and the "
            "over is the popular side, which is where the value against it sits."
        )
    elif mk == "btts":
        body.append(
            "Both ends have been busy enough to expect goals at each, and the price "
            "rewards it."
            if sel == "yes"
            else "One of these defences should hold, and that is the value here."
        )

    # 3b) The model's wider outlook on the match shape (both-teams, goal count).
    outlook = _model_outlook(prices)
    if outlook:
        body.append(outlook)

    # 4) Early-season honesty: name what we deliberately left out.
    if excluded_labels:
        shown = ", ".join(excluded_labels[:3]).lower()
        body.append(
            f"This early we're leaving {shown} out of it — the sample is too thin to "
            "lean on, so this read stands on form and the matchup rather than on noise."
        )

    return lead + " " + " ".join(body)
