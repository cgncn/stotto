"""
Form score — core + extended signals.

Core:
  FormScore = Σ(metric_i * weight_i)
  weights = [1.00, 0.85, 0.72, 0.61, 0.52]  (most recent first)

Extended:
  - Away-specific form from standings home/away splits
  - xG proxy from shots_on_target (× 0.33) in statistics snapshots
  - Lucky / unlucky form flags based on xG vs actual goal differential
"""
from __future__ import annotations
from dataclasses import dataclass

FORM_WEIGHTS = [1.00, 0.85, 0.72, 0.61, 0.52]
WEIGHT_SUM = sum(FORM_WEIGHTS)

_XG_CONVERSION_FACTOR = 0.33   # shots_on_target → xG approximation

# ── Last-5 fixture performance ─────────────────────────────────────────────


@dataclass(frozen=True)
class Last5Metrics:
    goals_scored_avg: float    # normalised [0, 1]  (raw / 4, clamped)
    goals_conceded_avg: float  # normalised [0, 1]  (raw / 4, clamped)
    points_per_game: float     # normalised [0, 1]  (pts / 3)
    goal_diff_avg: float       # normalised [0, 1]  ((diff + 4) / 8)


_LAST5_NEUTRAL = Last5Metrics(0.5, 0.5, 0.5, 0.5)
_LAST5_WEIGHTS = FORM_WEIGHTS  # same decay schedule as form_score


def _last5_from_rows(fixtures: list, team_id: int) -> Last5Metrics:
    """Pure computation from Fixture-like rows — testable without a DB session.

    Accepts any objects with attributes:
        home_team_id, away_team_id, home_score, away_score, status, kickoff_at
    """
    recent = sorted(
        [
            f for f in fixtures
            if f.status == "FT"
            and (f.home_team_id == team_id or f.away_team_id == team_id)
        ],
        key=lambda f: f.kickoff_at,
        reverse=True,
    )[:5]

    if len(recent) < 2:
        return _LAST5_NEUTRAL

    weights = _LAST5_WEIGHTS[: len(recent)]
    w_total = sum(weights)

    scored = conceded = points = 0.0
    for w, f in zip(weights, recent):
        is_home = f.home_team_id == team_id
        gs = (f.home_score if is_home else f.away_score) or 0
        gc = (f.away_score if is_home else f.home_score) or 0
        gd = gs - gc
        pts = 3 if gd > 0 else (1 if gd == 0 else 0)
        scored += w * gs
        conceded += w * gc
        points += w * pts

    scored_avg = min(4.0, scored / w_total) / 4.0
    conceded_avg = min(4.0, conceded / w_total) / 4.0
    ppg = (points / w_total) / 3.0
    raw_diff = scored / w_total - conceded / w_total
    diff_norm = (max(-4.0, min(4.0, raw_diff)) + 4.0) / 8.0

    return Last5Metrics(
        goals_scored_avg=scored_avg,
        goals_conceded_avg=conceded_avg,
        points_per_game=ppg,
        goal_diff_avg=diff_norm,
    )


def compute_last5_from_fixtures(team_id: int, db) -> Last5Metrics:
    """Query last 5 finished fixtures for *team_id* (DB primary key) and return
    weighted performance metrics.  Falls back to neutral if data is sparse."""
    from sqlalchemy import or_
    from app.db import models

    fixtures = (
        db.query(models.Fixture)
        .filter(
            or_(
                models.Fixture.home_team_id == team_id,
                models.Fixture.away_team_id == team_id,
            ),
            models.Fixture.status == "FT",
        )
        .order_by(models.Fixture.kickoff_at.desc())
        .limit(5)
        .all()
    )
    return _last5_from_rows(fixtures, team_id)


_LUCKY_THRESHOLD = 0.4         # xg_luck > +0.4 per game = overperforming
_UNLUCKY_THRESHOLD = -0.4      # xg_luck < -0.4 per game = underperforming


def compute_form_score(recent_results: list[str | None]) -> float:
    """
    recent_results: list of up to 5 most recent results, most recent first.
    Each element: 'W', 'D', 'L', or None (unknown).
    Returns a normalized form score in [0, 1].
    """
    result_values = {"W": 1.0, "D": 0.5, "L": 0.0}
    score = 0.0
    effective_weight = 0.0

    for i, result in enumerate(recent_results[:5]):
        if result is None:
            continue
        w = FORM_WEIGHTS[i]
        score += result_values.get(result.upper(), 0.5) * w
        effective_weight += w

    if effective_weight == 0:
        return 0.5  # degrade to neutral when no data

    return score / effective_weight


def extract_form_string(standings_entry: dict | None) -> list[str | None]:
    """
    Parse API-Football form string (e.g. 'WDLWW') into a list of characters,
    most recent first.
    """
    if not standings_entry:
        return [None] * 5
    form_str = standings_entry.get("form") or ""
    chars = list(form_str.upper())
    chars.reverse()  # API returns oldest → newest; we want newest first
    result = chars[:5]
    while len(result) < 5:
        result.append(None)
    return result


def compute_away_form(standings_entry: dict | None) -> float:
    """
    Compute a team's away-only form score from the standings home/away split.

    API-Football standings entry has:
      entry["away"]["win"], entry["away"]["draw"], entry["away"]["lose"]

    Returns [0, 1]. Degrades to 0.4 (slightly below neutral) when no data.
    """
    if not standings_entry:
        return 0.4

    away = standings_entry.get("away") or {}
    wins = away.get("win", 0) or 0
    draws = away.get("draw", 0) or 0
    losses = away.get("lose", 0) or 0
    total = wins + draws + losses

    if total == 0:
        return 0.4

    return round((wins + 0.5 * draws) / total, 4)


def compute_xg_features(
    recent_statistics: list[dict],
    team_ext_id: int,
) -> dict:
    """
    Compute xG proxy and luck flags from the last N statistics snapshots.

    Each element of recent_statistics is a FixtureStatisticsSnapshot.payload_json
    paired with the actual goals scored by the team in that fixture:
        [{"stats": <payload_json>, "team_goals": int, "team_ext_id": int}, ...]

    Returns:
        xg_proxy   - mean xG estimate per game
        xg_luck    - mean (actual_goals - xg_per_game), positive = lucky
        lucky_form  - True if overperforming xG by threshold
        unlucky_form - True if underperforming xG by threshold
    """
    xg_per_game = []
    luck_per_game = []

    for entry in recent_statistics:
        stats_payload = entry.get("stats") or []
        team_goals = entry.get("team_goals")
        entry_team_id = entry.get("team_ext_id")

        if team_goals is None:
            continue

        shots_on_target = _extract_shots_on_target(stats_payload, entry_team_id)
        if shots_on_target is None:
            continue

        xg_estimate = shots_on_target * _XG_CONVERSION_FACTOR
        xg_per_game.append(xg_estimate)
        luck_per_game.append(team_goals - xg_estimate)

    if not xg_per_game:
        return {
            "xg_proxy": None,
            "xg_luck": None,
            "lucky_form": False,
            "unlucky_form": False,
        }

    xg_proxy = round(sum(xg_per_game) / len(xg_per_game), 3)
    xg_luck = round(sum(luck_per_game) / len(luck_per_game), 3)

    return {
        "xg_proxy": xg_proxy,
        "xg_luck": xg_luck,
        "lucky_form": xg_luck > _LUCKY_THRESHOLD,
        "unlucky_form": xg_luck < _UNLUCKY_THRESHOLD,
    }


def _extract_shots_on_target(stats_payload: list[dict], team_ext_id: int | None) -> float | None:
    """
    Parse API-Football fixture statistics payload to find shots on target for a team.

    Payload structure:
        [{"team": {"id": 529}, "statistics": [{"type": "Shots on Target", "value": 5}, ...]}, ...]
    """
    for team_block in stats_payload:
        team = team_block.get("team") or {}
        if team_ext_id is not None and team.get("id") != team_ext_id:
            continue
        for stat in team_block.get("statistics") or []:
            if stat.get("type") == "Shots on Target":
                val = stat.get("value")
                try:
                    return float(val) if val is not None else None
                except (TypeError, ValueError):
                    return None
    return None
