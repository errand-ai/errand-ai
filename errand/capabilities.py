"""Server capability detection for cloud registration.

Derives the list of capabilities from runtime configuration to report
to errand-cloud on WebSocket connect.
"""
import logging
import os
from pathlib import Path

import database
from models import LlmProvider, PlatformCredential, Setting
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Version file at project root (dev layout: errand/errand/capabilities.py → errand/VERSION)
# In Docker the errand/ contents are flat under /app/, so also check parent/VERSION.
_HERE = Path(__file__).resolve().parent
_VERSION_PATHS = [_HERE.parent / "VERSION", _HERE / "VERSION"]


def get_server_version() -> str:
    """Read server version from VERSION file. Returns 'unknown' on failure."""
    for path in _VERSION_PATHS:
        try:
            return path.read_text().strip()
        except (FileNotFoundError, OSError):
            continue
    return "unknown"


# The single set of capabilities advertised to consumers. This is the ONE
# capability source: it is sent to errand-cloud in the WebSocket `register`
# message (`cloud_client._send_register`) AND returned by `GET /api/capabilities`
# for the locally-served SPA. The shared `@errand-ai/ui-components` settings
# cards (desktop AND cloud) gate on the snake_case keys, so the Wave 1 keys MUST
# be snake_case — advertising kebab-case (`mcp-servers`) hides those cards.
ALWAYS_ON_CAPABILITIES = [
    # Wave 1 settings cards (snake_case — consumed by the shared card library).
    "system_prompt",
    "mcp_servers",
    "skills_git_repo",
    "task_management",
    "telemetry",
    # Wave 2 settings cards (snake_case — consumed by the shared card library).
    # `platforms` (below) is also a Wave 2 card key and is already advertised.
    # The kebab-case `task-profiles` below is a separate pre-Wave-1 key consumed
    # by errand-cloud; the Wave 2 TaskProfileListCard gates on `task_profiles`.
    "llm_providers",
    "llm_models",
    "task_profiles",
    # Pre-Wave-1 capabilities (consumed by errand-cloud for other features).
    "tasks",
    "settings",
    "task-profiles",
    "platforms",
]


async def _detect_conditional_capabilities(
    session: AsyncSession, capabilities: list[str]
) -> None:
    """Append DB-conditional capabilities in place, using ``session``."""
    # voice-input: a transcription model is configured.
    result = await session.execute(
        select(Setting).where(Setting.key == "transcription_model")
    )
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        capabilities.append("voice-input")

    # litellm_mcp: a LiteLLM proxy is detected (a `litellm` provider row, or the
    # legacy OPENAI_BASE_URL env var). This gates the LiteLLM MCP settings card,
    # which is what enables/disables servers — so it must appear whenever a proxy
    # exists, not only once servers have already been enabled.
    result = await session.execute(
        select(LlmProvider).where(LlmProvider.provider_type == "litellm").limit(1)
    )
    if result.scalar_one_or_none() is not None or os.environ.get("OPENAI_BASE_URL"):
        capabilities.append("litellm_mcp")

    # cloud_storage (OneDrive) / google_workspace (Google Drive): advertise the
    # settings card when the provider can actually be connected in this
    # deployment — via local OAuth client credentials OR a connected errand-cloud
    # OAuth proxy (plus any required MCP URL) — or is already connected. Gating on
    # local credentials alone hid these cards on cloud-connected deployments,
    # which use the proxy rather than local client id/secret.
    from integration_routes import _provider_available

    for provider, capability in (
        ("onedrive", "cloud_storage"),
        ("google_drive", "google_workspace"),
    ):
        available, _mode = await _provider_available(provider, session)
        if not available:
            row = await session.execute(
                select(PlatformCredential.platform_id).where(
                    PlatformCredential.platform_id == provider
                )
            )
            available = row.scalar_one_or_none() is not None
        if available:
            capabilities.append(capability)


async def get_capabilities(session: AsyncSession | None = None) -> list[str]:
    """Derive the capability list advertised to errand-cloud and the local SPA.

    Always-on keys are unconditional. Conditional keys reflect runtime config:
    - ``voice-input`` — a transcription model is configured
    - ``litellm_mcp`` — a LiteLLM proxy is detected
    - ``cloud_storage`` — OneDrive is connectable (local creds or cloud proxy) or connected
    - ``google_workspace`` — Google Drive is connectable (local creds or cloud proxy) or connected
    - ``jira`` — the Jira platform integration is registered

    Pass ``session`` to reuse a request-scoped session (e.g. the HTTP route);
    omit it and a session is opened internally (e.g. cloud registration).
    """
    capabilities = list(ALWAYS_ON_CAPABILITIES)

    try:
        from platforms import get_registry

        if get_registry().get("jira") is not None:
            capabilities.append("jira")
    except Exception:
        logger.debug("jira capability probe failed", exc_info=True)

    if session is not None:
        await _detect_conditional_capabilities(session, capabilities)
    else:
        async with database.async_session() as own_session:
            await _detect_conditional_capabilities(own_session, capabilities)

    return capabilities
