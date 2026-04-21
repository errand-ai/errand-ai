"""add encrypted_env column to tasks table

Revision ID: 024
Revises: 023
"""

from alembic import op
import sqlalchemy as sa

revision = "024"
down_revision = "023"


def upgrade() -> None:
    op.add_column("tasks", sa.Column("encrypted_env", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "encrypted_env")
