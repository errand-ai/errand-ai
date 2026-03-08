"""Convert task_profiles.model from Text to JSONB for provider-scoped models.

Existing string values like "gpt-4o" become {"provider_id": null, "model": "gpt-4o"}.

Revision ID: 020
Revises: 019
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add a temporary JSONB column
    op.add_column("task_profiles", sa.Column("model_new", postgresql.JSONB(), nullable=True))

    # Step 2: Migrate existing string values to {provider_id: null, model: "old-value"}
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE task_profiles
            SET model_new = jsonb_build_object('provider_id', NULL, 'model', model)
            WHERE model IS NOT NULL
            """
        )
    )

    # Step 3: Drop old column, rename new
    op.drop_column("task_profiles", "model")
    op.alter_column("task_profiles", "model_new", new_column_name="model")


def downgrade() -> None:
    # Step 1: Add a temporary Text column
    op.add_column("task_profiles", sa.Column("model_old", sa.Text(), nullable=True))

    # Step 2: Extract model string from JSON
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE task_profiles
            SET model_old = model->>'model'
            WHERE model IS NOT NULL
            """
        )
    )

    # Step 3: Drop old column, rename new
    op.drop_column("task_profiles", "model")
    op.alter_column("task_profiles", "model_old", new_column_name="model")
