"""
Scoring engine snapshot tests: fixed features → deterministic P1/PX/P2.
"""
import pytest
from app.scoring.engine import _softmax, _choose_double


def test_softmax_sums_to_one():
    p1, px, p2 = _softmax([0.6, 0.4, 0.3])
    assert abs(p1 + px + p2 - 1.0) < 1e-6


def test_softmax_preserves_ranking():
    p1, px, p2 = _softmax([0.8, 0.5, 0.3])
    assert p1 > px > p2


def test_softmax_deterministic():
    a = _softmax([0.5, 0.3, 0.2])
    b = _softmax([0.5, 0.3, 0.2])
    assert a == b


def test_softmax_equal_inputs():
    p1, px, p2 = _softmax([0.5, 0.5, 0.5])
    assert abs(p1 - 1 / 3) < 1e-6
    assert abs(px - 1 / 3) < 1e-6
    assert abs(p2 - 1 / 3) < 1e-6


# ── Double direction ────────────────────────────────────────────────────────────

def test_choose_double_1x():
    assert _choose_double("1", "X", px=0.3) == "1X"


def test_choose_double_x2():
    assert _choose_double("2", "X", px=0.3) == "X2"


def test_choose_double_12_low_draw_risk():
    result = _choose_double("1", "2", px=0.15)
    assert result == "12"


def test_choose_double_12_high_draw_risk_picks_x_protection():
    result = _choose_double("1", "2", px=0.30)
    assert result == "1X"


def test_choose_double_2_primary_high_draw():
    result = _choose_double("2", "1", px=0.30)
    assert result == "X2"
