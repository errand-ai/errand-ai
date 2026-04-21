"""Tests for cloud auth routes (login, callback, disconnect, status)."""
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

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
        encrypted_env TEXT,
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
        assert "state=" in data["redirect_url"]

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
    async def test_callback_missing_state_returns_error(self, cloud_client):
        client, _ = cloud_client

        resp = await client.get(
            "/api/cloud/auth/callback?code=test-code",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "window.close()" in resp.text
        assert "Invalid or missing state" in resp.text

    @pytest.mark.asyncio
    async def test_callback_invalid_state_returns_error(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        # Generate a valid state via login
        resp = await client.get("/api/cloud/auth/login")
        assert resp.status_code == 200

        # Use a wrong state
        resp = await client.get(
            "/api/cloud/auth/callback?code=test-code&state=wrong-state",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Invalid or missing state" in resp.text

    @pytest.mark.asyncio
    async def test_callback_success_stores_credentials(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        # Generate a valid state via login
        login_resp = await client.get("/api/cloud/auth/login")
        redirect_url = login_resp.json()["redirect_url"]
        from urllib.parse import urlparse, parse_qs
        state = parse_qs(urlparse(redirect_url).query)["state"][0]

        mock_tokens = {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.eyJzdWIiOiJ0ZW5hbnQtMTIzIiwiZXhwIjo5OTk5OTk5OTk5fQ.",
            "refresh_token": "refresh-token-123",
            "expires_in": 300,
        }

        with patch("main.exchange_code", new_callable=AsyncMock, return_value=mock_tokens), \
             patch("cloud_client.start_cloud_client", new_callable=AsyncMock), \
             patch("cloud_endpoints.try_register_endpoints", new_callable=AsyncMock):
            resp = await client.get(
                f"/api/cloud/auth/callback?code=test-code&state={state}",
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
    async def test_disconnect_when_not_connected_publishes_not_configured(self, cloud_client):
        client, _ = cloud_client
        _mock_admin_user()

        with patch("main.publish_event", new_callable=AsyncMock) as mock_publish:
            resp = await client.post("/api/cloud/auth/disconnect")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_publish.assert_called_once_with("cloud_status", {"status": "not_configured"})

    @pytest.mark.asyncio
    async def test_disconnect_deletes_credentials_publishes_not_configured(self, cloud_client):
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
             patch("main._get_cloud_url", new_callable=AsyncMock, return_value="https://test.cloud"), \
             patch("main.publish_event", new_callable=AsyncMock) as mock_publish:
            resp = await client.post("/api/cloud/auth/disconnect")

        assert resp.status_code == 200
        mock_publish.assert_called_once_with("cloud_status", {"status": "not_configured"})

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
    async def test_status_connected_when_ws_active(self, cloud_client):
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

        with patch("cloud_client.is_connected", return_value=True), \
             patch("cloud_endpoints.fetch_subscription_status", new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert data["tenant_id"] == "t1"
        assert data["slack_configured"] is False

    @pytest.mark.asyncio
    async def test_status_disconnected_when_ws_inactive(self, cloud_client):
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

        with patch("cloud_client.is_connected", return_value=False):
            resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disconnected"
        assert data["tenant_id"] == "t1"

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

    @pytest.mark.asyncio
    async def test_status_includes_endpoint_error(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        from platforms.credentials import encrypt
        from models import PlatformCredential, Setting
        import json
        async with session_maker() as session:
            cred_data = encrypt({"access_token": "test", "refresh_token": "test", "token_expiry": 0, "tenant_id": "t1"})
            session.add(PlatformCredential(
                platform_id="cloud", encrypted_data=cred_data, status="connected",
            ))
            session.add(Setting(
                key="cloud_endpoint_error",
                value={"detail": "Active subscription required", "timestamp": 1234567890.0},
            ))
            await session.commit()

        with patch("cloud_client.is_connected", return_value=True), \
             patch("cloud_endpoints.fetch_subscription_status", new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert data["endpoint_error"] == {"detail": "Active subscription required"}

    @pytest.mark.asyncio
    async def test_status_includes_subscription(self, cloud_client):
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

        sub_data = {"active": True, "expires_at": "2026-12-31T23:59:59Z"}
        with patch("cloud_client.is_connected", return_value=True), \
             patch("cloud_endpoints.fetch_subscription_status", new_callable=AsyncMock, return_value=sub_data):
            resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription"] == sub_data

    @pytest.mark.asyncio
    async def test_status_omits_subscription_when_fetch_fails(self, cloud_client):
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

        with patch("cloud_client.is_connected", return_value=True), \
             patch("cloud_endpoints.fetch_subscription_status", new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "subscription" not in data
        assert "endpoint_error" not in data


class TestCloudDisconnectCleansEndpointError:
    @pytest.mark.asyncio
    async def test_disconnect_deletes_endpoint_error_setting(self, cloud_client):
        client, session_maker = cloud_client
        _mock_admin_user()

        from platforms.credentials import encrypt
        from models import PlatformCredential, Setting
        from sqlalchemy import select
        async with session_maker() as session:
            cred_data = encrypt({"access_token": "test", "refresh_token": "test", "token_expiry": 0, "tenant_id": "t1"})
            session.add(PlatformCredential(
                platform_id="cloud", encrypted_data=cred_data, status="connected",
            ))
            session.add(Setting(
                key="cloud_endpoint_error",
                value={"detail": "Active subscription required", "timestamp": 1234567890.0},
            ))
            await session.commit()

        with patch("cloud_client.stop_cloud_client", new_callable=AsyncMock), \
             patch("cloud_endpoints.revoke_cloud_endpoints", new_callable=AsyncMock), \
             patch("main._get_cloud_url", new_callable=AsyncMock, return_value="https://test.cloud"), \
             patch("main.publish_event", new_callable=AsyncMock):
            resp = await client.post("/api/cloud/auth/disconnect")

        assert resp.status_code == 200

        async with session_maker() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == "cloud_endpoint_error")
            )
            assert result.scalar_one_or_none() is None


class TestCloudEndpointErrorPersistence:
    @pytest.mark.asyncio
    async def test_registration_failure_stores_error(self, cloud_client):
        _, session_maker = cloud_client

        import httpx
        mock_response = httpx.Response(
            403,
            json={"detail": "Active subscription required"},
            request=httpx.Request("POST", "https://cloud.test/api/endpoints"),
        )

        async with session_maker() as session:
            with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                from cloud_endpoints import register_cloud_endpoints
                result = await register_cloud_endpoints(
                    cloud_creds={"access_token": "test"},
                    slack_creds={"signing_secret": "secret"},
                    cloud_service_url="https://cloud.test",
                    session=session,
                )
                assert result is None

            # Verify error was stored
            from models import Setting
            from sqlalchemy import select
            result = await session.execute(
                select(Setting).where(Setting.key == "cloud_endpoint_error")
            )
            error_setting = result.scalar_one_or_none()
            assert error_setting is not None
            assert error_setting.value["detail"] == "Active subscription required"

    @pytest.mark.asyncio
    async def test_successful_registration_clears_error(self, cloud_client):
        _, session_maker = cloud_client

        import httpx
        from models import Setting

        # Pre-populate an endpoint error
        async with session_maker() as session:
            session.add(Setting(
                key="cloud_endpoint_error",
                value={"detail": "Previous error", "timestamp": 1234567890.0},
            ))
            await session.commit()

        mock_response = httpx.Response(
            200,
            json={"integration": "slack", "endpoints": [{"type": "events", "url": "https://cloud.test/hook/t1", "token": "t1"}]},
            request=httpx.Request("POST", "https://cloud.test/api/endpoints"),
        )

        async with session_maker() as session:
            with patch("cloud_endpoints.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                from cloud_endpoints import register_cloud_endpoints
                result = await register_cloud_endpoints(
                    cloud_creds={"access_token": "test"},
                    slack_creds={"signing_secret": "secret"},
                    cloud_service_url="https://cloud.test",
                    session=session,
                )
                assert result is not None
                assert len(result) == 1

            # Verify error was cleared
            from sqlalchemy import select
            result = await session.execute(
                select(Setting).where(Setting.key == "cloud_endpoint_error")
            )
            assert result.scalar_one_or_none() is None


class TestProxyRequestMarker:
    """Verify mark_proxy_requests middleware sets state readable by route handlers."""

    @pytest.mark.asyncio
    async def test_proxy_secret_sets_marker_readable_by_route(self, cloud_client):
        """Marker set via setattr in middleware must be visible via getattr in route handler."""
        client, _ = cloud_client
        from cloud_auth_jwt import PROXY_SECRET, PROXY_SECRET_HEADER

        # Include a dummy Bearer token so HTTPBearer doesn't short-circuit with 403.
        # With the proxy secret, _try_cloud_jwt_auth reads the marker and attempts
        # cloud JWT validation — which fails with 401 for our bogus token.
        resp = await client.get(
            "/api/tasks",
            headers={
                "Authorization": "Bearer dummy",
                PROXY_SECRET_HEADER: PROXY_SECRET,
                "X-Cloud-JWT": "bogus-cloud-jwt",
            },
        )
        # 401 with "Invalid cloud token" = marker was set and cloud JWT path was taken
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid cloud token"

    @pytest.mark.asyncio
    async def test_without_proxy_secret_marker_not_set(self, cloud_client):
        """Without the proxy secret header, the marker should not be set."""
        client, _ = cloud_client

        # Without PROXY_SECRET_HEADER, _try_cloud_jwt_auth returns None (skips cloud auth).
        # Falls through to normal token validation which fails on the dummy token.
        resp = await client.get(
            "/api/tasks",
            headers={
                "Authorization": "Bearer dummy",
                "X-Cloud-JWT": "bogus-cloud-jwt",
            },
        )
        # Still 401, but NOT "Invalid cloud token" — proves marker was not set
        assert resp.status_code == 401
        assert resp.json()["detail"] != "Invalid cloud token"
