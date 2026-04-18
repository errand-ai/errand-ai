"""Tests for GET /api/auth/status endpoint."""
import os
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.conftest import _create_tables
from main import app
from database import get_session

import events as events_module
from fakeredis.aioredis import FakeRedis


async def _make_status_client():
    """Create a minimal client for auth status tests (no auth overrides)."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    return engine, session_factory, redis, transport


async def test_auth_status_setup_mode():
    """No OIDC, no local users → setup mode."""
    engine, session_factory, redis, transport = await _make_status_client()

    env_overrides = {
        "OIDC_DISCOVERY_URL": "",
        "OIDC_CLIENT_ID": "",
        "OIDC_CLIENT_SECRET": "",
    }
    with patch.dict(os.environ, env_overrides, clear=False):
        # Remove OIDC env vars entirely
        for key in ["OIDC_DISCOVERY_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"]:
            os.environ.pop(key, None)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "setup"
    assert "login_url" not in data

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_auth_status_local_mode():
    """No OIDC, local user exists → local mode."""
    engine, session_factory, redis, transport = await _make_status_client()

    import bcrypt
    async with session_factory() as session:
        password_hash = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
        await session.execute(
            text("INSERT INTO local_users (username, password_hash, role) VALUES ('admin', :hash, 'admin')"),
            {"hash": password_hash},
        )
        await session.commit()

    # Ensure no OIDC env vars
    env_clear = {}
    for key in ["OIDC_DISCOVERY_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"]:
        env_clear[key] = ""

    with patch.dict(os.environ, env_clear, clear=False):
        for key in ["OIDC_DISCOVERY_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"]:
            os.environ.pop(key, None)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "local"
    assert "login_url" not in data

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_auth_status_sso_mode_env():
    """OIDC env vars set → SSO mode."""
    engine, session_factory, redis, transport = await _make_status_client()

    env_overrides = {
        "OIDC_DISCOVERY_URL": "https://auth.example.com/.well-known/openid-configuration",
        "OIDC_CLIENT_ID": "test-client",
        "OIDC_CLIENT_SECRET": "test-secret",
    }
    with patch.dict(os.environ, env_overrides):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "sso"
    assert data["login_url"] == "/auth/login"

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_auth_status_sso_mode_db():
    """OIDC settings in DB → SSO mode."""
    engine, session_factory, redis, transport = await _make_status_client()

    async with session_factory() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('oidc_discovery_url', '\"https://auth.example.com\"')")
        )
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('oidc_client_id', '\"client-id\"')")
        )
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('oidc_client_secret', '\"client-secret\"')")
        )
        await session.commit()

    # Ensure no OIDC env vars
    for key in ["OIDC_DISCOVERY_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET"]:
        os.environ.pop(key, None)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "sso"

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()
