"""create model_metadata_cache table

Revision ID: 022
Revises: 021
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"


def upgrade() -> None:
    op.create_table(
        "model_metadata_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("supports_reasoning", sa.Boolean(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("source_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )


def downgrade() -> None:
    op.drop_table("model_metadata_cache")
