"""Tests for motivation / objective scoring."""
import pytest
from app.features.motivation import compute_motivation_features, parse_standings_entries, _DEFAULT


def _entry(team_id, rank, points, form="", played=30):
    return {
        "rank": rank,
        "team": {"id": team_id},
        "points": points,
        "form": form,
        "all": {"played": played, "win": 0, "draw": 0, "lose": 0},
    }


def _league(entries):
    return [{"league": {"standings": [entries]}}]


def test_empty_input_returns_default():
    result = compute_motivation_features(None, [])
    assert result.motivation == pytest.approx(_DEFAULT.motivation)


def test_relegation_zone_high_urgency():
    entries = [_entry(1, i, (20 - i) * 3) for i in range(1, 21)]
    # Team at rank 20 (bottom, in relegation zone)
    team_entry = entries[19]
    result = compute_motivation_features(team_entry, entries)
    assert result.motivation > 0.5
    assert result.points_above_relegation <= 3


def test_title_race_high_urgency():
    entries = [_entry(i, i, (20 - i) * 3) for i in range(1, 21)]
    # Team at rank 2, 3 pts from leader — motivation raises above default 0.3
    entries[0] = _entry(1, 1, 60)
    entries[1] = _entry(2, 2, 57)
    entries[2] = _entry(3, 3, 50)
    result = compute_motivation_features(entries[1], entries)
    assert result.motivation > _DEFAULT.motivation
    assert result.points_to_title <= 6


def test_mid_table_team_gets_default():
    # Team at rank 10, safe from relegation, far from top 6
    entries = [_entry(i, i, (21 - i) * 3) for i in range(1, 21)]
    result = compute_motivation_features(entries[9], entries)
    assert result.motivation == pytest.approx(_DEFAULT.motivation)


def test_long_unbeaten_detected():
    entries = [_entry(1, 5, 30, form="WWWWWWDD")]
    result = compute_motivation_features(entries[0], entries)
    assert result.long_unbeaten is True


def test_not_long_unbeaten_with_loss():
    result = compute_motivation_features(
        _entry(1, 5, 30, form="WWWLWW"), []
    )
    assert result.long_unbeaten is False


def test_parse_standings_entries():
    entries = [_entry(1, 1, 60), _entry(2, 2, 55)]
    payload = _league(entries)
    result = parse_standings_entries(payload)
    assert len(result) == 2
    assert result[0]["team"]["id"] == 1
