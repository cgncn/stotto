"""
Feature regression tests: same input → same output (deterministic).
"""
import pytest
from app.features.strength import compute_strength_score, extract_strength_features
from app.features.form import compute_form_score, extract_form_string
from app.features.draw import compute_draw_tendency, extract_draw_features, get_draw_rate
from app.features.lineup import compute_lineup_penalty, compute_lineup_continuity
from app.features.market import compute_market_support


# ── Strength ────────────────��────────────────────────────��─────────────────────

def test_strength_score_deterministic():
    score_a = compute_strength_score(2.0, 0.8, 0.7, 0.6, 0.5)
    score_b = compute_strength_score(2.0, 0.8, 0.7, 0.6, 0.5)
    assert score_a == score_b


def test_strength_score_range():
    score = compute_strength_score(2.0, 0.8, 0.7, 0.6, 0.5)
    assert 0.0 <= score <= 1.0


def test_strength_higher_ppg_yields_higher_score():
    low = compute_strength_score(0.5, 0.0, 0.3, 0.3, 0.3)
    high = compute_strength_score(2.8, 1.5, 0.8, 0.8, 0.8)
    assert high > low


def test_extract_strength_features_missing_returns_neutral():
    feats = extract_strength_features(None, is_home=True)
    assert feats["season_ppg"] == 0.5


def test_extract_strength_features_from_standings():
    standings = {
        "rank": 3,
        "points": 45,
        "all": {"played": 20, "win": 14, "draw": 3, "lose": 3,
                "goals": {"for": 50, "against": 10}},  # 2.5 goals/game → 0.625 attack_index
        "home": {"played": 10, "win": 8, "draw": 1, "lose": 1},
        "form": "WWWDW",
    }
    feats = extract_strength_features(standings, is_home=True)
    assert feats["attack_index"] > 0.5
    assert feats["defense_index"] > 0.5


# ── Form ───────────────────────────────────────────────────────────────────────

def test_form_score_all_wins():
    score = compute_form_score(["W", "W", "W", "W", "W"])
    assert abs(score - 1.0) < 1e-6


def test_form_score_all_losses():
    score = compute_form_score(["L", "L", "L", "L", "L"])
    assert abs(score - 0.0) < 1e-6


def test_form_score_no_data():
    score = compute_form_score([None, None, None])
    assert score == 0.5


def test_form_score_recent_weighs_more():
    # Recent win + old loss vs recent loss + old win
    win_recent = compute_form_score(["W", "L", None, None, None])
    loss_recent = compute_form_score(["L", "W", None, None, None])
    assert win_recent > loss_recent


def test_extract_form_string_parses_correctly():
    standings = {"form": "WDLWW"}  # oldest to newest
    chars = extract_form_string(standings)
    assert chars[0] == "W"  # most recent = last char reversed
    assert len(chars) == 5


# ── Draw ───────────────────────────────────────────────────────────────────────

def test_draw_tendency_range():
    score = compute_draw_tendency(0.6, 0.7, 0.5, 0.3, 0.4)
    assert 0.0 <= score <= 1.0


def test_draw_tendency_balanced_teams_higher():
    balanced = compute_draw_tendency(0.9, 0.8, 0.7, 0.35, 0.7)
    unbalanced = compute_draw_tendency(0.1, 0.2, 0.3, 0.2, 0.1)
    assert balanced > unbalanced


def test_get_draw_rate_no_data():
    assert get_draw_rate(None) == pytest.approx(0.27)


def test_get_draw_rate_from_standings():
    standings = {"all": {"played": 20, "draw": 8}}
    assert get_draw_rate(standings) == pytest.approx(0.4)


# ── Lineup ───────────────────────────────��─────────────────────────────────────

def test_lineup_penalty_empty_injuries():
    penalty = compute_lineup_penalty([], team_id=100)
    assert penalty == 0.0


def test_lineup_penalty_goalkeeper_injury():
    injuries = [
        {
            "team": {"id": 100},
            "player": {"type": "Goalkeeper"},
            "type": "injured",
        }
    ]
    penalty = compute_lineup_penalty(injuries, team_id=100)
    assert penalty > 0.0


def test_lineup_continuity_no_lineup():
    assert compute_lineup_continuity([], team_id=100) == 0.0


def test_lineup_continuity_full_lineup():
    lineup = [
        {
            "team": {"id": 100},
            "startXI": [{"player": {"id": i}} for i in range(11)],
        }
    ]
    assert compute_lineup_continuity(lineup, team_id=100) == 1.0


# ── Market ─────────────────────────────────────────────────────────────────────

def test_market_support_no_odds():
    result = compute_market_support(None, None, None)
    assert result["implied_p1"] == pytest.approx(0.33)


def test_market_support_sums_to_one():
    result = compute_market_support(2.0, 3.5, 4.0)
    total = result["implied_p1"] + result["implied_px"] + result["implied_p2"]
    assert abs(total - 1.0) < 1e-6


def test_market_support_heavy_favourite():
    result = compute_market_support(1.2, 6.0, 9.0)
    assert result["implied_p1"] > 0.7


def test_market_dispersion_balanced():
    result = compute_market_support(2.0, 2.0, 2.0)
    assert result["bookmaker_dispersion"] == pytest.approx(1.0, abs=0.01)
