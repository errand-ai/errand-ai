"""create task_profiles table and add profile_id to tasks

Revision ID: 018
Revises: 017
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"


def upgrade() -> None:
    op.create_table(
        "task_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("match_rules", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("max_turns", sa.Integer(), nullable=True),
        sa.Column("reasoning_effort", sa.Text(), nullable=True),
        sa.Column("mcp_servers", sa.JSON(), nullable=True),
        sa.Column("litellm_mcp_servers", sa.JSON(), nullable=True),
        sa.Column("skill_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.add_column("tasks", sa.Column("profile_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_tasks_profile_id",
        "tasks",
        "task_profiles",
        ["profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_tasks_profile_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "profile_id")
    op.drop_table("task_profiles")
