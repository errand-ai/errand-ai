"""Tests for MCP server: API key generation, regeneration, tools, and auth."""
import secrets
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
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
    assert resp.json()["mcp_api_key"] == "test-key-123"


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


async def test_mcp_server_has_four_tools():
    """The MCP server exposes exactly four tools."""
    from mcp_server import mcp
    tools = mcp._tool_manager.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names == {"new_task", "task_status", "task_output", "post_tweet"}


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
