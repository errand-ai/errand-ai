"""add category, execute_at, repeat_interval, repeat_until to tasks

Revision ID: 005
Revises: 004
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("category", sa.Text, nullable=True, server_default=sa.text("'immediate'")))
    op.add_column("tasks", sa.Column("execute_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("repeat_interval", sa.Text, nullable=True))
    op.add_column("tasks", sa.Column("repeat_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "repeat_until")
    op.drop_column("tasks", "repeat_interval")
    op.drop_column("tasks", "execute_at")
    op.drop_column("tasks", "category")
