"""
Motivation / objective scoring.

Converts standings data (points gaps to title/top4/top6/relegation) into
a single motivation score [0, 1] per team.

A mid-table team with no objective scores 0.3 (not 0.5) to better separate
genuinely motivated sides from neutral ones.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MotivationFeatures:
    motivation: float              # [0, 1] urgency score
    points_to_title: int           # 0 if leading
    points_to_top4: int            # 0 if in top 4
    points_to_top6: int            # 0 if in top 6
    points_above_relegation: int   # negative if in relegation zone
    long_unbeaten: bool            # 6+ unbeaten in a row


_DEFAULT = MotivationFeatures(
    motivation=0.3,
    points_to_title=999,
    points_to_top4=999,
    points_to_top6=999,
    points_above_relegation=999,
    long_unbeaten=False,
)

# Thresholds
_RELEGATION_DANGER = 3    # ≤ 3 pts above = danger zone
_TITLE_RACE = 6           # ≤ 6 pts off = title race
_TOP4_RACE = 4            # ≤ 4 pts off = CL spot race
_TOP6_RACE = 3            # ≤ 3 pts off = EL spot race
_LONG_UNBEATEN_GAMES = 6  # W/D streak length threshold


def compute_motivation_features(
    team_entry: dict | None,
    all_entries: list[dict],
) -> MotivationFeatures:
    """
    Args:
        team_entry: the standings dict for this specific team (from API-Football)
        all_entries: all standings entries for the league (sorted by rank)

    API-Football standings entry structure (relevant fields):
        {
          "rank": 1,
          "team": {"id": 529, "name": "Real Madrid"},
          "points": 72,
          "form": "WWDWW",
          "all": {"played": 30, "win": 22, "draw": 6, "lose": 2, ...},
          "home": {"win": 12, ...},
          "away": {"win": 10, ...}
        }
    """
    if not team_entry or not all_entries:
        return _DEFAULT

    team_points = team_entry.get("points", 0) or 0
    form_str = team_entry.get("form") or ""
    rank = team_entry.get("rank", 999) or 999

    # Sort all entries by rank to get reliable position
    sorted_entries = sorted(all_entries, key=lambda e: e.get("rank", 999))
    total_teams = len(sorted_entries)

    points_list = [e.get("points", 0) or 0 for e in sorted_entries]
    if not points_list:
        return _DEFAULT

    # Gaps
    leader_points = points_list[0]
    top4_cutoff = points_list[3] if total_teams >= 4 else points_list[-1]
    top6_cutoff = points_list[5] if total_teams >= 6 else points_list[-1]
    # Relegation: bottom 3 teams (or bottom 20% for smaller leagues)
    relegation_idx = max(total_teams - 3, total_teams - max(1, total_teams // 6))
    relegation_cutoff = points_list[relegation_idx] if relegation_idx < total_teams else 0

    points_to_title = max(0, leader_points - team_points)
    points_to_top4 = max(0, top4_cutoff - team_points) if rank > 4 else 0
    points_to_top6 = max(0, top6_cutoff - team_points) if rank > 6 else 0
    points_above_relegation = team_points - relegation_cutoff

    # Motivation formula
    urgency = 0.0

    if points_above_relegation <= _RELEGATION_DANGER:
        ratio = max(0.0, points_above_relegation / _RELEGATION_DANGER)
        urgency += 0.40 * (1.0 - ratio)

    if points_to_title <= _TITLE_RACE:
        urgency += 0.35 * (1.0 - points_to_title / _TITLE_RACE)
    elif points_to_top4 <= _TOP4_RACE:
        urgency += 0.25 * (1.0 - points_to_top4 / _TOP4_RACE)
    elif points_to_top6 <= _TOP6_RACE:
        urgency += 0.15 * (1.0 - points_to_top6 / _TOP6_RACE)

    motivation = min(1.0, max(0.0, _DEFAULT.motivation + urgency))

    long_unbeaten = _compute_long_unbeaten(form_str)

    return MotivationFeatures(
        motivation=round(motivation, 4),
        points_to_title=points_to_title,
        points_to_top4=points_to_top4,
        points_to_top6=points_to_top6,
        points_above_relegation=points_above_relegation,
        long_unbeaten=long_unbeaten,
    )


def parse_standings_entries(payload_json: list) -> list[dict]:
    """
    Extract the flat list of team entries from a StandingsSnapshot.payload_json.
    API-Football returns: [{league: {standings: [[...entries...]]}}]
    """
    entries: list[dict] = []
    for item in payload_json or []:
        league = item.get("league", {}) if isinstance(item, dict) else {}
        standings = league.get("standings", [])
        for group in standings:
            if isinstance(group, list):
                entries.extend(group)
    return entries


def _compute_long_unbeaten(form_str: str) -> bool:
    """True if the last N consecutive results are all W or D."""
    recent = list((form_str or "").upper())
    if len(recent) < _LONG_UNBEATEN_GAMES:
        return False
    return all(r in ("W", "D") for r in recent[-_LONG_UNBEATEN_GAMES:])
