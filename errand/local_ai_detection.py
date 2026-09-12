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
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from host_gateway import get_host_gateway_address, is_local_detection_available
from llm_providers import (
    _clear_model_settings_for_provider,
    decrypt_api_key,
    encrypt_api_key,
    evict_client,
    probe_provider_type,
    provider_to_dict,
)
from models import LlmProvider

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 5.0

# Local runtimes ignore Authorization entirely, but `api_key_encrypted` is NOT
# NULL. This is the placeholder llama.cpp, LocalAI and LM Studio use in their
# own documentation, so it is the one an operator is most likely to recognise
# as a placeholder rather than mistake for a credential.
DETECTED_API_KEY = "sk-no-key-required"

# What a candidate endpoint said, from detection's point of view. This is a
# different question from `probe_provider_type()`'s — that one answers "what
# type is this provider", and for an endpoint that will not talk to us
# `unknown` remains the right answer, which four other call sites rely on.
# Detection needs to know whether something is *there*, which a 401 proves as
# firmly as a 200 does.
ENDPOINT_ANSWERED = "answered"
ENDPOINT_UNAUTHORIZED = "unauthorized"
ENDPOINT_NO_ANSWER = "no_answer"


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

# `owned_by` values that name their runtime. A missing signature costs a display
# name, never a working provider.
OWNED_BY_SIGNATURES: dict[str, str] = {
    "library": "ollama",
    "organization_owner": "lm-studio",
    "llamacpp": "llama.cpp",
    "llama.cpp": "llama.cpp",
    "vllm": "vllm",
    "localai": "localai",
    "omlx": "omlx",
}


def candidate_ports() -> list[int]:
    """The distinct ports to probe, in candidate order."""
    seen: list[int] = []
    for candidate in LOCAL_AI_CANDIDATES:
        if candidate.port not in seen:
            seen.append(candidate.port)
    return seen


def identify_runtime(models_payload: dict | None, port: int | None) -> str:
    """Name the runtime that produced a /v1/models response.

    The response is the authority. Only when it carries no recognisable marker
    does the port contribute, and then only when exactly one candidate claims
    it — a shared port names the endpoint instead, because asserting either
    runtime would be a guess presented as a fact.

    A payload of ``None`` means no body was read at all, which is not the same
    as a body carrying no marker; and a body carrying a marker we do not
    recognise is different again — that is the response telling us it is not
    the port's usual occupant. Falling back to the port's single claimant is
    a fair inference from a listing that simply did not say; it is a guess
    presented as a fact when nothing was read, and it would name an oMLX server
    on 8000 `vllm` for no better reason than the candidate table.
    """
    claimed_by_response = False
    if models_payload is not None:
        for entry in models_payload.get("data", []) or []:
            if not isinstance(entry, dict):
                continue
            owner = str(entry.get("owned_by", "")).strip().lower()
            if not owner:
                continue
            if owner in OWNED_BY_SIGNATURES:
                return OWNED_BY_SIGNATURES[owner]
            # It said something, and it was not a runtime we know. That is a
            # statement, not a silence: an oMLX server on 8000 says `omlx`, and
            # answering `vllm` because the candidate table calls 8000 vLLM
            # contradicts the response we just read.
            claimed_by_response = True

        if not claimed_by_response:
            claimants = [c.name for c in LOCAL_AI_CANDIDATES if c.port == port]
            if len(claimants) == 1:
                return claimants[0]

    return f"local-ai-{port}" if port is not None else "local-ai"


def port_of(base_url: str) -> int | None:
    """The port a base URL names, or None if it names none."""
    try:
        return urlparse(base_url).port
    except ValueError:
        return None


async def probe_local_endpoint(base_url: str, api_key: str) -> tuple[str, dict | None]:
    """Ask a candidate endpoint whether it is there, and what it is.

    One request answers both questions, so there is no window in which the two
    can disagree: a 200 carrying a listing is an answer and the listing is the
    identification; a 401 or 403 proves a service that wants credentials we do
    not have; anything else is nothing we can use.

    The same rule `local-ai-provider-detection` used to verify the eighteen
    catalog base URLs — 401/403 proves the endpoint exists, 404 or a DNS
    failure proves it does not — applied where it was originally missing.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=PROBE_TIMEOUT,
            )
    except Exception:
        logger.debug("Endpoint probe failed for %s", base_url, exc_info=True)
        return ENDPOINT_NO_ANSWER, None

    if resp.status_code in (401, 403):
        return ENDPOINT_UNAUTHORIZED, None
    if resp.status_code == 200:
        try:
            payload = resp.json()
        except Exception:
            logger.debug("Unreadable listing from %s", base_url, exc_info=True)
            return ENDPOINT_NO_ANSWER, None
        if isinstance(payload, dict):
            return ENDPOINT_ANSWERED, payload
    return ENDPOINT_NO_ANSWER, None


async def _available_name(session: AsyncSession, name: str, port: int) -> str | None:
    """A provider name not already taken, or None if none can be found.

    A name already held belongs to whoever holds it — detection never renames
    or repoints another provider. But refusing to register the runtime at all
    would mean a user whose own provider happens to be called `ollama` can
    never detect their actual Ollama, so the endpoint's port disambiguates.
    The port is also what separates two endpoints that identify as the same
    runtime, which keying by endpoint makes possible and keying by name hid.
    """
    for candidate in (name, f"{name}-{port}"):
        taken = (await session.execute(
            select(LlmProvider).where(LlmProvider.name == candidate)
        )).scalar_one_or_none()
        if taken is None:
            return candidate
    return None


async def _claim_default(session: AsyncSession) -> bool:
    """Whether a provider created now may become the default.

    An empty installation is the only one where detection may choose what
    inference runs against; anywhere else, adopting a provider is the user's
    decision to make explicitly.
    """
    total = (await session.execute(select(func.count()).select_from(LlmProvider))).scalar() or 0
    return total == 0


async def scan_local_ai(session: AsyncSession) -> dict:
    """Probe the candidate endpoints and reconcile ``source="detected"`` providers.

    Returns ``{"available", "detected", "needs_key", "message"}``. When
    detection is unavailable — no gateway address, or Kubernetes, where there
    is no host — nothing is probed and nothing is reconciled: "cannot tell" is
    not the same statement as "nothing is running", and reconciling on it would
    delete providers that are perfectly healthy.

    ``needs_key`` sits alongside ``detected`` rather than inside it. Those
    endpoints exist and are OpenAI-compatible, but no provider is created for
    them: a row carrying the keyless sentinel against a service that has just
    rejected it would be a provider guaranteed to fail, reported as a success.
    """
    if not is_local_detection_available():
        return {
            "available": False,
            "detected": [],
            "needs_key": [],
            "message": (
                "Local AI detection is not available for this deployment, because "
                "there is no container host to probe."
            ),
        }

    gateway = get_host_gateway_address()

    # Every configured endpoint, whatever its source. A detected provider's key
    # is used to probe its own endpoint and no other, and any configured
    # endpoint is one the caller has already dealt with — so it is never
    # offered for adoption again.
    configured = (await session.execute(select(LlmProvider))).scalars().all()
    adopted_keys = {
        p.base_url: p.api_key_encrypted for p in configured if p.source == "detected"
    }
    configured_urls = {p.base_url for p in configured}

    # Keyed by base_url, not by name. The endpoint is the stable identity of a
    # runtime; the name is a label the user is free to change. Keying by name
    # meant a renamed detected provider matched nothing on the next scan, so it
    # was reconciled away as departed — taking its model settings with it — and
    # re-created as a duplicate under the original name.
    detected: dict[str, dict] = {}
    needs_key: list[dict] = []
    # A runtime that answers at all is present, whether or not it will talk to
    # us. Only the ones that answer nothing have gone.
    present: set[str] = set()

    for port in candidate_ports():
        base_url = f"http://{gateway}:{port}/v1"
        stored = adopted_keys.get(base_url)
        api_key = decrypt_api_key(stored) if stored else DETECTED_API_KEY

        status, models_payload = await probe_local_endpoint(base_url, api_key)

        if status == ENDPOINT_NO_ANSWER:
            continue

        present.add(base_url)

        if status == ENDPOINT_UNAUTHORIZED:
            # Nothing beyond the endpoint is known: a 401 returns no body, so
            # asserting a runtime name or type here would be inventing one.
            if base_url not in configured_urls:
                needs_key.append({"base_url": base_url})
            continue

        detected[base_url] = {
            "name": identify_runtime(models_payload, port),
            "base_url": base_url,
            "provider_type": await probe_provider_type(base_url, api_key),
            "port": port,
        }

    claim_default = await _claim_default(session)

    now = datetime.now(timezone.utc)
    registered: list[dict] = []

    for base_url, info in detected.items():
        existing = (await session.execute(
            select(LlmProvider).where(
                LlmProvider.base_url == base_url,
                LlmProvider.source == "detected",
            )
        )).scalar_one_or_none()

        if existing is not None:
            # Its name is the user's to keep — they may have renamed it, and a
            # scan reconciles the endpoint, not the label. Its key is left
            # alone too: the probe just succeeded with whatever is stored, so
            # overwriting it with the sentinel would break an adopted runtime
            # on its first re-scan.
            existing.provider_type = info["provider_type"]
            existing.updated_at = now
            evict_client(existing.id)
            registered.append({**info, "name": existing.name})
            continue

        name = await _available_name(session, info["name"], info["port"])
        if name is None:
            logger.info(
                "Skipping detected runtime at %s: no available name for %r",
                base_url, info["name"],
            )
            continue

        session.add(LlmProvider(
            name=name,
            base_url=base_url,
            api_key_encrypted=encrypt_api_key(DETECTED_API_KEY),
            provider_type=info["provider_type"],
            is_default=claim_default,
            source="detected",
        ))
        await session.flush()
        # Only the first one — two runtimes found on an empty install must
        # not both claim the default.
        claim_default = False
        registered.append({**info, "name": name})

    # Reconcile: a runtime that has gone away should not leave a row behind.
    # One that answered but rejected its stored key has not gone away — a
    # rotated or revoked credential is not evidence of absence, and deleting
    # the provider would take its model settings with it. Saying that provider
    # is not currently usable is the reachability check's job.
    stale = (await session.execute(
        select(LlmProvider).where(LlmProvider.source == "detected")
    )).scalars().all()
    for provider in stale:
        if provider.base_url in present:
            continue
        evict_client(provider.id)
        await _clear_model_settings_for_provider(session, provider.id)
        await session.delete(provider)

    await session.commit()

    return {
        "available": True,
        "detected": [
            {k: v for k, v in info.items() if k != "port"} for info in registered
        ],
        "needs_key": needs_key,
        "message": None,
    }


async def adopt_local_runtime(
    session: AsyncSession,
    base_url: str,
    api_key: str,
    name: str | None = None,
) -> dict:
    """Create a detected provider for an endpoint, using a caller-supplied key.

    Probes with the key first and creates the provider only if it is accepted,
    so a key that does not work never becomes a stored credential.

    The outcome is a finding rather than a failure: the request was well formed
    and the probe ran, so what the probe found is reported as a result, the way
    the reachability check reports what it saw. The discriminator is whether a
    provider was created, because adoption can fail for reasons other than the
    key.

    The provider is created with ``source="detected"`` — that is what it is.
    Creating it as ``database`` would work on the first day and be wrong on the
    second, when the next scan found the same endpoint, still saw a 401, and
    offered it for adoption all over again.
    """
    status, models_payload = await probe_local_endpoint(base_url, api_key)

    if status == ENDPOINT_NO_ANSWER:
        return {
            "adopted": False,
            "reason": "unreachable",
            "message": f"Nothing answered at {base_url}.",
        }
    if status == ENDPOINT_UNAUTHORIZED:
        return {
            "adopted": False,
            "reason": "key_rejected",
            "message": "The runtime did not accept that API key.",
        }

    # Only now is there a response to read. Naming before this point would mean
    # naming from the candidate table, which is how an oMLX server on 8000
    # becomes `vllm`.
    resolved_name = name or identify_runtime(models_payload, port_of(base_url))

    taken = (await session.execute(
        select(LlmProvider).where(LlmProvider.name == resolved_name)
    )).scalar_one_or_none()
    if taken is not None:
        # The name was derived server-side after the key was accepted, so the
        # caller has never seen it and could not otherwise say which name to
        # avoid.
        return {
            "adopted": False,
            "reason": "name_conflict",
            "conflicting_name": resolved_name,
            "message": (
                f"A provider named {resolved_name!r} already exists. "
                "Supply a different name to adopt this runtime."
            ),
        }

    provider = LlmProvider(
        name=resolved_name,
        base_url=base_url,
        api_key_encrypted=encrypt_api_key(api_key),
        provider_type=await probe_provider_type(base_url, api_key),
        is_default=await _claim_default(session),
        source="detected",
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)

    return {"adopted": True, "provider": provider_to_dict(provider)}
