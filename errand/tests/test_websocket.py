import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import auth as auth_module
import events as events_module
import main as main_module
from fakeredis.aioredis import FakeRedis
from database import get_session

app = main_module.app
get_current_user = main_module.get_current_user

_JWT_SECRET = "testsecret1234567890123456789012345"


def _make_local_token(sub="test-user", expired=False):
    """Create a real local JWT token for WebSocket auth tests."""
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


# SQLite-compatible DDL
_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'review' NOT NULL,
    profile_id VARCHAR(36),
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


async def _seed_jwt_secret(session_factory):
    """Insert the JWT signing secret so local token validation works."""
    async with session_factory() as session:
        await session.execute(
            text("INSERT OR IGNORE INTO settings (key, value) VALUES ('jwt_signing_secret', :val)"),
            {"val": json.dumps(_JWT_SECRET)},
        )
        await session.commit()


@pytest.fixture()
def ws_app():
    """Set up the app with local JWT auth and fake Valkey for WebSocket tests."""
    fake_redis = FakeRedis(decode_responses=True)
    events_module._valkey = fake_redis
    original_oidc = getattr(auth_module, "oidc", None)
    auth_module.oidc = None  # Use local auth mode

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_create_tables(engine))

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    loop.run_until_complete(_seed_jwt_secret(test_session))

    # Patch async_session used directly by _validate_token
    original_async_session = main_module.async_session
    main_module.async_session = test_session

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return {"sub": "test-user", "_roles": ["admin"]}

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    yield app, fake_redis

    app.dependency_overrides.clear()
    auth_module.oidc = original_oidc
    main_module.async_session = original_async_session
    events_module._valkey = None
    loop.run_until_complete(fake_redis.aclose())
    loop.run_until_complete(engine.dispose())


def test_ws_missing_token(ws_app):
    test_app, _ = ws_app
    client = TestClient(test_app)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/tasks"):
            pass


def test_ws_invalid_token(ws_app):
    test_app, _ = ws_app
    client = TestClient(test_app)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/tasks?token=bad-token"):
            pass


def test_ws_expired_token(ws_app):
    test_app, _ = ws_app
    client = TestClient(test_app)
    expired_token = _make_local_token(expired=True)
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/ws/tasks?token={expired_token}"):
            pass


def test_ws_valid_token_connects(ws_app):
    test_app, fake_redis = ws_app
    client = TestClient(test_app)
    valid_token = _make_local_token()
    with client.websocket_connect(f"/api/ws/tasks?token={valid_token}") as ws:
        # Connection succeeded — send a dummy message to verify the connection is live
        # The server loop reads messages, so we can close cleanly
        pass


# ---------------------------------------------------------------------------
# ws_task_logs tests
# ---------------------------------------------------------------------------

# Full SQLite-compatible DDL (ORM Task model requires all columns)
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


async def _create_full_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_FULL_TASKS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))


async def _insert_task(session_factory, task_id, status="review"):
    # Store as 32-char hex (no hyphens) to match SQLAlchemy UUID(as_uuid=True) format
    hex_id = uuid.UUID(task_id).hex
    async with session_factory() as session:
        await session.execute(
            text("INSERT INTO tasks (id, title, status) VALUES (:id, :title, :status)"),
            {"id": hex_id, "title": "Test task", "status": status},
        )
        await session.commit()


class FakePubSub:
    """Pubsub mock that yields predefined messages."""

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
        await asyncio.sleep(timeout)
        return None

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
def ws_logs_app():
    """Set up the app with local JWT auth, fake Valkey, and full DB for ws_task_logs tests."""
    fake_redis = FakeRedis(decode_responses=True)
    events_module._valkey = fake_redis
    original_oidc = getattr(auth_module, "oidc", None)
    auth_module.oidc = None  # Use local auth mode

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_create_full_tables(engine))

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    loop.run_until_complete(_seed_jwt_secret(test_session))

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return {"sub": "test-user", "_roles": ["admin"]}

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Patch async_session used directly (not via DI) by ws_task_logs
    original_async_session = main_module.async_session
    main_module.async_session = test_session

    yield app, fake_redis, test_session

    app.dependency_overrides.clear()
    auth_module.oidc = original_oidc
    main_module.async_session = original_async_session
    events_module._valkey = None
    loop.run_until_complete(fake_redis.aclose())
    loop.run_until_complete(engine.dispose())


def test_ws_logs_missing_token(ws_logs_app):
    test_app, _, _ = ws_logs_app
    client = TestClient(test_app)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/tasks/fake-id/logs"):
            pass


def test_ws_logs_invalid_token(ws_logs_app):
    test_app, _, _ = ws_logs_app
    client = TestClient(test_app)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/tasks/fake-id/logs?token=bad-token"):
            pass


def test_ws_logs_expired_token(ws_logs_app):
    test_app, _, _ = ws_logs_app
    client = TestClient(test_app)
    expired_token = _make_local_token(expired=True)
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/ws/tasks/fake-id/logs?token={expired_token}"):
            pass


def test_ws_logs_nonexistent_task(ws_logs_app):
    test_app, _, _ = ws_logs_app
    client = TestClient(test_app)
    valid_token = _make_local_token()
    with pytest.raises(Exception):
        with client.websocket_connect(
            f"/api/ws/tasks/{uuid.uuid4()}/logs?token={valid_token}"
        ):
            pass


def test_ws_logs_non_running_task(ws_logs_app):
    test_app, _, test_session = ws_logs_app
    client = TestClient(test_app)
    task_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_insert_task(test_session, task_id, "completed"))
    valid_token = _make_local_token()

    with client.websocket_connect(
        f"/api/ws/tasks/{task_id}/logs?token={valid_token}"
    ) as ws:
        data = ws.receive_json()
        assert data == {"event": "task_log_end"}


def test_ws_logs_forwards_and_closes(ws_logs_app):
    test_app, _, test_session = ws_logs_app
    client = TestClient(test_app)
    task_id = str(uuid.uuid4())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_insert_task(test_session, task_id, "running"))

    # Replace Valkey with a mock that yields predefined messages
    messages = [
        json.dumps({"event": "task_log", "line": "Building...\n"}),
        json.dumps({"event": "task_log", "line": "Done.\n"}),
        json.dumps({"event": "task_log_end"}),
    ]
    events_module._valkey = FakeValkeyWithPubSub(messages)
    valid_token = _make_local_token()

    with client.websocket_connect(
        f"/api/ws/tasks/{task_id}/logs?token={valid_token}"
    ) as ws:
        data1 = json.loads(ws.receive_text())
        assert data1["event"] == "task_log"
        assert data1["line"] == "Building...\n"

        data2 = json.loads(ws.receive_text())
        assert data2["event"] == "task_log"
        assert data2["line"] == "Done.\n"

        data3 = json.loads(ws.receive_text())
        assert data3["event"] == "task_log_end"
