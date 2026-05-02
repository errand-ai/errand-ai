"""add cloud_webhook_url and cloud_endpoint_token columns to webhook_triggers

Revision ID: 027
Revises: 026
"""

from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"


def upgrade() -> None:
    op.add_column(
        "webhook_triggers",
        sa.Column("cloud_webhook_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "webhook_triggers",
        sa.Column("cloud_endpoint_token", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("webhook_triggers", "cloud_endpoint_token")
    op.drop_column("webhook_triggers", "cloud_webhook_url")
