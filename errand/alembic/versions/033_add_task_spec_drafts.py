"""add task_spec_drafts

Revision ID: 033
Revises: 032

Tasks being clarified before they exist. Additive and self-contained: nothing
reads these rows except the intake flow, and a draft left behind only ever
becomes `abandoned` and is swept.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "033"
down_revision = "032"


def upgrade() -> None:
    op.create_table(
        "task_spec_drafts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("conversation", sa.JSON(), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=True),
        sa.Column("questions_unresolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_channel_id", sa.Text(), nullable=True),
        sa.Column("external_message_ts", sa.Text(), nullable=True),
        sa.Column(
            "resolved_task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('drafting', 'ready', 'confirmed', 'abandoned')",
            name="ck_task_spec_drafts_status",
        ),
    )
    op.create_index("ix_task_spec_drafts_owner_id", "task_spec_drafts", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_task_spec_drafts_owner_id", table_name="task_spec_drafts")
    op.drop_table("task_spec_drafts")
