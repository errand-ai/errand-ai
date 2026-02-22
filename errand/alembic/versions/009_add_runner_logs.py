"""add runner_logs to tasks

Revision ID: 009
Revises: 008
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("runner_logs", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "runner_logs")
