"""
Head-to-head features.

Computes historical H2H win rates, venue-specific rates, and the bogey-team flag
from the API-Football /fixtures/headtohead payload.

All values degrade gracefully to neutral priors when sample size is 0.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class H2HFeatures:
    h2h_home_win_rate: float       # [0, 1]
    h2h_away_win_rate: float       # [0, 1]
    h2h_draw_rate: float           # [0, 1]
    h2h_venue_home_win_rate: float # [0, 1] — at this specific venue
    h2h_bogey_flag: bool           # away team historically dominates
    h2h_sample_size: int           # number of past meetings used


_NEUTRAL = H2HFeatures(
    h2h_home_win_rate=0.33,
    h2h_away_win_rate=0.33,
    h2h_draw_rate=0.33,
    h2h_venue_home_win_rate=0.33,
    h2h_bogey_flag=False,
    h2h_sample_size=0,
)

_BOGEY_WIN_RATE_THRESHOLD = 0.55
_BOGEY_MIN_SAMPLE = 4


def compute_h2h_features(
    past_fixtures: list[dict],
    home_team_ext_id: int,
    away_team_ext_id: int,
    current_venue: str | None,
) -> H2HFeatures:
    """
    Args:
        past_fixtures: API-Football response list from /fixtures/headtohead
        home_team_ext_id: external_provider_id of the current home team
        away_team_ext_id: external_provider_id of the current away team
        current_venue: venue name of the current fixture (for venue-specific rates)

    Returns:
        H2HFeatures with all computed values.
    """
    if not past_fixtures:
        return _NEUTRAL

    home_wins = draws = away_wins = 0
    venue_home_wins = venue_total = 0

    current_venue_norm = _norm(current_venue)

    for fix in past_fixtures:
        fixture_data = fix.get("fixture", {})
        teams_data = fix.get("teams", {})
        goals_data = fix.get("goals", {})

        fixture_home_id = (teams_data.get("home") or {}).get("id")
        fixture_away_id = (teams_data.get("away") or {}).get("id")

        home_goals = goals_data.get("home")
        away_goals = goals_data.get("away")

        if home_goals is None or away_goals is None:
            continue
        if fixture_home_id is None or fixture_away_id is None:
            continue

        # Determine outcome from the perspective of current home team
        if fixture_home_id == home_team_ext_id:
            # current home team was home in this past fixture
            if home_goals > away_goals:
                outcome = "home_win"
            elif home_goals == away_goals:
                outcome = "draw"
            else:
                outcome = "away_win"
        elif fixture_home_id == away_team_ext_id:
            # current home team was away in this past fixture — invert
            if away_goals > home_goals:
                outcome = "home_win"
            elif away_goals == home_goals:
                outcome = "draw"
            else:
                outcome = "away_win"
        else:
            continue  # unrecognised teams — skip

        if outcome == "home_win":
            home_wins += 1
        elif outcome == "draw":
            draws += 1
        else:
            away_wins += 1

        # Venue-specific rate (only when current home team was also home in past fixture)
        if fixture_home_id == home_team_ext_id and current_venue_norm:
            past_venue = _norm((fixture_data.get("venue") or {}).get("name"))
            if past_venue and past_venue == current_venue_norm:
                venue_total += 1
                if outcome == "home_win":
                    venue_home_wins += 1

    total = home_wins + draws + away_wins
    if total == 0:
        return _NEUTRAL

    h2h_home_win_rate = home_wins / total
    h2h_away_win_rate = away_wins / total
    h2h_draw_rate = draws / total

    h2h_venue_home_win_rate = (
        venue_home_wins / venue_total if venue_total > 0 else h2h_home_win_rate
    )

    h2h_bogey_flag = (
        h2h_away_win_rate > _BOGEY_WIN_RATE_THRESHOLD and total >= _BOGEY_MIN_SAMPLE
    )

    return H2HFeatures(
        h2h_home_win_rate=round(h2h_home_win_rate, 4),
        h2h_away_win_rate=round(h2h_away_win_rate, 4),
        h2h_draw_rate=round(h2h_draw_rate, 4),
        h2h_venue_home_win_rate=round(h2h_venue_home_win_rate, 4),
        h2h_bogey_flag=h2h_bogey_flag,
        h2h_sample_size=min(total, 10),
    )


def _norm(s: str | None) -> str:
    """Lowercase + strip for fuzzy venue matching."""
    if not s:
        return ""
    return s.lower().strip()
