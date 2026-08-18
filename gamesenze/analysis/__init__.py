"""The analysis layer — §6.

Every factor here is Tier 1 or Tier 2: computed from data we already hold, or
one cheap request. Tiers 1-3 are entirely free and represent more analytical
depth than any consumer competitor publishes; Tier 4 (premium expected
lineups, live in-play, 140+ book coverage) is a later upgrade, not a launch
requirement.

Everything in this package takes `as_of` and never reads a clock. The lookahead
lint (gamesenze/jobs/lookahead_lint.py) enforces it.
"""

from .model import MatchModel, MatchPrices
from .stakes import stakes_tags

__all__ = ["MatchModel", "MatchPrices", "stakes_tags"]
