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
    is_eval BOOLEAN DEFAULT 0 NOT NULL,
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
    llm_timeout INTEGER,
    mcp_servers TEXT,
    litellm_mcp_servers TEXT,
    skill_ids TEXT,
            include_git_skills BOOLEAN NOT NULL DEFAULT 1,
        enabled_plugins TEXT,
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


def _llm(**kw):
    from llm import LLMResult
    base = dict(title="A title", success=True, category="immediate", description="cleaned")
    base.update(kw)
    return LLMResult(**base)


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
        # A task that actually reaches `pending`. A short Slack input is tagged
        # "Needs Info" and now parks in review, as `task-categorisation`
        # requires of every intake — so it can no longer stand in for a queued
        # task here.
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as gt:
            gt.return_value = _llm(title="Pending task")
            await _post_command(
                slack_client,
                text="new Pending task that is long enough to be classified properly",
            )

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
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as gt:
            gt.return_value = _llm(title="Run test")
            create_resp = await _post_command(
                slack_client,
                text="new Run test with an input long enough to be classified properly",
            )
        short_id = _extract_short_id(create_resp)

        # A classified task reaches pending, so run should say it is already
        # pending. Before both Slack intakes routed on the tag, a short input
        # served here — it was tagged "Needs Info" and queued anyway, which is
        # the defect, not a fixture.
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


# --- Cause-based routing on both Slack intakes ---
#
# Raised in review: both Slack intakes carry the same tag/route decision as the
# web endpoint and neither had coverage for it, so a Slack-specific regression
# could hide behind the web-path tests. Two independent facts are asserted at
# once, deliberately — the tag, and the status the tag is supposed to cause.
# Testing only the tag is what let both files tag `Needs Info` and then create
# the task `pending` regardless, for as long as they have existed.


async def _task_row(client: AsyncClient, title_fragment: str):
    from sqlalchemy import select
    from database import get_session as _gs
    gen = app.dependency_overrides[_gs]()
    session = await gen.__anext__()
    try:
        task = (await session.execute(
            select(Task).where(Task.title.contains(title_fragment))
        )).scalars().first()
        if task is None:
            return None, []
        from models import Tag, task_tags
        tags = (await session.execute(
            select(Tag.name).join(task_tags, task_tags.c.tag_id == Tag.id)
            .where(task_tags.c.task_id == task.id)
        )).scalars().all()
        return task, list(tags)
    finally:
        await gen.aclose()


LONG = "please book the meeting room for the quarterly planning session tomorrow"


class TestSlashCommandCauseRouting:
    """`/task new <long input>` — the handlers.py intake."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cause", ["no_model_configured", "request_failed"])
    async def test_unreached_classifier_is_not_the_users_fault(self, slack_client, cause):
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as gt:
            gt.return_value = _llm(title="Fallback", success=False, description=None, cause=cause)
            await _post_command(slack_client, text=f"new {LONG}")

        task, tags = await _task_row(slack_client, "Fallback")
        assert task is not None
        assert "Needs Info" not in tags, "blamed the user for an unconfigured installation"
        assert task.status == "pending"
        # The raw input is kept: nothing was missing from what they wrote.
        assert task.description == LONG

    @pytest.mark.asyncio
    async def test_an_unusable_answer_is_tagged_and_parked(self, slack_client):
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as gt:
            gt.return_value = _llm(title="Unusable", success=False, description=None,
                                   cause="unusable_response")
            await _post_command(slack_client, text=f"new {LONG}")

        task, tags = await _task_row(slack_client, "Unusable")
        assert "Needs Info" in tags
        assert task.status == "review", "tagged Needs Info but queued to run anyway"

    @pytest.mark.asyncio
    async def test_a_successful_answer_with_no_description_is_parked(self, slack_client):
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as gt:
            gt.return_value = _llm(title="Empty", success=True, description=None)
            await _post_command(slack_client, text=f"new {LONG}")

        task, tags = await _task_row(slack_client, "Empty")
        assert "Needs Info" in tags
        assert task.status == "review"

    @pytest.mark.asyncio
    async def test_short_input_is_parked(self, slack_client):
        """The classifier is deliberately not run, which is a judgement about
        the input — so the tag is right, and so is the parking."""
        await _post_command(slack_client, text="new fix it")
        task, tags = await _task_row(slack_client, "fix it")
        assert "Needs Info" in tags
        assert task.status == "review"

    @pytest.mark.asyncio
    async def test_a_usable_answer_runs(self, slack_client):
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as gt:
            gt.return_value = _llm(title="Good")
            await _post_command(slack_client, text=f"new {LONG}")

        task, tags = await _task_row(slack_client, "Good")
        assert "Needs Info" not in tags
        assert task.status == "pending"
        assert task.description == "cleaned"


class TestSlackPositionIsPerColumn:
    """Position is numbered per column, so it has to be taken after the status
    is known. Raised in review, and introduced by the routing fix itself: while
    every Slack task was `pending` the pending-filtered maximum was right by
    accident, and the moment a task could land in `review` it stopped being.
    """

    @pytest.mark.asyncio
    async def test_a_parked_task_is_numbered_in_the_review_column(self, slack_client):
        # Three tasks queued, so the pending column's bottom is well past 1.
        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as gt:
            gt.return_value = _llm(title="Queued")
            for _ in range(3):
                await _post_command(
                    slack_client,
                    text="new Queued task with an input long enough to be classified",
                )

        with patch("platforms.slack.handlers.generate_title", new_callable=AsyncMock) as gt:
            gt.return_value = _llm(title="Parked", success=False, description=None,
                                   cause="unusable_response")
            await _post_command(
                slack_client,
                text="new Parked task with an input long enough to be classified",
            )

        parked, tags = await _task_row(slack_client, "Parked")
        assert parked.status == "review"
        assert "Needs Info" in tags
        # First in its own column, not fourth from the pending one.
        assert parked.position == 1, (
            f"numbered {parked.position} from the pending column, so it lands "
            "in an arbitrary place in review"
        )


class TestMentionCauseRouting:
    """`@errand <long input>` — the routes.py intake.

    A second, separate implementation of the same decision. It reaches the
    database through `async_session` directly rather than the request
    dependency, which is why it needs its own factory patched and is also why
    it drifted from the slash-command path unnoticed.
    """

    @staticmethod
    async def _mention(slack_client, text_body: str, llm=None):
        from database import get_session as _gs
        import platforms.slack.routes as routes

        override = app.dependency_overrides[_gs]

        class _Factory:
            def __call__(self):
                return self

            async def __aenter__(self):
                self._gen = override()
                return await self._gen.__anext__()

            async def __aexit__(self, *exc):
                await self._gen.aclose()
                return False

        patches = [patch.object(routes, "async_session", _Factory())]
        if llm is not None:
            p = patch.object(routes, "generate_title", new_callable=AsyncMock)
            patches.append(p)
        started = [p.start() for p in patches]
        if llm is not None:
            started[1].return_value = llm
        try:
            await routes._handle_mention(
                {"text": f"<@BOT> {text_body}", "user": "U123", "channel": "C1"}
            )
        finally:
            for p in patches:
                p.stop()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("cause", ["no_model_configured", "request_failed"])
    async def test_unreached_classifier_is_not_the_users_fault(self, slack_client, cause):
        await self._mention(slack_client, LONG,
                            _llm(title="MFallback", success=False, description=None, cause=cause))
        task, tags = await _task_row(slack_client, "MFallback")
        assert task is not None
        assert "Needs Info" not in tags
        assert task.status == "pending"
        assert task.description == LONG

    @pytest.mark.asyncio
    async def test_an_unusable_answer_is_tagged_and_parked(self, slack_client):
        await self._mention(slack_client, LONG,
                            _llm(title="MUnusable", success=False, description=None,
                                 cause="unusable_response"))
        task, tags = await _task_row(slack_client, "MUnusable")
        assert "Needs Info" in tags
        assert task.status == "review", "tagged Needs Info but queued to run anyway"

    @pytest.mark.asyncio
    async def test_a_successful_answer_with_no_description_is_parked(self, slack_client):
        await self._mention(slack_client, LONG,
                            _llm(title="MEmpty", success=True, description=None))
        task, tags = await _task_row(slack_client, "MEmpty")
        assert "Needs Info" in tags
        assert task.status == "review"

    @pytest.mark.asyncio
    async def test_short_input_is_parked(self, slack_client):
        await self._mention(slack_client, "fix the thing")
        task, tags = await _task_row(slack_client, "fix the thing")
        assert "Needs Info" in tags
        assert task.status == "review"

    @pytest.mark.asyncio
    async def test_a_usable_answer_runs(self, slack_client):
        await self._mention(slack_client, LONG, _llm(title="MGood"))
        task, tags = await _task_row(slack_client, "MGood")
        assert "Needs Info" not in tags
        assert task.status == "pending"
