"""Tests for the settings registry module."""
import os
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from settings_registry import (
    EXCLUDED_KEYS,
    MODEL_SETTING_KEYS,
    SETTINGS_REGISTRY,
    _coerce,
    mask_sensitive_value,
    normalize_model_setting_value,
    resolve_setting_value,
    resolve_settings,
)
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

    assert result["llm_model"]["value"] == {"provider_id": None, "model": ""}
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
            text("INSERT INTO settings (key, value) VALUES ('oidc_discovery_url', '\"http://db-url\"')")
        )
        await session.commit()

    with patch.dict(os.environ, {"OIDC_DISCOVERY_URL": "http://env-url"}):
        async with session_factory() as session:
            result = await resolve_settings(session)

    assert result["oidc_discovery_url"]["value"] == "http://env-url"
    assert result["oidc_discovery_url"]["source"] == "env"
    assert result["oidc_discovery_url"]["readonly"] is True

    await engine.dispose()


async def test_sensitive_env_values_masked():
    """Sensitive env-sourced values should be masked."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch.dict(os.environ, {"OIDC_CLIENT_SECRET": "sk-1234567890abcdef"}):
        async with session_factory() as session:
            result = await resolve_settings(session)

    assert result["oidc_client_secret"]["value"] == "sk-1****"
    assert result["oidc_client_secret"]["sensitive"] is True
    assert result["oidc_client_secret"]["readonly"] is True

    await engine.dispose()


async def test_hindsight_token_masked_when_env_sourced():
    """Env-sourced hindsight_token should be marked sensitive and masked in API responses."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch.dict(os.environ, {"HINDSIGHT_TOKEN": "sk-abc1234567890"}):
        async with session_factory() as session:
            result = await resolve_settings(session)

    assert result["hindsight_token"]["sensitive"] is True
    assert result["hindsight_token"]["readonly"] is True
    assert result["hindsight_token"]["source"] == "env"
    assert result["hindsight_token"]["value"] != "sk-abc1234567890"
    assert result["hindsight_token"]["value"].endswith("****")

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


# --- _coerce ---


def test_coerce_int_from_string():
    assert _coerce("7", 3) == 7


def test_coerce_int_from_int():
    assert _coerce(7, 3) == 7


def test_coerce_str_passthrough():
    assert _coerce("hello", "default") == "hello"


def test_coerce_list_from_json_string():
    assert _coerce('["a", "b"]', []) == ["a", "b"]


def test_coerce_list_passthrough():
    assert _coerce(["a"], []) == ["a"]


def test_coerce_dict_from_json_string():
    assert _coerce('{"k": 1}', {}) == {"k": 1}


def test_coerce_dict_passthrough():
    assert _coerce({"k": 1}, {}) == {"k": 1}


def test_coerce_bool_from_json_string():
    assert _coerce("true", True) is True
    assert _coerce("false", True) is False


def test_coerce_none_default_returns_raw():
    assert _coerce("anything", None) == "anything"
    assert _coerce({"k": 1}, None) == {"k": 1}


def test_coerce_int_failure_raises():
    with pytest.raises(ValueError):
        _coerce("abc", 3)


def test_coerce_bool_strict_string_forms_only():
    """bool coercion accepts only the explicit forms 'true'/'false'/'1'/'0'.

    Other strings (including JSON-encoded `"false"`, free-form `yes`/`no`)
    raise so the caller falls back to the registered default — this avoids
    the historical bug where ``json.loads("0")`` returned int 0 and slipped
    through type checks expecting bool.
    """
    assert _coerce("0", True) is False
    assert _coerce("1", True) is True
    with pytest.raises(ValueError):
        _coerce("yes", True)
    with pytest.raises(ValueError):
        _coerce('"false"', True)  # JSON-encoded string, not an accepted form


def test_coerce_dict_rejects_list():
    """A list value must not pass when default is a dict."""
    with pytest.raises(TypeError):
        _coerce(["a", "b"], {"k": 1})
    with pytest.raises(TypeError):
        _coerce("[1, 2]", {"k": 1})


def test_coerce_list_rejects_dict():
    """A dict value must not pass when default is a list."""
    with pytest.raises(TypeError):
        _coerce({"k": 1}, [])
    with pytest.raises(TypeError):
        _coerce('{"k": 1}', [])


def test_coerce_int_rejects_bool():
    """bool is a subclass of int but should not silently pass."""
    with pytest.raises(TypeError):
        _coerce(True, 3)


# --- resolve_setting_value ---


async def test_resolve_setting_value_env_only():
    """Env value wins, returned as coerced int."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch.dict(os.environ, {"MAX_CONCURRENT_TASKS": "7"}):
        async with session_factory() as session:
            value, source = await resolve_setting_value(session, "max_concurrent_tasks")

    assert value == 7
    assert source == "env"
    await engine.dispose()


async def test_resolve_setting_value_db_only():
    """DB row used when no env var."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        await session.execute(text("INSERT INTO settings (key, value) VALUES ('max_concurrent_tasks', '4')"))
        await session.commit()

    # Ensure env var is unset
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MAX_CONCURRENT_TASKS", None)
        async with session_factory() as session:
            value, source = await resolve_setting_value(session, "max_concurrent_tasks")

    assert value == 4
    assert source == "database"
    await engine.dispose()


async def test_resolve_setting_value_env_overrides_db():
    """Env wins even when DB row exists — the regression we're fixing."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        await session.execute(text("INSERT INTO settings (key, value) VALUES ('max_concurrent_tasks', '4')"))
        await session.commit()

    with patch.dict(os.environ, {"MAX_CONCURRENT_TASKS": "7"}):
        async with session_factory() as session:
            value, source = await resolve_setting_value(session, "max_concurrent_tasks")

    assert value == 7
    assert source == "env"
    await engine.dispose()


async def test_resolve_setting_value_default_only():
    """Neither env nor DB → registered default."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    os.environ.pop("MAX_CONCURRENT_TASKS", None)
    async with session_factory() as session:
        value, source = await resolve_setting_value(session, "max_concurrent_tasks")

    assert value == 3
    assert source == "default"
    await engine.dispose()


async def test_resolve_setting_value_empty_env_treated_as_unset():
    """Empty env string → fall through to DB row."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        await session.execute(text("INSERT INTO settings (key, value) VALUES ('max_concurrent_tasks', '4')"))
        await session.commit()

    with patch.dict(os.environ, {"MAX_CONCURRENT_TASKS": ""}):
        async with session_factory() as session:
            value, source = await resolve_setting_value(session, "max_concurrent_tasks")

    assert value == 4
    assert source == "database"
    await engine.dispose()


async def test_resolve_setting_value_coercion_failure_falls_back_to_default():
    """A malformed DB value logs a warning and returns the default."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        await session.execute(text("INSERT INTO settings (key, value) VALUES ('max_concurrent_tasks', '\"abc\"')"))
        await session.commit()

    os.environ.pop("MAX_CONCURRENT_TASKS", None)
    async with session_factory() as session:
        value, source = await resolve_setting_value(session, "max_concurrent_tasks")

    assert value == 3
    assert source == "default"
    await engine.dispose()


async def test_resolve_setting_value_uses_prefetched_db_rows():
    """When db_rows is provided, no SELECT is executed."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    os.environ.pop("MAX_CONCURRENT_TASKS", None)
    async with session_factory() as session:
        # Real session, but no DB row at all — value comes from db_rows arg.
        value, source = await resolve_setting_value(
            session, "max_concurrent_tasks", db_rows={"max_concurrent_tasks": 5}
        )

    assert value == 5
    assert source == "database"
    await engine.dispose()


async def test_resolve_setting_value_default_is_none_returns_raw():
    """When the registered default is None, the raw DB value is returned untouched."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # mcp_servers has default=None
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('mcp_servers', '{\"foo\": \"bar\"}')")
        )
        await session.commit()

    async with session_factory() as session:
        value, source = await resolve_setting_value(session, "mcp_servers")

    assert source == "database"
    # JSONB decoded by SQLAlchemy → dict
    assert value == {"foo": "bar"}
    await engine.dispose()


# --- Snapshot: API response shape preserved ---


async def test_resolve_settings_response_shape_snapshot():
    """Every resolved entry has exactly {value, source, sensitive, readonly}."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    await _create_tables(engine)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Mix of DB-backed and default-backed values; no env vars set.
    async with session_factory() as session:
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('system_prompt', '\"hello\"')")
        )
        await session.execute(
            text("INSERT INTO settings (key, value) VALUES ('archive_after_days', '7')")
        )
        await session.commit()

    # Clear env vars that might bleed in
    for env_var in ("OIDC_DISCOVERY_URL", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET",
                    "OIDC_ROLES_CLAIM", "TELEMETRY_ENABLED", "MAX_CONCURRENT_TASKS"):
        os.environ.pop(env_var, None)

    async with session_factory() as session:
        result = await resolve_settings(session)

    # Every entry has exactly the four expected fields.
    for key, entry in result.items():
        assert set(entry.keys()) == {"value", "source", "sensitive", "readonly"}, (
            f"unexpected fields for {key}: {entry.keys()}"
        )

    # Excluded keys are absent.
    for key in EXCLUDED_KEYS:
        assert key not in result

    # Spot-check a DB-backed entry and a default entry.
    assert result["system_prompt"] == {
        "value": "hello", "source": "database", "sensitive": False, "readonly": False,
    }
    assert result["archive_after_days"] == {
        "value": 7, "source": "database", "sensitive": False, "readonly": False,
    }
    assert result["timezone"] == {
        "value": "UTC", "source": "default", "sensitive": False, "readonly": False,
    }

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


# ---------------------------------------------------------------------------
# Compaction settings
#
# Context compaction had a 0% success rate in production, in part because the
# model, timeout and token budget were fixed at deploy time and could not be
# corrected without a redeploy.
# ---------------------------------------------------------------------------

def test_compaction_keys_registered():
    for key in ("compaction_model", "compaction_timeout", "compaction_max_tokens"):
        assert key in SETTINGS_REGISTRY, f"{key} must be registered"


def test_compaction_keys_not_sensitive():
    for key in ("compaction_model", "compaction_timeout", "compaction_max_tokens"):
        assert SETTINGS_REGISTRY[key]["sensitive"] is False


def test_compaction_model_is_a_model_setting_key():
    """Without this, a model chosen in the UI resolves to an empty string.

    The shared settings card writes `model_id`; the backend resolves `model`.
    `normalize_model_setting_value` mirrors them only for keys in this set —
    the same defect fixed for task profiles in selective-mcp-server-defaults.
    """
    assert "compaction_model" in MODEL_SETTING_KEYS


def test_compaction_model_normalizes_model_id():
    normalized = normalize_model_setting_value(
        {"provider_id": "p1", "model_id": "claude-haiku-4-5-20251001"}
    )
    assert normalized["model"] == "claude-haiku-4-5-20251001"
    assert normalized["model_id"] == "claude-haiku-4-5-20251001"


def test_compaction_timeout_default_is_generous():
    """30s cannot cover the token budget on a local or free-tier model."""
    assert SETTINGS_REGISTRY["compaction_timeout"]["default"] >= 120


def test_compaction_max_tokens_default_above_2048():
    assert SETTINGS_REGISTRY["compaction_max_tokens"]["default"] > 2048


def test_compaction_model_default_matches_other_model_settings():
    """The default's TYPE drives _coerce, so it must be a dict like its peers.

    A plain "" default makes _coerce stringify the stored dict on read, which
    breaks the settings card — it expects an object carrying `model_id`. An
    empty `model` still means "use the task's own model".
    """
    default = SETTINGS_REGISTRY["compaction_model"]["default"]
    assert isinstance(default, dict), "must be a dict or _coerce stringifies stored values"
    assert default.get("model") == ""
    assert default == SETTINGS_REGISTRY["task_processing_model"]["default"]


def test_compaction_model_survives_a_round_trip_as_an_object():
    """Regression: a stored selection must read back as an object, not a string."""
    stored = normalize_model_setting_value(
        {"provider_id": None, "model_id": "claude-haiku-4-5-20251001"}
    )
    coerced = _coerce(stored, SETTINGS_REGISTRY["compaction_model"]["default"])
    assert isinstance(coerced, dict), "read-back must stay an object"
    assert coerced["model_id"] == "claude-haiku-4-5-20251001"


def test_compaction_env_var_names():
    """Existing deployments setting these in the environment must keep working."""
    assert SETTINGS_REGISTRY["compaction_model"]["env_var"] == "COMPACTION_MODEL"
    assert SETTINGS_REGISTRY["compaction_timeout"]["env_var"] == "COMPACTION_TIMEOUT_SECONDS"
    assert SETTINGS_REGISTRY["compaction_max_tokens"]["env_var"] == "COMPACTION_MAX_TOKENS"
