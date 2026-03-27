"""Tests for MCP server: API key generation, regeneration, tools, and auth."""
import json
import secrets
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import database as database_module
from models import Setting, Task
from main import app, get_current_user, require_editor, require_admin

FAKE_ADMIN_CLAIMS = {
    "sub": "admin-user-id",
    "preferred_username": "adminuser",
    "email": "admin@example.com",
    "resource_access": {
        "errand": {"roles": ["user", "admin"]},
    },
}

_TABLES_SQL = [
    """CREATE TABLE IF NOT EXISTS task_profiles (
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
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
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
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS settings (
        key TEXT NOT NULL PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS tags (
        id VARCHAR(36) NOT NULL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS task_tags (
        task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        PRIMARY KEY (task_id, tag_id)
    )""",
    """CREATE TABLE IF NOT EXISTS platform_credentials (
        platform_id TEXT NOT NULL PRIMARY KEY,
        encrypted_data TEXT NOT NULL,
        status TEXT DEFAULT 'disconnected' NOT NULL,
        last_verified_at DATETIME,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
    )""",
]


async def _create_tables(engine):
    async with engine.begin() as conn:
        for sql in _TABLES_SQL:
            await conn.execute(text(sql))


@pytest.fixture()
async def db_session(fake_valkey):
    """Provides a session factory + engine with patched database.async_session."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    original = database_module.async_session
    database_module.async_session = test_session

    import mcp_server
    mcp_server.async_session = test_session

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_require_admin():
        return FAKE_ADMIN_CLAIMS

    app.dependency_overrides[database_module.get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: FAKE_ADMIN_CLAIMS
    app.dependency_overrides[require_editor] = lambda: FAKE_ADMIN_CLAIMS
    app.dependency_overrides[require_admin] = override_require_admin

    yield engine, test_session

    app.dependency_overrides.clear()
    database_module.async_session = original
    mcp_server.async_session = original
    await engine.dispose()


@pytest.fixture()
async def admin_mcp_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- 5.1: API key auto-generation on startup ---


async def test_api_key_auto_generated(db_session):
    """Simulates the lifespan key generation logic."""
    _, session_factory = db_session

    async with session_factory() as session:
        result = await session.execute(select(Setting).where(Setting.key == "mcp_api_key"))
        assert result.scalar_one_or_none() is None

        # Simulate lifespan logic
        session.add(Setting(key="mcp_api_key", value=secrets.token_hex(32)))
        await session.commit()

    async with session_factory() as session:
        result = await session.execute(select(Setting).where(Setting.key == "mcp_api_key"))
        setting = result.scalar_one()
        assert len(setting.value) == 64


async def test_api_key_preserved_when_exists(db_session):
    """Existing key is not overwritten by startup logic."""
    _, session_factory = db_session
    existing_key = "a" * 64

    async with session_factory() as session:
        session.add(Setting(key="mcp_api_key", value=existing_key))
        await session.commit()

    # Simulate lifespan check
    async with session_factory() as session:
        result = await session.execute(select(Setting).where(Setting.key == "mcp_api_key"))
        setting = result.scalar_one_or_none()
        if setting is None:
            session.add(Setting(key="mcp_api_key", value=secrets.token_hex(32)))
            await session.commit()

    async with session_factory() as session:
        result = await session.execute(select(Setting).where(Setting.key == "mcp_api_key"))
        setting = result.scalar_one()
        assert setting.value == existing_key


# --- 5.2: POST /api/settings/regenerate-mcp-key ---


async def test_regenerate_mcp_key_admin(admin_mcp_client: AsyncClient, db_session):
    _, session_factory = db_session
    async with session_factory() as session:
        session.add(Setting(key="mcp_api_key", value="old-key-" + "0" * 56))
        await session.commit()

    resp = await admin_mcp_client.post("/api/settings/regenerate-mcp-key")
    assert resp.status_code == 200
    data = resp.json()
    assert "mcp_api_key" in data
    assert len(data["mcp_api_key"]) == 64
    assert data["mcp_api_key"] != "old-key-" + "0" * 56


async def test_regenerate_mcp_key_non_admin(fake_valkey):
    """Non-admin users are rejected."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    from fastapi import HTTPException

    async def override_require_admin_reject():
        raise HTTPException(status_code=403, detail="Admin role required")

    app.dependency_overrides[database_module.get_session] = override_get_session
    app.dependency_overrides[require_admin] = override_require_admin_reject

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/api/settings/regenerate-mcp-key")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin role required"

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_regenerate_mcp_key_creates_when_missing(admin_mcp_client: AsyncClient, db_session):
    resp = await admin_mcp_client.post("/api/settings/regenerate-mcp-key")
    assert resp.status_code == 200
    assert len(resp.json()["mcp_api_key"]) == 64


async def test_mcp_api_key_in_settings_response(admin_mcp_client: AsyncClient, db_session):
    """GET /api/settings includes the mcp_api_key when it exists."""
    _, session_factory = db_session
    async with session_factory() as session:
        session.add(Setting(key="mcp_api_key", value="test-key-123"))
        await session.commit()

    resp = await admin_mcp_client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["mcp_api_key"]["value"] == "test-key-123"


# --- 5.3: MCP endpoint auth (via TokenVerifier) ---


async def test_api_key_verifier_valid(db_session):
    """ApiKeyVerifier accepts a valid token."""
    _, session_factory = db_session
    api_key = "valid-key-" + "a" * 54

    async with session_factory() as session:
        session.add(Setting(key="mcp_api_key", value=api_key))
        await session.commit()

    from mcp_server import ApiKeyVerifier
    verifier = ApiKeyVerifier()
    result = await verifier.verify_token(api_key)
    assert result is not None
    assert result.token == api_key


async def test_api_key_verifier_invalid(db_session):
    """ApiKeyVerifier rejects an invalid token."""
    _, session_factory = db_session
    async with session_factory() as session:
        session.add(Setting(key="mcp_api_key", value="real-key-" + "b" * 55))
        await session.commit()

    from mcp_server import ApiKeyVerifier
    verifier = ApiKeyVerifier()
    result = await verifier.verify_token("wrong-key")
    assert result is None


async def test_api_key_verifier_no_key_stored(db_session):
    """ApiKeyVerifier rejects when no key is stored."""
    from mcp_server import ApiKeyVerifier
    verifier = ApiKeyVerifier()
    result = await verifier.verify_token("any-key")
    assert result is None


# --- 5.3: MCP tool discovery ---


async def test_mcp_server_has_fifteen_tools():
    """The MCP server exposes exactly fifteen tools (7 task + 6 email + 2 search)."""
    from mcp_server import mcp
    tools = mcp._tool_manager.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names == {
        "new_task", "task_status", "task_output", "task_logs", "schedule_task", "list_tasks", "post_tweet",
        "list_emails", "read_email", "list_email_folders", "move_email", "send_email", "forward_email",
        "web_search", "read_url",
    }


# --- 5.4: MCP tools (tested as direct function calls) ---


async def test_new_task_tool(db_session):
    _, session_factory = db_session

    from mcp_server import new_task

    with patch("mcp_server.generate_title") as mock_gen:
        mock_result = type("LLMResult", (), {
            "title": "Research Python Frameworks",
            "success": True,
            "category": "immediate",
            "execute_at": None,
            "repeat_interval": None,
            "repeat_until": None,
            "description": "Research the latest Python web frameworks for building APIs",
            "profile": None,
        })()
        mock_gen.return_value = mock_result

        task_uuid = await new_task("Research the latest Python web frameworks for building APIs")

    assert len(task_uuid) == 36  # UUID format

    # Verify task was created in DB
    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.title == "Research Python Frameworks"
        assert task.status == "pending"
        assert task.category == "immediate"


async def test_new_task_short_description(db_session):
    """Short descriptions (<=5 words) use the description as the title."""
    from mcp_server import new_task

    task_uuid = await new_task("Fix login bug")

    _, session_factory = db_session
    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.title == "Fix login bug"


async def test_task_status_found(db_session):
    _, session_factory = db_session

    async with session_factory() as session:
        task = Task(title="Test task", description="Testing", status="running", category="one-off")
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = str(task.id)

    from mcp_server import task_status
    result = await task_status(task_id)
    assert "Test task" in result
    assert "running" in result


async def test_task_status_not_found(db_session):
    from mcp_server import task_status
    result = await task_status("00000000-0000-0000-0000-000000000000")
    assert "not found" in result.lower()


async def test_task_output_completed(db_session):
    _, session_factory = db_session

    async with session_factory() as session:
        task = Task(title="Done", status="completed", output="Final result", category="one-off")
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = str(task.id)

    from mcp_server import task_output
    result = await task_output(task_id)
    assert "Final result" in result


async def test_task_output_review(db_session):
    _, session_factory = db_session

    async with session_factory() as session:
        task = Task(title="Review", status="review", output="Review content", category="one-off")
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = str(task.id)

    from mcp_server import task_output
    result = await task_output(task_id)
    assert "Review content" in result


async def test_task_output_in_progress(db_session):
    _, session_factory = db_session

    async with session_factory() as session:
        task = Task(title="Running", status="running", category="one-off")
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = str(task.id)

    from mcp_server import task_output
    result = await task_output(task_id)
    assert "still in progress" in result.lower()
    assert "running" in result


async def test_task_output_not_found(db_session):
    from mcp_server import task_output
    result = await task_output("00000000-0000-0000-0000-000000000000")
    assert "not found" in result.lower()


# --- list_tasks MCP tool ---


async def test_list_tasks_no_filter(db_session):
    """list_tasks with no filter returns board-visible tasks, excluding new/deleted/archived."""
    _, session_factory = db_session

    async with session_factory() as session:
        session.add(Task(title="Pending task", status="pending", category="immediate", position=1))
        session.add(Task(title="Running task", status="running", category="immediate", position=0))
        session.add(Task(title="Completed task", status="completed", category="immediate"))
        session.add(Task(title="New task", status="new", category="immediate"))
        session.add(Task(title="Deleted task", status="deleted", category="immediate"))
        session.add(Task(title="Archived task", status="archived", category="immediate"))
        await session.commit()

    from mcp_server import list_tasks
    result = await list_tasks()
    tasks = json.loads(result)
    titles = [t["title"] for t in tasks]
    assert "Running task" in titles
    assert "Pending task" in titles
    assert "Completed task" in titles
    assert "New task" not in titles
    assert "Deleted task" not in titles
    assert "Archived task" not in titles
    for t in tasks:
        assert set(t.keys()) == {"id", "title", "status"}
    # Active tasks ordered by position ASC, completed tasks at end
    assert titles.index("Running task") < titles.index("Pending task")  # position 0 < 1
    assert titles.index("Pending task") < titles.index("Completed task")  # active before completed


async def test_list_tasks_filter_by_status(db_session):
    """list_tasks with status filter returns only matching tasks."""
    _, session_factory = db_session

    async with session_factory() as session:
        session.add(Task(title="Scheduled one", status="scheduled", category="immediate"))
        session.add(Task(title="Scheduled two", status="scheduled", category="immediate"))
        session.add(Task(title="Running one", status="running", category="immediate"))
        await session.commit()

    from mcp_server import list_tasks
    result = await list_tasks(status="scheduled")
    tasks = json.loads(result)
    assert len(tasks) == 2
    assert all(t["status"] == "scheduled" for t in tasks)


async def test_list_tasks_invalid_status(db_session):
    """list_tasks with invalid status returns an error message."""
    from mcp_server import list_tasks
    result = await list_tasks(status="bogus")
    assert "Error" in result
    assert "bogus" in result
    assert "scheduled" in result  # lists valid options


async def test_list_tasks_empty_result(db_session):
    """list_tasks returns empty JSON array when no tasks match."""
    from mcp_server import list_tasks
    result = await list_tasks()
    tasks = json.loads(result)
    assert tasks == []


# --- task_logs MCP tool ---


async def test_task_logs_with_logs(db_session):
    """task_logs returns runner_logs content when present."""
    _, session_factory = db_session

    async with session_factory() as session:
        task = Task(
            title="Logged task",
            status="completed",
            category="immediate",
            runner_logs="Step 1: started\nStep 2: finished",
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = str(task.id)

    from mcp_server import task_logs
    result = await task_logs(task_id)
    assert result == "Step 1: started\nStep 2: finished"


async def test_task_logs_no_logs(db_session):
    """task_logs returns '(no logs available)' when runner_logs is null."""
    _, session_factory = db_session

    async with session_factory() as session:
        task = Task(title="No logs", status="completed", category="immediate")
        session.add(task)
        await session.commit()
        await session.refresh(task)
        task_id = str(task.id)

    from mcp_server import task_logs
    result = await task_logs(task_id)
    assert result == "(no logs available)"


async def test_task_logs_not_found(db_session):
    """task_logs returns error for non-existent task."""
    from mcp_server import task_logs
    result = await task_logs("00000000-0000-0000-0000-000000000000")
    assert "Error" in result
    assert "not found" in result.lower()


# --- schedule_task MCP tool ---


async def test_schedule_task_basic(db_session):
    """schedule_task creates a scheduled task with correct fields."""
    _, session_factory = db_session

    from mcp_server import schedule_task
    task_uuid = await schedule_task(
        description="Send report",
        execute_at="2026-03-01T09:00:00Z",
    )

    assert len(task_uuid) == 36

    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.status == "scheduled"
        assert task.category == "scheduled"
        assert task.title == "Send report"
        assert task.repeat_interval is None
        assert task.repeat_until is None
        assert task.created_by == "mcp"


async def test_schedule_task_repeating(db_session):
    """schedule_task with repeat_interval sets category to 'repeating'."""
    _, session_factory = db_session

    from mcp_server import schedule_task
    task_uuid = await schedule_task(
        description="Check health",
        execute_at="2026-03-01T09:00:00Z",
        repeat_interval="1h",
    )

    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.category == "repeating"
        assert task.repeat_interval == "1h"
        assert task.repeat_until is None


async def test_schedule_task_repeating_with_end(db_session):
    """schedule_task with repeat_interval and repeat_until sets both."""
    _, session_factory = db_session

    from mcp_server import schedule_task
    task_uuid = await schedule_task(
        description="Standup",
        execute_at="2026-03-01T09:00:00Z",
        repeat_interval="1d",
        repeat_until="2026-06-01T00:00:00Z",
    )

    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.category == "repeating"
        assert task.repeat_interval == "1d"
        assert task.repeat_until is not None


async def test_schedule_task_invalid_execute_at(db_session):
    """schedule_task returns error for invalid execute_at format."""
    from mcp_server import schedule_task
    result = await schedule_task(
        description="Bad time",
        execute_at="next tuesday",
    )
    assert "Error" in result
    assert "execute_at" in result


async def test_schedule_task_invalid_repeat_until(db_session):
    """schedule_task returns error for invalid repeat_until format."""
    from mcp_server import schedule_task
    result = await schedule_task(
        description="Bad end",
        execute_at="2026-03-01T09:00:00Z",
        repeat_interval="1d",
        repeat_until="forever",
    )
    assert "Error" in result
    assert "repeat_until" in result


async def test_schedule_task_short_description_no_llm(db_session):
    """Short descriptions (<= 5 words) use description as title, no LLM."""
    from mcp_server import schedule_task

    with patch("mcp_server.generate_title") as mock_gen:
        task_uuid = await schedule_task(
            description="Check logs",
            execute_at="2026-03-01T09:00:00Z",
        )
        mock_gen.assert_not_called()

    _, session_factory = db_session
    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.title == "Check logs"


async def test_schedule_task_long_description_uses_llm(db_session):
    """Long descriptions (> 5 words) use generate_title() for the title."""
    from mcp_server import schedule_task

    with patch("mcp_server.generate_title") as mock_gen:
        mock_result = type("LLMResult", (), {
            "title": "Weekly Report",
            "success": True,
            "category": "scheduled",
            "execute_at": None,
            "repeat_interval": None,
            "repeat_until": None,
            "description": "Send the weekly status report to the team every Monday morning",
            "profile": None,
        })()
        mock_gen.return_value = mock_result

        task_uuid = await schedule_task(
            description="Send the weekly status report to the team every Monday morning",
            execute_at="2026-03-01T09:00:00Z",
        )
        mock_gen.assert_called_once()

    _, session_factory = db_session
    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.title == "Weekly Report"
        # Category should be "scheduled" (from parameters), not LLM's "scheduled"
        assert task.category == "scheduled"


async def test_schedule_task_human_readable_interval_normalised(db_session):
    """schedule_task normalises human-readable repeat_interval to compact form."""
    _, session_factory = db_session

    from mcp_server import schedule_task
    task_uuid = await schedule_task(
        description="Weekly check",
        execute_at="2026-03-01T09:00:00Z",
        repeat_interval="7 days",
    )

    async with session_factory() as session:
        result = await session.execute(select(Task).where(Task.id == uuid.UUID(task_uuid)))
        task = result.scalar_one()
        assert task.category == "repeating"
        assert task.repeat_interval == "7d"


async def test_schedule_task_invalid_repeat_interval_rejected(db_session):
    """schedule_task returns error for unparseable repeat_interval and does not create a task."""
    _, session_factory = db_session

    from mcp_server import schedule_task
    result = await schedule_task(
        description="Bad interval",
        execute_at="2026-03-01T09:00:00Z",
        repeat_interval="every other tuesday",
    )
    assert "Error" in result
    assert "repeat_interval" in result

    # Verify no task was created
    async with session_factory() as session:
        count = await session.execute(select(func.count()).select_from(Task))
        assert count.scalar() == 0


# --- post_tweet MCP tool ---


async def test_post_tweet_valid(monkeypatch):
    """Successful tweet returns the tweet URL."""
    monkeypatch.setenv("TWITTER_API_KEY", "key")
    monkeypatch.setenv("TWITTER_API_SECRET", "secret")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "token")
    monkeypatch.setenv("TWITTER_ACCESS_SECRET", "access")

    from platforms import get_registry
    from platforms.twitter import TwitterPlatform
    registry = get_registry()
    registry.register(TwitterPlatform())

    mock_response = type("Response", (), {"data": {"id": "123456"}})()
    mock_user = type("User", (), {"data": type("Data", (), {"username": "testuser"})()})()

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.create_tweet.return_value = mock_response
        instance.get_me.return_value = mock_user

        from mcp_server import post_tweet
        result = await post_tweet("Hello world!")

    assert "https://x.com/testuser/status/123456" in result
    instance.create_tweet.assert_called_once_with(text="Hello world!")


async def test_post_tweet_too_long():
    """Messages over 280 characters are rejected."""
    from mcp_server import post_tweet
    result = await post_tweet("a" * 281)
    assert "Error" in result
    assert "280 character limit" in result
    assert "281" in result


async def test_post_tweet_empty():
    """Empty messages are rejected."""
    from mcp_server import post_tweet
    result = await post_tweet("")
    assert "Error" in result
    assert "empty" in result.lower()


async def test_post_tweet_whitespace_only():
    """Whitespace-only messages are rejected."""
    from mcp_server import post_tweet
    result = await post_tweet("   ")
    assert "Error" in result
    assert "empty" in result.lower()


async def test_post_tweet_credentials_not_configured(monkeypatch):
    """Missing credentials returns an error."""
    monkeypatch.delenv("TWITTER_API_KEY", raising=False)
    monkeypatch.delenv("TWITTER_API_SECRET", raising=False)
    monkeypatch.delenv("TWITTER_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_ACCESS_SECRET", raising=False)

    from mcp_server import post_tweet
    result = await post_tweet("Hello world!")
    assert "Error" in result
    assert "credentials not configured" in result.lower()


async def test_post_tweet_twitter_api_error(monkeypatch):
    """Twitter API errors are caught and returned."""
    monkeypatch.setenv("TWITTER_API_KEY", "key")
    monkeypatch.setenv("TWITTER_API_SECRET", "secret")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "token")
    monkeypatch.setenv("TWITTER_ACCESS_SECRET", "access")

    from platforms import get_registry
    from platforms.twitter import TwitterPlatform
    registry = get_registry()
    registry.register(TwitterPlatform())

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.create_tweet.side_effect = Exception("403 Forbidden: duplicate tweet")

        from mcp_server import post_tweet
        result = await post_tweet("Hello world!")

    assert "Error posting tweet" in result
    assert "403 Forbidden" in result


# --- post_tweet with DB credentials (Task 8.4) ---


async def test_post_tweet_uses_db_credentials(db_session, monkeypatch):
    """post_tweet loads credentials from DB when available."""
    monkeypatch.delenv("TWITTER_API_KEY", raising=False)
    monkeypatch.delenv("TWITTER_API_SECRET", raising=False)
    monkeypatch.delenv("TWITTER_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("TWITTER_ACCESS_SECRET", raising=False)

    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)

    # Register the twitter platform
    from platforms import get_registry
    from platforms.twitter import TwitterPlatform
    registry = get_registry()
    registry.register(TwitterPlatform())

    # Store encrypted credentials in DB
    from platforms.credentials import encrypt
    from models import PlatformCredential
    creds = {
        "api_key": "db-key",
        "api_secret": "db-secret",
        "access_token": "db-token",
        "access_secret": "db-access",
    }
    _, session_factory = db_session
    async with session_factory() as session:
        session.add(PlatformCredential(
            platform_id="twitter",
            encrypted_data=encrypt(creds),
            status="connected",
        ))
        await session.commit()

    mock_response = type("Response", (), {"data": {"id": "777"}})()
    mock_user = type("User", (), {"data": type("Data", (), {"username": "dbuser"})()})()

    with patch("tweepy.Client") as MockClient:
        instance = MockClient.return_value
        instance.create_tweet.return_value = mock_response
        instance.get_me.return_value = mock_user

        from mcp_server import post_tweet
        result = await post_tweet("DB tweet!")

    assert "https://x.com/dbuser/status/777" in result
    # Verify the DB credentials were used
    MockClient.assert_called_once_with(
        consumer_key="db-key",
        consumer_secret="db-secret",
        access_token="db-token",
        access_token_secret="db-access",
    )


# --- Email MCP tools (Task 7.3) ---


FAKE_EMAIL_CREDS = {
    "imap_host": "imap.example.com",
    "imap_port": "993",
    "smtp_host": "smtp.example.com",
    "smtp_port": "465",
    "security": "ssl",
    "username": "user@example.com",
    "password": "secret",
    "authorized_recipients": "allowed@example.com\nboss@example.com",
}


def _make_test_email(subject="Test", sender="alice@test.com", body="Hello world"):
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "user@example.com"
    msg["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    msg.set_content(body)
    return msg.as_bytes()


async def test_list_emails_success(db_session):
    """list_emails returns JSON with messages array."""
    mock_imap = AsyncMock()

    search_resp = MagicMock()
    search_resp.result = "OK"
    search_resp.lines = [b"1 2"]
    mock_imap.search.return_value = search_resp
    mock_imap.select.return_value = MagicMock()

    fetch_resp = MagicMock()
    fetch_resp.result = "OK"
    fetch_resp.lines = [b"1 FETCH (UID 1 FLAGS (\\Seen))"]
    mock_imap.fetch.return_value = fetch_resp

    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS), \
         patch("mcp_server._connect_imap", return_value=mock_imap):
        from mcp_server import list_emails
        result = await list_emails()

    data = json.loads(result)
    assert "messages" in data
    assert isinstance(data["messages"], list)


async def test_list_emails_no_credentials(db_session):
    """list_emails returns error when no credentials configured."""
    with patch("mcp_server._get_email_credentials", return_value=None):
        from mcp_server import list_emails
        result = await list_emails()

    data = json.loads(result)
    assert "error" in data
    assert "not configured" in data["error"]


async def test_read_email_success(db_session):
    """read_email returns JSON with body, headers, attachments."""
    raw_email = _make_test_email(subject="Read Me", body="Email body here")
    mock_imap = AsyncMock()
    mock_imap.select.return_value = MagicMock()

    fetch_resp = MagicMock()
    fetch_resp.result = "OK"
    fetch_resp.lines = [raw_email]
    mock_imap.fetch.return_value = fetch_resp

    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS), \
         patch("mcp_server._connect_imap", return_value=mock_imap):
        from mcp_server import read_email
        result = await read_email("1")

    data = json.loads(result)
    assert data["subject"] == "Read Me"
    assert "Email body here" in data["body"]
    assert "attachments" in data
    assert "from" in data


async def test_list_email_folders_success(db_session):
    """list_email_folders returns JSON with folders."""
    mock_imap = AsyncMock()

    list_resp = MagicMock()
    list_resp.result = "OK"
    list_resp.lines = [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent"']
    mock_imap.list.return_value = list_resp

    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS), \
         patch("mcp_server._connect_imap", return_value=mock_imap):
        from mcp_server import list_email_folders
        result = await list_email_folders()

    data = json.loads(result)
    assert "folders" in data
    assert isinstance(data["folders"], list)


async def test_move_email_success(db_session):
    """move_email success case."""
    mock_imap = AsyncMock()
    mock_imap.select.return_value = MagicMock()

    # LIST response for target folder (no blocked attributes)
    list_resp = MagicMock()
    list_resp.result = "OK"
    list_resp.lines = [b'(\\HasNoChildren) "/" "Archive"']
    mock_imap.list.return_value = list_resp

    copy_resp = MagicMock()
    copy_resp.result = "OK"
    mock_imap.copy.return_value = copy_resp

    mock_imap.store.return_value = MagicMock()
    mock_imap.expunge.return_value = MagicMock()
    mock_imap.create.return_value = MagicMock()

    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS), \
         patch("mcp_server._connect_imap", return_value=mock_imap):
        from mcp_server import move_email
        result = await move_email("1", "Archive")

    data = json.loads(result)
    assert data["success"] is True


async def test_move_email_blocked_folder(db_session):
    """move_email to Trash returns error."""
    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS):
        from mcp_server import move_email
        result = await move_email("1", "Trash")

    data = json.loads(result)
    assert "error" in data
    assert "not permitted" in data["error"]


# --- Blocked folder detection (Task 7.4) ---


class TestIsBlockedFolder:
    def test_trash(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("Trash") is True

    def test_trash_case_insensitive(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("TRASH") is True

    def test_gmail_trash(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("[Gmail]/Trash") is True

    def test_junk(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("Junk") is True

    def test_spam(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("Spam") is True

    def test_deleted_items(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("Deleted Items") is True

    def test_safe_folder_invoices(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("Invoices") is False

    def test_safe_folder_archive(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("Archive") is False

    def test_special_use_trash(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("SomeFolder", ["\\Trash"]) is True

    def test_special_use_junk(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("SomeFolder", ["\\Junk"]) is True

    def test_special_use_no_match(self):
        from mcp_server import _is_blocked_folder
        assert _is_blocked_folder("SomeFolder", ["\\HasNoChildren"]) is False


# --- Authorized recipient enforcement (Task 7.5) ---


async def test_send_email_authorized_recipient(db_session):
    """send_email with authorized recipient succeeds."""
    mock_smtp_instance = AsyncMock()
    mock_aiosmtplib = MagicMock()
    mock_aiosmtplib.SMTP.return_value = mock_smtp_instance

    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS), \
         patch.dict("sys.modules", {"aiosmtplib": mock_aiosmtplib}):
        from mcp_server import send_email
        result = await send_email("allowed@example.com", "Subject", "Body")

    data = json.loads(result)
    assert data["success"] is True


async def test_send_email_unauthorized_recipient(db_session):
    """send_email with unauthorized recipient returns error."""
    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS):
        from mcp_server import send_email
        result = await send_email("hacker@evil.com", "Subject", "Body")

    data = json.loads(result)
    assert "error" in data
    assert "not in authorised" in data["error"]


async def test_send_email_no_authorized_recipients(db_session):
    """send_email with no authorized_recipients configured returns error."""
    creds_no_auth = {**FAKE_EMAIL_CREDS, "authorized_recipients": ""}

    with patch("mcp_server._get_email_credentials", return_value=creds_no_auth):
        from mcp_server import send_email
        result = await send_email("anyone@example.com", "Subject", "Body")

    data = json.loads(result)
    assert "error" in data
    assert "No recipients are authorised" in data["error"]


async def test_forward_email_authorized_recipient(db_session):
    """forward_email with authorized recipient succeeds."""
    raw_email = _make_test_email(subject="Forward Me", body="Original content")
    mock_imap = AsyncMock()
    mock_imap.select.return_value = MagicMock()

    fetch_resp = MagicMock()
    fetch_resp.result = "OK"
    fetch_resp.lines = [raw_email]
    mock_imap.fetch.return_value = fetch_resp

    mock_smtp_instance = AsyncMock()
    mock_aiosmtplib = MagicMock()
    mock_aiosmtplib.SMTP.return_value = mock_smtp_instance

    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS), \
         patch("mcp_server._connect_imap", return_value=mock_imap), \
         patch.dict("sys.modules", {"aiosmtplib": mock_aiosmtplib}):
        from mcp_server import forward_email
        result = await forward_email("1", "allowed@example.com")

    data = json.loads(result)
    assert data["success"] is True


async def test_forward_email_unauthorized_recipient(db_session):
    """forward_email with unauthorized recipient returns error."""
    with patch("mcp_server._get_email_credentials", return_value=FAKE_EMAIL_CREDS):
        from mcp_server import forward_email
        result = await forward_email("1", "hacker@evil.com")

    data = json.loads(result)
    assert "error" in data
    assert "not in authorised" in data["error"]


# --- web_search MCP tool ---


async def test_web_search_default_url(db_session):
    """web_search uses default URL when no credentials configured."""
    mock_search_result = {
        "query": "python frameworks",
        "results": [{"title": "Flask", "url": "https://flask.palletsprojects.com", "content": "A micro framework", "engines": ["google"], "score": 1.0}],
        "suggestions": [],
        "number_of_results": 10,
    }

    with patch("platforms.credentials.load_credentials", return_value=None), \
         patch("platforms.searxng.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_search_result
        mock_client.get.return_value = mock_response
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server import web_search
        result = await web_search("python frameworks")

    data = json.loads(result)
    assert data["query"] == "python frameworks"
    assert len(data["results"]) == 1
    assert data["results"][0]["title"] == "Flask"


async def test_web_search_with_db_credentials(db_session):
    """web_search uses DB credentials when available."""
    from cryptography.fernet import Fernet
    import os

    _, session_factory = db_session
    key = Fernet.generate_key().decode()
    os.environ["CREDENTIAL_ENCRYPTION_KEY"] = key

    from platforms.credentials import encrypt
    from models import PlatformCredential
    creds = {"url": "https://custom.search.com", "username": "user", "password": "pass"}
    async with session_factory() as session:
        session.add(PlatformCredential(
            platform_id="searxng",
            encrypted_data=encrypt(creds),
            status="connected",
        ))
        await session.commit()

    mock_search_result = {
        "results": [{"title": "R1", "url": "https://r1.com", "content": "c", "engines": ["g"], "score": 1.0}],
        "suggestions": [],
        "number_of_results": 1,
    }

    with patch("platforms.searxng.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_search_result
        mock_client.get.return_value = mock_response
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server import web_search
        result = await web_search("test")

    data = json.loads(result)
    assert "results" in data
    # Verify custom URL was used
    call_args = mock_client.get.call_args
    assert "custom.search.com" in call_args.args[0]

    os.environ.pop("CREDENTIAL_ENCRYPTION_KEY", None)


async def test_web_search_error_handling(db_session):
    """web_search returns error JSON when SearXNG is unreachable."""
    import httpx

    with patch("platforms.credentials.load_credentials", return_value=None), \
         patch("platforms.searxng.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server import web_search
        result = await web_search("test")

    data = json.loads(result)
    assert "error" in data


# --- read_url MCP tool ---


async def test_read_url_success(db_session):
    """read_url fetches URL and returns JSON with title and markdown content."""
    html = "<html><head><title>Test Page</title></head><body><h1>Hello</h1><p>World</p></body></html>"

    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server import read_url
        result = await read_url("https://example.com")

    data = json.loads(result)
    assert data["url"] == "https://example.com"
    assert data["title"] == "Test Page"
    assert "Hello" in data["content"]


async def test_read_url_no_title(db_session):
    """read_url returns empty title when HTML has no <title> tag."""
    html = "<html><body><p>No title here</p></body></html>"

    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server import read_url
        result = await read_url("https://example.com")

    data = json.loads(result)
    assert data["title"] == ""


async def test_read_url_truncation(db_session):
    """read_url truncates content to max_length."""
    html = "<html><head><title>Big</title></head><body>" + "<p>x</p>" * 10000 + "</body></html>"

    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server import read_url
        result = await read_url("https://example.com", max_length=100)

    data = json.loads(result)
    assert len(data["content"]) <= 100


async def test_read_url_fetch_error(db_session):
    """read_url returns error JSON on fetch failure."""
    import httpx

    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server import read_url
        result = await read_url("https://bad.example.com")

    data = json.loads(result)
    assert "error" in data


async def test_read_url_timeout(db_session):
    """read_url returns error JSON on timeout."""
    import httpx

    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server import read_url
        result = await read_url("https://slow.example.com")

    data = json.loads(result)
    assert "error" in data
    assert "Timeout" in data["error"]
