"""Tests for zombie task detection and recovery."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

import events as events_module
import zombie_cleanup as zombie_module
from models import Task
from zombie_cleanup import (
    acquire_zombie_lock,
    recover_zombie_tasks,
)


# --- Helpers ---

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
            include_git_skills BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_TASKS_TABLE_SQL))
        await conn.execute(text(_TAGS_TABLE_SQL))
        await conn.execute(text(_TASK_TAGS_TABLE_SQL))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    with patch.object(zombie_module, "async_session", session_factory):
        yield session_factory
    await engine.dispose()


@pytest.fixture()
async def fake_valkey():
    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis
    yield redis
    events_module._valkey = None
    await redis.aclose()


def _fmt_dt(dt: datetime) -> str:
    """Format datetime for SQLite storage (no timezone suffix, UTC assumed)."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def _insert_task(session_factory, **overrides) -> str:
    defaults = {
        "id": uuid.uuid4().hex,
        "title": "Test task",
        "status": "running",
        "category": "immediate",
        "position": 0,
        "retry_count": 0,
        "created_at": _fmt_dt(datetime.now(timezone.utc)),
        "updated_at": _fmt_dt(datetime.now(timezone.utc)),
    }
    defaults.update(overrides)
    # Format datetime values
    for key in ("heartbeat_at", "updated_at", "created_at", "execute_at"):
        if key in defaults and isinstance(defaults[key], datetime):
            defaults[key] = _fmt_dt(defaults[key])
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f":{k}" for k in defaults.keys())
    async with session_factory() as session:
        await session.execute(text(f"INSERT INTO tasks ({cols}) VALUES ({placeholders})"), defaults)
        await session.commit()
    return defaults["id"]


async def _get_task(session_factory, task_id):
    async with session_factory() as session:
        result = await session.execute(text("SELECT * FROM tasks WHERE id = :id"), {"id": task_id})
        return result.mappings().first()


# --- Stale task recovered to scheduled ---


@pytest.mark.asyncio
async def test_stale_running_task_recovered_to_scheduled(db_session, fake_valkey):
    """A running task with stale heartbeat is moved to scheduled with backoff."""
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
    task_id = await _insert_task(db_session, status="running", heartbeat_at=stale_time, retry_count=0)

    count = await recover_zombie_tasks()

    assert count == 1
    task = await _get_task(db_session, task_id)
    assert task["status"] == "scheduled"
    assert task["retry_count"] == 1
    assert task["execute_at"] is not None
    assert task["heartbeat_at"] is None


# --- Fresh running task left alone ---


@pytest.mark.asyncio
async def test_fresh_running_task_not_recovered(db_session, fake_valkey):
    """A running task with recent heartbeat is NOT recovered."""
    fresh_time = datetime.now(timezone.utc) - timedelta(seconds=30)
    task_id = await _insert_task(db_session, status="running", heartbeat_at=fresh_time)

    count = await recover_zombie_tasks()

    assert count == 0
    task = await _get_task(db_session, task_id)
    assert task["status"] == "running"


# --- NULL heartbeat fallback to updated_at ---


@pytest.mark.asyncio
async def test_null_heartbeat_falls_back_to_updated_at(db_session, fake_valkey):
    """A running task with NULL heartbeat but stale updated_at is treated as zombie."""
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
    task_id = await _insert_task(db_session, status="running", updated_at=stale_time)

    count = await recover_zombie_tasks()

    assert count == 1
    task = await _get_task(db_session, task_id)
    assert task["status"] == "scheduled"
    assert task["retry_count"] == 1


@pytest.mark.asyncio
async def test_null_heartbeat_fresh_updated_at_not_recovered(db_session, fake_valkey):
    """A running task with NULL heartbeat but recent updated_at is NOT recovered."""
    fresh_time = datetime.now(timezone.utc) - timedelta(seconds=30)
    task_id = await _insert_task(db_session, status="running", updated_at=fresh_time)

    count = await recover_zombie_tasks()

    assert count == 0
    task = await _get_task(db_session, task_id)
    assert task["status"] == "running"


# --- Max retries → review ---


@pytest.mark.asyncio
async def test_exhausted_retries_moved_to_review(db_session, fake_valkey):
    """A zombie task with retry_count >= 5 is moved to review instead of scheduled."""
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
    task_id = await _insert_task(db_session, status="running", heartbeat_at=stale_time, retry_count=5)

    count = await recover_zombie_tasks()

    assert count == 1
    task = await _get_task(db_session, task_id)
    assert task["status"] == "review"
    assert "zombie" in task["output"].lower()
    assert task["heartbeat_at"] is None


# --- Exponential backoff ---


@pytest.mark.asyncio
async def test_exponential_backoff_formula(db_session, fake_valkey):
    """Recovered task has execute_at set with 2^retry_count minute backoff."""
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
    task_id = await _insert_task(db_session, status="running", heartbeat_at=stale_time, retry_count=3)

    now_before = datetime.now(timezone.utc)
    count = await recover_zombie_tasks()

    assert count == 1
    task = await _get_task(db_session, task_id)
    assert task["status"] == "scheduled"
    assert task["retry_count"] == 4
    # 2^3 = 8 minutes backoff
    execute_at_str = task["execute_at"]
    execute_at = datetime.fromisoformat(str(execute_at_str))
    if execute_at.tzinfo is None:
        execute_at = execute_at.replace(tzinfo=timezone.utc)
    expected_min = now_before + timedelta(minutes=7)
    expected_max = now_before + timedelta(minutes=9)
    assert expected_min <= execute_at <= expected_max


# --- WebSocket event published ---


@pytest.mark.asyncio
async def test_websocket_event_published_on_recovery(db_session, fake_valkey):
    """A task_updated event is published for each recovered zombie task."""
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
    await _insert_task(db_session, status="running", heartbeat_at=stale_time)
    await _insert_task(db_session, status="running", heartbeat_at=stale_time)

    with patch.object(zombie_module, "publish_event", new_callable=AsyncMock) as mock_publish:
        count = await recover_zombie_tasks()

    assert count == 2
    assert mock_publish.call_count == 2
    for call in mock_publish.call_args_list:
        assert call[0][0] == "task_updated"


# --- Non-running tasks ignored ---


@pytest.mark.asyncio
async def test_non_running_tasks_ignored(db_session, fake_valkey):
    """Tasks not in running status are never touched by zombie cleanup."""
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
    await _insert_task(db_session, status="scheduled", heartbeat_at=stale_time)
    await _insert_task(db_session, status="pending", heartbeat_at=stale_time)
    await _insert_task(db_session, status="completed", heartbeat_at=stale_time)

    count = await recover_zombie_tasks()

    assert count == 0


# --- Distributed lock ---


@pytest.mark.asyncio
async def test_acquire_zombie_lock_with_valkey(fake_valkey):
    """Lock acquisition works with Valkey available."""
    result = await acquire_zombie_lock()
    assert result is True


@pytest.mark.asyncio
async def test_acquire_zombie_lock_without_valkey():
    """Lock acquisition fails gracefully when Valkey is unavailable."""
    with patch.object(zombie_module, "get_valkey", return_value=None):
        result = await acquire_zombie_lock()
    assert result is False
