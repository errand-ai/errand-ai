"""Tests for Slack interactions endpoint (button clicks)."""
import json
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from fastapi import Request

import events as events_module
from main import app
from database import get_session
from models import Task
from platforms.slack.verification import verify_slack_request

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

_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tags (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
)
"""

_TASK_TAGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS task_tags (
    task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
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


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.execute(text(_TASK_PROFILES_TABLE_SQL))
        await conn.execute(text(_TASKS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))
        await conn.execute(text(_TAGS_TABLE_SQL))
        await conn.execute(text(_TASK_TAGS_TABLE_SQL))
        await conn.execute(text(_PLATFORM_CREDENTIALS_TABLE_SQL))


@pytest.fixture()
async def interactions_client() -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker], None]:
    """Test client for interactions endpoint. Returns (client, session_maker) tuple."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with test_session() as session:
            yield session

    async def override_verify(request: Request) -> bytes:
        return await request.body()

    redis = FakeRedis(decode_responses=True)
    events_module._valkey = redis

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[verify_slack_request] = override_verify

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, test_session

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def _create_test_task(session_maker, title="Test Task", status="pending") -> uuid.UUID:
    """Create a task directly in the DB for testing."""
    async with session_maker() as session:
        task = Task(
            title=title,
            status=status,
            position=1,
            created_by="test@example.com",
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task.id


def _interaction_payload(action_id: str, value: str, response_url: str = "https://hooks.slack.com/actions/T123/456/test") -> str:
    """Build a form-encoded interaction payload."""
    payload = json.dumps({
        "type": "block_actions",
        "actions": [{"action_id": action_id, "value": value}],
        "user": {"id": "U123"},
        "channel": {"id": "C123"},
        "response_url": response_url,
    })
    return urlencode({"payload": payload})


class TestInteractionsEndpoint:
    @pytest.mark.asyncio
    async def test_task_status_button(self, interactions_client):
        client, session_maker = interactions_client
        task_id = await _create_test_task(session_maker, title="Status Test")

        with patch("platforms.slack.routes._slack_client") as mock_client:
            mock_client.post_response_url = AsyncMock()
            response = await client.post(
                "/slack/interactions",
                content=_interaction_payload("task_status", str(task_id)),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status_code == 200
            assert response.json() == {"ok": True}

            # Background task posts ephemeral response via response_url
            mock_client.post_response_url.assert_called_once()
            call_args = mock_client.post_response_url.call_args
            assert call_args[0][0] == "https://hooks.slack.com/actions/T123/456/test"
            blocks = call_args[0][1]
            assert blocks[0]["type"] == "header"
            assert blocks[0]["text"]["text"] == "Status Test"

    @pytest.mark.asyncio
    async def test_task_output_button(self, interactions_client):
        client, session_maker = interactions_client
        task_id = await _create_test_task(session_maker, title="Output Test")

        with patch("platforms.slack.routes._slack_client") as mock_client:
            mock_client.post_response_url = AsyncMock()
            response = await client.post(
                "/slack/interactions",
                content=_interaction_payload("task_output", str(task_id)),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert response.status_code == 200
            assert response.json() == {"ok": True}

            mock_client.post_response_url.assert_called_once()
            blocks = mock_client.post_response_url.call_args[0][1]
            assert blocks[0]["type"] == "header"
            assert "Output: Output Test" in blocks[0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_unknown_action_returns_200(self, interactions_client):
        client, _ = interactions_client
        response = await client.post(
            "/slack/interactions",
            content=_interaction_payload("unknown_action", "some_value"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_empty_payload_returns_200(self, interactions_client):
        client, _ = interactions_client
        response = await client.post(
            "/slack/interactions",
            content="",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_non_block_actions_type_returns_200(self, interactions_client):
        client, _ = interactions_client
        payload = json.dumps({"type": "view_submission", "view": {}})
        response = await client.post(
            "/slack/interactions",
            content=urlencode({"payload": payload}),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}
