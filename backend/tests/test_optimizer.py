"""
Optimizer tests: column limit compliance, scenario validity.
"""
import pytest
from app.optimizer.engine import (
    MatchInput,
    _optimize,
    _count_columns,
    _assign_coverage_pick,
    SCENARIO_PARAMS,
)


def _make_match(seq: int, coverage_need: float, criticality: float = 50.0) -> MatchInput:
    return MatchInput(
        pool_match_id=seq,
        sequence_no=seq,
        p1=0.45,
        px=0.30,
        p2=0.25,
        primary_pick="1",
        secondary_pick="X",
        confidence_score=60.0,
        coverage_need_score=coverage_need,
        coverage_type="single",
        coverage_pick="1",
        coupon_criticality_score=criticality,
    )


def _make_15_matches(coverage_needs: list[float]) -> list[MatchInput]:
    return [_make_match(i + 1, cn) for i, cn in enumerate(coverage_needs)]


def test_column_limit_safe():
    matches = _make_15_matches([80] * 5 + [55] * 5 + [25] * 5)
    params = SCENARIO_PARAMS["safe"]
    picks = _optimize(matches, params)
    cols = _count_columns(picks)
    assert cols <= params["max_columns"], f"Column count {cols} exceeds limit {params['max_columns']}"


def test_column_limit_balanced():
    matches = _make_15_matches([85] * 8 + [50] * 4 + [20] * 3)
    params = SCENARIO_PARAMS["balanced"]
    picks = _optimize(matches, params)
    cols = _count_columns(picks)
    assert cols <= params["max_columns"]


def test_column_limit_aggressive():
    matches = _make_15_matches([90] * 15)
    params = SCENARIO_PARAMS["aggressive"]
    picks = _optimize(matches, params)
    cols = _count_columns(picks)
    assert cols <= params["max_columns"]


def test_all_15_matches_covered():
    matches = _make_15_matches([50.0] * 15)
    params = SCENARIO_PARAMS["balanced"]
    picks = _optimize(matches, params)
    assert len(picks) == 15


def test_sequence_numbers_intact():
    matches = _make_15_matches([60.0] * 15)
    params = SCENARIO_PARAMS["balanced"]
    picks = _optimize(matches, params)
    seqs = [p.sequence_no for p in picks]
    assert seqs == sorted(seqs)


def test_low_coverage_need_gives_single():
    m = _make_match(1, coverage_need=10.0)
    params = SCENARIO_PARAMS["safe"]  # threshold 35
    picks = _optimize([m], params)
    assert picks[0].coverage_type == "single"


def test_high_coverage_need_gives_double_or_triple():
    m = _make_match(1, coverage_need=80.0)
    params = SCENARIO_PARAMS["balanced"]
    picks = _optimize([m], params)
    assert picks[0].coverage_type in ("double", "triple")


def test_assign_coverage_pick_single():
    m = _make_match(1, 20.0)
    assert _assign_coverage_pick(m, "single") == "1"


def test_assign_coverage_pick_double_1x():
    m = _make_match(1, 50.0)
    result = _assign_coverage_pick(m, "double")
    assert result == "1X"


def test_assign_coverage_pick_triple():
    m = _make_match(1, 80.0)
    assert _assign_coverage_pick(m, "triple") == "1X2"


def test_max_triples_respected():
    matches = _make_15_matches([90.0] * 15)
    params = SCENARIO_PARAMS["safe"].copy()  # max_triples = 2
    picks = _optimize(matches, params)
    triple_count = sum(1 for p in picks if p.coverage_type == "triple")
    assert triple_count <= params["max_triples"]


def test_max_doubles_respected():
    matches = _make_15_matches([60.0] * 15)
    params = SCENARIO_PARAMS["safe"].copy()  # max_doubles = 10
    picks = _optimize(matches, params)
    double_count = sum(1 for p in picks if p.coverage_type == "double")
    assert double_count <= params["max_doubles"]
