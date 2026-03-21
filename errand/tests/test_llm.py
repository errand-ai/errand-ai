import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import llm as llm_module
import llm_providers as llm_providers_module
from llm import DEFAULT_LLM_TIMEOUT, _parse_llm_response, _strip_markdown_fences, generate_title
from models import Setting


async def create_task(client: AsyncClient, input_text: str = "Test task") -> dict:
    resp = await client.post("/api/tasks", json={"input": input_text})
    assert resp.status_code == 201
    return resp.json()


def _mock_llm_response(content: str) -> MagicMock:
    """Create a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    return response


def _mock_json_response(title: str, category: str = "immediate", execute_at=None, repeat_interval=None, repeat_until=None, description=None) -> MagicMock:
    """Create a mock response with JSON content."""
    data = {"title": title, "category": category, "execute_at": execute_at, "repeat_interval": repeat_interval, "repeat_until": repeat_until, "description": description}
    return _mock_llm_response(json.dumps(data))


# --- LLM JSON parsing unit tests ---


def test_parse_llm_response_valid_json():
    raw = json.dumps({"title": "Fix Auth Bug", "category": "immediate", "execute_at": None, "repeat_interval": None, "repeat_until": None})
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.title == "Fix Auth Bug"
    assert result.category == "immediate"
    assert result.success is True


def test_parse_llm_response_scheduled_with_timing():
    raw = json.dumps({"title": "Send Report", "category": "scheduled", "execute_at": "2026-02-10T17:00:00Z", "repeat_interval": None, "repeat_until": None})
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.category == "scheduled"
    assert result.execute_at == "2026-02-10T17:00:00Z"


def test_parse_llm_response_repeating_with_all_fields():
    raw = json.dumps({
        "title": "Daily Report",
        "category": "repeating",
        "execute_at": "2026-02-11T09:00:00Z",
        "repeat_interval": "1d",
        "repeat_until": "2026-03-31T00:00:00Z",
    })
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.category == "repeating"
    assert result.repeat_interval == "1d"
    assert result.repeat_until == "2026-03-31T00:00:00Z"


def test_parse_llm_response_invalid_json():
    result = _parse_llm_response("Just a plain title")
    assert result is None


def test_parse_llm_response_missing_title():
    raw = json.dumps({"category": "immediate"})
    result = _parse_llm_response(raw)
    assert result is None


def test_parse_llm_response_invalid_category_defaults_to_immediate():
    raw = json.dumps({"title": "Some Task", "category": "invalid"})
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.category == "immediate"


# --- Markdown fence stripping ---


def test_strip_markdown_fences_json_block():
    raw = '```json\n{"title": "Fix Bug", "category": "immediate"}\n```'
    assert _strip_markdown_fences(raw) == '{"title": "Fix Bug", "category": "immediate"}'


def test_strip_markdown_fences_plain_block():
    raw = '```\n{"title": "Fix Bug"}\n```'
    assert _strip_markdown_fences(raw) == '{"title": "Fix Bug"}'


def test_strip_markdown_fences_no_fences():
    raw = '{"title": "Fix Bug"}'
    assert _strip_markdown_fences(raw) == '{"title": "Fix Bug"}'


def test_parse_llm_response_with_markdown_fences():
    raw = '```json\n{"title": "Send Report", "category": "scheduled", "execute_at": "2026-02-10T17:00:00Z", "repeat_interval": null, "repeat_until": null}\n```'
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.title == "Send Report"
    assert result.category == "scheduled"
    assert result.execute_at == "2026-02-10T17:00:00Z"


# --- Description field parsing ---


def test_parse_llm_response_extracts_description():
    raw = json.dumps({"title": "Publish Tweet", "category": "scheduled", "execute_at": "2026-03-21T18:00:00Z", "repeat_interval": None, "repeat_until": None, "description": "Publish one of the approved tweets"})
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.description == "Publish one of the approved tweets"


def test_parse_llm_response_missing_description_returns_none():
    raw = json.dumps({"title": "Fix Bug", "category": "immediate", "execute_at": None, "repeat_interval": None, "repeat_until": None})
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.description is None


def test_parse_llm_response_non_string_description_returns_none():
    raw = json.dumps({"title": "Fix Bug", "category": "immediate", "execute_at": None, "repeat_interval": None, "repeat_until": None, "description": 123})
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.description is None


def test_parse_llm_response_empty_string_description_returns_none():
    raw = json.dumps({"title": "Reminder", "category": "scheduled", "execute_at": "2026-03-21T18:00:00Z", "repeat_interval": None, "repeat_until": None, "description": ""})
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.description is None


def test_parse_llm_response_whitespace_description_returns_none():
    raw = json.dumps({"title": "Reminder", "category": "scheduled", "execute_at": "2026-03-21T18:00:00Z", "repeat_interval": None, "repeat_until": None, "description": "   "})
    result = _parse_llm_response(raw)
    assert result is not None
    assert result.description is None


# --- Task creation with LLM JSON categorisation ---


async def test_create_task_long_input_calls_llm(client: AsyncClient):
    """Long input (>5 words) triggers LLM title + categorisation."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Fix Auth Bug", "immediate", description="Fix the authentication bug that prevents login on mobile devices")
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "We need to fix the authentication bug that prevents login on mobile devices"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Fix Auth Bug"
    assert data["description"] == "Fix the authentication bug that prevents login on mobile devices"
    assert data["category"] == "immediate"
    assert "Needs Info" not in data["tags"]
    mock_client.chat.completions.create.assert_called_once()


async def test_create_task_scheduled_categorisation(client: AsyncClient):
    """LLM categorises task as scheduled with execute_at."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Send Report", "scheduled", execute_at="2026-02-10T17:00:00Z", description="Send the quarterly financial report to the board")
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "Send the quarterly financial report to the board at 5pm today"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Send Report"
    assert data["category"] == "scheduled"
    assert data["execute_at"] is not None
    assert data["status"] == "scheduled"  # auto-routed


async def test_create_task_repeating_categorisation(client: AsyncClient):
    """LLM categorises task as repeating with interval and repeat_until."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response(
            "Daily Report", "repeating",
            execute_at="2026-02-11T09:00:00Z",
            repeat_interval="1d",
            repeat_until="2026-03-31T00:00:00Z",
            description="Run the daily sales report",
        )
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "Run the daily sales report every morning at 9am until the end of Q1 2026"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "repeating"
    assert data["repeat_interval"] == "1d"
    assert data["repeat_until"] is not None
    assert data["status"] == "scheduled"


async def test_create_task_short_input_no_llm(client: AsyncClient):
    """Short input (<=5 words) uses input as title directly, no LLM call."""
    mock_client = AsyncMock()

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post("/api/tasks", json={"input": "Fix login"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Fix login"
    assert data["description"] is None
    assert data["category"] == "immediate"
    assert "Needs Info" in data["tags"]
    assert data["status"] == "review"  # Needs Info routes to review
    mock_client.chat.completions.create.assert_not_called()


async def test_create_task_llm_returns_invalid_json(client: AsyncClient):
    """When LLM returns non-JSON, raw response becomes title, Needs Info applied."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_llm_response("Just a plain title response")
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "We need to fix the authentication bug that prevents login on mobile devices"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Just a plain title response"
    assert data["category"] == "immediate"
    assert "Needs Info" in data["tags"]
    assert data["status"] == "review"


async def test_create_task_llm_failure_uses_fallback(client: AsyncClient):
    """When LLM fails, a fallback title is generated and Needs Info tag is applied."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM timeout"))

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "We need to fix the authentication bug that prevents login on mobile devices"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "We need to fix the..."
    assert data["category"] == "immediate"
    assert "Needs Info" in data["tags"]


async def test_create_task_llm_not_configured_uses_fallback(client: AsyncClient):
    """When LLM client is None, fallback title is used."""
    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(None, None))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "This is a longer description that should trigger title generation"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "This is a longer description..."
    assert data["category"] == "immediate"
    assert "Needs Info" in data["tags"]


async def test_create_task_exactly_five_words_is_short(client: AsyncClient):
    """Exactly 5 words is treated as short input (title, no LLM)."""
    resp = await client.post("/api/tasks", json={"input": "one two three four five"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "one two three four five"
    assert data["description"] is None
    assert "Needs Info" in data["tags"]


async def test_create_task_six_words_triggers_llm(client: AsyncClient):
    """Six words triggers LLM title generation."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Generated Title", description="one two three four five six")
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks", json={"input": "one two three four five six"}
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Generated Title"
    mock_client.chat.completions.create.assert_called_once()


# --- Session fixture for direct generate_title tests ---

_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_SETTINGS_TABLE_SQL))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# --- 4.1 generate_title includes injected now datetime in system prompt ---


async def test_generate_title_includes_now_in_system_prompt(db_session: AsyncSession):
    """generate_title includes the injected now datetime in the system prompt."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Test Title")
    )
    test_now = datetime(2026, 2, 11, 14, 30, 0, tzinfo=timezone.utc)

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        await generate_title("some long enough description for the test", db_session, now=test_now)

    call_args = mock_client.chat.completions.create.call_args
    system_content = call_args.kwargs["messages"][0]["content"]
    assert "2026-02-11T14:30:00Z" in system_content


# --- 4.2 generate_title includes configured timezone in system prompt ---


async def test_generate_title_includes_timezone_in_system_prompt(db_session: AsyncSession):
    """generate_title includes the configured timezone in the system prompt."""
    # Set timezone in DB
    db_session.add(Setting(key="timezone", value="Europe/London"))
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Test Title")
    )
    test_now = datetime(2026, 2, 11, 14, 30, 0, tzinfo=timezone.utc)

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        await generate_title("some long enough description for the test", db_session, now=test_now)

    call_args = mock_client.chat.completions.create.call_args
    system_content = call_args.kwargs["messages"][0]["content"]
    assert "Europe/London" in system_content


# --- 4.3 generate_title defaults to UTC when no timezone setting exists ---


async def test_generate_title_defaults_to_utc_timezone(db_session: AsyncSession):
    """generate_title defaults to UTC when no timezone setting exists."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Test Title")
    )
    test_now = datetime(2026, 2, 11, 14, 30, 0, tzinfo=timezone.utc)

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        await generate_title("some long enough description for the test", db_session, now=test_now)

    call_args = mock_client.chat.completions.create.call_args
    system_content = call_args.kwargs["messages"][0]["content"]
    assert "timezone is: UTC" in system_content


# --- 4.4 task creation with immediate category sets execute_at to now ---


async def test_create_task_immediate_sets_execute_at(client: AsyncClient):
    """Task creation with category immediate sets execute_at to approximately now."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Fix Auth Bug", "immediate", description="Fix the authentication bug that prevents login on mobile devices")
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "We need to fix the authentication bug that prevents login on mobile devices"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["category"] == "immediate"
    assert data["execute_at"] is not None


# --- Configurable LLM timeout ---


async def test_generate_title_uses_custom_timeout(db_session: AsyncSession):
    """generate_title uses llm_timeout setting when it exists."""
    db_session.add(Setting(key="llm_timeout", value="60"))
    await db_session.commit()

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Test Title")
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        await generate_title("some long enough description for the test", db_session)

    call_args = mock_client.chat.completions.create.call_args
    assert call_args.kwargs["timeout"] == 60.0


async def test_generate_title_uses_default_timeout(db_session: AsyncSession):
    """generate_title uses default 30s timeout when no llm_timeout setting exists."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Test Title")
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        await generate_title("some long enough description for the test", db_session)

    call_args = mock_client.chat.completions.create.call_args
    assert call_args.kwargs["timeout"] == DEFAULT_LLM_TIMEOUT


# --- generate_title returns cleaned description ---


async def test_generate_title_returns_cleaned_description(db_session: AsyncSession):
    """generate_title returns the description field from the LLM response."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response("Publish Tweet", "scheduled", execute_at="2026-03-21T18:00:00Z", description="Publish one of the approved tweets")
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        result = await generate_title("In two hours, publish one of the approved tweets", db_session)

    assert result.success is True
    assert result.description == "Publish one of the approved tweets"
    assert result.category == "scheduled"


# --- Integration: task created with cleaned description ---


async def test_create_task_uses_cleaned_description(client: AsyncClient):
    """Task creation uses the LLM-cleaned description, not the raw input."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response(
            "Publish Tweet", "scheduled",
            execute_at="2026-03-21T18:00:00Z",
            description="Publish one of the approved tweets",
        )
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "In two hours, publish one of the approved tweets"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] == "Publish one of the approved tweets"
    assert data["category"] == "scheduled"
    assert data["status"] == "scheduled"
    assert "Needs Info" not in data["tags"]


async def test_create_task_empty_description_routes_to_review(client: AsyncClient):
    """When LLM returns null description, task gets Needs Info and routes to review."""
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_json_response(
            "Reminder", "scheduled",
            execute_at="2026-03-21T18:00:00Z",
            description=None,
        )
    )

    with patch.object(llm_providers_module, "resolve_model_setting", AsyncMock(return_value=(mock_client, "test-model"))):
        resp = await client.post(
            "/api/tasks",
            json={"input": "Remind me in two hours about the thing"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] is None
    assert data["category"] == "scheduled"
    assert data["execute_at"] is not None
    assert data["status"] == "review"
    assert "Needs Info" in data["tags"]
