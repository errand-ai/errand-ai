"""Server capability detection for cloud registration.

Derives the list of capabilities from runtime configuration to report
to errand-cloud on WebSocket connect.
"""
import logging
import os
from pathlib import Path

import database
from models import LlmProvider, Setting
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


async def get_capabilities(session: AsyncSession | None = None) -> list[str]:
    """Derive the capability list advertised to errand-cloud and the local SPA.

    Always-on keys are unconditional. Conditional keys reflect runtime config:
    - ``voice-input`` — a transcription model is configured
    - ``litellm_mcp`` — a LiteLLM proxy is detected
    - ``cloud_storage`` — the OneDrive MCP URL is configured in this server build
    - ``jira`` — the Jira platform integration is registered

    Pass ``session`` to reuse a request-scoped session (e.g. the HTTP route);
    omit it and a session is opened internally (e.g. cloud registration).
    """
    capabilities = list(ALWAYS_ON_CAPABILITIES)

    # Env/registry checks need no DB session.
    if os.environ.get("ONEDRIVE_MCP_URL"):
        capabilities.append("cloud_storage")

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
