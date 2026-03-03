import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import auth as auth_module
import events as events_module
import main as main_module
from database import get_session

app = main_module.app

_JWT_SECRET = "testsecret1234567890123456789012345"


def _make_local_token(sub="test-user", expired=False):
    """Create a real local JWT token for SSE auth tests."""
    now = datetime.now(timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=24)
    claims = {
        "sub": sub,
        "email": f"{sub}@local",
        "_roles": ["admin"],
        "iss": "errand-local",
        "iat": now,
        "exp": exp,
    }
    return pyjwt.encode(claims, _JWT_SECRET, algorithm="HS256")


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

_FULL_TASKS_TABLE_SQL = """
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


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_FULL_TASKS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))


async def _seed_jwt_secret(session_factory):
    async with session_factory() as session:
        await session.execute(
            text("INSERT OR IGNORE INTO settings (key, value) VALUES ('jwt_signing_secret', :val)"),
            {"val": json.dumps(_JWT_SECRET)},
        )
        await session.commit()


async def _insert_task(session_factory, task_id, status="review"):
    hex_id = uuid.UUID(task_id).hex
    async with session_factory() as session:
        await session.execute(
            text("INSERT INTO tasks (id, title, status) VALUES (:id, :title, :status)"),
            {"id": hex_id, "title": "Test task", "status": status},
        )
        await session.commit()


class FakePubSub:
    """Pubsub mock that yields predefined messages then raises CancelledError."""

    def __init__(self, messages):
        self._messages = list(messages)
        self._idx = 0

    async def subscribe(self, channel):
        pass

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if self._idx < len(self._messages):
            msg = self._messages[self._idx]
            self._idx += 1
            return {"type": "message", "data": msg}
        # No more messages — raise CancelledError to terminate the generator
        raise asyncio.CancelledError()

    async def unsubscribe(self, channel):
        pass

    async def aclose(self):
        pass


class FakeValkeyWithPubSub:
    """Fake Valkey that returns a FakePubSub with predefined messages."""

    def __init__(self, messages):
        self._messages = messages

    def pubsub(self):
        return FakePubSub(self._messages)


@pytest.fixture()
async def sse_app():
    """Set up the app with local JWT auth and fake Valkey for SSE tests."""
    from fakeredis.aioredis import FakeRedis

    fake_redis = FakeRedis(decode_responses=True)
    events_module._valkey = fake_redis
    original_oidc = getattr(auth_module, "oidc", None)
    auth_module.oidc = None

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_jwt_secret(test_session)

    original_async_session = main_module.async_session
    main_module.async_session = test_session

    async def override_get_session():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    yield app, fake_redis, test_session

    app.dependency_overrides.clear()
    auth_module.oidc = original_oidc
    main_module.async_session = original_async_session
    events_module._valkey = None
    await fake_redis.aclose()
    await engine.dispose()


# ---------------------------------------------------------------------------
# SSE task events tests (/api/events)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_events_missing_token(sse_app):
    test_app, _, _ = sse_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/events")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_events_invalid_token(sse_app):
    test_app, _, _ = sse_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/events?token=bad-token")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_events_expired_token(sse_app):
    test_app, _, _ = sse_app
    expired_token = _make_local_token(expired=True)
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/events?token={expired_token}")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_events_receives_events(sse_app):
    """Test that SSE endpoint streams task events in correct format."""
    test_app, _, _ = sse_app
    valid_token = _make_local_token()

    messages = [
        json.dumps({"event": "task_created", "task": {"id": "1", "title": "New task"}}),
        json.dumps({"event": "task_updated", "task": {"id": "1", "status": "running"}}),
    ]
    events_module._valkey = FakeValkeyWithPubSub(messages)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/events?token={valid_token}")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        body = resp.text
        assert "event: task_created" in body
        assert "event: task_updated" in body
        assert '"task": {"id": "1"' in body or '"id": "1"' in body


@pytest.mark.asyncio
async def test_sse_events_cloud_status(sse_app):
    """Test that cloud_status events are forwarded."""
    test_app, _, _ = sse_app
    valid_token = _make_local_token()

    messages = [
        json.dumps({"event": "cloud_status", "task": {"status": "connected"}}),
    ]
    events_module._valkey = FakeValkeyWithPubSub(messages)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/events?token={valid_token}")
        assert resp.status_code == 200
        assert "event: cloud_status" in resp.text


# ---------------------------------------------------------------------------
# SSE log streaming tests (/api/tasks/{task_id}/logs/stream)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_logs_missing_token(sse_app):
    test_app, _, _ = sse_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{uuid.uuid4()}/logs/stream")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_logs_invalid_token(sse_app):
    test_app, _, _ = sse_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{uuid.uuid4()}/logs/stream?token=bad-token")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_logs_expired_token(sse_app):
    test_app, _, _ = sse_app
    expired_token = _make_local_token(expired=True)
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{uuid.uuid4()}/logs/stream?token={expired_token}")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_logs_nonexistent_task(sse_app):
    test_app, _, _ = sse_app
    valid_token = _make_local_token()
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{uuid.uuid4()}/logs/stream?token={valid_token}")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sse_logs_non_running_task(sse_app):
    """Non-running task sends task_log_end immediately."""
    test_app, _, test_session = sse_app
    task_id = str(uuid.uuid4())
    await _insert_task(test_session, task_id, "completed")
    valid_token = _make_local_token()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{task_id}/logs/stream?token={valid_token}")
        assert resp.status_code == 200
        assert "event: task_log_end" in resp.text
        assert "data: {}" in resp.text


@pytest.mark.asyncio
async def test_sse_logs_forwards_and_closes(sse_app):
    """Running task forwards log lines and closes on task_log_end."""
    test_app, _, test_session = sse_app
    task_id = str(uuid.uuid4())
    await _insert_task(test_session, task_id, "running")

    messages = [
        json.dumps({"event": "task_log", "line": "Building...\n"}),
        json.dumps({"event": "task_log", "line": "Done.\n"}),
        json.dumps({"event": "task_log_end"}),
    ]
    events_module._valkey = FakeValkeyWithPubSub(messages)
    valid_token = _make_local_token()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/tasks/{task_id}/logs/stream?token={valid_token}")
        assert resp.status_code == 200
        body = resp.text

        # Verify log lines were forwarded
        assert "event: log" in body
        assert "Building..." in body
        assert "Done." in body
        # Verify end sentinel
        assert "event: task_log_end" in body
