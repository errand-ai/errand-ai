"""Worker unit tests: settings reader, output truncation, task_to_dict, retry scheduling."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import Setting, Task

# Import worker functions under test
from worker import (
    read_settings, truncate_output, _task_to_dict, put_archive,
    _schedule_retry, process_task_in_container, DEFAULT_TASK_PROCESSING_MODEL,
    TaskRunnerOutput,
)


# --- Output truncation ---


def test_truncate_output_short():
    """Output within limit is returned unchanged."""
    result = truncate_output("short output", max_bytes=1024)
    assert result == "short output"


def test_truncate_output_exact_limit():
    """Output exactly at limit is returned unchanged."""
    text = "a" * 100
    result = truncate_output(text, max_bytes=100)
    assert result == text


def test_truncate_output_exceeds_limit():
    """Output exceeding limit is truncated with marker."""
    text = "a" * 200
    result = truncate_output(text, max_bytes=100)
    assert len(result.encode("utf-8")) < 200 + 100  # truncated + marker
    assert "--- OUTPUT TRUNCATED" in result
    assert "100 bytes" in result


def test_truncate_output_unicode():
    """Multi-byte characters are handled without crashing."""
    text = "\U0001f600" * 100  # emoji, 4 bytes each
    result = truncate_output(text, max_bytes=50)
    assert "--- OUTPUT TRUNCATED" in result


# --- _task_to_dict ---


def _make_mock_task(**overrides):
    """Create a mock Task with all fields populated for _task_to_dict tests."""
    task = MagicMock(spec=Task)
    task.id = overrides.get("id", "abc-123")
    task.title = overrides.get("title", "Test task")
    task.description = overrides.get("description", "Task description text")
    task.status = overrides.get("status", "pending")
    task.position = overrides.get("position", 3)
    task.category = overrides.get("category", "immediate")
    task.execute_at = overrides.get("execute_at", None)
    task.repeat_interval = overrides.get("repeat_interval", None)
    task.repeat_until = overrides.get("repeat_until", None)
    task.output = overrides.get("output", None)
    task.retry_count = overrides.get("retry_count", 0)
    # Tags: list of mock Tag objects with .name attribute
    tags = overrides.get("tags", [])
    mock_tags = []
    for t in tags:
        tag = MagicMock()
        tag.name = t
        mock_tags.append(tag)
    task.tags = mock_tags
    task.created_at = MagicMock()
    task.created_at.isoformat.return_value = overrides.get("created_at_iso", "2026-01-01T00:00:00")
    task.updated_at = MagicMock()
    task.updated_at.isoformat.return_value = overrides.get("updated_at_iso", "2026-01-01T00:01:00")
    return task


def test_task_to_dict_includes_output():
    """_task_to_dict includes the output field."""
    task = _make_mock_task(status="review", output="Container output here")
    result = _task_to_dict(task)
    assert result["output"] == "Container output here"
    assert result["status"] == "review"
    assert result["retry_count"] == 0


def test_task_to_dict_null_output():
    """_task_to_dict handles None output."""
    task = _make_mock_task(status="pending", output=None, retry_count=2)
    result = _task_to_dict(task)
    assert result["output"] is None
    assert result["retry_count"] == 2


def test_task_to_dict_includes_description_and_tags():
    """_task_to_dict includes description, position, category, and tags."""
    task = _make_mock_task(
        description="Fix the login bug",
        position=5,
        category="scheduled",
        tags=["urgent", "backend"],
    )
    result = _task_to_dict(task)
    assert result["description"] == "Fix the login bug"
    assert result["position"] == 5
    assert result["category"] == "scheduled"
    assert result["tags"] == ["backend", "urgent"]  # sorted


# --- WebSocket event payload schema regression ---


def test_task_to_dict_keys_match_task_response():
    """_task_to_dict keys must exactly match TaskResponse schema fields.

    This test fails if a field is added to TaskResponse but not _task_to_dict,
    or vice versa. Prevents regressions where WebSocket events have partial data.
    """
    from main import TaskResponse

    task = _make_mock_task(tags=["test"])
    result = _task_to_dict(task)

    expected_keys = set(TaskResponse.model_fields.keys())
    actual_keys = set(result.keys())
    assert actual_keys == expected_keys, (
        f"Key mismatch between _task_to_dict and TaskResponse.\n"
        f"Missing from _task_to_dict: {expected_keys - actual_keys}\n"
        f"Extra in _task_to_dict: {actual_keys - expected_keys}"
    )


def test_task_to_dict_preserves_fields_across_status_transitions():
    """Description, tags, and position are preserved regardless of task status.

    Simulates the worker updating status from pending→running→review and
    asserts critical fields are always present in the payload.
    """
    for status in ["pending", "running", "review", "scheduled", "completed"]:
        task = _make_mock_task(
            status=status,
            description="Important task details",
            position=7,
            tags=["deploy", "ci"],
        )
        result = _task_to_dict(task)
        assert result["description"] == "Important task details", f"description lost at status={status}"
        assert result["position"] == 7, f"position lost at status={status}"
        assert result["tags"] == ["ci", "deploy"], f"tags lost at status={status}"


# --- put_archive ---


def test_put_archive_creates_tar():
    """put_archive calls container.put_archive with tar data."""
    container = MagicMock()
    files = {"prompt.txt": "Hello world", "mcp.json": '{"servers": []}'}
    put_archive(container, files, dest="/workspace")

    container.put_archive.assert_called_once()
    call_args = container.put_archive.call_args
    assert call_args[0][0] == "/workspace"
    # Second arg is the tar buffer
    tar_data = call_args[0][1]
    assert tar_data is not None


# --- Settings reader ---


@pytest.fixture()
async def db_session():
    """Create an in-memory SQLite session for testing."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT NOT NULL PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'new' NOT NULL,
                category TEXT DEFAULT 'immediate',
                execute_at DATETIME,
                repeat_interval TEXT,
                repeat_until DATETIME,
                position INTEGER DEFAULT 0 NOT NULL,
                output TEXT,
                retry_count INTEGER DEFAULT 0 NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tags (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_tags (
                task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (task_id, tag_id)
            )
        """))

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture()
async def retry_session_factory(db_session):
    """Create a session factory for retry tests that shares the same engine."""
    # db_session is already connected to an in-memory SQLite with tables created.
    # We need a session factory that worker._schedule_retry can use.
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'new' NOT NULL,
                category TEXT DEFAULT 'immediate',
                execute_at DATETIME,
                repeat_interval TEXT,
                repeat_until DATETIME,
                position INTEGER DEFAULT 0 NOT NULL,
                output TEXT,
                retry_count INTEGER DEFAULT 0 NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tags (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS task_tags (
                task_id VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                tag_id VARCHAR(36) NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                PRIMARY KEY (task_id, tag_id)
            )
        """))

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield engine, factory
    await engine.dispose()


# --- Retry scheduling ---


async def _insert_task(factory, **kwargs):
    """Insert a task using the ORM model and return its id."""
    task = Task(**kwargs)
    async with factory() as session:
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task.id


async def test_schedule_retry_first_failure(retry_session_factory):
    """First failure schedules retry in 1 minute with retry_count=1."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=0)

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("worker.async_session", factory), \
         patch("worker.publish_event", new_callable=AsyncMock):
        await _schedule_retry(mock_task, output="Docker error: not found")

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.status == "scheduled"
        assert updated.retry_count == 1
        assert updated.execute_at is not None
        assert updated.output == "Docker error: not found"


async def test_schedule_retry_exponential_backoff(retry_session_factory):
    """Third failure (retry_count=2) schedules retry in 4 minutes."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=2)

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id
    before = datetime.now(timezone.utc)

    with patch("worker.async_session", factory), \
         patch("worker.publish_event", new_callable=AsyncMock):
        await _schedule_retry(mock_task)

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.retry_count == 3
        assert updated.execute_at is not None
        # execute_at should be ~4 minutes in the future (2^2 = 4)
        # SQLite returns naive datetimes, so strip tzinfo for comparison
        delta = updated.execute_at.replace(tzinfo=None) - before.replace(tzinfo=None)
        assert delta >= timedelta(minutes=3, seconds=50)
        assert delta <= timedelta(minutes=5)


async def test_schedule_retry_preserves_output_when_none(retry_session_factory):
    """When no output is provided, existing output is preserved."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=0, output="previous output")

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("worker.async_session", factory), \
         patch("worker.publish_event", new_callable=AsyncMock):
        await _schedule_retry(mock_task)

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.output == "previous output"


async def test_read_settings_defaults(db_session):
    """When no settings exist, returns empty defaults."""
    settings = await read_settings(db_session)
    assert settings["mcp_servers"] == {}
    assert settings["credentials"] == []
    assert settings["task_processing_model"] == DEFAULT_TASK_PROCESSING_MODEL
    assert settings["system_prompt"] == ""


async def test_read_settings_with_mcp(db_session):
    """Reads mcp_servers from settings table."""
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "mcp_servers", "value": json.dumps({"servers": [{"name": "test"}]})},
    )
    await db_session.commit()

    settings = await read_settings(db_session)
    assert settings["mcp_servers"] == {"servers": [{"name": "test"}]}
    assert settings["credentials"] == []


async def test_read_settings_with_credentials(db_session):
    """Reads credentials from settings table."""
    creds = [{"key": "API_KEY", "value": "secret123"}]
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "credentials", "value": json.dumps(creds)},
    )
    await db_session.commit()

    settings = await read_settings(db_session)
    assert settings["mcp_servers"] == {}
    assert settings["credentials"] == [{"key": "API_KEY", "value": "secret123"}]


async def test_read_settings_with_task_processing_model(db_session):
    """Reads task_processing_model from settings table."""
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "task_processing_model", "value": json.dumps("gpt-4o")},
    )
    await db_session.commit()

    settings = await read_settings(db_session)
    assert settings["task_processing_model"] == "gpt-4o"


async def test_read_settings_with_system_prompt(db_session):
    """Reads system_prompt from settings table."""
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "system_prompt", "value": json.dumps("You are a helpful assistant.")},
    )
    await db_session.commit()

    settings = await read_settings(db_session)
    assert settings["system_prompt"] == "You are a helpful assistant."


# --- Container environment variables ---


def test_process_task_container_env_vars():
    """process_task_in_container sets correct env vars on the container."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {"mcpServers": {"test": {"url": "http://localhost/mcp"}}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful",
    }

    mock_container = MagicMock()
    mock_container.id = "container-123"
    mock_container.short_id = "cont123"
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b'{"status":"completed","result":"done","questions":[]}'

    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container

    import worker
    original_client = worker.docker_client
    worker.docker_client = mock_client

    try:
        with patch.dict("os.environ", {"OPENAI_BASE_URL": "http://litellm:4000", "OPENAI_API_KEY": "sk-test"}):
            exit_code, stdout, stderr = process_task_in_container(task, settings)
    finally:
        worker.docker_client = original_client

    # Check container was created with correct env vars
    create_call = mock_client.containers.create.call_args
    env = create_call[1]["environment"]
    assert env["OPENAI_BASE_URL"] == "http://litellm:4000"
    assert env["OPENAI_API_KEY"] == "sk-test"
    assert env["OPENAI_MODEL"] == "gpt-4o"
    assert env["USER_PROMPT_PATH"] == "/workspace/prompt.txt"
    assert env["SYSTEM_PROMPT_PATH"] == "/workspace/system_prompt.txt"
    assert env["MCP_CONFIGURATION_PATH"] == "/workspace/mcp.json"
    assert exit_code == 0


def test_process_task_container_copies_three_files():
    """process_task_in_container copies prompt.txt, system_prompt.txt, and mcp.json."""
    task = _make_mock_task(description="My task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "System instructions",
    }

    mock_container = MagicMock()
    mock_container.id = "container-456"
    mock_container.short_id = "cont456"
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b"output"

    mock_client = MagicMock()
    mock_client.containers.create.return_value = mock_container

    import worker
    original_client = worker.docker_client
    worker.docker_client = mock_client

    try:
        with patch.dict("os.environ", {"OPENAI_BASE_URL": "", "OPENAI_API_KEY": ""}):
            process_task_in_container(task, settings)
    finally:
        worker.docker_client = original_client

    # put_archive is called on the container with tar data
    mock_container.put_archive.assert_called_once()
    call_args = mock_container.put_archive.call_args[0]
    assert call_args[0] == "/workspace"


# --- Structured output parsing ---


def test_task_runner_output_valid_completed():
    """Valid completed output parses correctly."""
    raw = '{"status": "completed", "result": "Task done successfully", "questions": []}'
    parsed = TaskRunnerOutput.model_validate_json(raw)
    assert parsed.status == "completed"
    assert parsed.result == "Task done successfully"
    assert parsed.questions == []


def test_task_runner_output_valid_needs_input():
    """Valid needs_input output parses correctly."""
    raw = '{"status": "needs_input", "result": "Need clarification", "questions": ["What scope?", "Which env?"]}'
    parsed = TaskRunnerOutput.model_validate_json(raw)
    assert parsed.status == "needs_input"
    assert parsed.result == "Need clarification"
    assert parsed.questions == ["What scope?", "Which env?"]


def test_task_runner_output_invalid_json():
    """Invalid JSON raises ValidationError."""
    with pytest.raises(Exception):  # ValidationError or ValueError
        TaskRunnerOutput.model_validate_json("not json at all")


def test_task_runner_output_invalid_status():
    """Invalid status value raises ValidationError."""
    raw = '{"status": "unknown", "result": "test", "questions": []}'
    with pytest.raises(Exception):
        TaskRunnerOutput.model_validate_json(raw)


def test_task_runner_output_missing_result():
    """Missing required result field raises ValidationError."""
    raw = '{"status": "completed", "questions": []}'
    with pytest.raises(Exception):
        TaskRunnerOutput.model_validate_json(raw)


def test_task_runner_output_default_questions():
    """Questions field defaults to empty list when omitted."""
    raw = '{"status": "completed", "result": "done"}'
    parsed = TaskRunnerOutput.model_validate_json(raw)
    assert parsed.questions == []
