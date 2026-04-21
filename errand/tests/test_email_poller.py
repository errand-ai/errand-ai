"""Tests for the email poller module."""
import uuid
import email
from email import policy
from email.message import EmailMessage
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import database as database_module
import email_poller as email_poller_module
import events as events_module
from models import Task, TaskGenerator


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
    profile_id VARCHAR(36) REFERENCES task_profiles(id) ON DELETE SET NULL,
    created_by TEXT,
    updated_by TEXT,
        encrypted_env TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
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

_TASK_GENERATORS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_generators (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    type TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 0 NOT NULL,
    profile_id VARCHAR(36) REFERENCES task_profiles(id) ON DELETE SET NULL,
    config TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


@pytest.fixture()
async def fake_valkey() -> AsyncGenerator[FakeRedis, None]:
    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis
    yield redis
    events_module._valkey = None
    await redis.aclose()


@pytest.fixture()
async def db_session(fake_valkey):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_TASKS_TABLE_SQL))
        await conn.execute(text(_PLATFORM_CREDENTIALS_TABLE_SQL))
        await conn.execute(text(_TASK_GENERATORS_TABLE_SQL))

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    original_db = database_module.async_session
    original_poller = email_poller_module.async_session
    database_module.async_session = test_session
    email_poller_module.async_session = test_session

    yield engine, test_session

    database_module.async_session = original_db
    email_poller_module.async_session = original_poller
    await engine.dispose()


def _make_generator(profile_id=None, config=None, enabled=True):
    """Create a TaskGenerator instance for testing."""
    gen = TaskGenerator(
        id=uuid.uuid4(),
        type="email",
        enabled=enabled,
        profile_id=uuid.UUID(profile_id) if profile_id else None,
        config=config or {},
    )
    return gen


def _make_plain_email(subject="Test Subject", sender="alice@example.com",
                      to="bob@example.com", date="Mon, 1 Jan 2024 12:00:00 +0000",
                      body="Hello, this is plain text."):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = date
    msg.set_content(body)
    return msg.as_bytes()


def _make_html_email(subject="HTML Email", sender="alice@example.com",
                     to="bob@example.com", date="Mon, 1 Jan 2024 12:00:00 +0000",
                     html_body="<h1>Hello</h1><p>World</p>"):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = date
    msg.make_alternative()
    msg.add_alternative("Fallback text", subtype="plain")
    msg.add_alternative(html_body, subtype="html")
    return msg.as_bytes()


class TestExtractBody:
    def test_plain_text_email(self):
        from email_poller import extract_body

        raw = _make_plain_email(body="Hello plain text")
        result = extract_body(raw)
        assert "Hello plain text" in result

    def test_html_email_converted_to_markdown(self):
        from email_poller import extract_body

        raw = _make_html_email(html_body="<h1>Title</h1><p>Paragraph</p>")
        result = extract_body(raw)
        # html2text converts <h1> to # Title
        assert "Title" in result
        assert "Paragraph" in result

    def test_body_truncation(self):
        from email_poller import extract_body, MAX_BODY_LENGTH

        long_text = "x" * (MAX_BODY_LENGTH + 100)
        raw = _make_plain_email(body=long_text)
        result = extract_body(raw)
        assert len(result) == MAX_BODY_LENGTH


class TestBuildDescription:
    def test_format(self):
        from email_poller import build_description

        result = build_description(
            sender="alice@example.com",
            to="bob@example.com",
            date="Mon, 1 Jan 2024",
            subject="Test",
            uid="123",
            body="Message body",
        )
        assert "**From:** alice@example.com" in result
        assert "**To:** bob@example.com" in result
        assert "**Date:** Mon, 1 Jan 2024" in result
        assert "**Subject:** Test" in result
        assert "**Email UID:** 123" in result
        assert "Message body" in result

    def test_format_with_task_prompt(self):
        from email_poller import build_description

        result = build_description(
            sender="alice@example.com",
            to="bob@example.com",
            date="Mon, 1 Jan 2024",
            subject="Test",
            uid="123",
            body="Message body",
            task_prompt="Process this email carefully",
        )
        assert "Message body" in result
        assert "**Additional Instructions:**" in result
        assert "Process this email carefully" in result

    def test_format_without_task_prompt(self):
        from email_poller import build_description

        result = build_description(
            sender="alice@example.com",
            to="bob@example.com",
            date="Mon, 1 Jan 2024",
            subject="Test",
            uid="123",
            body="Message body",
            task_prompt=None,
        )
        assert "Additional Instructions" not in result


class TestCreateTaskFromEmail:
    @pytest.mark.asyncio
    async def test_creates_task(self, db_session):
        _, session_factory = db_session
        from email_poller import create_task_from_email

        success = await create_task_from_email(
            subject="Important Email",
            description="Some description",
            profile_id="00000000-0000-0000-0000-000000000001",
        )
        assert success is True

        async with session_factory() as session:
            result = await session.execute(select(Task))
            task = result.scalar_one()
            assert task.title == "Important Email"
            assert task.description == "Some description"
            assert task.status == "pending"
            assert task.created_by == "email_poller"
            assert str(task.profile_id) == "00000000-0000-0000-0000-000000000001"

    @pytest.mark.asyncio
    async def test_publishes_task_created_event(self, db_session):
        from email_poller import create_task_from_email

        with patch("email_poller.publish_event", new_callable=AsyncMock) as mock_publish:
            await create_task_from_email(
                subject="Event Email",
                description="Description",
                profile_id=None,
            )
            mock_publish.assert_awaited_once()
            args = mock_publish.call_args
            assert args[0][0] == "task_created"
            event_data = args[0][1]
            assert event_data["title"] == "Event Email"
            assert event_data["created_by"] == "email_poller"
            assert event_data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_creates_task_without_profile(self, db_session):
        _, session_factory = db_session
        from email_poller import create_task_from_email

        success = await create_task_from_email(
            subject="No Profile Email",
            description="Description",
            profile_id=None,
        )
        assert success is True

        async with session_factory() as session:
            result = await session.execute(select(Task))
            task = result.scalar_one()
            assert task.profile_id is None

    @pytest.mark.asyncio
    async def test_no_subject_uses_placeholder(self, db_session):
        _, session_factory = db_session
        from email_poller import create_task_from_email

        success = await create_task_from_email(
            subject="",
            description="No subject email",
            profile_id="00000000-0000-0000-0000-000000000002",
        )
        assert success is True

        async with session_factory() as session:
            result = await session.execute(select(Task))
            task = result.scalar_one()
            assert task.title == "(no subject)"


class TestGetPollInterval:
    def test_default_interval(self):
        from email_poller import _get_poll_interval, MIN_POLL_INTERVAL
        gen = _make_generator(config={})
        result = _get_poll_interval(gen)
        assert result == MIN_POLL_INTERVAL

    def test_below_minimum(self):
        from email_poller import _get_poll_interval, MIN_POLL_INTERVAL
        gen = _make_generator(config={"poll_interval": 10})
        result = _get_poll_interval(gen)
        assert result == MIN_POLL_INTERVAL

    def test_valid_interval(self):
        from email_poller import _get_poll_interval
        gen = _make_generator(config={"poll_interval": 300})
        result = _get_poll_interval(gen)
        assert result == 300

    def test_invalid_string(self):
        from email_poller import _get_poll_interval, MIN_POLL_INTERVAL
        gen = _make_generator(config={"poll_interval": "abc"})
        result = _get_poll_interval(gen)
        assert result == MIN_POLL_INTERVAL

    def test_none_value(self):
        from email_poller import _get_poll_interval, MIN_POLL_INTERVAL
        gen = _make_generator(config={"poll_interval": None})
        result = _get_poll_interval(gen)
        assert result == MIN_POLL_INTERVAL


class TestProcessMessages:
    @pytest.mark.asyncio
    async def test_process_unseen_messages(self, db_session):
        _, session_factory = db_session
        from email_poller import process_messages

        raw_email = _make_plain_email(subject="New Email", body="Test body")
        generator = _make_generator(
            profile_id="00000000-0000-0000-0000-000000000003",
        )

        mock_imap = AsyncMock()
        # search returns UIDs
        search_response = MagicMock()
        search_response.result = "OK"
        search_response.lines = [b"1"]
        mock_imap.search.return_value = search_response

        # fetch returns email
        fetch_response = MagicMock()
        fetch_response.result = "OK"
        fetch_response.lines = [raw_email]
        mock_imap.fetch.return_value = fetch_response

        # store (mark as read)
        mock_imap.store.return_value = MagicMock()

        count = await process_messages(mock_imap, generator)

        assert count == 1

        # Verify task was created
        async with session_factory() as session:
            result = await session.execute(select(Task))
            task = result.scalar_one()
            assert task.title == "New Email"
            assert task.created_by == "email_poller"

        # Verify message was marked as read
        mock_imap.store.assert_awaited_once_with("1", "+FLAGS", "\\Seen")

    @pytest.mark.asyncio
    async def test_process_with_task_prompt(self, db_session):
        _, session_factory = db_session
        from email_poller import process_messages

        raw_email = _make_plain_email(subject="Prompted Email", body="Email body")
        generator = _make_generator(
            config={"task_prompt": "Handle this urgently"},
        )

        mock_imap = AsyncMock()
        search_response = MagicMock()
        search_response.result = "OK"
        search_response.lines = [b"1"]
        mock_imap.search.return_value = search_response

        fetch_response = MagicMock()
        fetch_response.result = "OK"
        fetch_response.lines = [raw_email]
        mock_imap.fetch.return_value = fetch_response
        mock_imap.store.return_value = MagicMock()

        count = await process_messages(mock_imap, generator)
        assert count == 1

        async with session_factory() as session:
            result = await session.execute(select(Task))
            task = result.scalar_one()
            assert "Handle this urgently" in task.description
            assert "Additional Instructions" in task.description

    @pytest.mark.asyncio
    async def test_process_without_profile(self, db_session):
        _, session_factory = db_session
        from email_poller import process_messages

        raw_email = _make_plain_email(subject="No Profile", body="Body")
        generator = _make_generator(profile_id=None)

        mock_imap = AsyncMock()
        search_response = MagicMock()
        search_response.result = "OK"
        search_response.lines = [b"1"]
        mock_imap.search.return_value = search_response

        fetch_response = MagicMock()
        fetch_response.result = "OK"
        fetch_response.lines = [raw_email]
        mock_imap.fetch.return_value = fetch_response
        mock_imap.store.return_value = MagicMock()

        count = await process_messages(mock_imap, generator)
        assert count == 1

        async with session_factory() as session:
            result = await session.execute(select(Task))
            task = result.scalar_one()
            assert task.profile_id is None

    @pytest.mark.asyncio
    async def test_process_no_unseen(self, db_session):
        from email_poller import process_messages

        generator = _make_generator()
        mock_imap = AsyncMock()
        search_response = MagicMock()
        search_response.result = "OK"
        search_response.lines = [b""]
        mock_imap.search.return_value = search_response

        count = await process_messages(mock_imap, generator)
        assert count == 0

    @pytest.mark.asyncio
    async def test_process_search_failure(self, db_session):
        from email_poller import process_messages

        generator = _make_generator()
        mock_imap = AsyncMock()
        search_response = MagicMock()
        search_response.result = "NO"
        search_response.lines = ["search failed"]
        mock_imap.search.return_value = search_response

        count = await process_messages(mock_imap, generator)
        assert count == 0


class TestLoadEmailGenerator:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_generator(self, db_session):
        from email_poller import _load_email_generator
        result = await _load_email_generator()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_generator(self, db_session):
        _, session_factory = db_session
        from email_poller import _load_email_generator

        # Insert a generator record
        async with session_factory() as session:
            gen = TaskGenerator(
                type="email",
                enabled=True,
                config={"poll_interval": 120},
            )
            session.add(gen)
            await session.commit()

        result = await _load_email_generator()
        assert result is not None
        assert result.type == "email"
        assert result.enabled is True
