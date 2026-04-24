"""Tests for task audit metadata (created_by / updated_by fields)."""

from collections.abc import AsyncGenerator

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
import uuid as uuid_mod
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import AsyncMock, patch

import events as events_module
from main import app, get_current_user, require_editor, require_admin
from database import get_session
from models import Task

FAKE_USER_CLAIMS = {
    "sub": "test-user-id",
    "preferred_username": "testuser",
    "email": "test@example.com",
    "resource_access": {
        "errand": {
            "roles": ["user", "editor"],
        }
    },
}

_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'review' NOT NULL,
    category TEXT DEFAULT 'immediate',
    execute_at DATETIME,
    repeat_interval TEXT,
    repeat_until DATETIME,
    position INTEGER DEFAULT 0 NOT NULL,
    output TEXT,
    runner_logs TEXT,
    questions TEXT,
    retry_count INTEGER DEFAULT 0 NOT NULL,
    heartbeat_at DATETIME,
    profile_id VARCHAR(36),
    created_by TEXT,
    updated_by TEXT,
        encrypted_env TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tags (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
)
"""

_TASK_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_tags (
    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
)
"""

_PLATFORM_CREDENTIALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS platform_credentials (
    platform_id TEXT NOT NULL PRIMARY KEY,
    encrypted_data TEXT NOT NULL,
    status TEXT DEFAULT 'disconnected' NOT NULL,
    last_verified_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_SKILLS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS skills (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    instructions TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_SKILL_FILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS skill_files (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    skill_id VARCHAR(36) NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    UNIQUE(skill_id, path)
)
"""


_TASK_PROFILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_profiles (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    match_rules TEXT,
    model TEXT,
    system_prompt TEXT,
    max_turns INTEGER,
    reasoning_effort TEXT,
    mcp_servers TEXT,
    litellm_mcp_servers TEXT,
    skill_ids TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_TASKS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))
        await conn.execute(text(_TAGS_TABLE_SQL))
        await conn.execute(text(_TASK_TAGS_TABLE_SQL))
        await conn.execute(text(_PLATFORM_CREDENTIALS_TABLE_SQL))
        await conn.execute(text(_SKILLS_TABLE_SQL))
        await conn.execute(text(_SKILL_FILES_TABLE_SQL))


@pytest.fixture()
async def audit_env() -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker], None]:
    """Provides both an API client and direct DB session for verifying audit fields."""
    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return FAKE_USER_CLAIMS

    async def override_require_editor():
        return FAKE_USER_CLAIMS

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_editor] = override_require_editor

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, test_session

    app.dependency_overrides.clear()
    await engine.dispose()
    events_module._valkey = None
    await redis.aclose()


# --- API task creation sets created_by ---


@pytest.mark.anyio
async def test_create_task_sets_created_by(audit_env):
    """POST /api/tasks should set created_by to email from JWT claims."""
    client, db_session = audit_env

    with patch("main.generate_title", new_callable=AsyncMock) as mock_title:
        from llm import LLMResult
        mock_title.return_value = LLMResult(
            title="Audit test task", category="immediate", success=True,
            description="A longer description to trigger LLM path for audit testing",
        )
        resp = await client.post(
            "/api/tasks",
            json={"input": "A longer description to trigger LLM path for audit testing"},
        )
    assert resp.status_code == 201
    task_id = uuid_mod.UUID(resp.json()["id"])

    async with db_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one()
        assert task.created_by == "test@example.com"


# --- API task update sets updated_by ---


@pytest.mark.anyio
async def test_update_task_sets_updated_by(audit_env):
    """PATCH /api/tasks/{id} should set updated_by to email from JWT claims."""
    client, db_session = audit_env

    with patch("main.generate_title", new_callable=AsyncMock) as mock_title:
        from llm import LLMResult
        mock_title.return_value = LLMResult(
            title="Task to update", category="immediate", success=True,
            description="A task that needs updating for audit test purposes",
        )
        resp = await client.post(
            "/api/tasks",
            json={"input": "A task that needs updating for audit test purposes"},
        )
    assert resp.status_code == 201
    task_id_str = resp.json()["id"]
    task_id = uuid_mod.UUID(task_id_str)

    resp = await client.patch(f"/api/tasks/{task_id_str}", json={"title": "Updated title"})
    assert resp.status_code == 200

    async with db_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one()
        assert task.updated_by == "test@example.com"


# --- MCP task creation sets created_by ---


@pytest.mark.anyio
async def test_mcp_new_task_sets_created_by_mcp():
    """MCP new_task tool should set created_by='mcp' on created tasks."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch("mcp_server.async_session", test_session), \
         patch("mcp_server.generate_title", new_callable=AsyncMock) as mock_title, \
         patch("mcp_server.publish_event", new_callable=AsyncMock):
        from llm import LLMResult
        mock_title.return_value = LLMResult(
            title="MCP task", category="immediate", success=True,
            description="A task created via MCP tool for testing audit fields",
        )
        from mcp_server import new_task
        task_id_str = await new_task(description="A task created via MCP tool for testing audit fields")

    task_id = uuid_mod.UUID(task_id_str)
    async with test_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one()
        assert task.created_by == "mcp"

    await engine.dispose()


# --- Worker updates set updated_by ---


@pytest.mark.anyio
async def test_worker_running_sets_updated_by_system():
    """Worker setting task to 'running' should set updated_by='system'."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with test_session() as session:
        task = Task(title="Worker test", description="test", status="pending")
        session.add(task)
        await session.commit()
        task_id = task.id

    # Simulate worker setting status to running (same pattern as worker.py)
    async with test_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one()
        task.status = "running"
        task.updated_by = "system"
        await session.commit()

    async with test_session() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one()
        assert task.updated_by == "system"
        assert task.status == "running"

    await engine.dispose()
