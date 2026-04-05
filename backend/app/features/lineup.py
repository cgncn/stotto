"""
Lineup impact features.
LineupPenalty = Σ(player_importance * role_weight * absence_severity)
"""
from __future__ import annotations

ROLE_WEIGHTS = {
    "Goalkeeper": 1.0,
    "Defender": 0.7,
    "Midfielder": 0.6,
    "Attacker": 0.5,
}

ABSENCE_SEVERITY = {
    "injured": 1.0,
    "suspended": 0.9,
    "doubtful": 0.5,
}


def compute_lineup_penalty(injuries_payload: list[dict], team_id: int) -> float:
    """
    injuries_payload: API-Football /injuries response for a fixture.
    Returns a penalty score in [0, 1]. Higher = more impacted.
    """
    penalty = 0.0

    for entry in injuries_payload:
        player = entry.get("player", {})
        team = entry.get("team", {})

        if team.get("id") != team_id:
            continue

        reason = (entry.get("type") or "").lower()
        role = (player.get("type") or "").strip()

        severity = ABSENCE_SEVERITY.get(reason, 0.3)
        role_w = ROLE_WEIGHTS.get(role, 0.5)

        # Importance placeholder: assume 0.6 for known players (improves with squad data)
        importance = 0.6

        penalty += importance * role_w * severity

    # Cap penalty at 1.0; typical impactful injury = ~0.3 per key player
    return min(1.0, penalty)


def compute_lineup_continuity(lineups_payload: list[dict], team_id: int) -> float:
    """
    Returns [0, 1] lineup certainty.
    1.0 = full lineup confirmed; 0.0 = lineup unknown.
    """
    for entry in lineups_payload:
        team = entry.get("team", {})
        if team.get("id") == team_id:
            starters = entry.get("startXI", [])
            if len(starters) == 11:
                return 1.0
            if len(starters) > 0:
                return len(starters) / 11.0
    return 0.0  # lineup not yet available
