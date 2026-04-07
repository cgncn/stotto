"""Tests for H2H feature computation."""
import pytest
from app.features.h2h import compute_h2h_features, _NEUTRAL


HOME_EXT = 529  # simulated home team ID
AWAY_EXT = 530  # simulated away team ID


def _make_fixture(home_id, away_id, home_goals, away_goals, venue=None):
    return {
        "fixture": {"venue": {"name": venue or "Camp Nou"}},
        "teams": {"home": {"id": home_id}, "away": {"id": away_id}},
        "goals": {"home": home_goals, "away": away_goals},
    }


def test_empty_payload_returns_neutral():
    result = compute_h2h_features([], HOME_EXT, AWAY_EXT, "Camp Nou")
    assert result.h2h_home_win_rate == pytest.approx(0.33)
    assert result.h2h_sample_size == 0
    assert result.h2h_bogey_flag is False


def test_home_dominant():
    fixtures = [_make_fixture(HOME_EXT, AWAY_EXT, 2, 0) for _ in range(5)]
    result = compute_h2h_features(fixtures, HOME_EXT, AWAY_EXT, "Camp Nou")
    assert result.h2h_home_win_rate == pytest.approx(1.0)
    assert result.h2h_away_win_rate == pytest.approx(0.0)
    assert result.h2h_bogey_flag is False


def test_bogey_team_flag():
    # Away team wins 6 out of 8 meetings
    fixtures = (
        [_make_fixture(HOME_EXT, AWAY_EXT, 0, 2) for _ in range(6)] +
        [_make_fixture(HOME_EXT, AWAY_EXT, 1, 0) for _ in range(2)]
    )
    result = compute_h2h_features(fixtures, HOME_EXT, AWAY_EXT, "Camp Nou")
    assert result.h2h_bogey_flag is True
    assert result.h2h_away_win_rate > 0.55


def test_bogey_flag_requires_min_sample():
    # Away wins 3/3 but sample < 4 → no bogey flag
    fixtures = [_make_fixture(HOME_EXT, AWAY_EXT, 0, 1) for _ in range(3)]
    result = compute_h2h_features(fixtures, HOME_EXT, AWAY_EXT, "Camp Nou")
    assert result.h2h_bogey_flag is False


def test_team_was_away_in_past_fixture():
    # Same matchup but current home team was AWAY in the past fixture and won
    # Fixture stored as: home=AWAY_EXT, away=HOME_EXT, home_goals=0, away_goals=1
    fixtures = [_make_fixture(AWAY_EXT, HOME_EXT, 0, 1)]  # HOME_EXT won as away
    result = compute_h2h_features(fixtures, HOME_EXT, AWAY_EXT, "Camp Nou")
    assert result.h2h_home_win_rate == pytest.approx(1.0)


def test_venue_specific_rate():
    fixtures = [
        _make_fixture(HOME_EXT, AWAY_EXT, 2, 0, venue="Camp Nou"),  # home win at venue
        _make_fixture(HOME_EXT, AWAY_EXT, 0, 1, venue="Bernabéu"),  # away win at other venue
        _make_fixture(HOME_EXT, AWAY_EXT, 2, 0, venue="Camp Nou"),  # home win at venue
    ]
    result = compute_h2h_features(fixtures, HOME_EXT, AWAY_EXT, "Camp Nou")
    # Venue filter: 2/2 home wins at Camp Nou
    assert result.h2h_venue_home_win_rate == pytest.approx(1.0)
    # Overall: 2/3 home wins (rounded to 4dp = 0.6667)
    assert result.h2h_home_win_rate == pytest.approx(2 / 3, abs=0.001)


def test_draw_rate():
    fixtures = [
        _make_fixture(HOME_EXT, AWAY_EXT, 1, 1),
        _make_fixture(HOME_EXT, AWAY_EXT, 1, 1),
        _make_fixture(HOME_EXT, AWAY_EXT, 2, 0),
    ]
    result = compute_h2h_features(fixtures, HOME_EXT, AWAY_EXT, None)
    assert result.h2h_draw_rate == pytest.approx(2 / 3, abs=0.001)


def test_missing_goals_skipped():
    fixtures = [
        {"fixture": {"venue": {"name": "X"}}, "teams": {"home": {"id": HOME_EXT}, "away": {"id": AWAY_EXT}}, "goals": {"home": None, "away": None}},
        _make_fixture(HOME_EXT, AWAY_EXT, 1, 0),
    ]
    result = compute_h2h_features(fixtures, HOME_EXT, AWAY_EXT, None)
    assert result.h2h_sample_size == 1
