"""add mode to model_metadata_cache

Revision ID: 032
Revises: 031

A plain OpenAI-compatible `/v1/models` listing says nothing about what a model
is for, so chat and embedding models arrive indistinguishable. The LiteLLM
registry this table caches records a `mode` per model; this column carries it
through so the distinction survives the lookup.

Nullable, because the registry itself leaves `mode` unset for some entries and
an unknown mode is a real answer — a model whose mode we cannot establish must
stay selectable rather than be filtered away as the wrong kind.

Existing rows land with NULL and are filled by the next registry refresh, which
runs on staleness within the hour.
"""

import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_metadata_cache",
        sa.Column("mode", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_metadata_cache", "mode")
