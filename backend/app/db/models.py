"""
All SQLAlchemy ORM models for STOTTO.
Snapshot tables are immutable — always INSERT, never UPDATE.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    FREE = "FREE"
    SUBSCRIBER = "SUBSCRIBER"
    ADMIN = "ADMIN"


class PoolStatus(str, enum.Enum):
    open = "open"
    locked = "locked"
    settled = "settled"


class MatchStatus(str, enum.Enum):
    pending = "pending"
    live = "live"
    finished = "finished"
    locked = "locked"


class CoverageType(str, enum.Enum):
    single = "single"
    double = "double"
    triple = "triple"


class ScenarioType(str, enum.Enum):
    safe = "safe"
    balanced = "balanced"
    aggressive = "aggressive"


class RiskProfile(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


# ── Master data ───────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, server_default="FREE")
    display_name = Column(String(100))
    iyzico_customer_ref = Column(String(100))
    iyzico_subscription_ref = Column(String(100))
    subscription_status = Column(String(30), default="inactive")
    subscription_expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_subscriber(self) -> bool:
        return self.role in (UserRole.SUBSCRIBER, UserRole.ADMIN)


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    external_provider_id = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    country = Column(String(100))
    league_id = Column(Integer)
    logo_url = Column(String(500))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True)
    external_provider_id = Column(Integer, unique=True, nullable=False, index=True)
    season = Column(Integer, nullable=False)
    league_id = Column(Integer, nullable=False)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    kickoff_at = Column(DateTime, nullable=False)
    venue = Column(String(255))
    status = Column(String(50), default="NS")
    home_score = Column(Integer)
    away_score = Column(Integer)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])


# ── Weekly pool ───────────────────────────────────────────────────────────────

class WeeklyPool(Base):
    __tablename__ = "weekly_pools"

    id = Column(Integer, primary_key=True)
    week_code = Column(String(20), unique=True, nullable=False, index=True)
    announcement_time = Column(DateTime)
    deadline_at = Column(DateTime)
    status = Column(Enum(PoolStatus), default=PoolStatus.open, nullable=False)
    model_version = Column(String(50), default="v1")
    feature_set_version = Column(String(50), default="v1")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    matches = relationship("WeeklyPoolMatch", back_populates="pool", order_by="WeeklyPoolMatch.sequence_no")


class WeeklyPoolMatch(Base):
    __tablename__ = "weekly_pool_matches"
    __table_args__ = (
        UniqueConstraint("weekly_pool_id", "sequence_no", name="uq_pool_match_seq"),
    )

    id = Column(Integer, primary_key=True)
    weekly_pool_id = Column(Integer, ForeignKey("weekly_pools.id"), nullable=False, index=True)
    sequence_no = Column(Integer, nullable=False)  # 1–15
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    fixture_external_id = Column(Integer, nullable=False)
    kickoff_at = Column(DateTime)
    status = Column(Enum(MatchStatus), default=MatchStatus.pending, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    result = Column(String(1))  # '1', 'X', '2'
    is_derby = Column(Boolean, default=False, nullable=False)
    admin_flags = Column(JSON, default=dict)  # {"thursday_european_away": bool}
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    pool = relationship("WeeklyPool", back_populates="matches")
    fixture = relationship("Fixture")
    model_scores = relationship("MatchModelScore", back_populates="pool_match",
                                order_by="MatchModelScore.created_at.desc()")


# ── Raw snapshots ─────────────────────────────────────────────────────────────

class FixtureOddsSnapshot(Base):
    __tablename__ = "fixture_odds_snapshots"

    id = Column(BigInteger, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    home_odds = Column(Float)
    draw_odds = Column(Float)
    away_odds = Column(Float)
    bookmaker = Column(String(100))
    raw_payload = Column(JSON)


class FixtureLineupsSnapshot(Base):
    __tablename__ = "fixture_lineups_snapshots"

    id = Column(BigInteger, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    payload_json = Column(JSON)


class FixtureInjuriesSnapshot(Base):
    __tablename__ = "fixture_injuries_snapshots"

    id = Column(BigInteger, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    payload_json = Column(JSON)


class FixtureStatisticsSnapshot(Base):
    __tablename__ = "fixture_statistics_snapshots"

    id = Column(BigInteger, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    payload_json = Column(JSON)


class FixtureH2HSnapshot(Base):
    __tablename__ = "fixture_h2h_snapshots"

    id = Column(BigInteger, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False, index=True)
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    home_team_id = Column(Integer, nullable=False)
    away_team_id = Column(Integer, nullable=False)
    payload_json = Column(JSON)


class StandingsSnapshot(Base):
    __tablename__ = "standings_snapshots"

    id = Column(BigInteger, primary_key=True)
    league_id = Column(Integer, nullable=False, index=True)
    season = Column(Integer, nullable=False)
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    payload_json = Column(JSON)


# ── Feature snapshots ─────────────────────────────────────────────────────────

class TeamFeatureSnapshot(Base):
    __tablename__ = "team_feature_snapshots"

    id = Column(BigInteger, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False, index=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    feature_set_version = Column(String(50), default="v1")

    # Strength
    strength_score = Column(Float)
    season_ppg = Column(Float)
    goal_diff_per_game = Column(Float)
    attack_index = Column(Float)
    defense_index = Column(Float)
    opponent_adjusted_score = Column(Float)

    # Form
    form_score = Column(Float)
    last_5_points = Column(Float)
    weighted_recent_form = Column(Float)

    # Home/Away
    home_ppg = Column(Float)
    away_ppg = Column(Float)
    home_clean_sheet_rate = Column(Float)

    raw_features = Column(JSON)


class MatchFeatureSnapshot(Base):
    __tablename__ = "match_feature_snapshots"

    id = Column(BigInteger, primary_key=True)
    weekly_pool_match_id = Column(Integer, ForeignKey("weekly_pool_matches.id"), nullable=False, index=True)
    snapshot_time = Column(DateTime, nullable=False, default=func.now())
    feature_set_version = Column(String(50), default="v1")

    strength_edge = Column(Float)
    form_edge = Column(Float)
    home_advantage = Column(Float)
    draw_tendency = Column(Float)
    balance_score = Column(Float)
    low_tempo_signal = Column(Float)
    low_goal_signal = Column(Float)
    draw_history = Column(Float)
    tactical_symmetry = Column(Float)
    lineup_continuity = Column(Float)
    market_support = Column(Float)
    volatility_score = Column(Float)
    rest_days_home = Column(Integer)
    rest_days_away = Column(Integer)
    lineup_penalty_home = Column(Float)
    lineup_penalty_away = Column(Float)
    lineup_certainty = Column(Float)

    # H2H
    h2h_home_win_rate = Column(Float)
    h2h_away_win_rate = Column(Float)
    h2h_draw_rate = Column(Float)
    h2h_venue_home_win_rate = Column(Float)
    h2h_bogey_flag = Column(Boolean)
    h2h_sample_size = Column(Integer)

    # Real rest days
    rest_days_home_actual = Column(Float)
    rest_days_away_actual = Column(Float)

    # International break
    post_intl_break_home = Column(Boolean)
    post_intl_break_away = Column(Boolean)

    # Fixture congestion
    congestion_risk_home = Column(Boolean)
    congestion_risk_away = Column(Boolean)

    # Derby
    is_derby = Column(Boolean)
    derby_confidence_suppressor = Column(Float)

    # Odds movement
    opening_odds_home = Column(Float)
    opening_odds_away = Column(Float)
    opening_odds_draw = Column(Float)
    odds_delta_home = Column(Float)
    sharp_money_signal = Column(Float)

    # Away-specific form
    away_form_home = Column(Float)
    away_form_away = Column(Float)

    # xG proxy & luck flags
    xg_proxy_home = Column(Float)
    xg_proxy_away = Column(Float)
    xg_luck_home = Column(Float)
    xg_luck_away = Column(Float)
    lucky_form_home = Column(Boolean)
    lucky_form_away = Column(Boolean)
    unlucky_form_home = Column(Boolean)
    unlucky_form_away = Column(Boolean)

    # Motivation / objective
    motivation_home = Column(Float)
    motivation_away = Column(Float)
    points_above_relegation_home = Column(Integer)
    points_above_relegation_away = Column(Integer)
    points_to_top4_home = Column(Integer)
    points_to_top4_away = Column(Integer)
    points_to_top6_home = Column(Integer)
    points_to_top6_away = Column(Integer)
    points_to_title_home = Column(Integer)
    points_to_title_away = Column(Integer)
    long_unbeaten_home = Column(Boolean)
    long_unbeaten_away = Column(Boolean)

    # Role-specific absences
    key_attacker_absent_home = Column(Boolean)
    key_attacker_absent_away = Column(Boolean)
    key_defender_absent_home = Column(Boolean)
    key_defender_absent_away = Column(Boolean)

    raw_features = Column(JSON)


# ── Scoring outputs ───────────────────────────────────────────────────────────

class MatchModelScore(Base):
    __tablename__ = "match_model_scores"

    id = Column(BigInteger, primary_key=True)
    weekly_pool_match_id = Column(Integer, ForeignKey("weekly_pool_matches.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    model_version = Column(String(50), default="v1")

    p1 = Column(Float, nullable=False)
    px = Column(Float, nullable=False)
    p2 = Column(Float, nullable=False)
    primary_pick = Column(String(1), nullable=False)   # '1', 'X', '2'
    secondary_pick = Column(String(1))
    confidence_score = Column(Float)
    coverage_need_score = Column(Float)
    coverage_pick = Column(String(2))  # '1X', 'X2', '12', '1', 'X', '2'
    coverage_type = Column(Enum(CoverageType))
    coupon_criticality_score = Column(Float)

    reason_codes = Column(JSON)  # list of strings
    feature_snapshot_id = Column(BigInteger, ForeignKey("match_feature_snapshots.id"))

    pool_match = relationship("WeeklyPoolMatch", back_populates="model_scores")


class CouponScenario(Base):
    __tablename__ = "coupon_scenarios"

    id = Column(BigInteger, primary_key=True)
    weekly_pool_id = Column(Integer, ForeignKey("weekly_pools.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    scenario_type = Column(Enum(ScenarioType), nullable=False)
    risk_profile = Column(Enum(RiskProfile), default=RiskProfile.medium)
    max_columns = Column(Integer)
    max_doubles = Column(Integer)
    max_triples = Column(Integer)

    # picks_json: list of {match_id, sequence_no, coverage_pick, coverage_type}
    picks_json = Column(JSON, nullable=False)
    total_columns = Column(Integer, nullable=False)
    expected_coverage_score = Column(Float)
    optimizer_version = Column(String(50), default="v1")


class ScoreChangeLog(Base):
    __tablename__ = "score_change_log"

    id = Column(BigInteger, primary_key=True)
    weekly_pool_match_id = Column(Integer, ForeignKey("weekly_pool_matches.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    old_primary_pick = Column(String(1))
    new_primary_pick = Column(String(1))
    old_p1 = Column(Float)
    old_px = Column(Float)
    old_p2 = Column(Float)
    new_p1 = Column(Float)
    new_px = Column(Float)
    new_p2 = Column(Float)
    old_coverage_pick = Column(String(2))
    new_coverage_pick = Column(String(2))
    change_reason_code = Column(String(100))
    triggered_by = Column(String(100))  # 'daily_refresh', 'pre_kickoff', 'manual'


# ── User coupons & subscription ───────────────────────────────────────────────

class UserCoupon(Base):
    __tablename__ = "user_coupons"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    weekly_pool_id = Column(Integer, ForeignKey("weekly_pools.id"), nullable=False)
    scenario_type = Column(String(20))
    picks_json = Column(JSON, nullable=False)
    column_count = Column(Integer)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_submitted = Column(Boolean, nullable=False, default=False)


class UserCouponPerformance(Base):
    __tablename__ = "user_coupon_performance"
    id = Column(Integer, primary_key=True)
    user_coupon_id = Column(Integer, ForeignKey("user_coupons.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    week_code = Column(String(20), nullable=False)
    correct_count = Column(Integer)
    total_picks = Column(Integer)
    brier_score = Column(Float)
    roi_estimate = Column(Float)
    settled_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SubscriptionLog(Base):
    __tablename__ = "subscription_log"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    payment_event_ref = Column(String(200), nullable=False, unique=True)
    event_type = Column(String(80), nullable=False)
    payload_json = Column(JSON)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
