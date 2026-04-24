"""Tests for RBAC and task lifecycle features."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
import scheduler as scheduler_module
from models import Setting, Task
from scheduler import archive_completed_tasks


async def create_task(client: AsyncClient, input_text: str = "Test task") -> dict:
    resp = await client.post("/api/tasks", json={"input": input_text})
    assert resp.status_code == 201
    return resp.json()


# --- 10.1 Test require_editor ---


async def test_editor_can_create_task(client: AsyncClient):
    """Editor role is allowed to create tasks."""
    resp = await client.post("/api/tasks", json={"input": "Editor task"})
    assert resp.status_code == 201


async def test_admin_can_create_task(admin_client: AsyncClient):
    """Admin role is allowed to create tasks."""
    resp = await admin_client.post("/api/tasks", json={"input": "Admin task"})
    assert resp.status_code == 201


async def test_viewer_cannot_create_task(viewer_client: AsyncClient):
    """Viewer role is denied from creating tasks (403)."""
    resp = await viewer_client.post("/api/tasks", json={"input": "Viewer task"})
    assert resp.status_code == 403


async def test_viewer_cannot_update_task(client: AsyncClient, viewer_client: AsyncClient):
    """Viewer role is denied from updating tasks (403)."""
    # Create task with editor client (separate DB — need to test the 403 response directly)
    resp = await viewer_client.patch(
        f"/api/tasks/00000000-0000-0000-0000-000000000001",
        json={"title": "Updated"},
    )
    assert resp.status_code == 403


async def test_viewer_cannot_delete_task(viewer_client: AsyncClient):
    """Viewer role is denied from deleting tasks (403)."""
    resp = await viewer_client.delete(
        f"/api/tasks/00000000-0000-0000-0000-000000000001"
    )
    assert resp.status_code == 403


async def test_unauthenticated_cannot_create_task(unauth_client: AsyncClient):
    """Unauthenticated request is denied (401)."""
    resp = await unauth_client.post("/api/tasks", json={"input": "No auth"})
    assert resp.status_code in (401, 403)


# --- 10.2 Test soft delete ---


async def test_soft_delete_changes_status(client: AsyncClient):
    """DELETE sets task status to 'deleted' instead of removing the row."""
    task = await create_task(client, "Soft delete me")
    resp = await client.delete(f"/api/tasks/{task['id']}")
    assert resp.status_code == 204

    # Task still exists via direct GET
    resp = await client.get(f"/api/tasks/{task['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


async def test_soft_delete_preserves_tags(client: AsyncClient):
    """Soft-deleted task still has its tags."""
    task = await create_task(client, "Tag test")
    # Add a tag
    await client.patch(f"/api/tasks/{task['id']}", json={"tags": ["important"]})

    await client.delete(f"/api/tasks/{task['id']}")

    resp = await client.get(f"/api/tasks/{task['id']}")
    data = resp.json()
    assert data["status"] == "deleted"
    assert "important" in data["tags"]


async def test_soft_delete_returns_204(client: AsyncClient):
    """DELETE still returns 204 after soft delete."""
    task = await create_task(client, "Return code test")
    resp = await client.delete(f"/api/tasks/{task['id']}")
    assert resp.status_code == 204


async def test_soft_delete_publishes_event(client: AsyncClient, fake_valkey):
    """DELETE publishes task_deleted event."""
    task = await create_task(client, "Event test")

    pubsub = fake_valkey.pubsub()
    await pubsub.subscribe("task_events")
    await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

    await client.delete(f"/api/tasks/{task['id']}")

    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
    assert msg is not None
    data = json.loads(msg["data"])
    assert data["event"] == "task_deleted"
    assert data["task"]["id"] == task["id"]

    await pubsub.unsubscribe("task_events")
    await pubsub.aclose()


# --- 10.3 Test list_tasks excludes deleted and archived ---


async def test_list_tasks_excludes_deleted(client: AsyncClient):
    """Deleted tasks are not returned by GET /api/tasks."""
    task = await create_task(client, "Hide me")
    await client.delete(f"/api/tasks/{task['id']}")

    resp = await client.get("/api/tasks")
    data = resp.json()
    task_ids = [t["id"] for t in data]
    assert task["id"] not in task_ids


async def test_list_tasks_excludes_archived(client: AsyncClient):
    """Archived tasks are not returned by GET /api/tasks."""
    task = await create_task(client, "Archive me")
    # Manually set status to archived via PATCH
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "archived"})

    resp = await client.get("/api/tasks")
    data = resp.json()
    task_ids = [t["id"] for t in data]
    assert task["id"] not in task_ids


# --- 10.4 Test archived endpoint ---


async def test_archived_endpoint_admin_sees_deleted_and_archived(admin_client: AsyncClient):
    """Admin sees both deleted and archived tasks at /api/tasks/archived."""
    task1 = await create_task(admin_client, "Archived task")
    task2 = await create_task(admin_client, "Deleted task")

    await admin_client.patch(f"/api/tasks/{task1['id']}", json={"status": "archived"})
    await admin_client.delete(f"/api/tasks/{task2['id']}")

    resp = await admin_client.get("/api/tasks/archived")
    assert resp.status_code == 200
    data = resp.json()
    statuses = [t["status"] for t in data]
    assert "archived" in statuses
    assert "deleted" in statuses


async def test_archived_endpoint_non_admin_sees_only_archived(client: AsyncClient):
    """Non-admin sees only archived tasks, not deleted ones."""
    task1 = await create_task(client, "Archived task")
    task2 = await create_task(client, "Deleted task")

    await client.patch(f"/api/tasks/{task1['id']}", json={"status": "archived"})
    await client.delete(f"/api/tasks/{task2['id']}")

    resp = await client.get("/api/tasks/archived")
    assert resp.status_code == 200
    data = resp.json()
    statuses = [t["status"] for t in data]
    assert "archived" in statuses
    assert "deleted" not in statuses


# --- 10.5 Test running task PATCH guard ---


async def test_running_task_patch_returns_409(client: AsyncClient):
    """PATCH on a running task returns 409."""
    task = await create_task(client, "Running task")
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "running"})

    resp = await client.patch(f"/api/tasks/{task['id']}", json={"title": "Updated"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Cannot edit a running task"


async def test_non_running_task_patch_allowed(client: AsyncClient):
    """PATCH on a non-running task is allowed."""
    task = await create_task(client, "Pending task")
    await client.patch(f"/api/tasks/{task['id']}", json={"status": "pending"})

    resp = await client.patch(f"/api/tasks/{task['id']}", json={"title": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"


# --- 10.6 Test scheduler auto-archive ---

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


@pytest.fixture()
async def archive_db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_TASKS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))
        await conn.execute(text(_TAGS_TABLE_SQL))
        await conn.execute(text(_TASK_TAGS_TABLE_SQL))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    with patch.object(scheduler_module, "async_session", session_factory):
        yield session_factory
    await engine.dispose()


@pytest.fixture()
async def archive_valkey():
    from fakeredis.aioredis import FakeRedis
    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis
    yield redis
    events_module._valkey = None
    await redis.aclose()


async def _insert_task(session_factory, **overrides):
    defaults = {
        "id": uuid.uuid4().hex,
        "title": "Test task",
        "status": "completed",
        "category": "immediate",
        "position": 0,
        "retry_count": 0,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f":{k}" for k in defaults.keys())
    async with session_factory() as session:
        await session.execute(text(f"INSERT INTO tasks ({cols}) VALUES ({placeholders})"), defaults)
        await session.commit()
    return defaults["id"]


@pytest.mark.asyncio
async def test_auto_archive_old_completed_tasks(archive_db_session, archive_valkey):
    """Completed task older than archive interval is archived."""
    old_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    task_id = await _insert_task(archive_db_session, status="completed", updated_at=old_date)

    count = await archive_completed_tasks()

    assert count == 1
    async with archive_db_session() as session:
        result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id})
        assert result.scalar() == "archived"


@pytest.mark.asyncio
async def test_auto_archive_does_not_archive_recent_completed(archive_db_session, archive_valkey):
    """Recent completed task is not archived."""
    recent_date = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    task_id = await _insert_task(archive_db_session, status="completed", updated_at=recent_date)

    count = await archive_completed_tasks()

    assert count == 0
    async with archive_db_session() as session:
        result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id})
        assert result.scalar() == "completed"
