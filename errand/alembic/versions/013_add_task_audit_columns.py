"""add created_by and updated_by columns to tasks table

Revision ID: 013
Revises: 012
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("created_by", sa.Text(), nullable=True))
    op.add_column("tasks", sa.Column("updated_by", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "updated_by")
    op.drop_column("tasks", "created_by")
