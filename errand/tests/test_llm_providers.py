"""Tests for LLM provider management."""

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
    evict_client,
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
    await _create_test_provider(admin_client, "default-prov")
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


# --- Reachability ---


async def test_reachability_reports_a_working_provider(admin_client: AsyncClient):
    provider = await _create_test_provider(admin_client, "reachable-prov")

    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="openai_compatible"):
        resp = await admin_client.get(f"/api/llm/providers/{provider['id']}/reachability")

    assert resp.status_code == 200
    body = resp.json()
    assert body["reachable"] is True
    assert body["provider_type"] == "openai_compatible"
    assert body["checked_at"]


async def test_reachability_reports_a_stopped_provider(admin_client: AsyncClient):
    """A detected runtime that has since stopped must be distinguishable from a working one."""
    provider = await _create_test_provider(admin_client, "stopped-prov")

    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="unknown"):
        resp = await admin_client.get(f"/api/llm/providers/{provider['id']}/reachability")

    assert resp.status_code == 200
    assert resp.json()["reachable"] is False


async def test_reachability_does_not_mutate_stored_configuration(admin_client: AsyncClient):
    """Checking is not re-probing: a provider whose service is down keeps its type."""
    provider = await _create_test_provider(admin_client, "unchanged-prov")
    assert provider["provider_type"] == "openai_compatible"

    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="unknown"):
        await admin_client.get(f"/api/llm/providers/{provider['id']}/reachability")

    after = next(
        p for p in (await admin_client.get("/api/llm/providers")).json()
        if p["id"] == provider["id"]
    )
    assert after["provider_type"] == "openai_compatible"
    assert after["base_url"] == provider["base_url"]
    assert after["api_key"] == provider["api_key"]
    assert after["is_default"] == provider["is_default"]


async def test_reachability_unknown_provider_is_404(admin_client: AsyncClient):
    resp = await admin_client.get(f"/api/llm/providers/{uuid.uuid4()}/reachability")
    assert resp.status_code == 404


async def test_reachability_requires_admin(client: AsyncClient):
    resp = await client.get(f"/api/llm/providers/{uuid.uuid4()}/reachability")
    assert resp.status_code == 403


# --- Local AI scan endpoint ---


async def test_scan_local_reports_what_was_detected(admin_client: AsyncClient):
    scan_result = {
        "available": True,
        "detected": [{"name": "ollama", "base_url": "http://host.docker.internal:11434/v1",
                      "provider_type": "openai_compatible"}],
        "message": None,
    }
    with patch("local_ai_detection.scan_local_ai", new_callable=AsyncMock, return_value=scan_result):
        resp = await admin_client.post("/api/llm/providers/scan-local")

    assert resp.status_code == 200
    assert resp.json() == scan_result


async def test_scan_local_reports_nothing_found_without_erroring(admin_client: AsyncClient):
    with patch("local_ai_detection.scan_local_ai", new_callable=AsyncMock,
               return_value={"available": True, "detected": [], "message": None}):
        resp = await admin_client.post("/api/llm/providers/scan-local")

    assert resp.status_code == 200
    assert resp.json()["detected"] == []


async def test_scan_local_reports_unavailability_rather_than_failing(admin_client: AsyncClient):
    """No host to probe is a fact to report, not a server error."""
    with patch("local_ai_detection.scan_local_ai", new_callable=AsyncMock,
               return_value={"available": False, "detected": [], "message": "no container host"}):
        resp = await admin_client.post("/api/llm/providers/scan-local")

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["message"]


async def test_scan_local_requires_admin(client: AsyncClient):
    resp = await client.post("/api/llm/providers/scan-local")
    assert resp.status_code == 403


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
    await _create_test_provider(admin_client, "main-prov")
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
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "gpt-4"
    assert data[0]["supports_reasoning"] is None
    assert data[0]["max_output_tokens"] is None


async def test_list_provider_models_enriched_with_metadata(admin_client: AsyncClient):
    """Model list returns enriched objects with metadata from cache."""
    provider = await _create_test_provider(admin_client)

    mock_model = MagicMock()
    mock_model.id = "deepseek-r1:8b"
    mock_models = MagicMock()
    mock_models.data = [mock_model]

    # Seed the metadata cache via the test's overridden session
    from database import get_session
    from main import app
    from models import ModelMetadataCache
    override_fn = app.dependency_overrides[get_session]
    async for session in override_fn():
        session.add(ModelMetadataCache(
            normalized_name="deepseek-r1",
            supports_reasoning=True,
            max_output_tokens=8192,
            source_keys=["deepseek/deepseek-r1"],
        ))
        await session.commit()

    with patch("llm_providers.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=mock_models)
        MockOpenAI.return_value = mock_client
        _clients.clear()
        resp = await admin_client.get(f"/api/llm/providers/{provider['id']}/models")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "deepseek-r1:8b"
    assert data[0]["supports_reasoning"] is True
    assert data[0]["max_output_tokens"] == 8192


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
async def test_resolve_model_setting_accepts_model_id_field():
    """A setting saved by the shared LlmModelCard (using `model_id` instead of the
    backend's canonical `model`) still resolves."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        from tests.conftest import _LLM_PROVIDERS_TABLE_SQL, _SETTINGS_TABLE_SQL
        await conn.execute(text(_LLM_PROVIDERS_TABLE_SQL))
        await conn.execute(text(_SETTINGS_TABLE_SQL))

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    provider_id = uuid.uuid4()
    async with session_maker() as session:
        session.add(LlmProvider(
            id=provider_id, name="p", base_url="https://test.example.com/v1",
            api_key_encrypted=encrypt_api_key("sk-test"), provider_type="openai_compatible",
            is_default=True, source="database",
        ))
        # Note: `model_id` only, no `model` — the raw card-saved shape.
        session.add(Setting(key="llm_model", value={"provider_id": str(provider_id), "model_id": "gpt-4"}))
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


async def test_list_provider_models_role_mode_alias(admin_client: AsyncClient):
    """The settings card's role-based mode names (`title`, `task_processing`,
    `transcription`) are mapped to the `chat`/`audio_transcription` vocabulary
    shared by LiteLLM's `model_info.mode` and the metadata registry.

    Every filter is lenient about *unknown* mode and strict about *known-other*
    mode: a model LiteLLM leaves unset and the registry does not recognise is
    returned with `mode: null`, whichever role was asked for. Dropping those
    would leave anyone whose provider publishes no modes — every local runtime —
    staring at an empty dropdown."""
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="litellm"):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": "lite", "base_url": "https://litellm.example.com", "api_key": "sk-key",
        })
    provider = resp.json()

    model_info = {"data": [
        {"model_name": "claude-x", "model_info": {"mode": "chat"}},
        {"model_name": "untagged-chat", "model_info": {"mode": None}},        # null mode -> treated as chat
        {"model_name": "no-mode-field", "model_info": {}},                    # missing mode -> treated as chat
        {"model_name": "embed-1", "model_info": {"mode": "embedding"}},       # explicit non-chat -> excluded
        {"model_name": "whisper-z", "model_info": {"mode": "audio_transcription"}},
    ]}
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = model_info

    def make_client(*_a, **_k):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.get = AsyncMock(return_value=mock_resp)
        return instance

    # The names come from /v1/models for every provider type; /model/info is
    # consulted only for the modes it reports.
    listing = _model_listing([e["model_name"] for e in model_info["data"]])

    with patch("main.httpx.AsyncClient", side_effect=make_client), \
            patch("llm_providers.AsyncOpenAI") as MockOpenAI:
        oa = AsyncMock()
        oa.models.list = AsyncMock(return_value=listing)
        MockOpenAI.return_value = oa
        _clients.clear()
        r_title = await admin_client.get(f"/api/llm/providers/{provider['id']}/models?mode=title")
        _clients.clear()
        r_task = await admin_client.get(f"/api/llm/providers/{provider['id']}/models?mode=task_processing")
        _clients.clear()
        r_trans = await admin_client.get(f"/api/llm/providers/{provider['id']}/models?mode=transcription")
    _clients.clear()

    assert r_title.status_code == 200
    # title/task -> chat: chat-mode + unknown-mode; excludes embedding + audio_transcription
    assert {m["id"] for m in r_title.json()} == {"claude-x", "untagged-chat", "no-mode-field"}
    assert {m["id"] for m in r_task.json()} == {"claude-x", "untagged-chat", "no-mode-field"}
    # transcription -> audio_transcription: the whisper model, plus the two the
    # provider did not classify, which are marked so the UI can tell them apart
    # from a positive match.
    assert {m["id"] for m in r_trans.json()} == {"whisper-z", "untagged-chat", "no-mode-field"}
    by_id = {m["id"]: m for m in r_trans.json()}
    assert by_id["whisper-z"]["mode"] == "audio_transcription"
    assert by_id["untagged-chat"]["mode"] is None


async def test_openai_compatible_mode_filter_uses_the_registry(admin_client: AsyncClient):
    """A provider whose listing carries no mode is filterable all the same."""
    provider = await _create_test_provider(admin_client, "local-ollama")

    models = MagicMock()
    models.data = [_bare_model("qwen3:8b"), _bare_model("bge-m3"), _bare_model("mystery-7b")]

    from database import get_session
    from main import app
    from models import ModelMetadataCache
    async for session in app.dependency_overrides[get_session]():
        session.add(ModelMetadataCache(
            normalized_name="qwen3", supports_reasoning=False,
            max_output_tokens=None, mode="chat", source_keys=["qwen3"],
        ))
        session.add(ModelMetadataCache(
            normalized_name="bge-m3", supports_reasoning=False,
            max_output_tokens=None, mode="embedding", source_keys=["bge-m3"],
        ))
        await session.commit()

    with patch("llm_providers.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=models)
        MockOpenAI.return_value = mock_client
        _clients.clear()
        resp = await admin_client.get(
            f"/api/llm/providers/{provider['id']}/models?mode=task_processing"
        )

    assert resp.status_code == 200
    by_id = {m["id"]: m for m in resp.json()}
    # The embedding model is positively something else, so it goes.
    assert "bge-m3" not in by_id
    assert by_id["qwen3:8b"]["mode"] == "chat"
    # Unknown to the registry — kept, and marked as unknown.
    assert by_id["mystery-7b"]["mode"] is None


async def test_provider_reported_mode_wins_over_the_registry(admin_client: AsyncClient):
    provider = await _create_test_provider(admin_client, "reports-mode")

    reporting = MagicMock()
    reporting.id = "surprise-1"
    reporting.mode = "embedding"
    models = MagicMock()
    models.data = [reporting]

    from database import get_session
    from main import app
    from models import ModelMetadataCache
    async for session in app.dependency_overrides[get_session]():
        session.add(ModelMetadataCache(
            normalized_name="surprise-1", supports_reasoning=False,
            max_output_tokens=None, mode="chat", source_keys=["surprise-1"],
        ))
        await session.commit()

    with patch("llm_providers.AsyncOpenAI") as MockOpenAI:
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=models)
        MockOpenAI.return_value = mock_client
        _clients.clear()
        unfiltered = await admin_client.get(f"/api/llm/providers/{provider['id']}/models")
        _clients.clear()
        filtered = await admin_client.get(
            f"/api/llm/providers/{provider['id']}/models?mode=task_processing"
        )

    # The registry says chat; the provider says embedding and is believed.
    assert unfiltered.json()[0]["mode"] == "embedding"
    assert filtered.json() == []


async def test_litellm_listing_does_not_depend_on_model_info(admin_client: AsyncClient):
    """A LiteLLM proxy that restricts /model/info still has browsable models.

    LiteLLM serves /model/info to admin keys and can refuse it to a virtual
    key. Sourcing the list from there rather than /v1/models left such a
    deployment with no models at all, where the plain listing would have
    served them.
    """
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="litellm"):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": "restricted-proxy", "base_url": "https://litellm.example.com", "api_key": "sk-virtual",
        })
    provider = resp.json()

    def failing_http(*_a, **_k):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.get = AsyncMock(side_effect=Exception("403 Forbidden"))
        return instance

    listing = _model_listing(["claude-x", "gpt-y"])
    with patch("main.httpx.AsyncClient", side_effect=failing_http), \
            patch("llm_providers.AsyncOpenAI") as MockOpenAI:
        oa = AsyncMock()
        oa.models.list = AsyncMock(return_value=listing)
        MockOpenAI.return_value = oa
        _clients.clear()
        unfiltered = await admin_client.get(f"/api/llm/providers/{provider['id']}/models")
        _clients.clear()
        filtered = await admin_client.get(
            f"/api/llm/providers/{provider['id']}/models?mode=task_processing"
        )
    _clients.clear()

    assert unfiltered.status_code == 200
    assert {m["id"] for m in unfiltered.json()} == {"claude-x", "gpt-y"}
    # Modes are unknown without /model/info, so nothing is positively excluded.
    assert filtered.status_code == 200
    assert {m["id"] for m in filtered.json()} == {"claude-x", "gpt-y"}


async def test_litellm_unfiltered_listing_uses_the_model_list(admin_client: AsyncClient):
    """With no mode filter, a LiteLLM provider lists exactly what /v1/models returns."""
    with patch("main.probe_provider_type", new_callable=AsyncMock, return_value="litellm"):
        resp = await admin_client.post("/api/llm/providers", json={
            "name": "plain-proxy", "base_url": "https://litellm.example.com", "api_key": "sk-key",
        })
    provider = resp.json()

    model_info = {"data": [{"model_name": "claude-x", "model_info": {"mode": "chat"}}]}
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = model_info

    def make_client(*_a, **_k):
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.get = AsyncMock(return_value=mock_resp)
        return instance

    # /v1/models knows about a model /model/info does not describe.
    listing = _model_listing(["claude-x", "undocumented-z"])
    with patch("main.httpx.AsyncClient", side_effect=make_client), \
            patch("llm_providers.AsyncOpenAI") as MockOpenAI:
        oa = AsyncMock()
        oa.models.list = AsyncMock(return_value=listing)
        MockOpenAI.return_value = oa
        _clients.clear()
        r = await admin_client.get(f"/api/llm/providers/{provider['id']}/models")
    _clients.clear()

    assert r.status_code == 200
    by_id = {m["id"]: m for m in r.json()}
    assert set(by_id) == {"claude-x", "undocumented-z"}
    assert by_id["claude-x"]["mode"] == "chat"
    assert by_id["undocumented-z"]["mode"] is None


def _model_listing(ids: list[str]):
    """An OpenAI-compatible /v1/models response carrying no mode of its own."""
    listing = MagicMock()
    listing.data = []
    for model_id in ids:
        m = MagicMock(spec=["id"])
        m.id = model_id
        listing.data.append(m)
    return listing


def _bare_model(model_id: str):
    """An OpenAI-compatible model entry that reports no mode of its own."""
    m = MagicMock(spec=["id"])
    m.id = model_id
    return m


def test_normalize_model_setting_value_mirrors_model_and_model_id():
    """normalize_model_setting_value keeps `model` and `model_id` in sync."""
    from settings_registry import normalize_model_setting_value

    # Card-saved shape (model_id only) -> gains `model`.
    out = normalize_model_setting_value({"provider_id": "p", "model_id": "claude-x"})
    assert out["model"] == "claude-x"
    assert out["model_id"] == "claude-x"

    # Backend-saved shape (model only) -> gains `model_id`.
    out = normalize_model_setting_value({"provider_id": "p", "model": "claude-y"})
    assert out["model"] == "claude-y"
    assert out["model_id"] == "claude-y"

    # Empty / non-dict pass through unchanged.
    assert normalize_model_setting_value({"provider_id": "p"}) == {"provider_id": "p"}
    assert normalize_model_setting_value(None) is None


async def test_settings_model_setting_round_trip_syncs_fields(admin_client: AsyncClient):
    """PUT a model setting in the card's shape (`model_id`); GET returns both
    `model_id` (for the card to display) and `model` (for backend resolution)."""
    await admin_client.put("/api/settings", json={
        "llm_model": {"provider_id": "prov-1", "model_id": "claude-opus-4-6"},
    })
    resp = await admin_client.get("/api/settings")
    value = resp.json()["llm_model"]["value"]
    assert value["provider_id"] == "prov-1"
    assert value["model_id"] == "claude-opus-4-6"
    assert value["model"] == "claude-opus-4-6"
