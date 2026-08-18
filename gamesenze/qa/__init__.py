"""Data quality supervision — §5.

Seven layers, each failing closed:

  1. validation   — range and type rules on arrival
  2. cross_source — two sources must agree on facts both cover
  3. anomaly      — individually valid, collectively implausible
  4. samples      — hard minimums before a factor may be used
  5. gate         — the pre-publication checklist
  6. audit        — yesterday, reviewed every morning
  7. backtest     — point-in-time correctness (see gamesenze.backtest)
"""

from .errors import QAViolation, Severity

__all__ = ["QAViolation", "Severity"]
