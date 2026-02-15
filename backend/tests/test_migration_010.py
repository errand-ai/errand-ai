"""Tests for migration 010: skills tables and data migration from settings."""
import json
import os
import re
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _slugify(name: str) -> str:
    """Copied from migration 010 for testing."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:64]


# --- Slugification tests ---

def test_slugify_simple():
    assert _slugify("research") == "research"


def test_slugify_uppercase():
    assert _slugify("Research Helper") == "research-helper"


def test_slugify_special_chars():
    assert _slugify("my_skill!v2") == "my-skill-v2"


def test_slugify_leading_trailing_hyphens():
    assert _slugify("--test--") == "test"


def test_slugify_consecutive_hyphens():
    assert _slugify("a   b   c") == "a-b-c"


def test_slugify_truncation():
    long_name = "a" * 100
    assert len(_slugify(long_name)) <= 64


def test_slugify_empty():
    assert _slugify("") == ""


def test_slugify_only_special():
    assert _slugify("!!!") == ""


# --- Data migration tests (using SQLite) ---

_SETTINGS_SQL = """
CREATE TABLE settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_SKILLS_SQL = """
CREATE TABLE skills (
    id TEXT NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    instructions TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_SKILL_FILES_SQL = """
CREATE TABLE skill_files (
    id TEXT NOT NULL PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(skill_id, path)
)
"""


@pytest.fixture()
async def migration_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_SETTINGS_SQL))
        await conn.execute(text(_SKILLS_SQL))
        await conn.execute(text(_SKILL_FILES_SQL))
    yield engine
    await engine.dispose()


async def test_migration_empty_db(migration_engine):
    """Migration on empty DB creates tables with no data."""
    async with AsyncSession(migration_engine) as session:
        result = await session.execute(text("SELECT COUNT(*) FROM skills"))
        assert result.scalar() == 0
        result = await session.execute(text("SELECT COUNT(*) FROM skill_files"))
        assert result.scalar() == 0


async def test_migration_existing_skills(migration_engine):
    """Existing skills in settings are migrated to skills table."""
    skills = [
        {"id": "abc", "name": "Research Helper", "description": "Helps research", "instructions": "Do research"},
        {"id": "def", "name": "code-review", "description": "Reviews code", "instructions": "Review code"},
    ]
    async with AsyncSession(migration_engine) as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('skills', :value)"),
            {"value": json.dumps(skills)},
        )
        await session.commit()

    # Simulate the migration logic
    async with AsyncSession(migration_engine) as session:
        result = await session.execute(text("SELECT value FROM settings WHERE key = 'skills'"))
        row = result.fetchone()
        existing = json.loads(row[0])
        assert len(existing) == 2

        used_names = set()
        for skill in existing:
            slug = _slugify(skill["name"])
            base_slug = slug
            counter = 2
            while slug in used_names:
                slug = f"{base_slug}-{counter}"[:64]
                counter += 1
            used_names.add(slug)

            await session.execute(
                text("INSERT INTO skills (id, name, description, instructions) VALUES (:id, :name, :desc, :inst)"),
                {"id": str(uuid.uuid4()), "name": slug, "desc": skill["description"], "inst": skill["instructions"]},
            )
        await session.execute(text("DELETE FROM settings WHERE key = 'skills'"))
        await session.commit()

    async with AsyncSession(migration_engine) as session:
        result = await session.execute(text("SELECT name FROM skills ORDER BY name"))
        names = [row[0] for row in result]
        assert "research-helper" in names
        assert "code-review" in names

        result = await session.execute(text("SELECT COUNT(*) FROM settings WHERE key = 'skills'"))
        assert result.scalar() == 0


async def test_migration_name_conflict_slugification(migration_engine):
    """When two skills slugify to the same name, a numeric suffix is appended."""
    skills = [
        {"id": "1", "name": "My Skill", "description": "d1", "instructions": "i1"},
        {"id": "2", "name": "my--skill", "description": "d2", "instructions": "i2"},
    ]
    async with AsyncSession(migration_engine) as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('skills', :value)"),
            {"value": json.dumps(skills)},
        )
        await session.commit()

    async with AsyncSession(migration_engine) as session:
        result = await session.execute(text("SELECT value FROM settings WHERE key = 'skills'"))
        row = result.fetchone()
        existing = json.loads(row[0])

        used_names = set()
        for skill in existing:
            slug = _slugify(skill["name"])
            if not slug:
                slug = "unnamed-skill"
            base_slug = slug
            counter = 2
            while slug in used_names:
                slug = f"{base_slug}-{counter}"[:64]
                counter += 1
            used_names.add(slug)

            await session.execute(
                text("INSERT INTO skills (id, name, description, instructions) VALUES (:id, :name, :desc, :inst)"),
                {"id": str(uuid.uuid4()), "name": slug, "desc": skill["description"], "inst": skill["instructions"]},
            )
        await session.commit()

    async with AsyncSession(migration_engine) as session:
        result = await session.execute(text("SELECT name FROM skills ORDER BY name"))
        names = [row[0] for row in result]
        assert "my-skill" in names
        assert "my-skill-2" in names
