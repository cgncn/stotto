"""auth_subscription

Revision ID: 002
Revises: 001
Create Date: 2026-04-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TABLE users - add auth/subscription columns
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="FREE"))
    op.add_column("users", sa.Column("display_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(100), nullable=True, unique=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(100), nullable=True, unique=True))
    op.add_column("users", sa.Column("subscription_status", sa.String(30), nullable=True, server_default="inactive"))
    op.add_column("users", sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True))

    # CREATE TABLE user_coupons
    op.create_table(
        "user_coupons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekly_pool_id", sa.Integer(), sa.ForeignKey("weekly_pools.id"), nullable=False),
        sa.Column("scenario_type", sa.String(20), nullable=True),
        sa.Column("picks_json", postgresql.JSONB(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("user_id", "weekly_pool_id", "scenario_type", name="uq_user_coupon_pool_scenario"),
    )
    op.create_index("ix_user_coupons_user_id", "user_coupons", ["user_id"])
    op.create_index("ix_user_coupons_weekly_pool_id", "user_coupons", ["weekly_pool_id"])

    # CREATE TABLE user_coupon_performance
    op.create_table(
        "user_coupon_performance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_coupon_id", sa.Integer(), sa.ForeignKey("user_coupons.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("week_code", sa.String(20), nullable=False),
        sa.Column("correct_count", sa.Integer(), nullable=True),
        sa.Column("total_picks", sa.Integer(), nullable=True),
        sa.Column("brier_score", sa.Float(), nullable=True),
        sa.Column("roi_estimate", sa.Float(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_user_coupon_performance_user_coupon_id", "user_coupon_performance", ["user_coupon_id"])
    op.create_index("ix_user_coupon_performance_user_id", "user_coupon_performance", ["user_id"])

    # CREATE TABLE subscription_log
    op.create_table(
        "subscription_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("stripe_event_id", sa.String(100), nullable=False, unique=True),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_subscription_log_user_id", "subscription_log", ["user_id"])


def downgrade() -> None:
    # Drop tables in reverse order (respecting FK dependencies)
    op.drop_index("ix_subscription_log_user_id", table_name="subscription_log")
    op.drop_table("subscription_log")

    op.drop_index("ix_user_coupon_performance_user_id", table_name="user_coupon_performance")
    op.drop_index("ix_user_coupon_performance_user_coupon_id", table_name="user_coupon_performance")
    op.drop_table("user_coupon_performance")

    op.drop_index("ix_user_coupons_weekly_pool_id", table_name="user_coupons")
    op.drop_index("ix_user_coupons_user_id", table_name="user_coupons")
    op.drop_table("user_coupons")

    # Drop added columns from users in reverse order
    op.drop_column("users", "subscription_expires_at")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
    op.drop_column("users", "display_name")
    op.drop_column("users", "role")
