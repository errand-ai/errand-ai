"""Tests for Slack status updater (Valkey subscriber)."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import SlackMessageRef
from platforms.slack.status_updater import _process_task_event

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

_SLACK_MESSAGE_REFS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS slack_message_refs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    message_ts TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
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


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_TASKS_TABLE_SQL))
        await conn.execute(text(_SLACK_MESSAGE_REFS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))
        await conn.execute(text(_PLATFORM_CREDENTIALS_TABLE_SQL))


@pytest.fixture()
async def db_session():
    """Provide a test database session with tables."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


async def _insert_task(session, task_id, title="Test", status="running"):
    """Insert a task into the DB."""
    from models import Task
    task = Task(id=task_id, title=title, status=status, position=1, created_by="test@example.com")
    session.add(task)
    await session.flush()
    return task


async def _insert_msg_ref(session, task_id, channel_id="C123", message_ts="111.222"):
    """Insert a Slack message ref into the DB."""
    ref = SlackMessageRef(task_id=task_id, channel_id=channel_id, message_ts=message_ts)
    session.add(ref)
    await session.flush()
    return ref


class TestProcessTaskEvent:
    @pytest.mark.asyncio
    async def test_updates_message_when_ref_exists(self, db_session):
        task_id = uuid.uuid4()
        await _insert_task(db_session, task_id, status="running")
        await _insert_msg_ref(db_session, task_id, "C123", "111.222")
        await db_session.commit()

        event_data = {
            "event": "task_updated",
            "task": {
                "id": str(task_id),
                "title": "Test",
                "status": "running",
                "category": "immediate",
                "created_by": "test@example.com",
            },
        }

        with patch("platforms.slack.status_updater._slack_client") as mock_client:
            mock_client.update_message = AsyncMock(return_value={"ok": True})
            await _process_task_event(event_data, db_session, "xoxb-token")

            mock_client.update_message.assert_called_once()
            call_args = mock_client.update_message.call_args
            assert call_args[0][0] == "xoxb-token"  # token
            assert call_args[0][1] == "C123"  # channel
            assert call_args[0][2] == "111.222"  # ts
            assert isinstance(call_args[0][3], list)  # blocks

    @pytest.mark.asyncio
    async def test_skips_when_no_ref(self, db_session):
        task_id = uuid.uuid4()
        await _insert_task(db_session, task_id)
        await db_session.commit()

        event_data = {
            "event": "task_updated",
            "task": {"id": str(task_id), "title": "Test", "status": "pending"},
        }

        with patch("platforms.slack.status_updater._slack_client") as mock_client:
            mock_client.update_message = AsyncMock()
            await _process_task_event(event_data, db_session, "xoxb-token")
            mock_client.update_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_task_id(self, db_session):
        event_data = {"event": "task_updated", "task": {}}

        with patch("platforms.slack.status_updater._slack_client") as mock_client:
            mock_client.update_message = AsyncMock()
            await _process_task_event(event_data, db_session, "xoxb-token")
            mock_client.update_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_update_failure(self, db_session):
        task_id = uuid.uuid4()
        await _insert_task(db_session, task_id)
        await _insert_msg_ref(db_session, task_id)
        await db_session.commit()

        event_data = {
            "event": "task_updated",
            "task": {
                "id": str(task_id),
                "title": "Test",
                "status": "completed",
                "category": "immediate",
                "created_by": "test@example.com",
            },
        }

        with patch("platforms.slack.status_updater._slack_client") as mock_client:
            mock_client.update_message = AsyncMock(side_effect=Exception("Slack API error"))
            # Should not raise — error is logged and ref is deleted
            await _process_task_event(event_data, db_session, "xoxb-token")

            # Verify the message ref was deleted to prevent future retries
            result = await db_session.execute(
                select(SlackMessageRef).where(SlackMessageRef.task_id == task_id)
            )
            assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_sends_correct_blocks_for_status(self, db_session):
        task_id = uuid.uuid4()
        await _insert_task(db_session, task_id, title="Deploy app", status="completed")
        await _insert_msg_ref(db_session, task_id)
        await db_session.commit()

        event_data = {
            "event": "task_updated",
            "task": {
                "id": str(task_id),
                "title": "Deploy app",
                "status": "completed",
                "category": "immediate",
                "created_by": "test@example.com",
            },
        }

        with patch("platforms.slack.status_updater._slack_client") as mock_client:
            mock_client.update_message = AsyncMock(return_value={"ok": True})
            await _process_task_event(event_data, db_session, "xoxb-token")

            blocks = mock_client.update_message.call_args[0][3]
            # Check status field contains completed emoji
            fields_text = " ".join(f["text"] for f in blocks[1]["fields"])
            assert ":white_check_mark: completed" in fields_text
