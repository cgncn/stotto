"""
Lineup impact features.
LineupPenalty = Σ(player_importance * role_weight * absence_severity)

Extended: key attacker / key defender absent flags for role-specific impact.
An absent starting attacker raises the penalty multiplier (top scorer proxy).
An absent starting defender raises the penalty multiplier (set piece + aerial vulnerability).
"""
from __future__ import annotations

from collections import Counter

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


# ── Typical-XI helpers ─────────────────────────────────────────────────────


def _typical_xi_from_payloads(
    payloads: list[list[dict]],
    team_external_id: int,
) -> set[int] | None:
    """Pure computation from a list of lineups payload lists.

    Returns the set of player external IDs who started in 3 or more of the
    given snapshots, or None if no data is found for the team.
    """
    counts: Counter[int] = Counter()
    for payload in payloads:
        for entry in payload:
            if entry.get("team", {}).get("id") == team_external_id:
                for starter in entry.get("startXI", []):
                    pid = starter.get("player", {}).get("id")
                    if pid is not None:
                        counts[pid] += 1
    if not counts:
        return None
    return {pid for pid, n in counts.items() if n >= 3}


def build_typical_xi(team_external_id: int, db) -> set[int] | None:
    """Build a typical starting XI from the last 5 confirmed lineup snapshots
    for completed fixtures involving *team_external_id*.

    Returns None when fewer than 2 snapshots are available (falls back to
    legacy behaviour in callers).
    """
    from sqlalchemy import or_
    from app.db import models

    team = db.query(models.Team).filter_by(
        external_provider_id=team_external_id
    ).first()
    if not team:
        return None

    completed_fids = (
        db.query(models.Fixture.id)
        .filter(
            or_(
                models.Fixture.home_team_id == team.id,
                models.Fixture.away_team_id == team.id,
            ),
            models.Fixture.status == "FT",
        )
        .subquery()
    )

    snapshots = (
        db.query(models.FixtureLineupsSnapshot)
        .filter(models.FixtureLineupsSnapshot.fixture_id.in_(completed_fids))
        .order_by(models.FixtureLineupsSnapshot.snapshot_time.desc())
        .limit(5)
        .all()
    )

    if len(snapshots) < 2:
        return None

    payloads = [s.payload_json or [] for s in snapshots]
    return _typical_xi_from_payloads(payloads, team_external_id)


def compute_lineup_penalty(
    injuries_payload: list[dict],
    team_id: int,
    typical_xi: set[int] | None = None,
) -> float:
    """
    injuries_payload: API-Football /injuries response for a fixture.
    team_id: external provider team ID.
    typical_xi: if provided, only count players whose ID is in this set.
    Returns a penalty score in [0, 1]. Higher = more impacted.
    """
    penalty = 0.0

    for entry in injuries_payload:
        player = entry.get("player", {})
        team = entry.get("team", {})

        if team.get("id") != team_id:
            continue

        if typical_xi is not None:
            pid = player.get("id")
            if pid not in typical_xi:
                continue

        reason = (entry.get("type") or "").lower()
        role = (player.get("type") or "").strip()

        severity = ABSENCE_SEVERITY.get(reason, 0.3)
        role_w = ROLE_WEIGHTS.get(role, 0.5)
        importance = 0.6

        if severity >= _KEY_ABSENCE_SEVERITY_THRESHOLD:
            if role == "Attacker":
                role_w *= _ATTACKER_MULTIPLIER
            elif role == "Defender":
                role_w *= _DEFENDER_MULTIPLIER

        penalty += importance * role_w * severity

    return min(1.0, penalty)


def compute_key_absences(
    injuries_payload: list[dict],
    team_id: int,
    typical_xi: set[int] | None = None,
) -> dict:
    """
    Detect whether a key attacker or key defender is absent (injured/suspended).
    If typical_xi is provided, only players in that set are considered.

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

        if typical_xi is not None:
            pid = player.get("id")
            if pid not in typical_xi:
                continue

        reason = (entry.get("type") or "").lower()
        role = (player.get("type") or "").strip()
        severity = ABSENCE_SEVERITY.get(reason, 0.3)

        if severity < _KEY_ABSENCE_SEVERITY_THRESHOLD:
            continue

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
