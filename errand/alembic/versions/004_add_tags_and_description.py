"""add tags, task_tags tables and description column to tasks

Revision ID: 004
Revises: 003
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add description column to tasks
    op.add_column("tasks", sa.Column("description", sa.Text, nullable=True))

    # Create tags table
    op.create_table(
        "tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text, nullable=False, unique=True),
    )

    # Create task_tags join table
    op.create_table(
        "task_tags",
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    # Migrate need-input tasks: create "Needs Info" tag, link tasks, update status
    op.execute(
        "INSERT INTO tags (id, name) VALUES (gen_random_uuid(), 'Needs Info') ON CONFLICT (name) DO NOTHING"
    )
    op.execute(
        """
        INSERT INTO task_tags (task_id, tag_id)
        SELECT t.id, tags.id
        FROM tasks t, tags
        WHERE t.status = 'need-input' AND tags.name = 'Needs Info'
        """
    )
    op.execute("UPDATE tasks SET status = 'new' WHERE status = 'need-input'")


def downgrade() -> None:
    # Restore need-input status for tasks that had "Needs Info" tag
    op.execute(
        """
        UPDATE tasks SET status = 'need-input'
        WHERE id IN (
            SELECT tt.task_id FROM task_tags tt
            JOIN tags ON tags.id = tt.tag_id
            WHERE tags.name = 'Needs Info'
        )
        """
    )
    op.drop_table("task_tags")
    op.drop_table("tags")
    op.drop_column("tasks", "description")
