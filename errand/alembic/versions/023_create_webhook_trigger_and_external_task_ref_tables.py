"""Create webhook_triggers and external_task_refs tables.

Revision ID: 023
Revises: 022
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_triggers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("profile_id", UUID(as_uuid=True), sa.ForeignKey("task_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filters", JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("actions", JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("task_prompt", sa.Text(), nullable=True),
        sa.Column("webhook_secret", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_webhook_triggers_source_enabled", "webhook_triggers", ["source", "enabled"])

    op.create_table(
        "external_task_refs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_id", UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("trigger_id", UUID(as_uuid=True), sa.ForeignKey("webhook_triggers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("external_url", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("external_id", "source", name="uq_external_task_ref_external_id_source"),
    )
    op.create_index("ix_external_task_refs_task_id", "external_task_refs", ["task_id"])
    op.create_index("ix_external_task_refs_external_id_source", "external_task_refs", ["external_id", "source"])


def downgrade() -> None:
    op.drop_table("external_task_refs")
    op.drop_table("webhook_triggers")
