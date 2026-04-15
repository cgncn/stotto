"""score_change_log coverage_pick varchar(2) -> varchar(3)

Revision ID: 007
Revises: 006
Create Date: 2026-04-15
"""
from alembic import op

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("ALTER TABLE score_change_log ALTER COLUMN old_coverage_pick TYPE VARCHAR(3)")
    op.execute("ALTER TABLE score_change_log ALTER COLUMN new_coverage_pick TYPE VARCHAR(3)")

def downgrade():
    op.execute("ALTER TABLE score_change_log ALTER COLUMN old_coverage_pick TYPE VARCHAR(2)")
    op.execute("ALTER TABLE score_change_log ALTER COLUMN new_coverage_pick TYPE VARCHAR(2)")
