"""Tests for cloud storage integration OAuth routes."""

from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
from fakeredis.aioredis import FakeRedis
from main import app
from database import get_session
from integration_routes import _require_user
from models import PlatformCredential
from platforms.credentials import encrypt, decrypt
from tests.conftest import _create_tables


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture()
async def integration_client(monkeypatch):
    """Client for integration route tests with auth bypassed."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    async def override_require_user():
        return {"sub": "test-user", "email": "test@example.com", "_roles": ["admin"]}

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[_require_user] = override_require_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as ac:
        yield ac, session_factory, redis

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


# --- Authorize ---


@pytest.mark.anyio
async def test_authorize_google_drive(integration_client, monkeypatch):
    client, _, redis = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    resp = await client.get("/api/integrations/google_drive/authorize")
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "accounts.google.com" in location
    assert "goog-client-id" in location
    assert "access_type=offline" in location
    assert "drive" in location
    assert "state=" in location


@pytest.mark.anyio
async def test_authorize_onedrive(integration_client, monkeypatch):
    client, _, redis = integration_client
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-secret")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "my-tenant")

    resp = await client.get("/api/integrations/onedrive/authorize")
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "login.microsoftonline.com/my-tenant" in location
    assert "ms-client-id" in location
    assert "Files.ReadWrite.All" in location
    assert "state=" in location


@pytest.mark.anyio
async def test_authorize_not_configured(integration_client):
    """No local credentials and no cloud — returns 404 with descriptive error."""
    client, _, _ = integration_client
    resp = await client.get("/api/integrations/google_drive/authorize")
    assert resp.status_code == 404
    assert "configure client credentials or connect to errand cloud" in resp.json()["detail"].lower()


@pytest.mark.anyio
async def test_authorize_cloud_proxy_flow(integration_client, monkeypatch):
    """When no local credentials but cloud is connected, redirects to cloud service."""
    client, session_factory, redis = integration_client
    monkeypatch.setenv("GDRIVE_MCP_URL", "http://gdrive:8080/mcp")
    # No GOOGLE_CLIENT_ID/SECRET

    # Create cloud PlatformCredential
    async with session_factory() as session:
        from models import Setting
        session.add(PlatformCredential(
            platform_id="cloud",
            encrypted_data=encrypt({"access_token": "cloud-token"}),
            status="connected",
        ))
        session.add(Setting(key="cloud_service_url", value="https://cloud.example.com"))
        await session.commit()

    mock_ws = AsyncMock()
    with patch("cloud_client.is_connected", return_value=True), \
         patch("cloud_client.get_ws", return_value=mock_ws):
        resp = await client.get("/api/integrations/google_drive/authorize")

    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "cloud.example.com/oauth/google_drive/authorize" in location
    assert "state=" in location

    # Verify WS message was sent
    mock_ws.send.assert_called_once()
    import json
    sent = json.loads(mock_ws.send.call_args[0][0])
    assert sent["type"] == "oauth_initiate"
    assert sent["provider"] == "google_drive"


@pytest.mark.anyio
async def test_authorize_cloud_proxy_ws_disconnected(integration_client, monkeypatch):
    """Cloud credential exists but WS not connected — returns 503."""
    client, session_factory, _ = integration_client
    # No local credentials

    async with session_factory() as session:
        session.add(PlatformCredential(
            platform_id="cloud",
            encrypted_data=encrypt({"access_token": "cloud-token"}),
            status="connected",
        ))
        await session.commit()

    with patch("cloud_client.is_connected", return_value=False):
        resp = await client.get("/api/integrations/google_drive/authorize")

    assert resp.status_code == 503


@pytest.mark.anyio
async def test_authorize_unknown_provider(integration_client):
    client, _, _ = integration_client
    resp = await client.get("/api/integrations/dropbox/authorize")
    assert resp.status_code == 404


# --- Callback ---


def _mock_token_response(access_token="ya29.test", refresh_token="1//refresh", expires_in=3600):
    resp = Response(200, json={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "token_type": "Bearer",
    })
    return resp


def _mock_userinfo_response(email="user@example.com", name="Test User", provider="google_drive"):
    if provider == "google_drive":
        return Response(200, json={"email": email, "name": name})
    else:
        return Response(200, json={"mail": email, "displayName": name})


@pytest.mark.anyio
async def test_callback_google_success(integration_client, monkeypatch):
    client, session_factory, redis = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    # Set up valid OAuth state
    await redis.setex("oauth_state:test-state", 600, "google_drive")

    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_token_response()
    mock_client.get.return_value = _mock_userinfo_response()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("integration_routes.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get("/api/integrations/google_drive/callback?code=AUTH_CODE&state=test-state")

    assert resp.status_code == 307
    assert resp.headers["location"] == "/settings/integrations"

    # Verify state was consumed
    assert await redis.get("oauth_state:test-state") is None

    # Verify credentials were stored
    async with session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(PlatformCredential).where(PlatformCredential.platform_id == "google_drive")
        )
        cred = result.scalar_one()
        assert cred.status == "connected"
        data = decrypt(cred.encrypted_data)
        assert data["access_token"] == "ya29.test"
        assert data["refresh_token"] == "1//refresh"
        assert data["user_email"] == "user@example.com"
        assert data["user_name"] == "Test User"


@pytest.mark.anyio
async def test_callback_onedrive_success(integration_client, monkeypatch):
    client, session_factory, redis = integration_client
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-secret")

    await redis.setex("oauth_state:ms-state", 600, "onedrive")

    mock_client = AsyncMock()
    mock_client.post.return_value = _mock_token_response()
    mock_client.get.return_value = _mock_userinfo_response(provider="onedrive")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("integration_routes.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get("/api/integrations/onedrive/callback?code=AUTH_CODE&state=ms-state")

    assert resp.status_code == 307
    assert resp.headers["location"] == "/settings/integrations"


@pytest.mark.anyio
async def test_callback_invalid_state(integration_client, monkeypatch):
    """Callback with invalid state should be rejected."""
    client, _, redis = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    resp = await client.get("/api/integrations/google_drive/callback?code=AUTH_CODE&state=bad-state")
    assert resp.status_code == 307
    assert "error=invalid_state" in resp.headers["location"]


@pytest.mark.anyio
async def test_callback_missing_state(integration_client, monkeypatch):
    """Callback without state parameter should be rejected."""
    client, _, redis = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    resp = await client.get("/api/integrations/google_drive/callback?code=AUTH_CODE")
    assert resp.status_code == 307
    assert "error=invalid_state" in resp.headers["location"]


@pytest.mark.anyio
async def test_callback_oauth_error(integration_client, monkeypatch):
    client, _, _ = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    resp = await client.get("/api/integrations/google_drive/callback?error=access_denied")
    assert resp.status_code == 307
    assert "error=oauth_denied" in resp.headers["location"]


@pytest.mark.anyio
async def test_callback_token_exchange_failure(integration_client, monkeypatch):
    client, _, redis = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    await redis.setex("oauth_state:fail-state", 600, "google_drive")

    mock_client = AsyncMock()
    mock_client.post.return_value = Response(400, json={"error": "invalid_grant"})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("integration_routes.httpx.AsyncClient", return_value=mock_client):
        resp = await client.get("/api/integrations/google_drive/callback?code=BAD_CODE&state=fail-state")

    assert resp.status_code == 307
    assert "error=token_exchange_failed" in resp.headers["location"]


# --- Disconnect ---


@pytest.mark.anyio
async def test_disconnect(integration_client, monkeypatch):
    client, session_factory, _ = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    # Store a credential first
    async with session_factory() as session:
        cred = PlatformCredential(
            platform_id="google_drive",
            encrypted_data=encrypt({"access_token": "test"}),
            status="connected",
        )
        session.add(cred)
        await session.commit()

    resp = await client.delete("/api/integrations/google_drive")
    assert resp.status_code == 200

    # Verify credential was deleted
    async with session_factory() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(PlatformCredential).where(PlatformCredential.platform_id == "google_drive")
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.anyio
async def test_disconnect_idempotent(integration_client, monkeypatch):
    client, _, _ = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")

    resp = await client.delete("/api/integrations/google_drive")
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_disconnect_unknown_provider(integration_client):
    client, _, _ = integration_client
    resp = await client.delete("/api/integrations/dropbox")
    assert resp.status_code == 404


# --- Status ---


@pytest.mark.anyio
async def test_status_both_available_one_connected(integration_client, monkeypatch):
    client, session_factory, _ = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")
    monkeypatch.setenv("GDRIVE_MCP_URL", "http://gdrive:8080/mcp")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-secret")
    monkeypatch.setenv("ONEDRIVE_MCP_URL", "http://onedrive:8080/mcp")

    # Connect Google Drive only
    async with session_factory() as session:
        session.add(PlatformCredential(
            platform_id="google_drive",
            encrypted_data=encrypt({
                "access_token": "test",
                "user_email": "user@gmail.com",
                "user_name": "Test User",
            }),
            status="connected",
        ))
        await session.commit()

    resp = await client.get("/api/integrations/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["google_drive"]["available"] is True
    assert data["google_drive"]["connected"] is True
    assert data["google_drive"]["mode"] == "direct"
    assert data["google_drive"]["user_email"] == "user@gmail.com"

    assert data["onedrive"]["available"] is True
    assert data["onedrive"]["connected"] is False
    assert data["onedrive"]["mode"] == "direct"
    assert "user_email" not in data["onedrive"]


@pytest.mark.anyio
async def test_status_not_available(integration_client):
    """When env vars are not set, providers show as unavailable."""
    client, _, _ = integration_client
    resp = await client.get("/api/integrations/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["google_drive"]["available"] is False
    assert data["google_drive"]["connected"] is False
    assert data["google_drive"]["mode"] is None
    assert data["onedrive"]["available"] is False
    assert data["onedrive"]["connected"] is False
    assert data["onedrive"]["mode"] is None


@pytest.mark.anyio
async def test_status_partial_config(integration_client, monkeypatch):
    """Client ID set but no MCP URL — not available."""
    client, _, _ = integration_client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")
    # No GDRIVE_MCP_URL

    resp = await client.get("/api/integrations/status")
    data = resp.json()
    assert data["google_drive"]["available"] is False
    assert data["google_drive"]["mode"] is None
    assert data["google_drive"]["mcp_configured"] is False


@pytest.mark.anyio
async def test_status_cloud_mode(integration_client, monkeypatch):
    """When no local credentials but cloud is connected, mode is 'cloud'."""
    client, session_factory, _ = integration_client
    monkeypatch.setenv("GDRIVE_MCP_URL", "http://gdrive:8080/mcp")
    # No GOOGLE_CLIENT_ID/SECRET

    # Create cloud PlatformCredential
    async with session_factory() as session:
        session.add(PlatformCredential(
            platform_id="cloud",
            encrypted_data=encrypt({"access_token": "cloud-token"}),
            status="connected",
        ))
        await session.commit()

    resp = await client.get("/api/integrations/status")
    data = resp.json()
    assert data["google_drive"]["available"] is True
    assert data["google_drive"]["mode"] == "cloud"
    assert data["google_drive"]["connected"] is False
    assert data["google_drive"]["mcp_configured"] is True


@pytest.mark.anyio
async def test_status_cloud_not_connected(integration_client, monkeypatch):
    """MCP URL set, no local creds, cloud credential exists but not connected."""
    client, session_factory, _ = integration_client
    monkeypatch.setenv("GDRIVE_MCP_URL", "http://gdrive:8080/mcp")

    async with session_factory() as session:
        session.add(PlatformCredential(
            platform_id="cloud",
            encrypted_data=encrypt({"access_token": "cloud-token"}),
            status="error",
        ))
        await session.commit()

    resp = await client.get("/api/integrations/status")
    data = resp.json()
    assert data["google_drive"]["available"] is False
    assert data["google_drive"]["mode"] is None
    assert data["google_drive"]["mcp_configured"] is True


@pytest.mark.anyio
async def test_status_mcp_configured_field(integration_client, monkeypatch):
    """mcp_configured field reflects MCP URL presence."""
    client, _, _ = integration_client
    monkeypatch.setenv("ONEDRIVE_MCP_URL", "http://onedrive:8080/mcp")

    resp = await client.get("/api/integrations/status")
    data = resp.json()
    assert data["google_drive"]["mcp_configured"] is False
    assert data["onedrive"]["mcp_configured"] is True
