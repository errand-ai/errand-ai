"""create marketplaces and plugins tables, add enabled_plugins to task_profiles, seed Anthropic marketplace

Revision ID: 028
Revises: 027
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "028"
down_revision = "027"


def upgrade() -> None:
    op.create_table(
        "marketplaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=True),
        sa.Column("auth_token_encrypted", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("predefined", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cached_manifest", JSONB(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.Text(), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("source_type IN ('github','git','http','local')", name="ck_marketplaces_source_type"),
    )

    op.create_table(
        "plugins",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("marketplace_id", UUID(as_uuid=True),
                  sa.ForeignKey("marketplaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("plugin_name", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("ref", sa.Text(), nullable=True),
        sa.Column("auth_token_encrypted", sa.Text(), nullable=True),
        sa.Column("installed_version", sa.Text(), nullable=False),
        sa.Column("latest_available_version", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("manifest", JSONB(), nullable=True),
        sa.Column("ignored_artifacts", JSONB(), nullable=True),
        sa.Column("skill_conflicts", JSONB(), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("marketplace_id", "plugin_name", name="uq_plugins_marketplace_name"),
    )

    # Postgres treats NULLs as distinct in UNIQUE constraints, so manual installs
    # (marketplace_id IS NULL) could otherwise have duplicate plugin_name rows.
    # A partial unique index enforces uniqueness on the manual-install slice.
    op.create_index(
        "uq_plugins_manual_name",
        "plugins",
        ["plugin_name"],
        unique=True,
        postgresql_where=sa.text("marketplace_id IS NULL"),
    )

    op.add_column(
        "task_profiles",
        sa.Column("enabled_plugins", sa.JSON(), nullable=True),
    )

    op.execute(
        sa.text(
            "INSERT INTO marketplaces (id, name, source_type, source_url, enabled, predefined) "
            "VALUES (:id, :name, :source_type, :source_url, :enabled, :predefined)"
        ).bindparams(
            id=uuid.uuid4(),
            name="anthropics/claude-plugins-official",
            source_type="github",
            source_url="anthropics/claude-plugins-official",
            enabled=False,
            predefined=True,
        )
    )


def downgrade() -> None:
    op.drop_column("task_profiles", "enabled_plugins")
    op.drop_index("uq_plugins_manual_name", table_name="plugins")
    op.drop_table("plugins")
    op.drop_table("marketplaces")
