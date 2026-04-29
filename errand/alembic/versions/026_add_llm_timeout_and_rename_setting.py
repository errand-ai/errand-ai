"""add llm_timeout column to task_profiles and rename llm_timeout setting

Revision ID: 026
Revises: 025
"""

from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"


def upgrade() -> None:
    op.add_column(
        "task_profiles",
        sa.Column("llm_timeout", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE settings SET key = 'title_generation_timeout' "
        "WHERE key = 'llm_timeout'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE settings SET key = 'llm_timeout' "
        "WHERE key = 'title_generation_timeout'"
    )
    op.drop_column("task_profiles", "llm_timeout")
