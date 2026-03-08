"""Tests for LLM provider management."""

import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llm_providers import (
    encrypt_api_key,
    decrypt_api_key,
    probe_provider_type,
    get_client_for_provider,
    evict_client,
    _clear_model_settings_for_provider,
    resolve_model_setting,
    scan_env_providers,
    _clients,
)
from models import LlmProvider, Setting


# --- Encryption helpers ---


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Set CREDENTIAL_ENCRYPTION_KEY for all tests."""
    # Fernet key must be 32 url-safe base64-encoded bytes
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "_26HOOIDUcxDH7fkoqI39DZulVPVK-hZe5THhiVLxIs=")


def test_encrypt_decrypt_api_key():
    original = "sk-test-key-12345"
    encrypted = encrypt_api_key(original)
    assert encrypted != original
    decrypted = decrypt_api_key(encrypted)
    assert decrypted == original


# --- Provider type probing ---


@pytest.mark.asyncio
async def test_probe_litellm():
    """Detect LiteLLM when /model/info responds with data array."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"model_name": "gpt-4"}]}

    with patch("llm_providers.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = instance
        result = await probe_provider_type("https://litellm.example.com/v1", "sk-key")
        assert result == "litellm"


@pytest.mark.asyncio
async def test_probe_openai_compatible():
    """Detect OpenAI-compatible when /models responds but /model/info doesn't."""
    litellm_resp = MagicMock()
    litellm_resp.status_code = 404

    openai_resp = MagicMock()
    openai_resp.status_code = 200
    openai_resp.json.return_value = {"data": [{"id": "gpt-4"}]}

    call_count = 0

    async def mock_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "model/info" in url:
            return litellm_resp
        return openai_resp

    with patch("llm_providers.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.get = mock_get
        MockClient.return_value = instance
        result = await probe_provider_type("https://api.openai.com/v1", "sk-key")
        assert result == "openai_compatible"


@pytest.mark.asyncio
async def test_probe_unknown():
    """Return unknown when neither endpoint responds."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("llm_providers.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.get = AsyncMock(return_value=mock_resp)
        MockClient.return_value = instance
        result = await probe_provider_type("https://unknown.example.com", "sk-key")
        assert result == "unknown"


# --- Provider CRUD API endpoints ---


async def _create_test_provider(admin_client: AsyncClient, name: str = "test-provider") -> dict:
    """Helper to create a provider via API with probing mocked."""
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="openai_compatible"):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": name,
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-key",
        })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_provider(admin_client: AsyncClient):
    provider = await _create_test_provider(admin_client)
    assert provider["name"] == "test-provider"
    assert provider["provider_type"] == "openai_compatible"
    assert provider["source"] == "database"
    assert provider["is_default"] is True  # first provider becomes default
    assert "****" in provider["api_key"]


async def test_create_provider_duplicate_name(admin_client: AsyncClient):
    await _create_test_provider(admin_client, "dupe")
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="unknown"):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": "dupe",
            "base_url": "https://other.example.com/v1",
            "api_key": "sk-other",
        })
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


async def test_list_providers(admin_client: AsyncClient):
    await _create_test_provider(admin_client, "provider-a")
    await _create_test_provider(admin_client, "provider-b")
    resp = await admin_client.get("/api/llm/providers")
    assert resp.status_code == 200
    providers = resp.json()
    assert len(providers) == 2
    # Default first
    assert providers[0]["is_default"] is True


async def test_update_provider(admin_client: AsyncClient):
    provider = await _create_test_provider(admin_client)
    resp = await admin_client.put(f"/api/llm/providers/{provider['id']}", json={"name": "updated-name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "updated-name"


async def test_update_provider_re_probes_on_url_change(admin_client: AsyncClient):
    provider = await _create_test_provider(admin_client)
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="litellm"):
        resp = await admin_client.put(f"/api/llm/providers/{provider['id']}", json={
            "base_url": "https://litellm.example.com/v1",
        })
    assert resp.status_code == 200
    assert resp.json()["provider_type"] == "litellm"


async def test_delete_provider(admin_client: AsyncClient):
    p1 = await _create_test_provider(admin_client, "default-prov")
    p2 = await _create_test_provider(admin_client, "other-prov")
    # Can delete non-default
    resp = await admin_client.delete(f"/api/llm/providers/{p2['id']}")
    assert resp.status_code == 204


async def test_delete_default_provider_rejected(admin_client: AsyncClient):
    provider = await _create_test_provider(admin_client)
    resp = await admin_client.delete(f"/api/llm/providers/{provider['id']}")
    assert resp.status_code == 409
    assert "default" in resp.json()["detail"].lower()


async def test_set_default_provider(admin_client: AsyncClient):
    p1 = await _create_test_provider(admin_client, "first")
    p2 = await _create_test_provider(admin_client, "second")
    assert p1["is_default"] is True
    resp = await admin_client.put(f"/api/llm/providers/{p2['id']}/default")
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True
    # Verify first is no longer default
    list_resp = await admin_client.get("/api/llm/providers")
    providers = list_resp.json()
    first = next(p for p in providers if p["id"] == p1["id"])
    assert first["is_default"] is False


async def test_non_admin_rejected(client: AsyncClient):
    resp = await client.get("/api/llm/providers")
    assert resp.status_code == 403


# --- Client pool ---


@pytest.mark.asyncio
async def test_client_pool_eviction():
    """Test that evict_client removes cached client."""
    test_id = uuid.uuid4()
    _clients[test_id] = MagicMock()
    assert test_id in _clients
    evict_client(test_id)
    assert test_id not in _clients


# --- Provider deletion cascade ---


async def test_delete_provider_clears_model_settings(admin_client: AsyncClient):
    p1 = await _create_test_provider(admin_client, "main-prov")
    p2 = await _create_test_provider(admin_client, "secondary")

    # Set llm_model to reference secondary provider
    await admin_client.put("/api/settings", json={
        "llm_model": {"provider_id": p2["id"], "model": "gpt-4"},
    })

    # Delete secondary provider
    resp = await admin_client.delete(f"/api/llm/providers/{p2['id']}")
    assert resp.status_code == 204

    # Verify llm_model was cleared
    settings_resp = await admin_client.get("/api/settings")
    llm_model = settings_resp.json()["llm_model"]["value"]
    assert llm_model.get("provider_id") is None or llm_model.get("model") == ""


# --- Per-provider model listing ---


async def test_list_provider_models_unknown_returns_404(admin_client: AsyncClient):
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="unknown"):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": "unknown-prov",
            "base_url": "https://unknown.example.com",
            "api_key": "sk-key",
        })
    provider = resp.json()
    resp = await admin_client.get(f"/api/llm/providers/{provider['id']}/models")
    assert resp.status_code == 404


async def test_list_provider_models_openai_compatible(admin_client: AsyncClient):
    provider = await _create_test_provider(admin_client)

    mock_model = MagicMock()
    mock_model.id = "gpt-4"
    mock_models = MagicMock()
    mock_models.data = [mock_model]

    with patch("llm_providers.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=mock_models)
        MockOpenAI.return_value = mock_client
        # Clear cached clients to force new creation
        _clients.clear()
        resp = await admin_client.get(f"/api/llm/providers/{provider['id']}/models")

    assert resp.status_code == 200
    assert resp.json() == ["gpt-4"]


# --- Env var scanning ---


@pytest.mark.asyncio
async def test_scan_env_providers(monkeypatch):
    """Test env var scanning creates providers."""
    monkeypatch.setenv("LLM_PROVIDER_0_NAME", "litellm")
    monkeypatch.setenv("LLM_PROVIDER_0_BASE_URL", "https://litellm.example.com/v1")
    monkeypatch.setenv("LLM_PROVIDER_0_API_KEY", "sk-test")

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        from tests.conftest import _LLM_PROVIDERS_TABLE_SQL, _SETTINGS_TABLE_SQL
        await conn.execute(text(_LLM_PROVIDERS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch("llm_providers.probe_provider_type", new_callable=AsyncMock, return_value="litellm"):
        async with session_maker() as session:
            await scan_env_providers(session)

    async with session_maker() as session:
        from sqlalchemy import select
        result = await session.execute(select(LlmProvider))
        providers = result.scalars().all()
        assert len(providers) == 1
        assert providers[0].name == "litellm"
        assert providers[0].source == "env"
        assert providers[0].is_default is True

    await engine.dispose()


# --- Worker provider resolution ---


@pytest.mark.asyncio
async def test_resolve_model_setting_valid():
    """Test resolving a model setting with valid provider."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        from tests.conftest import _LLM_PROVIDERS_TABLE_SQL, _SETTINGS_TABLE_SQL
        await conn.execute(text(_LLM_PROVIDERS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    provider_id = uuid.uuid4()
    async with session_maker() as session:
        provider = LlmProvider(
            id=provider_id,
            name="test-prov",
            base_url="https://test.example.com/v1",
            api_key_encrypted=encrypt_api_key("sk-test"),
            provider_type="openai_compatible",
            is_default=True,
            source="database",
        )
        session.add(provider)
        setting = Setting(
            key="llm_model",
            value={"provider_id": str(provider_id), "model": "gpt-4"},
        )
        session.add(setting)
        await session.commit()

    _clients.clear()
    async with session_maker() as session:
        client, model = await resolve_model_setting(session, "llm_model")
        assert client is not None
        assert model == "gpt-4"

    _clients.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_model_setting_empty():
    """Test resolving an empty model setting returns None."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        from tests.conftest import _LLM_PROVIDERS_TABLE_SQL, _SETTINGS_TABLE_SQL
        await conn.execute(text(_LLM_PROVIDERS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        client, model = await resolve_model_setting(session, "llm_model")
        assert client is None
        assert model is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_model_setting_missing_provider():
    """Test resolving a model setting with deleted provider returns None."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        from tests.conftest import _LLM_PROVIDERS_TABLE_SQL, _SETTINGS_TABLE_SQL
        await conn.execute(text(_LLM_PROVIDERS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        setting = Setting(
            key="llm_model",
            value={"provider_id": str(uuid.uuid4()), "model": "gpt-4"},
        )
        session.add(setting)
        await session.commit()

    async with session_maker() as session:
        client, model = await resolve_model_setting(session, "llm_model")
        assert client is None
        assert model is None

    await engine.dispose()
