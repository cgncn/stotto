"""
Scoring engine v2.
Implements §9 of the specification with expanded signal suite:
  Score_1, Score_X, Score_2 → softmax → P1, PX, P2
  Confidence score (with derby / international break / lucky form suppressors)
  Coverage-need score
  Coverage type assignment (single/double/triple)
  Expanded reason codes
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db import models

logger = logging.getLogger(__name__)

MODEL_VERSION = "v2"

# Softmax temperature (lower T = more confident distribution)
SOFTMAX_T = 0.25

# Coverage-need thresholds from spec §9.4
SINGLE_MAX = 45.0
DOUBLE_MAX = 75.0

# Confidence suppressors
_DERBY_SUPPRESSOR = 0.75
_INTL_BREAK_SUPPRESSOR = 0.88
_LUCKY_FORM_SUPPRESSOR = 0.90
_LONG_UNBEATEN_SUPPRESSOR = 0.93   # complacency risk for home side


def _load_calibration_multipliers(db: Session) -> dict:
    """Return the active calibration multipliers, or empty dict if none set."""
    row = (
        db.query(models.ModelCalibration)
        .filter_by(is_active=True)
        .order_by(models.ModelCalibration.created_at.desc())
        .first()
    )
    return row.multipliers if row else {}


def _apply_multipliers(base_weights: dict, multipliers: dict) -> dict:
    """Multiply each base weight by its calibration factor, then renormalise to sum=1."""
    if not multipliers:
        return base_weights
    adjusted = {k: v * multipliers.get(k, 1.0) for k, v in base_weights.items()}
    total = sum(adjusted.values()) or 1.0
    return {k: v / total for k, v in adjusted.items()}


def run_scoring_engine(db: Session, pool: models.WeeklyPool) -> None:
    """Score every unlocked match in the pool and write MatchModelScore rows."""
    logger.info("Scoring engine v2 running for pool %d", pool.id)
    cal = _load_calibration_multipliers(db)

    for pm in pool.matches:
        if pm.is_locked:
            continue
        try:
            _score_match(db, pm, cal)
        except Exception as exc:
            logger.error("Scoring failed for match %d: %s", pm.id, exc, exc_info=True)


def _score_match(db: Session, pm: models.WeeklyPoolMatch, cal: dict | None = None) -> None:
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
    cal = cal or {}

    # Base weights — calibration multipliers are applied on top of these
    _w1 = _apply_multipliers({
        "strength_edge_norm": 0.08, "form_edge_norm": 0.18, "home_advantage": 0.10,
        "lineup_edge_home": 0.09, "motivation_edge": 0.08, "h2h_home_advantage": 0.08,
        "market_support": 0.07, "away_form_penalty": 0.07, "schedule_edge": 0.06,
        "sharp_money_home_signal": 0.05, "congestion_advantage": 0.04,
        "xg_luck_edge": 0.04, "last_5_home_attack_edge": 0.06,
    }, cal.get("score_1", {}))

    _wx = _apply_multipliers({
        "draw_tendency": 0.22, "balance_score": 0.14, "low_tempo_signal": 0.11,
        "low_goal_signal": 0.10, "h2h_draw_rate": 0.09, "market_draw_signal": 0.09,
        "equal_motivation": 0.08, "tactical_symmetry": 0.08, "volatility_mid_zone": 0.09,
    }, cal.get("score_x", {}))

    _w2 = _apply_multipliers({
        "away_strength_edge_norm": 0.08, "away_form_edge_norm": 0.18, "weak_home_signal": 0.10,
        "lineup_edge_away": 0.09, "away_motivation_edge": 0.08, "h2h_bogey_signal": 0.08,
        "away_market_support": 0.07, "away_form_away": 0.07, "schedule_edge_away": 0.06,
        "sharp_money_away_signal": 0.05, "intl_break_home_penalty": 0.04,
        "xg_luck_edge_away": 0.04, "last_5_away_attack_edge": 0.06,
    }, cal.get("score_2", {}))

    # ── Score_1 (Home Win) ─────────────────────────────────────────────────
    score_1 = sum(w * getattr(f, sig) for sig, w in _w1.items())

    # ── Score_X (Draw) ─────────────────────────────────────────────────────
    score_x = sum(w * getattr(f, sig) for sig, w in _wx.items())

    # ── Score_2 (Away Win) ─────────────────────────────────────────────────
    score_2 = sum(w * getattr(f, sig) for sig, w in _w2.items())

    # ── Draw dampening & home form at home adjustment ─────────────────────
    # Draw is statistically over-represented in balanced matches; suppress it
    # unless both teams are confirmed strong in their respective venues.
    _DRAW_BASE_DAMPENER = 0.04   # always reduce draw score a little
    _HOME_FORM_THRESHOLD = 0.60  # above this, home team is "strong at home"
    _AWAY_FORM_THRESHOLD = 0.60  # above this, away team is "strong when away"

    score_x -= _DRAW_BASE_DAMPENER

    home_form_at_home = f.home_form_at_home
    away_form_when_away = f.away_form_when_away

    if home_form_at_home > _HOME_FORM_THRESHOLD:
        # Strong home form → shift weight from X to 1
        home_bonus = (home_form_at_home - _HOME_FORM_THRESHOLD) * 0.50  # 0 – 0.20
        score_1 += home_bonus
        score_x -= home_bonus * 0.70  # most of the draw penalty absorbed here

        # Only partially restore draw if away team is also strong when away
        if away_form_when_away > _AWAY_FORM_THRESHOLD:
            restoration = min(
                home_bonus * 0.55,
                (away_form_when_away - _AWAY_FORM_THRESHOLD) * 0.40,
            )
            score_x += restoration
            score_1 -= restoration * 0.45

    p1, px, p2 = _softmax([score_1, score_x, score_2], T=SOFTMAX_T)

    # ── Primary / Secondary pick ────────────────────────────────────────────
    ranked = sorted([("1", p1), ("X", px), ("2", p2)], key=lambda x: x[1], reverse=True)
    primary_pick = ranked[0][0]
    secondary_pick = ranked[1][0]

    # ── Confidence (raw) ──────────────────────────────────────────────────
    p_max = ranked[0][1]
    p_second = ranked[1][1]
    h2h_alignment = _h2h_alignment(primary_pick, f)
    motivation_clarity = abs(f.motivation_home_raw - f.motivation_away_raw)

    lineup_cert_floored = max(0.30, f.lineup_certainty)
    confidence_raw = (
        0.50 * (p_max - p_second)      # was 0.40 — probability gap is the strongest signal
        + 0.15 * f.market_agreement    # unchanged
        + 0.15 * lineup_cert_floored   # merged slot, floor at 0.30 so pre-match ≠ 0
        + 0.10 * h2h_alignment         # unchanged
        + 0.10 * motivation_clarity    # unchanged
    )

    # Apply suppressors
    if f.is_derby:
        confidence_raw *= _DERBY_SUPPRESSOR
    if f.post_intl_break_home or f.post_intl_break_away:
        confidence_raw *= _INTL_BREAK_SUPPRESSOR
    if f.lucky_form_home or f.lucky_form_away:
        confidence_raw *= _LUCKY_FORM_SUPPRESSOR
    if f.long_unbeaten_home and primary_pick == "1":
        confidence_raw *= _LONG_UNBEATEN_SUPPRESSOR

    confidence_score = max(0.0, min(100.0, confidence_raw * 180.0))

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
    # Derby and H2H bogey increase coverage need
    if f.is_derby:
        coverage_need = min(1.0, coverage_need * 1.15)
    if f.h2h_bogey_flag:
        coverage_need = min(1.0, coverage_need * 1.10)

    coverage_need_score = max(0.0, min(100.0, coverage_need * 100.0))

    # ── Coverage type ──────────────────────────────────────────────────────
    if coverage_need_score <= SINGLE_MAX:
        coverage_type = models.CoverageType.single.value
        coverage_pick = primary_pick
    elif coverage_need_score <= DOUBLE_MAX:
        coverage_type = models.CoverageType.double.value
        coverage_pick = _choose_double(primary_pick, secondary_pick, px)
    else:
        coverage_type = models.CoverageType.triple.value
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
        if px >= 0.25:
            if primary == "1":
                return "1X"
            return "X2"
        return "12"
    return primary + secondary  # fallback


def _h2h_alignment(primary_pick: str, f: "_FeatureBundle") -> float:
    """How well the H2H record agrees with the model's pick."""
    if f.h2h_sample_size == 0:
        return 0.5  # no data = neutral
    if primary_pick == "1":
        return f.h2h_home_win_rate_raw
    if primary_pick == "2":
        return f.h2h_away_win_rate_raw
    return f.h2h_draw_rate_raw


def _build_reason_codes(
    f: "_FeatureBundle", primary: str, coverage: str
) -> list[str]:
    codes = []
    # Existing codes
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
    if coverage == models.CoverageType.triple.value:
        codes.append("TRIPLE_RISK")
    # New codes
    if f.is_derby:
        codes.append("DERBY_FLAG")
    if f.h2h_bogey_flag:
        codes.append("H2H_BOGEY")
    if f.h2h_home_win_rate_raw > 0.6 and f.h2h_sample_size >= 4:
        codes.append("H2H_HOME_DOMINANT")
    if f.post_intl_break_home or f.post_intl_break_away:
        codes.append("POST_INTL_BREAK")
    if f.sharp_money_signal_raw > 0.5:
        codes.append("SHARP_MONEY_AWAY")
    if f.sharp_money_signal_raw < -0.5:
        codes.append("SHARP_MONEY_HOME")
    if f.lucky_form_home:
        codes.append("LUCKY_FORM_HOME")
    if f.lucky_form_away:
        codes.append("LUCKY_FORM_AWAY")
    if f.unlucky_form_home:
        codes.append("UNLUCKY_FORM_HOME")
    if f.unlucky_form_away:
        codes.append("UNLUCKY_FORM_AWAY")
    if f.motivation_home_raw > 0.65:
        codes.append("HIGH_MOTIVATION_HOME")
    if f.motivation_away_raw > 0.65:
        codes.append("HIGH_MOTIVATION_AWAY")
    if f.congestion_risk_away:
        codes.append("CONGESTION_RISK_AWAY")
    if f.key_attacker_absent_home or f.key_attacker_absent_away:
        codes.append("KEY_ATTACKER_ABSENT")
    if f.key_defender_absent_home or f.key_defender_absent_away:
        codes.append("KEY_DEFENDER_ABSENT")
    if f.long_unbeaten_home:
        codes.append("LONG_UNBEATEN_HOME")
    if f.home_form_at_home > 0.65:
        codes.append("HOME_STRONG_AT_HOME")
    return codes


class _FeatureBundle:
    """Read-only accessor for a MatchFeatureSnapshot with safe defaults."""

    def __init__(self, snap: models.MatchFeatureSnapshot):
        self._s = snap

    def _get(self, attr, default=0.5):
        v = getattr(self._s, attr, None)
        return v if v is not None else default

    def _getb(self, attr) -> bool:
        v = getattr(self._s, attr, None)
        return bool(v) if v is not None else False

    # ── Core existing ──────────────────────────────────────────────────────

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
        return max(0.0, 1.0 - self._get("lineup_penalty_home", 0.0))

    @property
    def lineup_edge_away(self):
        return max(0.0, 1.0 - self._get("lineup_penalty_away", 0.0))

    @property
    def weak_home_signal(self):
        return 1.0 - self.home_advantage

    @property
    def schedule_edge(self):
        rh = self._get("rest_days_home_actual", 7)
        ra = self._get("rest_days_away_actual", 7)
        diff = (rh - ra) / 7.0
        return max(0.0, min(1.0, 0.5 + diff * 0.5))

    @property
    def schedule_edge_away(self):
        return 1.0 - self.schedule_edge

    @property
    def stability_edge(self):
        return self.lineup_edge_home * 0.5 + self.lineup_certainty * 0.5

    @property
    def last_5_home_attack_edge(self) -> float:
        rf = getattr(self._s, "raw_features", None) or {}
        return float(rf.get("last_5", {}).get("last_5_home_attack_edge", 0.5))

    @property
    def last_5_away_attack_edge(self) -> float:
        rf = getattr(self._s, "raw_features", None) or {}
        return float(rf.get("last_5", {}).get("last_5_away_attack_edge", 0.5))

    @property
    def home_form_at_home(self) -> float:
        """
        Composite signal: how strong the home team is specifically at their home venue.
        Combines structural home advantage, last-5 attack edge, long unbeaten run, and H2H record.
        Returns 0–1 (0.5 = neutral, >0.65 = strong, >0.75 = dominant at home).
        """
        base = 0.50
        # Structural home advantage (typically 0.04–0.12 normalized)
        ha = self._get("home_advantage", 0.06)
        base += min(0.12, ha * 1.2)
        # Last-5 home attack edge (0=weak, 0.5=neutral, 1=dominant)
        l5 = self.last_5_home_attack_edge
        base += (l5 - 0.5) * 0.25
        # Long unbeaten run at home — strong signal of home dominance
        if self._getb("long_unbeaten_home"):
            base += 0.14
        # H2H home win rate (only if meaningful sample)
        if self.h2h_sample_size >= 3:
            base += (self.h2h_home_win_rate_raw - 0.33) * 0.25
        return max(0.0, min(1.0, base))

    @property
    def away_form_when_away(self) -> float:
        """How strong the away team is specifically when playing away from home."""
        return self.away_form_away  # away_form_away = away team's performance as visitors

    @property
    def draw_risk(self):
        return self.draw_tendency

    @property
    def coupon_criticality(self):
        return 0.5  # set by optimizer pass

    # ── H2H ────────────────────────────────────────────────────────────────

    @property
    def h2h_home_win_rate_raw(self):
        return self._get("h2h_home_win_rate", 0.33)

    @property
    def h2h_away_win_rate_raw(self):
        return self._get("h2h_away_win_rate", 0.33)

    @property
    def h2h_draw_rate_raw(self):
        return self._get("h2h_draw_rate", 0.33)

    @property
    def h2h_home_advantage(self):
        return self._get("h2h_home_win_rate", 0.33)

    @property
    def h2h_draw_rate(self):
        return self._get("h2h_draw_rate", 0.33)

    @property
    def h2h_bogey_signal(self):
        if self._getb("h2h_bogey_flag"):
            return 0.8  # strong away signal
        return self._get("h2h_away_win_rate", 0.33)

    @property
    def h2h_bogey_flag(self):
        return self._getb("h2h_bogey_flag")

    @property
    def h2h_sample_size(self):
        return self._get("h2h_sample_size", 0)

    # ── Context ────────────────────────────────────────────────────────────

    @property
    def is_derby(self):
        return self._getb("is_derby")

    @property
    def post_intl_break_home(self):
        return self._getb("post_intl_break_home")

    @property
    def post_intl_break_away(self):
        return self._getb("post_intl_break_away")

    @property
    def congestion_risk_away(self):
        return self._getb("congestion_risk_away")

    @property
    def congestion_advantage(self):
        """1.0 if away congested, 0.0 if home congested, 0.5 neutral."""
        ha = self._getb("congestion_risk_home")
        aa = self._getb("congestion_risk_away")
        if aa and not ha:
            return 1.0
        if ha and not aa:
            return 0.0
        return 0.5

    @property
    def intl_break_home_penalty(self):
        """Away team gets a boost if home team is post-international break."""
        return 1.0 if self.post_intl_break_home else 0.0

    # ── Motivation ─────────────────────────────────────────────────────────

    @property
    def motivation_home_raw(self):
        return self._get("motivation_home", 0.3)

    @property
    def motivation_away_raw(self):
        return self._get("motivation_away", 0.3)

    @property
    def motivation_edge(self):
        """Normalized [0, 1] advantage for home motivation over away."""
        diff = self.motivation_home_raw - self.motivation_away_raw
        return max(0.0, min(1.0, 0.5 + diff))

    @property
    def away_motivation_edge(self):
        return 1.0 - self.motivation_edge

    @property
    def equal_motivation(self):
        """High when both teams equally motivated → draw more likely."""
        return 1.0 - abs(self.motivation_home_raw - self.motivation_away_raw)

    @property
    def long_unbeaten_home(self):
        return self._getb("long_unbeaten_home")

    # ── Odds movement ──────────────────────────────────────────────────────

    @property
    def sharp_money_signal_raw(self):
        return self._get("sharp_money_signal", 0.0)

    @property
    def sharp_money_home_signal(self):
        """1.0 when sharp money strongly toward home (negative delta = odds shortened)."""
        return max(0.0, min(1.0, 0.5 - self.sharp_money_signal_raw / 2.0))

    @property
    def sharp_money_away_signal(self):
        """1.0 when sharp money strongly toward away (positive delta = odds drifted)."""
        return max(0.0, min(1.0, 0.5 + self.sharp_money_signal_raw / 2.0))

    # ── Away form ──────────────────────────────────────────────────────────

    @property
    def away_form_away(self):
        return self._get("away_form_away", 0.4)

    @property
    def away_form_penalty(self):
        """1 - away_form_away: strong away team = higher threat, lower home confidence."""
        return 1.0 - self.away_form_away

    # ── xG / luck ──────────────────────────────────────────────────────────

    @property
    def lucky_form_home(self):
        return self._getb("lucky_form_home")

    @property
    def lucky_form_away(self):
        return self._getb("lucky_form_away")

    @property
    def unlucky_form_home(self):
        return self._getb("unlucky_form_home")

    @property
    def unlucky_form_away(self):
        return self._getb("unlucky_form_away")

    @property
    def xg_luck_edge(self):
        """
        Positive signal for home win when:
        - home team is unlucky (due for positive reversion) OR
        - away team is lucky (due for negative reversion)
        """
        score = 0.5
        if self.unlucky_form_home:
            score += 0.25
        if self.lucky_form_away:
            score += 0.25
        if self.lucky_form_home:
            score -= 0.25
        if self.unlucky_form_away:
            score -= 0.25
        return max(0.0, min(1.0, score))

    @property
    def xg_luck_edge_away(self):
        return 1.0 - self.xg_luck_edge

    # ── Key absences ───────────────────────────────────────────────────────

    @property
    def key_attacker_absent_home(self):
        return self._getb("key_attacker_absent_home")

    @property
    def key_attacker_absent_away(self):
        return self._getb("key_attacker_absent_away")

    @property
    def key_defender_absent_home(self):
        return self._getb("key_defender_absent_home")

    @property
    def key_defender_absent_away(self):
        return self._getb("key_defender_absent_away")

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
        # New fields default to None / False
        h2h_home_win_rate=0.33,
        h2h_away_win_rate=0.33,
        h2h_draw_rate=0.33,
        h2h_sample_size=0,
        is_derby=False,
        derby_confidence_suppressor=1.0,
        motivation_home=0.3,
        motivation_away=0.3,
    )
    snap.id = None
    return snap
