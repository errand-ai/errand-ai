"""add retry_count to tasks

Revision ID: 008
Revises: 007
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("tasks", "retry_count")
