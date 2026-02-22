"""create platform_credentials table

Revision ID: 012
Revises: 011
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"


def upgrade() -> None:
    op.create_table(
        "platform_credentials",
        sa.Column("platform_id", sa.Text(), primary_key=True),
        sa.Column("encrypted_data", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="disconnected"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_credentials")
