import json

import pytest
from starlette.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import auth as auth_module
import events as events_module
from fakeredis.aioredis import FakeRedis
from main import app, get_current_user
from database import get_session


# SQLite-compatible DDL
_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'new' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


class FakeOIDC:
    """Minimal OIDC stub for WebSocket auth tests."""

    def decode_token(self, token: str) -> dict:
        if token == "valid-token":
            return {
                "sub": "test-user",
                "resource_access": {"content-manager": {"roles": ["user"]}},
            }
        if token == "expired-token":
            import jwt
            raise jwt.ExpiredSignatureError("Token expired")
        raise __import__("jwt").InvalidTokenError("Bad token")

    def extract_roles(self, claims: dict) -> list:
        return claims.get("resource_access", {}).get("content-manager", {}).get("roles", [])


@pytest.fixture()
def ws_app():
    """Set up the app with fake OIDC and fake Valkey for WebSocket tests."""
    fake_redis = FakeRedis(decode_responses=True)
    events_module._valkey = fake_redis
    original_oidc = getattr(auth_module, "oidc", None)
    auth_module.oidc = FakeOIDC()

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    import asyncio
    asyncio.get_event_loop().run_until_complete(_create_tables(engine))

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return {"sub": "test-user", "resource_access": {"content-manager": {"roles": ["user"]}}}

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    yield app, fake_redis

    app.dependency_overrides.clear()
    auth_module.oidc = original_oidc
    events_module._valkey = None
    asyncio.get_event_loop().run_until_complete(fake_redis.aclose())
    asyncio.get_event_loop().run_until_complete(engine.dispose())


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_TASKS_TABLE_SQL))


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
    with pytest.raises(Exception):
        with client.websocket_connect("/api/ws/tasks?token=expired-token"):
            pass


def test_ws_valid_token_connects(ws_app):
    test_app, fake_redis = ws_app
    client = TestClient(test_app)
    with client.websocket_connect("/api/ws/tasks?token=valid-token") as ws:
        # Connection succeeded — send a dummy message to verify the connection is live
        # The server loop reads messages, so we can close cleanly
        pass
