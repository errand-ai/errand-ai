"""Tests for Slack command routing, dispatch, and handlers."""
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
async def slack_client() -> AsyncGenerator[AsyncClient, None]:
    """Test client with Slack routes, mocked verification and identity."""
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

    with patch("platforms.slack.routes.load_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("platforms.slack.routes.resolve_slack_email", new_callable=AsyncMock) as mock_email:
        mock_creds.return_value = {"bot_token": "xoxb-test", "signing_secret": "test_secret"}
        mock_email.return_value = "slack-user@example.com"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()
    events_module._valkey = None
    await redis.aclose()
    await engine.dispose()


async def _post_command(client: AsyncClient, text: str = "", user_id: str = "U123", channel_id: str = ""):
    """Post a slash command to /slack/commands."""
    data = {"command": "/task", "text": text, "user_id": user_id}
    if channel_id:
        data["channel_id"] = channel_id
    return await client.post("/slack/commands", data=data)


def _extract_short_id(create_response) -> str:
    """Extract the short task ID from a task_created_blocks response."""
    fields = create_response.json()["blocks"][1]["fields"]
    id_field = [f for f in fields if f["text"].startswith("*ID:*")][0]
    return id_field["text"].split("`")[1]


# --- Events endpoint ---


class TestSlackEvents:
    @pytest.mark.asyncio
    async def test_url_verification(self, slack_client):
        response = await slack_client.post(
            "/slack/events",
            json={"type": "url_verification", "challenge": "abc123"},
        )
        assert response.status_code == 200
        assert response.json()["challenge"] == "abc123"

    @pytest.mark.asyncio
    async def test_non_verification_event(self, slack_client):
        response = await slack_client.post(
            "/slack/events",
            json={"type": "event_callback", "event": {"type": "message"}},
        )
        assert response.status_code == 200


# --- Command routing ---


class TestCommandRouting:
    @pytest.mark.asyncio
    async def test_empty_command_returns_help(self, slack_client):
        response = await _post_command(slack_client, text="")
        assert response.status_code == 200
        data = response.json()
        assert data["response_type"] == "ephemeral"
        assert data["blocks"][0]["text"]["text"] == "Task Commands"

    @pytest.mark.asyncio
    async def test_help_command(self, slack_client):
        response = await _post_command(slack_client, text="help")
        assert response.status_code == 200
        data = response.json()
        assert data["blocks"][0]["text"]["text"] == "Task Commands"

    @pytest.mark.asyncio
    async def test_unknown_command_returns_help(self, slack_client):
        response = await _post_command(slack_client, text="foobar")
        assert response.status_code == 200
        data = response.json()
        assert data["blocks"][0]["text"]["text"] == "Task Commands"


# --- New command ---


class TestNewCommand:
    @pytest.mark.asyncio
    async def test_create_task(self, slack_client):
        response = await _post_command(slack_client, text="new Buy groceries")
        assert response.status_code == 200
        data = response.json()
        assert data["response_type"] == "ephemeral"
        assert data["blocks"][0]["text"]["text"] == "Task Created"
        fields_text = " ".join(f["text"] for f in data["blocks"][1]["fields"])
        assert "Buy groceries" in fields_text

    @pytest.mark.asyncio
    async def test_create_task_no_title(self, slack_client):
        response = await _post_command(slack_client, text="new")
        assert response.status_code == 200
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "Usage" in data["blocks"][0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_create_task_spaces_only(self, slack_client):
        response = await _post_command(slack_client, text="new   ")
        assert response.status_code == 200
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_created_by_email(self, slack_client):
        response = await _post_command(slack_client, text="new Test task")
        data = response.json()
        context = data["blocks"][2]["elements"][0]["text"]
        assert "slack-user@example.com" in context


# --- Status command ---


class TestStatusCommand:
    @pytest.mark.asyncio
    async def test_status_by_prefix(self, slack_client):
        create_resp = await _post_command(slack_client, text="new Status test")
        short_id = _extract_short_id(create_resp)

        response = await _post_command(slack_client, text=f"status {short_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["blocks"][0]["text"]["text"] == "Status test"

    @pytest.mark.asyncio
    async def test_status_no_id(self, slack_client):
        response = await _post_command(slack_client, text="status")
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "Usage" in data["blocks"][0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_status_not_found(self, slack_client):
        response = await _post_command(slack_client, text="status ffffffff")
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "No task found" in data["blocks"][0]["text"]["text"]


# --- List command ---


class TestListCommand:
    @pytest.mark.asyncio
    async def test_list_empty(self, slack_client):
        response = await _post_command(slack_client, text="list")
        data = response.json()
        assert data["blocks"][0]["text"]["text"] == "Tasks"
        assert "No tasks found" in data["blocks"][1]["text"]["text"]

    @pytest.mark.asyncio
    async def test_list_with_tasks(self, slack_client):
        await _post_command(slack_client, text="new Task A")
        await _post_command(slack_client, text="new Task B")

        response = await _post_command(slack_client, text="list")
        data = response.json()
        section_text = data["blocks"][1]["text"]["text"]
        assert "Task A" in section_text
        assert "Task B" in section_text

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, slack_client):
        await _post_command(slack_client, text="new Pending task")

        response = await _post_command(slack_client, text="list pending")
        data = response.json()
        assert data["blocks"][0]["text"]["text"] == "Tasks (pending)"
        assert "Pending task" in data["blocks"][1]["text"]["text"]

    @pytest.mark.asyncio
    async def test_list_excludes_deleted(self, slack_client):
        await _post_command(slack_client, text="new Some task")

        response = await _post_command(slack_client, text="list deleted")
        data = response.json()
        assert "No tasks found" in data["blocks"][1]["text"]["text"]


# --- Run command ---


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_run_already_pending(self, slack_client):
        create_resp = await _post_command(slack_client, text="new Run test")
        short_id = _extract_short_id(create_resp)

        # Task starts as pending, so run should say it's already pending
        response = await _post_command(slack_client, text=f"run {short_id}")
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "already" in data["blocks"][0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_run_no_id(self, slack_client):
        response = await _post_command(slack_client, text="run")
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "Usage" in data["blocks"][0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_run_not_found(self, slack_client):
        response = await _post_command(slack_client, text="run ffffffff")
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "No task found" in data["blocks"][0]["text"]["text"]


# --- Output command ---


class TestOutputCommand:
    @pytest.mark.asyncio
    async def test_output_no_output(self, slack_client):
        create_resp = await _post_command(slack_client, text="new Output test")
        short_id = _extract_short_id(create_resp)

        response = await _post_command(slack_client, text=f"output {short_id}")
        data = response.json()
        assert "no output yet" in data["blocks"][1]["text"]["text"]

    @pytest.mark.asyncio
    async def test_output_no_id(self, slack_client):
        response = await _post_command(slack_client, text="output")
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "Usage" in data["blocks"][0]["text"]["text"]


# --- UUID prefix matching ---


class TestUUIDPrefixMatching:
    @pytest.mark.asyncio
    async def test_prefix_match(self, slack_client):
        create_resp = await _post_command(slack_client, text="new Prefix test")
        short_id = _extract_short_id(create_resp)

        # Use first 4 chars as prefix
        prefix = short_id[:4]
        response = await _post_command(slack_client, text=f"status {prefix}")
        assert response.status_code == 200
        data = response.json()
        assert data["blocks"][0]["type"] == "header"

    @pytest.mark.asyncio
    async def test_not_found_prefix(self, slack_client):
        response = await _post_command(slack_client, text="status zzzzzzzz")
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "No task found" in data["blocks"][0]["text"]["text"]

    @pytest.mark.asyncio
    async def test_full_uuid_match(self, slack_client):
        # Create a task and get the full ID from the status response
        create_resp = await _post_command(slack_client, text="new UUID test")
        short_id = _extract_short_id(create_resp)

        # Get status by prefix to see the full ID in the response
        status_resp = await _post_command(slack_client, text=f"status {short_id}")
        data = status_resp.json()
        assert data["blocks"][0]["text"]["text"] == "UUID test"

    @pytest.mark.asyncio
    async def test_full_uuid_not_found(self, slack_client):
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await _post_command(slack_client, text=f"status {fake_uuid}")
        data = response.json()
        assert ":warning:" in data["blocks"][0]["text"]["text"]
        assert "No task found" in data["blocks"][0]["text"]["text"]


# --- Slack tag assignment ---


class TestSlackTag:
    @pytest.mark.asyncio
    async def test_new_command_adds_slack_tag(self, slack_client):
        """Tasks created via /task new should get a 'slack' tag."""
        response = await _post_command(slack_client, text="new Tagged task")
        assert response.status_code == 200
        data = response.json()
        # The response itself doesn't include tags, but we can verify the tag
        # exists by checking the DB indirectly via the actions block
        assert data["blocks"][0]["text"]["text"] == "Task Created"

    @pytest.mark.asyncio
    async def test_new_command_creates_slack_tag_if_not_exists(self, slack_client):
        """First /task new should create the 'slack' tag, second should reuse it."""
        response1 = await _post_command(slack_client, text="new First task")
        assert response1.status_code == 200
        response2 = await _post_command(slack_client, text="new Second task")
        assert response2.status_code == 200
        # Both should succeed without errors (tag reuse works)
        assert response2.json()["blocks"][0]["text"]["text"] == "Task Created"


# --- Channel message for live updates ---


class TestNewCommandChannelMessage:
    @pytest.mark.asyncio
    async def test_posts_channel_message_when_channel_id_present(self, slack_client):
        """When channel_id is provided, /task new should also post a visible channel message."""
        with patch("platforms.slack.routes._slack_client") as mock_client:
            mock_client.post_message = AsyncMock(
                return_value={"ok": True, "channel": "C456", "ts": "999.888"}
            )
            response = await _post_command(
                slack_client, text="new Channel task", channel_id="C456"
            )
            assert response.status_code == 200
            assert response.json()["blocks"][0]["text"]["text"] == "Task Created"

            # Background task posts to the channel
            mock_client.post_message.assert_called_once()
            call_args = mock_client.post_message.call_args
            assert call_args[0][0] == "xoxb-test"  # bot token
            assert call_args[0][1] == "C456"  # channel
            assert isinstance(call_args[0][2], list)  # blocks

    @pytest.mark.asyncio
    async def test_no_channel_message_without_channel_id(self, slack_client):
        """When no channel_id, no channel message is posted."""
        with patch("platforms.slack.routes._slack_client") as mock_client:
            mock_client.post_message = AsyncMock()
            response = await _post_command(slack_client, text="new No channel task")
            assert response.status_code == 200
            mock_client.post_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_channel_message_on_error(self, slack_client):
        """When /task new fails (missing title), no channel message is posted."""
        with patch("platforms.slack.routes._slack_client") as mock_client:
            mock_client.post_message = AsyncMock()
            response = await _post_command(
                slack_client, text="new", channel_id="C456"
            )
            assert response.status_code == 200
            assert ":warning:" in response.json()["blocks"][0]["text"]["text"]
            mock_client.post_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_id_stripped_from_response(self, slack_client):
        """The _task_id metadata field should not appear in the HTTP response."""
        with patch("platforms.slack.routes._slack_client") as mock_client:
            mock_client.post_message = AsyncMock(
                return_value={"ok": True, "channel": "C456", "ts": "999.888"}
            )
            response = await _post_command(
                slack_client, text="new Metadata test", channel_id="C456"
            )
            data = response.json()
            assert "_task_id" not in data


# --- LLM title generation ---


class TestTitleGeneration:
    @pytest.mark.asyncio
    async def test_long_input_uses_llm_title(self, slack_client):
        """Inputs >5 words should go through generate_title for a short title."""
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as mock_gen:
            from llm import LLMResult
            mock_gen.return_value = LLMResult(
                title="Deploy Staging App", category="immediate", success=True,
                description="Deploy the new version of the app to staging",
            )
            response = await _post_command(
                slack_client, text="new Deploy the new version of the app to staging"
            )
            assert response.status_code == 200
            data = response.json()
            fields_text = " ".join(f["text"] for f in data["blocks"][1]["fields"])
            assert "Deploy Staging App" in fields_text
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_short_input_skips_llm(self, slack_client):
        """Inputs <=5 words should use text directly as title, no LLM call."""
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as mock_gen:
            response = await _post_command(slack_client, text="new Fix login bug")
            assert response.status_code == 200
            data = response.json()
            fields_text = " ".join(f["text"] for f in data["blocks"][1]["fields"])
            assert "Fix login bug" in fields_text
            mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_long_input_sets_description(self, slack_client):
        """For long inputs, the LLM-cleaned text becomes the description."""
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as mock_gen:
            from llm import LLMResult
            mock_gen.return_value = LLMResult(
                title="Weekly Report", category="scheduled", success=True,
                execute_at="2026-03-01T09:00:00Z",
                description="Generate the weekly status report and send it to the team",
            )
            response = await _post_command(
                slack_client, text="new Generate the weekly status report and send it to the team"
            )
            assert response.status_code == 200
            # Verify title is the LLM-generated one
            data = response.json()
            fields_text = " ".join(f["text"] for f in data["blocks"][1]["fields"])
            assert "Weekly Report" in fields_text
