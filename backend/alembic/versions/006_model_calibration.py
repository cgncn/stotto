"""model_calibration

Revision ID: 006
Revises: 005
Create Date: 2026-04-14 00:00:00.000000

Adds model_calibration table to store per-signal weight multipliers
produced by the automatic gradient-based calibration system.
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_calibration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("applied_by", sa.String(20), nullable=False, server_default="auto"),
        # JSON: {"score_1": {signal: multiplier}, "score_x": {...}, "score_2": {...}}
        sa.Column("multipliers", sa.JSON(), nullable=False),
        sa.Column("brier_before", sa.Float()),
        sa.Column("brier_after", sa.Float()),
        sa.Column("n_matches", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_model_calibration_is_active", "model_calibration", ["is_active"])


def downgrade():
    op.drop_index("ix_model_calibration_is_active", "model_calibration")
    op.drop_table("model_calibration")
