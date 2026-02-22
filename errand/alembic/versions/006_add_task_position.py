"""add position column to tasks

Revision ID: 006
Revises: 005
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("position", sa.Integer, nullable=True))

    # Backfill positions per status group ordered by created_at
    op.execute("""
        UPDATE tasks SET position = sub.row_num
        FROM (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY status ORDER BY created_at) AS row_num
            FROM tasks
        ) sub
        WHERE tasks.id = sub.id
    """)

    # Set NOT NULL with default 0
    op.alter_column("tasks", "position", nullable=False, server_default=sa.text("0"))


def downgrade() -> None:
    op.drop_column("tasks", "position")
