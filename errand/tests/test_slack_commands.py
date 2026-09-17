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


_SLACK_MESSAGE_REFS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS slack_message_refs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    task_id VARCHAR(36) NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    message_ts TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


async def _create_tables(engine):
    from tests.conftest import _create_tables as _create_shared_tables

    await _create_shared_tables(engine)
    async with engine.begin() as conn:
        await conn.execute(text(_SLACK_MESSAGE_REFS_TABLE_SQL))


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

    # Every intake now goes through the classifier. By default it understands
    # the input exactly as written and has no questions, so the draft is ready
    # at once; a test that wants another answer sets `classifier.side_effect`.
    with patch("platforms.slack.routes.load_credentials", new_callable=AsyncMock) as mock_creds, \
         patch("platforms.slack.routes.resolve_slack_email", new_callable=AsyncMock) as mock_email, \
         patch("platforms.slack.intake.load_credentials", new=mock_creds), \
         patch("platforms.slack.intake.resolve_slack_email", new=mock_email), \
         patch("clarify.generate_title", new_callable=AsyncMock) as mock_classifier:
        mock_creds.return_value = {"bot_token": "xoxb-test", "signing_secret": "test_secret"}
        mock_email.return_value = "slack-user@example.com"
        mock_classifier.side_effect = lambda text, *a, **kw: _llm(title=text, description=text)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            ac.classifier = mock_classifier
            ac.session_factory = test_session
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


QUESTIONS = [
    {"id": "room", "text": "Which room?", "kind": "free_text"},
    {"id": "time", "text": "Morning or afternoon?", "kind": "choice", "choices": ["Morning", "Afternoon"]},
]


async def _post_command(client: AsyncClient, text: str = "", user_id: str = "U123", channel_id: str = ""):
    """Post a slash command to /slack/commands."""
    data = {"command": "/task", "text": text, "user_id": user_id}
    if channel_id:
        data["channel_id"] = channel_id
    return await client.post("/slack/commands", data=data)


def _button_value(blocks: list, action_id: str) -> str:
    for block in blocks:
        for element in block.get("elements", []) if block["type"] == "actions" else []:
            if element["action_id"] == action_id:
                return element["value"]
    raise AssertionError(f"no {action_id} button in {blocks}")


async def _act(client: AsyncClient, blocks: list, action_id: str, *, user_id="U123", channel_id="C1", values=None):
    """Click a draft button; returns (replies posted to response_url, channel posts)."""
    from platforms.slack import intake

    payload = {
        "type": "block_actions",
        "user": {"id": user_id},
        "channel": {"id": channel_id},
        "response_url": "https://hooks.slack.test/response",
        "state": {"values": values or {}},
    }
    action = {"action_id": action_id, "value": _button_value(blocks, action_id)}
    with patch.object(intake, "_slack_client") as mock_client:
        mock_client.post_response_url = AsyncMock()
        mock_client.post_message = AsyncMock(return_value={"ok": True, "channel": channel_id, "ts": "111.222"})
        await intake.handle_draft_action(payload, action, client.session_factory)
    replies = [(c.args[1], c.kwargs) for c in mock_client.post_response_url.call_args_list]
    return replies, mock_client.post_message.call_args_list


async def _create_task(client: AsyncClient, text: str, **kw) -> list:
    """`/task new` then Run; returns the task confirmation blocks."""
    draft = await _post_command(client, text=f"new {text}", **kw)
    replies, _ = await _act(client, draft.json()["blocks"], "task_spec_run")
    blocks, options = replies[-1]
    assert options["replace_original"] is True
    return blocks


def _extract_short_id(blocks: list) -> str:
    """Extract the short task ID from task confirmation blocks."""
    fields = blocks[1]["fields"]
    id_field = [f for f in fields if f["text"].startswith("*ID:*")][0]
    return id_field["text"].split("`")[1]


async def _task_row(client: AsyncClient, title_fragment: str):
    from sqlalchemy import select
    from models import Tag, task_tags

    async with client.session_factory() as session:
        task = (await session.execute(
            select(Task).where(Task.title.contains(title_fragment))
        )).scalars().first()
        if task is None:
            return None, []
        tags = (await session.execute(
            select(Tag.name).join(task_tags, task_tags.c.tag_id == Tag.id)
            .where(task_tags.c.task_id == task.id)
        )).scalars().all()
        return task, list(tags)


async def _count(client: AsyncClient, model) -> int:
    from sqlalchemy import func, select

    async with client.session_factory() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


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


# --- New command: a draft first, a task only on Run ---


class TestNewCommand:
    @pytest.mark.asyncio
    async def test_new_returns_a_draft_and_creates_no_task(self, slack_client):
        response = await _post_command(slack_client, text="new Buy groceries")
        assert response.status_code == 200
        data = response.json()
        assert data["response_type"] == "ephemeral"
        assert data["blocks"][0]["text"]["text"] == "I'll do this — run it?"
        fields_text = " ".join(f["text"] for f in data["blocks"][1]["fields"])
        assert "Buy groceries" in fields_text
        assert _button_value(data["blocks"], "task_spec_run")
        assert await _count(slack_client, Task) == 0

    @pytest.mark.asyncio
    async def test_run_creates_task(self, slack_client):
        blocks = await _create_task(slack_client, "Buy groceries")
        assert blocks[0]["text"]["text"] == "Task Created"
        fields_text = " ".join(f["text"] for f in blocks[1]["fields"])
        assert "Buy groceries" in fields_text
        assert await _count(slack_client, Task) == 1

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
        blocks = await _create_task(slack_client, "Test task")
        context = blocks[2]["elements"][0]["text"]
        assert "slack-user@example.com" in context
        task, _ = await _task_row(slack_client, "Test task")
        assert task.created_by == "slack-user@example.com"

    @pytest.mark.asyncio
    async def test_ambiguous_input_asks_with_input_blocks(self, slack_client):
        slack_client.classifier.side_effect = None
        slack_client.classifier.return_value = _llm(title="Book Room", questions=QUESTIONS)
        response = await _post_command(slack_client, text="new book the room")
        blocks = response.json()["blocks"]
        inputs = [b for b in blocks if b["type"] == "input"]
        assert [b["block_id"] for b in inputs] == ["task_spec_q:room", "task_spec_q:time"]
        assert inputs[0]["element"]["type"] == "plain_text_input"
        assert inputs[1]["element"]["type"] == "static_select"
        assert [o["value"] for o in inputs[1]["element"]["options"]] == ["Morning", "Afternoon"]
        for action_id in ("task_spec_submit", "task_spec_run", "task_spec_cancel"):
            assert _button_value(blocks, action_id)
        assert await _count(slack_client, Task) == 0


# --- Draft actions ---


class TestDraftActions:
    @pytest.mark.asyncio
    async def test_submit_folds_answers_then_run(self, slack_client):
        slack_client.classifier.side_effect = [
            _llm(title="Book Room", questions=QUESTIONS),
            _llm(title="Book Room", description="Book room 4 for the morning"),
        ]
        draft = (await _post_command(slack_client, text="new book the room")).json()["blocks"]

        values = {
            "task_spec_q:room": {"answer": {"type": "plain_text_input", "value": "Room 4"}},
            "task_spec_q:time": {"answer": {"type": "static_select", "selected_option": {"value": "Morning"}}},
        }
        replies, _ = await _act(slack_client, draft, "task_spec_submit", values=values)
        preview, options = replies[-1]
        assert options["replace_original"] is True
        assert preview[0]["text"]["text"] == "I'll do this — run it?"
        history = slack_client.classifier.call_args.kwargs["history"]
        assert history[-1]["content"] == "Which room? -> Room 4\nMorning or afternoon? -> Morning"

        replies, _ = await _act(slack_client, preview, "task_spec_run")
        assert replies[-1][0][0]["text"]["text"] == "Task Created"
        task, tags = await _task_row(slack_client, "Book Room")
        assert task.description == "Book room 4 for the morning"
        assert task.status == "pending"
        assert tags == ["slack"]

    @pytest.mark.asyncio
    async def test_other_user_cannot_advance(self, slack_client):
        slack_client.classifier.side_effect = None
        slack_client.classifier.return_value = _llm(title="Book Room", questions=QUESTIONS)
        draft = (await _post_command(slack_client, text="new book the room")).json()["blocks"]

        with patch("platforms.slack.intake.resolve_slack_email", AsyncMock(return_value="mallory@example.com")):
            for action_id in ("task_spec_submit", "task_spec_run", "task_spec_cancel"):
                replies, _ = await _act(slack_client, draft, action_id, user_id="U999")
                blocks, options = replies[-1]
                assert options["replace_original"] is False
                assert "Only the person who started this draft" in blocks[0]["text"]["text"]

        assert await _count(slack_client, Task) == 0
        assert slack_client.classifier.call_count == 1
        from models import TaskSpecDraft
        async with slack_client.session_factory() as session:
            from sqlalchemy import select
            stored = (await session.execute(select(TaskSpecDraft))).scalar_one()
        assert (stored.status, stored.round) == ("drafting", 0)

    @pytest.mark.asyncio
    async def test_cancel_then_run_is_inactive(self, slack_client):
        draft = (await _post_command(slack_client, text="new Buy groceries")).json()["blocks"]
        replies, _ = await _act(slack_client, draft, "task_spec_cancel")
        assert "cancelled" in replies[-1][0][0]["text"]["text"]
        replies, _ = await _act(slack_client, draft, "task_spec_run")
        assert "no longer active" in replies[-1][0][0]["text"]["text"]
        assert replies[-1][1]["replace_original"] is True
        assert await _count(slack_client, Task) == 0

    @pytest.mark.asyncio
    async def test_run_twice_creates_one_task(self, slack_client):
        draft = (await _post_command(slack_client, text="new Buy groceries")).json()["blocks"]
        await _act(slack_client, draft, "task_spec_run")
        replies, _ = await _act(slack_client, draft, "task_spec_run")
        assert "no longer active" in replies[-1][0][0]["text"]["text"]
        assert await _count(slack_client, Task) == 1

    @pytest.mark.asyncio
    async def test_interactions_endpoint_dispatches_in_background(self, slack_client):
        import json

        payload = {
            "type": "block_actions",
            "user": {"id": "U123"},
            "response_url": "https://hooks.slack.test/response",
            "actions": [{"action_id": "task_spec_run", "value": "abc"}],
        }
        with patch("platforms.slack.routes.intake.handle_draft_action", new_callable=AsyncMock) as handler:
            response = await slack_client.post("/slack/interactions", data={"payload": json.dumps(payload)})
            import asyncio
            await asyncio.sleep(0)
        assert response.status_code == 200
        handler.assert_awaited_once()
        assert handler.call_args.args[1]["action_id"] == "task_spec_run"


# --- Status command ---


class TestStatusCommand:
    @pytest.mark.asyncio
    async def test_status_by_prefix(self, slack_client):
        short_id = _extract_short_id(await _create_task(slack_client, "Status test"))

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
        await _create_task(slack_client, "Task A")
        await _create_task(slack_client, "Task B")

        response = await _post_command(slack_client, text="list")
        data = response.json()
        section_text = data["blocks"][1]["text"]["text"]
        assert "Task A" in section_text
        assert "Task B" in section_text

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, slack_client):
        await _create_task(slack_client, "Pending task")

        response = await _post_command(slack_client, text="list pending")
        data = response.json()
        assert data["blocks"][0]["text"]["text"] == "Tasks (pending)"
        assert "Pending task" in data["blocks"][1]["text"]["text"]

    @pytest.mark.asyncio
    async def test_list_excludes_deleted(self, slack_client):
        await _create_task(slack_client, "Some task")

        response = await _post_command(slack_client, text="list deleted")
        data = response.json()
        assert "No tasks found" in data["blocks"][1]["text"]["text"]


# --- Run command ---


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_run_already_pending(self, slack_client):
        short_id = _extract_short_id(await _create_task(slack_client, "Run test"))

        # A confirmed immediate task reaches pending, so run should say it is
        # already pending.
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
        short_id = _extract_short_id(await _create_task(slack_client, "Output test"))

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
        short_id = _extract_short_id(await _create_task(slack_client, "Prefix test"))

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
        await _create_task(slack_client, "UUID test")
        task, _ = await _task_row(slack_client, "UUID test")

        status_resp = await _post_command(slack_client, text=f"status {task.id}")
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
        await _create_task(slack_client, "Tagged task")
        _, tags = await _task_row(slack_client, "Tagged task")
        assert tags == ["slack"]

    @pytest.mark.asyncio
    async def test_new_command_creates_slack_tag_if_not_exists(self, slack_client):
        """First /task new should create the 'slack' tag, second should reuse it."""
        await _create_task(slack_client, "First task")
        blocks = await _create_task(slack_client, "Second task")
        assert blocks[0]["text"]["text"] == "Task Created"
        _, tags = await _task_row(slack_client, "Second task")
        assert tags == ["slack"]


# --- Channel message for live updates ---


class TestNewCommandChannelMessage:
    @pytest.mark.asyncio
    async def test_run_posts_channel_message_and_stores_ref(self, slack_client):
        """The slash-command draft is ephemeral and cannot be updated later, so
        Run posts a visible channel message and links it for status updates."""
        from models import SlackMessageRef

        draft = (await _post_command(slack_client, text="new Channel task", channel_id="C456")).json()
        _, posts = await _act(slack_client, draft["blocks"], "task_spec_run", channel_id="C456")

        assert len(posts) == 1
        assert posts[0].args[0] == "xoxb-test"
        assert posts[0].args[1] == "C456"
        assert isinstance(posts[0].args[2], list)
        async with slack_client.session_factory() as session:
            from sqlalchemy import select
            ref = (await session.execute(select(SlackMessageRef))).scalar_one()
        assert (ref.channel_id, ref.message_ts) == ("C456", "111.222")

    @pytest.mark.asyncio
    async def test_new_posts_nothing_to_the_channel(self, slack_client):
        """No task exists yet, so there is nothing to announce."""
        with patch("platforms.slack.routes._slack_client") as mock_client:
            mock_client.post_message = AsyncMock()
            response = await _post_command(slack_client, text="new No channel task", channel_id="C456")
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
        response = await _post_command(slack_client, text="new Metadata test", channel_id="C456")
        assert "_task_id" not in response.json()


# --- What the classifier's answer becomes on Slack ---
#
# A Slack task is only ever created from a draft the user has seen and run, so
# none of these park the task under "Needs Info": whatever the classifier said,
# the user chose to run what the preview showed.


LONG = "please book the meeting room for the quarterly planning session tomorrow"


class TestSlashCommandClassification:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("cause", ["no_model_configured", "request_failed", "unusable_response"])
    async def test_unusable_classifier_keeps_the_raw_input(self, slack_client, cause):
        slack_client.classifier.side_effect = None
        slack_client.classifier.return_value = _llm(title="x", success=False, description=None, cause=cause)
        await _create_task(slack_client, LONG)

        task, tags = await _task_row(slack_client, "please book the meeting room")
        assert task.title == "please book the meeting room..."
        assert "Needs Info" not in tags
        assert task.status == "pending"
        assert task.description == LONG

    @pytest.mark.asyncio
    async def test_short_input_is_classified_too(self, slack_client):
        await _create_task(slack_client, "fix it")
        assert slack_client.classifier.await_count == 1
        task, tags = await _task_row(slack_client, "fix it")
        assert "Needs Info" not in tags
        assert task.status == "pending"

    @pytest.mark.asyncio
    async def test_a_usable_answer_runs(self, slack_client):
        slack_client.classifier.side_effect = None
        slack_client.classifier.return_value = _llm(title="Good")
        await _create_task(slack_client, LONG)

        task, tags = await _task_row(slack_client, "Good")
        assert tags == ["slack"]
        assert task.status == "pending"
        assert task.description == "cleaned"

    @pytest.mark.asyncio
    async def test_a_scheduled_answer_is_scheduled(self, slack_client):
        slack_client.classifier.side_effect = None
        slack_client.classifier.return_value = _llm(
            title="Weekly Report", category="scheduled", execute_at="2026-03-01T09:00:00+00:00",
        )
        await _create_task(slack_client, LONG)
        task, _ = await _task_row(slack_client, "Weekly Report")
        assert task.status == "scheduled"
        assert task.category == "scheduled"


class TestMentionDraft:
    """`@errand <input>` — the draft is posted in the mention's thread."""

    @staticmethod
    async def _mention(slack_client, text_body: str, post_result=None):
        import platforms.slack.routes as routes
        from platforms.slack import intake

        with patch.object(routes, "async_session", slack_client.session_factory), \
             patch.object(intake, "_slack_client") as mock_client:
            mock_client.post_message = AsyncMock(
                return_value=post_result or {"ok": True, "channel": "C1", "ts": "555.666"}
            )
            await routes._handle_mention(
                {"text": f"<@BOT> {text_body}", "user": "U123", "channel": "C1", "ts": "444.333"}
            )
        return mock_client.post_message

    @pytest.mark.asyncio
    async def test_draft_posted_in_thread_and_recorded(self, slack_client):
        from models import TaskSpecDraft
        from sqlalchemy import select

        post = await self._mention(slack_client, LONG)
        post.assert_awaited_once()
        assert post.call_args.args[:2] == ("xoxb-test", "C1")
        assert post.call_args.kwargs["thread_ts"] == "444.333"
        assert await _count(slack_client, Task) == 0

        async with slack_client.session_factory() as session:
            draft = (await session.execute(select(TaskSpecDraft))).scalar_one()
        assert (draft.owner_id, draft.source) == ("slack-user@example.com", "slack")
        assert (draft.external_channel_id, draft.external_message_ts) == ("C1", "555.666")

    @pytest.mark.asyncio
    async def test_run_links_the_thread_message(self, slack_client):
        from models import SlackMessageRef
        from sqlalchemy import select

        post = await self._mention(slack_client, LONG)
        blocks = post.call_args.args[2]
        _, posts = await _act(slack_client, blocks, "task_spec_run")

        assert posts == [], "the thread message is replaced, not duplicated"
        async with slack_client.session_factory() as session:
            ref = (await session.execute(select(SlackMessageRef))).scalar_one()
        assert (ref.channel_id, ref.message_ts) == ("C1", "555.666")
        task, tags = await _task_row(slack_client, "please book")
        assert tags == ["slack"]
        assert task.created_by == "slack-user@example.com"

    @pytest.mark.asyncio
    async def test_empty_mention_starts_nothing(self, slack_client):
        from models import TaskSpecDraft

        post = await self._mention(slack_client, "")
        post.assert_not_called()
        assert await _count(slack_client, TaskSpecDraft) == 0
