"""
Draw tendency score.
DrawTendency = 0.28*Balance + 0.22*LowTempo + 0.18*LowGoal + 0.18*DrawHistory + 0.14*TacticalSymmetry
"""
from __future__ import annotations


def compute_draw_tendency(
    balance_score: float,      # closeness of team strengths [0,1]
    low_tempo_signal: float,   # fewer shots/actions expected [0,1]
    low_goal_signal: float,    # under 2.5 goals tendency [0,1]
    draw_history: float,       # historical draw rate [0,1]
    tactical_symmetry: float,  # similar tactical systems [0,1]
) -> float:
    score = (
        0.28 * balance_score
        + 0.22 * low_tempo_signal
        + 0.18 * low_goal_signal
        + 0.18 * draw_history
        + 0.14 * tactical_symmetry
    )
    return max(0.0, min(1.0, score))


def extract_draw_features(
    home_strength: float,
    away_strength: float,
    home_goals_per_game: float,
    away_goals_per_game: float,
    home_draw_rate: float,
    away_draw_rate: float,
) -> dict:
    # Balance: how similar are the two teams (0 = very unequal, 1 = identical)
    balance_score = 1.0 - min(1.0, abs(home_strength - away_strength))

    # Low tempo: few total goals expected
    total_goals_pg = home_goals_per_game + away_goals_per_game
    low_tempo_signal = max(0.0, min(1.0, 1.0 - (total_goals_pg - 1.5) / 3.0))

    # Low goal signal: combined probability of under 2.5 goals
    # Simplified: if combined > 3 goals/game, signal is 0
    low_goal_signal = max(0.0, min(1.0, 1.0 - (total_goals_pg / 3.0)))

    # Draw history: average of both teams' draw rates
    draw_history = (home_draw_rate + away_draw_rate) / 2.0

    # Tactical symmetry: placeholder (full implementation uses formation data)
    tactical_symmetry = balance_score * 0.8

    return {
        "balance_score": balance_score,
        "low_tempo_signal": low_tempo_signal,
        "low_goal_signal": low_goal_signal,
        "draw_history": draw_history,
        "tactical_symmetry": tactical_symmetry,
    }


def get_draw_rate(standings_entry: dict | None) -> float:
    """Calculate historical draw rate from standings data."""
    if not standings_entry:
        return 0.27  # league average prior
    played = standings_entry.get("all", {}).get("played") or 1
    draws = standings_entry.get("all", {}).get("draw") or 0
    return min(1.0, draws / played)
