"""Tests for the settings registry module."""
import os
from unittest.mock import patch

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from settings_registry import EXCLUDED_KEYS, mask_sensitive_value, resolve_settings
from tests.conftest import _create_tables


# --- mask_sensitive_value ---


def test_mask_empty():
    assert mask_sensitive_value("") == "****"


def test_mask_short():
    assert mask_sensitive_value("abc") == "****"


def test_mask_exactly_four():
    assert mask_sensitive_value("abcd") == "****"


def test_mask_long():
    assert mask_sensitive_value("sk-12345678") == "sk-1****"


# --- resolve_settings ---


async def test_resolve_defaults():
    """Without DB or env, all keys should return defaults."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await resolve_settings(session)

    assert "system_prompt" in result
    assert result["system_prompt"]["value"] == ""
    assert result["system_prompt"]["source"] == "default"
    assert result["system_prompt"]["sensitive"] is False
    assert result["system_prompt"]["readonly"] is False

    assert result["llm_model"]["value"] == "claude-haiku-4-5-20251001"
    assert result["llm_model"]["source"] == "default"

    await engine.dispose()


async def test_resolve_db_overrides_default():
    """DB values should override defaults."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Insert a setting into DB
    async with session_factory() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('system_prompt', '\"custom prompt\"')")
        )
        await session.commit()

    async with session_factory() as session:
        result = await resolve_settings(session)

    assert result["system_prompt"]["value"] == "custom prompt"
    assert result["system_prompt"]["source"] == "database"
    assert result["system_prompt"]["readonly"] is False

    await engine.dispose()


async def test_resolve_env_overrides_db():
    """Env vars should override DB values and be marked readonly."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Insert a DB value
    async with session_factory() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('openai_base_url', '\"http://db-url\"')")
        )
        await session.commit()

    with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://env-url"}):
        async with session_factory() as session:
            result = await resolve_settings(session)

    assert result["openai_base_url"]["value"] == "http://env-url"
    assert result["openai_base_url"]["source"] == "env"
    assert result["openai_base_url"]["readonly"] is True

    await engine.dispose()


async def test_sensitive_env_values_masked():
    """Sensitive env-sourced values should be masked."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-1234567890abcdef"}):
        async with session_factory() as session:
            result = await resolve_settings(session)

    assert result["openai_api_key"]["value"] == "sk-1****"
    assert result["openai_api_key"]["sensitive"] is True
    assert result["openai_api_key"]["readonly"] is True

    await engine.dispose()


async def test_excluded_keys_not_in_result():
    """EXCLUDED_KEYS should not appear in resolved settings."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await resolve_settings(session)

    for key in EXCLUDED_KEYS:
        assert key not in result

    await engine.dispose()


# --- API integration: PUT /api/settings ignores readonly ---


async def test_put_settings_ignores_readonly_env_keys(admin_client: AsyncClient):
    """PUT /api/settings should silently ignore env-sourced readonly keys."""
    with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://env-value"}):
        resp = await admin_client.put(
            "/api/settings",
            json={"openai_base_url": "http://attempt-override", "system_prompt": "new prompt"},
        )
    assert resp.status_code == 200
    data = resp.json()
    # system_prompt should be updated
    assert data["system_prompt"]["value"] == "new prompt"
    assert data["system_prompt"]["source"] == "database"


async def test_put_settings_excludes_jwt_signing_secret(admin_client: AsyncClient):
    """PUT /api/settings should not allow writing jwt_signing_secret."""
    resp = await admin_client.put(
        "/api/settings",
        json={"jwt_signing_secret": "stolen-secret", "system_prompt": "ok"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "jwt_signing_secret" not in data
