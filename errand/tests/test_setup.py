"""Tests for the setup wizard backend endpoints."""
import jwt
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import bcrypt

from tests.conftest import _create_tables
from main import app
from database import get_session

import events as events_module
from fakeredis.aioredis import FakeRedis


async def _make_setup_client():
    """Create a test client for setup tests with JWT secret pre-configured."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Pre-create JWT signing secret
    async with session_factory() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('jwt_signing_secret', '\"setupsecret1234567890123456789012\"')")
        )
        await session.commit()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    # Clear auth overrides so the endpoints use real auth logic
    from main import get_current_user, require_editor, require_admin
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_editor, None)
    app.dependency_overrides.pop(require_admin, None)

    transport = ASGITransport(app=app)
    return engine, session_factory, redis, transport


async def test_setup_create_user_success():
    engine, session_factory, redis, transport = await _make_setup_client()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/setup/create-user",
            json={"username": "myadmin", "password": "mypassword123"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Decode the JWT
    token = data["access_token"]
    claims = jwt.decode(token, "setupsecret1234567890123456789012", algorithms=["HS256"])
    assert claims["sub"] == "myadmin"
    assert claims["iss"] == "errand-local"

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_setup_create_user_already_exists():
    engine, session_factory, redis, transport = await _make_setup_client()

    # Pre-create a local user
    async with session_factory() as session:
        password_hash = bcrypt.hashpw(b"existingpass", bcrypt.gensalt()).decode()
        await session.execute(
            text("INSERT INTO local_users (username, password_hash, role) VALUES ('existing', :hash, 'admin')"),
            {"hash": password_hash},
        )
        await session.commit()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/setup/create-user",
            json={"username": "newadmin", "password": "newpassword"},
        )

    assert resp.status_code == 403
    assert "already completed" in resp.json()["detail"].lower()

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_setup_create_user_missing_fields():
    engine, session_factory, redis, transport = await _make_setup_client()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/setup/create-user",
            json={"username": "", "password": ""},
        )

    assert resp.status_code == 422
    assert "required" in resp.json()["detail"].lower()

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_setup_then_login():
    """After setup, the created user can log in."""
    engine, session_factory, redis, transport = await _make_setup_client()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user
        resp = await client.post(
            "/api/setup/create-user",
            json={"username": "admin", "password": "setuppass"},
        )
        assert resp.status_code == 200

        # Login
        resp = await client.post(
            "/auth/local/login",
            json={"username": "admin", "password": "setuppass"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()
