from collections.abc import AsyncGenerator

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import events as events_module
from models import Base, Task
from main import app, get_current_user
from database import get_session

FAKE_USER_CLAIMS = {
    "sub": "test-user-id",
    "preferred_username": "testuser",
    "email": "test@example.com",
    "resource_access": {
        "content-manager": {
            "roles": ["user"],
        }
    },
}

# SQLite-compatible DDL for the tasks table (replaces now() with CURRENT_TIMESTAMP)
_TASKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT DEFAULT 'new' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_TASKS_TABLE_SQL))


@pytest.fixture()
async def fake_valkey() -> AsyncGenerator[FakeRedis, None]:
    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis
    yield redis
    events_module._valkey = None
    await redis.aclose()


@pytest.fixture()
async def client(fake_valkey) -> AsyncGenerator[AsyncClient, None]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_get_current_user():
        return FAKE_USER_CLAIMS

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture()
async def unauth_client(fake_valkey) -> AsyncGenerator[AsyncClient, None]:
    """Client without auth override — requests will be rejected."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()
