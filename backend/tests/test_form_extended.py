"""Tests for extended form features: away form, xG proxy, lucky/unlucky flags."""
import pytest
from app.features.form import compute_away_form, compute_xg_features


# ── Away form ──────────────────────────────────────────────────────────────────

def test_away_form_all_wins():
    entry = {"away": {"win": 10, "draw": 0, "lose": 0}}
    assert compute_away_form(entry) == pytest.approx(1.0)


def test_away_form_all_losses():
    entry = {"away": {"win": 0, "draw": 0, "lose": 10}}
    assert compute_away_form(entry) == pytest.approx(0.0)


def test_away_form_mixed():
    entry = {"away": {"win": 4, "draw": 2, "lose": 4}}
    expected = (4 + 0.5 * 2) / 10
    assert compute_away_form(entry) == pytest.approx(expected)


def test_away_form_no_games():
    entry = {"away": {"win": 0, "draw": 0, "lose": 0}}
    assert compute_away_form(entry) == pytest.approx(0.4)


def test_away_form_none_entry():
    assert compute_away_form(None) == pytest.approx(0.4)


# ── xG proxy ──────────────────────────────────────────────────────────────────

def _stats_entry(team_ext_id, shots_on_target, team_goals):
    return {
        "stats": [
            {
                "team": {"id": team_ext_id},
                "statistics": [{"type": "Shots on Target", "value": shots_on_target}],
            }
        ],
        "team_goals": team_goals,
        "team_ext_id": team_ext_id,
    }


TEAM_ID = 529


def test_xg_proxy_computed():
    entries = [_stats_entry(TEAM_ID, 6, 2), _stats_entry(TEAM_ID, 4, 1)]
    result = compute_xg_features(entries, TEAM_ID)
    expected_xg = (6 * 0.33 + 4 * 0.33) / 2
    assert result["xg_proxy"] == pytest.approx(expected_xg, abs=0.01)


def test_lucky_form_flag():
    # Scoring 2 goals per game on only 1 shot on target (xG ~0.33) = overperforming
    entries = [_stats_entry(TEAM_ID, 1, 2) for _ in range(5)]
    result = compute_xg_features(entries, TEAM_ID)
    assert result["lucky_form"] is True
    assert result["unlucky_form"] is False


def test_unlucky_form_flag():
    # 0 goals per game on 5 shots on target (xG ~1.65) = underperforming
    entries = [_stats_entry(TEAM_ID, 5, 0) for _ in range(5)]
    result = compute_xg_features(entries, TEAM_ID)
    assert result["unlucky_form"] is True
    assert result["lucky_form"] is False


def test_empty_stats_returns_none():
    result = compute_xg_features([], TEAM_ID)
    assert result["xg_proxy"] is None
    assert result["lucky_form"] is False
    assert result["unlucky_form"] is False


def test_missing_shots_on_target_skipped():
    # Entry with no matching stat type → no data
    entry = {
        "stats": [{"team": {"id": TEAM_ID}, "statistics": [{"type": "Total Shots", "value": 10}]}],
        "team_goals": 2,
        "team_ext_id": TEAM_ID,
    }
    result = compute_xg_features([entry], TEAM_ID)
    assert result["xg_proxy"] is None


# ── Last5Metrics tests ──────────────────────────────────────────────────────

from types import SimpleNamespace
from datetime import datetime
from app.features.form import _last5_from_rows, Last5Metrics
import pytest


def _fixture(home_id, away_id, home_score, away_score, day):
    return SimpleNamespace(
        home_team_id=home_id,
        away_team_id=away_id,
        home_score=home_score,
        away_score=away_score,
        status="FT",
        kickoff_at=datetime(2026, 1, day),
    )


def test_last5_all_wins_2_0():
    """5 home 2-0 wins: scored=0.5, conceded=0.0, ppg=1.0, diff=0.75"""
    rows = [_fixture(1, 2, 2, 0, i) for i in range(1, 6)]
    m = _last5_from_rows(rows, team_id=1)
    assert m.goals_scored_avg == pytest.approx(0.5)      # 2/4
    assert m.goals_conceded_avg == pytest.approx(0.0)
    assert m.points_per_game == pytest.approx(1.0)
    assert m.goal_diff_avg == pytest.approx(0.75)         # (2+4)/8


def test_last5_all_losses_0_3():
    """5 away 0-3 losses: scored=0.0, conceded=0.75, ppg=0.0, diff=0.125"""
    rows = [_fixture(2, 1, 3, 0, i) for i in range(1, 6)]
    m = _last5_from_rows(rows, team_id=1)
    assert m.goals_scored_avg == pytest.approx(0.0)
    assert m.goals_conceded_avg == pytest.approx(0.75)    # 3/4
    assert m.points_per_game == pytest.approx(0.0)
    assert m.goal_diff_avg == pytest.approx(0.125)        # (-3+4)/8


def test_last5_neutral_on_empty():
    """No fixtures → all 0.5 neutral"""
    m = _last5_from_rows([], team_id=1)
    assert m == Last5Metrics(0.5, 0.5, 0.5, 0.5)


def test_last5_neutral_on_one_row():
    """Only 1 fixture (< 2 minimum) → all 0.5 neutral"""
    rows = [_fixture(1, 2, 1, 1, 1)]
    m = _last5_from_rows(rows, team_id=1)
    assert m == Last5Metrics(0.5, 0.5, 0.5, 0.5)


def test_last5_uses_only_ft_fixtures():
    """NS fixtures are ignored even if they pass the team_id filter"""
    ft_row = _fixture(1, 2, 2, 0, 3)
    ns_row = SimpleNamespace(
        home_team_id=1, away_team_id=2,
        home_score=None, away_score=None,
        status="NS", kickoff_at=datetime(2026, 1, 5),
    )
    rows = [ft_row, ft_row, ns_row, ns_row, ns_row]
    m = _last5_from_rows(rows, team_id=1)
    # Only 2 FT rows → still enough, but NS should not contribute
    assert m.goals_scored_avg == pytest.approx(0.5)


def test_last5_caps_goals_at_4():
    """6-goal games clamp to 4 before normalising"""
    rows = [_fixture(1, 2, 6, 6, i) for i in range(1, 6)]
    m = _last5_from_rows(rows, team_id=1)
    assert m.goals_scored_avg == pytest.approx(1.0)   # min(6,4)/4
    assert m.goals_conceded_avg == pytest.approx(1.0)
