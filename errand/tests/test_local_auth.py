"""Tests for local authentication endpoints."""
import jwt
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from passlib.hash import bcrypt

from tests.conftest import _create_tables
from main import app
from database import get_session

import events as events_module
from fakeredis.aioredis import FakeRedis


async def _setup_local_auth_client():
    """Create a test client with a local user and JWT secret, no auth overrides."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Create JWT signing secret and a local user
    async with session_factory() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('jwt_signing_secret', '\"testsecret123456789012345678901234\"')")
        )
        password_hash = bcrypt.hash("testpassword")
        await session.execute(
            text("INSERT INTO local_users (username, password_hash, role) VALUES ('testadmin', :hash, 'admin')"),
            {"hash": password_hash},
        )
        await session.commit()

    return engine, session_factory


async def test_local_login_success():
    engine, session_factory = await _setup_local_auth_client()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    # Clear auth overrides so real auth is used
    from main import get_current_user, require_editor, require_admin
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_editor, None)
    app.dependency_overrides.pop(require_admin, None)

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/local/login",
            json={"username": "testadmin", "password": "testpassword"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    # Decode and verify the JWT
    token = data["access_token"]
    claims = jwt.decode(token, "testsecret123456789012345678901234", algorithms=["HS256"])
    assert claims["sub"] == "testadmin"
    assert claims["iss"] == "errand-local"
    assert claims["email"] == "testadmin@local"
    assert "admin" in claims["_roles"]

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_local_login_wrong_password():
    engine, session_factory = await _setup_local_auth_client()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    from main import get_current_user, require_editor, require_admin
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_editor, None)
    app.dependency_overrides.pop(require_admin, None)

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/local/login",
            json={"username": "testadmin", "password": "wrongpassword"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_local_login_unknown_user():
    engine, session_factory = await _setup_local_auth_client()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    from main import get_current_user, require_editor, require_admin
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_editor, None)
    app.dependency_overrides.pop(require_admin, None)

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/local/login",
            json={"username": "nonexistent", "password": "whatever"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_local_login_missing_fields():
    engine, session_factory = await _setup_local_auth_client()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    from main import get_current_user, require_editor, require_admin
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_editor, None)
    app.dependency_overrides.pop(require_admin, None)

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/local/login",
            json={"username": ""},
        )

    assert resp.status_code == 422

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_local_logout():
    engine, session_factory = await _setup_local_auth_client()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        resp = await client.get("/auth/local/logout")

    assert resp.status_code == 307
    assert resp.headers["location"] == "/"

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_change_password_success():
    engine, session_factory = await _setup_local_auth_client()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    from main import get_current_user, require_editor, require_admin
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_editor, None)
    app.dependency_overrides.pop(require_admin, None)

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login first
        login_resp = await client.post(
            "/auth/local/login",
            json={"username": "testadmin", "password": "testpassword"},
        )
        token = login_resp.json()["access_token"]

        # Change password
        resp = await client.post(
            "/auth/local/change-password",
            json={
                "token": token,
                "current_password": "testpassword",
                "new_password": "newpassword123",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify new password works
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/auth/local/login",
            json={"username": "testadmin", "password": "newpassword123"},
        )
    assert resp.status_code == 200

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def test_change_password_wrong_current():
    engine, session_factory = await _setup_local_auth_client()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    from main import get_current_user, require_editor, require_admin
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_editor, None)
    app.dependency_overrides.pop(require_admin, None)

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login first
        login_resp = await client.post(
            "/auth/local/login",
            json={"username": "testadmin", "password": "testpassword"},
        )
        token = login_resp.json()["access_token"]

        # Try with wrong current password
        resp = await client.post(
            "/auth/local/change-password",
            json={
                "token": token,
                "current_password": "wrongpassword",
                "new_password": "newpassword123",
            },
        )

    assert resp.status_code == 401
    assert "incorrect" in resp.json()["detail"].lower()

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()
