"""
Lineup impact features.
LineupPenalty = Σ(player_importance * role_weight * absence_severity)

Extended: key attacker / key defender absent flags for role-specific impact.
An absent starting attacker raises the penalty multiplier (top scorer proxy).
An absent starting defender raises the penalty multiplier (set piece + aerial vulnerability).
"""
from __future__ import annotations

ROLE_WEIGHTS = {
    "Goalkeeper": 1.0,
    "Defender": 0.7,
    "Midfielder": 0.6,
    "Attacker": 0.5,
}

# Enhanced multipliers for role-specific absences
_ATTACKER_MULTIPLIER = 1.5   # top scorer proxy — goal threat collapses disproportionately
_DEFENDER_MULTIPLIER = 1.4   # set piece + aerial duel vulnerability

ABSENCE_SEVERITY = {
    "injured": 1.0,
    "suspended": 0.9,
    "doubtful": 0.5,
}

# Severity threshold to flag as "key absence" (not for doubtful players)
_KEY_ABSENCE_SEVERITY_THRESHOLD = 0.85


def compute_lineup_penalty(injuries_payload: list[dict], team_id: int) -> float:
    """
    injuries_payload: API-Football /injuries response for a fixture.
    Returns a penalty score in [0, 1]. Higher = more impacted.
    Attacker and Defender absences carry enhanced multipliers.
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
        importance = 0.6

        # Apply role-specific multiplier for severe absences
        if severity >= _KEY_ABSENCE_SEVERITY_THRESHOLD:
            if role == "Attacker":
                role_w *= _ATTACKER_MULTIPLIER
            elif role == "Defender":
                role_w *= _DEFENDER_MULTIPLIER

        penalty += importance * role_w * severity

    return min(1.0, penalty)


def compute_key_absences(injuries_payload: list[dict], team_id: int) -> dict:
    """
    Detect whether a key attacker or key defender is absent (injured/suspended).

    Returns:
        {"key_attacker_absent": bool, "key_defender_absent": bool}
    """
    key_attacker_absent = False
    key_defender_absent = False

    for entry in injuries_payload:
        player = entry.get("player", {})
        team = entry.get("team", {})

        if team.get("id") != team_id:
            continue

        reason = (entry.get("type") or "").lower()
        role = (player.get("type") or "").strip()
        severity = ABSENCE_SEVERITY.get(reason, 0.3)

        if severity < _KEY_ABSENCE_SEVERITY_THRESHOLD:
            continue  # doubtful — not counted as confirmed key absence

        if role == "Attacker":
            key_attacker_absent = True
        elif role == "Defender":
            key_defender_absent = True

    return {
        "key_attacker_absent": key_attacker_absent,
        "key_defender_absent": key_defender_absent,
    }


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
