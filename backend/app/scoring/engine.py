"""
Scoring engine.
Implements §9 of the specification:
  Score_1, Score_X, Score_2 → softmax → P1, PX, P2
  Confidence score
  Coverage-need score
  Coverage type assignment (single/double/triple)
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import models

logger = logging.getLogger(__name__)

MODEL_VERSION = "v1"

# Softmax temperature (higher T = less confident distribution)
SOFTMAX_T = 0.4

# Coverage-need thresholds from spec §9.4
SINGLE_MAX = 38.0
DOUBLE_MAX = 72.0


def run_scoring_engine(db: Session, pool: models.WeeklyPool) -> None:
    """Score every unlocked match in the pool and write MatchModelScore rows."""
    logger.info("Scoring engine running for pool %d", pool.id)

    for pm in pool.matches:
        if pm.is_locked:
            continue
        try:
            _score_match(db, pm)
        except Exception as exc:
            logger.error("Scoring failed for match %d: %s", pm.id, exc)


def _score_match(db: Session, pm: models.WeeklyPoolMatch) -> None:
    # Get latest feature snapshot
    feat_snap = (
        db.query(models.MatchFeatureSnapshot)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchFeatureSnapshot.snapshot_time.desc())
        .first()
    )

    if not feat_snap:
        logger.warning("No feature snapshot for pool_match %d — using neutral values", pm.id)
        feat_snap = _neutral_features(pm.id)
        is_stub = True
    else:
        is_stub = False

    f = _FeatureBundle(feat_snap)

    # ── Score_1 ────────────────────────────────────────────────────────────
    score_1 = (
        0.24 * f.strength_edge_norm
        + 0.18 * f.form_edge_norm
        + 0.14 * f.home_advantage
        + 0.12 * f.lineup_edge_home
        + 0.10 * 0.5   # motivation (placeholder)
        + 0.10 * f.market_support
        + 0.06 * f.schedule_edge
        + 0.06 * f.stability_edge
    )

    # ── Score_X ────────────────────────────────────────────────────────────
    score_x = (
        0.26 * f.draw_tendency
        + 0.18 * f.balance_score
        + 0.14 * f.low_tempo_signal
        + 0.12 * f.low_goal_signal
        + 0.10 * f.market_draw_signal
        + 0.10 * f.tactical_symmetry
        + 0.10 * f.volatility_mid_zone
    )

    # ── Score_2 ────────────────────────────────────────────────────────────
    score_2 = (
        0.24 * f.away_strength_edge_norm
        + 0.18 * f.away_form_edge_norm
        + 0.14 * f.weak_home_signal
        + 0.12 * f.lineup_edge_away
        + 0.10 * 0.5   # motivation (placeholder)
        + 0.10 * f.away_market_support
        + 0.06 * f.schedule_edge
        + 0.06 * f.stability_edge
    )

    p1, px, p2 = _softmax([score_1, score_x, score_2], T=SOFTMAX_T)

    # ── Primary / Secondary pick ────────────────────────────────────────────
    ranked = sorted([("1", p1), ("X", px), ("2", p2)], key=lambda x: x[1], reverse=True)
    primary_pick = ranked[0][0]
    secondary_pick = ranked[1][0]

    # ── Confidence ────────────────────────────────────────────────────────
    p_max = ranked[0][1]
    p_second = ranked[1][1]
    confidence = (
        0.45 * (p_max - p_second)
        + 0.20 * 0.5  # model consensus (placeholder)
        + 0.15 * f.feature_stability
        + 0.10 * f.market_agreement
        + 0.10 * f.lineup_certainty
    )
    confidence_score = max(0.0, min(100.0, confidence * 100.0))

    # ── Coverage need ──────────────────────────────────────────────────────
    uncertainty = 1.0 - p_max
    coverage_need = (
        0.30 * uncertainty
        + 0.20 * f.volatility_score
        + 0.15 * f.draw_risk
        + 0.15 * f.market_disagreement
        + 0.10 * f.lineup_uncertainty
        + 0.10 * f.coupon_criticality
    )
    coverage_need_score = max(0.0, min(100.0, coverage_need * 100.0))

    # ── Coverage type ──────────────────────────────────────────────────────
    if coverage_need_score <= SINGLE_MAX:
        coverage_type = models.CoverageType.single
        coverage_pick = primary_pick
    elif coverage_need_score <= DOUBLE_MAX:
        coverage_type = models.CoverageType.double
        coverage_pick = _choose_double(primary_pick, secondary_pick, px)
    else:
        coverage_type = models.CoverageType.triple
        coverage_pick = "1X2"

    # ── Reason codes ──────────────────────────────────────────────────────
    reason_codes = _build_reason_codes(f, primary_pick, coverage_type)

    # ── Coupon criticality (used by optimizer) ────────────────────────────
    coupon_criticality = coverage_need_score / 100.0 * 0.7 + (1.0 - p_max) * 0.3
    coupon_criticality_score = max(0.0, min(100.0, coupon_criticality * 100.0))

    # ── Write to DB ────────────────────────────────────────────────────────
    previous = (
        db.query(models.MatchModelScore)
        .filter_by(weekly_pool_match_id=pm.id)
        .order_by(models.MatchModelScore.created_at.desc())
        .first()
    )

    score = models.MatchModelScore(
        weekly_pool_match_id=pm.id,
        model_version=MODEL_VERSION,
        p1=p1,
        px=px,
        p2=p2,
        primary_pick=primary_pick,
        secondary_pick=secondary_pick,
        confidence_score=confidence_score,
        coverage_need_score=coverage_need_score,
        coverage_pick=coverage_pick,
        coverage_type=coverage_type,
        coupon_criticality_score=coupon_criticality_score,
        reason_codes=reason_codes,
        feature_snapshot_id=feat_snap.id if not is_stub else None,
    )
    db.add(score)
    db.flush()

    # ── Change log ────────────────────────────────────────────────────────
    if previous:
        direction_changed = previous.primary_pick != primary_pick
        coverage_changed = previous.coverage_pick != coverage_pick
        if direction_changed or coverage_changed:
            change = models.ScoreChangeLog(
                weekly_pool_match_id=pm.id,
                old_primary_pick=previous.primary_pick,
                new_primary_pick=primary_pick,
                old_p1=previous.p1,
                old_px=previous.px,
                old_p2=previous.p2,
                new_p1=p1,
                new_px=px,
                new_p2=p2,
                old_coverage_pick=previous.coverage_pick,
                new_coverage_pick=coverage_pick,
                change_reason_code="DIRECTION_CHANGE" if direction_changed else "COVERAGE_CHANGE",
                triggered_by="scoring_engine",
            )
            db.add(change)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _softmax(scores: list[float], T: float = 1.0) -> tuple[float, float, float]:
    exps = [math.exp(s / T) for s in scores]
    total = sum(exps)
    return tuple(e / total for e in exps)


def _choose_double(primary: str, secondary: str, px: float) -> str:
    """§10.4 double direction logic."""
    pair = frozenset([primary, secondary])
    if pair == frozenset(["1", "X"]):
        return "1X"
    if pair == frozenset(["2", "X"]):
        return "X2"
    if pair == frozenset(["1", "2"]):
        # Use X protection when draw risk is meaningful
        if px >= 0.25:
            if primary == "1":
                return "1X"
            return "X2"
        return "12"
    return primary + secondary  # fallback


def _build_reason_codes(f: "_FeatureBundle", primary: str, coverage: models.CoverageType) -> list[str]:
    codes = []
    if f.strength_edge_norm > 0.6:
        codes.append("HOME_STRENGTH")
    if f.away_strength_edge_norm > 0.6:
        codes.append("AWAY_STRENGTH")
    if f.form_edge_norm > 0.6:
        codes.append("HOME_FORM")
    if f.away_form_edge_norm > 0.6:
        codes.append("AWAY_FORM")
    if f.draw_tendency > 0.55:
        codes.append("DRAW_RISK")
    if f.lineup_edge_home < 0.4:
        codes.append("HOME_ABSENCE")
    if f.lineup_edge_away < 0.4:
        codes.append("AWAY_ABSENCE")
    if f.market_agreement > 0.7:
        codes.append("MARKET_ALIGNED")
    if f.volatility_score > 0.65:
        codes.append("HIGH_VOLATILITY")
    if coverage == models.CoverageType.triple:
        codes.append("TRIPLE_RISK")
    return codes


class _FeatureBundle:
    """Read-only accessor for a MatchFeatureSnapshot with safe defaults."""

    def __init__(self, snap: models.MatchFeatureSnapshot):
        self._s = snap

    def _get(self, attr, default=0.5):
        v = getattr(self._s, attr, None)
        return v if v is not None else default

    @property
    def strength_edge_norm(self):
        return max(0.0, min(1.0, (self._get("strength_edge") + 1.0) / 2.0))

    @property
    def away_strength_edge_norm(self):
        return 1.0 - self.strength_edge_norm

    @property
    def form_edge_norm(self):
        return max(0.0, min(1.0, (self._get("form_edge") + 1.0) / 2.0))

    @property
    def away_form_edge_norm(self):
        return 1.0 - self.form_edge_norm

    @property
    def home_advantage(self):
        return self._get("home_advantage", 0.06)

    @property
    def draw_tendency(self):
        return self._get("draw_tendency")

    @property
    def balance_score(self):
        return self._get("balance_score")

    @property
    def low_tempo_signal(self):
        return self._get("low_tempo_signal")

    @property
    def low_goal_signal(self):
        return self._get("low_goal_signal")

    @property
    def tactical_symmetry(self):
        return self._get("tactical_symmetry")

    @property
    def market_support(self):
        return self._get("market_support")

    @property
    def away_market_support(self):
        raw = self._get("raw_features") or {}
        return (raw.get("market") or {}).get("implied_p2", 0.33)

    @property
    def market_draw_signal(self):
        raw = self._get("raw_features") or {}
        return (raw.get("market") or {}).get("market_draw_signal", 0.33)

    @property
    def market_agreement(self):
        raw = self._get("raw_features") or {}
        disp = (raw.get("market") or {}).get("bookmaker_dispersion", 0.5)
        return 1.0 - disp

    @property
    def market_disagreement(self):
        return 1.0 - self.market_agreement

    @property
    def volatility_score(self):
        return self._get("volatility_score")

    @property
    def volatility_mid_zone(self):
        v = self.volatility_score
        return 1.0 - abs(v - 0.5) * 2.0

    @property
    def lineup_certainty(self):
        return self._get("lineup_certainty")

    @property
    def lineup_uncertainty(self):
        return 1.0 - self.lineup_certainty

    @property
    def lineup_edge_home(self):
        penalty = self._get("lineup_penalty_home", 0.0)
        return max(0.0, 1.0 - penalty)

    @property
    def lineup_edge_away(self):
        penalty = self._get("lineup_penalty_away", 0.0)
        return max(0.0, 1.0 - penalty)

    @property
    def weak_home_signal(self):
        return 1.0 - self.home_advantage

    @property
    def schedule_edge(self):
        rh = self._get("rest_days_home", 7)
        ra = self._get("rest_days_away", 7)
        diff = (rh - ra) / 7.0
        return max(0.0, min(1.0, 0.5 + diff * 0.5))

    @property
    def stability_edge(self):
        return self.lineup_edge_home * 0.5 + self.lineup_certainty * 0.5

    @property
    def feature_stability(self):
        return self.lineup_certainty

    @property
    def draw_risk(self):
        return self.draw_tendency

    @property
    def coupon_criticality(self):
        return 0.5  # placeholder until optimizer pass sets it

    @property
    def id(self):
        return getattr(self._s, "id", None)


def _neutral_features(pm_id: int) -> models.MatchFeatureSnapshot:
    """Return a stub snapshot with neutral values when no real data exists."""
    snap = models.MatchFeatureSnapshot(
        weekly_pool_match_id=pm_id,
        snapshot_time=datetime.now(timezone.utc),
        strength_edge=0.0,
        form_edge=0.0,
        home_advantage=0.06,
        draw_tendency=0.33,
        balance_score=0.5,
        low_tempo_signal=0.5,
        low_goal_signal=0.5,
        draw_history=0.27,
        tactical_symmetry=0.5,
        lineup_continuity=0.0,
        market_support=0.33,
        volatility_score=0.5,
        rest_days_home=7,
        rest_days_away=7,
        lineup_penalty_home=0.0,
        lineup_penalty_away=0.0,
        lineup_certainty=0.0,
    )
    snap.id = None
    return snap


from datetime import datetime  # noqa: E402 (already imported above, kept for _neutral_features)
