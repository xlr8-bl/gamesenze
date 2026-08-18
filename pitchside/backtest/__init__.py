"""Layer 7 — backtest integrity (§5.7).

This is the layer that separates a real edge from a fictional one.
"""

from .calibration import brier_score, calibration_bins, calibration_error
from .features import FeatureWindow, LookaheadError, get_features_as_of
from .harness import BacktestHarness, BacktestResult

__all__ = [
    "FeatureWindow",
    "get_features_as_of",
    "LookaheadError",
    "brier_score",
    "calibration_bins",
    "calibration_error",
    "BacktestHarness",
    "BacktestResult",
]
