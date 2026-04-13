"""coverage_pick_length

Revision ID: 005
Revises: 004
Create Date: 2026-04-13 00:00:00.000000

Extends coverage_pick from VARCHAR(2) to VARCHAR(3) so that '1X2'
(triple coverage, all three outcomes) can be stored without truncation.
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "match_model_scores",
        "coverage_pick",
        type_=sa.String(3),
        existing_type=sa.String(2),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "match_model_scores",
        "coverage_pick",
        type_=sa.String(2),
        existing_type=sa.String(3),
        existing_nullable=True,
    )
