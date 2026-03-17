"""Create task_generators table and migrate email settings from credentials.

Revision ID: 021
Revises: 020
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Create the task_generators table
    op.create_table(
        "task_generators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("type", sa.Text(), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("task_profiles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Step 2: Migrate existing email credentials that have email_profile/poll_interval
    conn = op.get_bind()

    # Load the encryption module to decrypt/re-encrypt credentials
    from platforms.credentials import decrypt as decrypt_credentials, encrypt as encrypt_credentials

    rows = conn.execute(
        sa.text("SELECT platform_id, encrypted_data FROM platform_credentials WHERE platform_id = 'email'")
    ).fetchall()

    for row in rows:
        platform_id, encrypted_data = row
        try:
            creds = decrypt_credentials(encrypted_data)
        except Exception:
            continue

        email_profile = creds.pop("email_profile", None)
        poll_interval = creds.pop("poll_interval", None)

        if email_profile or poll_interval:
            # Create a task_generator record
            config = {}
            if poll_interval:
                try:
                    config["poll_interval"] = int(poll_interval)
                except (ValueError, TypeError):
                    config["poll_interval"] = 60

            conn.execute(
                sa.text(
                    """
                    INSERT INTO task_generators (type, enabled, profile_id, config)
                    VALUES ('email', true, :profile_id, :config)
                    """
                ),
                {
                    "profile_id": email_profile if email_profile else None,
                    "config": sa.type_coerce(config, postgresql.JSONB()),
                },
            )

            # Re-encrypt credentials without email_profile and poll_interval
            new_encrypted = encrypt_credentials(creds)
            conn.execute(
                sa.text(
                    "UPDATE platform_credentials SET encrypted_data = :data WHERE platform_id = :pid"
                ),
                {"data": new_encrypted, "pid": platform_id},
            )


def downgrade() -> None:
    # Note: downgrade doesn't attempt to move data back to credentials
    op.drop_table("task_generators")
