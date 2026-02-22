"""update task statuses and default

Revision ID: 002
Revises: 001
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Map failed tasks to new for triage
    op.execute(sa.text("UPDATE tasks SET status = 'new' WHERE status = 'failed'"))
    # Change the server default from 'pending' to 'new'
    op.alter_column("tasks", "status", server_default=sa.text("'new'"))


def downgrade() -> None:
    # Reverse: map new back to pending
    op.execute(sa.text("UPDATE tasks SET status = 'pending' WHERE status = 'new'"))
    # Restore original default
    op.alter_column("tasks", "status", server_default=sa.text("'pending'"))
