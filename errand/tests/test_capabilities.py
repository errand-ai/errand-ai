"""Tests for capability detection."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import capabilities as cap_module

# Raw DDL (Postgres-specific column types like JSONB can't be rendered on
# SQLite via Base.metadata). get_capabilities() reads both tables.
_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

_LLM_PROVIDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS llm_providers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    provider_type TEXT DEFAULT 'unknown' NOT NULL,
    is_default INTEGER DEFAULT 0 NOT NULL,
    source TEXT DEFAULT 'database' NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""

# cloud_storage / google_workspace detection queries platform_credentials
# (via integration_routes._provider_available + a connection existence check).
_PLATFORM_CREDENTIALS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS platform_credentials (
    platform_id TEXT NOT NULL PRIMARY KEY,
    encrypted_data TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'disconnected',
    last_verified_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
)
"""


@pytest.fixture()
async def cap_db():
    """Set up an in-memory DB for capability tests.

    Creates the ``settings`` and ``llm_providers`` tables because
    ``get_capabilities()`` queries both (LiteLLM proxy detection).
    """
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_SETTINGS_TABLE_SQL))
        await conn.execute(text(_LLM_PROVIDERS_TABLE_SQL))
        await conn.execute(text(_PLATFORM_CREDENTIALS_TABLE_SQL))

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
async def test_capabilities_always_on(cap_db, monkeypatch):
    """Always-on keys are present (snake_case for Wave 1/2); conditionals absent."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    capabilities = await cap_module.get_capabilities()

    for key in [
        "system_prompt",
        "mcp_servers",
        "skills_git_repo",
        "task_management",
        "telemetry",
        "tasks",
        "settings",
        "task-profiles",
        "platforms",
    ]:
        assert key in capabilities
    # Wave 1 cards gate on snake_case — the legacy kebab spellings are gone.
    assert "mcp-servers" not in capabilities
    assert "litellm-mcp" not in capabilities
    # Conditional keys should NOT be present with no config.
    assert "voice-input" not in capabilities
    assert "litellm_mcp" not in capabilities
    assert "google_workspace" not in capabilities


@pytest.mark.asyncio
async def test_capabilities_wave_2_always_on(cap_db, monkeypatch):
    """Wave 2 always-on card keys are advertised (snake_case for the card library)."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    capabilities = await cap_module.get_capabilities()

    for key in ["llm_providers", "llm_models", "platforms", "task_profiles"]:
        assert key in capabilities


@pytest.mark.asyncio
async def test_google_workspace_present_when_oauth_configured(cap_db, monkeypatch):
    """google_workspace present when Google OAuth client credentials are set."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")

    capabilities = await cap_module.get_capabilities()
    assert "google_workspace" in capabilities


@pytest.mark.asyncio
async def test_google_workspace_absent_when_credentials_partial(cap_db, monkeypatch):
    """google_workspace absent unless BOTH client id and secret are configured."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)

    capabilities = await cap_module.get_capabilities()
    assert "google_workspace" not in capabilities


@pytest.mark.asyncio
async def test_cloud_storage_and_google_workspace_via_cloud_proxy(cap_db, monkeypatch):
    """When connected to errand-cloud, cloud_storage and google_workspace are
    advertised via the OAuth proxy even without local OAuth client credentials."""
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("ONEDRIVE_MCP_URL", "https://onedrive.example/mcp")

    # A connected `cloud` platform credential means the errand-cloud OAuth proxy
    # is available.
    async with cap_db() as session:
        await session.execute(
            text(
                "INSERT INTO platform_credentials (platform_id, encrypted_data, status) "
                "VALUES ('cloud', 'x', 'connected')"
            )
        )
        await session.commit()

    capabilities = await cap_module.get_capabilities()
    assert "cloud_storage" in capabilities
    assert "google_workspace" in capabilities


@pytest.mark.asyncio
async def test_cloud_storage_absent_without_creds_or_cloud(cap_db, monkeypatch):
    """cloud_storage is NOT advertised when OneDrive has an MCP URL but there is
    no local Microsoft credential and no connected cloud proxy."""
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("ONEDRIVE_MCP_URL", "https://onedrive.example/mcp")

    capabilities = await cap_module.get_capabilities()
    assert "cloud_storage" not in capabilities


@pytest.mark.asyncio
async def test_cloud_storage_not_advertised_for_orphaned_credential_without_mcp_url(cap_db, monkeypatch):
    """A lingering OneDrive credential does NOT advertise cloud_storage when the
    provider's baseline requirement (ONEDRIVE_MCP_URL) is absent — the provider
    can no longer actually serve, so the card must not appear."""
    monkeypatch.delenv("MICROSOFT_CLIENT_ID", raising=False)
    monkeypatch.delenv("MICROSOFT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("ONEDRIVE_MCP_URL", raising=False)

    async with cap_db() as session:
        await session.execute(
            text(
                "INSERT INTO platform_credentials (platform_id, encrypted_data, status) "
                "VALUES ('onedrive', 'x', 'connected')"
            )
        )
        await session.commit()

    capabilities = await cap_module.get_capabilities()
    assert "cloud_storage" not in capabilities


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
async def test_litellm_mcp_present_when_proxy_env_set(cap_db, monkeypatch):
    """litellm_mcp present when a LiteLLM proxy is detected (legacy env var)."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://litellm.example")

    capabilities = await cap_module.get_capabilities()
    assert "litellm_mcp" in capabilities


@pytest.mark.asyncio
async def test_litellm_mcp_present_when_provider_row_exists(cap_db, monkeypatch):
    """litellm_mcp present when a `litellm` LLM provider row exists."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    from models import LlmProvider

    async with cap_db() as session:
        session.add(
            LlmProvider(
                name="lite",
                provider_type="litellm",
                base_url="https://litellm.example",
                api_key_encrypted="x",
                is_default=False,
                source="database",
            )
        )
        await session.commit()

    capabilities = await cap_module.get_capabilities()
    assert "litellm_mcp" in capabilities
