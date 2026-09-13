"""LLM Provider management: CRUD, type probing, client pool, env var scanning."""

import logging
import os
import uuid as uuid_mod
from datetime import datetime, timezone

import httpx
from cryptography.fernet import Fernet
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import LlmProvider, Setting

logger = logging.getLogger(__name__)

# --- Encryption helpers ---


def _get_fernet() -> Fernet:
    key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY environment variable is not set")
    return Fernet(key.encode())


def encrypt_api_key(api_key: str) -> str:
    return _get_fernet().encrypt(api_key.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


# --- Provider type probing ---

PROBE_TIMEOUT = 10.0


async def probe_provider_type(base_url: str, api_key: str) -> str:
    """Probe a provider URL to detect its type.

    Returns: 'litellm', 'openai_compatible', or 'unknown'.
    """
    headers = {"Authorization": f"Bearer {api_key}"}

    # 1. Try LiteLLM /model/info endpoint
    stripped_url = base_url.rstrip("/")
    if stripped_url.endswith("/v1"):
        stripped_url = stripped_url[:-3]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{stripped_url}/model/info",
                headers=headers,
                timeout=PROBE_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data.get("data"), list):
                    return "litellm"
    except Exception:
        logger.debug("LiteLLM probe failed for %s", stripped_url, exc_info=True)

    # 2. Try OpenAI-compatible /models endpoint
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers=headers,
                timeout=PROBE_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data.get("data"), list):
                    return "openai_compatible"
    except Exception:
        logger.debug("OpenAI-compatible probe failed for %s", base_url, exc_info=True)

    return "unknown"


# --- Client pool ---

_clients: dict[uuid_mod.UUID, AsyncOpenAI] = {}


def get_client_for_provider_sync(provider: LlmProvider) -> AsyncOpenAI:
    """Get or create an AsyncOpenAI client for a provider (from a loaded model instance)."""
    if provider.id in _clients:
        return _clients[provider.id]
    api_key = decrypt_api_key(provider.api_key_encrypted)
    client = AsyncOpenAI(base_url=provider.base_url, api_key=api_key)
    _clients[provider.id] = client
    return client


async def get_client_for_provider(provider_id: uuid_mod.UUID, session: AsyncSession) -> AsyncOpenAI | None:
    """Get or create an AsyncOpenAI client for a provider by ID."""
    if provider_id in _clients:
        return _clients[provider_id]
    result = await session.execute(
        select(LlmProvider).where(LlmProvider.id == provider_id)
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        return None
    return get_client_for_provider_sync(provider)


def evict_client(provider_id: uuid_mod.UUID) -> None:
    """Remove a cached client for a provider."""
    _clients.pop(provider_id, None)


def mask_api_key(encrypted_key: str) -> str:
    """Decrypt and mask an API key for display: first 4 chars + ****."""
    try:
        decrypted = decrypt_api_key(encrypted_key)
        if len(decrypted) <= 4:
            return "****"
        return decrypted[:4] + "****"
    except Exception:
        return "****"


def provider_to_dict(provider: LlmProvider) -> dict:
    """Serialize a provider for API responses (API key masked)."""
    return {
        "id": str(provider.id),
        "name": provider.name,
        "base_url": provider.base_url,
        "api_key": mask_api_key(provider.api_key_encrypted),
        "provider_type": provider.provider_type,
        "is_default": provider.is_default,
        "source": provider.source,
        "created_at": provider.created_at.isoformat() if provider.created_at else None,
        "updated_at": provider.updated_at.isoformat() if provider.updated_at else None,
    }


# --- Env var scanning ---


async def scan_env_providers(session: AsyncSession) -> None:
    """Scan LLM_PROVIDER_{N}_* env vars and upsert providers with source='env'.

    Cleans up stale env-sourced providers that no longer have matching env vars.
    """
    env_provider_names: set[str] = set()
    index = 0

    while True:
        name = os.environ.get(f"LLM_PROVIDER_{index}_NAME")
        base_url = os.environ.get(f"LLM_PROVIDER_{index}_BASE_URL")
        api_key = os.environ.get(f"LLM_PROVIDER_{index}_API_KEY")

        if not (name and base_url and api_key):
            break

        env_provider_names.add(name)
        is_default = index == 0

        # Probe provider type
        provider_type = await probe_provider_type(base_url, api_key)

        # Upsert: check if exists by name
        result = await session.execute(
            select(LlmProvider).where(LlmProvider.name == name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.base_url = base_url
            existing.api_key_encrypted = encrypt_api_key(api_key)
            existing.provider_type = provider_type
            existing.is_default = is_default
            existing.source = "env"
            existing.updated_at = datetime.now(timezone.utc)
            evict_client(existing.id)
        else:
            provider = LlmProvider(
                name=name,
                base_url=base_url,
                api_key_encrypted=encrypt_api_key(api_key),
                provider_type=provider_type,
                is_default=is_default,
                source="env",
            )
            session.add(provider)

        index += 1

    # If env providers were found, clear default from all non-env providers
    # so only the index-0 env provider remains default
    if env_provider_names:
        result = await session.execute(
            select(LlmProvider).where(LlmProvider.is_default == True)
        )
        for p in result.scalars().all():
            if p.source != "env" or p.name not in env_provider_names:
                p.is_default = False

    # Clean up stale env-sourced providers
    result = await session.execute(
        select(LlmProvider).where(LlmProvider.source == "env")
    )
    for provider in result.scalars().all():
        if provider.name not in env_provider_names:
            evict_client(provider.id)
            await _clear_model_settings_for_provider(session, provider.id)
            await session.delete(provider)

    await session.commit()


# --- First-run model selection ---

# The settings that must name a model before errand can do anything: one
# classifies new tasks, the other runs them. They are established together
# because leaving either unset reproduces the defect this exists to fix — the
# task either parks for want of a title model, or fails at the runner.
MODEL_ROLE_SETTINGS = ("llm_model", "task_processing_model")


async def list_provider_model_ids(provider: LlmProvider) -> list[str] | None:
    """The model ids a provider serves, or None if the listing cannot be read.

    None and an empty list are different answers: one is "we could not ask",
    the other is "it serves nothing". Neither yields a model, but only the
    second is a fact about the provider.
    """
    try:
        client = get_client_for_provider_sync(provider)
        resp = await client.models.list()
        return sorted(m.id for m in resp.data)
    except Exception:
        logger.debug("Model listing failed for provider %s", provider.id, exc_info=True)
        return None


async def _write_model_setting(session: AsyncSession, key: str, provider_id, model: str) -> None:
    setting = (await session.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    value = {"provider_id": str(provider_id), "model": model}
    if setting is None:
        session.add(Setting(key=key, value=value))
    else:
        setting.value = value


async def set_model_selection(session: AsyncSession, provider: LlmProvider, model: str) -> None:
    """Point every model role at this provider and model.

    Callers state which model errand should use; which settings implement that,
    and how many there are, is decided here. Expressing it as a settings write
    would put the current set of roles into every caller, so adding one later
    would leave them configuring a subset with the rest silently unset.
    """
    for key in MODEL_ROLE_SETTINGS:
        await _write_model_setting(session, key, provider.id, model)
    await session.commit()


async def model_selection_state(session: AsyncSession) -> dict:
    """Whether a usable model is configured, and which one.

    A setting naming a provider that no longer exists reports as not
    configured: it looks configured and cannot be used, which is the direction
    that hurts — a caller would say all is well while every task fails.
    """
    provider_ids = {
        str(p.id) for p in (await session.execute(select(LlmProvider))).scalars().all()
    }
    resolved: dict[str, dict] = {}
    for key in MODEL_ROLE_SETTINGS:
        setting = (await session.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
        value = setting.value if setting and isinstance(setting.value, dict) else {}
        provider_id = str(value.get("provider_id") or "")
        # `model` is canonical, but the shared LlmModelCard writes `model_id`,
        # and `resolve_model_setting` accepts either. Reading only `model` here
        # would report a card-saved installation as unconfigured — and then a
        # sole-model scan would overwrite the selection the user had made.
        model = value.get("model") or value.get("model_id") or ""
        if provider_id and model and provider_id in provider_ids:
            resolved[key] = {"provider_id": provider_id, "model": model}

    configured = len(resolved) == len(MODEL_ROLE_SETTINGS)
    first = next(iter(resolved.values()), None)
    return {
        "model_configured": configured,
        "provider_id": first["provider_id"] if configured and first else None,
        "model": first["model"] if configured and first else None,
        # Distinct from `model_configured`: one role set is not a working
        # installation, but it is a deliberate choice that must not be
        # overwritten by a scan the user did not connect to their settings.
        "any_role_configured": bool(resolved),
    }


async def establish_model_settings_if_unset(
    session: AsyncSession, provider: LlmProvider
) -> str | None:
    """Establish the model settings from a provider's sole model.

    Returns the model established, or None. Only where no role is configured —
    the same empty-installation rule detection uses for the default provider:
    with nothing configured there is nothing to override.

    Where the provider serves more than one model, nothing is written. A
    listing carries no mode, and chat, embedding, reranker and speech models
    arrive in one list, so any pick would be a guess — and a model stored on a
    guess is a setting the user did not make, presented as one they did.
    """
    state = await model_selection_state(session)
    if state["any_role_configured"]:
        return None

    models = await list_provider_model_ids(provider)
    if not models or len(models) != 1:
        return None

    # Re-read before writing. The check above happened before a network call,
    # so the window between them is as long as the listing takes — long enough
    # for a user to choose a model in the settings card and have this overwrite
    # it with the sole-model result arriving afterwards. Not a lock, but it
    # closes the part of the window that is measured in seconds.
    if (await model_selection_state(session))["any_role_configured"]:
        return None

    await set_model_selection(session, provider, models[0])
    return models[0]


async def _clear_model_settings_for_provider(session: AsyncSession, provider_id: uuid_mod.UUID) -> list[str]:
    """Clear model settings that reference a given provider. Returns list of affected setting keys."""
    affected = []
    provider_id_str = str(provider_id)
    for key in ["llm_model", "task_processing_model", "transcription_model"]:
        result = await session.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting and isinstance(setting.value, dict) and str(setting.value.get("provider_id", "")) == provider_id_str:
            setting.value = {"provider_id": None, "model": ""}
            affected.append(key)
    return affected


# --- Model setting helpers ---


async def resolve_model_setting(session: AsyncSession, key: str) -> tuple[AsyncOpenAI | None, str | None]:
    """Read a model setting ({provider_id, model}), resolve to client and model name.

    Returns (client, model_name) or (None, None) if not configured.
    """
    result = await session.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if not setting or not isinstance(setting.value, dict):
        return None, None

    provider_id_str = setting.value.get("provider_id")
    # Canonical field is `model`; also accept `model_id` (the field the shared
    # LlmModelCard writes) so a card-saved setting resolves even if it wasn't
    # normalized on write.
    model = setting.value.get("model") or setting.value.get("model_id")
    if not provider_id_str or not model:
        return None, None

    try:
        provider_id = uuid_mod.UUID(provider_id_str)
    except (ValueError, TypeError):
        return None, None

    client = await get_client_for_provider(provider_id, session)
    if client is None:
        logger.warning("Provider %s for setting %s no longer exists", provider_id_str, key)
        return None, None

    return client, model
