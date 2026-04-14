"""
Coupon optimizer (§10).
Produces safe / balanced / aggressive scenarios from the 15 match scores.

Objective ≈ Max(ExpectedCoverageScore - α*ColumnCost - β*OverHedgingPenalty + γ*CriticalMatchProtection)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import NamedTuple

from sqlalchemy.orm import Session

from app.db import models

logger = logging.getLogger(__name__)

OPTIMIZER_VERSION = "v1"

COLUMN_COST = {"single": 1, "double": 2, "triple": 3}

# Objective weights per scenario
SCENARIO_PARAMS = {
    "safe": {
        "max_columns": 96,  # 2^7 * 3/4 reasonable cap
        "max_doubles": 10,
        "max_triples": 2,
        "alpha": 0.005,   # column cost penalty
        "beta": 0.02,     # over-hedging penalty
        "gamma": 0.10,    # critical match protection reward
        "upgrade_threshold": 35.0,  # coverage_need threshold to upgrade to double
        "triple_threshold": 70.0,
    },
    "balanced": {
        "max_columns": 192,
        "max_doubles": 8,
        "max_triples": 3,
        "alpha": 0.003,
        "beta": 0.015,
        "gamma": 0.12,
        "upgrade_threshold": 45.0,
        "triple_threshold": 68.0,
    },
    "aggressive": {
        "max_columns": 512,
        "max_doubles": 7,
        "max_triples": 5,
        "alpha": 0.001,
        "beta": 0.01,
        "gamma": 0.15,
        "upgrade_threshold": 55.0,
        "triple_threshold": 65.0,
    },
}


@dataclass
class MatchInput:
    pool_match_id: int
    sequence_no: int
    p1: float
    px: float
    p2: float
    primary_pick: str
    secondary_pick: str
    confidence_score: float
    coverage_need_score: float
    coverage_type: str          # single/double/triple (from scoring engine)
    coverage_pick: str          # 1X, X2, 12, 1, X, 2, 1X2
    coupon_criticality_score: float


@dataclass
class PickDecision:
    pool_match_id: int
    sequence_no: int
    coverage_pick: str
    coverage_type: str


def run_optimizer(db: Session, pool: models.WeeklyPool) -> None:
    """Generate 3 coupon scenarios for the pool."""
    logger.info("Optimizer running for pool %d", pool.id)

    match_inputs = _collect_inputs(db, pool)
    if not match_inputs:
        logger.warning("No scored matches for pool %d — skipping optimizer", pool.id)
        return

    for scenario_name, params in SCENARIO_PARAMS.items():
        picks = _optimize(match_inputs, params)
        total_columns = _count_columns(picks)
        coverage_score = _expected_coverage_score(match_inputs, picks)

        scenario = models.CouponScenario(
            weekly_pool_id=pool.id,
            scenario_type=getattr(models.ScenarioType, scenario_name).value,
            risk_profile=models.RiskProfile.medium.value,
            max_columns=params["max_columns"],
            max_doubles=params["max_doubles"],
            max_triples=params["max_triples"],
            picks_json=[
                {
                    "pool_match_id": p.pool_match_id,
                    "sequence_no": p.sequence_no,
                    "coverage_pick": p.coverage_pick,
                    "coverage_type": p.coverage_type,
                }
                for p in picks
            ],
            total_columns=total_columns,
            expected_coverage_score=coverage_score,
            optimizer_version=OPTIMIZER_VERSION,
        )
        db.add(scenario)

    db.flush()
    logger.info("Optimizer complete for pool %d", pool.id)


def run_optimizer_custom(
    db: Session,
    pool: models.WeeklyPool,
    max_columns: int,
    max_doubles: int,
    max_triples: int,
    risk_profile: str = "medium",
) -> list[dict]:
    """Run optimizer with custom constraints (used by POST /coupon-optimize)."""
    match_inputs = _collect_inputs(db, pool)
    if not match_inputs:
        return []

    # Map risk_profile to parameter alpha/beta/gamma
    base = SCENARIO_PARAMS["balanced"].copy()
    base["max_columns"] = max_columns
    base["max_doubles"] = max_doubles
    base["max_triples"] = max_triples

    if risk_profile == "low":
        base["upgrade_threshold"] = 30.0
        base["triple_threshold"] = 75.0
    elif risk_profile == "high":
        base["upgrade_threshold"] = 55.0
        base["triple_threshold"] = 62.0

    picks = _optimize(match_inputs, base)
    total_columns = _count_columns(picks)
    coverage_score = _expected_coverage_score(match_inputs, picks)

    scenario = models.CouponScenario(
        weekly_pool_id=pool.id,
        scenario_type=models.ScenarioType.balanced.value,
        risk_profile=getattr(models.RiskProfile, risk_profile, models.RiskProfile.medium).value,
        max_columns=max_columns,
        max_doubles=max_doubles,
        max_triples=max_triples,
        picks_json=[
            {
                "pool_match_id": p.pool_match_id,
                "sequence_no": p.sequence_no,
                "coverage_pick": p.coverage_pick,
                "coverage_type": p.coverage_type,
            }
            for p in picks
        ],
        total_columns=total_columns,
        expected_coverage_score=coverage_score,
        optimizer_version=OPTIMIZER_VERSION,
    )
    db.add(scenario)
    db.flush()

    return scenario.picks_json


# ── Core algorithm ─────────────────────────────────────────────────────────────

def _optimize(match_inputs: list[MatchInput], params: dict) -> list[PickDecision]:
    """
    Greedy heuristic optimizer (§10.3):
    1. Rank by (coverage_need + criticality).
    2. Mark low-risk as singles.
    3. Add secondary as double in medium-risk.
    4. Mark highest-risk as triples.
    5. Reduce until column limit is satisfied.
    6. Apply double direction logic.
    """
    max_cols = params["max_columns"]
    max_doubles = params["max_doubles"]
    max_triples = params["max_triples"]
    upgrade_threshold = params["upgrade_threshold"]
    triple_threshold = params["triple_threshold"]

    # Sort by combined risk score descending
    ranked = sorted(
        match_inputs,
        key=lambda m: m.coverage_need_score * 0.7 + m.coupon_criticality_score * 0.3,
        reverse=True,
    )

    decisions: dict[int, PickDecision] = {}

    # Initial assignment based on thresholds
    for m in ranked:
        if m.coverage_need_score >= triple_threshold:
            ctype = "triple"
        elif m.coverage_need_score >= upgrade_threshold:
            ctype = "double"
        else:
            ctype = "single"

        cpick = _assign_coverage_pick(m, ctype)
        decisions[m.pool_match_id] = PickDecision(
            pool_match_id=m.pool_match_id,
            sequence_no=m.sequence_no,
            coverage_pick=cpick,
            coverage_type=ctype,
        )

    # Enforce max_doubles and max_triples
    _cap_coverage_type(decisions, ranked, "triple", max_triples)
    _cap_coverage_type(decisions, ranked, "double", max_doubles)

    # Enforce max column count
    _reduce_to_column_limit(decisions, ranked, max_cols, match_inputs)

    # Return sorted by sequence_no
    return sorted(decisions.values(), key=lambda d: d.sequence_no)


def _assign_coverage_pick(m: MatchInput, ctype: str) -> str:
    """§10.4 double direction logic."""
    if ctype == "single":
        return m.primary_pick
    if ctype == "triple":
        return "1X2"

    # Double
    primary = m.primary_pick
    secondary = m.secondary_pick
    pair = frozenset([primary, secondary])

    if pair == frozenset(["1", "X"]):
        return "1X"
    if pair == frozenset(["2", "X"]):
        return "X2"
    if pair == frozenset(["1", "2"]):
        # Prefer X protection when draw probability is >= 25%
        if m.px >= 0.25:
            return "1X" if primary == "1" else "X2"
        return "12"

    return primary  # fallback to single if secondary undefined


def _cap_coverage_type(
    decisions: dict[int, PickDecision],
    ranked: list[MatchInput],
    ctype: str,
    limit: int,
) -> None:
    """Downgrade excess coverage decisions of `ctype` starting from lowest risk."""
    current = [d for d in decisions.values() if d.coverage_type == ctype]
    if len(current) <= limit:
        return

    downgrade_order = sorted(current, key=lambda d: _risk_score_for_id(ranked, d.pool_match_id))
    for d in downgrade_order[limit:]:
        m = _match_for_id(ranked, d.pool_match_id)
        new_type = "double" if ctype == "triple" else "single"
        d.coverage_type = new_type
        d.coverage_pick = _assign_coverage_pick(m, new_type)


def _reduce_to_column_limit(
    decisions: dict[int, PickDecision],
    ranked: list[MatchInput],
    max_cols: int,
    match_inputs: list[MatchInput],
) -> None:
    """Iteratively downgrade the lowest-risk high-coverage match until under column limit."""
    while _count_columns(list(decisions.values())) > max_cols:
        # Find best candidate to downgrade (lowest criticality, currently double or triple)
        candidates = [
            d for d in decisions.values()
            if d.coverage_type in ("double", "triple")
        ]
        if not candidates:
            break
        # Sort ascending by risk (lowest risk first = best to downgrade)
        candidates.sort(key=lambda d: _risk_score_for_id(ranked, d.pool_match_id))
        target = candidates[0]

        m = _match_for_id(ranked, target.pool_match_id)
        if target.coverage_type == "triple":
            target.coverage_type = "double"
            target.coverage_pick = _assign_coverage_pick(m, "double")
        else:
            target.coverage_type = "single"
            target.coverage_pick = _assign_coverage_pick(m, "single")


def _count_columns(picks: list[PickDecision]) -> int:
    total = 1
    for p in picks:
        total *= COLUMN_COST.get(p.coverage_type, 1)
    return total


def _expected_coverage_score(match_inputs: list[MatchInput], picks: list[PickDecision]) -> float:
    """
    Expected coverage = product of per-match coverage probability.
    Single: P(primary), Double: P(a)+P(b), Triple: 1.0
    """
    pick_map = {p.pool_match_id: p for p in picks}
    prob_map = {m.pool_match_id: {"1": m.p1, "X": m.px, "2": m.p2} for m in match_inputs}

    total = 1.0
    for pm_id, decision in pick_map.items():
        probs = prob_map.get(pm_id, {"1": 0.33, "X": 0.33, "2": 0.33})
        covered_prob = sum(probs.get(c, 0.0) for c in decision.coverage_pick if c in ("1", "X", "2"))
        total *= covered_prob

    return round(total * 100.0, 2)


def _risk_score_for_id(ranked: list[MatchInput], pm_id: int) -> float:
    m = _match_for_id(ranked, pm_id)
    return m.coverage_need_score * 0.7 + m.coupon_criticality_score * 0.3 if m else 0.0


def _match_for_id(ranked: list[MatchInput], pm_id: int) -> MatchInput | None:
    for m in ranked:
        if m.pool_match_id == pm_id:
            return m
    return None


def _collect_inputs(db: Session, pool: models.WeeklyPool) -> list[MatchInput]:
    inputs = []
    for pm in pool.matches:
        score = (
            db.query(models.MatchModelScore)
            .filter_by(weekly_pool_match_id=pm.id)
            .order_by(models.MatchModelScore.created_at.desc())
            .first()
        )
        if not score:
            continue
        inputs.append(MatchInput(
            pool_match_id=pm.id,
            sequence_no=pm.sequence_no,
            p1=score.p1,
            px=score.px,
            p2=score.p2,
            primary_pick=score.primary_pick,
            secondary_pick=score.secondary_pick or score.primary_pick,
            confidence_score=score.confidence_score or 50.0,
            coverage_need_score=score.coverage_need_score or 50.0,
            coverage_type=score.coverage_type.value if score.coverage_type else "single",
            coverage_pick=score.coverage_pick or score.primary_pick,
            coupon_criticality_score=score.coupon_criticality_score or 50.0,
        ))
    return inputs
