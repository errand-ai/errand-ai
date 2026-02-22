"""migrate tasks with status 'new' to 'review'

Revision ID: 011
Revises: 010
"""
from alembic import op

revision = "011"
down_revision = "010"


def upgrade():
    op.execute("UPDATE tasks SET status = 'review' WHERE status = 'new'")
    op.alter_column("tasks", "status", server_default="'review'")


def downgrade():
    op.alter_column("tasks", "status", server_default="'new'")
    op.execute("UPDATE tasks SET status = 'new' WHERE status = 'review'")
