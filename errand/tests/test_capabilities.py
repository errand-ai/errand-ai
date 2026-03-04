"""Tests for capability detection."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import capabilities as cap_module

_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


@pytest.fixture()
async def cap_db():
    """Set up an in-memory DB for capability tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_SETTINGS_TABLE_SQL))

    test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    import database
    original = database.async_session
    database.async_session = test_session

    yield test_session

    database.async_session = original
    await engine.dispose()


# --- Version tests ---


def test_get_server_version():
    """Should read version from VERSION file."""
    version = cap_module.get_server_version()
    # The real VERSION file should exist and return a valid version
    assert version != "unknown"
    assert "." in version  # semver-like


def test_get_server_version_missing():
    """Should return 'unknown' when VERSION file is missing."""
    with patch.object(cap_module, '_VERSION_PATHS', [Path("/nonexistent/VERSION")]):
        assert cap_module.get_server_version() == "unknown"


# --- Capability detection tests ---


@pytest.mark.asyncio
async def test_capabilities_minimal(cap_db):
    """Minimal capabilities when no optional features are configured."""
    capabilities = await cap_module.get_capabilities()
    assert "tasks" in capabilities
    assert "settings" in capabilities
    assert "mcp-servers" in capabilities
    assert "task-profiles" in capabilities
    assert "platforms" in capabilities
    # Optional capabilities should NOT be present
    assert "voice-input" not in capabilities
    assert "litellm-mcp" not in capabilities


@pytest.mark.asyncio
async def test_capabilities_with_voice_input(cap_db):
    """voice-input capability present when transcription_model is set."""
    async with cap_db() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('transcription_model', :val)"),
            {"val": json.dumps("whisper-1")},
        )
        await session.commit()

    capabilities = await cap_module.get_capabilities()
    assert "voice-input" in capabilities


@pytest.mark.asyncio
async def test_capabilities_with_litellm_mcp(cap_db):
    """litellm-mcp capability present when LiteLLM MCP servers are configured."""
    async with cap_db() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('litellm_mcp_servers', :val)"),
            {"val": json.dumps(["server1", "server2"])},
        )
        await session.commit()

    capabilities = await cap_module.get_capabilities()
    assert "litellm-mcp" in capabilities


@pytest.mark.asyncio
async def test_capabilities_full_set(cap_db):
    """Full capability set when all optional features are configured."""
    async with cap_db() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('transcription_model', :val)"),
            {"val": json.dumps("whisper-1")},
        )
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('litellm_mcp_servers', :val)"),
            {"val": json.dumps(["server1"])},
        )
        await session.commit()

    capabilities = await cap_module.get_capabilities()
    assert "voice-input" in capabilities
    assert "litellm-mcp" in capabilities
    # All always-present capabilities
    for cap in ["tasks", "settings", "mcp-servers", "task-profiles", "platforms"]:
        assert cap in capabilities


@pytest.mark.asyncio
async def test_capabilities_empty_litellm_list(cap_db):
    """Empty litellm_mcp_servers list should not add litellm-mcp capability."""
    async with cap_db() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('litellm_mcp_servers', :val)"),
            {"val": json.dumps([])},
        )
        await session.commit()

    capabilities = await cap_module.get_capabilities()
    assert "litellm-mcp" not in capabilities
