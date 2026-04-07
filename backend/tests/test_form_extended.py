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
