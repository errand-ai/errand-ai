"""Tests for cloud auth routes (login, callback, disconnect, status)."""
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from cryptography.fernet import Fernet
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
from main import app
from database import get_session

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
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
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

FERNET_KEY = Fernet.generate_key().decode()


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_SETTINGS_TABLE_SQL))
        await conn.execute(text(_PLATFORM_CREDENTIALS_TABLE_SQL))
        await conn.execute(text(_TASKS_TABLE_SQL))
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))


@pytest.fixture()
async def cloud_client() -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker], None]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session

    with patch.dict("os.environ", {"CREDENTIAL_ENCRYPTION_KEY": FERNET_KEY}):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, test_session

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


def _admin_headers():
    """Headers with a mock admin token."""
    return {"Authorization": "Bearer admin-token"}


def _mock_admin_user():
    """Mock the require_admin dependency."""
    from main import require_admin

    async def override():
        return {"sub": "admin", "_roles": ["admin"]}
    app.dependency_overrides[require_admin] = override


class TestCloudAuthLogin:
    @pytest.mark.asyncio
    async def test_login_redirects_to_cloud_tenant_auth(self, cloud_client):
        client, _ = cloud_client
        _mock_admin_user()

        resp = await client.get("/api/cloud/auth/login")
        assert resp.status_code == 200
        data = resp.json()
        assert "redirect_url" in data
        assert "/auth/tenant/login" in data["redirect_url"]
        assert "redirect_uri=" in data["redirect_url"]

    @pytest.mark.asyncio
    async def test_login_returns_503_when_not_configured(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        with patch("main._get_cloud_url", new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/cloud/auth/login", follow_redirects=False)
            assert resp.status_code == 503
            assert "not configured" in resp.json()["detail"]


class TestCloudAuthCallback:
    @pytest.mark.asyncio
    async def test_callback_error_closes_popup(self, cloud_client):
        client, _ = cloud_client

        resp = await client.get(
            "/api/cloud/auth/callback?error=access_denied",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        body = resp.text
        assert "window.close()" in body
        assert "access_denied" in body

    @pytest.mark.asyncio
    async def test_callback_missing_code(self, cloud_client):
        client, _ = cloud_client

        resp = await client.get(
            "/api/cloud/auth/callback",
            follow_redirects=False,
        )
        assert resp.status_code == 400
        assert "Missing code" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_callback_success_stores_credentials(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        mock_tokens = {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.eyJzdWIiOiJ0ZW5hbnQtMTIzIiwiZXhwIjo5OTk5OTk5OTk5fQ.",
            "refresh_token": "refresh-token-123",
            "expires_in": 300,
        }

        with patch("main.exchange_code", new_callable=AsyncMock, return_value=mock_tokens), \
             patch("cloud_client.start_cloud_client", new_callable=AsyncMock), \
             patch("cloud_endpoints.try_register_endpoints", new_callable=AsyncMock):
            resp = await client.get(
                "/api/cloud/auth/callback?code=test-code",
                follow_redirects=False,
            )

        assert resp.status_code == 200
        assert "window.close()" in resp.text

        # Verify credentials were stored
        from models import PlatformCredential
        from sqlalchemy import select
        async with session_maker() as session:
            result = await session.execute(
                select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
            )
            cred = result.scalar_one_or_none()
            assert cred is not None
            assert cred.status == "connected"


class TestCloudDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, cloud_client):
        client, _ = cloud_client
        _mock_admin_user()

        resp = await client.post("/api/cloud/auth/disconnect")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_disconnect_deletes_credentials(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        # Create cloud credentials
        from platforms.credentials import encrypt
        from models import PlatformCredential
        from sqlalchemy import select
        async with session_maker() as session:
            cred_data = encrypt({"access_token": "test", "refresh_token": "test", "token_expiry": 0, "tenant_id": "t1"})
            session.add(PlatformCredential(
                platform_id="cloud", encrypted_data=cred_data, status="connected",
            ))
            await session.commit()

        with patch("cloud_client.stop_cloud_client", new_callable=AsyncMock), \
             patch("cloud_endpoints.revoke_cloud_endpoints", new_callable=AsyncMock), \
             patch("main._get_cloud_url", new_callable=AsyncMock, return_value="https://test.cloud"):
            resp = await client.post("/api/cloud/auth/disconnect")

        assert resp.status_code == 200

        # Verify credentials deleted
        async with session_maker() as session:
            result = await session.execute(
                select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
            )
            assert result.scalar_one_or_none() is None


class TestCloudStatus:
    @pytest.mark.asyncio
    async def test_status_not_configured(self, cloud_client):
        client, _ = cloud_client
        _mock_admin_user()

        resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_configured"

    @pytest.mark.asyncio
    async def test_status_connected(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        from platforms.credentials import encrypt
        from models import PlatformCredential
        async with session_maker() as session:
            cred_data = encrypt({"access_token": "test", "refresh_token": "test", "token_expiry": 0, "tenant_id": "t1"})
            session.add(PlatformCredential(
                platform_id="cloud", encrypted_data=cred_data, status="connected",
            ))
            await session.commit()

        resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert data["tenant_id"] == "t1"
        assert data["slack_configured"] is False

    @pytest.mark.asyncio
    async def test_status_error(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        from platforms.credentials import encrypt
        from models import PlatformCredential
        async with session_maker() as session:
            cred_data = encrypt({"access_token": "test", "refresh_token": "test", "token_expiry": 0, "tenant_id": "t1"})
            session.add(PlatformCredential(
                platform_id="cloud", encrypted_data=cred_data, status="error",
            ))
            await session.commit()

        resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
