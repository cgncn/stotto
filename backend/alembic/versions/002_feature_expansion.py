"""feature_expansion

Revision ID: 002
Revises: 001
Create Date: 2026-04-07 00:00:00.000000

Adds: fixture_h2h_snapshots table, is_derby + admin_flags on weekly_pool_matches,
and all new signal columns on match_feature_snapshots.
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── New table: fixture_h2h_snapshots ─────────────────────────────────────
    op.create_table(
        "fixture_h2h_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("payload_json", sa.JSON()),
    )
    op.create_index("ix_fixture_h2h_snapshots_fixture_id", "fixture_h2h_snapshots", ["fixture_id"])

    # ── weekly_pool_matches: is_derby + admin_flags ───────────────────────────
    op.add_column("weekly_pool_matches", sa.Column("is_derby", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("weekly_pool_matches", sa.Column("admin_flags", sa.JSON(), server_default="{}"))

    # ── match_feature_snapshots: all new signals ──────────────────────────────

    # H2H
    op.add_column("match_feature_snapshots", sa.Column("h2h_home_win_rate", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("h2h_away_win_rate", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("h2h_draw_rate", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("h2h_venue_home_win_rate", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("h2h_bogey_flag", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("h2h_sample_size", sa.Integer()))

    # Real rest days (replaces hardcoded 7)
    op.add_column("match_feature_snapshots", sa.Column("rest_days_home_actual", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("rest_days_away_actual", sa.Float()))

    # International break
    op.add_column("match_feature_snapshots", sa.Column("post_intl_break_home", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("post_intl_break_away", sa.Boolean()))

    # Fixture congestion
    op.add_column("match_feature_snapshots", sa.Column("congestion_risk_home", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("congestion_risk_away", sa.Boolean()))

    # Derby
    op.add_column("match_feature_snapshots", sa.Column("is_derby", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("derby_confidence_suppressor", sa.Float()))

    # Odds movement
    op.add_column("match_feature_snapshots", sa.Column("opening_odds_home", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("opening_odds_away", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("opening_odds_draw", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("odds_delta_home", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("sharp_money_signal", sa.Float()))

    # Away-specific form
    op.add_column("match_feature_snapshots", sa.Column("away_form_home", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("away_form_away", sa.Float()))

    # xG proxy & luck flags
    op.add_column("match_feature_snapshots", sa.Column("xg_proxy_home", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("xg_proxy_away", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("xg_luck_home", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("xg_luck_away", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("lucky_form_home", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("lucky_form_away", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("unlucky_form_home", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("unlucky_form_away", sa.Boolean()))

    # Motivation / objective
    op.add_column("match_feature_snapshots", sa.Column("motivation_home", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("motivation_away", sa.Float()))
    op.add_column("match_feature_snapshots", sa.Column("points_above_relegation_home", sa.Integer()))
    op.add_column("match_feature_snapshots", sa.Column("points_above_relegation_away", sa.Integer()))
    op.add_column("match_feature_snapshots", sa.Column("points_to_top4_home", sa.Integer()))
    op.add_column("match_feature_snapshots", sa.Column("points_to_top4_away", sa.Integer()))
    op.add_column("match_feature_snapshots", sa.Column("points_to_top6_home", sa.Integer()))
    op.add_column("match_feature_snapshots", sa.Column("points_to_top6_away", sa.Integer()))
    op.add_column("match_feature_snapshots", sa.Column("points_to_title_home", sa.Integer()))
    op.add_column("match_feature_snapshots", sa.Column("points_to_title_away", sa.Integer()))
    op.add_column("match_feature_snapshots", sa.Column("long_unbeaten_home", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("long_unbeaten_away", sa.Boolean()))

    # Role-specific absences
    op.add_column("match_feature_snapshots", sa.Column("key_attacker_absent_home", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("key_attacker_absent_away", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("key_defender_absent_home", sa.Boolean()))
    op.add_column("match_feature_snapshots", sa.Column("key_defender_absent_away", sa.Boolean()))


def downgrade() -> None:
    # Role-specific absences
    op.drop_column("match_feature_snapshots", "key_defender_absent_away")
    op.drop_column("match_feature_snapshots", "key_defender_absent_home")
    op.drop_column("match_feature_snapshots", "key_attacker_absent_away")
    op.drop_column("match_feature_snapshots", "key_attacker_absent_home")

    # Motivation
    op.drop_column("match_feature_snapshots", "long_unbeaten_away")
    op.drop_column("match_feature_snapshots", "long_unbeaten_home")
    op.drop_column("match_feature_snapshots", "points_to_title_away")
    op.drop_column("match_feature_snapshots", "points_to_title_home")
    op.drop_column("match_feature_snapshots", "points_to_top6_away")
    op.drop_column("match_feature_snapshots", "points_to_top6_home")
    op.drop_column("match_feature_snapshots", "points_to_top4_away")
    op.drop_column("match_feature_snapshots", "points_to_top4_home")
    op.drop_column("match_feature_snapshots", "points_above_relegation_away")
    op.drop_column("match_feature_snapshots", "points_above_relegation_home")
    op.drop_column("match_feature_snapshots", "motivation_away")
    op.drop_column("match_feature_snapshots", "motivation_home")

    # xG
    op.drop_column("match_feature_snapshots", "unlucky_form_away")
    op.drop_column("match_feature_snapshots", "unlucky_form_home")
    op.drop_column("match_feature_snapshots", "lucky_form_away")
    op.drop_column("match_feature_snapshots", "lucky_form_home")
    op.drop_column("match_feature_snapshots", "xg_luck_away")
    op.drop_column("match_feature_snapshots", "xg_luck_home")
    op.drop_column("match_feature_snapshots", "xg_proxy_away")
    op.drop_column("match_feature_snapshots", "xg_proxy_home")

    # Away form
    op.drop_column("match_feature_snapshots", "away_form_away")
    op.drop_column("match_feature_snapshots", "away_form_home")

    # Odds movement
    op.drop_column("match_feature_snapshots", "sharp_money_signal")
    op.drop_column("match_feature_snapshots", "odds_delta_home")
    op.drop_column("match_feature_snapshots", "opening_odds_draw")
    op.drop_column("match_feature_snapshots", "opening_odds_away")
    op.drop_column("match_feature_snapshots", "opening_odds_home")

    # Derby
    op.drop_column("match_feature_snapshots", "derby_confidence_suppressor")
    op.drop_column("match_feature_snapshots", "is_derby")

    # Congestion
    op.drop_column("match_feature_snapshots", "congestion_risk_away")
    op.drop_column("match_feature_snapshots", "congestion_risk_home")

    # Intl break
    op.drop_column("match_feature_snapshots", "post_intl_break_away")
    op.drop_column("match_feature_snapshots", "post_intl_break_home")

    # Rest days
    op.drop_column("match_feature_snapshots", "rest_days_away_actual")
    op.drop_column("match_feature_snapshots", "rest_days_home_actual")

    # H2H
    op.drop_column("match_feature_snapshots", "h2h_sample_size")
    op.drop_column("match_feature_snapshots", "h2h_bogey_flag")
    op.drop_column("match_feature_snapshots", "h2h_venue_home_win_rate")
    op.drop_column("match_feature_snapshots", "h2h_draw_rate")
    op.drop_column("match_feature_snapshots", "h2h_away_win_rate")
    op.drop_column("match_feature_snapshots", "h2h_home_win_rate")

    # weekly_pool_matches
    op.drop_column("weekly_pool_matches", "admin_flags")
    op.drop_column("weekly_pool_matches", "is_derby")

    # H2H table
    op.drop_index("ix_fixture_h2h_snapshots_fixture_id", "fixture_h2h_snapshots")
    op.drop_table("fixture_h2h_snapshots")
