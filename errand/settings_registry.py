import json
import logging
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Setting

logger = logging.getLogger(__name__)

# Registry: key -> {env_var, sensitive, default}
SETTINGS_REGISTRY = {
    "system_prompt": {"env_var": None, "sensitive": False, "default": ""},
    "llm_model": {"env_var": None, "sensitive": False, "default": {"provider_id": None, "model": ""}},
    "task_processing_model": {"env_var": None, "sensitive": False, "default": {"provider_id": None, "model": ""}},
    "transcription_model": {"env_var": None, "sensitive": False, "default": {"provider_id": None, "model": ""}},
    "task_runner_log_level": {"env_var": None, "sensitive": False, "default": "INFO"},
    "timezone": {"env_var": None, "sensitive": False, "default": "UTC"},
    "archive_after_days": {"env_var": None, "sensitive": False, "default": 3},
    "mcp_servers": {"env_var": None, "sensitive": False, "default": None},
    "mcp_api_key": {"env_var": None, "sensitive": True, "default": None},
    "ssh_public_key": {"env_var": None, "sensitive": False, "default": None},
    "git_ssh_hosts": {"env_var": None, "sensitive": False, "default": ["github.com", "bitbucket.org"]},
    "skills_git_repo": {"env_var": None, "sensitive": False, "default": None},
    "oidc_discovery_url": {"env_var": "OIDC_DISCOVERY_URL", "sensitive": False, "default": ""},
    "oidc_client_id": {"env_var": "OIDC_CLIENT_ID", "sensitive": False, "default": ""},
    "oidc_client_secret": {"env_var": "OIDC_CLIENT_SECRET", "sensitive": True, "default": ""},
    "oidc_roles_claim": {"env_var": "OIDC_ROLES_CLAIM", "sensitive": False, "default": "resource_access.errand.roles"},
    "litellm_mcp_servers": {"env_var": None, "sensitive": False, "default": []},
    "hindsight_url": {"env_var": "HINDSIGHT_URL", "sensitive": False, "default": ""},
    "hindsight_bank_id": {"env_var": "HINDSIGHT_BANK_ID", "sensitive": False, "default": "errand-tasks"},
    "hindsight_token": {"env_var": "HINDSIGHT_TOKEN", "sensitive": True, "default": ""},
    "title_generation_timeout": {"env_var": None, "sensitive": False, "default": 30},
    "task_processing_timeout": {"env_var": None, "sensitive": False, "default": 30},
    "transcription_timeout": {"env_var": None, "sensitive": False, "default": 30},
    # Context compaction. Fixed at deploy time until now, which is part of why
    # compaction failed every time it ran: a 30s timeout cannot cover the token
    # budget on a local or free-tier model, and correcting it meant a redeploy.
    # Empty `compaction_model` means "use the task's own model".
    # Same default shape as the other model settings: `_coerce` targets the type
    # of the default, so a plain "" here would stringify the stored dict on read
    # and break the settings card, which expects an object with `model_id`.
    # An empty `model` means "use the task's own model".
    "compaction_model": {"env_var": "COMPACTION_MODEL", "sensitive": False, "default": {"provider_id": None, "model": ""}},
    "compaction_timeout": {"env_var": "COMPACTION_TIMEOUT_SECONDS", "sensitive": False, "default": 180},
    "compaction_max_tokens": {"env_var": "COMPACTION_MAX_TOKENS", "sensitive": False, "default": 4096},
    # The ceiling compaction fires at, and the denominator the context pressure
    # thresholds are measured against. Matches the task runner's own default.
    "max_context_tokens": {"env_var": "MAX_CONTEXT_TOKENS", "sensitive": False, "default": 150000},
    "cloud_service_url": {"env_var": None, "sensitive": False, "default": "https://errand.cloud"},
    "cloud_endpoints": {"env_var": None, "sensitive": False, "default": []},
    "telemetry_enabled": {"env_var": "TELEMETRY_ENABLED", "sensitive": False, "default": True},
    "max_concurrent_tasks": {"env_var": "MAX_CONCURRENT_TASKS", "sensitive": False, "default": 3},
    "max_retry_attempts": {"env_var": "MAX_RETRY_ATTEMPTS", "sensitive": False, "default": 5},
    "task_log_buffer_max_entries": {"env_var": None, "sensitive": False, "default": 5000},
    "task_log_buffer_ttl_seconds": {"env_var": None, "sensitive": False, "default": 86400},
    "plugin_poll_interval_seconds": {"env_var": None, "sensitive": False, "default": 21600},
}

# Keys excluded from API responses
EXCLUDED_KEYS = {"ssh_private_key", "jwt_signing_secret"}


def mask_sensitive_value(value: str) -> str:
    """Mask a sensitive value: show first 4 chars + ****"""
    if not value or len(str(value)) <= 4:
        return "****"
    return str(value)[:4] + "****"


def _coerce(raw: Any, default: Any) -> Any:
    """Coerce a raw value (env string or DB-decoded value) to the type of the registered default.

    Rules:
      - default is None: return raw verbatim
      - default is bool: pass-through if already bool; if str, only the explicit
        forms ``true``/``false``/``1``/``0`` (case-insensitive, whitespace-stripped)
        are accepted — anything else raises. Other types raise TypeError.
      - default is int: int(raw); refuses bool inputs (since ``bool`` subclasses ``int``).
      - default is str: pass-through if already str, else ``str(raw)``.
      - default is dict: pass-through if already dict; if str, ``json.loads`` and
        require the result to be a dict — raises TypeError otherwise.
      - default is list: pass-through if already list; if str, ``json.loads`` and
        require the result to be a list — raises TypeError otherwise.
    Raises on coercion failure; the caller is expected to fall back to default.
    """
    if default is None:
        return raw
    target = type(default)
    if target is bool:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            normalised = raw.strip().lower()
            if normalised in ("true", "1"):
                return True
            if normalised in ("false", "0"):
                return False
            raise ValueError(f"cannot coerce {raw!r} to bool")
        raise TypeError(f"cannot coerce {type(raw).__name__} to bool")
    if target is int:
        if isinstance(raw, bool):
            raise TypeError("refusing to coerce bool to int")
        return int(raw)
    if target is str:
        return raw if isinstance(raw, str) else str(raw)
    if target is dict:
        if isinstance(raw, dict):
            return raw
        decoded = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(decoded, dict):
            raise TypeError(f"expected dict, got {type(decoded).__name__}")
        return decoded
    if target is list:
        if isinstance(raw, list):
            return raw
        decoded = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(decoded, list):
            raise TypeError(f"expected list, got {type(decoded).__name__}")
        return decoded
    return raw


async def resolve_setting_value(
    session: AsyncSession,
    key: str,
    *,
    db_rows: dict | None = None,
) -> tuple[Any, str]:
    """Resolve a single registered setting using env → DB → default.

    Returns (value, source) where source ∈ {"env", "database", "default"}.
    Coerces the resolved value to the type of the registered default. On
    coercion failure, logs a warning and returns (default, "default").

    If `db_rows` is provided, it is used as the DB lookup table; otherwise a
    SELECT against the session is executed.
    """
    meta = SETTINGS_REGISTRY[key]
    env_var = meta["env_var"]
    default = meta["default"]

    env_value = os.environ.get(env_var) if env_var else None
    if env_value is not None and env_value != "":
        try:
            return _coerce(env_value, default), "env"
        except Exception as e:
            logger.warning("Failed to coerce env value for %s: %r (%s); falling back to default", key, env_value, e)
            return default, "default"

    if db_rows is None:
        result = await session.execute(select(Setting).where(Setting.key == key))
        row = result.scalars().first()
        db_value = row.value if row is not None else None
        present = row is not None
    else:
        present = key in db_rows
        db_value = db_rows.get(key)

    if present:
        try:
            return _coerce(db_value, default), "database"
        except Exception as e:
            logger.warning("Failed to coerce DB value for %s: %r (%s); falling back to default", key, db_value, e)
            return default, "default"

    return default, "default"


# The per-role LLM model settings whose value is a `{provider_id, model}` dict.
# Keys whose value is a model selection object. Membership is what makes
# `normalize_model_setting_value` mirror `model` and `model_id` — the shared
# settings card writes `model_id` while the backend resolves `model`, so a key
# omitted here resolves to an empty model name at runtime.
MODEL_SETTING_KEYS = {"llm_model", "task_processing_model", "transcription_model", "compaction_model"}


def normalize_model_setting_value(value):
    """Keep the ``model`` and ``model_id`` fields in sync for LLM model settings.

    The errand backend's canonical field is ``model`` (read by
    ``resolve_model_setting`` and the task runner), while the shared settings card
    (``LlmModelCard``) reads and writes ``model_id``. Mirroring the two — on both
    write (PUT /api/settings) and read (GET /api/settings) — lets each side find
    the value regardless of which one wrote it, without a library release.
    """
    if not isinstance(value, dict):
        return value
    model = value.get("model") or value.get("model_id")
    if model is None:
        return value
    normalized = dict(value)
    normalized["model"] = model
    normalized["model_id"] = model
    return normalized


async def resolve_settings(session: AsyncSession) -> dict:
    """Resolve all settings with metadata: {key: {value, source, sensitive, readonly}}"""
    # Load all DB settings once and pass through the per-key resolver.
    result = await session.execute(select(Setting))
    db_rows = {s.key: s.value for s in result.scalars().all()}

    resolved = {}
    for key, meta in SETTINGS_REGISTRY.items():
        if key in EXCLUDED_KEYS:
            continue

        sensitive = meta["sensitive"]
        value, source = await resolve_setting_value(session, key, db_rows=db_rows)

        if sensitive and source == "env":
            value = mask_sensitive_value(value)

        if key in MODEL_SETTING_KEYS:
            value = normalize_model_setting_value(value)

        resolved[key] = {
            "value": value,
            "source": source,
            "sensitive": sensitive,
            "readonly": source == "env",
        }

    return resolved
