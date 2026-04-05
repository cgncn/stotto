"""initial_schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_provider_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country", sa.String(100)),
        sa.Column("league_id", sa.Integer()),
        sa.Column("logo_url", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_teams_external_provider_id", "teams", ["external_provider_id"])

    op.create_table(
        "fixtures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_provider_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("home_team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("away_team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(), nullable=False),
        sa.Column("venue", sa.String(255)),
        sa.Column("status", sa.String(50), server_default="NS"),
        sa.Column("home_score", sa.Integer()),
        sa.Column("away_score", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_fixtures_external_provider_id", "fixtures", ["external_provider_id"])

    op.create_table(
        "weekly_pools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_code", sa.String(20), nullable=False, unique=True),
        sa.Column("announcement_time", sa.DateTime()),
        sa.Column("deadline_at", sa.DateTime()),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("model_version", sa.String(50), server_default="v1"),
        sa.Column("feature_set_version", sa.String(50), server_default="v1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_weekly_pools_week_code", "weekly_pools", ["week_code"])

    op.create_table(
        "weekly_pool_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("weekly_pool_id", sa.Integer(), sa.ForeignKey("weekly_pools.id"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("fixture_external_id", sa.Integer(), nullable=False),
        sa.Column("kickoff_at", sa.DateTime()),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("result", sa.String(1)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("weekly_pool_id", "sequence_no", name="uq_pool_match_seq"),
    )
    op.create_index("ix_weekly_pool_matches_weekly_pool_id", "weekly_pool_matches", ["weekly_pool_id"])

    op.create_table(
        "fixture_odds_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(), nullable=False),
        sa.Column("home_odds", sa.Float()),
        sa.Column("draw_odds", sa.Float()),
        sa.Column("away_odds", sa.Float()),
        sa.Column("bookmaker", sa.String(100)),
        sa.Column("raw_payload", sa.JSON()),
    )
    op.create_index("ix_fixture_odds_snapshots_fixture_id", "fixture_odds_snapshots", ["fixture_id"])

    op.create_table(
        "fixture_lineups_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(), nullable=False),
        sa.Column("payload_json", sa.JSON()),
    )
    op.create_index("ix_fixture_lineups_snapshots_fixture_id", "fixture_lineups_snapshots", ["fixture_id"])

    op.create_table(
        "fixture_injuries_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(), nullable=False),
        sa.Column("payload_json", sa.JSON()),
    )
    op.create_index("ix_fixture_injuries_snapshots_fixture_id", "fixture_injuries_snapshots", ["fixture_id"])

    op.create_table(
        "fixture_statistics_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(), nullable=False),
        sa.Column("payload_json", sa.JSON()),
    )
    op.create_index("ix_fixture_statistics_snapshots_fixture_id", "fixture_statistics_snapshots", ["fixture_id"])

    op.create_table(
        "standings_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("league_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(), nullable=False),
        sa.Column("payload_json", sa.JSON()),
    )
    op.create_index("ix_standings_snapshots_league_id", "standings_snapshots", ["league_id"])

    op.create_table(
        "team_feature_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(), nullable=False),
        sa.Column("feature_set_version", sa.String(50), server_default="v1"),
        sa.Column("strength_score", sa.Float()),
        sa.Column("season_ppg", sa.Float()),
        sa.Column("goal_diff_per_game", sa.Float()),
        sa.Column("attack_index", sa.Float()),
        sa.Column("defense_index", sa.Float()),
        sa.Column("opponent_adjusted_score", sa.Float()),
        sa.Column("form_score", sa.Float()),
        sa.Column("last_5_points", sa.Float()),
        sa.Column("weighted_recent_form", sa.Float()),
        sa.Column("home_ppg", sa.Float()),
        sa.Column("away_ppg", sa.Float()),
        sa.Column("home_clean_sheet_rate", sa.Float()),
        sa.Column("raw_features", sa.JSON()),
    )
    op.create_index("ix_team_feature_snapshots_team_id", "team_feature_snapshots", ["team_id"])

    op.create_table(
        "match_feature_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("weekly_pool_match_id", sa.Integer(), sa.ForeignKey("weekly_pool_matches.id"), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(), nullable=False),
        sa.Column("feature_set_version", sa.String(50), server_default="v1"),
        sa.Column("strength_edge", sa.Float()),
        sa.Column("form_edge", sa.Float()),
        sa.Column("home_advantage", sa.Float()),
        sa.Column("draw_tendency", sa.Float()),
        sa.Column("balance_score", sa.Float()),
        sa.Column("low_tempo_signal", sa.Float()),
        sa.Column("low_goal_signal", sa.Float()),
        sa.Column("draw_history", sa.Float()),
        sa.Column("tactical_symmetry", sa.Float()),
        sa.Column("lineup_continuity", sa.Float()),
        sa.Column("market_support", sa.Float()),
        sa.Column("volatility_score", sa.Float()),
        sa.Column("rest_days_home", sa.Integer()),
        sa.Column("rest_days_away", sa.Integer()),
        sa.Column("lineup_penalty_home", sa.Float()),
        sa.Column("lineup_penalty_away", sa.Float()),
        sa.Column("lineup_certainty", sa.Float()),
        sa.Column("raw_features", sa.JSON()),
    )
    op.create_index("ix_match_feature_snapshots_weekly_pool_match_id", "match_feature_snapshots", ["weekly_pool_match_id"])

    op.create_table(
        "match_model_scores",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("weekly_pool_match_id", sa.Integer(), sa.ForeignKey("weekly_pool_matches.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("model_version", sa.String(50), server_default="v1"),
        sa.Column("p1", sa.Float(), nullable=False),
        sa.Column("px", sa.Float(), nullable=False),
        sa.Column("p2", sa.Float(), nullable=False),
        sa.Column("primary_pick", sa.String(1), nullable=False),
        sa.Column("secondary_pick", sa.String(1)),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("coverage_need_score", sa.Float()),
        sa.Column("coverage_pick", sa.String(2)),
        sa.Column("coverage_type", sa.String(10)),
        sa.Column("coupon_criticality_score", sa.Float()),
        sa.Column("reason_codes", sa.JSON()),
        sa.Column("feature_snapshot_id", sa.BigInteger(), sa.ForeignKey("match_feature_snapshots.id")),
    )
    op.create_index("ix_match_model_scores_weekly_pool_match_id", "match_model_scores", ["weekly_pool_match_id"])

    op.create_table(
        "coupon_scenarios",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("weekly_pool_id", sa.Integer(), sa.ForeignKey("weekly_pools.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("scenario_type", sa.String(20), nullable=False),
        sa.Column("risk_profile", sa.String(10), server_default="medium"),
        sa.Column("max_columns", sa.Integer()),
        sa.Column("max_doubles", sa.Integer()),
        sa.Column("max_triples", sa.Integer()),
        sa.Column("picks_json", sa.JSON(), nullable=False),
        sa.Column("total_columns", sa.Integer(), nullable=False),
        sa.Column("expected_coverage_score", sa.Float()),
        sa.Column("optimizer_version", sa.String(50), server_default="v1"),
    )
    op.create_index("ix_coupon_scenarios_weekly_pool_id", "coupon_scenarios", ["weekly_pool_id"])

    op.create_table(
        "score_change_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("weekly_pool_match_id", sa.Integer(), sa.ForeignKey("weekly_pool_matches.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("old_primary_pick", sa.String(1)),
        sa.Column("new_primary_pick", sa.String(1)),
        sa.Column("old_p1", sa.Float()),
        sa.Column("old_px", sa.Float()),
        sa.Column("old_p2", sa.Float()),
        sa.Column("new_p1", sa.Float()),
        sa.Column("new_px", sa.Float()),
        sa.Column("new_p2", sa.Float()),
        sa.Column("old_coverage_pick", sa.String(2)),
        sa.Column("new_coverage_pick", sa.String(2)),
        sa.Column("change_reason_code", sa.String(100)),
        sa.Column("triggered_by", sa.String(100)),
    )
    op.create_index("ix_score_change_log_weekly_pool_match_id", "score_change_log", ["weekly_pool_match_id"])


def downgrade() -> None:
    op.drop_table("score_change_log")
    op.drop_table("coupon_scenarios")
    op.drop_table("match_model_scores")
    op.drop_table("match_feature_snapshots")
    op.drop_table("team_feature_snapshots")
    op.drop_table("standings_snapshots")
    op.drop_table("fixture_statistics_snapshots")
    op.drop_table("fixture_injuries_snapshots")
    op.drop_table("fixture_lineups_snapshots")
    op.drop_table("fixture_odds_snapshots")
    op.drop_table("weekly_pool_matches")
    op.drop_table("weekly_pools")
    op.drop_table("fixtures")
    op.drop_table("teams")
    op.drop_table("users")
