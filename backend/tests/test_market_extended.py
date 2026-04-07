"""Tests for extended market features: odds movement, sharp money signal."""
import pytest
from app.features.market import compute_odds_movement


def test_no_movement_when_single_snapshot():
    snaps = [{"home_odds": 2.0, "draw_odds": 3.4, "away_odds": 3.8}]
    result = compute_odds_movement(snaps)
    assert result["odds_delta_home"] == pytest.approx(0.0)
    assert result["sharp_money_signal"] == pytest.approx(0.0)
    assert result["opening_odds_home"] == pytest.approx(2.0)


def test_home_odds_drifted_sharp_toward_away():
    snaps = [
        {"home_odds": 2.0, "draw_odds": 3.4, "away_odds": 3.8},  # opening
        {"home_odds": 2.5, "draw_odds": 3.4, "away_odds": 3.2},  # current: home drifted +0.5
    ]
    result = compute_odds_movement(snaps)
    assert result["odds_delta_home"] == pytest.approx(0.5, abs=0.01)
    assert result["sharp_money_signal"] == pytest.approx(1.0)  # clamped at 1.0 (0.5/0.5)


def test_home_odds_shortened_sharp_toward_home():
    snaps = [
        {"home_odds": 2.4, "draw_odds": 3.4, "away_odds": 3.0},  # opening
        {"home_odds": 1.9, "draw_odds": 3.4, "away_odds": 3.5},  # current: home shortened -0.5
    ]
    result = compute_odds_movement(snaps)
    assert result["odds_delta_home"] == pytest.approx(-0.5, abs=0.01)
    assert result["sharp_money_signal"] == pytest.approx(-1.0)  # clamped at -1.0


def test_partial_movement_within_range():
    snaps = [
        {"home_odds": 2.0, "draw_odds": 3.4, "away_odds": 3.8},
        {"home_odds": 2.25, "draw_odds": 3.4, "away_odds": 3.5},  # +0.25 drift
    ]
    result = compute_odds_movement(snaps)
    assert result["sharp_money_signal"] == pytest.approx(0.5, abs=0.01)


def test_empty_snapshots_returns_neutral():
    result = compute_odds_movement([])
    assert result["odds_delta_home"] == pytest.approx(0.0)
    assert result["sharp_money_signal"] == pytest.approx(0.0)
    assert result["opening_odds_home"] is None


def test_null_odds_snapshots_skipped():
    snaps = [
        {"home_odds": None, "draw_odds": 3.4, "away_odds": 3.8},  # invalid
        {"home_odds": 2.0, "draw_odds": 3.4, "away_odds": 3.8},   # valid opening
        {"home_odds": 2.3, "draw_odds": 3.4, "away_odds": 3.6},   # valid current
    ]
    result = compute_odds_movement(snaps)
    assert result["opening_odds_home"] == pytest.approx(2.0)
    assert result["odds_delta_home"] == pytest.approx(0.3, abs=0.01)


def test_opening_odds_preserved():
    snaps = [
        {"home_odds": 1.8, "draw_odds": 3.5, "away_odds": 4.2},
        {"home_odds": 2.1, "draw_odds": 3.3, "away_odds": 3.9},
    ]
    result = compute_odds_movement(snaps)
    assert result["opening_odds_home"] == pytest.approx(1.8)
    assert result["opening_odds_draw"] == pytest.approx(3.5)
    assert result["opening_odds_away"] == pytest.approx(4.2)
