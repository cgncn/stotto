"""
Market support feature.
Derived from the latest odds snapshot for a fixture.
"""
from __future__ import annotations
import math


def compute_market_support(
    home_odds: float | None,
    draw_odds: float | None,
    away_odds: float | None,
) -> dict:
    """
    Returns:
      implied_p1, implied_px, implied_p2  (margin-adjusted implied probabilities)
      market_draw_signal                  (strength of draw signal from market)
      bookmaker_dispersion                (how spread-out the market is)
    All values in [0, 1].
    """
    if home_odds is None or draw_odds is None or away_odds is None:
        return {
            "implied_p1": 0.33,
            "implied_px": 0.33,
            "implied_p2": 0.33,
            "market_draw_signal": 0.5,
            "bookmaker_dispersion": 0.5,
        }

    raw_p1 = 1.0 / home_odds
    raw_px = 1.0 / draw_odds
    raw_p2 = 1.0 / away_odds
    total = raw_p1 + raw_px + raw_p2

    # Remove overround
    implied_p1 = raw_p1 / total
    implied_px = raw_px / total
    implied_p2 = raw_p2 / total

    # Draw signal: how strongly the market prices the draw
    market_draw_signal = implied_px

    # Dispersion: entropy-based spread (higher = more uncertain market)
    probs = [implied_p1, implied_px, implied_p2]
    entropy = -sum(p * math.log(p + 1e-9) for p in probs)
    max_entropy = math.log(3)
    bookmaker_dispersion = entropy / max_entropy

    return {
        "implied_p1": implied_p1,
        "implied_px": implied_px,
        "implied_p2": implied_p2,
        "market_draw_signal": market_draw_signal,
        "bookmaker_dispersion": bookmaker_dispersion,
    }
