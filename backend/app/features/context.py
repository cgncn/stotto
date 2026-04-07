"""
Contextual match features.

Covers: real rest days, international break flag, fixture congestion risk,
Thursday European effect (from admin flags), and derby detection.

All DB queries are passed in as pre-computed values so the module stays
pure-Python testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

_INTL_BREAK_THRESHOLD_DAYS = 14   # gap ≥ 14 days = post-international-break
_CONGESTION_WINDOW_DAYS = 7        # upcoming matches within N days
_CONGESTION_MIN_FIXTURES = 2       # N or more additional fixtures = congestion risk


@dataclass
class ContextFeatures:
    rest_days_home: float
    rest_days_away: float
    post_intl_break_home: bool
    post_intl_break_away: bool
    congestion_risk_home: bool
    congestion_risk_away: bool
    is_derby: bool
    derby_confidence_suppressor: float  # 0.75 if derby, else 1.0
    thursday_european_away: bool        # from admin_flags


def compute_context_features(
    *,
    kickoff_at: datetime,
    home_last_kickoff: datetime | None,
    away_last_kickoff: datetime | None,
    home_upcoming_count: int,           # fixtures for home team in next 7 days (excl. current)
    away_upcoming_count: int,           # fixtures for away team in next 7 days (excl. current)
    is_derby: bool,
    admin_flags: dict,
) -> ContextFeatures:
    """
    Args:
        kickoff_at: current fixture kickoff time
        home_last_kickoff: most recent completed fixture kickoff for home team (None if unknown)
        away_last_kickoff: most recent completed fixture kickoff for away team (None if unknown)
        home_upcoming_count: count of upcoming fixtures for home team in next 7 days
        away_upcoming_count: count of upcoming fixtures for away team in next 7 days
        is_derby: True if this is a known rivalry (from rivalries.py or admin toggle)
        admin_flags: dict from WeeklyPoolMatch.admin_flags
    """
    rest_days_home = _rest_days(kickoff_at, home_last_kickoff)
    rest_days_away = _rest_days(kickoff_at, away_last_kickoff)

    post_intl_break_home = rest_days_home >= _INTL_BREAK_THRESHOLD_DAYS
    post_intl_break_away = rest_days_away >= _INTL_BREAK_THRESHOLD_DAYS

    congestion_risk_home = home_upcoming_count >= _CONGESTION_MIN_FIXTURES
    congestion_risk_away = away_upcoming_count >= _CONGESTION_MIN_FIXTURES

    derby_confidence_suppressor = 0.75 if is_derby else 1.0

    thursday_european_away = bool(admin_flags.get("thursday_european_away", False))

    return ContextFeatures(
        rest_days_home=rest_days_home,
        rest_days_away=rest_days_away,
        post_intl_break_home=post_intl_break_home,
        post_intl_break_away=post_intl_break_away,
        congestion_risk_home=congestion_risk_home,
        congestion_risk_away=congestion_risk_away,
        is_derby=is_derby,
        derby_confidence_suppressor=derby_confidence_suppressor,
        thursday_european_away=thursday_european_away,
    )


def _rest_days(kickoff_at: datetime, last_kickoff: datetime | None) -> float:
    """Days since last match. Returns 7.0 (neutral) when last fixture is unknown."""
    if last_kickoff is None:
        return 7.0
    # Strip timezone info for naive comparison if needed
    ko = kickoff_at.replace(tzinfo=None) if kickoff_at.tzinfo else kickoff_at
    lk = last_kickoff.replace(tzinfo=None) if last_kickoff.tzinfo else last_kickoff
    delta = (ko - lk).total_seconds() / 86400
    return max(0.0, round(delta, 1))
