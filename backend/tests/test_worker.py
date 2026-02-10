"""Worker unit tests: settings reader, output truncation, task_to_dict."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import Setting, Task

# Import worker functions under test
from worker import read_settings, truncate_output, _task_to_dict, put_archive


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


def test_task_to_dict_includes_output():
    """_task_to_dict includes the output field."""
    task = MagicMock(spec=Task)
    task.id = "abc-123"
    task.title = "Test task"
    task.status = "review"
    task.output = "Container output here"
    task.created_at = MagicMock()
    task.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    task.updated_at = MagicMock()
    task.updated_at.isoformat.return_value = "2026-01-01T00:01:00"

    result = _task_to_dict(task)
    assert result["output"] == "Container output here"
    assert result["status"] == "review"


def test_task_to_dict_null_output():
    """_task_to_dict handles None output."""
    task = MagicMock(spec=Task)
    task.id = "abc-123"
    task.title = "Test task"
    task.status = "pending"
    task.output = None
    task.created_at = MagicMock()
    task.created_at.isoformat.return_value = "2026-01-01T00:00:00"
    task.updated_at = MagicMock()
    task.updated_at.isoformat.return_value = "2026-01-01T00:01:00"

    result = _task_to_dict(task)
    assert result["output"] is None


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

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def test_read_settings_defaults(db_session):
    """When no settings exist, returns empty defaults."""
    mcp_servers, credentials = await read_settings(db_session)
    assert mcp_servers == {}
    assert credentials == []


async def test_read_settings_with_mcp(db_session):
    """Reads mcp_servers from settings table."""
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "mcp_servers", "value": json.dumps({"servers": [{"name": "test"}]})},
    )
    await db_session.commit()

    mcp_servers, credentials = await read_settings(db_session)
    assert mcp_servers == {"servers": [{"name": "test"}]}
    assert credentials == []


async def test_read_settings_with_credentials(db_session):
    """Reads credentials from settings table."""
    creds = [{"key": "API_KEY", "value": "secret123"}]
    await db_session.execute(
        text("INSERT INTO settings (key, value) VALUES (:key, :value)"),
        {"key": "credentials", "value": json.dumps(creds)},
    )
    await db_session.commit()

    mcp_servers, credentials = await read_settings(db_session)
    assert mcp_servers == {}
    assert credentials == [{"key": "API_KEY", "value": "secret123"}]
