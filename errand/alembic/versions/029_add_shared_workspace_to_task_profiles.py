"""add shared workspace columns to task_profiles

Revision ID: 029
Revises: 028
"""

from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"


def upgrade() -> None:
    op.add_column(
        "task_profiles",
        sa.Column(
            "shared_workspace_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "task_profiles",
        sa.Column("shared_workspace_subpath", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_profiles", "shared_workspace_subpath")
    op.drop_column("task_profiles", "shared_workspace_enabled")
