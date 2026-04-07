"""Tests for context feature computation (rest days, international break, congestion, derby)."""
import pytest
from datetime import datetime, timedelta
from app.features.context import compute_context_features, _INTL_BREAK_THRESHOLD_DAYS


KICKOFF = datetime(2026, 4, 12, 15, 0)


def _ctx(
    *,
    home_last=None,
    away_last=None,
    home_upcoming=0,
    away_upcoming=0,
    is_derby=False,
    admin_flags=None,
):
    return compute_context_features(
        kickoff_at=KICKOFF,
        home_last_kickoff=home_last,
        away_last_kickoff=away_last,
        home_upcoming_count=home_upcoming,
        away_upcoming_count=away_upcoming,
        is_derby=is_derby,
        admin_flags=admin_flags or {},
    )


def test_rest_days_computed_correctly():
    last = KICKOFF - timedelta(days=4)
    ctx = _ctx(home_last=last)
    assert ctx.rest_days_home == pytest.approx(4.0, abs=0.2)


def test_rest_days_defaults_to_7_when_unknown():
    ctx = _ctx()
    assert ctx.rest_days_home == pytest.approx(7.0)
    assert ctx.rest_days_away == pytest.approx(7.0)


def test_international_break_detected():
    last = KICKOFF - timedelta(days=15)
    ctx = _ctx(home_last=last)
    assert ctx.post_intl_break_home is True


def test_no_international_break_below_threshold():
    last = KICKOFF - timedelta(days=10)
    ctx = _ctx(home_last=last)
    assert ctx.post_intl_break_home is False


def test_congestion_risk():
    ctx = _ctx(away_upcoming=2)
    assert ctx.congestion_risk_away is True


def test_no_congestion_below_threshold():
    ctx = _ctx(away_upcoming=1)
    assert ctx.congestion_risk_away is False


def test_derby_flag():
    ctx = _ctx(is_derby=True)
    assert ctx.is_derby is True
    assert ctx.derby_confidence_suppressor == pytest.approx(0.75)


def test_non_derby():
    ctx = _ctx(is_derby=False)
    assert ctx.derby_confidence_suppressor == pytest.approx(1.0)


def test_thursday_european_away_from_admin_flags():
    ctx = _ctx(admin_flags={"thursday_european_away": True})
    assert ctx.thursday_european_away is True


def test_thursday_european_away_defaults_false():
    ctx = _ctx()
    assert ctx.thursday_european_away is False
