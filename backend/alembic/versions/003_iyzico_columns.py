"""iyzico_columns

Revision ID: 003
Revises: 002
Create Date: 2026-04-06 00:00:00.000000
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old unique constraints before renaming
    op.drop_constraint("uq_users_stripe_customer_id", "users", type_="unique")
    op.drop_constraint("uq_users_stripe_subscription_id", "users", type_="unique")

    # Rename columns on users table
    op.alter_column("users", "stripe_customer_id", new_column_name="iyzico_customer_ref")
    op.alter_column("users", "stripe_subscription_id", new_column_name="iyzico_subscription_ref")

    # Re-create unique constraints with new names
    op.create_unique_constraint("uq_users_iyzico_customer_ref", "users", ["iyzico_customer_ref"])
    op.create_unique_constraint("uq_users_iyzico_subscription_ref", "users", ["iyzico_subscription_ref"])

    # Rename column on subscription_log table
    op.alter_column("subscription_log", "stripe_event_id", new_column_name="payment_event_ref")


def downgrade() -> None:
    op.alter_column("subscription_log", "payment_event_ref", new_column_name="stripe_event_id")

    op.drop_constraint("uq_users_iyzico_subscription_ref", "users", type_="unique")
    op.drop_constraint("uq_users_iyzico_customer_ref", "users", type_="unique")

    op.alter_column("users", "iyzico_subscription_ref", new_column_name="stripe_subscription_id")
    op.alter_column("users", "iyzico_customer_ref", new_column_name="stripe_customer_id")

    op.create_unique_constraint("uq_users_stripe_customer_id", "users", ["stripe_customer_id"])
    op.create_unique_constraint("uq_users_stripe_subscription_id", "users", ["stripe_subscription_id"])
