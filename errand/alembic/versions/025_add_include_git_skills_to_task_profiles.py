"""add include_git_skills column to task_profiles table

Revision ID: 025
Revises: 024
"""

from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"


def upgrade() -> None:
    op.add_column(
        "task_profiles",
        sa.Column(
            "include_git_skills",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("task_profiles", "include_git_skills")
