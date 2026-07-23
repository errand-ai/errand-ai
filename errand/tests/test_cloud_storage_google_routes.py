"""Tests for the library-facing cloud-storage and google-workspace adapters.

These endpoints (`/api/cloud-storage/*`, `/api/google-workspace/*`) reuse the
`/api/integrations` OAuth machinery but return the shapes the shared
`@errand-ai/ui-components` cards consume (`CloudStorageStatus`,
`GoogleWorkspaceStatus`, and their authorize responses).
"""

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
from fakeredis.aioredis import FakeRedis
from main import app
from database import get_session
from integration_routes import _require_user
from models import PlatformCredential
from platforms.credentials import encrypt
from tests.conftest import _create_tables


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture()
async def client(monkeypatch):
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
        yield ac, session_factory

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def _seed_credential(session_factory, provider: str, **data):
    async with session_factory() as session:
        session.add(PlatformCredential(
            platform_id=provider,
            encrypted_data=encrypt({"access_token": "tok", "refresh_token": "r", **data}),
            status="connected",
        ))
        await session.commit()


# --- Cloud storage (OneDrive) ---

@pytest.mark.anyio
async def test_cloud_storage_status_not_connected(client):
    ac, _ = client
    resp = await ac.get("/api/cloud-storage/status")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"connected": False, "provider": None, "account": None, "authorize_url": None}


@pytest.mark.anyio
async def test_cloud_storage_status_connected(client):
    ac, session_factory = client
    await _seed_credential(session_factory, "onedrive", user_email="me@corp.com", user_name="Me")
    resp = await ac.get("/api/cloud-storage/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["provider"] == "onedrive"
    assert body["account"] == "me@corp.com"


@pytest.mark.anyio
async def test_cloud_storage_authorize_returns_authorize_url(client, monkeypatch):
    ac, _ = client
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-secret")
    resp = await ac.post("/api/cloud-storage/authorize")
    assert resp.status_code == 200
    body = resp.json()
    assert "authorize_url" in body
    assert body["authorize_url"].startswith("https://login.microsoftonline.com/")
    assert "ms-client-id" in body["authorize_url"]


@pytest.mark.anyio
async def test_cloud_storage_disconnect_idempotent(client):
    ac, session_factory = client
    await _seed_credential(session_factory, "onedrive", user_email="me@corp.com")
    # First delete removes the connection
    resp = await ac.request("DELETE", "/api/cloud-storage")
    assert resp.status_code == 204
    # Second delete is idempotent
    resp = await ac.request("DELETE", "/api/cloud-storage")
    assert resp.status_code == 204
    # Status now not-connected
    resp = await ac.get("/api/cloud-storage/status")
    assert resp.json()["connected"] is False


# --- Google Workspace (google_drive) ---

@pytest.mark.anyio
async def test_google_workspace_status_not_connected(client):
    ac, _ = client
    resp = await ac.get("/api/google-workspace/status")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"connected": False, "email": None, "scopes": None}


@pytest.mark.anyio
async def test_google_workspace_status_connected(client):
    ac, session_factory = client
    await _seed_credential(
        session_factory, "google_drive",
        user_email="me@gmail.com",
        granted_scopes=["https://www.googleapis.com/auth/drive"],
    )
    resp = await ac.get("/api/google-workspace/status")
    body = resp.json()
    assert body["connected"] is True
    assert body["email"] == "me@gmail.com"
    assert body["scopes"] == ["https://www.googleapis.com/auth/drive"]


@pytest.mark.anyio
async def test_google_workspace_authorize_returns_redirect_url(client, monkeypatch):
    ac, _ = client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")
    resp = await ac.post("/api/google-workspace/authorize")
    assert resp.status_code == 200
    body = resp.json()
    assert "redirect_url" in body
    assert body["redirect_url"].startswith("https://accounts.google.com/")


@pytest.mark.anyio
async def test_google_workspace_disconnect_idempotent(client):
    ac, session_factory = client
    await _seed_credential(session_factory, "google_drive", user_email="me@gmail.com")
    resp = await ac.request("DELETE", "/api/google-workspace")
    assert resp.status_code == 204
    resp = await ac.request("DELETE", "/api/google-workspace")
    assert resp.status_code == 204


# --- Capability ⇒ working endpoint consistency (group 3) ---

@pytest.mark.anyio
async def test_cloud_storage_capability_implies_working_status(client, monkeypatch):
    """When `cloud_storage` is advertised, its status endpoint returns 200 JSON
    (never the SPA catch-all)."""
    ac, _ = client
    monkeypatch.setenv("ONEDRIVE_MCP_URL", "https://onedrive.example/mcp")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "ms-client-id")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "ms-secret")
    caps = (await ac.get("/api/capabilities")).json()["capabilities"]
    assert "cloud_storage" in caps
    resp = await ac.get("/api/cloud-storage/status")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.anyio
async def test_google_workspace_capability_implies_working_status(client, monkeypatch):
    """When `google_workspace` is advertised, its status endpoint returns 200 JSON."""
    ac, _ = client
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "goog-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "goog-secret")
    caps = (await ac.get("/api/capabilities")).json()["capabilities"]
    assert "google_workspace" in caps
    resp = await ac.get("/api/google-workspace/status")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
