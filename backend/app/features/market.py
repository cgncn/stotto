"""
Market support feature.
Derived from the latest odds snapshot for a fixture.

Extended: odds movement delta + sharp money signal.
  - odds_delta_home: current_home_odds - opening_home_odds
    (positive = odds drifted up = market moved against home = signal toward away)
  - sharp_money_signal: [-1, 1]
    +1 = strong signal toward away (home drifted badly)
    -1 = strong signal toward home (home shortened significantly)
"""
from __future__ import annotations
import math

_SHARP_NORMALISER = 0.5   # clamp factor: a 0.50 drift = signal ±1.0


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


def compute_odds_movement(
    snapshots: list[dict],
) -> dict:
    """
    Compute odds movement delta and sharp money signal from ordered snapshots.

    Args:
        snapshots: list of dicts ordered by snapshot_time ASC, each with:
            {"home_odds": float, "draw_odds": float, "away_odds": float}
            (None values are tolerated — snapshot is skipped)

    Returns:
        opening_odds_home, opening_odds_draw, opening_odds_away: first valid snapshot
        odds_delta_home: latest_home - opening_home (positive = odds drifted = against home)
        sharp_money_signal: float in [-1, 1]
            +1 = sharp money toward away, -1 = sharp money toward home
    """
    valid = [
        s for s in snapshots
        if s.get("home_odds") is not None
        and s.get("draw_odds") is not None
        and s.get("away_odds") is not None
    ]

    if len(valid) < 2:
        # Not enough data to compute movement — return neutral
        first = valid[0] if valid else {}
        return {
            "opening_odds_home": first.get("home_odds"),
            "opening_odds_draw": first.get("draw_odds"),
            "opening_odds_away": first.get("away_odds"),
            "odds_delta_home": 0.0,
            "sharp_money_signal": 0.0,
        }

    opening = valid[0]
    latest = valid[-1]

    odds_delta_home = (latest["home_odds"] or 0) - (opening["home_odds"] or 0)
    # Positive delta: home drifted out (odds rose) = market moving against home = sharp toward away
    sharp_money_signal = max(-1.0, min(1.0, odds_delta_home / _SHARP_NORMALISER))

    return {
        "opening_odds_home": opening["home_odds"],
        "opening_odds_draw": opening["draw_odds"],
        "opening_odds_away": opening["away_odds"],
        "odds_delta_home": round(odds_delta_home, 4),
        "sharp_money_signal": round(sharp_money_signal, 4),
    }
