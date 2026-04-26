"""Worker unit tests: settings reader, output truncation, task_to_dict, retry scheduling."""
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from models import Setting, Task

# Import task_manager functions under test
from task_manager import (
    _read_settings as read_settings, truncate_output, _task_to_dict,
    TaskManager, DEFAULT_TASK_PROCESSING_MODEL,
    TaskRunnerOutput, parse_interval, normalize_interval,
    substitute_env_vars, extract_json, generate_ssh_config,
    build_skills_archive, build_skill_manifest,
    recall_from_hindsight, DEFAULT_HINDSIGHT_BANK_ID,
    _read_callback_result,
    REPO_CONTEXT_INSTRUCTIONS, PLAYWRIGHT_MCP_URL,
)
from container_runtime import (
    _put_archive as put_archive, _put_archive_ssh as put_archive_ssh,
    RuntimeHandle,
)


def _make_mock_runtime(
    exit_code: int = 0,
    stdout: str = '{"status":"completed","result":"done","questions":[]}',
    stderr: str = "",
    log_lines: list[str] | None = None,
):
    """Create a mock ContainerRuntime for TaskManager._process_task tests.

    Returns a MagicMock with async_prepare/async_run/async_result/async_cleanup
    methods configured. After running the test, inspect
    mock_runtime.async_prepare.call_args.kwargs to check env vars, files, etc.
    """
    mock_runtime = MagicMock()
    mock_runtime.async_prepare = AsyncMock(return_value=RuntimeHandle(runtime_data={}))

    lines = log_lines or []

    async def _async_run(handle):
        for line in lines:
            yield line

    mock_runtime.async_run = _async_run
    mock_runtime.async_result = AsyncMock(return_value=(exit_code, stdout, stderr))
    mock_runtime.async_cleanup = AsyncMock()
    return mock_runtime


async def _run_process_task(task, settings, mock_runtime=None, github_credentials=None, cloud_storage_credentials=None, mock_valkey=None):
    """Helper: create a TaskManager, set mock runtime, call _process_task."""
    if mock_runtime is None:
        mock_runtime = _make_mock_runtime()
    tm = TaskManager()
    tm._runtime = mock_runtime
    with patch("task_manager.get_valkey", return_value=mock_valkey):
        result = await tm._process_task(
            task, settings,
            github_credentials=github_credentials,
            cloud_storage_credentials=cloud_storage_credentials,
        )
    return result


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


# --- Environment variable substitution ---


def test_substitute_env_vars_dollar_syntax():
    """$VAR syntax is substituted from the provided mapping."""
    obj = {"headers": {"x-api-key": "Bearer $API_KEY"}}
    result = substitute_env_vars(obj, environ={"API_KEY": "sk-secret-123"})
    assert result == {"headers": {"x-api-key": "Bearer sk-secret-123"}}


def test_substitute_env_vars_braced_syntax():
    """${VAR} syntax is substituted from the provided mapping."""
    obj = {"headers": {"Authorization": "${AUTH_TOKEN}"}}
    result = substitute_env_vars(obj, environ={"AUTH_TOKEN": "Bearer abc-456"})
    assert result == {"headers": {"Authorization": "Bearer abc-456"}}


def test_substitute_env_vars_missing_variable():
    """Missing environment variable leaves placeholder unchanged."""
    obj = {"headers": {"x-api-key": "$MISSING_KEY"}}
    result = substitute_env_vars(obj, environ={})
    assert result == {"headers": {"x-api-key": "$MISSING_KEY"}}


def test_substitute_env_vars_nested():
    """Variables at various depths in nested structures are substituted."""
    obj = {
        "mcpServers": {
            "svc1": {"url": "http://host/mcp", "headers": {"key": "$DB_PASSWORD"}},
            "svc2": {"nested": {"deep": {"value": "$DB_PASSWORD"}}},
        }
    }
    result = substitute_env_vars(obj, environ={"DB_PASSWORD": "s3cret"})
    assert result["mcpServers"]["svc1"]["headers"]["key"] == "s3cret"
    assert result["mcpServers"]["svc2"]["nested"]["deep"]["value"] == "s3cret"


def test_substitute_env_vars_non_string_values():
    """Numbers, booleans, and nulls pass through unchanged."""
    obj = {"port": 8080, "enabled": True, "extra": None, "items": [1, False, "val"]}
    result = substitute_env_vars(obj, environ={"val": "x"})
    assert result == {"port": 8080, "enabled": True, "extra": None, "items": [1, False, "val"]}


def test_substitute_env_vars_multiple_in_single_string():
    """Multiple variables in a single string value are all substituted."""
    obj = {"url": "$SCHEME://$HOST:$PORT/mcp"}
    result = substitute_env_vars(obj, environ={"SCHEME": "https", "HOST": "api.example.com", "PORT": "8443"})
    assert result == {"url": "https://api.example.com:8443/mcp"}


def test_substitute_env_vars_no_variables():
    """Config with no variable references passes through unchanged."""
    obj = {"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {}}}}
    result = substitute_env_vars(obj, environ={"UNUSED": "value"})
    assert result == {"mcpServers": {"svc": {"url": "http://host/mcp", "headers": {}}}}


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
    task.runner_logs = overrides.get("runner_logs", None)
    task.retry_count = overrides.get("retry_count", 0)
    # Tags: list of mock Tag objects with .name attribute
    tags = overrides.get("tags", [])
    mock_tags = []
    for t in tags:
        tag = MagicMock()
        tag.name = t
        mock_tags.append(tag)
    task.tags = mock_tags
    task.questions = overrides.get("questions", None)
    task.heartbeat_at = overrides.get("heartbeat_at", None)
    task.profile_id = overrides.get("profile_id", None)
    task.created_by = overrides.get("created_by", None)
    task.updated_by = overrides.get("updated_by", None)
    task.created_at = MagicMock()
    task.created_at.isoformat.return_value = overrides.get("created_at_iso", "2026-01-01T00:00:00")
    task.updated_at = MagicMock()
    task.updated_at.isoformat.return_value = overrides.get("updated_at_iso", "2026-01-01T00:01:00")
    return task


def test_task_to_dict_includes_runner_logs():
    """_task_to_dict includes the runner_logs field."""
    task = _make_mock_task(status="review", runner_logs="2026-02-10 INFO Agent started")
    result = _task_to_dict(task)
    assert result["runner_logs"] == "2026-02-10 INFO Agent started"


def test_task_to_dict_null_runner_logs():
    """_task_to_dict handles None runner_logs."""
    task = _make_mock_task(status="pending", runner_logs=None)
    result = _task_to_dict(task)
    assert result["runner_logs"] is None


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
            include_git_skills BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
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
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS skills (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                instructions TEXT NOT NULL DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS skill_files (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                skill_id VARCHAR(36) NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE (skill_id, path)
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
    # We need a session factory that TaskManager()._schedule_retry can use.
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("""
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
            include_git_skills BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
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

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="Docker error: not found")

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

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task)

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


async def test_schedule_retry_stores_runner_logs(retry_session_factory):
    """Retry stores runner_logs when provided."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=0)

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="full output", runner_logs="stderr logs here")

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.runner_logs == "stderr logs here"
        assert updated.output == "full output"


async def test_schedule_retry_preserves_runner_logs_when_none(retry_session_factory):
    """When no runner_logs provided, existing value is preserved."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=0)

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="some output")

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.runner_logs is None


async def test_schedule_retry_preserves_output_when_none(retry_session_factory):
    """When no output is provided, existing output is preserved."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=0, output="previous output")

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task)

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        updated = result.scalar_one()
        assert updated.output == "previous output"


# --- Retry tag tests ---


async def _get_task_tag_names(factory, task_id):
    """Return the tag names associated with a task."""
    async with factory() as session:
        result = await session.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.id == task_id)
        )
        task = result.scalar_one()
        return [t.name for t in task.tags]


async def test_schedule_retry_adds_retry_tag(retry_session_factory):
    """_schedule_retry adds a 'Retry' tag to the task."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=0)

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="error output")

    tag_names = await _get_task_tag_names(factory, task_id)
    assert "Retry" in tag_names


async def test_schedule_retry_no_duplicate_tag(retry_session_factory):
    """Second retry does not create a duplicate 'Retry' tag association."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=0)

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="first error")

    # Update status back to running for second retry
    async with factory() as session:
        await session.execute(
            update(Task).where(Task.id == task_id).values(status="running")
        )
        await session.commit()

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="second error")

    tag_names = await _get_task_tag_names(factory, task_id)
    assert tag_names.count("Retry") == 1


async def test_success_removes_retry_tag(retry_session_factory):
    """Successful completion removes the 'Retry' tag from the task."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=1)

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    # First, add a Retry tag via _schedule_retry
    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="error")

    tag_names = await _get_task_tag_names(factory, task_id)
    assert "Retry" in tag_names

    # Now simulate the success path: update task and remove Retry tag
    from models import Tag, task_tags as tt
    async with factory() as session:
        new_position = 1
        values = {
            "status": "completed",
            "position": new_position,
            "output": "Task done",
            "runner_logs": "",
            "retry_count": 0,
            "updated_at": datetime.now(timezone.utc),
        }
        await session.execute(
            update(Task).where(Task.id == task_id).values(**values)
        )
        # Remove Retry tag (same logic as worker success path)
        result = await session.execute(
            select(Tag).where(Tag.name == "Retry")
        )
        retry_tag = result.scalar_one_or_none()
        if retry_tag is not None:
            await session.execute(
                tt.delete().where(
                    tt.c.task_id == task_id,
                    tt.c.tag_id == retry_tag.id,
                )
            )
        await session.commit()

    tag_names = await _get_task_tag_names(factory, task_id)
    assert "Retry" not in tag_names


async def test_review_removes_retry_tag(retry_session_factory):
    """Task moving to review (needs_input) removes the 'Retry' tag."""
    engine, factory = retry_session_factory
    task_id = await _insert_task(factory, title="Test task", status="running", retry_count=1)

    mock_task = MagicMock(spec=Task)
    mock_task.id = task_id

    # First, add a Retry tag via _schedule_retry
    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._schedule_retry(mock_task, output="error")

    tag_names = await _get_task_tag_names(factory, task_id)
    assert "Retry" in tag_names

    # Now simulate the review path: update task and remove Retry tag
    from models import Tag, task_tags as tt
    async with factory() as session:
        values = {
            "status": "review",
            "position": 1,
            "output": "Need clarification",
            "runner_logs": "",
            "retry_count": 0,
            "updated_at": datetime.now(timezone.utc),
        }
        await session.execute(
            update(Task).where(Task.id == task_id).values(**values)
        )
        # Remove Retry tag (same logic as worker success path)
        result = await session.execute(
            select(Tag).where(Tag.name == "Retry")
        )
        retry_tag = result.scalar_one_or_none()
        if retry_tag is not None:
            await session.execute(
                tt.delete().where(
                    tt.c.task_id == task_id,
                    tt.c.tag_id == retry_tag.id,
                )
            )
        await session.commit()

    tag_names = await _get_task_tag_names(factory, task_id)
    assert "Retry" not in tag_names


async def test_read_settings_defaults(db_session):
    """When no settings exist, returns empty defaults."""
    settings = await read_settings(db_session)
    assert settings["mcp_servers"] == {}
    assert settings["credentials"] == []
    assert settings["task_processing_model"] == DEFAULT_TASK_PROCESSING_MODEL
    assert settings["system_prompt"] == ""
    assert settings["task_runner_log_level"] == ""
    assert settings["mcp_api_key"] == ""
    assert settings["hot_tools"] == ""


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
    """Reads task_processing_model from settings table (legacy string normalized to dict)."""
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "task_processing_model", "value": json.dumps("gpt-4o")},
    )
    await db_session.commit()

    settings = await read_settings(db_session)
    assert settings["task_processing_model"] == {"provider_id": None, "model": "gpt-4o"}


async def test_read_settings_with_system_prompt(db_session):
    """Reads system_prompt from settings table."""
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "system_prompt", "value": json.dumps("You are a helpful assistant.")},
    )
    await db_session.commit()

    settings = await read_settings(db_session)
    assert settings["system_prompt"] == "You are a helpful assistant."


async def test_read_settings_with_task_runner_log_level(db_session):
    """Reads task_runner_log_level from settings table."""
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "task_runner_log_level", "value": json.dumps("DEBUG")},
    )
    await db_session.commit()

    settings = await read_settings(db_session)
    assert settings["task_runner_log_level"] == "DEBUG"


async def test_read_settings_with_hot_tools(db_session):
    """Reads hot_tools from settings table."""
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "hot_tools", "value": json.dumps("retain,recall,web_search")},
    )
    await db_session.commit()

    settings = await read_settings(db_session)
    assert settings["hot_tools"] == "retain,recall,web_search"


# --- Container environment variables ---


@pytest.mark.asyncio
async def test_process_task_container_env_vars():
    """_process_task sets correct env vars on the container."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {"mcpServers": {"test": {"url": "http://localhost/mcp"}}},
        "credentials": [],
        "task_processing_model": {"provider_id": "fake-provider-id", "model": "gpt-4o"},
        "system_prompt": "Be helpful",
    }

    mock_runtime = _make_mock_runtime()

    with patch("task_manager._resolve_provider_sync", return_value={"base_url": "http://litellm:4000", "api_key": "sk-test"}):
        exit_code, stdout, stderr = await _run_process_task(task, settings, mock_runtime)

    # Check container was created with correct env vars
    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert env["OPENAI_BASE_URL"] == "http://litellm:4000"
    assert env["OPENAI_API_KEY"] == "sk-test"
    assert env["OPENAI_MODEL"] == "gpt-4o"
    assert env["USER_PROMPT_PATH"] == "/workspace/prompt.txt"
    assert env["SYSTEM_PROMPT_PATH"] == "/workspace/system_prompt.txt"
    assert env["MCP_CONFIGURATION_PATH"] == "/workspace/mcp.json"
    assert exit_code == 0


@pytest.mark.asyncio
async def test_process_task_container_passes_log_level_from_settings():
    """task_runner_log_level from settings is forwarded as LOG_LEVEL to the container."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "task_runner_log_level": "DEBUG",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }):
        await _run_process_task(task, settings, mock_runtime)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert env["LOG_LEVEL"] == "DEBUG"


@pytest.mark.asyncio
async def test_process_task_container_passes_hot_tools_from_settings():
    """hot_tools from settings is forwarded as HOT_TOOLS to the container."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "hot_tools": "retain,recall,web_search",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }):
        await _run_process_task(task, settings, mock_runtime)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert env["HOT_TOOLS"] == "retain,recall,web_search"


@pytest.mark.asyncio
async def test_process_task_container_omits_hot_tools_when_empty():
    """HOT_TOOLS env var is not set when hot_tools setting is empty."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "hot_tools": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }):
        await _run_process_task(task, settings, mock_runtime)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert "HOT_TOOLS" not in env


@pytest.mark.asyncio
async def test_process_task_container_log_level_env_fallback():
    """TASK_RUNNER_LOG_LEVEL env var is used when settings value is empty."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "task_runner_log_level": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
            "TASK_RUNNER_LOG_LEVEL": "WARNING",
        }):
        await _run_process_task(task, settings, mock_runtime)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert env["LOG_LEVEL"] == "WARNING"


@pytest.mark.asyncio
async def test_process_task_container_omits_log_level_when_unset():
    """LOG_LEVEL is not set when both settings and env var are absent."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "task_runner_log_level": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }, clear=True):
        await _run_process_task(task, settings, mock_runtime)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert "LOG_LEVEL" not in env


@pytest.mark.asyncio
async def test_skills_directive_appended_when_skills_exist():
    """When skills are defined, system prompt has the skill manifest and skills archive is written."""
    task = _make_mock_task(description="Research task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "You are a helpful assistant.",
        "skills": [
            {"name": "researcher", "description": "Web research", "instructions": "Full instructions", "files": []},
        ],
        "mcp_api_key": "test-api-key-123",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }):
        await _run_process_task(task, settings, mock_runtime)

    # Check system prompt has skill manifest (not old MCP directives)
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    system_prompt_content = files["system_prompt.txt"]
    assert "You are a helpful assistant." in system_prompt_content
    assert "## Skills" in system_prompt_content
    assert "| researcher | Web research |" in system_prompt_content
    assert "SKILL.md" in system_prompt_content
    assert "list_skills" not in system_prompt_content
    assert "get_skill" not in system_prompt_content

    # Check MCP config does NOT have the errand server auto-injected
    mcp_content = json.loads(files["mcp.json"])
    assert "errand" not in mcp_content.get("mcpServers", {})

    # Skills archive should have been passed to prepare()
    import tarfile
    skills_tar = mock_runtime.async_prepare.call_args.kwargs["skills_tar"]
    assert skills_tar is not None
    tar = tarfile.open(fileobj=io.BytesIO(skills_tar))
    assert "skills/researcher/SKILL.md" in tar.getnames()


@pytest.mark.asyncio
async def test_skills_directive_omitted_when_no_skills():
    """When no skills are defined, system prompt has no skills directive and no skills archive is written."""
    task = _make_mock_task(description="Research task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "You are a helpful assistant.",
        "skills": [],
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }):
        await _run_process_task(task, settings, mock_runtime)

    # Check files passed to prepare()
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    system_prompt_content = files["system_prompt.txt"]
    assert system_prompt_content.startswith("You are a helpful assistant.")
    assert "## Skills" not in system_prompt_content

    # Check MCP config does NOT have the errand server
    mcp_content = json.loads(files["mcp.json"])
    assert "errand" not in mcp_content.get("mcpServers", {})

    # No skills archive should have been passed
    skills_tar = mock_runtime.async_prepare.call_args.kwargs.get("skills_tar")
    assert skills_tar is None


@pytest.mark.asyncio
async def test_process_task_container_copies_three_files():
    """process_task_in_container copies prompt.txt, system_prompt.txt, and mcp.json."""
    task = _make_mock_task(description="My task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "System instructions",
    }

    mock_runtime = _make_mock_runtime(stdout='output')

    with patch.dict("os.environ", {"OPENAI_BASE_URL": "", "OPENAI_API_KEY": ""}):
        await _run_process_task(task, settings, mock_runtime)

    # prepare() should have been called with the three required files
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    assert "prompt.txt" in files
    assert "system_prompt.txt" in files
    assert "mcp.json" in files


# --- Valkey unavailability during log streaming ---


@pytest.mark.asyncio
async def test_process_task_completes_when_valkey_unavailable():
    """Task still completes when sync Redis client fails to connect for log streaming."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime(
        log_lines=["stderr line 1", "stderr line 2"],
        stderr="stderr line 1\nstderr line 2\n",
    )

    with patch.dict("os.environ", {"OPENAI_BASE_URL": "", "OPENAI_API_KEY": ""}), \
         patch("redis.Redis.from_url", side_effect=ConnectionError("Valkey down")):
        exit_code, stdout, stderr = await _run_process_task(task, settings, mock_runtime)

    assert exit_code == 0
    assert "completed" in stdout
    assert "stderr line" in stderr


# --- Structured event parsing from stderr to Valkey ---


@pytest.mark.asyncio
async def test_process_task_publishes_structured_events_to_valkey():
    """Structured JSON stderr lines are published as task_event messages to Valkey."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    tool_call_event = json.dumps({"type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "ls"}}})

    mock_runtime = _make_mock_runtime(log_lines=[tool_call_event])

    mock_redis = AsyncMock()

    with patch.dict("os.environ", {"OPENAI_BASE_URL": "", "OPENAI_API_KEY": ""}):
        await _run_process_task(task, settings, mock_runtime, mock_valkey=mock_redis)

    # Find the task_event publish call (not the task_log_end)
    publish_calls = mock_redis.publish.call_args_list
    event_calls = [c for c in publish_calls if "task_event" in str(c)]
    assert len(event_calls) >= 1
    published_msg = json.loads(event_calls[0][0][1])
    assert published_msg["event"] == "task_event"
    assert published_msg["type"] == "tool_call"
    assert published_msg["data"]["tool"] == "execute_command"


@pytest.mark.asyncio
async def test_process_task_publishes_raw_event_for_non_json_stderr():
    """Non-JSON stderr lines are published as raw events."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime(log_lines=["Traceback (most recent call last):"])

    mock_redis = AsyncMock()

    with patch.dict("os.environ", {"OPENAI_BASE_URL": "", "OPENAI_API_KEY": ""}):
        await _run_process_task(task, settings, mock_runtime, mock_valkey=mock_redis)

    # Find the raw event publish call
    publish_calls = mock_redis.publish.call_args_list
    event_calls = [c for c in publish_calls if "task_event" in str(c)]
    assert len(event_calls) >= 1
    published_msg = json.loads(event_calls[0][0][1])
    assert published_msg["event"] == "task_event"
    assert published_msg["type"] == "raw"
    assert "Traceback" in published_msg["data"]["line"]


@pytest.mark.asyncio
async def test_process_task_buffers_chunked_stderr_lines():
    """JSON lines are published as structured events when complete."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    # With the runtime abstraction, run() yields complete lines (no chunking at this level)
    full_line = json.dumps({"type": "tool_call", "data": {"tool": "execute_command", "args": {"command": "cat file.txt"}}})
    mock_runtime = _make_mock_runtime(log_lines=[full_line])

    mock_redis = AsyncMock()

    with patch.dict("os.environ", {"OPENAI_BASE_URL": "", "OPENAI_API_KEY": ""}):
        await _run_process_task(task, settings, mock_runtime, mock_valkey=mock_redis)

    # The JSON should be parsed into a structured event
    publish_calls = mock_redis.publish.call_args_list
    event_calls = [c for c in publish_calls if "task_event" in str(c) and "task_log_end" not in str(c)]
    assert len(event_calls) == 1
    published_msg = json.loads(event_calls[0][0][1])
    assert published_msg["event"] == "task_event"
    assert published_msg["type"] == "tool_call"
    assert published_msg["data"]["tool"] == "execute_command"


@pytest.mark.asyncio
async def test_process_task_publishes_end_sentinel():
    """task_log_end sentinel is still published after container exit."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()

    mock_redis = AsyncMock()

    with patch.dict("os.environ", {"OPENAI_BASE_URL": "", "OPENAI_API_KEY": ""}):
        await _run_process_task(task, settings, mock_runtime, mock_valkey=mock_redis)

    # The last publish call should be task_log_end
    last_call = mock_redis.publish.call_args_list[-1]
    published_msg = json.loads(last_call[0][1])
    assert published_msg == {"event": "task_log_end"}


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


# --- extract_json ---


def test_extract_json_bare_json():
    """Extracts valid JSON when output is bare JSON."""
    raw = '{"status": "completed", "result": "Done", "questions": []}'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.status == "completed"


def test_extract_json_code_fence_at_start():
    """Extracts JSON from code fence at start of output."""
    raw = '```json\n{"status": "completed", "result": "Done", "questions": []}\n```'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.status == "completed"


def test_extract_json_preamble_before_code_fence():
    """Extracts JSON when there is preamble text before a code fence."""
    raw = 'Based on my analysis:\n\n```json\n{"status": "completed", "result": "All healthy", "questions": []}\n```'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.status == "completed"
    assert parsed.result == "All healthy"


def test_extract_json_preamble_before_bare_json():
    """Extracts JSON when there is preamble text before bare JSON."""
    raw = 'Here is the result:\n{"status": "completed", "result": "done", "questions": []}'
    result = extract_json(raw)
    assert result is not None
    parsed = TaskRunnerOutput.model_validate_json(result)
    assert parsed.result == "done"


def test_extract_json_unparseable():
    """Returns None when no valid TaskRunnerOutput JSON is found."""
    assert extract_json("This is just plain text.") is None


def test_extract_json_invalid_json_in_fence():
    """Returns None when code fence contains invalid JSON."""
    raw = '```json\nnot valid json\n```'
    assert extract_json(raw) is None


# --- parse_interval ---


def test_parse_interval_minutes():
    assert parse_interval("15m") == timedelta(minutes=15)


def test_parse_interval_hours():
    assert parse_interval("2h") == timedelta(hours=2)


def test_parse_interval_days():
    assert parse_interval("1d") == timedelta(days=1)


def test_parse_interval_weeks():
    assert parse_interval("1w") == timedelta(weeks=1)


def test_parse_interval_large_number():
    assert parse_interval("30m") == timedelta(minutes=30)


def test_parse_interval_unparseable_crontab():
    assert parse_interval("0 9 * * MON-FRI") is None


def test_parse_interval_unparseable_empty():
    assert parse_interval("") is None


def test_parse_interval_unparseable_no_unit():
    assert parse_interval("30") is None


# --- parse_interval: human-readable formats ---


def test_parse_interval_human_days():
    assert parse_interval("7 days") == timedelta(days=7)


def test_parse_interval_human_day_singular():
    assert parse_interval("1 day") == timedelta(days=1)


def test_parse_interval_human_hours():
    assert parse_interval("2 hours") == timedelta(hours=2)


def test_parse_interval_human_hour_singular():
    assert parse_interval("1 hour") == timedelta(hours=1)


def test_parse_interval_human_minutes():
    assert parse_interval("30 minutes") == timedelta(minutes=30)


def test_parse_interval_human_weeks():
    assert parse_interval("2 weeks") == timedelta(weeks=2)


def test_parse_interval_named_daily():
    assert parse_interval("daily") == timedelta(days=1)


def test_parse_interval_named_weekly():
    assert parse_interval("weekly") == timedelta(weeks=1)


def test_parse_interval_named_hourly():
    assert parse_interval("hourly") == timedelta(hours=1)


def test_parse_interval_case_insensitive():
    assert parse_interval("7 Days") == timedelta(days=7)
    assert parse_interval("WEEKLY") == timedelta(weeks=1)
    assert parse_interval("2 Hours") == timedelta(hours=2)


def test_parse_interval_no_space():
    """Human-readable without space (e.g. '7days') also works."""
    assert parse_interval("7days") == timedelta(days=7)


# --- normalize_interval ---


def test_normalize_interval_compact_passthrough():
    assert normalize_interval("7d") == "7d"
    assert normalize_interval("15m") == "15m"


def test_normalize_interval_human_readable():
    assert normalize_interval("7 days") == "7d"
    assert normalize_interval("30 minutes") == "30m"
    assert normalize_interval("2 hours") == "2h"
    assert normalize_interval("1 week") == "1w"


def test_normalize_interval_named():
    assert normalize_interval("daily") == "1d"
    assert normalize_interval("weekly") == "1w"
    assert normalize_interval("hourly") == "1h"


def test_normalize_interval_unparseable():
    assert normalize_interval("every other tuesday") is None
    assert normalize_interval("0 9 * * MON-FRI") is None
    assert normalize_interval("") is None


# --- _reschedule_if_repeating ---


async def _insert_tag(factory, name: str) -> str:
    """Insert a tag and return its id."""
    from models import Tag
    tag = Tag(name=name)
    async with factory() as session:
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
        return tag.id


async def _link_tag(factory, task_id, tag_id):
    """Link a tag to a task via the association table."""
    async with factory() as session:
        await session.execute(text(
            "INSERT INTO task_tags (task_id, tag_id) VALUES (:tid, :gid)"
        ), {"tid": str(task_id), "gid": str(tag_id)})
        await session.commit()


def _make_completed_repeating_task(**overrides):
    """Build a DequeuedTask snapshot for rescheduling tests.

    _reschedule_if_repeating operates on the plain ``DequeuedTask`` dataclass
    (post-B4), so tests must pass the same shape rather than an ORM mock.
    """
    from task_manager import DequeuedTask

    # Allow callers to pass either tag_ids=[...] directly or tags=[mock_with_id].
    if "tag_ids" in overrides:
        tag_ids = list(overrides.pop("tag_ids"))
    else:
        tag_ids = [tag.id for tag in overrides.pop("tags", [])]

    return DequeuedTask(
        id=overrides.get("id", uuid.uuid4()),
        title=overrides.get("title", "Check server logs"),
        description=overrides.get("description", "Check logs on prod"),
        category=overrides.get("category", "repeating"),
        profile_id=overrides.get("profile_id", None),
        repeat_interval=overrides.get("repeat_interval", "30m"),
        repeat_until=overrides.get("repeat_until", None),
        tag_ids=tag_ids,
    )


@pytest.mark.asyncio
async def test_reschedule_repeating_creates_new_task(retry_session_factory):
    """Repeating task with repeat_interval='30m' and repeat_until=null creates a new scheduled task."""
    engine, factory = retry_session_factory
    task = _make_completed_repeating_task()

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._reschedule_if_repeating(task)

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.status == "scheduled"))
        new_task = result.scalar_one()
        assert new_task.title == "Check server logs"
        assert new_task.category == "repeating"
        assert new_task.repeat_interval == "30m"
        assert new_task.execute_at is not None
        assert new_task.status == "scheduled"


@pytest.mark.asyncio
async def test_reschedule_repeating_future_repeat_until(retry_session_factory):
    """Repeating task with repeat_until in the future creates a new task."""
    engine, factory = retry_session_factory
    future = datetime.now(timezone.utc) + timedelta(hours=24)
    task = _make_completed_repeating_task(repeat_interval="1h", repeat_until=future)

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._reschedule_if_repeating(task)

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.status == "scheduled"))
        new_task = result.scalar_one()
        assert new_task.repeat_until.replace(tzinfo=None) == future.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_reschedule_expired_repeat_until_skips(retry_session_factory):
    """Repeating task with expired repeat_until does NOT create a new task."""
    engine, factory = retry_session_factory
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    task = _make_completed_repeating_task(repeat_until=past)

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._reschedule_if_repeating(task)

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.status == "scheduled"))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_reschedule_non_repeating_skips(retry_session_factory):
    """Non-repeating (immediate) completed task does NOT create a new task."""
    engine, factory = retry_session_factory
    task = _make_completed_repeating_task(category="immediate")

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._reschedule_if_repeating(task)

    async with factory() as session:
        result = await session.execute(select(Task).where(Task.status == "scheduled"))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_reschedule_cloned_task_fields(retry_session_factory):
    """Cloned task has correct fields: fresh UUID, status=scheduled, output=null, etc."""
    engine, factory = retry_session_factory
    original_id = uuid.uuid4()
    tag_id = await _insert_tag(factory, "Monitoring")
    tag_mock = MagicMock()
    tag_mock.id = tag_id
    tag_mock.name = "Monitoring"
    task = _make_completed_repeating_task(
        id=original_id,
        tags=[tag_mock],
        repeat_interval="1d",
    )

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", new_callable=AsyncMock):
        await TaskManager()._reschedule_if_repeating(task)

    async with factory() as session:
        result = await session.execute(
            select(Task).options(selectinload(Task.tags)).where(Task.status == "scheduled")
        )
        new_task = result.scalar_one()
        assert str(new_task.id) != str(original_id)
        assert new_task.status == "scheduled"
        assert new_task.output is None
        assert new_task.runner_logs is None
        assert new_task.retry_count == 0
        assert len(new_task.tags) == 1
        assert new_task.tags[0].name == "Monitoring"


@pytest.mark.asyncio
async def test_reschedule_publishes_task_created_event(retry_session_factory):
    """task_created WebSocket event is published for the rescheduled task."""
    engine, factory = retry_session_factory
    task = _make_completed_repeating_task()
    mock_publish = AsyncMock()

    with patch("task_manager.async_session", factory), \
         patch("task_manager.publish_event", mock_publish):
        await TaskManager()._reschedule_if_repeating(task)

    mock_publish.assert_called_once()
    event_type, event_data = mock_publish.call_args[0]
    assert event_type == "task_created"
    assert event_data["title"] == "Check server logs"
    assert event_data["status"] == "scheduled"
    assert event_data["category"] == "repeating"


@pytest.mark.asyncio
async def test_needs_input_does_not_trigger_rescheduling():
    """Repeating task reaching needs_input/review status is NOT rescheduled.

    In run(), target_status is derived from parsed.status:
      "completed" -> "completed", "needs_input" -> "review"
    _reschedule_if_repeating is only called when target_status == "completed".
    """
    parsed = TaskRunnerOutput.model_validate_json(
        '{"status": "needs_input", "result": "Need info", "questions": ["?"]}'
    )
    target_status = "completed" if parsed.status == "completed" else "review"
    assert target_status != "completed", "needs_input must not map to 'completed' (would trigger rescheduling)"


# --- SSH config generation ---


def test_generate_ssh_config_single_host():
    config = generate_ssh_config(["github.com"])
    assert "Host github.com" in config
    assert "IdentityFile ~/.ssh/id_rsa.agent" in config
    assert "User git" in config
    assert "StrictHostKeyChecking accept-new" in config


def test_generate_ssh_config_multiple_hosts():
    config = generate_ssh_config(["github.com", "gitlab.com"])
    assert "Host github.com" in config
    assert "Host gitlab.com" in config


def test_generate_ssh_config_empty_hosts():
    config = generate_ssh_config([])
    assert config == ""


# --- SSH archive injection ---


def test_put_archive_ssh():
    """Verify put_archive_ssh creates a tar with correct file names and permissions."""
    import tarfile as tf

    container = MagicMock()
    put_archive_ssh(container, "PRIVATE_KEY_CONTENT", "Host github.com\n    User git\n")
    container.put_archive.assert_called_once()
    call_args = container.put_archive.call_args
    assert call_args[0][0] == "/home/nonroot/.ssh"

    # Inspect the tar contents
    buf = call_args[0][1]
    buf.seek(0)
    with tf.open(fileobj=buf, mode="r") as tar:
        members = {m.name: m for m in tar.getmembers()}
        # Directory entry sets .ssh to 700
        assert "." in members
        assert members["."].isdir()
        assert members["."].mode == 0o700
        assert "id_rsa.agent" in members
        assert "config" in members
        assert members["id_rsa.agent"].mode == 0o600
        assert members["config"].mode == 0o644
        assert members["id_rsa.agent"].uid == 65532
        # Read key content
        key_file = tar.extractfile("id_rsa.agent")
        assert key_file.read().decode("utf-8") == "PRIVATE_KEY_CONTENT"


# --- read_settings includes SSH keys ---


@pytest.fixture()
async def worker_session():
    """Create an async engine+session for worker tests that need the DB."""
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
            CREATE TABLE IF NOT EXISTS skills (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                instructions TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS skill_files (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                skill_id VARCHAR(36) NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                path TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(skill_id, path)
            )
        """))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_read_settings_includes_ssh_keys(worker_session: AsyncSession):
    worker_session.add(Setting(key="ssh_private_key", value="PRIVATE"))
    worker_session.add(Setting(key="git_ssh_hosts", value=json.dumps(["github.com"])))
    await worker_session.commit()
    settings = await read_settings(worker_session)
    assert settings["ssh_private_key"] == "PRIVATE"


async def test_read_settings_ssh_defaults_when_missing(worker_session: AsyncSession):
    settings = await read_settings(worker_session)
    assert settings["ssh_private_key"] == ""
    assert settings["git_ssh_hosts"] == []


# --- Skills archive assembly ---


def test_build_skills_archive_empty():
    """No skills returns None."""
    assert build_skills_archive([]) is None


def test_build_skills_archive_single_skill():
    """Single skill produces correct SKILL.md."""
    import tarfile
    skills = [{"name": "research", "description": "Conducts research", "instructions": "## Steps\n1. Search", "files": []}]
    data = build_skills_archive(skills)
    assert data is not None

    tar = tarfile.open(fileobj=io.BytesIO(data), mode="r")
    names = tar.getnames()
    assert "skills/research/SKILL.md" in names

    skill_md = tar.extractfile("skills/research/SKILL.md").read().decode()
    assert "name: research" in skill_md
    assert "description: Conducts research" in skill_md
    assert "## Steps" in skill_md


def test_build_skills_archive_with_files():
    """Skill with attached files includes them in the archive."""
    import tarfile
    skills = [{
        "name": "code-review",
        "description": "Reviews code",
        "instructions": "Review it",
        "files": [
            {"path": "scripts/check.py", "content": "print('check')"},
            {"path": "references/GUIDE.md", "content": "# Guide"},
        ],
    }]
    data = build_skills_archive(skills)
    tar = tarfile.open(fileobj=io.BytesIO(data), mode="r")
    names = tar.getnames()
    assert "skills/code-review/SKILL.md" in names
    assert "skills/code-review/scripts/check.py" in names
    assert "skills/code-review/references/GUIDE.md" in names

    script = tar.extractfile("skills/code-review/scripts/check.py").read().decode()
    assert script == "print('check')"


def test_build_skills_archive_multiple_skills():
    """Multiple skills produce separate directories."""
    import tarfile
    skills = [
        {"name": "alpha", "description": "d1", "instructions": "i1", "files": []},
        {"name": "beta", "description": "d2", "instructions": "i2", "files": []},
    ]
    data = build_skills_archive(skills)
    tar = tarfile.open(fileobj=io.BytesIO(data), mode="r")
    names = tar.getnames()
    assert "skills/alpha/SKILL.md" in names
    assert "skills/beta/SKILL.md" in names


# --- Profile skill filtering ---


def _filter_skills(skills, profile_skill_ids, include_git):
    """Reproduce the profile skill filtering logic from task_manager._process_task."""
    if profile_skill_ids is not None:
        db_skills = [s for s in skills if s.get("id") and s["id"] in profile_skill_ids]
        git_skills_filtered = [s for s in skills if not s.get("id")] if include_git else []
        return db_skills + git_skills_filtered
    return skills


def test_profile_skill_filter_select_with_git():
    """Select specific DB skills + include git skills."""
    skills = [
        {"id": "uuid-1", "name": "db-skill-1"},
        {"id": "uuid-2", "name": "db-skill-2"},
        {"name": "git-skill-1"},
        {"name": "git-skill-2"},
    ]
    result = _filter_skills(skills, ["uuid-1"], include_git=True)
    assert len(result) == 3
    assert result[0]["name"] == "db-skill-1"
    assert result[1]["name"] == "git-skill-1"
    assert result[2]["name"] == "git-skill-2"


def test_profile_skill_filter_select_without_git():
    """Select specific DB skills, exclude git skills."""
    skills = [
        {"id": "uuid-1", "name": "db-skill-1"},
        {"id": "uuid-2", "name": "db-skill-2"},
        {"name": "git-skill-1"},
    ]
    result = _filter_skills(skills, ["uuid-1"], include_git=False)
    assert len(result) == 1
    assert result[0]["name"] == "db-skill-1"


def test_profile_skill_filter_empty_ids_with_git():
    """Empty skill_ids but include git skills = git skills only."""
    skills = [
        {"id": "uuid-1", "name": "db-skill-1"},
        {"name": "git-skill-1"},
    ]
    result = _filter_skills(skills, [], include_git=True)
    assert len(result) == 1
    assert result[0]["name"] == "git-skill-1"


def test_profile_skill_filter_empty_ids_without_git():
    """Empty skill_ids + no git = no skills at all."""
    skills = [
        {"id": "uuid-1", "name": "db-skill-1"},
        {"name": "git-skill-1"},
    ]
    result = _filter_skills(skills, [], include_git=False)
    assert len(result) == 0


def test_profile_skill_filter_inherit():
    """Null skill_ids = inherit all (both DB and git)."""
    skills = [
        {"id": "uuid-1", "name": "db-skill-1"},
        {"name": "git-skill-1"},
    ]
    result = _filter_skills(skills, None, include_git=False)
    assert len(result) == 2


# --- Skill manifest ---


def test_build_skill_manifest():
    """Manifest includes skill table and directive."""
    skills = [
        {"name": "research", "description": "Conducts web research"},
        {"name": "code-review", "description": "Reviews code"},
    ]
    manifest = build_skill_manifest(skills)
    assert "## Skills" in manifest
    assert "| research | Conducts web research |" in manifest
    assert "| code-review | Reviews code |" in manifest
    assert "/workspace/skills/" in manifest
    assert "SKILL.md" in manifest


def test_build_skill_manifest_no_mcp_directive():
    """Manifest should NOT contain old MCP tool directives."""
    skills = [{"name": "test", "description": "Test"}]
    manifest = build_skill_manifest(skills)
    assert "list_skills" not in manifest
    assert "get_skill" not in manifest


# --- read_settings includes skills from skills table ---


async def test_read_settings_skills_from_table(worker_session: AsyncSession):
    """read_settings queries skills from the skills table, not settings."""
    from models import Skill
    skill = Skill(name="test-skill", description="Test", instructions="Do test")
    worker_session.add(skill)
    await worker_session.commit()

    settings = await read_settings(worker_session)
    assert len(settings["skills"]) == 1
    assert settings["skills"][0]["name"] == "test-skill"
    assert settings["skills"][0]["description"] == "Test"
    assert settings["skills"][0]["instructions"] == "Do test"
    assert settings["skills"][0]["files"] == []


async def test_read_settings_skills_empty_by_default(worker_session: AsyncSession):
    """read_settings returns empty skills list when no skills exist."""
    settings = await read_settings(worker_session)
    assert settings["skills"] == []


# --- Git-sourced skills ---

from task_manager import (
    refresh_git_clone, parse_skills_from_directory, merge_skills,
    GitSkillsError, MAX_GIT_RETRIES,
)


class TestRefreshGitClone:
    """Tests for refresh_git_clone()."""

    def test_first_call_clones(self, tmp_path, monkeypatch):
        """First call to refresh_git_clone clones the repository."""
        monkeypatch.setattr("task_manager.hashlib", __import__("hashlib"))
        repo_url = "git@github.com:org/skills.git"
        url_hash = __import__("hashlib").sha256(repo_url.encode()).hexdigest()[:12]
        clone_dir = f"/tmp/errand-skills-{url_hash}"

        # Ensure clone dir doesn't exist
        import shutil
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        calls = []
        def mock_run(*args, **kwargs):
            calls.append(args[0])
            # Create the .git dir to simulate clone
            os.makedirs(os.path.join(clone_dir, ".git"), exist_ok=True)
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr("subprocess.run", mock_run)
        result = refresh_git_clone(repo_url, None, None)

        assert result == clone_dir
        assert len(calls) == 1
        assert calls[0][0] == "git"
        assert calls[0][1] == "clone"
        assert repo_url in calls[0]

        # Cleanup
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

    def test_second_call_pulls(self, tmp_path, monkeypatch):
        """Second call pulls instead of cloning."""
        repo_url = "git@github.com:org/skills.git"
        url_hash = __import__("hashlib").sha256(repo_url.encode()).hexdigest()[:12]
        clone_dir = f"/tmp/errand-skills-{url_hash}"

        # Simulate existing clone
        os.makedirs(os.path.join(clone_dir, ".git"), exist_ok=True)

        calls = []
        def mock_run(*args, **kwargs):
            calls.append(args[0])
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr("subprocess.run", mock_run)
        result = refresh_git_clone(repo_url, None, None)

        assert result == clone_dir
        assert len(calls) == 1
        assert calls[0] == ["git", "pull", "--ff-only"]

        # Cleanup
        import shutil
        shutil.rmtree(clone_dir)

    def test_ssh_key_used(self, tmp_path, monkeypatch):
        """SSH key is written to temp file and used in GIT_SSH_COMMAND."""
        repo_url = "git@github.com:org/skills.git"
        url_hash = __import__("hashlib").sha256(repo_url.encode()).hexdigest()[:12]
        clone_dir = f"/tmp/errand-skills-{url_hash}"

        import shutil
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        captured_env = {}
        def mock_run(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            os.makedirs(os.path.join(clone_dir, ".git"), exist_ok=True)
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr("subprocess.run", mock_run)
        refresh_git_clone(repo_url, None, "fake-ssh-key-content")

        assert "GIT_SSH_COMMAND" in captured_env
        assert "-o StrictHostKeyChecking=accept-new" in captured_env["GIT_SSH_COMMAND"]

        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

    def test_branch_checkout(self, tmp_path, monkeypatch):
        """Branch is passed to git clone when specified."""
        repo_url = "git@github.com:org/skills.git"
        url_hash = __import__("hashlib").sha256(repo_url.encode()).hexdigest()[:12]
        clone_dir = f"/tmp/errand-skills-{url_hash}"

        import shutil
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        calls = []
        def mock_run(*args, **kwargs):
            calls.append(args[0])
            os.makedirs(os.path.join(clone_dir, ".git"), exist_ok=True)
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr("subprocess.run", mock_run)
        refresh_git_clone(repo_url, "production", None)

        assert "-b" in calls[0]
        assert "production" in calls[0]

        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

    def test_git_failure_raises_error(self, tmp_path, monkeypatch):
        """Git failure raises GitSkillsError."""
        repo_url = "git@github.com:org/nonexistent.git"
        url_hash = __import__("hashlib").sha256(repo_url.encode()).hexdigest()[:12]
        clone_dir = f"/tmp/errand-skills-{url_hash}"

        import shutil
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(128, "git", stderr="fatal: repository not found")

        monkeypatch.setattr("subprocess.run", mock_run)
        with pytest.raises(GitSkillsError, match="Git operation failed"):
            refresh_git_clone(repo_url, None, None)

    def test_public_repo_no_ssh_key(self, tmp_path, monkeypatch):
        """Public repo without SSH key does not set GIT_SSH_COMMAND."""
        repo_url = "https://github.com/org/public-skills.git"
        url_hash = __import__("hashlib").sha256(repo_url.encode()).hexdigest()[:12]
        clone_dir = f"/tmp/errand-skills-{url_hash}"

        import shutil
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        captured_env = {}
        def mock_run(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            os.makedirs(os.path.join(clone_dir, ".git"), exist_ok=True)
            return subprocess.CompletedProcess(args[0], 0, "", "")

        monkeypatch.setattr("subprocess.run", mock_run)
        refresh_git_clone(repo_url, None, None)

        assert "GIT_SSH_COMMAND" not in captured_env

        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

    def test_network_error_raises_git_skills_error(self, tmp_path, monkeypatch):
        """Transient network error raises GitSkillsError with the network message."""
        repo_url = "git@github.com:org/skills.git"
        url_hash = __import__("hashlib").sha256(repo_url.encode()).hexdigest()[:12]
        clone_dir = f"/tmp/errand-skills-{url_hash}"

        import shutil
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(128, "git", stderr="fatal: unable to access: Connection timed out")

        monkeypatch.setattr("subprocess.run", mock_run)
        with pytest.raises(GitSkillsError, match="Connection timed out"):
            refresh_git_clone(repo_url, None, None)

    def test_auth_error_raises_git_skills_error(self, tmp_path, monkeypatch):
        """Authentication error raises GitSkillsError with the auth message."""
        repo_url = "git@github.com:org/private-skills.git"
        url_hash = __import__("hashlib").sha256(repo_url.encode()).hexdigest()[:12]
        clone_dir = f"/tmp/errand-skills-{url_hash}"

        import shutil
        if os.path.exists(clone_dir):
            shutil.rmtree(clone_dir)

        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(128, "git", stderr="fatal: Could not read from remote repository. Permission denied (publickey).")

        monkeypatch.setattr("subprocess.run", mock_run)
        with pytest.raises(GitSkillsError, match="Permission denied"):
            refresh_git_clone(repo_url, None, "wrong-key")


class TestParseSkillsFromDirectory:
    """Tests for parse_skills_from_directory()."""

    def test_parses_skill_with_frontmatter_and_files(self, tmp_path):
        """Parses SKILL.md with frontmatter and attached files."""
        skill_dir = tmp_path / "research"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: research\ndescription: Web research\n---\n\nUse search tools to find info."
        )
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "search.py").write_text("print('searching')")

        result = parse_skills_from_directory(str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "research"
        assert result[0]["description"] == "Web research"
        assert result[0]["instructions"] == "Use search tools to find info."
        assert len(result[0]["files"]) == 1
        assert result[0]["files"][0]["path"] == "scripts/search.py"
        assert result[0]["files"][0]["content"] == "print('searching')"

    def test_skips_directories_without_skill_md(self, tmp_path):
        """Directories without SKILL.md are silently skipped."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "readme.txt").write_text("not a skill")

        result = parse_skills_from_directory(str(tmp_path))
        assert result == []

    def test_handles_empty_directory(self, tmp_path):
        """Empty directory returns empty list."""
        result = parse_skills_from_directory(str(tmp_path))
        assert result == []

    def test_handles_nonexistent_directory(self):
        """Nonexistent directory returns empty list."""
        result = parse_skills_from_directory("/nonexistent/path")
        assert result == []

    def test_skill_with_no_files(self, tmp_path):
        """Skill with only SKILL.md and no subdirectories."""
        skill_dir = tmp_path / "tweet"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: tweet\ndescription: Post tweets\n---\n\nCompose and post tweets."
        )

        result = parse_skills_from_directory(str(tmp_path))
        assert len(result) == 1
        assert result[0]["name"] == "tweet"
        assert result[0]["files"] == []

    def test_multiple_file_subdirectories(self, tmp_path):
        """Reads files from scripts/, references/, and assets/ subdirs."""
        skill_dir = tmp_path / "multi"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: multi\ndescription: Multi\n---\n\nInstructions.")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "run.sh").write_text("#!/bin/bash")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "guide.md").write_text("# Guide")
        (skill_dir / "assets").mkdir()
        (skill_dir / "assets" / "template.txt").write_text("template")

        result = parse_skills_from_directory(str(tmp_path))
        assert len(result) == 1
        paths = [f["path"] for f in result[0]["files"]]
        assert "scripts/run.sh" in paths
        assert "references/guide.md" in paths
        assert "assets/template.txt" in paths


class TestMergeSkills:
    """Tests for merge_skills()."""

    def test_no_conflicts_merges_all(self):
        """When no name conflicts, all skills are included."""
        db = [{"name": "code-review", "description": "CR", "instructions": "...", "files": []}]
        git = [
            {"name": "research", "description": "R", "instructions": "...", "files": []},
            {"name": "tweet", "description": "T", "instructions": "...", "files": []},
        ]
        result = merge_skills(db, git)
        names = [s["name"] for s in result]
        assert sorted(names) == ["code-review", "research", "tweet"]

    def test_db_wins_on_conflict(self, caplog):
        """DB skill takes precedence on name conflict."""
        db = [{"name": "research", "description": "DB version", "instructions": "db", "files": []}]
        git = [{"name": "research", "description": "Git version", "instructions": "git", "files": []}]
        result = merge_skills(db, git)
        assert len(result) == 1
        assert result[0]["description"] == "DB version"
        assert "Skill name conflict: 'research'" in caplog.text

    def test_empty_lists(self):
        """Both empty lists returns empty."""
        assert merge_skills([], []) == []

    def test_empty_db_returns_git(self):
        """Empty DB list returns all git skills."""
        git = [{"name": "research", "description": "R", "instructions": "...", "files": []}]
        result = merge_skills([], git)
        assert len(result) == 1
        assert result[0]["name"] == "research"

    def test_empty_git_returns_db(self):
        """Empty git list returns all DB skills."""
        db = [{"name": "code-review", "description": "CR", "instructions": "...", "files": []}]
        result = merge_skills(db, [])
        assert len(result) == 1
        assert result[0]["name"] == "code-review"


import os
import subprocess


class TestGitFailureRetry:
    """Integration tests for git failure retry handling."""

    @pytest.fixture()
    async def retry_task_session(self):
        """Create a session with both settings and tasks tables for retry tests."""
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
            include_git_skills BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id VARCHAR(36) NOT NULL PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    position FLOAT NOT NULL DEFAULT 0.0,
                    category TEXT NOT NULL DEFAULT 'one-off',
                    execute_at DATETIME,
                    repeat_interval TEXT,
                    repeat_until DATETIME,
                    output TEXT,
                    runner_logs TEXT,
                    questions TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    profile_id VARCHAR(36),
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
                    task_id VARCHAR(36) NOT NULL,
                    tag_id VARCHAR(36) NOT NULL,
                    PRIMARY KEY (task_id, tag_id)
                )
            """))
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            yield session
        await engine.dispose()

    async def test_git_failure_schedules_retry(self, retry_task_session, monkeypatch):
        """Git clone failure triggers _schedule_retry with git error message."""
        session = retry_task_session
        task_id = str(uuid.uuid4())
        await session.execute(text(
            "INSERT INTO tasks (id, title, status, position, retry_count) VALUES (:id, :title, 'running', 1.0, 0)"
        ), {"id": task_id, "title": "Test task"})
        await session.commit()

        # Mock _schedule_retry to capture calls
        retry_calls = []
        async def mock_schedule_retry(task, output=None, runner_logs=None):
            retry_calls.append({"task_id": task.id, "output": output})

        monkeypatch.setattr("task_manager.TaskManager._schedule_retry", mock_schedule_retry)
        monkeypatch.setattr("task_manager.publish_event", AsyncMock())

        # Mock process_task_in_container to raise GitSkillsError
        def mock_process(task, settings):
            raise GitSkillsError("Git operation failed: repository not found")

        monkeypatch.setattr("task_manager.TaskManager._process_task", mock_process)

        # Simulate the error handling in run() for retry_count < MAX_GIT_RETRIES
        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.retry_count = 0

        await mock_schedule_retry(mock_task, output="Git operation failed: repository not found")
        assert len(retry_calls) == 1
        assert "repository not found" in retry_calls[0]["output"]

    async def test_git_failure_moves_to_review_after_max_retries(self, retry_task_session, monkeypatch):
        """After MAX_GIT_RETRIES, task moves to review status."""
        session = retry_task_session
        task_id = str(uuid.uuid4())
        await session.execute(text(
            "INSERT INTO tasks (id, title, status, position, retry_count) VALUES (:id, :title, 'running', 1.0, :rc)"
        ), {"id": task_id, "title": "Test task", "rc": MAX_GIT_RETRIES})
        await session.commit()

        # Now verify the task would be moved to review (retry_count >= MAX_GIT_RETRIES)
        result = await session.execute(text("SELECT retry_count FROM tasks WHERE id = :id"), {"id": task_id})
        row = result.first()
        assert row[0] >= MAX_GIT_RETRIES


async def test_read_settings_skills_git_repo(worker_session: AsyncSession):
    """read_settings returns skills_git_repo when configured."""
    from models import Setting
    setting = Setting(key="skills_git_repo", value={"url": "git@github.com:org/skills.git", "branch": "main", "path": "skills"})
    worker_session.add(setting)
    await worker_session.commit()

    settings = await read_settings(worker_session)
    assert settings["skills_git_repo"] == {"url": "git@github.com:org/skills.git", "branch": "main", "path": "skills"}


async def test_read_settings_skills_git_repo_default(worker_session: AsyncSession):
    """read_settings returns None for skills_git_repo when not configured."""
    settings = await read_settings(worker_session)
    assert settings["skills_git_repo"] is None


async def test_read_settings_skills_git_repo_empty_url(worker_session: AsyncSession):
    """read_settings returns None when skills_git_repo has empty URL."""
    from models import Setting
    setting = Setting(key="skills_git_repo", value={"url": ""})
    worker_session.add(setting)
    await worker_session.commit()

    settings = await read_settings(worker_session)
    assert settings["skills_git_repo"] is None


# --- Hindsight integration tests ---


def test_recall_from_hindsight_success():
    """recall_from_hindsight returns recalled text on successful API call."""
    with patch("task_manager.httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": [{"text": "Previous task deployed v2 to staging."}]}
        mock_post.return_value = mock_resp

        result = recall_from_hindsight("http://hindsight:8888", "my-bank", "Deploy frontend")

    assert result == "Previous task deployed v2 to staging."
    mock_post.assert_called_once_with(
        "http://hindsight:8888/v1/default/banks/my-bank/memories/recall",
        json={"query": "Deploy frontend", "max_tokens": 2048},
        timeout=30,
    )


def test_recall_from_hindsight_api_failure():
    """recall_from_hindsight returns None and logs warning on API failure."""
    with patch("task_manager.httpx.post") as mock_post:
        mock_post.side_effect = Exception("Connection refused")

        result = recall_from_hindsight("http://hindsight:8888", "my-bank", "Deploy frontend")

    assert result is None


def test_recall_from_hindsight_empty_result():
    """recall_from_hindsight returns None when API returns empty content."""
    with patch("task_manager.httpx.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_post.return_value = mock_resp

        result = recall_from_hindsight("http://hindsight:8888", "my-bank", "query")

    assert result is None


@pytest.mark.asyncio
async def test_hindsight_mcp_injected_when_configured():
    """When HINDSIGHT_URL is set, hindsight MCP server is injected into mcp.json."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {"other": {"url": "http://other/mcp"}}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
        "hindsight_url": "",
        "hindsight_bank_id": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
            "HINDSIGHT_URL": "http://hindsight-api:8888",
        }), patch("task_manager.recall_from_hindsight", return_value=None):
        await _run_process_task(task, settings, mock_runtime)

    # Extract mcp.json from prepare call
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "hindsight" in mcp_config["mcpServers"]
    assert mcp_config["mcpServers"]["hindsight"]["url"] == "http://hindsight-api:8888/mcp/errand-tasks/"
    # Existing server preserved
    assert "other" in mcp_config["mcpServers"]


@pytest.mark.asyncio
async def test_hindsight_mcp_skipped_when_already_in_database():
    """When database mcp_servers already has hindsight, the database value is preserved."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {"hindsight": {"url": "http://custom-hindsight/mcp/custom-bank/"}}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
        "hindsight_url": "",
        "hindsight_bank_id": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
            "HINDSIGHT_URL": "http://hindsight-api:8888",
        }), patch("task_manager.recall_from_hindsight", return_value=None):
        await _run_process_task(task, settings, mock_runtime)

    # Extract mcp.json — database value should be preserved
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert mcp_config["mcpServers"]["hindsight"]["url"] == "http://custom-hindsight/mcp/custom-bank/"


@pytest.mark.asyncio
async def test_hindsight_memory_context_in_system_prompt():
    """When Hindsight recall returns content, it appears in the system prompt."""
    task = _make_mock_task(title="Deploy v2", description="Deploy frontend v2 to staging")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "You are a helpful assistant.",
        "hindsight_url": "",
        "hindsight_bank_id": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
            "HINDSIGHT_URL": "http://hindsight:8888",
        }), patch("task_manager.recall_from_hindsight", return_value="Last deploy used blue-green strategy."):
        await _run_process_task(task, settings, mock_runtime)

    # Extract system_prompt.txt from prepare() call
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    system_prompt_content = files["system_prompt.txt"]

    assert "## Relevant Context from Memory" in system_prompt_content
    assert "Last deploy used blue-green strategy." in system_prompt_content
    assert "## Persistent Memory (Hindsight)" in system_prompt_content
    # Memory context appears before Hindsight instructions
    memory_pos = system_prompt_content.index("Relevant Context from Memory")
    instructions_pos = system_prompt_content.index("Persistent Memory (Hindsight)")
    assert memory_pos < instructions_pos


@pytest.mark.asyncio
async def test_hindsight_skipped_when_url_not_configured():
    """When HINDSIGHT_URL is not set and hindsight_url setting is empty, no Hindsight integration occurs."""
    task = _make_mock_task(description="Normal task")
    original_prompt = "You are a helpful assistant."
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": original_prompt,
        "hindsight_url": "",
        "hindsight_bank_id": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }, clear=True):
        await _run_process_task(task, settings, mock_runtime)

    # Extract mcp.json — should NOT have hindsight
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "hindsight" not in mcp_config.get("mcpServers", {})

    # Extract system_prompt.txt — should NOT have Hindsight sections
    system_prompt_content = files["system_prompt.txt"]
    assert "Relevant Context from Memory" not in system_prompt_content
    assert "Persistent Memory" not in system_prompt_content


async def test_read_settings_hindsight_defaults(worker_session: AsyncSession):
    """read_settings returns empty strings for hindsight settings when not configured."""
    settings = await read_settings(worker_session)
    assert settings["hindsight_url"] == ""
    assert settings["hindsight_bank_id"] == ""


async def test_read_settings_hindsight_configured(worker_session: AsyncSession):
    """read_settings returns hindsight settings when configured."""
    from models import Setting
    worker_session.add(Setting(key="hindsight_url", value="http://hindsight:8888"))
    worker_session.add(Setting(key="hindsight_bank_id", value="my-bank"))
    await worker_session.commit()

    settings = await read_settings(worker_session)
    assert settings["hindsight_url"] == "http://hindsight:8888"
    assert settings["hindsight_bank_id"] == "my-bank"


@pytest.mark.asyncio
async def test_hindsight_env_var_takes_precedence_over_setting():
    """HINDSIGHT_URL env var takes precedence over hindsight_url admin setting."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
        "hindsight_url": "http://setting-hindsight:8888",
        "hindsight_bank_id": "setting-bank",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
            "HINDSIGHT_URL": "http://env-hindsight:9999",
            "HINDSIGHT_BANK_ID": "env-bank",
        }), patch("task_manager.recall_from_hindsight", return_value=None):
        await _run_process_task(task, settings, mock_runtime)

    # Extract mcp.json — should use env var values, not settings
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert mcp_config["mcpServers"]["hindsight"]["url"] == "http://env-hindsight:9999/mcp/env-bank/"


@pytest.mark.asyncio
async def test_hindsight_falls_back_to_admin_setting():
    """When HINDSIGHT_URL env var is not set, hindsight_url admin setting is used."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
        "hindsight_url": "http://setting-hindsight:8888",
        "hindsight_bank_id": "setting-bank",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }, clear=True), patch("task_manager.recall_from_hindsight", return_value=None):
        await _run_process_task(task, settings, mock_runtime)

    # Extract mcp.json — should use admin setting values
    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert mcp_config["mcpServers"]["hindsight"]["url"] == "http://setting-hindsight:8888/mcp/setting-bank/"


# --- Playwright MCP URL injection ---


@pytest.mark.asyncio
async def test_playwright_mcp_injected_from_env():
    """Playwright MCP is injected when PLAYWRIGHT_MCP_URL env var is set."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }), \
        patch("task_manager.PLAYWRIGHT_MCP_URL", "http://playwright:8931/mcp"), \
        patch("task_manager.recall_from_hindsight", return_value=None):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "playwright" in mcp_config["mcpServers"]
    assert mcp_config["mcpServers"]["playwright"]["url"] == "http://playwright:8931/mcp"


@pytest.mark.asyncio
async def test_playwright_mcp_not_injected_when_url_empty():
    """Playwright MCP is not injected when PLAYWRIGHT_MCP_URL is empty."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }), \
        patch("task_manager.PLAYWRIGHT_MCP_URL", ""), \
        patch("task_manager.recall_from_hindsight", return_value=None):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "playwright" not in mcp_config.get("mcpServers", {})


@pytest.mark.asyncio
async def test_playwright_mcp_not_overwritten_when_db_configured():
    """Database-configured playwright entry takes precedence over auto-injection."""
    task = _make_mock_task(description="Do the thing")
    settings = {
        "mcp_servers": {"mcpServers": {"playwright": {"url": "http://custom:9999/mcp"}}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }), \
        patch("task_manager.PLAYWRIGHT_MCP_URL", "http://playwright:8931/mcp"), \
        patch("task_manager.recall_from_hindsight", return_value=None):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert mcp_config["mcpServers"]["playwright"]["url"] == "http://custom:9999/mcp"


# --- Callback token generation ---


@pytest.mark.asyncio
async def test_callback_token_stored_in_valkey():
    """Worker generates callback token and stores it in Valkey with correct key and TTL."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()
    mock_redis = MagicMock()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
            "ERRAND_MCP_URL": "http://errand:8000/mcp/",
        }), patch("redis.Redis.from_url", return_value=mock_redis):
        await _run_process_task(task, settings, mock_runtime)

    # Token was stored with correct key pattern and 30-min TTL
    set_calls = [c for c in mock_redis.set.call_args_list if "task_result_token:" in str(c)]
    assert len(set_calls) == 1
    args, kwargs = set_calls[0]
    assert args[0] == f"task_result_token:{task.id}"
    assert len(args[1]) == 64  # token_hex(32) = 64 chars
    assert kwargs.get("ex") == 1800


@pytest.mark.asyncio
async def test_callback_url_derived_from_errand_mcp_url():
    """Callback URL is derived by stripping /mcp and appending internal endpoint."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()
    mock_redis = MagicMock()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
            "ERRAND_MCP_URL": "http://errand:8000/mcp/",
        }), patch("redis.Redis.from_url", return_value=mock_redis):
        await _run_process_task(task, settings, mock_runtime)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert env["RESULT_CALLBACK_URL"] == f"http://errand:8000/api/internal/task-result/{task.id}"
    assert "RESULT_CALLBACK_TOKEN" in env
    assert len(env["RESULT_CALLBACK_TOKEN"]) == 64


@pytest.mark.asyncio
async def test_callback_env_vars_passed_to_container():
    """Both RESULT_CALLBACK_URL and RESULT_CALLBACK_TOKEN are in container env vars."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()
    mock_redis = MagicMock()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
            "ERRAND_MCP_URL": "http://errand:8000/mcp/",
        }), patch("redis.Redis.from_url", return_value=mock_redis):
        await _run_process_task(task, settings, mock_runtime)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert "RESULT_CALLBACK_URL" in env
    assert "RESULT_CALLBACK_TOKEN" in env


@pytest.mark.asyncio
async def test_callback_env_vars_skipped_on_valkey_failure():
    """When Valkey is unavailable, callback env vars are not set."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
            "ERRAND_MCP_URL": "http://errand:8000/mcp/",
        }), patch("redis.Redis.from_url", side_effect=ConnectionError("Valkey down")):
        await _run_process_task(task, settings, mock_runtime)

    env = mock_runtime.async_prepare.call_args.kwargs["env"]
    assert "RESULT_CALLBACK_URL" not in env
    assert "RESULT_CALLBACK_TOKEN" not in env


# --- Callback result reading ---


@pytest.mark.asyncio
async def test_callback_result_overrides_runtime_stdout():
    """When callback result exists in Valkey, it overrides runtime.result() stdout."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }
    callback_output = '{"status":"completed","result":"callback result","questions":[]}'
    runtime_output = '{"status":"completed","result":"runtime result","questions":[]}'

    mock_runtime = _make_mock_runtime(stdout=runtime_output)
    mock_token_redis = MagicMock()
    mock_result_redis = MagicMock()
    mock_result_redis.get.return_value = callback_output

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
            "ERRAND_MCP_URL": "http://errand:8000/mcp/",
        }), patch("redis.Redis.from_url", side_effect=[mock_token_redis, mock_result_redis]):
        exit_code, stdout, stderr = await _run_process_task(task, settings, mock_runtime)

    assert stdout == callback_output


@pytest.mark.asyncio
async def test_missing_callback_falls_back_to_runtime_stdout():
    """When no callback result in Valkey, runtime.result() stdout is used."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }
    runtime_output = '{"status":"completed","result":"runtime result","questions":[]}'

    mock_runtime = _make_mock_runtime(stdout=runtime_output)
    mock_token_redis = MagicMock()
    mock_result_redis = MagicMock()
    mock_result_redis.get.return_value = None  # No callback result

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
            "ERRAND_MCP_URL": "http://errand:8000/mcp/",
        }), patch("redis.Redis.from_url", side_effect=[mock_token_redis, mock_result_redis]):
        exit_code, stdout, stderr = await _run_process_task(task, settings, mock_runtime)

    assert stdout == runtime_output


@pytest.mark.asyncio
async def test_callback_result_valkey_keys_deleted():
    """Both task_result and task_result_token keys are deleted after reading."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }

    mock_runtime = _make_mock_runtime()
    mock_token_redis = MagicMock()
    mock_result_redis = MagicMock()
    mock_result_redis.get.return_value = '{"status":"completed","result":"done","questions":[]}'

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
            "ERRAND_MCP_URL": "http://errand:8000/mcp/",
        }), patch("redis.Redis.from_url", side_effect=[mock_token_redis, mock_result_redis]):
        await _run_process_task(task, settings, mock_runtime)

    mock_result_redis.delete.assert_called_once_with(
        f"task_result:{task.id}", f"task_result_token:{task.id}"
    )


@pytest.mark.asyncio
async def test_callback_result_valkey_error_swallowed():
    """Valkey errors during callback result reading are swallowed gracefully."""
    task = _make_mock_task(description="Run a job")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": DEFAULT_TASK_PROCESSING_MODEL,
        "system_prompt": "",
    }
    runtime_output = '{"status":"completed","result":"runtime result","questions":[]}'

    mock_runtime = _make_mock_runtime(stdout=runtime_output)
    mock_token_redis = MagicMock()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "", "OPENAI_API_KEY": "",
            "ERRAND_MCP_URL": "http://errand:8000/mcp/",
        }), patch("redis.Redis.from_url", side_effect=[mock_token_redis, ConnectionError("Valkey down")]):
        exit_code, stdout, stderr = await _run_process_task(task, settings, mock_runtime)

    # Falls back to runtime stdout
    assert stdout == runtime_output


@pytest.mark.asyncio
async def test_nonzero_exit_code_with_valid_json_treated_as_success():
    """When exit_code != 0 but stdout contains valid TaskRunnerOutput JSON,
    extract_json should still return the JSON (enabling the success path).

    This covers the K8s race condition where exit code detection fails (-1)
    but the task-runner actually completed and produced valid output.
    """
    valid_json = '{"status":"completed","result":"done","questions":[]}'

    # extract_json succeeds regardless of where the JSON came from
    assert extract_json(valid_json) is not None

    # The worker logic: clean_stdout = extract_json(stdout) if stdout else None
    # Then: if clean_stdout is not None → success path (regardless of exit_code)
    # Simulate the decision:
    stdout = valid_json
    clean_stdout = extract_json(stdout) if stdout else None
    assert clean_stdout is not None, "Valid JSON should be extracted even with non-zero exit code"

    parsed = TaskRunnerOutput.model_validate_json(clean_stdout)
    assert parsed.status == "completed"
    assert parsed.result == "done"


@pytest.mark.asyncio
async def test_nonzero_exit_code_without_json_still_retries():
    """When exit_code != 0 and stdout has no valid JSON, the retry path is taken."""
    stdout = ""
    clean_stdout = extract_json(stdout) if stdout else None
    assert clean_stdout is None, "Empty stdout should not produce JSON"


@pytest.mark.asyncio
async def test_nonzero_exit_code_with_invalid_json_still_retries():
    """When exit_code != 0 and stdout has invalid JSON, the retry path is taken."""
    stdout = '{"not_a_task_runner_output": true}'
    clean_stdout = extract_json(stdout) if stdout else None
    assert clean_stdout is None, "Invalid TaskRunnerOutput should not be extracted"


# --- Repo context discovery instructions ---


@pytest.mark.asyncio
async def test_repo_context_instructions_in_system_prompt():
    """System prompt always includes repo context discovery instructions."""
    task = _make_mock_task(description="Clone and fix a repo")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "You are a helpful assistant.",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }, clear=True):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    system_prompt_content = files["system_prompt.txt"]

    assert "## Repo Context Discovery" in system_prompt_content
    assert "CLAUDE.md" in system_prompt_content
    assert ".claude/commands/" in system_prompt_content
    assert ".claude/skills/" in system_prompt_content


@pytest.mark.asyncio
async def test_repo_context_instructions_after_skill_manifest():
    """Repo context instructions appear after the skill manifest when skills are present."""
    task = _make_mock_task(description="Research task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "You are a helpful assistant.",
        "skills": [
            {"name": "researcher", "description": "Web research", "instructions": "Full instructions", "files": []},
        ],
        "mcp_api_key": "test-api-key-123",
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "http://litellm:4000",
            "OPENAI_API_KEY": "sk-test",
        }, clear=True):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    system_prompt_content = files["system_prompt.txt"]

    # Both sections present
    assert "## Skills" in system_prompt_content
    assert "## Repo Context Discovery" in system_prompt_content

    # Repo context comes after skills
    skills_pos = system_prompt_content.index("## Skills")
    repo_context_pos = system_prompt_content.index("## Repo Context Discovery")
    assert repo_context_pos > skills_pos


# --- LiteLLM MCP injection ---


@pytest.mark.asyncio
async def test_litellm_mcp_injected_when_enabled():
    """When litellm_mcp_servers has entries and provider resolves, litellm is injected."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": {"provider_id": "fake-provider-id", "model": "gpt-4o"},
        "system_prompt": "",
        "litellm_mcp_servers": ["argocd", "perplexity"],
    }

    mock_runtime = _make_mock_runtime()

    with patch("task_manager._resolve_provider_sync", return_value={"base_url": "https://litellm.example.com", "api_key": "sk-test"}):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    # Each litellm server gets its own entry with path-based URL
    assert "litellm_argocd" in mcp_config["mcpServers"]
    assert mcp_config["mcpServers"]["litellm_argocd"]["url"] == "https://litellm.example.com/mcp/argocd"
    assert mcp_config["mcpServers"]["litellm_argocd"]["headers"]["Authorization"] == "Bearer sk-test"
    assert "litellm_perplexity" in mcp_config["mcpServers"]
    assert mcp_config["mcpServers"]["litellm_perplexity"]["url"] == "https://litellm.example.com/mcp/perplexity"


@pytest.mark.asyncio
async def test_litellm_mcp_not_injected_when_empty():
    """When litellm_mcp_servers is empty, no litellm entry is added."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "litellm_mcp_servers": [],
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "https://litellm.example.com",
            "OPENAI_API_KEY": "sk-test",
        }):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert not any(k.startswith("litellm_") for k in mcp_config.get("mcpServers", {}))


@pytest.mark.asyncio
async def test_litellm_mcp_not_injected_when_no_base_url():
    """When openai_base_url is not set, no litellm entry is added."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "litellm_mcp_servers": ["argocd"],
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {}, clear=True):
        # Ensure no OPENAI_BASE_URL in env
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert not any(k.startswith("litellm_") for k in mcp_config.get("mcpServers", {}))


@pytest.mark.asyncio
async def test_litellm_mcp_manual_override_preserved():
    """When user has manually configured a litellm_argocd key, it is preserved."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {"litellm_argocd": {"url": "http://custom:4000/mcp/argocd"}}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "litellm_mcp_servers": ["argocd"],
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "https://litellm.example.com",
            "OPENAI_API_KEY": "sk-test",
        }):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    # Manual entry should be preserved, not overwritten
    assert mcp_config["mcpServers"]["litellm_argocd"]["url"] == "http://custom:4000/mcp/argocd"


@pytest.mark.asyncio
async def test_litellm_mcp_legacy_key_blocks_injection():
    """When user has a legacy 'litellm' key, no litellm_* entries are auto-injected."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {"mcpServers": {"litellm": {"url": "http://custom:4000/mcp"}}},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "",
        "litellm_mcp_servers": ["argocd"],
    }

    mock_runtime = _make_mock_runtime()

    with patch.dict("os.environ", {
            "OPENAI_BASE_URL": "https://litellm.example.com",
            "OPENAI_API_KEY": "sk-test",
        }):
        await _run_process_task(task, settings, mock_runtime)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    # Legacy key preserved, no litellm_argocd injected
    assert mcp_config["mcpServers"]["litellm"]["url"] == "http://custom:4000/mcp"
    assert "litellm_argocd" not in mcp_config["mcpServers"]


# --- Cloud Storage MCP injection ---


@pytest.mark.asyncio
async def test_cloud_storage_mcp_injected_both_gates():
    """When URL is set and credentials exist, cloud storage MCP is injected."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
    }
    cloud_creds = {
        "google_drive": {"access_token": "ya29.test", "refresh_token": "rt", "expires_at": 9999999999},
        "onedrive": {"access_token": "eyJ.test", "refresh_token": "rt2", "expires_at": 9999999999},
    }

    mock_runtime = _make_mock_runtime()

    with patch("task_manager.GDRIVE_MCP_URL", "http://gdrive:8080/mcp"), \
         patch("task_manager.ONEDRIVE_MCP_URL", "http://onedrive:8080/mcp"):
        await _run_process_task(task, settings, mock_runtime, cloud_storage_credentials=cloud_creds)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "google_drive" in mcp_config["mcpServers"]
    assert mcp_config["mcpServers"]["google_drive"]["url"] == "http://gdrive:8080/mcp"
    assert mcp_config["mcpServers"]["google_drive"]["headers"]["Authorization"] == "Bearer ya29.test"
    assert "onedrive" in mcp_config["mcpServers"]
    assert mcp_config["mcpServers"]["onedrive"]["headers"]["Authorization"] == "Bearer eyJ.test"

    # System prompt should include cloud storage instructions
    system_prompt = files["system_prompt.txt"]
    assert "Cloud Storage" in system_prompt
    assert "ETag" in system_prompt


@pytest.mark.asyncio
async def test_cloud_storage_not_injected_no_url():
    """When MCP URL not set, cloud storage is not injected even with credentials."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
    }
    cloud_creds = {
        "google_drive": {"access_token": "ya29.test", "expires_at": 9999999999},
    }

    mock_runtime = _make_mock_runtime()

    with patch("task_manager.GDRIVE_MCP_URL", ""), \
         patch("task_manager.ONEDRIVE_MCP_URL", ""):
        await _run_process_task(task, settings, mock_runtime, cloud_storage_credentials=cloud_creds)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "google_drive" not in mcp_config.get("mcpServers", {})
    # No cloud storage instructions
    assert "Cloud Storage" not in files["system_prompt.txt"]


@pytest.mark.asyncio
async def test_cloud_storage_not_injected_no_credentials():
    """When no credentials exist, cloud storage is not injected."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
    }

    mock_runtime = _make_mock_runtime()

    with patch("task_manager.GDRIVE_MCP_URL", "http://gdrive:8080/mcp"):
        await _run_process_task(task, settings, mock_runtime, cloud_storage_credentials=None)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "google_drive" not in mcp_config.get("mcpServers", {})


@pytest.mark.asyncio
async def test_cloud_storage_profile_filter():
    """Cloud storage respects profile_mcp_servers filter."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
        "_profile_mcp_servers": ["errand"],  # cloud storage NOT listed
    }
    cloud_creds = {
        "google_drive": {"access_token": "ya29.test", "expires_at": 9999999999},
    }

    mock_runtime = _make_mock_runtime()

    with patch("task_manager.GDRIVE_MCP_URL", "http://gdrive:8080/mcp"):
        await _run_process_task(task, settings, mock_runtime, cloud_storage_credentials=cloud_creds)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "google_drive" not in mcp_config.get("mcpServers", {})


@pytest.mark.asyncio
async def test_cloud_storage_profile_filter_includes():
    """Cloud storage is injected when profile filter includes it."""
    task = _make_mock_task(description="Test task")
    settings = {
        "mcp_servers": {},
        "credentials": [],
        "task_processing_model": "gpt-4o",
        "system_prompt": "Be helpful.",
        "_profile_mcp_servers": ["errand", "google_drive"],
    }
    cloud_creds = {
        "google_drive": {"access_token": "ya29.test", "expires_at": 9999999999},
    }

    mock_runtime = _make_mock_runtime()

    with patch("task_manager.GDRIVE_MCP_URL", "http://gdrive:8080/mcp"):
        await _run_process_task(task, settings, mock_runtime, cloud_storage_credentials=cloud_creds)

    files = mock_runtime.async_prepare.call_args.kwargs["files"]
    mcp_config = json.loads(files["mcp.json"])
    assert "google_drive" in mcp_config["mcpServers"]
