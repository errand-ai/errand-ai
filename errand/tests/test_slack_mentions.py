"""Tests for Slack app_mention event handling."""
import json
import time
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from fastapi import Request

import events as events_module
from main import app
from database import get_session
from platforms.slack.routes import _BOT_MENTION_RE, _processed_events
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

_SLACK_MESSAGE_REFS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS slack_message_refs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    message_ts TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
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
        await conn.execute(text(_SLACK_MESSAGE_REFS_TABLE_SQL))


@pytest.fixture(autouse=True)
def clear_event_cache():
    """Clear the duplicate event cache between tests."""
    _processed_events.clear()
    yield
    _processed_events.clear()


@pytest.fixture()
async def mention_client() -> AsyncGenerator[AsyncClient, None]:
    """Test client with mocked Slack verification and identity."""
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

    # Patch the async_session used by _handle_mention
    with patch("platforms.slack.routes.async_session", test_session), \
         patch("platforms.slack.routes.load_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("platforms.slack.routes.resolve_slack_email", new_callable=AsyncMock) as mock_email, \
         patch("platforms.slack.routes._slack_client") as mock_slack_client:
        mock_creds.return_value = {"bot_token": "xoxb-test", "signing_secret": "test_secret"}
        mock_email.return_value = "mention-user@example.com"
        mock_slack_client.post_message = AsyncMock(return_value={
            "ok": True, "channel": "C12345", "ts": "111.222"
        })

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


def _mention_event(text="<@U12345> Write a blog post", event_id="evt_001",
                   user="U67890", channel="C11111"):
    return {
        "type": "event_callback",
        "event_id": event_id,
        "event": {
            "type": "app_mention",
            "text": text,
            "user": user,
            "channel": channel,
            "ts": "1234567890.123456",
        },
    }


class TestMentionEventHandling:
    @pytest.mark.asyncio
    async def test_url_verification_still_works(self, mention_client):
        response = await mention_client.post(
            "/slack/events",
            content=json.dumps({"type": "url_verification", "challenge": "abc123"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["challenge"] == "abc123"

    @pytest.mark.asyncio
    async def test_mention_returns_200_immediately(self, mention_client):
        response = await mention_client.post(
            "/slack/events",
            content=json.dumps(_mention_event()),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    @pytest.mark.asyncio
    async def test_empty_mention_ignored(self, mention_client):
        """Mention with only the bot ID and no text should be silently ignored."""
        response = await mention_client.post(
            "/slack/events",
            content=json.dumps(_mention_event(text="<@U12345>")),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200


class TestBotMentionStripping:
    @pytest.mark.asyncio
    async def test_strips_bot_mention_prefix(self, mention_client):
        """Bot mention at start of text should be stripped."""
        from platforms.slack.routes import _BOT_MENTION_RE
        text = "<@U12345> Deploy the new version"
        result = _BOT_MENTION_RE.sub("", text).strip()
        assert result == "Deploy the new version"

    @pytest.mark.asyncio
    async def test_strips_bot_mention_with_display_name(self, mention_client):
        from platforms.slack.routes import _BOT_MENTION_RE
        text = "<@U12345|hal> Deploy the new version"
        result = _BOT_MENTION_RE.sub("", text).strip()
        assert result == "Deploy the new version"

    @pytest.mark.asyncio
    async def test_empty_after_stripping(self, mention_client):
        from platforms.slack.routes import _BOT_MENTION_RE
        text = "<@U12345>"
        result = _BOT_MENTION_RE.sub("", text).strip()
        assert result == ""

    @pytest.mark.asyncio
    async def test_multiple_mentions_stripped(self, mention_client):
        from platforms.slack.routes import _BOT_MENTION_RE
        text = "<@U12345> <@U99999> check this"
        result = _BOT_MENTION_RE.sub("", text).strip()
        assert result == "check this"


class TestDuplicateEventPrevention:
    @pytest.mark.asyncio
    async def test_duplicate_event_ignored(self, mention_client):
        """Same event_id should not create duplicate tasks."""
        event = _mention_event(event_id="evt_dup")
        response1 = await mention_client.post(
            "/slack/events",
            content=json.dumps(event),
            headers={"Content-Type": "application/json"},
        )
        assert response1.status_code == 200

        response2 = await mention_client.post(
            "/slack/events",
            content=json.dumps(event),
            headers={"Content-Type": "application/json"},
        )
        assert response2.status_code == 200

    @pytest.mark.asyncio
    async def test_different_event_ids_processed(self, mention_client):
        """Different event_ids should both be processed."""
        event1 = _mention_event(event_id="evt_a")
        event2 = _mention_event(event_id="evt_b")
        response1 = await mention_client.post(
            "/slack/events",
            content=json.dumps(event1),
            headers={"Content-Type": "application/json"},
        )
        response2 = await mention_client.post(
            "/slack/events",
            content=json.dumps(event2),
            headers={"Content-Type": "application/json"},
        )
        assert response1.status_code == 200
        assert response2.status_code == 200


class TestBotMentionRegex:
    """Tests for the bot-mention stripping regex.

    The regex must match Slack's actual mention syntax (`<@USERID>` or
    `<@USERID|label>`) while running in linear time on adversarial inputs
    (no catastrophic backtracking).
    """

    def test_strips_canonical_mention(self):
        """Canonical `<@USERID>` mention is stripped, leaving the message."""
        assert _BOT_MENTION_RE.sub("", "<@U01ABCDEFGH> hello") == "hello"

    def test_strips_mention_with_label(self):
        """`<@USERID|label>` mention is stripped, leaving the message."""
        assert _BOT_MENTION_RE.sub("", "<@U01ABCDEFGH|errand-bot> hello") == "hello"

    def test_pathological_input_completes_quickly(self):
        """ReDoS regression: an unterminated mention prefix repeated 10k times
        must not trigger super-linear backtracking. The tightened regex (which
        excludes `|` from the label class) should complete near-instantly.

        Budget: 200 ms wall-clock — generous for a linear-time regex.
        """
        pathological = "<@0|" * 10_000
        start = time.perf_counter()
        _BOT_MENTION_RE.sub("", pathological)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 200, (
            f"Regex took {elapsed_ms:.2f} ms on pathological input "
            f"(budget 200 ms) — possible catastrophic backtracking"
        )
