"""create skills and skill_files tables, migrate existing skills from settings

Revision ID: 010
Revises: 009
"""
import json
import re

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "010"
down_revision = "009"


def _slugify(name: str) -> str:
    """Convert a skill name to Agent Skills compliant slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:64]


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "skill_files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("skill_id", UUID(as_uuid=True), sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("skill_id", "path", name="uq_skill_files_skill_id_path"),
    )

    # Data migration: move existing skills from settings to skills table
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT value FROM settings WHERE key = 'skills'")
    )
    row = result.fetchone()
    if row:
        try:
            skills = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except (json.JSONDecodeError, TypeError):
            skills = []

        if isinstance(skills, list):
            used_names: set[str] = set()
            for skill in skills:
                if not isinstance(skill, dict):
                    continue
                raw_name = skill.get("name", "")
                slug = _slugify(raw_name)
                if not slug:
                    slug = "unnamed-skill"

                # Handle name conflicts
                base_slug = slug
                counter = 2
                while slug in used_names:
                    slug = f"{base_slug}-{counter}"[:64]
                    counter += 1
                used_names.add(slug)

                import uuid
                skill_id = str(uuid.uuid4())
                description = skill.get("description", "")
                instructions = skill.get("instructions", "")

                conn.execute(
                    sa.text(
                        "INSERT INTO skills (id, name, description, instructions) "
                        "VALUES (:id, :name, :description, :instructions)"
                    ),
                    {"id": skill_id, "name": slug, "description": description, "instructions": instructions},
                )

        # Remove the skills key from settings
        conn.execute(sa.text("DELETE FROM settings WHERE key = 'skills'"))


def downgrade() -> None:
    # Move skills back to settings before dropping tables
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT name, description, instructions FROM skills ORDER BY name"))
    skills = []
    for row in result:
        import uuid
        skills.append({
            "id": str(uuid.uuid4()),
            "name": row[0],
            "description": row[1],
            "instructions": row[2],
        })
    if skills:
        conn.execute(
            sa.text("INSERT INTO settings (key, value) VALUES ('skills', :value)"),
            {"value": json.dumps(skills)},
        )

    op.drop_table("skill_files")
    op.drop_table("skills")
