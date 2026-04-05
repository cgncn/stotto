"""
Team strength score.
StrengthScore = 0.30*SeasonPPG + 0.20*GoalDiffPerGame + 0.20*AttackIndex + 0.20*DefenseIndex + 0.10*OpponentAdjustedScore
All inputs are expected to be in [0, 1] normalized range before applying weights.
"""
from __future__ import annotations

import math


def compute_strength_score(
    season_ppg: float,          # points per game this season
    goal_diff_per_game: float,  # raw goal difference per game (can be negative)
    attack_index: float,        # normalized goals scored per game
    defense_index: float,       # normalized goals conceded per game (inverted: higher = better defense)
    opponent_adjusted_score: float,  # performance vs similar-ranked opponents
) -> float:
    score = (
        0.30 * _norm_ppg(season_ppg)
        + 0.20 * _norm_goal_diff(goal_diff_per_game)
        + 0.20 * attack_index
        + 0.20 * defense_index
        + 0.10 * opponent_adjusted_score
    )
    return max(0.0, min(1.0, score))


def _norm_ppg(ppg: float) -> float:
    """Normalize PPG (max theoretical 3.0) to [0, 1]."""
    return max(0.0, min(1.0, ppg / 3.0))


def _norm_goal_diff(gd: float) -> float:
    """Normalize goal difference per game from ~[-3, 3] to [0, 1]."""
    return max(0.0, min(1.0, (gd + 3.0) / 6.0))


def extract_strength_features(standings_entry: dict | None, is_home: bool) -> dict:
    """
    Parse an API-Football standings entry into strength feature components.
    Returns normalized floats. Degrades gracefully when data is missing.
    """
    if not standings_entry:
        return {
            "season_ppg": 0.5,
            "goal_diff_per_game": 0.5,
            "attack_index": 0.5,
            "defense_index": 0.5,
            "opponent_adjusted_score": 0.5,
        }

    played = standings_entry.get("all", {}).get("played") or 1
    points = standings_entry.get("points") or 0
    goals_for = standings_entry.get("all", {}).get("goals", {}).get("for") or 0
    goals_against = standings_entry.get("all", {}).get("goals", {}).get("against") or 0

    ppg = points / played
    gd_per_game = (goals_for - goals_against) / played

    # Attack index: normalize goals_for/game (range ~0–4 goals/game)
    attack_index = max(0.0, min(1.0, (goals_for / played) / 4.0))

    # Defense index: fewer goals conceded = better; normalize ~0–4 range
    defense_index = max(0.0, min(1.0, 1.0 - (goals_against / played) / 4.0))

    # Rank-based opponent adjustment: top teams have higher baseline
    rank = standings_entry.get("rank") or 10
    opponent_adjusted = max(0.0, min(1.0, 1.0 - (rank - 1) / 20.0))

    # Home advantage modifier
    if is_home:
        home_played = standings_entry.get("home", {}).get("played") or 1
        home_points = standings_entry.get("home", {}).get("win", 0) * 3 + standings_entry.get("home", {}).get("draw", 0)
        home_ppg = home_points / home_played
        ppg = 0.6 * ppg + 0.4 * home_ppg

    return {
        "season_ppg": ppg,
        "goal_diff_per_game": gd_per_game,
        "attack_index": attack_index,
        "defense_index": defense_index,
        "opponent_adjusted_score": opponent_adjusted,
    }
