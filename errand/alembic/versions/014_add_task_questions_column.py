"""add questions column to tasks table

Revision ID: 014
Revises: 013
"""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("questions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "questions")
