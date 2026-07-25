"""Tests for retry-cap escalation and backoff ceiling in TaskManager.

See openspec/changes/cap-runner-retry-storm for the spec.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import Setting, Tag, Task, task_tags
from task_manager import (
    DEFAULT_MAX_RETRY_ATTEMPTS,
    MAX_RETRY_BACKOFF_MINUTES,
    TaskManager,
)


# ---------------------------------------------------------------------------
# Shared fixture: in-memory SQLite with tasks/tags/settings tables.
# Mirrors the schema used by `retry_session_factory` in test_worker.py.
# ---------------------------------------------------------------------------


@pytest.fixture()
async def retry_factory():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("""
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
                is_eval BOOLEAN DEFAULT 0 NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tags (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_tags (
                task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (task_id, tag_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT NOT NULL PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield engine, factory
    await engine.dispose()


async def _insert_task(factory, **kwargs):
    task = Task(**kwargs)
    async with factory() as session:
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task.id


async def _set_setting(factory, key: str, value):
    async with factory() as session:
        session.add(Setting(key=key, value=value))
        await session.commit()


async def _task_tags(factory, task_id) -> set[str]:
    async with factory() as session:
        result = await session.execute(
            select(Tag.name).join(task_tags, Tag.id == task_tags.c.tag_id).where(
                task_tags.c.task_id == task_id
            )
        )
        return {row[0] for row in result.all()}


# ---------------------------------------------------------------------------
# 4.1 — Retry cap escalation tests
# ---------------------------------------------------------------------------


async def test_escalates_to_review_at_default_cap(retry_factory):
    """retry_count=4 with default cap (5) escalates to review + Failed."""
    engine, factory = retry_factory
    task_id = await _insert_task(
        factory, title="t", status="running", retry_count=4,
    )

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(
            mock_task, output="upstream failure", runner_logs="stderr",
        )

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.status == "review"
        assert updated.retry_count == 5
        assert "exceeded max retries" in updated.output
        assert "upstream failure" in updated.output
        assert updated.runner_logs == "stderr"

    tags = await _task_tags(factory, task_id)
    assert "Failed" in tags
    assert "Retry" not in tags


async def test_reschedules_below_cap(retry_factory):
    """retry_count=2 (< cap - 1) reschedules with backoff and Retry tag."""
    engine, factory = retry_factory
    task_id = await _insert_task(
        factory, title="t", status="running", retry_count=2,
    )

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="boom")

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.status == "scheduled"
        assert updated.retry_count == 3

    tags = await _task_tags(factory, task_id)
    assert "Retry" in tags
    assert "Failed" not in tags


async def test_operator_raising_cap_mid_flight(retry_factory):
    """Raising max_retry_attempts at runtime changes the escalation decision."""
    engine, factory = retry_factory
    task_id = await _insert_task(
        factory, title="t", status="running", retry_count=4,
    )
    # Operator bumps the cap to 10
    await _set_setting(factory, "max_retry_attempts", "10")

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="boom")

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.status == "scheduled"  # reschedule, not escalate
        assert updated.retry_count == 5

    tags = await _task_tags(factory, task_id)
    assert "Failed" not in tags


# ---------------------------------------------------------------------------
# 4.2 — Backoff cap at MAX_RETRY_BACKOFF_MINUTES
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "retry_count, expected_min, expected_max",
    [
        (3, 8, 8),    # 2 ** 3 = 8
        (6, 60, 60),  # 2 ** 6 = 64 — capped at 60
        (13, 60, 60),  # 2 ** 13 — capped at 60
    ],
)
async def test_backoff_cap(retry_factory, retry_count, expected_min, expected_max):
    """Backoff is min(2**retry_count, 60) and never exceeds the ceiling."""
    engine, factory = retry_factory
    # Set a high cap so we exercise the reschedule branch.
    await _set_setting(factory, "max_retry_attempts", "50")
    task_id = await _insert_task(
        factory, title="t", status="running", retry_count=retry_count,
    )

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    before = datetime.now(timezone.utc)
    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="boom")

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        delta = (
            updated.execute_at.replace(tzinfo=None) - before.replace(tzinfo=None)
        )
        # Use a generous wiggle to absorb DB roundtrip overhead.
        assert delta >= timedelta(minutes=expected_min) - timedelta(seconds=10)
        assert delta <= timedelta(minutes=expected_max) + timedelta(seconds=10)
        assert MAX_RETRY_BACKOFF_MINUTES == 60


# ---------------------------------------------------------------------------
# 4.3 — _get_max_retry_attempts resolution + clamping
# ---------------------------------------------------------------------------


async def test_get_max_retry_attempts_default(retry_factory, monkeypatch):
    engine, factory = retry_factory
    monkeypatch.delenv("MAX_RETRY_ATTEMPTS", raising=False)
    async with factory() as session:
        value = await TaskManager()._get_max_retry_attempts(session)
    assert value == DEFAULT_MAX_RETRY_ATTEMPTS


async def test_get_max_retry_attempts_env_overrides_db(retry_factory, monkeypatch):
    engine, factory = retry_factory
    await _set_setting(factory, "max_retry_attempts", "3")
    monkeypatch.setenv("MAX_RETRY_ATTEMPTS", "8")
    async with factory() as session:
        value = await TaskManager()._get_max_retry_attempts(session)
    assert value == 8


async def test_get_max_retry_attempts_db_value(retry_factory, monkeypatch):
    engine, factory = retry_factory
    monkeypatch.delenv("MAX_RETRY_ATTEMPTS", raising=False)
    await _set_setting(factory, "max_retry_attempts", "7")
    async with factory() as session:
        value = await TaskManager()._get_max_retry_attempts(session)
    assert value == 7


async def test_get_max_retry_attempts_clamps_zero(retry_factory, monkeypatch):
    engine, factory = retry_factory
    monkeypatch.delenv("MAX_RETRY_ATTEMPTS", raising=False)
    await _set_setting(factory, "max_retry_attempts", "0")
    async with factory() as session:
        value = await TaskManager()._get_max_retry_attempts(session)
    assert value == 1


async def test_get_max_retry_attempts_clamps_negative(retry_factory, monkeypatch):
    engine, factory = retry_factory
    monkeypatch.delenv("MAX_RETRY_ATTEMPTS", raising=False)
    await _set_setting(factory, "max_retry_attempts", "-5")
    async with factory() as session:
        value = await TaskManager()._get_max_retry_attempts(session)
    assert value == 1


async def test_get_max_retry_attempts_invalid_falls_back(retry_factory, monkeypatch, caplog):
    engine, factory = retry_factory
    monkeypatch.delenv("MAX_RETRY_ATTEMPTS", raising=False)
    # Coercion failure path: store a non-numeric string.
    await _set_setting(factory, "max_retry_attempts", "not-a-number")
    async with factory() as session:
        with caplog.at_level("WARNING"):
            value = await TaskManager()._get_max_retry_attempts(session)
    assert value == DEFAULT_MAX_RETRY_ATTEMPTS


# ---------------------------------------------------------------------------
# 4.4 — Retry tag removed, Failed tag added (mutually exclusive)
# ---------------------------------------------------------------------------


async def test_escalation_removes_retry_and_adds_failed(retry_factory):
    engine, factory = retry_factory
    task_id = await _insert_task(
        factory, title="t", status="running", retry_count=4,
    )
    # Pre-seed the task with a Retry tag association.
    async with factory() as session:
        retry_tag = Tag(name="Retry")
        session.add(retry_tag)
        await session.flush()
        await session.execute(
            task_tags.insert().values(task_id=task_id, tag_id=retry_tag.id)
        )
        await session.commit()

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="boom")

    tags = await _task_tags(factory, task_id)
    assert tags == {"Failed"}


# ---------------------------------------------------------------------------
# 4.5 — publish_event is invoked on escalation
# ---------------------------------------------------------------------------


async def test_escalation_publishes_task_updated_event(retry_factory):
    engine, factory = retry_factory
    task_id = await _insert_task(
        factory, title="t", status="running", retry_count=4,
    )

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    publish_mock = AsyncMock()
    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", publish_mock):
        await TaskManager()._schedule_retry(mock_task, output="boom")

    # Exactly one task_updated emission on escalation.
    assert publish_mock.await_count == 1
    event_name, payload = publish_mock.await_args.args
    assert event_name == "task_updated"
    assert payload["status"] == "review"
    assert "Failed" in payload["tags"]
