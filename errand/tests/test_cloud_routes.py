"""Tests for cloud auth routes (device grant, disconnect, status)."""
import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
import main
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
    is_eval BOOLEAN DEFAULT 0 NOT NULL,
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
    llm_timeout INTEGER,
    mcp_servers TEXT,
    litellm_mcp_servers TEXT,
    skill_ids TEXT,
            include_git_skills BOOLEAN NOT NULL DEFAULT 1,
        enabled_plugins TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_WEBHOOK_TRIGGERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS webhook_triggers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    enabled INTEGER DEFAULT 1 NOT NULL,
    source TEXT NOT NULL,
    profile_id VARCHAR(36) REFERENCES task_profiles(id) ON DELETE SET NULL,
    filters TEXT DEFAULT '{}' NOT NULL,
    actions TEXT DEFAULT '{}' NOT NULL,
    task_prompt TEXT,
    webhook_secret TEXT,
    cloud_webhook_url TEXT,
    cloud_endpoint_token TEXT,
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
        await conn.execute(text(_WEBHOOK_TRIGGERS_TABLE_SQL))


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

    main.app.dependency_overrides[get_session] = override_get_session

    with patch.dict("os.environ", {"CREDENTIAL_ENCRYPTION_KEY": FERNET_KEY}):
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, test_session

    main.app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


def _admin_headers():
    """Headers with a mock admin token."""
    return {"Authorization": "Bearer admin-token"}


def _mock_admin_user():
    """Mock the require_admin dependency."""
    async def override():
        return {"sub": "admin", "_roles": ["admin"]}
    main.app.dependency_overrides[main.require_admin] = override


@pytest.fixture()
def device_grant_state():
    """Reset the in-memory device grant around each test that touches it."""
    main_module = main

    main_module._cloud_device_grant = None
    main_module._cloud_device_task = None
    main_module._cloud_device_generation = 0
    yield main_module
    task = main_module._cloud_device_task
    if task is not None and not task.done():
        task.cancel()
    main_module._cloud_device_grant = None
    main_module._cloud_device_task = None


_GRANT = {
    "device_code": "dc-secret",
    "user_code": "JHBW-PMHF",
    "verification_uri": "https://cloud.test/auth/tenant/device",
    "verification_uri_complete": "https://cloud.test/auth/tenant/device?user_code=JHBW-PMHF",
    "expires_in": 600,
    "interval": 5,
}


class TestCloudAuthDeviceStart:
    @pytest.mark.asyncio
    async def test_requires_admin(self, cloud_client, device_grant_state):
        client, _ = cloud_client
        # Deliberately no _mock_admin_user()
        resp = await client.post("/api/cloud/auth/device")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_returns_verification_fields(self, cloud_client, device_grant_state):
        client, _ = cloud_client
        _mock_admin_user()

        with patch("main.request_device_code", new_callable=AsyncMock, return_value=dict(_GRANT)), \
             patch("main._run_device_grant", new_callable=AsyncMock):
            resp = await client.post("/api/cloud/auth/device")

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_code"] == "JHBW-PMHF"
        assert data["verification_uri"] == "https://cloud.test/auth/tenant/device"
        assert data["verification_uri_complete"].endswith("user_code=JHBW-PMHF")
        assert data["expires_in"] == 600

    @pytest.mark.asyncio
    async def test_never_returns_the_device_code(self, cloud_client, device_grant_state):
        """The device code is a bearer credential — it must not reach the browser."""
        client, _ = cloud_client
        _mock_admin_user()

        with patch("main.request_device_code", new_callable=AsyncMock, return_value=dict(_GRANT)), \
             patch("main._run_device_grant", new_callable=AsyncMock):
            resp = await client.post("/api/cloud/auth/device")

        assert "dc-secret" not in resp.text
        assert "device_code" not in resp.json()

        status_resp = await client.get("/api/cloud/auth/device/status")
        assert "dc-secret" not in status_resp.text
        assert "device_code" not in status_resp.json()

    @pytest.mark.asyncio
    async def test_returns_503_when_not_configured(self, cloud_client, device_grant_state):
        client, _ = cloud_client
        _mock_admin_user()

        with patch("main._get_cloud_url", new_callable=AsyncMock, return_value=None):
            resp = await client.post("/api/cloud/auth/device")
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_returns_502_when_the_cloud_rejects_initiation(self, cloud_client, device_grant_state):
        client, _ = cloud_client
        _mock_admin_user()

        with patch("main.request_device_code", new_callable=AsyncMock, side_effect=Exception("429")):
            resp = await client.post("/api/cloud/auth/device")
        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_second_initiation_abandons_the_first(self, cloud_client, device_grant_state):
        """A user who closed the tab must be able to restart, not wait out the grant."""
        client, _ = cloud_client
        main_module = device_grant_state
        _mock_admin_user()

        async def _never_finishes(*args, **kwargs):
            await asyncio.sleep(3600)

        with patch("main.request_device_code", new_callable=AsyncMock, return_value=dict(_GRANT)), \
             patch("main._run_device_grant", _never_finishes):
            first = await client.post("/api/cloud/auth/device")
            assert first.status_code == 200
            first_task = main_module._cloud_device_task
            assert first_task is not None

            second = await client.post("/api/cloud/auth/device")
            assert second.status_code == 200

        await asyncio.sleep(0)
        assert first_task.cancelled() or first_task.done()
        assert main_module._cloud_device_task is not first_task


class TestCloudAuthDeviceStatus:
    @pytest.mark.asyncio
    async def test_requires_admin(self, cloud_client, device_grant_state):
        client, _ = cloud_client
        resp = await client.get("/api/cloud/auth/device/status")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_none_in_progress(self, cloud_client, device_grant_state):
        client, _ = cloud_client
        _mock_admin_user()

        resp = await client.get("/api/cloud/auth/device/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "none"

    @pytest.mark.asyncio
    async def test_pending_includes_the_code_and_uri(self, cloud_client, device_grant_state):
        """A page reload must not lose an in-flight grant."""
        client, _ = cloud_client
        _mock_admin_user()

        with patch("main.request_device_code", new_callable=AsyncMock, return_value=dict(_GRANT)), \
             patch("main._run_device_grant", new_callable=AsyncMock):
            await client.post("/api/cloud/auth/device")

        resp = await client.get("/api/cloud/auth/device/status")
        data = resp.json()
        assert data["status"] == "pending"
        assert data["user_code"] == "JHBW-PMHF"
        assert data["verification_uri"] == "https://cloud.test/auth/tenant/device"
        assert data["verification_uri_complete"].endswith("user_code=JHBW-PMHF")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["connected", "denied", "expired", "error"])
    async def test_terminal_outcomes_are_distinct_from_pending(
        self, cloud_client, device_grant_state, status
    ):
        client, _ = cloud_client
        main_module = device_grant_state
        _mock_admin_user()

        main_module._cloud_device_grant = {"status": status}

        resp = await client.get("/api/cloud/auth/device/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == status


class TestRunDeviceGrant:
    """The completion path — what the retired callback used to do."""

    @pytest.mark.asyncio
    async def test_success_stores_credentials_and_starts_the_client(
        self, cloud_client, device_grant_state, monkeypatch
    ):
        _, session_maker = cloud_client
        main_module = device_grant_state
        monkeypatch.setattr(main_module, "async_session", session_maker)

        from cloud_auth import DEVICE_TOKENS, DeviceTokenResult
        tokens = {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.eyJzdWIiOiJ0ZW5hbnQtMTIzIiwiZW1haWwiOiJ1QGUuY29tIiwiZXhwIjo5OTk5OTk5OTk5fQ.",
            "refresh_token": "refresh-token-123",
            "expires_in": 300,
        }

        with patch("main.poll_until_complete", new_callable=AsyncMock,
                   return_value=DeviceTokenResult(outcome=DEVICE_TOKENS, tokens=tokens)), \
             patch("cloud_client.start_cloud_client", new_callable=AsyncMock) as start_ws, \
             patch("cloud_endpoints.try_register_endpoints", new_callable=AsyncMock) as register:
            await main_module._run_device_grant("https://cloud.test", "dc", 5, 600)

        assert main_module._cloud_device_grant["status"] == "connected"
        start_ws.assert_awaited_once()
        register.assert_awaited_once()

        from models import PlatformCredential
        from platforms.credentials import decrypt
        from sqlalchemy import select
        async with session_maker() as session:
            result = await session.execute(
                select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
            )
            cred = result.scalar_one_or_none()
            assert cred is not None
            assert cred.status == "connected"
            data = decrypt(cred.encrypted_data)
            assert data["tenant_id"] == "tenant-123"
            assert data["refresh_token"] == "refresh-token-123"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("outcome,expected", [
        ("access_denied", "denied"),
        ("expired_token", "expired"),
        ("error", "error"),
    ])
    async def test_failure_leaves_credentials_untouched(
        self, cloud_client, device_grant_state, monkeypatch, outcome, expected
    ):
        _, session_maker = cloud_client
        main_module = device_grant_state
        monkeypatch.setattr(main_module, "async_session", session_maker)

        from cloud_auth import DeviceTokenResult
        with patch("main.poll_until_complete", new_callable=AsyncMock,
                   return_value=DeviceTokenResult(outcome=outcome, detail="d")), \
             patch("cloud_client.start_cloud_client", new_callable=AsyncMock) as start_ws:
            await main_module._run_device_grant("https://cloud.test", "dc", 5, 600)

        assert main_module._cloud_device_grant["status"] == expected
        start_ws.assert_not_awaited()

        from models import PlatformCredential
        from sqlalchemy import select
        async with session_maker() as session:
            result = await session.execute(
                select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
            )
            assert result.scalar_one_or_none() is None


    @pytest.mark.asyncio
    async def test_no_polling_task_survives_a_terminal_outcome(
        self, cloud_client, device_grant_state, monkeypatch
    ):
        """The poller must not outlive the grant it polls for."""
        client, session_maker = cloud_client
        main_module = device_grant_state
        monkeypatch.setattr(main_module, "async_session", session_maker)
        _mock_admin_user()

        from cloud_auth import DEVICE_DENIED, DeviceTokenResult
        with patch("main.request_device_code", new_callable=AsyncMock, return_value=dict(_GRANT)), \
             patch("main.poll_until_complete", new_callable=AsyncMock,
                   return_value=DeviceTokenResult(outcome=DEVICE_DENIED)):
            resp = await client.post("/api/cloud/auth/device")
            assert resp.status_code == 200
            task = main_module._cloud_device_task
            await asyncio.wait_for(task, timeout=5)

        assert task.done()
        status = await client.get("/api/cloud/auth/device/status")
        assert status.json()["status"] == "denied"


    @pytest.mark.asyncio
    async def test_a_superseded_poller_writes_nothing(
        self, cloud_client, device_grant_state, monkeypatch
    ):
        """A slow loser must not overwrite the grant that replaced it."""
        _, session_maker = cloud_client
        main_module = device_grant_state
        monkeypatch.setattr(main_module, "async_session", session_maker)

        main_module._cloud_device_generation = 2
        main_module._cloud_device_grant = {"status": "pending", "user_code": "NEW-CODE"}

        from cloud_auth import DEVICE_TOKENS, DeviceTokenResult
        tokens = {
            "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.eyJzdWIiOiJ0ZW5hbnQtOTk5In0.",
            "refresh_token": "stale-rt",
            "expires_in": 300,
        }

        with patch("main.poll_until_complete", new_callable=AsyncMock,
                   return_value=DeviceTokenResult(outcome=DEVICE_TOKENS, tokens=tokens)), \
             patch("cloud_client.start_cloud_client", new_callable=AsyncMock) as start_ws:
            await main_module._run_device_grant("https://cloud.test", "dc", 5, 600, 1)

        assert main_module._cloud_device_grant == {"status": "pending", "user_code": "NEW-CODE"}
        start_ws.assert_not_awaited()

        from models import PlatformCredential
        from sqlalchemy import select
        async with session_maker() as session:
            result = await session.execute(
                select(PlatformCredential).where(PlatformCredential.platform_id == "cloud")
            )
            assert result.scalar_one_or_none() is None


class TestMalformedCloudResponse:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("grant", [
        {"user_code": "AAAA-BBBB", "expires_in": 600, "interval": 5},          # no device code
        {"device_code": "dc", "expires_in": 600, "interval": 5},               # no user code
        {"device_code": "dc", "user_code": "A", "expires_in": "soon"},         # unusable expiry
        {"device_code": "dc", "user_code": "A", "expires_in": -1},             # already expired
        {"device_code": "dc", "user_code": "A", "expires_in": 600},            # nowhere to send the user
    ])
    async def test_returns_502_rather_than_starting_a_doomed_poller(
        self, cloud_client, device_grant_state, grant
    ):
        client, _ = cloud_client
        main_module = device_grant_state
        _mock_admin_user()

        with patch("main.request_device_code", new_callable=AsyncMock, return_value=grant), \
             patch("main._run_device_grant", new_callable=AsyncMock) as run:
            resp = await client.post("/api/cloud/auth/device")

        assert resp.status_code == 502
        run.assert_not_called()
        assert main_module._cloud_device_task is None


class TestRetiredRedirectFlow:
    @pytest.mark.asyncio
    async def test_callback_is_gone(self, cloud_client):
        client, _ = cloud_client
        resp = await client.get("/api/cloud/auth/callback?code=x&state=y", follow_redirects=False)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_login_redirect_endpoint_is_gone(self, cloud_client):
        client, _ = cloud_client
        _mock_admin_user()
        resp = await client.get("/api/cloud/auth/login", follow_redirects=False)
        assert resp.status_code == 404


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
             patch("cloud_endpoints.revoke_cloud_endpoints_for_integration", new_callable=AsyncMock), \
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

    @pytest.mark.asyncio
    async def test_status_includes_payment_warning_in_subscription(self, cloud_client):
        """A cloud_payment_warning Setting surfaces under subscription.payment_warning."""
        client, session_maker = cloud_client
        _mock_admin_user()

        from platforms.credentials import encrypt
        from models import PlatformCredential, Setting
        warning = {
            "alert": "payment_failed",
            "plan": "monthly",
            "attempt_count": 1,
            "next_retry_at": "2026-03-12T14:00:00Z",
            "final_attempt": False,
        }
        async with session_maker() as session:
            cred_data = encrypt({"access_token": "test", "refresh_token": "test", "token_expiry": 0, "tenant_id": "t1"})
            session.add(PlatformCredential(
                platform_id="cloud", encrypted_data=cred_data, status="connected",
            ))
            session.add(Setting(key="cloud_payment_warning", value=warning))
            await session.commit()

        sub_data = {"active": True, "expires_at": "2026-12-31T23:59:59Z"}
        with patch("cloud_client.is_connected", return_value=True), \
             patch("cloud_endpoints.fetch_subscription_status", new_callable=AsyncMock, return_value=sub_data):
            resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription"]["active"] is True
        assert data["subscription"]["payment_warning"] == warning

    @pytest.mark.asyncio
    async def test_status_payment_warning_without_subscription_fetch(self, cloud_client):
        """A payment warning surfaces even when the cloud subscription fetch returns nothing."""
        client, session_maker = cloud_client
        _mock_admin_user()

        from platforms.credentials import encrypt
        from models import PlatformCredential, Setting
        warning = {
            "alert": "payment_failed",
            "plan": "monthly",
            "attempt_count": 3,
            "next_retry_at": None,
            "final_attempt": True,
        }
        async with session_maker() as session:
            cred_data = encrypt({"access_token": "test", "refresh_token": "test", "token_expiry": 0, "tenant_id": "t1"})
            session.add(PlatformCredential(
                platform_id="cloud", encrypted_data=cred_data, status="connected",
            ))
            session.add(Setting(key="cloud_payment_warning", value=warning))
            await session.commit()

        with patch("cloud_client.is_connected", return_value=True), \
             patch("cloud_endpoints.fetch_subscription_status", new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/cloud/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription"]["payment_warning"] == warning

    @pytest.mark.asyncio
    async def test_status_omits_payment_warning_when_absent(self, cloud_client):
        """No cloud_payment_warning Setting → subscription carries no payment_warning."""
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
        assert "payment_warning" not in data["subscription"]


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
             patch("cloud_endpoints.revoke_cloud_endpoints_for_integration", new_callable=AsyncMock), \
             patch("main._get_cloud_url", new_callable=AsyncMock, return_value="https://test.cloud"), \
             patch("main.publish_event", new_callable=AsyncMock):
            resp = await client.post("/api/cloud/auth/disconnect")

        assert resp.status_code == 200

        async with session_maker() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == "cloud_endpoint_error")
            )
            assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_disconnect_deletes_payment_warning_setting(self, cloud_client):
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
                key="cloud_payment_warning",
                value={"alert": "payment_failed", "plan": "monthly", "attempt_count": 1,
                       "next_retry_at": "2026-03-12T14:00:00Z", "final_attempt": False},
            ))
            await session.commit()

        with patch("cloud_client.stop_cloud_client", new_callable=AsyncMock), \
             patch("cloud_endpoints.revoke_cloud_endpoints", new_callable=AsyncMock), \
             patch("cloud_endpoints.revoke_cloud_endpoints_for_integration", new_callable=AsyncMock), \
             patch("main._get_cloud_url", new_callable=AsyncMock, return_value="https://test.cloud"), \
             patch("main.publish_event", new_callable=AsyncMock):
            resp = await client.post("/api/cloud/auth/disconnect")

        assert resp.status_code == 200

        async with session_maker() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == "cloud_payment_warning")
            )
            assert result.scalar_one_or_none() is None


class TestCloudDisconnectClearsTriggerCloudColumns:
    @pytest.mark.asyncio
    async def test_disconnect_clears_cloud_columns_for_jira_and_github(self, cloud_client):
        """5.6 — cloud disconnect clears cloud_webhook_url and cloud_endpoint_token on every
        webhook_triggers row whose source is jira or github."""
        client, session_maker = cloud_client
        _mock_admin_user()

        from platforms.credentials import encrypt
        from models import PlatformCredential, WebhookTrigger
        from sqlalchemy import select
        import uuid as _uuid

        async with session_maker() as session:
            cred_data = encrypt({"access_token": "test", "refresh_token": "test", "token_expiry": 0, "tenant_id": "t1"})
            session.add(PlatformCredential(
                platform_id="cloud", encrypted_data=cred_data, status="connected",
            ))
            jira_tid = _uuid.uuid4()
            github_tid = _uuid.uuid4()
            session.add(WebhookTrigger(
                id=jira_tid, name="J1", source="jira",
                cloud_webhook_url="https://cloud.test/hook/j1",
                cloud_endpoint_token="j1tok",
            ))
            session.add(WebhookTrigger(
                id=github_tid, name="G1", source="github",
                cloud_webhook_url="https://cloud.test/hook/g1",
                cloud_endpoint_token="g1tok",
            ))
            await session.commit()

        with patch("cloud_client.stop_cloud_client", new_callable=AsyncMock), \
             patch("cloud_endpoints.revoke_cloud_endpoints", new_callable=AsyncMock), \
             patch("cloud_endpoints.revoke_cloud_endpoints_for_integration", new_callable=AsyncMock) as mock_bulk, \
             patch("main._get_cloud_url", new_callable=AsyncMock, return_value="https://test.cloud"), \
             patch("main.publish_event", new_callable=AsyncMock):
            resp = await client.post("/api/cloud/auth/disconnect")

        assert resp.status_code == 200

        # Bulk revoke called for both jira and github
        called_integrations = sorted(call.args[2] for call in mock_bulk.call_args_list)
        assert called_integrations == ["github", "jira"]

        async with session_maker() as session:
            for tid in (jira_tid, github_tid):
                row = (await session.execute(
                    select(WebhookTrigger).where(WebhookTrigger.id == tid)
                )).scalar_one()
                assert row.cloud_webhook_url is None
                assert row.cloud_endpoint_token is None


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
