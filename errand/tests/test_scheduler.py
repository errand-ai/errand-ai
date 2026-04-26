"""Scheduler unit tests: promote_due_tasks, lock functions, events, resilience."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
import scheduler as scheduler_module
from models import Task
from scheduler import (
    acquire_lock,
    refresh_lock,
    release_lock,
    promote_due_tasks,
    LOCK_KEY,
    LOCK_TTL,
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
    with patch.object(scheduler_module, "async_session", session_factory):
        yield session_factory
    await engine.dispose()


@pytest.fixture()
async def fake_valkey():
    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis
    yield redis
    events_module._valkey = None
    await redis.aclose()


async def _insert_task(session_factory, **overrides):
    defaults = {
        "id": uuid.uuid4().hex,
        "title": "Test task",
        "status": "scheduled",
        "category": "scheduled",
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


# --- promote_due_tasks tests ---


@pytest.mark.asyncio
async def test_promote_past_execute_at(db_session, fake_valkey):
    """Task with execute_at in the past is promoted to pending."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    task_id = await _insert_task(db_session, execute_at=past)

    count = await promote_due_tasks()

    assert count == 1
    async with db_session() as session:
        result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id})
        assert result.scalar() == "pending"


@pytest.mark.asyncio
async def test_no_promote_future_execute_at(db_session, fake_valkey):
    """Task with execute_at in the future is not promoted."""
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    task_id = await _insert_task(db_session, execute_at=future)

    count = await promote_due_tasks()

    assert count == 0
    async with db_session() as session:
        result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id})
        assert result.scalar() == "scheduled"


@pytest.mark.asyncio
async def test_no_promote_null_execute_at(db_session, fake_valkey):
    """Task with null execute_at is not promoted."""
    task_id = await _insert_task(db_session, execute_at=None)

    count = await promote_due_tasks()

    assert count == 0
    async with db_session() as session:
        result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id})
        assert result.scalar() == "scheduled"


@pytest.mark.asyncio
async def test_only_scheduled_status_promoted(db_session, fake_valkey):
    """Only tasks with status 'scheduled' are promoted, not completed/running/etc."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    completed_id = await _insert_task(db_session, status="completed", execute_at=past)
    running_id = await _insert_task(db_session, status="running", execute_at=past)
    scheduled_id = await _insert_task(db_session, status="scheduled", execute_at=past)

    count = await promote_due_tasks()

    assert count == 1
    async with db_session() as session:
        result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": completed_id})
        assert result.scalar() == "completed"
        result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": running_id})
        assert result.scalar() == "running"
        result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": scheduled_id})
        assert result.scalar() == "pending"


@pytest.mark.asyncio
async def test_multiple_due_tasks_promoted(db_session, fake_valkey):
    """Multiple due tasks are promoted in one cycle."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    ids = []
    for _ in range(3):
        ids.append(await _insert_task(db_session, execute_at=past))

    count = await promote_due_tasks()

    assert count == 3
    async with db_session() as session:
        for task_id in ids:
            result = await session.execute(text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id})
            assert result.scalar() == "pending"


# --- Lock function tests ---


@pytest.mark.asyncio
async def test_acquire_lock_succeeds(fake_valkey):
    """acquire_lock succeeds when no lock exists."""
    result = await acquire_lock()
    assert result is True
    value = await fake_valkey.get(LOCK_KEY)
    assert value is not None


@pytest.mark.asyncio
async def test_acquire_lock_fails_when_held(fake_valkey):
    """acquire_lock fails when lock is already held."""
    await fake_valkey.set(LOCK_KEY, "other-host", ex=LOCK_TTL)

    result = await acquire_lock()
    assert result is False


@pytest.mark.asyncio
async def test_refresh_lock_extends_ttl(fake_valkey):
    """refresh_lock extends the TTL on the lock key."""
    await fake_valkey.set(LOCK_KEY, "test-host", ex=5)

    result = await refresh_lock()
    assert result is True
    ttl = await fake_valkey.ttl(LOCK_KEY)
    assert ttl == LOCK_TTL


@pytest.mark.asyncio
async def test_release_lock_deletes_key():
    """release_lock deletes the lock key when we still own it.

    Uses a minimal valkey stand-in because fakeredis does not support Lua
    scripting, and the conditional release is now implemented as an EVAL
    script (see B3 in fix-code-review-bugs).
    """
    import socket

    class _FakeLuaValkey:
        def __init__(self):
            self._store: dict[str, str] = {}

        async def set(self, key, value, **_ignored):
            self._store[key] = value

        async def get(self, key):
            return self._store.get(key)

        async def execute_command(self, *args):
            assert args[0] == "EVAL"
            _, _script, _numkeys, key, expected = args
            if self._store.get(key) == expected:
                self._store.pop(key, None)
                return 1
            return 0

    fake = _FakeLuaValkey()
    events_module._valkey = fake
    try:
        await fake.set(LOCK_KEY, socket.gethostname(), ex=LOCK_TTL)
        await release_lock()
        assert await fake.get(LOCK_KEY) is None
    finally:
        events_module._valkey = None


# --- WebSocket event tests ---


@pytest.mark.asyncio
async def test_promotion_publishes_event(db_session, fake_valkey):
    """Promoted task triggers task_updated event with full payload."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    task_id = await _insert_task(db_session, execute_at=past, title="Event test task")

    pubsub = fake_valkey.pubsub()
    await pubsub.subscribe("task_events")
    await pubsub.get_message()  # subscription confirmation

    await promote_due_tasks()

    msg = await pubsub.get_message()
    assert msg is not None
    import json
    payload = json.loads(msg["data"])
    assert payload["event"] == "task_updated"
    task_data = payload["task"]
    assert task_data["id"] == str(uuid.UUID(task_id))
    assert task_data["status"] == "pending"
    assert task_data["title"] == "Event test task"
    assert "tags" in task_data
    assert "created_at" in task_data
    assert "updated_at" in task_data
    await pubsub.unsubscribe()


# --- Resilience tests ---


@pytest.mark.asyncio
async def test_db_error_during_promotion_is_caught(fake_valkey, caplog):
    """Database error during promotion is caught and logged."""
    with patch.object(scheduler_module, "async_session") as mock_factory:
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("DB connection lost")
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_ctx.__aexit__.return_value = False
        mock_factory.return_value = mock_ctx

        with pytest.raises(Exception, match="DB connection lost"):
            await promote_due_tasks()


@pytest.mark.asyncio
async def test_valkey_error_during_lock_acquisition_is_caught(caplog):
    """Valkey error during lock acquisition is caught (returns False)."""
    mock_valkey = AsyncMock()
    mock_valkey.set.side_effect = Exception("Valkey unreachable")
    events_module._valkey = mock_valkey

    try:
        with pytest.raises(Exception, match="Valkey unreachable"):
            await acquire_lock()
    finally:
        events_module._valkey = None


@pytest.mark.asyncio
async def test_run_scheduler_catches_errors(fake_valkey, caplog):
    """run_scheduler catches exceptions per cycle without crashing."""
    import asyncio
    from scheduler import run_scheduler

    call_count = 0

    async def mock_promote():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Transient DB error")
        return 0

    with patch.object(scheduler_module, "SCHEDULER_INTERVAL", 0.01), \
         patch.object(scheduler_module, "promote_due_tasks", side_effect=mock_promote):
        task = asyncio.create_task(run_scheduler())
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Scheduler should have survived the first error and continued
    assert call_count >= 2
