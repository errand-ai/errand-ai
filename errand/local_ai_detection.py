"""Detect OpenAI-compatible AI runtimes running on the container host.

The scan contacts a fixed enumeration of well-known endpoints through the host
gateway address and registers what answers as a provider with
``source="detected"``. It never sweeps a port range: that trips security review
and buys nothing, since a runtime not on its own default port is one the user
can add by hand.

The URL stored is the URL that answered. errand-server, the memory service and
every task container all reach the host by the same gateway name, so the
address that worked here is the address that works there — no placeholder
tokens, no per-consumer rewriting.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from host_gateway import get_host_gateway_address, is_local_detection_available
from llm_providers import (
    _clear_model_settings_for_provider,
    encrypt_api_key,
    evict_client,
    probe_provider_type,
)
from models import LlmProvider

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 5.0

# Local runtimes ignore Authorization entirely, but `api_key_encrypted` is NOT
# NULL. This is the placeholder llama.cpp, LocalAI and LM Studio use in their
# own documentation, so it is the one an operator is most likely to recognise
# as a placeholder rather than mistake for a credential.
DETECTED_API_KEY = "sk-no-key-required"


@dataclass(frozen=True)
class LocalAiCandidate:
    """A runtime and the port it listens on by default."""

    name: str
    port: int


# Every one of these exposes an OpenAI-compatible /v1/models, so the existing
# provider-type probe classifies them with no per-runtime code. llama.cpp and
# LocalAI share 8080, which is why what answered is identified from its
# response rather than assumed from the port.
LOCAL_AI_CANDIDATES: tuple[LocalAiCandidate, ...] = (
    LocalAiCandidate("ollama", 11434),
    LocalAiCandidate("lm-studio", 1234),
    LocalAiCandidate("llama.cpp", 8080),
    LocalAiCandidate("jan", 1337),
    LocalAiCandidate("vllm", 8000),
    LocalAiCandidate("localai", 8080),
    LocalAiCandidate("gpt4all", 4891),
    LocalAiCandidate("mlx", 10240),
)

# `owned_by` values that name their runtime. Where a marker is absent or
# unrecognised the endpoint is named after itself rather than guessed at, so a
# wrong or missing signature costs a display name, never a working provider.
OWNED_BY_SIGNATURES: dict[str, str] = {
    "library": "ollama",
    "organization_owner": "lm-studio",
    "llamacpp": "llama.cpp",
    "llama.cpp": "llama.cpp",
    "vllm": "vllm",
    "localai": "localai",
}


def candidate_ports() -> list[int]:
    """The distinct ports to probe, in candidate order."""
    seen: list[int] = []
    for candidate in LOCAL_AI_CANDIDATES:
        if candidate.port not in seen:
            seen.append(candidate.port)
    return seen


def identify_runtime(models_payload: dict | None, port: int) -> str:
    """Name the runtime that produced a /v1/models response.

    The response is the authority. Only when it carries no recognisable marker
    does the port contribute, and then only when exactly one candidate claims
    it — a shared port names the endpoint instead, because asserting either
    runtime would be a guess presented as a fact.
    """
    for entry in (models_payload or {}).get("data", []) or []:
        if not isinstance(entry, dict):
            continue
        owner = str(entry.get("owned_by", "")).strip().lower()
        if owner in OWNED_BY_SIGNATURES:
            return OWNED_BY_SIGNATURES[owner]

    claimants = [c.name for c in LOCAL_AI_CANDIDATES if c.port == port]
    if len(claimants) == 1:
        return claimants[0]
    return f"local-ai-{port}"


async def _fetch_models(base_url: str) -> dict | None:
    """GET {base_url}/models, for identification only. None on any failure."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {DETECTED_API_KEY}"},
                timeout=PROBE_TIMEOUT,
            )
            if resp.status_code == 200:
                payload = resp.json()
                if isinstance(payload, dict):
                    return payload
    except Exception:
        logger.debug("Model listing failed for %s", base_url, exc_info=True)
    return None


async def scan_local_ai(session: AsyncSession) -> dict:
    """Probe the candidate endpoints and reconcile ``source="detected"`` providers.

    Returns ``{"available", "detected", "message"}``. When detection is
    unavailable — no gateway address, or Kubernetes, where there is no host —
    nothing is probed and nothing is reconciled: "cannot tell" is not the same
    statement as "nothing is running", and reconciling on it would delete
    providers that are perfectly healthy.
    """
    if not is_local_detection_available():
        return {
            "available": False,
            "detected": [],
            "message": (
                "Local AI detection is not available for this deployment, because "
                "there is no container host to probe."
            ),
        }

    gateway = get_host_gateway_address()
    detected: dict[str, dict] = {}

    for port in candidate_ports():
        base_url = f"http://{gateway}:{port}/v1"
        provider_type = await probe_provider_type(base_url, DETECTED_API_KEY)
        if provider_type == "unknown":
            continue
        name = identify_runtime(await _fetch_models(base_url), port)
        detected[name] = {
            "name": name,
            "base_url": base_url,
            "provider_type": provider_type,
        }

    # An empty installation is the only one where the scan may choose what
    # inference runs against; anywhere else, adopting a provider is the user's
    # decision to make explicitly.
    total = (await session.execute(select(func.count()).select_from(LlmProvider))).scalar() or 0
    claim_default = total == 0

    now = datetime.now(timezone.utc)
    registered: list[dict] = []

    for name, info in detected.items():
        existing = (await session.execute(
            select(LlmProvider).where(LlmProvider.name == name)
        )).scalar_one_or_none()

        if existing is not None and existing.source != "detected":
            # The name is already an operator's. Detection does not own it and
            # must not silently repoint their provider at a local runtime.
            logger.info(
                "Skipping detected runtime %s: a %s-sourced provider already has that name",
                name, existing.source,
            )
            continue

        if existing is not None:
            existing.base_url = info["base_url"]
            existing.api_key_encrypted = encrypt_api_key(DETECTED_API_KEY)
            existing.provider_type = info["provider_type"]
            existing.updated_at = now
            evict_client(existing.id)
        else:
            session.add(LlmProvider(
                name=name,
                base_url=info["base_url"],
                api_key_encrypted=encrypt_api_key(DETECTED_API_KEY),
                provider_type=info["provider_type"],
                is_default=claim_default,
                source="detected",
            ))
            # Only the first one — two runtimes found on an empty install must
            # not both claim the default.
            claim_default = False

        registered.append(info)

    # Reconcile: a runtime that has gone away should not leave a row behind.
    stale = (await session.execute(
        select(LlmProvider).where(LlmProvider.source == "detected")
    )).scalars().all()
    for provider in stale:
        if provider.name in detected:
            continue
        evict_client(provider.id)
        await _clear_model_settings_for_provider(session, provider.id)
        await session.delete(provider)

    await session.commit()

    return {"available": True, "detected": registered, "message": None}
